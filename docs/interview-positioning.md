# FinSight — Interview Positioning

**Purpose:** FinSight's narrative and artifact map for interviews, kept separate from the technical spec. One project, several audiences. This document says which artifact answers which interviewer's core question, and how to narrate the same project to an IC vs. a leadership panel.

**Scope:** generic to the target role band across AI-native companies. No company-specific tailoring lives here — that's a per-conversation overlay, not a document.

---

## 1. The target role band

FinSight is positioned for one coherent band of roles:

- **Forward-Deployed Engineer (FDE)** and **FDE Lead / Manager**
- **Director** (technical / applied)
- **Principal Solutions Architect (SA)**
- **Technical Program Manager (TPM)**
- **AI Product Manager (PM)**

What unifies them: every one is a **technical-credibility + customer/stakeholder-judgment** seat. They sit between a hard problem and the people who have it. **None is a deep-research or pure-MLE seat** — which is exactly why the project deliberately invests in deployment judgment, decision rationale, and product framing over benchmark depth (logged as DEC-009).

The project's job in these interviews is to prove: *I can own an ambiguous problem end-to-end, make defensible tradeoffs under real constraints, and ship something a customer or stakeholder would trust.*

---

## 2. Role → what they value → the artifact that answers it

| Role | Core question they're screening for | Lead artifact | Backed by |
|---|---|---|---|
| **Principal SA** | "Can you reason about enterprise risk and defend architecture tradeoffs cold?" | The retrieval ablation (hybrid+rerank beats dense by X% NDCG at $Y/query) + the tech-stack tradeoff table | [decisions.md](decisions.md) DEC-002/003, [architecture.md](architecture.md) |
| **FDE** | "Would I send you to a customer site with messy data and no ML team?" | [deployment-playbook.md](deployment-playbook.md) — degraded-mode-first rollout + the DEC-005 messy-data war story | [decisions.md](decisions.md) DEC-005, degradation chain |
| **FDE Lead / Manager** | "Can you lead engineers *and* still own the customer relationship?" | Deployment playbook (credibility) + the program artifacts (leadership) | The two-narrations split below |
| **Director** | "Can you set technical direction and make scope calls under constraint?" | The 5-week plan + risk register + weekly ship-vs-defer cuts | [finsight_spec_v2.3.md](finsight_spec_v2.3.md) §5/§9, DEC-009 |
| **TPM** | "Can you scope, sequence risk, and run a program to delivery?" | Same program artifacts, framed as program management: cut 55% of scope, front-loaded deployment risk, weekly cut decisions | [finsight_spec_v2.3.md](finsight_spec_v2.3.md) §0/§5/§9 |
| **AI PM** | "Do you think in problem / user / metric / ROI / responsible-AI terms?" | [PRD.md](PRD.md) — problem, ICP, North Star + guardrail metrics, ROI math, competitive landscape | PRD §3/§4/§10, trust framing below |

**Reading the table:** almost every artifact already exists. The positioning work is making sure the *right* one leads for each audience, not building new material per role.

---

## 3. One project, two narrations

The same project carries an IC and a leadership story. Don't build two projects — rehearse two emphases.

**IC framing (FDE, Principal SA):**
> "I designed and built this." Architecture, the retrieval tradeoffs, the real numbers, and the live demo lead. The code and the system *are* the evidence.

**Leader framing (FDE Lead/Manager, Director, TPM, AI PM):**
> "I scoped this, sequenced the risk, made the cut decisions, and can lead engineers on it *because* I've done the work." The decisions log, the 5-week plan, the risk register, and the ROI framing lead; the code is proof of credibility, not the headline.

The bridge between them is the decisions log and the program artifacts — they let you flip register on demand inside a single conversation (e.g. a panel that mixes an IC and a hiring manager).

---

## 4. The trustworthy-AI frame (universal across AI-native companies)

The single anxiety every AI-native company shares in 2026 is **confident hallucination**. FinSight was built to answer it, so lead with that framing rather than "RAG with reranking":

> "I built a financial RAG system that **knows what it doesn't know**: it refuses when it can't ground an answer, flags stale evidence, and surfaces contradictions between sources instead of confidently averaging them."

The ingredients already exist — this is a relabel, not new work:
- **Evidence Conflict Detector** → surfaces source disagreement instead of papering over it. (The differentiator; PRD Journey 2.)
- **Faithfulness / citation-precision gates** → every numeric claim is traceable or it doesn't ship. (PRD §3–4.)
- **Abstention accuracy** → measured ability to say "I don't know." (PRD §4.)
- **Temporal staleness check** → flags time-sensitive financial data that's gone stale.

Why it travels across the whole role band: it reads as *customer trust* to an FDE, *enterprise risk control* to an SA, *responsible-AI product thinking* to a PM, and *a guardrail to own* to a TPM — from one set of features.

---

## 5. The five interview moments (where to steer the conversation)

Per [finsight_spec_v2.3.md](finsight_spec_v2.3.md) §7, the project is built so you can steer any conversation toward one of these:

1. **"Let me show you the live demo"** — the conflict detector with a real example.
2. **"The architecture is a 6-node LangGraph DAG"** — whiteboard from architecture.md.
3. **"Here's the ablation: hybrid+rerank beats dense-only by X% NDCG at $Y/query"** — a real number.
4. **"Cost routing cuts spend ~55% — Haiku for intent, Sonnet only for synthesis, prompt caching at 80%+ hit rate"** — production thinking.
5. **"Retrieval and recommendation are the same problem — I reused the embeddings for related-ticker recs on shared infrastructure"** — architecture thinking.

For this role band, add a sixth that the playbook unlocks:

6. **"Here's how I'd actually deploy this at a regulated customer"** — degraded-mode-first rollout + the messy-data war story ([deployment-playbook.md](deployment-playbook.md)). This is the moment that separates "built a cool project" from "I'd hire this person to sit in front of my customer."
