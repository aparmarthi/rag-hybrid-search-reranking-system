import type { NonStreamingResult, RecommendResponse } from './api';
import { CAPTURES } from './demo-captures';

// Real captured payloads (see demo-captures.ts), replayed when the live API is unreachable.
export const DEMO_GROUNDED: NonStreamingResult = CAPTURES['What did Apple say about iPhone supply chain in 2020?'];

export const DEMO_ABSTAINED: NonStreamingResult = CAPTURES['What did Apple say about iPhone sales in 2015?'];

const REFUSAL_PATTERN = /2015|2016|2017|2018|stock price|today|should i (buy|sell)|buy or sell/i;

export function pickDemoResult(question: string): NonStreamingResult {
  return CAPTURES[question] ?? (REFUSAL_PATTERN.test(question) ? DEMO_ABSTAINED : DEMO_GROUNDED);
}

// GET /recommend/AAPL on the live API, 2026-10-16.
export const DEMO_RECOMMEND: RecommendResponse = {
  ticker: 'AAPL',
  related: [
    { ticker: 'DLB', score: 0.4904 },
    { ticker: 'GOOGL', score: 0.4872 },
    { ticker: 'ADSK', score: 0.4375 },
    { ticker: 'NOW', score: 0.428 },
    { ticker: 'STX', score: 0.4197 },
  ],
};
