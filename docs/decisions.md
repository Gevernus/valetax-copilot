# Decisions

Each entry: the decision, why, and what was rejected. Measurements behind them are in
[evals.md](evals.md) and [business-case.md](business-case.md).

## 1. A co-pilot, and what "route to a person" means

**Decision.** Every draft goes to a support agent; nothing is sent to a client automatically.
The route answers a narrower question: can the agent send the draft after reading it ("draft
ready"), or does the ticket need a person's decision, an account lookup or a reply the KB cannot
support ("needs a person", with reasons)? The card shows reasons and consequences first, then
the draft, then the sources.
**Why.** The risk that matters is a wrong answer that looks right; agents need to know where to
look, not just get text.
**Rejected.** Auto-sending covered answers in phase 1: the KB contradicts itself
([kb-issues.md](kb-issues.md)) and there is no production feedback yet.

## 2. Rules first, models in the middle, rules last

**Decision.** Deterministic steps wrap both models: PII masking and input patterns (injection,
trading-advice requests) before anything leaves the process; the source check, the reply checks
and the routing table after.
**Why.** The hard rules must hold whatever a model does. A pattern catches "ignore all previous
instructions" every time at no cost; the models cover paraphrases. Every layer is testable with
fake models (`tests/test_pipeline.py`).
**Rejected.** Prompt-only guardrails: a prompt is a request to the model, not a control.

## 3. Classification by a decision model, not an LLM

**Decision.** One request to a decision model answers nine typed `choice` questions: category,
urgency, sentiment, trading advice, complaint, KYC case, AML case, injection, account lookup.
Three backends share the `/v1/systemone` contract: Jev (hosted), Laya (open source, local) and
an LLM baseline with structured output.
**Why.** Typed answers cannot fall outside the option set; each answer carries a probability per
option, which the thresholds use; a call takes about 0.3 s against 4.7 s for the LLM, at a lower
price. Laya keeps tickets inside the perimeter and can be fine-tuned on our labels.
**Rejected.** Classifying inside the drafting call (no calibrated probabilities, and labels that
depend on the drafting prompt); training our own classifier (no labelled tickets yet).

## 4. Asymmetric thresholds

**Decision.** A flag is raised at P(yes) ≥ 0.35 for trading advice and AML and ≥ 0.5 for the
rest; a category below 0.5 goes to a person as low confidence (`routing.Thresholds`).
**Why.** A missed trading-advice or AML case costs more than an extra ticket for an agent.
**Rejected.** One global threshold. The values are hand-set; phase 2 fits them per question on
held-out data ([phase2.md](phase2.md)).

## 5. Language is detected, not classified

**Decision.** `lingua` over a closed list of 15 languages.
**Why.** Language is a property of the text, not a judgment: a local library is free, fast and
reproducible. It picks the reply language and the fixed texts.
**Rejected.** A tenth decision-model question: more tokens and a probability nobody needs.

## 6. The whole KB in the prompt; no vector database in phase 1

**Decision.** 20 sections with stable ids, about 2,000 tokens with the rules, in a system
prompt that is byte-identical across tickets and therefore cached.
**Why.** At this size retrieval can only lose: a missed section is a wrong abstention or a wrong
answer. With a cached prefix the KB costs a tenth of the input price.
**Rejected.** Embeddings and a vector store now. The trigger and design are in
[phase2.md](phase2.md#4-retrieval-when-the-kb-stops-fitting).

## 7. Citations are section ids from an enum

**Decision.** The output schema lists the citable section ids as an enum; the card resolves them
to titles and URLs. The drafter may abstain with a reason and list what it could not answer.
**Why.** An invalid citation cannot be produced. The source check still verifies ids, in case a
backend does not enforce the schema.
**Rejected.** Free-text citations checked afterwards.

## 8. Checks on every draft: numbers in code, wording by patterns and the decision model

**Decision.** A draft is withheld when it cites nothing; when a number with its unit ("48
hours", "$10"), a time word ("within the hour") or a fee or guarantee claim is in neither the
cited sections nor the client's message; or when it gives trading advice, announces a decision
on the client's case, names a compliance check, or says the case was passed on. A figure taken
only from the client's message ("3 days ago") stays visible and sends the ticket to a person
(`client_figures`). If a check cannot run, the draft is withheld.
**How.** Numbers are compared in code with their unit (`quantities.py`; its docstring lists
what it reads and where it fails closed). Wording is checked by frozen patterns (`rules.py`) and
by three typed questions about the reply on the decision model (`reply_guard.py`), asked only of
a draft that passed the source check. The patterns also read the model's other text (the
unanswered list, the abstain reason). Only a reply checker measured on the drafts set may be
configured; `--reply-checker none` (patterns only) is recorded in every trace line.
**Why.** These checks run on every draft, not only on tickets flagged as complaints, KYC or AML,
so a missed flag does not let an outcome through. Measured on blind sets written by a separate
agent: 91% of unsupported figures withheld and 93% sent to a person; the reply questions caught
93 of 93 decisions, checks and handovers, the patterns alone 27
([evals.md](evals.md#checks-on-drafts)). The patterns stay as a free floor that still runs when
the model is off; they are not widened.
**Rejected.** An LLM judge: a second generative model with its own errors, latency and cost,
and no probabilities.

## 9. Hard rules live in code

- **Trading advice**: the decline is a fixed text per language, appended by code; the drafter
  answers only the rest, and the decline stays when that part is withheld.
- **Complaints, KYC, AML**: the drafter does not run. The card carries a fixed acknowledgement
  per case and language (`draft.ACKNOWLEDGEMENT`) that promises no outcome or timeline, claims
  no handover and names no check.
- **Fixed texts are versioned**: a wording change adds a version, so saved cards are scored
  against the text they carry.
- **Injection**: rule or model hit, the drafter does not run.
- **Invented policy**: the source check (§8).

## 10. KB contradictions go to a person; known-wrong content is hidden

**Decision.** A draft citing a section tagged `conflict` goes to a person with the reason shown.
A section tagged `defect` (the withdrawal steps, which are the deposit steps) stays in the file
but out of the prompt.
**Why.** The co-pilot cannot know which of two statements is current; picking one is inventing
policy. The cost shows in the route mix, which makes the content fix measurable.
**Rejected.** Letting the model pick, or editing the KB text (it stays verbatim, so a citation
matches the live page).

## 11. Claude subscription CLI for development, the API for production

**Decision.** The `claude-cli` backend runs `claude -p` with a JSON schema and no tools, from an
empty directory with setting sources, MCP servers and slash commands off (`llm.ClaudeCli`). The
`anthropic` backend calls the Messages API with the system prompt cached. The evals ran on the
CLI.
**Why.** The CLI costs nothing per call during development. Without isolation it added ~12k
tokens of the developer's own setup to every call. The business case prices only our own tokens
at API list prices.
**Not verified.** The `anthropic` backend is written against the SDK documentation and was not
run: no API key was available. Its error mapping is tested with real SDK exceptions.
**Rejected.** The CLI in production: slow start, subscription limits.

## 12. One trace line per ticket, no text

**Decision.** `traces/*.jsonl`: route, reasons, labels with probabilities, rule hits,
citations, masked-entity counts, per-stage latency and attempts, tokens, models, and the
versions of the prompt, KB, questions, rules (a hash of the deterministic modules) and
thresholds.
**Why.** Enough for the weekly review and to tie any change to a version; nothing in it needs
PII handling.
**Rejected.** Logging prompts and replies: they hold client data.

## 13. Drafter model

**Decision.** Haiku by default.
**Why.** The cheapest model that keeps violations at 0 and route accuracy within the larger
model's interval: Haiku 98%, Sonnet 96%, both 0 violations, Sonnet about ten times the cost.
**Rejected.** Sonnet: nothing measurable for the price.

## 14. Evals written by us, with a holdout and blind sets

**Decision.** 80 hand-labelled tickets, one in four held out and pinned by hash; 60 blind
tickets, frozen before their one run; Wilson 95% intervals on every rate; violations per ticket.
**Why.** At this size an accuracy is a range; the intervals say how much a change must move to
mean anything. Our labels measure agreement with our reading of the brief, so the first pilot
weeks should replace them with real tickets.
**Rejected.** A single accuracy number on a set we also tuned on.

## 15. Failures go to a person

**Decision.** Nothing that fails produces a draft. A failed classification gives a neutral card
(`classifier_error`), any other failure `pipeline_error`, a provider failure while drafting or
checking `draft_error` or `check_error`. Every stage reads one normalised text, so an invisible
character cannot split an email, a fee or an injection phrase (`normalise.py`). Over 20,000
characters the ticket is masked and read by the patterns only, then goes to a person. Backends
raise three error kinds (`errors.py`); only transient ones are retried, three calls per stage
inside one 120 s budget per ticket, each call given the time left as its timeout. Raw input over
80,000 characters is not read at all. The trace keeps the failed stage and the error class,
never a message or a body. The agent's view (`pipeline.agent_view`: the CLI, the page and
`Card.to_dict`) never carries the raw reply, nor any model text when the draft is withheld.
The drafter's length caps are checked in code, not sent in the schema. An eval run stops on a
usage limit or five provider failures in a row instead of scoring them.
**Why.** A vendor outage should cost the agents their drafts, not their tickets, and should not
be scored as the co-pilot's quality.
**Limits.** The budget is checked between calls, and HTTP and SDK timeouts are per phase, so a
slow call can run past it; Laya runs in process and ignores it. Laya and the LLM classifier do
not map their errors to the three kinds, so they are not retried, but still end as a card for a
person. There is no ingest queue here; the length caps protect whatever feeds the co-pilot.
**Rejected.** Retrying permanent errors, the SDK's own retries (they would multiply ours), and a
resilience framework.
