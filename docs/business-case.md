# Business case: is it worth running at 10,000 tickets a month?

**Yes, as a co-pilot with Jev classification and Haiku drafting.** The model bill is about
$4–6 a month; the cost that matters is people's time to keep it correct (about $530 a month
assumed). It pays for itself if it saves the team more than about $0.30 of agent time per
ticket, and on our golden set it never let a ticket that needs a person through.

## Cost per configuration, measured

Measured on the 80-ticket golden set (`evals/results/2026-10-22.json`, `-v3.json`); our own
tokens at API list prices, CLI overhead removed ([evals.md](evals.md#method)). "Warm" prices
the ~2,000-token system prompt as a cache read, "cold" as a 5-minute cache write; at 10k
tickets a month (one every ~4 minutes on average) real traffic sits between the two.

| configuration | hard-rule violations | route accuracy | drafts ready | model cost per 10k tickets | p50 latency |
|---|---|---|---|---|---|
| **Jev + Haiku** (recommended) | 0 | 98% (91–99%) | 38% | **$3.40–6.10** | 5.7–7.4 s |
| Jev + Sonnet | 0 | 96% (90–99%) | 36% | $33–78 | 11.7 s |
| LLM classifier + Haiku | 1 | 98% (91–99%) | 38% | $5.20–8.50 | 17.8 s |
| Laya zero-shot + Haiku | 0 | 61% (50–71%) | 1% | $2.80–4.40 + a local machine | 7.8 s |

Prices: Haiku $0.10/$0.50 and Sonnet $2/$10 per million input/output tokens, cache read 0.1×,
cache write 1.25× (Anthropic list prices). Jev $0.042 per million input tokens, output free:
reported consistently by third parties (Zuplo gateway docs, launch coverage); **TypeSafe
publishes no price page, so this is unverified**. At ~1,180 tokens per ticket Jev costs about
$0.50 a month at this volume; even at ten times that price it does not change the answer.
Latency was measured through the `claude` CLI, which adds several seconds of start-up; the API
should be faster, but that is not measured here.

## Fixed cost (assumptions)

| item | assumption | per month |
|---|---|---|
| hosting | one small VM for the service; Laya adds a CPU/GPU box if used | $50 |
| weekly review and fixes | 2 h a week of an engineer at $50/h | $400 |
| support lead's review time | 1 h a week at $20/h | $80 |
| **total fixed** | | **$530** |

## What it saves (assumptions, with sensitivity)

- **A1. Human cost per contact.** Industry figures are $6–20 per contact (vendor sources, see
  the research notes); an offshore broker team is likely cheaper, so the table starts at $2.
- **A2. Time saved.** 50% of handling time on a ticket with a ready draft; 15% on a ticket
  that needs a person but arrives classified, prioritised and with a drafted acknowledgement,
  decline or partial answer. For scale: a field study of an LLM assistant in customer support
  measured +14% resolutions per hour on average and +34% for new agents (NBER, 2023).
- **A3. Share of ready drafts in live traffic.** Unknown. The golden set is built to be hard
  (60% needs a person) and gives 38%; live traffic has more routine questions. 30–70% shown.

Monthly saving with 20% of tickets assisted (`uv run python -m evals.business_case --date 2026-10-22`):

| cost per contact | 30% ready | 50% ready | 70% ready |
|---|---|---|---|
| $2 | $3,600 | $5,600 | $7,600 |
| $4 | $7,200 | $11,200 | $15,200 |
| $6 | $10,800 | $16,800 | $22,800 |
| $10 | $18,000 | $28,000 | $38,000 |

Break-even against $530 a month: **$0.29 of agent time per contact** at the low end. For
comparison, per-resolution pricing of hosted AI agents is about $0.50–0.99 per resolved
ticket (Fin $0.99; a forex broker on another vendor about $0.50, single source), i.e. roughly
$2,500–5,000 a month at this volume for a customer-facing bot, with less control over the
hard rules.

## Which configuration, and why not the others

- **Jev + Haiku.** Best measured quality, lowest latency, cost negligible.
- **Sonnet** adds nothing measurable on this set at roughly 10× the drafting cost. Revisit when
  the KB grows and answers need more synthesis; route to it by rule, not by default.
- **LLM as classifier** ties on routing but is 25× slower per ticket, returns no probabilities
  (so no confidence gate), and missed one complaint.
- **Laya** matters for **data residency**: classification runs inside the perimeter, only
  masked text leaves it, and there is no third-party dependency for routing. Zero-shot it is
  not usable: it flags almost everything and sends 79 of 80 tickets to a person (safe, but no
  value). The plan is to fine-tune it on the pilot's labelled tickets ([phase2.md](phase2.md))
  and switch when it matches Jev on the golden set. Cost is not the reason: Jev is ~$0.50 a
  month here.

## Risks that the numbers do not cover

- The golden set is ours: 80 synthetic tickets labelled by the same person who built the
  system. The pilot's first weeks replace it with real tickets and agents' corrections.
- The production LLM path (`--llm anthropic`) is written but not run; the evals used the CLI.
- The KB contradicts itself in three places ([kb-issues.md](kb-issues.md)); until fixed, every
  ticket on those topics goes to a person. That content fix is the cheapest gain available.
