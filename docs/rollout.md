# Rollout: stages, promotion and stop criteria, scaling triggers

A plan: nothing here has run on live traffic. The starting numbers are the evals
([evals.md](evals.md)) and the break-even of the business case
([business-case.md](business-case.md)): **a ready draft pays if it saves $0.16 of agent time,
3% of a $5 contact.** At 10,000 tickets a month the team gets about 2,300 tickets a week.

**Zero is a bound.** No violation in N reviewed drafts puts the rate below 1 − 0.05^(1/N) with
95% confidence, about 3/N: 100 → 3.0%, 300 → 1.0%, 1,000 → 0.3%, 3,000 → 0.1%. Every "0" below
comes with its N.

## Stages

| | 0. Shadow | 1. Assist pilot | 2. All agents | 3. Auto-send (maybe never) |
|---|---|---|---|---|
| agents see | nothing; cards and traces only | cards for 5 agents on half their tickets, by ticket hash (the other half is the control, still traced); "used / edited / discarded" on each draft | cards for everyone, per-agent opt-out; 10% of tickets kept as control | no agent for one narrow category, at 1% → 10% → 50% → 100% of it, a week per step |
| entry | CI green (`evals.gate`), golden 0 of 80 and blind 0 of 60 violations; help-desk webhook read-only; traces flowing | stage 0 exit | stage 1 exit | per category: stage 2 for ≥ 3 months, compliance sign-off, AI disclosure in the reply |
| minimum | 2 weeks, ~4,600 tickets | 4 weeks and ≥ 1,000 assisted replies | 8 weeks | ≥ 3,000 drafts in the category |
| exit | 0 hard-rule violations in ≥ 300 reviewed ready drafts (≤ 1.0%); 0 missed escalations on all tickets; ≥ 90% of reviewed ready drafts sendable with no or minor edits; live ready share ≥ 15% | 0 violations in ≥ 300 read and all 1,000+ auto-checked sent replies; 0 missed escalations; ≥ 60% of ready drafts sent with no or minor edits, ≤ 20% discarded; handling time saving ≥ 3% (point estimate); CSAT not below control | handover: the support lead runs the weekly loop alone for 4 weeks, all limits held | 0 violations in ≥ 3,000 (≤ 0.1%); reopen rate and CSAT not worse than agent-sent replies in the category; only sections with no `conflict` or `defect` tag |
| stop | any violation or missed escalation in the sample → fix and restart the 2 weeks | any violation in a sent reply; any missed escalation; discard > 30% in a week; a client complaint about an assisted reply; vendor failures > 5% or p95 > 30 s for a day | as stage 1, plus rubber-stamping: an agent sends > 95% of drafts unedited within 15 s of opening | any violation, any reopen caused by the reply; back to stage 2 for that category |
| decides | support lead + AI lead | same | same | same + compliance |

**Rollback** is a config flag, read per ticket, no deploy: `cards: off | shadow | on` per
agent, category and language. `shadow` keeps the traces, so every rollback still measures.
Either lead stops alone; a restart or a promotion needs both, written in the weekly note.

**Stage 3 may never come.** The KB contradicts itself on verification and credit times
([kb-issues.md](kb-issues.md)); a category that cites those sections never qualifies.

## Metrics

| metric | definition | source | limit |
|---|---|---|---|
| hard-rule violations | advice, a complaint/KYC/AML outcome, an invented fee or time, in a draft shown or a reply sent | support lead's sample; the reply and number checks rerun on every sent text | 0, with its N |
| missed escalations | a ticket the help desk tags complaint, KYC, AML or advice that the co-pilot routed "draft ready" | trace route joined to help-desk tags, all tickets | 0 |
| needless escalations | "needs a person" where the agent sent the draft unchanged, or the reviewer marks "no person needed" | card buttons, sample | watch; live ready share ≥ 15% |
| sent with no / minor edits | normalised character edit distance draft → sent reply: 0, < 0.4, ≥ 0.4, or discarded; 0.4 is a vendor rule of thumb we validate on the sample | help-desk send event; only the number enters the trace | ≥ 60% no/minor |
| handling time | agent active time from open to reply, ready-draft tickets vs control tickets the co-pilot would have marked ready (control is randomised by ticket and still traced) | help desk + trace | saving ≥ 3% |
| CSAT, complaints | survey score and complaints on assisted vs control tickets | help desk | not below control |
| cost per ticket | trace tokens × list prices (`evals/prices.py`) | trace | ≤ $0.002 (measured $0.00049 cold); budget alert at 80% |
| p95 latency | ticket in → card ready | trace `timings_ms` | ≤ 15 s (CLI measured 8.3 s) |
| vendor failures | tickets with `error` set (they go to a person with no draft) | trace | ≤ 1% a week |

