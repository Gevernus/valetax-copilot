# Support co-pilot: guide for coding agents

A ticket co-pilot for a forex/CFD broker's support team. Python 3.12, uv. Read README.md and
docs/decisions.md before changing behaviour.

## Commands

```bash
uv sync --all-extras                       # laya pulls torch; omit the extra to skip it
uv run pytest                              # unit tests, no network
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run copilot run "ticket text"           # needs TYPESAFE_API_KEY for the default jev classifier
uv run python -m evals.run run --classifier jev --model haiku
uv run python -m evals.run run --classifier jev --model haiku --set tickets_challenge --date <dir>-challenge
uv run python -m evals.run report --date <dir>   # re-score saved cards, no model calls
uv run python -m evals.run replay --date <dir>   # saved model outputs through current code, no network
uv run python -m evals.gate 2026-10-23 2026-10-23-challenge   # CI gate: no violation, no accuracy loss
uv run python -m evals.headline --golden <dir> --challenge <dir>-challenge --update-doc   # docs/evals.md table
uv run python -m evals.business_case --date <dir> --update-doc   # dir with all four configs
```

The drafter runs through the `claude` CLI by default; `llm.ClaudeCli` isolates it from the
local Claude Code setup. A usage-limit error stops an eval run and discards it: rerun later,
never score it.

Secrets: TYPESAFE_API_KEY and ANTHROPIC_API_KEY come from the environment only. Never print,
log or write them, and never put them in a test fixture.

## Where things are

- `src/copilot/pipeline.py`: the order of stages; the one place that decides what runs. Every
  stage reads the text from `normalise.py`, never the raw ticket; drafts are normalised too, so
  the shown text is the checked text.
- `src/copilot/errors.py`: the three provider errors (transient, permanent, usage limit) and the
  per-ticket budget; Jev, the claude CLI and the Anthropic API raise only these (Laya and the
  LLM classifier do not, and are not retried). `Copilot.process` returns a card for a person on
  any failure; only evals ask it to raise a usage limit (`raise_usage_limit=True`).
- `src/copilot/routing.py`: the reasons (in order of severity) and thresholds. A new reason
  needs a `Reason` member in its group, a `CONSEQUENCE` text, and a pipeline test that raises
  it. Failure cards (`too_long`, `classifier_error`, `pipeline_error`) use the same reasons.
- `src/copilot/classify/questions.py`: the typed questions, shared by every backend.
- `src/copilot/rules.py` and `grounding.py`: deterministic checks on input and draft.
- `src/copilot/draft.py`: the drafter prompt (`PROMPT_VERSION`) and the fixed decline texts.
- `kb/valetax.toml`: the knowledge base; `docs/kb-issues.md` explains the issue tags
  (`conflict` routes to a person, `defect` keeps a section out of the prompt, `gap`).
- `evals/tickets.jsonl`: golden set (holdout hash pinned in `tests/test_evals.py`);
  `evals/tickets_challenge.jsonl`: blind ticket set, run it, never tune on it or relabel it;
  `evals/metrics.py`: scoring; `evals/results/`: runs. A code change is checked with `replay`
  on the newest run; a prompt, question or KB change needs a new run.
- `src/copilot/reply_guard.py`: what a shown reply must not say (decision, compliance check,
  handover): frozen patterns plus the `REPLY` questions; `--reply-checker` picks a measured backend.
- `evals/drafts.jsonl`: labelled drafts for the reply checks; `uv run python -m evals.run_drafts
  [--classifier jev]`. Tune on `split: dev` only; the holdout hash is pinned in `tests/test_evals.py`.
  `evals/drafts_challenge.jsonl` is blind: run it, never tune on it or relabel it.
- `evals/figures_challenge.jsonl`: blind set for the number layer alone, `uv run python -m
  evals.run_figures`; same rule: run it, never tune on it or relabel it.

## Rules for changes

- Hard rules (no trading advice; complaints, KYC and AML only acknowledged and routed; no
  invented fees, limits or timelines) are enforced in code. A prompt change never replaces a
  check; add the check and a test with fake models (`tests/test_pipeline.py`).
- Nothing raw leaves `mask_pii`. Traces carry ids, labels, versions, tokens and timings, never
  ticket text, replies or prompts. `tests/test_pipeline.py::test_trace_has_no_text` guards it.
- Changing the prompt, the KB, a threshold or a classifier question: bump `PROMPT_VERSION` or
  `QUESTIONS_VERSION` for what changed, run the golden set for at least `jev+haiku`, and
  compare with the last results file. Violations must stay at 0.
- A miss found in a run becomes a case in `evals/tickets.jsonl` with a `note`; fix the cause
  (KB, rule, threshold, question wording), not that one ticket. Do not tune on `split: holdout`.
- KB text stays verbatim from the source pages, typos included; section ids are stable because
  citations, labels and traces refer to them.
