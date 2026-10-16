export const LINKS = {
  github: 'https://github.com/aparmarthi/rag-hybrid-search-reranking-system',
  streamlit: 'https://finsight-ui-995576020018.us-central1.run.app',
  wandb: 'https://wandb.ai/ameyparmarthi-finsight/finsight-biencoder-finetune',
};

export interface ExampleGroup {
  id: 'grounded' | 'conflict' | 'refuse';
  label: string;
  hint: string;
  questions: { text: string; tag?: string }[];
}

export const EXAMPLE_GROUPS: ExampleGroup[] = [
  {
    id: 'grounded',
    label: 'Grounded',
    hint: 'Answered with cited transcript evidence',
    questions: [
      { text: 'What did Apple say about iPhone supply chain in 2020?' },
      { text: 'What did companies say about COVID-19 supply chain disruptions?' },
      { text: 'Oracle cloud revenue growth' },
      {
        text: "How did Tesla's Shanghai Model 3 margins compare to Model 3 margins produced in Fremont during Q1 2020?",
        tag: 'golden-set g002',
      },
    ],
  },
  {
    id: 'conflict',
    label: 'Conflict check',
    hint: 'Slower: runs the guidance-vs-actual extraction node',
    questions: [
      { text: 'Did company revenue guidance match actual results?' },
      { text: 'How did management revise its full-year outlook over the year?' },
    ],
  },
  {
    id: 'refuse',
    label: 'Watch it refuse',
    hint: 'Honest abstention instead of a guess',
    questions: [
      { text: 'What did Apple say about iPhone sales in 2015?', tag: 'before the corpus' },
      { text: 'What is the current stock price of Tesla today?', tag: 'not a transcript' },
      { text: 'Should I buy or sell Nvidia stock?', tag: 'advice guardrail' },
    ],
  },
];

export const ROUTING_PATHS: { id: string; description: string }[] = [
  { id: 'earnings_analysis', description: 'What management said on earnings calls; answered from the transcript corpus.' },
  { id: 'financial_metrics', description: 'Reported fundamentals. SEC data is not ingested yet, so these abstain rather than guess.' },
  { id: 'risk_and_events', description: 'Risk factors and material events. Same interim state: honest abstention until SEC filings land.' },
];

export const PIPELINE_STAGES = [
  { label: 'Understanding query', ms: 1500 },
  { label: 'Routing', ms: 800 },
  { label: 'Retrieving', ms: 400 },
  { label: 'Reranking', ms: 1900 },
  { label: 'Checking conflicts', ms: 400 },
  { label: 'Generating', ms: Infinity },
] as const;

export const CORPUS = { chunks: 15023, tickers: 76, years: '2019–2023' };