The trace line exists today; card buttons, the edit distance and the help-desk joins come
with the help-desk integration ([phase2.md §7](phase2.md#7-production-integration)).

**Tied to break-even.** A pilot cannot resolve a 3% saving, but it can tell 15% (the low case)
from 3%: n per arm ≈ 2·CV²·(2.8 / 0.12)² ≈ 1,090·CV² ready-draft tickets (80% power, 95%
bound, 15% true saving against 3%), CV being the coefficient of variation of handling time,
read from the help desk in shadow (CV 0.8 → ~700 per arm). With 5 agents that may take 2–3 months, so stage 1 → 2 asks only for the point
estimate, and the control 10% in stage 2 keeps measuring. **Go or no-go for the project**
comes when n is reached: the 95% lower bound of the saving ≥ 3% keeps it; below 3% stops it or
changes the configuration.

## Scaling triggers

| trigger | threshold | what changes | design |
|---|---|---|---|
| volume | 429s > 1% of calls or p95 > 15 s (likely past ~30k tickets a month) | a queue and workers before the drafter; a daily cap under the monthly budget, past which cards come without a draft; Batch API at half price for nightly re-scoring and eval runs. The model bill is not the trigger: 50k a month is ~$25 | [phase2.md §6](phase2.md#6-cost-and-model-routing) |
| KB and SOP size | prompt > 30k tokens (now ~2k), or "expected section cited" on golden < 95% (now 39/39) | hybrid retrieval, narrowed by category; switch only at recall@10 ≥ 95% of expected sections, and the same gate after every KB change | [§4](phase2.md#4-retrieval-when-the-kb-stops-fitting) |
| KB authors | a second author or > 50 sections | an owner and a review-by date per section; CI fails on a cited section past its date | [§3](phase2.md#3-kb-as-owned-content) |
| language | ready drafts show only in languages with ≥ 30 labelled cases (now English 77, Russian 30); any other language over 2% of traffic | 30 cases with ≥ 5 reserved-topic traps, a run, then the language joins | [evals.md](evals.md) |
| category | a topic outside the four pages over 2% of tickets ("other" share, agent tags) | KB sections first, 30 labelled cases with traps, then drafts | [§3](phase2.md#3-kb-as-owned-content) |
| labelled tickets | ≥ 2,000 agent-confirmed labels (4–8 weeks of pilot) | fine-tune Laya; per-question thresholds on held-out real tickets; switch only at must-route recall 100% and route accuracy within Jev's interval | [§5](phase2.md#5-classifier-from-zero-shot-to-fine-tuned) |
| model, prompt, KB or threshold change; a Jev deprecation (30–60 days notice) | any | a new golden and blind run: 0 violations, needs-a-person recall 100%, route accuracy not below the current interval; then a week of paired shadow, old and new on the same tickets. Code-only changes pass `evals/gate.py` in CI | [evals.md](evals.md#reproduce) |

## Weekly loop

| who | reads | time |
|---|---|---|
| support lead | 50 sent ready drafts at random, stratified by category and language (6 weeks → 300, a 1.0% bound); every discard and edit ≥ 0.4; every missed escalation and every check hit on a sent reply | ~1 h |
| AI lead or engineer | the misses become cases, the cause is fixed, the gate is run; route mix, abstain rate, cost and p95 by KB and prompt version | ~2 h |

Both fit the hours the business case pays for. Nothing ships without the gate; the weekly
note lists the versions in the traces (prompt, questions, KB hash, model). The mechanics of
miss → case → fix → re-run: [phase2.md §2](phase2.md#2-the-weekly-loop-miss--case--fix--re-run).
