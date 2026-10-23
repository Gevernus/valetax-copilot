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
currency ("48 hours", "$10"), a time unit without a number ("within the hour"), or a fee or
guarantee claim appears in neither the cited sections nor the client's message; or when it
gives trading advice, announces a decision on the client's case, names a compliance, fraud or
security check, or says the case was passed on. These run on every draft, not only on tickets
flagged as complaints, KYC or AML, so a missed flag does not let an outcome through. Only the cited sections support policy:
a figure the draft takes from the client's message alone ("3 days ago") keeps the draft
visible, is listed on the card, and routes the ticket to a person (`client_figures`). If a
check cannot run, the draft is withheld (`check_error`).
**How.** Numbers are compared in code with their unit or currency (`quantities.py`, whose
docstring lists what is read and what fails closed): a number is supported only by the same
value with the same unit, a step number only by a step number, and an unknown unit by nothing.
Wording is checked by frozen patterns (`rules.py`) and three typed questions on the reply asked
of the decision model (`reply_guard.py`, P(yes) ≥ 0.5).
**The number layer, measured.** It is a frozen deterministic floor, not a parser of meaning;
its measured property is the blind figures set (`evals/figures_challenge.jsonl`, 200 drafts with
their cited sections and tickets, 91 with an unsupported figure, written by a separate agent that
never saw the code, frozen by hash, run once with `evals/run_figures.py`, not tuned on after).
The writer counts a correct KB figure restated in another unit ("within an hour" for 60
minutes) or taken from an uncited section as unsupported, and the same value as a word ("six
months") as supported.

| figures set, 200 rows | recall | precision |
|---|---|---|
| withheld | 91% (83/91, 84–96%) | 95% (83/87, 89–98%) |
| sent to a person (withheld, or shown with figures only from the ticket) | 93% (85/91, 86–97%) | 85% (85/100, 77–91%) |

The rows come in 40 groups of 5 drafts on one ticket, so they are not independent and the
Wilson intervals are optimistic; 45% of rows are positive, so the precision holds for this set,
not for live traffic. Misses are timelines without a unit word, unit words outside the tables
and figures from an uncited section; the false withholds and the 11 client figures the draft
attributes to the client are listed by id, as disagreements and not relabelled, in
[the results](../evals/results/figures_challenge-check_draft.md). Re-run after the list-marker
and step-range fixes (1ec259f and later), and with the ticket normalised and masked as the
pipeline gives it to the check (C2): 0 of 200 predictions changed.
**Why the decision model, and what the patterns are for.** Measured with
`evals/run_drafts.py` (results in `evals/results/drafts-*` and `drafts_challenge-*`, threshold 0.5,
jev-1.14.0, questions `reply-v2`). Headline: the blind challenge set, 180 rows written by a
separate agent that never saw the patterns, the questions or the drafts set, frozen by hash,
run once:

| challenge, 180 rows: recall / precision | patterns only | Jev only | patterns + Jev |
|---|---|---|---|
| decision | 7/50 / 7/7 | 50/50 (93–100%) / 50/53 | 50/50 / 50/53 |
| compliance check | 15/34 / 15/15 | 34/34 (90–100%) / 34/34 | 34/34 / 34/34 |
| handover | 9/34 / 9/9 | 34/34 (90–100%) / 34/35 | 34/34 / 34/35 |
| any of the three | 27/93 (29%) / 27/27 | 93/93 (96–100%) / 93/94 | 93/93 / 93/94 |

On our own `evals/drafts.jsonl` (465 rows: drafts from every saved run split by ticket, probe
sentences in dev, paraphrases written before the checks changed in holdout; dev
256 / holdout 209, holdout frozen by hash) the holdout agrees: patterns 55% recall, Jev only
and patterns + Jev 100% (87/87) at 97% precision. The patterns add one dev row the model
misses ("Your account has not been verified", p = 0.41) and nothing on holdout or challenge.
They stay because they cost nothing, still run when the model is disabled
(`--reply-checker none`, recorded in the trace) or the draft already failed the source check,
and never raised a false alarm on dev. They are a frozen, model-free floor: they are not widened. A new miss becomes a dev row in
`evals/drafts.jsonl` and, if needed, a change to the question wording, measured on dev and
then once on holdout.
**Limits.** A classifier and patterns, not proof. Both sets are synthetic and small (50
decisions, 34 checks, 34 handovers in the challenge set); the drafts set was labelled by one
person who also wrote the question wording, and four of its labels were corrected after reading
the model's disagreements ([evals.md](evals.md#reply-checks-labelled-drafts-and-label-changes)).
Its handover positives are mostly one template ("passed to the responsible team") repeated
across tickets. Observed over-caution: a future "we will send your request to the team"
(challenge c125, drafts d317) and "after verification is completed, you're all set" are
withheld. Disagreements on the challenge set, kept as labelled: c046 (a completed handover the
model also reads as a decision, p = 0.51), c058 and c166 ("flagged" payments the model also
reads as a decision, p = 0.53 and 0.67). The number layer's limits are in its measurement above
and in the `quantities.py` docstring. Trading advice in a draft is
still checked by a pattern only (`rules.gives_trading_advice`); the fixed decline is what the
client sees for an advice request. The reply check adds one decision-model call (about 0.3 s)
per draft that passed the source check; only Jev is measured, and an unmeasured backend is
refused as a reply checker.
**Rejected.** An LLM judge: a second generative model with its own errors, latency and cost;
the typed questions return probabilities on the contract the ticket classifier already uses.
An LLM backend for the REPLY questions answers with p = 0 or 1 and is not measured.

## 9. Hard rules live in code

- **Trading advice**: the decline text is fixed per language and appended by code, never
  written by the model; the ticket routes to a person. The drafter answers only the rest, and
  the decline stays on the card when that part is withheld.
- **Complaints, KYC, AML**: the drafter does not run, and its prompt says nothing about them
  (since `draft-v2`). The card carries a fixed, neutral acknowledgement per case and language
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
citations, masked-entity counts, per-stage latency and attempts, tokens, the backend and
resolved model of every call, and the versions of the prompt, KB, ticket questions, reply
questions, rules (a hash of the source of the deterministic checks and the routing table; any
edit to those files, a comment included, bumps it) and thresholds, once per line.
**Why.** Enough to run the weekly review and to attribute any change to a KB, prompt, question,
rule or threshold version; nothing in it needs PII handling.
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

## 15. Failures go to a person

**Decision.** Nothing that fails produces a draft. A failed classification gives a neutral card
(`classifier_error`), any other failure `pipeline_error`, a provider failure while drafting or
checking `draft_error` / `check_error` (a bug in our own check is `check_error` too, but scored).
Every stage reads one normalised text, the ticket and the draft alike (`copilot/normalise.py`:
NFKC; every space as " "; format characters, Unicode default-ignorable code points, lone
surrogates and a combining mark on an ASCII letter or digit dropped; a wide gap between two
digits kept as a column tab, other runs as one space). So a zero-width, variation-selector or
combining character cannot split an email, a card number, a fee claim, "AML" or "ignore all
previous instructions", and the draft the agent sees is the text that was checked. NFKC
changes some meanings: superscripts and circled digits become plain digits, "½" becomes "1⁄2",
"№" becomes "No". A ticket over 20,000 normalised characters is masked and read by the injection
and advice patterns, then goes to a person unread by the models (`too_long`); raw input over
80,000 characters is not read at all. Jev, the claude CLI and the Anthropic API normalise their
failures into transient, permanent and usage-limit errors (`copilot/errors.py`); Laya and the
LLM classifier do not, and still end as a card for a person. Only transient errors are retried:
three calls per stage inside one 120 s budget per ticket, each call given the time left as its
timeout. The trace keeps attempts, the failed stage and the error class, never a message or a
body; metrics count these cards as failures, apart from quality. The agent's view
(`pipeline.agent_view`, used by the CLI, the HTML page and `Card.to_dict`) drops the raw reply,
and all model-written text when the draft is withheld; problem texts can still quote a draft
fragment ("numbers not in cited sections: 10 USD"). A usage limit is a failed ticket for the
agent; an eval run stops on it, or after five provider failures in a row. The drafter's length
caps (reply, abstain reason, unanswered list) are checked in code, not sent in the schema: a
provider may reject or rewrite them.
**Why.** A vendor outage should cost the agents their drafts, not their tickets, and should not
be scored as the co-pilot's quality. A test reproduces the transient Jev failure seen in a
replay: the retried draft stays ready.
**Limits.** The budget is checked between calls; inside one call the HTTP and SDK timeouts are
per phase (connect, read), so a slow call can run past it. Laya runs in process and ignores it.
The Anthropic backend is written against the SDK documentation and has not been run live (no
API key here); its error mapping is tested with real SDK exception objects. There is no ingest
queue in this repo: the length cap protects whatever feeds the co-pilot later.
**Rejected.** Retrying permanent errors (they fail the same way, slower), the SDK's own retries
(they would multiply the pipeline's), and a resilience framework: three error classes and one
budget cover the four backends.
