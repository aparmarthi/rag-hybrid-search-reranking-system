import type { NonStreamingResult, RecommendResponse } from './api';

// Representative captured payloads, replayed when the live API is unreachable.
const APPLE_ANSWER = `## Summary
Apple described iPhone supply in 2020 as **constrained first by COVID-19 factory closures in China**, then by a **staggered launch** of the iPhone 12 family, with supply recovering faster than expected by late in the year [1][2].

## Key points
- **Q2 FY20 (January call):** management widened its revenue guidance range to reflect uncertainty around China-based manufacturing partners after the Lunar New Year shutdown [1].
- **Recovery:** Tim Cook said iPhone supply partners had restarted and were "ramping production" faster than initially feared, though some components remained tight [2].
- **iPhone 12 timing:** Apple told investors the 2020 lineup would ship "a few weeks later" than the prior year, shifting a portion of revenue into the December quarter [4].
- **Constraints into Q1 FY21:** supply of certain iPhone 12 Pro models was expected to stay below demand through the holiday quarter [4].

## Caveat
The transcripts describe management commentary only; they do not quantify units lost to supply disruptions.`;

const APPLE_CHUNK_TEXTS = [
  `Luca Maestri, CFO: As we enter the March quarter, we are factoring in a wider-than-usual range for revenue to reflect the uncertainty around the coronavirus situation in China. Our suppliers' factories for iPhone are located in China, and we are reflecting the extended Lunar New Year closures in our outlook. We expect revenue to be between $63 billion and $67 billion. While we have a good level of visibility into the supply chain, the timing of the restart of production at certain partner sites is still evolving, and we have taken into account the potential for those restarts to be slower than the typical post-holiday ramp. We will continue to monitor the situation closely and work with our partners on contingency plans.\n\nTim Cook, CEO: We have alternate sources for some components, and our teams are working around the clock with suppliers. Where production has resumed, it is ramping more slowly than we would normally expect after the holiday. Our first priority remains the health and well-being of the people across our supply chain.`,
  `Tim Cook, CEO: I want to talk for a moment about supply. During the quarter, iPhone supply was temporarily affected by the closures of our partners' factories in China. By the end of the quarter, those factories had largely returned to normal operating levels and were ramping production faster than we had initially feared. We did see some constraints on certain components, and we expect some of those to persist into the June quarter, but overall the supply picture improved through the period. We are also grateful to the many people who worked to restart production safely.\n\nAnalyst: Could you give more color on the shape of the recovery?\n\nTim Cook: The recovery has been quicker on the supply side than on the demand side in some geographies. We think we are in a good position on supply as we head into the back half of the year.`,
  `Luca Maestri, CFO: Services revenue reached an all-time record, growing 16% year over year, with records in the App Store, cloud services, music and video, and payment services. Our installed base of active devices continues to grow and reached a new all-time high in all of our geographic segments. Wearables, Home and Accessories also set a new record, driven by Apple Watch and AirPods. We now have over 550 million paid subscriptions across the services on our platform, up 130 million from a year ago. We remain on track to reach our goal of 600 million paid subscriptions before the end of calendar 2020.`,
  `Luca Maestri, CFO: As you know, last year we started selling new iPhones in late September. This year, we project supply to be available a few weeks later, so that shifts a portion of iPhone revenue from the September quarter into the December quarter. For the December quarter, we expect supply of certain iPhone 12 models, particularly iPhone 12 Pro, to remain constrained relative to demand through the holiday season. We are working with our supply chain partners to increase output as quickly as possible.\n\nTim Cook, CEO: The response to the iPhone 12 lineup has been very strong. We are supply constrained on some models, and we are doing everything we can to get product into customers' hands.`,
  `Tim Cook, CEO: Our Mac business set a September-quarter record, driven by strong demand for MacBook Air and MacBook Pro as customers adapted to working and learning from home. iPad also grew strongly, with nearly half of iPad purchasers being new to the product. We continue to see remote work and remote learning as tailwinds for these categories, although we are mindful that some of that demand may have been pulled forward.`,
];

export const DEMO_GROUNDED: NonStreamingResult = {
  answer: APPLE_ANSWER,
  grounded: true,
  routing_path: 'earnings_analysis',
  rewritten_query: 'Apple iPhone supply chain constraints and production disruptions during 2020 earnings calls',
  staleness_flag: false,
  temporal_reference: { year: 2020, quarter: null },
  conflicts: [],
  citations: [
    { chunk_number: 1, source_label: 'AAPL earnings_transcript 2020-01-28' },
    { chunk_number: 2, source_label: 'AAPL earnings_transcript 2020-04-30' },
    { chunk_number: 4, source_label: 'AAPL earnings_transcript 2020-10-29' },
  ],
  chunks: [
    { chunk_id: 'AAPL_2020-01-28_017', ticker: 'AAPL', doc_type: 'earnings_transcript', date: '2020-01-28', score: 0.912, text: APPLE_CHUNK_TEXTS[0] },
    { chunk_id: 'AAPL_2020-04-30_009', ticker: 'AAPL', doc_type: 'earnings_transcript', date: '2020-04-30', score: 0.874, text: APPLE_CHUNK_TEXTS[1] },
    { chunk_id: 'AAPL_2020-07-30_012', ticker: 'AAPL', doc_type: 'earnings_transcript', date: '2020-07-30', score: 0.891, text: APPLE_CHUNK_TEXTS[2] },
    { chunk_id: 'AAPL_2020-10-29_021', ticker: 'AAPL', doc_type: 'earnings_transcript', date: '2020-10-29', score: 0.803, text: APPLE_CHUNK_TEXTS[3] },
    { chunk_id: 'AAPL_2020-10-29_006', ticker: 'AAPL', doc_type: 'earnings_transcript', date: '2020-10-29', score: 0.655, text: APPLE_CHUNK_TEXTS[4] },
  ],
  latency_ms: 13240,
  latency_per_node_ms: { query_understanding: 1480, router: 790, retrieve: 410, rerank: 1870, detect_conflicts: 0 },
  tokens: { input: 3412, output: 286, cache_read: 0 },
  cost_usd: 0.0145,
  failure_mode: null,
};

export const DEMO_ABSTAINED: NonStreamingResult = {
  answer:
    'INSUFFICIENT EVIDENCE\n\nThe retrieved transcripts do not contain information that answers this question. The corpus covers earnings calls from 2019 to 2023 and does not include live market data or investment recommendations.',
  grounded: false,
  routing_path: 'earnings_analysis',
  rewritten_query: 'question outside earnings-call transcript coverage',
  staleness_flag: false,
  temporal_reference: { year: null, quarter: null },
  conflicts: [],
  citations: [],
  chunks: [],
  latency_ms: 6840,
  latency_per_node_ms: { query_understanding: 1520, router: 810, retrieve: 390, rerank: 1870, detect_conflicts: 0 },
  tokens: { input: 612, output: 48, cache_read: 0 },
  cost_usd: 0.0031,
  failure_mode: null,
};

const REFUSAL_PATTERN = /2015|2016|2017|2018|stock price|today|should i (buy|sell)|buy or sell/i;

export function pickDemoResult(question: string): NonStreamingResult {
  return REFUSAL_PATTERN.test(question) ? DEMO_ABSTAINED : DEMO_GROUNDED;
}

export const DEMO_RECOMMEND: RecommendResponse = {
  ticker: 'AAPL',
  related: [
    { ticker: 'MSFT', score: 0.82 },
    { ticker: 'AMZN', score: 0.77 },
    { ticker: 'GOOGL', score: 0.74 },
    { ticker: 'NVDA', score: 0.69 },
  ],
};
