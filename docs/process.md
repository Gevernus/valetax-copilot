# How this was built

Built with Claude Code over about two days (first commit 2026-10-22 17:56, the last ones on
2026-10-23). I set the design, the eval sets and the gates; agents implemented and reviewed.
The brief's 3–5 hours is closer to my directing time than to the wall clock.

- **Design and decisions**: mine, written down in [decisions.md](decisions.md) before or with
  the code; [CLAUDE.md](../CLAUDE.md) is the guide the agents worked from.
- **Implementation**: agents, one chunk at a time, each ending with ruff, mypy, the tests and
  the eval gate green.
- **Review**: each chunk went through an independent review panel (critic, reviewer, a
  skeptic scoring each finding), and the whole repository through two adversarial reviews at
  the end. Their confirmed findings were fixed, not argued away: closed-list checks on drafts,
  the language gate, the completion-step rule, ID masking, the vendor paragraph, the cost of
  the cards that need a person, and a scope cut (a 15-language number parser, a second local
  classifier, a blind number set and a significance test were removed).
- **Evals**: the golden set was written and labelled by hand; the blind ticket and drafts sets
  were written by a separate agent that never saw the code, frozen by hash before one run.

The history is the record: every route a code change moved is listed in its commit message.
