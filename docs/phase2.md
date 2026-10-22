# Phase 2: scale up

Phase 1 is built for one fact: the knowledge base is four pages, about 2,100 tokens. Phase 2
is what changes when tickets grow past 10,000 a month and the KB grows into SOPs, product
pages and internal procedures. Each step below has a trigger, so it is done when the numbers
ask for it, not before.

## 1. Rollout: shadow, five agents, everyone

| stage | what agents see | exit criterion |
|---|---|---|
| Shadow, 1–2 weeks | nothing; the co-pilot runs on live tickets and only writes traces and cards | hard-rule violations 0 on a sample read by the support lead; "draft ready" precision ≥ 90% on that sample |
| Pilot, 5 agents | cards in the help desk, a "used / edited / discarded" button on every draft | edit distance and discard rate stable for a week; no complaint about a sent draft |
| Everyone | same, with per-agent opt-out | weekly review keeps the numbers inside the limits below |

Rollback is a flag that hides cards; the pipeline keeps writing traces, so shadow mode is
also the fallback.

## 2. The weekly loop: miss → case → fix → re-run

Once a week, 30–60 minutes, the AI engineer and the support lead:

1. **Pull misses** from the traces and agent feedback: discarded drafts, drafts edited by more
   than a threshold, routes the agent overrode, any hard-rule hit. Traces carry the KB version
   hash and prompt version, so every miss is tied to what produced it.
2. **Turn each miss into a case** in `evals/tickets.jsonl`: the masked ticket and the expected
   labels. A miss that is not a case will come back.
3. **Fix the cause, not the case**: a KB edit (most common: see [kb-issues.md](kb-issues.md)),
   a threshold, a classifier question, a prompt rule, or a new deterministic check. Not a
   string match for that one ticket.
4. **Re-run the golden set** on every change to KB, prompt, model or thresholds; merge only if
   hard-rule violations stay at 0 and route accuracy does not drop outside its interval.
5. **Grow the holdout**: one in four new cases goes to the holdout split nobody tunes on.

The goal from the hiring call is that the head of support runs steps 1–2 alone: the cases are
plain JSON lines and the KB is a TOML file.

## 3. KB as owned content

- Every section gets an **owner** and a **review-by date** in `kb/*.toml`; a CI check fails
  when a cited section is past its date.
- Conflicts are fixed at the source; the `conflict` tag is a temporary state with an owner.
- New sources (SOPs, account types, payment methods by country) arrive as new sections with
  the same id scheme. SOPs that drive actions (refund rules, KYC checklists) stay internal and
  are marked so the drafter can use them for the agent but never quote them to a client.

## 4. Retrieval, when the KB stops fitting

Trigger: the KB passes about 30–50k tokens, or ticket types need disjoint sources.
Until then the whole KB in a cached prompt is cheaper and has no retrieval misses.

- **Hybrid retrieval**: BM25 for exact terms (USDT, TRC20, ECN, error codes) plus multilingual
  embeddings for paraphrases and non-English tickets, merged with reciprocal rank fusion, then
  a cross-encoder reranker on the top 20–30.
- **Route first**: the classifier's category narrows the corpus (withdrawal SOPs for
  withdrawal tickets) before search.
- **A retrieval eval of its own**: for each golden case, the expected section ids; measure
  recall@k before the drafter sees anything. A drafter failure and a retrieval failure need
  different fixes.
- The grounding check does not change: it already checks claims against the cited text only.

## 5. Classifier: from zero-shot to fine-tuned

- After 4–8 weeks of pilot, agents' corrections give a few thousand labelled tickets.
- Fine-tune Laya on them (its notebook supports Apple Silicon and T4); the README reports
  0.362 → 0.766 accuracy from fine-tuning on another typed-decision workload.
- Fit per-question thresholds on held-out data instead of the hand-set ones in
  `routing.Thresholds`, with a target error per flag (stricter for trading advice and AML).
- Keep Jev and the fine-tuned Laya on the same `/v1/systemone` contract and compare them on
  the golden set; pick by accuracy at the required recall on reserved topics.

## 6. Cost and model routing

- Default drafter: the smallest model that holds 0 violations and the target route accuracy
  on the golden set (Haiku in phase 1, see [evals.md](evals.md)).
- Escalate to a larger model only by rule: a multi-intent ticket, a low classifier margin, or
  a grounding failure on the first attempt (one retry, then a person).
- A monthly token budget with an alert at 80%; per-ticket cost is in every trace line.
- Batch API at half price for anything not latency-bound (re-scoring, nightly shadow runs).

## 7. Production integration

- Help-desk webhook in, card out to the agent's sidebar; the CLI and static page are stand-ins.
- Traces to the existing log stack; dashboards on route mix, abstain rate, violations, p95
  latency and cost per ticket, split by KB and prompt version.
- Secrets in the platform secret store; the TypeSafe and Anthropic keys never in config files.
- For data residency, Laya runs inside the perimeter and only masked text leaves it; the
  drafter can move to a provider region or a self-hosted model the same way.
