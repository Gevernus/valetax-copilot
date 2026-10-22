# Decisions

Each entry: what was decided, why, and what was rejected. Numbers come from
[evals.md](evals.md) and [business-case.md](business-case.md).

## 1. A co-pilot, and what "route to a person" means

**Decision.** Every draft goes to a support agent; nothing is sent to a client automatically.
The route answers a narrower question: can the agent send the draft after reading it
("draft ready"), or does the ticket need a person's decision, an account lookup, or a reply the
KB cannot support ("needs a person", with reasons)? The card shows reasons and consequences
first, then the draft, then the sources.
**Why.** The pilot runs on five agents collecting feedback; the risk that matters is a wrong
answer that looks right. Agents need to know where to look, not just get text.
**Rejected.** Auto-sending covered answers in phase 1: the KB contradicts itself
([kb-issues.md](kb-issues.md)) and there is no production feedback yet.

## 2. Rules first, models in the middle, rules last

**Decision.** Deterministic steps wrap both models: PII masking and regex pre-checks
(injection, trading-advice requests) before anything leaves the process; a deterministic
grounding check and the routing table after.
**Why.** The hard rules from the brief must hold whatever a model does. A regex catches
"ignore all previous instructions" or "should I buy gold" every time at no cost; the models
cover the paraphrases. Each layer is testable without a model (`tests/test_pipeline.py` runs
the pipeline with fake models).
**Rejected.** Prompt-only guardrails: a prompt is a request to the model, not a control.

## 3. Classification by a decision model, not an LLM

**Decision.** One request to a System-One decision model answers nine typed `choice`
questions: category, urgency, sentiment, trading advice, complaint, KYC case, AML case,
injection, account lookup. Backends share the `/v1/systemone` contract: **Jev** (TypeSafe,
hosted), **Laya** (open source, local, multilingual checkpoint), and an **LLM baseline** with
structured output answering the same questions.
**Why.** Typed answers cannot fall outside the option set; the response carries a probability
per option, which the routing thresholds use; one call takes about 0.3 s against seconds for
an LLM; Jev's input price is under half of Haiku's and its output is free. Laya runs on the
machine, so tickets need not leave the perimeter, and it can be fine-tuned on our labels.
**Rejected.** Classification by the drafting LLM in the same call: no calibrated
probabilities, and the classification would depend on the drafting prompt. Training our own
classifier: no labelled tickets yet. Measured comparison in [evals.md](evals.md).

## 4. Asymmetric thresholds

**Decision.** A flag is raised at P(yes) ≥ 0.35 for trading advice and AML and ≥ 0.5 for the
rest; a category below 0.5 routes to a person as low confidence (`routing.Thresholds`).
**Why.** A missed trading-advice or AML case costs more than an extra ticket for an agent.
**Rejected.** One global threshold. The values are hand-set; phase 2 fits them on held-out
data per question ([phase2.md](phase2.md)).

## 5. Language is detected, not classified

**Decision.** `lingua` over a closed list of 15 languages.
**Why.** Language is a property of the text, not a judgment; a deterministic local library is
free, fast and reproducible. It decides the reply language and the decline template.
**Rejected.** A tenth decision-model question: more tokens and a probability for something
that does not need one.

## 6. The whole KB in the prompt; no vector database in phase 1

**Decision.** 20 sections with stable ids (the duplicated FAQ stored once); with the rules,
about 2,000 tokens in a system prompt that is byte-identical across tickets and therefore cached.
**Why.** At this size retrieval can only lose: a missed section is a wrong abstention or a
wrong answer, and an index is one more thing to keep fresh. With a cached prefix the KB costs
a tenth of the input price per ticket.
**Rejected.** Embeddings and a vector store now. The trigger to add hybrid retrieval and the
design are in [phase2.md](phase2.md).

## 7. Citations are section ids from an enum

**Decision.** The output schema lists the KB's section ids as an enum; the draft cites ids,
the card resolves them to titles and URLs. The drafter may abstain with a reason and list the
parts it could not answer.
**Why.** An invalid citation cannot be produced, and citation validity becomes a structural
property instead of a metric to watch. The grounding check still verifies ids, in case a
backend does not enforce the schema.

## 8. Checks on every draft: numbers in code, wording by patterns and the decision model

