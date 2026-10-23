# Business case

<!-- generated:headline -->
**A ready draft must save at least $0.61 of agent time (12% of a $5 contact) for the co-pilot to pay for itself** at the share of ready drafts on the golden set (25%, an authored mix, not a forecast). **If only 15% of live tickets get one, it must save $1.10 (22%).** The base hypothesis, 35% of a $5 contact, is $1.75. Costs a month: models about $4, people and hosting about $570, reading the cards that need a person about $938 (15 s of a 10-minute contact each); once, the help-desk integration, about $8,000.
<!-- /generated -->

The pilot measures the live share of ready drafts and the time they save; this is a success
criterion for a pilot, not a proven return.

Recommended: **Jev + Haiku**. Time, not models, dominates the cost, so the configuration moves
the total by less than a fifth. No configuration had a violation; Jev + Haiku has the best routing, a
classifier over ten times faster than the LLM classifier, and probabilities to gate on.

## Configurations

<!-- generated:configs -->
Run `2026-10-23`, with the reply check. Model cost at 10,000 tickets a month, all calls cold in brackets; total adds people and hosting and the reading of the cards that need a person at a $5 contact.

| configuration | violations | route accuracy | ready | p50 classify / end to end (CLI) | model $ a month | total $ a month |
|---|---|---|---|---|---|---|
| **Jev + Haiku** (recommended) | 0 | 92% | 25% | 0.3 s / 5.2 s | $3.71 ($4.89) | $1,511 |
| Jev + Sonnet | 0 | 91% | 24% | 0.6 s / 6.5 s | $38.19 ($62.82) | $1,561 |
| LLM classifier + Haiku | 0 | 91% | 24% | 4.7 s / 10.8 s | $5.54 ($7.44) | $1,529 |
<!-- /generated -->

- **Sonnet** adds nothing measurable here at a much higher model bill.
- **The LLM classifier** routes within one ticket of Jev (no significant difference, see
  [evals.md](evals.md#results)) but missed one complaint flag (the ticket still reached a
  person via account lookup), is slower, and gives no probabilities to gate on.

## Inputs

| input | value | tag | source |
|---|---|---|---|
| tickets a month | 10,000 | assumption | the brief |
| ready drafts, tokens | per configuration, from the run above, the Jev reply check included | measured | cards, `run.json` |
| prices | Anthropic and TypeSafe list prices; prompts of 512+ tokens cache | official | [`evals/prices.py`](../evals/prices.py) |
| cache | 67% of calls hit the 5-minute cache | assumption | `evals/prices.py` |
| people and hosting | $570 a month: VM $50, an engineer 2 h a week at $50, the support lead 1 h a week at $20, 52/12 weeks a month | assumption | ours |
| reading the other cards | 15 s per "needs a person" card, of a 10-minute contact (2.5% of its cost) | assumption | ours; the pilot measures it against control |
| integration, once | $8,000: 160 h at $50 for the help-desk webhook and sidebar card, card buttons, edit distance and per-agent flags ([rollout.md](rollout.md#metrics)) | assumption | ours |
| saving | a contact costs $2 / $5 / $10; a ready draft saves 15% / 35% / 50% of its handling time | assumption | fintech email or ticket $7–12 per case, offshore often 35–60% lower ([Office Gurus 2026](https://theofficegurus.com/customer-support-cost-benchmarks-for-2026-what-you-need-to-know/), vendor); AI assistance raised "issues resolved per hour, by 15% on average" ([Brynjolfsson, Li and Raymond, QJE 2025](https://academic.oup.com/qje/article/140/2/889/7990658)), i.e. 1 − 1/1.15 ≈ 13% less time per issue across all tickets |

## The saving, as the pilot's hypothesis

Net a month for Jev + Haiku, after the models, people and hosting and the reading of the
other cards. Only ready drafts save time here; acknowledgements and the classified card may
save some too, but are left out rather than guessed.

<!-- generated:sensitivity -->
| cost of a contact | low: 15% saved | base: 35% saved | high: 50% saved |
|---|---|---|---|
| low $2 | −$199 | $801 | $1,551 |
| base $5 | $364 | $2,864 | $4,739 |
| high $10 | $1,301 | $6,301 | $10,051 |

The $8,000 integration pays back in 2.8 months in the base case, never in a cell below zero.
<!-- /generated -->

The pilot measures handling time on ready-draft tickets against a control group randomised by
ticket, how often agents send, edit or discard a draft, and the live share of ready drafts;
the sample sizes and the go/no-go are in [rollout.md](rollout.md).

## Risks

The golden set is synthetic and labelled by its author; on a blind set written separately,
every ticket that needed a person reached one, and fewer got a ready draft. Token counts come
from the CLI, not the production API path. Details: [evals.md](evals.md).
