# Requirements checklist

What the brief asked for, where it lives, what proves it, and how far it goes. Numbers are
Jev + Haiku on the golden set (`evals/results/2026-10-23.md`, 80 tickets) and the blind set
(`evals/results/2026-10-23-challenge.md`, 60 tickets) unless a row says otherwise.

Status: **done** (built and measured), **partial** (built, with a stated gap), **plan** (written,
not built).

## The brief

| requirement | where in code | proof | status |
|---|---|---|---|
| Classify: category, urgency, sentiment | `classify/questions.py` (typed questions), `classify/jev.py`, `classify/llm.py` (baseline) | golden: category 99%, urgency 95%, sentiment 100%; blind: 95%, 85%, 87% | done |
| Classify: language | `language.py` (lingua, 15 languages) | golden 98% (78/80), blind 100% (60/60) | done |
| Draft grounded in the KB, with citations | `draft.py` (citations are an enum of section ids), `grounding.py` | citations valid 100% (42/42), an expected section cited 100% (38/38); `test_grounding.py` | done |
| Abstain when the KB does not cover it | `Draft.abstain` and `unanswered`, routed as `kb_gap` | golden abstention recall and precision 100% (9/9); blind 60% / 46% under the writer's different convention ([evals.md](evals.md#blind-challenge-set-2026-10-23-challenge-jev--haiku)) | done |
| Route to a human whenever required | `routing.py` (19 reasons in three groups), `pipeline.py` (`READY_LANGUAGES`: en, ru, es) | needs-a-person recall 54/54 golden, 42/42 blind; route accuracy 92% / 93% | done |
| Rule 1: no trading advice; detect and decline politely | `rules.asks_trading_advice`, the `trading_advice` question, `draft.TRADING_DECLINE` appended by code, `rules.gives_trading_advice` on drafts | 0 violations on 140 tickets; flag recall 9/9; `test_pipeline.py` (decline survives a withheld draft, a missed flag) | done; advice inside a draft is checked by a pattern only |
| Rule 2: never decide a complaint, KYC or AML outcome | the drafter does not run for them; `draft.ACKNOWLEDGEMENT` (fixed texts); `reply_guard.py` (patterns + decision-model questions on every draft) | 0 violations; flags 4/4 each; reply checks: 93/93 on the blind synthetic drafts set (`evals/results/drafts_challenge-patterns+jev.md`), 0 hits on 157 live drafts; the completion-step pattern (`test_pipeline.py`) | done |
| Rule 3: never invent policy, fees or timelines | `grounding.check_draft` with `quantities.py`; fee and guarantee patterns; abstention | 0 violations; `test_grounding.py`, `test_quantities.py`, the probe sentences in `test_pipeline.py` (links, currencies, payment methods, countries, a figure moved to another topic) | partial: a claim with no number, time word, fee wording, link or listed name passes ([evals.md](evals.md#limits)) |
| Use the KB as it is, gaps and contradictions included | `kb/valetax.toml` (verbatim, 20 sections), issue tags `conflict` / `defect` / `gap` | [kb-issues.md](kb-issues.md) (7 issues); `test_kb.py`; conflicted sections route to a person | done |
| Phase 1: running for agents fast | `cli.py` (`copilot run`), `view.py` + `agent_view.html` (static page) | `test_view.py`; README "Run it" | done; the help-desk integration is a stand-in |
| Phase 2: scale with volume and a growing KB/SOPs | — | [rollout.md](rollout.md#scaling-triggers): a threshold per trigger (volume, KB size, language, category, labels, model change); [phase2.md](phase2.md): what each builds (retrieval, fine-tuning, model routing, KB ownership) | plan |
| ~10,000 tickets a month | cost formula in `evals/prices.py` | $3.71 a month of model cost at 10k ([business-case.md](business-case.md)); p50 5.2 s per ticket through the CLI | partial: costed, not load-tested |
| Business case on one page | `evals/business_case.py` writes the tables | [business-case.md](business-case.md); `test_business_case.py` checks every number in it against the script | done |
| Python | Python 3.12, uv | `pyproject.toml` | done |
| Built with an agentic coding tool | Claude Code | [CLAUDE.md](../CLAUDE.md) is the guide it worked from | done |
| Mocks and stubs explained | `llm.AnthropicApi` (production path) | written against the SDK docs, not run live (no API key); its error mapping is tested with real SDK exceptions (`test_providers.py`); evals ran the drafter through the `claude` CLI ([decisions.md §11](decisions.md#11-claude-subscription-cli-for-development-the-api-for-production)) | done, stated |

## What the review call cares about

| topic | where | proof | status |
|---|---|---|---|
| Evals | `evals/`: golden set with a pinned holdout, blind ticket and drafts sets; Wilson intervals | [evals.md](evals.md); hashes pinned in `test_evals.py` | done |
| Guardrails | rules before and after the models, fixed texts by code, reply checks, failures to a person | `test_pipeline.py`, `test_failures.py`, `test_reply_guard.py` | done |
| Observability | `Card.trace()`: one line per ticket, versions, tokens, timings, no text | `test_pipeline.py::test_trace_has_no_text`; `evals/results/*/traces.jsonl` | partial: traces only; dashboards are in [phase2.md](phase2.md#7-production-integration) |
| Regression gate | `evals/gate.py`, `.github/workflows/ci.yml` | replay of the committed runs: 0 violations, route accuracy not below the committed one | done |
| Path to production | shadow, five agents, everyone (no auto-send); promotion and stop criteria with sample sizes; the pilot's success tied to the break-even; rollback by a config flag | [rollout.md](rollout.md) | plan: nothing has run on live traffic |
| Weekly improvement loop | miss, case, fix, re-run | run three times here ([evals.md](evals.md#the-weekly-loop-run-here)); [phase2.md §2](phase2.md#2-the-weekly-loop-miss--case--fix--re-run); who reads which sample: [rollout.md](rollout.md#weekly-loop) | done here, plan for production |

## What each test file proves

All tests run without a network; fakes stand in for the models.

| file | proves |
|---|---|
| `test_pipeline.py` | the hard rules hold whatever the models answer: injection skips the drafter, reserved cases get fixed texts, the decline is appended by code, invented fees and decisions are withheld, traces carry no text |
| `test_failures.py` | every failure becomes a card for a person; only transient errors are retried within one budget; invisible characters cannot hide PII or a rule; the length caps hold |
| `test_grounding.py` | a draft's numbers, time units, fee claims, links and listed names must be in the sections it cites; figures only the client gave are listed |
| `test_quantities.py` | numbers bind to their unit or currency in English, Russian and Spanish; an unknown unit, or one in another language, fails closed; steps never support an amount |
| `test_reply_guard.py` | the frozen patterns catch the plain wordings and raise no false alarm on the dev drafts |
| `test_routing.py` | reasons are ordered by severity, and each has a text for the agent |
| `test_normalise.py`, `test_masking.py` | one normalised text; PII masked in it |
| `test_classify.py` | a malformed probability answer is refused, not read as "no" |
| `test_providers.py` | Jev, the claude CLI and the Anthropic SDK map their failures to three errors and keep no response body |
| `test_view.py` | the agent's page and exports never carry withheld model text, and hostile strings render as text |
| `test_kb.py` | the KB loads with stable ids; conflicts are tagged; the defective section stays out of the prompt |
| `test_evals.py` | the scorer itself: frozen sets by hash, label-driven violations, replay of the committed runs, the docs table equals the script |
| `test_business_case.py` | the cost and saving formulas by hand; every figure in business-case.md equals the script's |