**Decision.** A draft is withheld when it has no citations; when a number with its unit or
currency ("48 hours", "a business day", "$10"), or a fee or guarantee claim, appears in neither
the cited sections nor the client's message; or when it gives trading advice, announces a
decision on the client's case, names a compliance, fraud or security check, or says the case
was passed on. These run on every shown draft, not only on tickets flagged as complaints, KYC or
AML, so a missed flag does not let an outcome through. Only the cited sections support policy:
a figure the draft takes from the client's message alone ("3 days ago") keeps the draft
visible, is listed on the card, and routes the ticket to a person (`client_figures`). If a
check cannot run, the draft is withheld (`check_error`).
**How.** Numbers are compared in code (`quantities.py`): each with its unit or currency, so
"$1,000" is not "$1", "3 days" is not "3 hours" or "3 business days", "8 €" is not "8 USD", and
a bare "8" is not "8 USD". A number with a unit the tables do not know ("2 AUD", "₹2", "2
trading days") is supported by nothing, step numbers ("Step 2") support nothing, and a locale-
ambiguous "1,000" needs a number with the same readings. Units are read in every language the
detector returns. Wording is checked in two layers: precise patterns (`rules.py`: "your
withdrawal was rejected", "мы одобрили", "has been passed to") and three typed questions on
the reply (`classify/questions.py: REPLY`) asked of the same decision model as the ticket
questions, withholding at P(yes) ≥ 0.5.
**Why two layers.** Measured on `evals/drafts.jsonl`: 465 labelled drafts and sentences (real
drafts from every saved run, both review panels' probes, and paraphrases written before the
checks were changed); thresholds and question wording were set on the dev split only, and the
holdout is frozen by a hash test (`evals/run_drafts.py`, results in `evals/results/drafts-*`).

| holdout (227 rows) | patterns only | patterns + Jev |
|---|---|---|
| decision recall | 34% (10/29) | 100% (29/29, 88–100%) |
| compliance-check recall | 38% (5/13) | 100% (13/13, 77–100%) |
| handover recall | 72% (33/46) | 100% (46/46, 92–100%) |
| any of the three: recall / precision | 55% / 100% | 100% (88/88, 96–100%) / 97% (88/91) |

Patterns alone missed paraphrases ("As discussed, your withdrawal has been approved",
"Penarikan Anda telah disetujui", "Ya trasladamos su consulta al equipo de pagos"); an earlier attempt to widen them and excuse
conditional sentences let "After reviewing your documents, we have approved…" through.
**Limits.** Patterns and a classifier, not proof. The set is small (29 decisions, 13
compliance checks in the holdout), labelled by one person, and the handover positives are
mostly one template ("passed to the responsible team"); four labels were corrected after
reading the model's disagreements, two of them in the holdout. Over-caution observed: "glad
your withdrawal arrived", "after verification is completed, you're all set" and a future "I
will pass your question" can be withheld. A paraphrased unsupported claim without a number
("withdrawals are usually quick") passes. The reply check adds one decision-model call (about
0.3 s) per shown draft.
**Rejected.** An LLM judge: a second generative model with its own errors, latency and cost;
the typed questions return probabilities on the contract the ticket classifier already uses.

## 9. Hard rules live in code

- **Trading advice**: the decline text is fixed per language and appended by code, never
  written by the model; the ticket routes to a person. The drafter answers only the rest, and
  the decline stays on the card when that part is withheld.
- **Complaints, KYC, AML**: the drafter does not run, and its prompt says nothing about them
  (`draft-v2`). The card carries a fixed, neutral acknowledgement per case and language
  (`draft.ACKNOWLEDGEMENT`) that promises no outcome or timeline, does not claim a handover
  that has not happened, and never names a compliance check; the route is always a person.
- **Fixed texts are versioned**: a wording change adds a version and keeps the old ones, so
  saved cards are scored against the text they carry (`evals/metrics.py`).
- **Injection**: rule or model hit, the drafter does not run at all.
- **Invented policy**: the grounding check above.

## 10. KB contradictions go to a person; known-wrong content is hidden

**Decision.** Sections tagged `conflict` route any draft that cites them to a person, with
the reason shown. A section tagged `defect` (the withdrawal steps, which are the deposit
steps) stays in the file but not in the prompt, so it cannot be cited.
**Why.** The co-pilot cannot know which of two statements is current; picking one is
inventing policy. The cost is visible in the route mix, which makes the content fix
measurable. The defect tag came from a miss: a draft copied "Start Trading!" into a withdrawal
answer while the section was only marked as a conflict.

## 11. Claude subscription CLI for development, the API for production

**Decision.** The `claude-cli` backend shells out to `claude -p` with `--json-schema` and no
tools; the `anthropic` backend calls the Messages API with the system prompt cached and
structured output. The evals ran on the CLI.
**Why.** The CLI costs nothing per call during development. It is not a production path: it
takes seconds to start, is subject to subscription limits, and by default brings the
developer's environment into every call. The first eval run showed ~12k tokens per call that
were not ours: the user's global CLAUDE.md, memory, hooks, MCP servers and skills. The drafter
now runs the CLI from an empty temporary directory with setting sources, MCP servers and slash
commands disabled (`llm.ClaudeCli`), which leaves ~600 tokens of CLI overhead. The business
case prices only our own tokens (system prompt size measured by calibration, see
`evals/run.py::calibrate`) at API list prices, not the CLI's reported cost.
**Not verified.** The `anthropic` backend is written against the SDK documentation but was
not run: no API key was available.

## 12. One trace line per ticket, no text

**Decision.** `traces/*.jsonl`: route, reasons, labels with probabilities, rule hits,
citations, masked-entity counts, per-stage latency, tokens, model ids, KB version hash and
prompt version.
**Why.** Enough to run the weekly review and to attribute any change to a KB or prompt
version; nothing in it needs PII handling.
**Rejected.** Logging prompts and replies: they contain client data, and the cards already
hold the reply for the agent.

## 13. Drafter model

**Decision.** Haiku by default; Sonnet measured on the same set.
**Why.** The rule is the cheapest model that keeps hard-rule violations at 0 and route
accuracy within the interval of the larger one. Measured: Haiku 98% (91–99%), Sonnet 96%
(90–99%), both 0 violations; Sonnet costs about ten times more per ticket
([evals.md](evals.md#results)).

## 14. Evals written by us, with a holdout

**Decision.** 80 hand-labelled tickets, one in four held out; Wilson 95% intervals on every
rate; hard-rule violations counted per ticket.
**Why.** At this size an accuracy is a range, not a number; the intervals say how much a
change must move to mean anything. The labels are ours, so the set measures agreement with
our reading of the brief, not with Valetax's agents: the first pilot week replaces it with
real tickets.
