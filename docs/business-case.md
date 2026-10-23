# Business case

**The pilot pays for itself if a ready draft saves at least $0.16 of agent time (3% of a $5
contact)**, at the golden set's ready share: an authored mix, not a forecast of live traffic.
The pilot measures the live share; a downside case is below the sensitivity table. The model
bill is about $4 a month; people and hosting are about $570.

Recommended: **Jev + Haiku**. People dominate the cost, so the configuration moves the total
by less than a fifth. No configuration had a violation; Jev + Haiku has the best routing, a
classifier as fast as the local Laya and over ten times faster than the LLM classifier, and
probabilities to gate on. This is a success criterion for a pilot, not a proven return.

## Configurations

<!-- generated:configs -->
Run `2026-10-23`, with the reply check. Model cost at 10,000 tickets a month, all calls cold in brackets; total adds people and hosting.

| configuration | violations | route accuracy | ready | p50 classify / end to end (CLI) | model $ a month | total $ a month |
|---|---|---|---|---|---|---|
| **Jev + Haiku** (recommended) | 0 | 98% | 38% | 0.3 s / 5.2 s | $3.71 ($4.89) | $574 |
| Jev + Sonnet | 0 | 96% | 36% | 0.6 s / 6.5 s | $38.19 ($62.82) | $608 |
| LLM classifier + Haiku | 0 | 96% | 36% | 4.7 s / 10.8 s | $5.54 ($7.44) | $576 |
| Laya + Haiku | 0 | 61% | 1% | 0.3 s / 0.3 s | $0.33 ($0.48) + $100 host | $670 |
<!-- /generated -->

- **Sonnet** adds nothing measurable here at a much higher model bill.
- **The LLM classifier** routes within one ticket of Jev (no significant difference, see
  [evals.md](evals.md#results)) but missed one complaint flag (the ticket still reached a
  person via account lookup), is slower, and gives no probabilities to gate on.
- **Laya** is a data-residency option; zero-shot it almost never produces a ready draft. Plan:
  fine-tune it on the pilot's labelled tickets ([phase2.md](phase2.md)).

## Inputs

| input | value | tag | source |
|---|---|---|---|
| tickets a month | 10,000 | assumption | the brief |
| ready drafts, tokens | per configuration, from the run above, the Jev reply check included | measured | cards, `run.json` |
| prices | Anthropic and TypeSafe list prices; prompts of 512+ tokens cache | official | [`evals/prices.py`](../evals/prices.py) |
| cache | 67% of calls hit the 5-minute cache | assumption | `evals/prices.py` |
| people and hosting | $570 a month: VM $50, an engineer 2 h a week at $50, the support lead 1 h a week at $20, 52/12 weeks a month; Laya adds a $100 host | assumption | ours |
| saving | a contact costs $2 / $5 / $10; a ready draft saves 15% / 35% / 50% of its handling time | assumption | fintech email or ticket $7–12 per case, offshore often 35–60% lower ([Office Gurus 2026](https://theofficegurus.com/customer-support-cost-benchmarks-for-2026-what-you-need-to-know/), vendor); AI assistance raised "issues resolved per hour, by 15% on average" ([Brynjolfsson, Li and Raymond, QJE 2025](https://academic.oup.com/qje/article/140/2/889/7990658)), i.e. 1 − 1/1.15 ≈ 13% less time per issue across all tickets |

## The saving, as the pilot's hypothesis

Net a month for Jev + Haiku. Only ready drafts count; acknowledgements and the classified card
may save time too, but are left out rather than guessed.

<!-- generated:sensitivity -->
| cost of a contact | low: 15% saved | base: 35% saved | high: 50% saved |
|---|---|---|---|
| low $2 | $551 | $2,051 | $3,176 |
| base $5 | $2,239 | $5,989 | $8,801 |
| high $10 | $5,051 | $12,551 | $18,176 |

Downside: if only 15% of live tickets get a ready draft instead of 38%, a ready draft must save at least $0.39 (8% of a $5 contact).
<!-- /generated -->

The pilot measures handling time on ready-draft tickets against a control group randomised by
ticket, how often agents send, edit or discard a draft, and the live share of ready drafts;
the sample sizes and the go/no-go are in [rollout.md](rollout.md).

## Risks

The golden set is synthetic and labelled by its author; on a blind set written separately,
every ticket that needed a person reached one, and fewer got a ready draft. Token counts come
from the CLI, not the production API path. Details: [evals.md](evals.md).
