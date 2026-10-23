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
Jev (hosted) is the backend; an LLM with structured output is the baseline it was measured
against.
**Why.** Typed answers cannot fall outside the option set; each answer carries a probability per
option, which the thresholds use; a call takes about 0.3 s against 4.7 s for the LLM, at a lower
price. This is one vendor: if Jev is down, every ticket gets a `classifier_error` card and no
draft (§15).
**Rejected.** Classifying inside the drafting call (no calibrated probabilities, and labels that
depend on the drafting prompt); training our own classifier (no labelled tickets yet). Laya,
the open-source local model on the same contract, was measured zero-shot on the golden set at
61% route accuracy as run (49/80) and 71% (57/80) replayed on the current code, with one ready
draft in 80 (`evals/results/2026-10-23/laya+haiku+reply-jev`)
and removed from the code: it is the fine-tuning candidate for data residency, not a fallback
([phase2.md §5](phase2.md#5-classifier-from-zero-shot-to-fine-tuned)).

## 4. Asymmetric thresholds

**Decision.** A flag is raised at P(yes) ≥ 0.35 for trading advice and AML and ≥ 0.5 for the
rest; a category below 0.5 goes to a person as low confidence (`routing.Thresholds`).
**Why.** A missed trading-advice or AML case costs more than an extra ticket for an agent.
**Rejected.** One global threshold. The values are hand-set; phase 2 fits them per question on
held-out data ([phase2.md](phase2.md)).
**Trade-off.** A flag is wired by hand in five places (its question in `classify/questions.py`,
its field in `routing.Thresholds`, its `routing.Reason`, the mapping in `pipeline._cases`, the
scorer in `evals/metrics.py`): explicit rather than generic, so a new flag needs a pipeline test
that raises it. The thresholds are calibrated to jev-1.14.0; a new Jev version re-runs the
golden set before it is used.

## 5. Language is detected, not classified

**Decision.** `lingua` over a closed list of 15 languages; a text in a script none of them uses
(Korean, Hebrew, Greek) is `und`, and a short Latin or Cyrillic text gets the best guess
("Min deposit?" is English; a plain-ASCII text close to English is English). Ready drafts only
in English and Russian (`language.READY_LANGUAGES`), and only when every sentence of the draft
is in the ticket's language and script (`language.written_in`): any other ticket, and a draft
with a clause in another language, goes to a person with the draft (`unsupported_language`).
A clause counts as a language from four words; a shorter foreign fragment ("Conta aprovada.") is
left to the lexicons and the reply check, because under four words the detector guesses and
would withhold names such as "Create Account". Spanish waits in the shadow stage until it has 30 labelled cases
([rollout.md](rollout.md)); its fixed texts are written, other languages fall back to English.
**Why.** Language is a property of the text, not a judgment: a local library is free, fast and
reproducible. It picks the reply language and the fixed texts. The labelled cases, the fixed
texts and the wording patterns exist for these languages; elsewhere a check would be silent
rather than right. The evals apply the same policy to the labels (`metrics.expected_route`),
so no label was rewritten.
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
cited sections nor the client's message; when it names a currency, payment method, country or
instrument from a closed list that neither carries; when it uses a fee, minimum, limit or speed
word ("a small fee", "a daily limit", "within the hour") and no cited section uses one from the
same lexicon; when a link is not verbatim in a cited section; when a sourced figure is stated
about deposits or withdrawals (in its sentence, or else in the ticket) and no cited section
gives it for that topic; or when it gives trading advice, announces a decision
on the client's case, names a compliance check, or says the case was passed on. A figure taken
only from the client's message ("3 days ago") stays visible and sends the ticket to a person
(`client_figures`). If a check cannot run, the draft is withheld.
**How.** Numbers are compared in code with their unit (`quantities.py`; its docstring lists
what it reads and where it fails closed); links, names and the fee, minimum, limit and speed
lexicons from closed lists (`terms.py`): the KB states no fee and no limit but the minimum
deposit, so the lexicons are a closed world over it, and a ticket that asks for one of them (or for the minimum withdrawal, or how
long a withdrawal takes) is a gap read on the ticket (`terms.kb_gaps`), so no wording of the
draft can make it ready. It says "instant" or "immediately" only
inside its conflicts (I1, I5, I7), so a speed claim sends the draft to a person as a conflict
whichever section it cites (`terms.CONTESTED`), and the deposit steps stay citable. Wording is checked by frozen patterns (`rules.py`) and
by three typed questions about the reply on the decision model (`reply_guard.py`), asked only of
a draft that passed the source check. The patterns also read the model's other text (the
unanswered list, the abstain reason). Only a reply checker measured on the drafts set may be
configured; `--reply-checker none` (patterns only) is recorded in every trace line.
**Why.** These checks run on every draft, not only on tickets flagged as complaints, KYC or AML,
so a missed flag does not let an outcome through. Measured on blind sets written by a separate
agent: the reply questions caught 93 of 93 decisions, checks and handovers, the patterns alone
27; in the live runs they have not fired on a single draft
([evals.md](evals.md#checks-on-drafts)). The patterns stay as a free floor that still runs when
the model is off. They were widened once (the completion step, "Account verification
completed!" restated as the client's status) and are otherwise frozen: any further miss
becomes a dev row in `evals/drafts.jsonl`.
**What the checks cannot prove.** A paraphrased claim with none of the words above, in a reply
to a question the KB does answer, passes. No lexicon closes that; the control is the product's
shape: a co-pilot, no auto-send, an agent reads every card ([evals.md](evals.md#limits)).
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
model's interval: Haiku 94%, Sonnet 92%, both 0 violations, Sonnet about ten times the cost.
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
slow call can run past it. The LLM classifier does not map its errors to the three kinds, so
it is not retried, but still ends as a card for a person. There is no ingest queue here; the length caps protect whatever feeds the co-pilot.
**Rejected.** Retrying permanent errors, the SDK's own retries (they would multiply ours), and a
resilience framework.

## 16. Data and vendors

**Decision.** Two vendors receive ticket text after masking: TypeSafe (Jev, the classifier and
the reply check) gets every ticket, because classification comes before routing, and every
shown draft; Anthropic (the drafter) gets every ticket that is not an injection or a reserved
case, with the whole KB as the system prompt. Masked first, and only this (`masking.py`):
emails; card numbers of 13–19 digits that pass the Luhn check, with at most one separator
character between two digits; IBANs in any case, with at most one space or hyphen between
groups; TRON, EVM and bc1 wallets; phones with a "+" right before the first digit; 5+ digits
right after an account, login or ID keyword; any run of 7+ digits; passport, DNI, NIE and
national-id tokens right after the keyword. Nothing else. **Not masked: names, addresses and dates of
birth**, local phone formats, other wallet formats, national numbers without a keyword (CPF,
Aadhaar, PAN, SSN) and a passport number written apart from its series; a KYC or complaint
ticket carries them to both vendors. The trace line carries no text.
**Not verified.** No DPA, retention period, sub-processor list or data region was reviewed for
either vendor. That review, and the masking it asks for, is required before any real ticket is
sent; shadow mode sends real tickets too, so vendor approval is the entry condition of stage 0
([rollout.md](rollout.md#stages)). The CLI takes the ticket from stdin or a file, never argv
(shell history, the process list), reads at most 80,001 characters, and starts the `claude`
subprocess in a private temporary directory with only the variables it needs to authenticate.
**Rejected.** Pattern-based name and address masking: it misses most names and mangles
ordinary words. A named-entity model, or a classifier inside the perimeter (Laya fine-tuned,
[phase2.md §5](phase2.md#5-classifier-from-zero-shot-to-fine-tuned)), is the phase-2 option.
