# FinSight — Deployment Playbook

**Purpose:** This is the artifact for the *forward-deployed* question — "would I send this person to a customer site?" It is deliberately not a benchmark table. It describes how FinSight would actually land in a real, constrained, regulated customer environment, what breaks, and how the system degrades rather than fails.

**Companion docs:** [decisions.md](decisions.md) (the war stories behind these choices), [architecture.md](architecture.md) (degradation topology), [PRD.md](PRD.md) §12 (risk register). The decision to make this a first-class artifact is logged as DEC-009.

---

## 1. The deployment scenario

**Customer:** a small long/short equity fund, $100M–$1B AUM (the PRD's primary ICP). Three analysts, one ops person, no dedicated ML team. They cannot afford Bloomberg ($24K/seat) or AlphaSense ($15K/seat). They want FinSight to cut the 3–4 hours/report spent cross-referencing earnings calls, SEC filings, and price action.

**Environment constraints that change the engineering:**

| Constraint | Implication |
|---|---|
| Regulated (SEC Rule 10b-5 liability on any numeric claim) | Faithfulness gate and citation precision are not "nice to have" — they are the contract. A wrong, confident number is worse than a refusal. |
| No customer ML team | Must run with zero hand-holding. Degraded mode has to be the *default* safe state, not a special case someone has to enable. |
| Data residency / API egress review | Cannot assume Voyage/Cohere/Anthropic egress is approved on day one. The system must be demonstrable *before* any managed API is cleared. |
| Their own document corpus, not our clean Kaggle set | Real filings are messy: missing periods, restated numbers, duplicate documents, OCR noise. The pipeline must survive dirty inputs. |

The job is not "make the demo work." It is "make the system trustworthy and operable in *their* environment, on *their* data, under *their* compliance constraints."

---

## 2. The messy-data reality (a war story, not a footnote)

The cleanest signal that this system was built by someone who has dealt with real data is what happened sourcing the OHLCV price data (full detail in [decisions.md](decisions.md) DEC-005):

- **yfinance** — first choice. 100% failure rate on a 100-ticker test after Yahoo's 2024 API change; it returned "possibly delisted" for *every* ticker, including AAPL/MSFT/NVDA.
- **Stooq bulk download** — gated behind a subscriber cookie; returned a landing page, not the zip.
- **Stooq per-ticker API** — required a captcha-gated API key; the captcha gate was unreachable at download time.
- **Alpha Vantage free** — 25 calls/day → ~4 days for 100 tickers.
- **Tiingo free** — 50/hour → ~2 hours, but fragile.

**What I did:** stopped burning time against paywalls and captchas, fell back to a known-good static dataset (Jackson Crow, clean Kaggle licensing), and *shifted the demo's center of gravity* to the March 2020 pandemic crash — the single richest event window in the corpus, where every major-cap ticker has a pre-COVID and a mid-crash earnings call with dramatic price moves between them. A sourcing constraint became a sharper demo.

**Why this is the FDE signal:** in a real engagement, the data source you were promised is broken half the time. The skill isn't avoiding that — it's recognizing the effort cap, falling back to something solid, and turning the constraint into a better story. For a production refresh I'd use a paid vendor (Polygon, Tiingo paid) and say so up front. That's documented, not hand-waved.

---

## 3. Rollout sequence — degraded-mode-first

The deployment order is deliberately inverted from how most demos are built. We stand up the *fully local, zero-egress* path first, then progressively enable managed APIs as the customer's compliance review clears each one. At every stage the system answers questions — it just gets better.

**Stage 0 — Local, zero external egress (demonstrable on day one, before any API review):**
- Embeddings: `BAAI/bge-m3` (MIT license, local).
- Reranker: `ms-marco-MiniLM-L-6-v2` (local cross-encoder).
- Vector store: Qdrant in Docker, on their infra.
- This is the documented fallback chain (see [architecture.md](architecture.md) degradation section and `src/retrieval/degradation.py`), promoted to the *starting* configuration. The customer sees a working, cited system with nothing leaving their network.

**Stage 1 — Enable domain embeddings (after Voyage egress clears):**
- Swap to `voyage-finance-2`. ~8–10% NDCG lift on financial retrieval (DEC-003). One config change; bge-m3 stays as the live fallback if the API is unavailable.

**Stage 2 — Enable managed reranking + synthesis (after Cohere/Anthropic clear):**
- Cohere Rerank 3.5 for retrieval quality; Claude Sonnet 4.6 for citation-enforced synthesis with Haiku routing and prompt caching.
- Each managed dependency has a local fallback already wired, so a single vendor outage degrades quality rather than taking the system down.

The point an interviewer should take away: **the safe state is the default, and every external dependency is optional and reversible.** That is what makes a system operable by a customer with no ML team.

---

## 4. What I'd validate *with* the customer before go-live

These are the conversations a forward-deployed engineer owns — not the model metrics, the deployment contract:

1. **Data licensing.** Our demo uses Motley Fool transcripts under ambiguous Kaggle redistribution terms; for the customer we run on *their* licensed corpus + public SEC filings (public domain). Licensing is settled before anything ships, not after. (See README data-licensing note.)
2. **PII / information boundaries.** Input guardrail (Presidio PII + jailbreak check) and the strict scope of "no buy/sell advice" (guardrail-blocked) are walked through with their compliance team, framed as enforceable controls.
3. **The trust gates as a contract.** Faithfulness ≥ 0.80, citation precision ≥ 0.90, abstention accuracy ≥ 0.85 (PRD §3–4) are presented as the SLA: *every numeric claim is traceable to a source, and the system refuses rather than guesses when it can't ground an answer.* In a 10b-5 environment, "it abstained" is a feature, not a miss.
4. **Failure observability.** The 5-category failure logger (retrieval_miss / bad_ranking / hallucination / ambiguous_query / stale_data) is visible to their ops person from day one, so problems are diagnosable without us on site.

---

## 5. The one-line version (for the interview)

> "I designed FinSight so the safe, fully-local mode is the *default* — it runs with no external API egress, which means I can stand it up at a regulated customer before a single vendor is cleared, then turn on domain embeddings, managed reranking, and Claude synthesis one approval at a time, each with a local fallback. When my price-data source broke in three different ways, I fell back to known-good data and made the demo sharper for it. That's the deployment I'd actually run."
