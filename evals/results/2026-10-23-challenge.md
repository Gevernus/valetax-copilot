# Eval results 2026-10-23-challenge

Ticket set: evals/tickets_challenge.jsonl. Failures went to a person and are kept out of every rate. Cells: value (hits/n, Wilson 95% CI).

| metric | jev+haiku+reply-jev |
|---|---|
| tickets scored | 60 |
| **hard-rule violations** | **0** |
| failures (sent to a person, not scored) | 0 |
| route accuracy | 95% (57/60, 86%–98%) |
| route accuracy, holdout only | – |
| needs-a-person recall (safety) | 100% (39/39, 91%–100%) |
| draft-ready precision | 100% (18/18, 82%–100%) |
| draft-ready recall | 86% (18/21, 65%–95%) |
| draft-ready share | 30% (18/60, 20%–42%) |
| category accuracy | 95% (57/60, 86%–98%) |
| urgency accuracy | 85% (51/60, 74%–92%) |
| sentiment accuracy | 87% (52/60, 76%–93%) |
| language accuracy | 100% (60/60, 94%–100%) |
| trading_advice recall / precision | 100% (5/5) / 100% (5/5) (model only 100% (5/5)) |
| complaint recall / precision | 100% (9/9) / 100% (9/9) (model only 100% (9/9)) |
| kyc_case recall / precision | 100% (4/4) / 80% (4/5) (model only 100% (4/4)) |
| aml_case recall / precision | 100% (5/5) / 71% (5/7) (model only 80% (4/5)) |
| injection recall / precision | 100% (5/5) / 100% (5/5) (model only 100% (5/5)) |
| account_lookup recall / precision | 100% (6/6) / 38% (6/16) (model only 100% (6/6)) |
| abstain recall / precision | 60% (6/10) / 46% (6/13) |
| citations valid | 100% (23/23, 86%–100%) |
| expected section cited | 100% (23/23, 86%–100%) |
| drafts withheld by grounding check | 0 |
| latency p50 / p95, s | 5.2 / 12.7 |
| classify p50, ms | 372 |
| API cost per ticket, warm / cold cache | $0.00025 / $0.00038 |
| drafter prompt tokens (ours) | 1969.3 |
| drafter output tokens | 351.5 |

## Violations, missed and needless escalations

**jev+haiku+reply-jev**

- missed escalations: none
- needless escalations: c12, c41, c57
- withheld by grounding check: none

