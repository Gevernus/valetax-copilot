# Business case

**The pilot pays for itself if a ready draft saves at least $0.16 of agent time (3% of a $5
contact)**, at the golden set's ready share: an authored mix, and an upper bound for current
code. The pilot measures the live share; a downside case is below the sensitivity table. The
model bill is about $5 a month; people and hosting are about $570.

Recommended: **Jev + Haiku**. People dominate the cost, so the configuration moves the total
by less than a fifth; Jev + Haiku has the fewest violations, the best routing, the fastest
classifier, and probabilities to gate on. This is a success criterion for a pilot, not a
proven return.

## Configurations

<!-- generated:configs -->
Run `2026-10-22`, before the reply check, so the ready share is an upper bound for current code. Model cost at 10,000 tickets a month, all calls cold in brackets; total adds people and hosting.

| configuration | violations | route accuracy | ready | p50 classify / end to end (CLI) | model $ a month | total $ a month |
|---|---|---|---|---|---|---|
| **Jev + Haiku** (recommended) | 0 | 98% | 38% | 0.3 s / 7.4 s | $4.70 ($6.22) | $575 |
| Jev + Sonnet | 0 | 96% | 36% | 0.3 s / 11.7 s | $46.90 ($78.64) | $617 |
| LLM classifier + Haiku | 1 | 98% | 38% | 8.1 s / 17.8 s | $6.42 ($8.66) | $576 |
| Laya + Haiku | 0 | 61% | 1% | 0.9 s / 7.8 s | $3.37 ($4.45) + $100 host | $673 |
<!-- /generated -->

- **Sonnet** adds nothing measurable here at a much higher model bill.
- **The LLM classifier** missed one complaint flag (the ticket still reached a person via
  account lookup) and gives no probabilities to gate on. The run's one violation (en11, a
  ticket routed to a person) was a draft that copied "Start Trading!" from the KB; the same
  drafter was clean on en11 in the Jev run, so one case points to drafter variance, not the
  classifier.
- **Laya** is a data-residency option; zero-shot it almost never produces a ready draft. Plan:
  fine-tune it on the pilot's labelled tickets ([phase2.md](phase2.md)).

## Inputs

| input | value | tag | source |
|---|---|---|---|
| tickets a month | 10,000 | assumption | the brief |
| ready drafts, tokens | per configuration, from the run above | measured | cards, `run.json` |
| prices | Anthropic and TypeSafe list prices; prompts of 512+ tokens cache | official | [`evals/prices.py`](../evals/prices.py) |
| cache, reply check | 67% of calls hit the 5-minute cache; the reply check reads ~600 Jev tokens | assumption | `evals/prices.py` |
| people and hosting | $570 a month: VM $50, an engineer 2 h a week at $50, the support lead 1 h a week at $20, 52/12 weeks a month; Laya adds a $100 host | assumption | ours |
| saving | a contact costs $2 / $5 / $10; a ready draft saves 15% / 35% / 50% of its handling time | assumption | fintech email or ticket $7–12 per case, offshore often 35–60% lower ([Office Gurus 2026](https://theofficegurus.com/customer-support-cost-benchmarks-for-2026-what-you-need-to-know/), vendor); AI assistance raised "issues resolved per hour, by 15% on average" ([Brynjolfsson, Li and Raymond, QJE 2025](https://academic.oup.com/qje/article/140/2/889/7990658)), i.e. 1 − 1/1.15 ≈ 13% less time per issue across all tickets |

## The saving, as the pilot's hypothesis

Net a month for Jev + Haiku. Only ready drafts count; acknowledgements and the classified card
may save time too, but are left out rather than guessed.

<!-- generated:sensitivity -->
| cost of a contact | low: 15% saved | base: 35% saved | high: 50% saved |
|---|---|---|---|
| low $2 | $550 | $2,050 | $3,175 |
| base $5 | $2,238 | $5,988 | $8,800 |
| high $10 | $5,050 | $12,550 | $18,175 |

Downside: if only 15% of live tickets get a ready draft instead of 38%, a ready draft must save at least $0.39 (8% of a $5 contact).
<!-- /generated -->

The pilot measures handling time on ready-draft tickets against a control group randomised by
ticket, how often agents send, edit or discard a draft, and the live share of ready drafts.

## Risks

The golden set is synthetic and labelled by its author; token counts come from the CLI, not the
production API path. Details: [evals.md](evals.md).
