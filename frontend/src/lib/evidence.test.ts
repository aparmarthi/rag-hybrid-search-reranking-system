import { describe, expect, it } from 'vitest';
import type { EvidenceChunk } from './api';
import { citationCounts, formatDate, formatScope, isAbstention, linkCitations, mostCitedTicker, parseSourceLabel } from './evidence';

const chunk = (ticker: string): EvidenceChunk => ({ chunk_id: ticker, ticker, doc_type: 'earnings_transcript', date: '2020-01-28', score: 0.9, text: '' });

describe('citationCounts', () => {
  it('counts single and grouped markers', () => {
    const counts = citationCounts('Revenue grew [1]. Margins held [1, 2]. Supply eased [4;2].');
    expect(Object.fromEntries(counts)).toEqual({ 1: 2, 2: 2, 4: 1 });
  });

  it('ignores markdown links and non-numeric brackets', () => {
    expect(citationCounts('See [docs](https://x.y) and [note] and [a1]').size).toBe(0);
  });

  it('returns empty for an answer without citations', () => {
    expect(citationCounts('INSUFFICIENT EVIDENCE').size).toBe(0);
  });
});

describe('linkCitations', () => {
  it('expands grouped markers into one anchor per chunk', () => {
    expect(linkCitations('Claim [1, 3].')).toBe('Claim [1](#cite-1)[3](#cite-3).');
  });

  it('leaves existing markdown links untouched', () => {
    const md = 'Read [2](#cite-2) then [x](https://a.b)';
    expect(linkCitations(md)).toBe(md);
  });
});

describe('isAbstention', () => {
  it('detects the sentinel regardless of case and leading whitespace', () => {
    expect(isAbstention({ grounded: true }, '  insufficient evidence\nnothing found')).toBe(true);
  });

  it('falls back to grounded=false', () => {
    expect(isAbstention({ grounded: false }, 'Partial answer')).toBe(true);
    expect(isAbstention({ grounded: true }, 'Grounded answer [1]')).toBe(false);
  });

  it('is false mid-stream before a result exists', () => {
    expect(isAbstention(null, 'Apple said')).toBe(false);
  });
});

describe('mostCitedTicker', () => {
  it('maps [N] to chunks[N-1] without re-sorting', () => {
    const chunks = [chunk('AAPL'), chunk('MSFT'), chunk('MSFT')];
    expect(mostCitedTicker(chunks, new Map([[1, 1], [2, 1], [3, 1]]))).toBe('MSFT');
  });

  it('ignores out-of-range citations and falls back to the first chunk', () => {
    expect(mostCitedTicker([chunk('TSLA')], new Map([[9, 3]]))).toBe('TSLA');
  });
});

describe('formatting', () => {
  it('formats ISO dates and passes through unknown shapes', () => {
    expect(formatDate('2020-01-28T00:00:00')).toBe('Jan 28, 2020');
    expect(formatDate('Q1 2020')).toBe('Q1 2020');
  });

  it('parses source labels', () => {
    expect(parseSourceLabel('AAPL earnings_transcript 2020-01-28')).toEqual({ ticker: 'AAPL', docType: 'earnings_transcript', date: '2020-01-28' });
  });

  it('formats temporal scope', () => {
    expect(formatScope({ year: 2020, quarter: 1 })).toBe('Q1 2020');
    expect(formatScope({ year: 2021, quarter: null })).toBe('2021');
    expect(formatScope({ year: null, quarter: null })).toBeNull();
  });
});
