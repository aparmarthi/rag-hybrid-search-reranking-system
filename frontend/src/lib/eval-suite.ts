import type { NonStreamingResult } from './api';
import { EXAMPLE_GROUPS, type ExampleGroup } from './constants';
import { citationCounts, isAbstention } from './evidence';

export type Expectation = ExampleGroup['id'];

export interface EvalCase {
  id: string;
  question: string;
  expect: Expectation;
  tag?: string;
}

export interface EvalCheck {
  label: string;
  pass: boolean;
  detail: string;
}

export interface EvalCaseResult {
  caseId: string;
  status: 'pass' | 'fail' | 'error';
  checks: EvalCheck[];
  error?: string;
  result?: NonStreamingResult;
  wallMs: number;
}

export const EXPECTATION_LABEL: Record<Expectation, string> = {
  grounded: 'Grounded answer',
  conflict: 'Conflict node runs',
  refuse: 'Abstains',
};

export const EVAL_CASES: EvalCase[] = EXAMPLE_GROUPS.flatMap((group) =>
  group.questions.map((q, i) => ({
    id: `${group.id}-${i + 1}`,
    question: q.text,
    expect: group.id,
    tag: q.tag,
  })),
);

function citationIntegrity(r: NonStreamingResult): EvalCheck {
  const n = r.chunks.length;
  const inline = [...citationCounts(r.answer).keys()];
  const structured = r.citations.map((c) => c.chunk_number);
  const bad = [...new Set([...inline, ...structured])].filter((k) => k < 1 || k > n);
  return {
    label: 'Citation integrity',
    pass: bad.length === 0,
    detail:
      bad.length === 0
        ? `All ${new Set([...inline, ...structured]).size} cited numbers map to one of ${n} returned passages`
        : `Citation${bad.length > 1 ? 's' : ''} ${bad.map((b) => `[${b}]`).join(', ')} point outside the ${n} returned passages`,
  };
}

function expectationCheck(c: EvalCase, r: NonStreamingResult): EvalCheck {
  const abstained = isAbstention(r, r.answer);
  switch (c.expect) {
    case 'grounded': {
      const pass = !abstained && r.citations.length > 0;
      return {
        label: EXPECTATION_LABEL.grounded,
        pass,
        detail: abstained
          ? 'System abstained on an in-corpus question'
          : `Answered with ${r.citations.length} citation${r.citations.length === 1 ? '' : 's'}`,
      };
    }
    case 'conflict': {
      const ms = r.latency_per_node_ms.detect_conflicts;
      return {
        label: EXPECTATION_LABEL.conflict,
        pass: ms > 0,
        detail: ms > 0 ? `Conflict detection ran (${Math.round(ms)} ms, ${r.conflicts.length} found)` : 'Conflict node was gated off',
      };
    }
    case 'refuse':
      return {
        label: EXPECTATION_LABEL.refuse,
        pass: abstained,
        detail: abstained ? 'Declined to answer without evidence' : 'Produced an answer where abstention was expected',
      };
  }
}

export function scoreCase(c: EvalCase, r: NonStreamingResult, wallMs: number): EvalCaseResult {
  const checks = [expectationCheck(c, r), citationIntegrity(r)];
  return {
    caseId: c.id,
    status: checks.every((k) => k.pass) ? 'pass' : 'fail',
    checks,
    result: r,
    wallMs,
  };
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, idx)];
}

export interface EvalSummary {
  total: number;
  passed: number;
  failed: number;
  errored: number;
  byExpectation: Record<Expectation, { passed: number; total: number }>;
  integrityPassed: number;
  integrityTotal: number;
  p50Ms: number;
  p95Ms: number;
  totalCostUsd: number;
  avgCostUsd: number;
  tokensIn: number;
  tokensOut: number;
}

export function summarize(results: EvalCaseResult[]): EvalSummary {
  const byExpectation: EvalSummary['byExpectation'] = {
    grounded: { passed: 0, total: 0 },
    conflict: { passed: 0, total: 0 },
    refuse: { passed: 0, total: 0 },
  };
  const caseById = new Map(EVAL_CASES.map((c) => [c.id, c]));
  const latencies: number[] = [];
  let integrityPassed = 0;
  let integrityTotal = 0;
  let totalCostUsd = 0;
  let tokensIn = 0;
  let tokensOut = 0;

  for (const r of results) {
    const c = caseById.get(r.caseId);
    if (c) {
      byExpectation[c.expect].total += 1;
      if (r.checks[0]?.pass) byExpectation[c.expect].passed += 1;
    }
    if (r.result) {
      latencies.push(r.result.latency_ms);
      totalCostUsd += r.result.cost_usd ?? 0;
      tokensIn += r.result.tokens.input;
      tokensOut += r.result.tokens.output;
      integrityTotal += 1;
      if (r.checks[1]?.pass) integrityPassed += 1;
    }
  }

  latencies.sort((a, b) => a - b);
  const answered = results.filter((r) => r.result).length;
  return {
    total: results.length,
    passed: results.filter((r) => r.status === 'pass').length,
    failed: results.filter((r) => r.status === 'fail').length,
    errored: results.filter((r) => r.status === 'error').length,
    byExpectation,
    integrityPassed,
    integrityTotal,
    p50Ms: percentile(latencies, 50),
    p95Ms: percentile(latencies, 95),
    totalCostUsd,
    avgCostUsd: answered ? totalCostUsd / answered : 0,
    tokensIn,
    tokensOut,
  };
}
