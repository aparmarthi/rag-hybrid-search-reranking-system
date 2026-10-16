import { describe, expect, it } from 'vitest';
import type { NonStreamingResult } from './api';
import { DEMO_ABSTAINED, DEMO_GROUNDED } from './demo';
import { EVAL_CASES, scoreCase, summarize, type EvalCase } from './eval-suite';

const grounded: EvalCase = { id: 'g', question: 'q', expect: 'grounded' };
const refuse: EvalCase = { id: 'r', question: 'q', expect: 'refuse' };
const conflict: EvalCase = { id: 'c', question: 'q', expect: 'conflict' };

describe('scoreCase', () => {
  it('passes a grounded answer with valid citations', () => {
    expect(scoreCase(grounded, DEMO_GROUNDED, 1).status).toBe('pass');
  });

  it('fails citation integrity when [N] exceeds the returned chunks', () => {
    const bad: NonStreamingResult = { ...DEMO_GROUNDED, answer: `${DEMO_GROUNDED.answer} Also [9].` };
    const r = scoreCase(grounded, bad, 1);
    expect(r.status).toBe('fail');
    expect(r.checks[1].pass).toBe(false);
    expect(r.checks[1].detail).toContain('[9]');
  });

  it('fails a grounded case when the system abstains', () => {
    expect(scoreCase(grounded, DEMO_ABSTAINED, 1).checks[0].pass).toBe(false);
  });

  it('passes a refusal case on abstention', () => {
    expect(scoreCase(refuse, DEMO_ABSTAINED, 1).status).toBe('pass');
  });

  it('requires the conflict node to have run', () => {
    const gated = { ...DEMO_GROUNDED, latency_per_node_ms: { ...DEMO_GROUNDED.latency_per_node_ms, detect_conflicts: 0 } };
    const ran = { ...DEMO_GROUNDED, latency_per_node_ms: { ...DEMO_GROUNDED.latency_per_node_ms, detect_conflicts: 15000 } };
    expect(scoreCase(conflict, gated, 1).checks[0].pass).toBe(false);
    expect(scoreCase(conflict, ran, 1).checks[0].pass).toBe(true);
  });
});

describe('summarize', () => {
  it('aggregates pass rate, abstention accuracy, and cost, excluding errored cases from latency', () => {
    const [g, , , , , , r] = EVAL_CASES;
    const results = [
      scoreCase(g, DEMO_GROUNDED, 1),
      scoreCase(r, DEMO_ABSTAINED, 1),
      { caseId: EVAL_CASES[1].id, status: 'error' as const, checks: [], error: 'timeout', wallMs: 1 },
    ];
    const s = summarize(results);
    expect(s.passed).toBe(2);
    expect(s.errored).toBe(1);
    expect(s.byExpectation.refuse).toEqual({ passed: 1, total: 1 });
    expect(s.integrityTotal).toBe(2);
    expect(s.totalCostUsd).toBeCloseTo(DEMO_GROUNDED.cost_usd + DEMO_ABSTAINED.cost_usd);
  });

  it('every example question is covered by the suite', () => {
    expect(new Set(EVAL_CASES.map((c) => c.id)).size).toBe(EVAL_CASES.length);
    expect(EVAL_CASES.some((c) => c.expect === 'refuse')).toBe(true);
  });
});
