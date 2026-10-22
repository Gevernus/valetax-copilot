# Reply checks on labelled drafts: patterns

465 rows (evals/drafts.jsonl). Cells: value (hits/n, Wilson 95% CI).

| label | dev recall | dev precision | holdout recall | holdout precision |
|---|---|---|---|---|
| decision | 56% (40/72, 44%–66%) | 100% (40/40, 91%–100%) | 34% (10/29, 20%–53%) | 100% (10/10, 72%–100%) |
| check | 73% (11/15, 48%–89%) | 100% (11/11, 74%–100%) | 38% (5/13, 18%–64%) | 100% (5/5, 57%–100%) |
| handover | 91% (42/46, 80%–97%) | 100% (42/42, 92%–100%) | 72% (33/46, 57%–83%) | 100% (33/33, 90%–100%) |
| any | 71% (93/131, 63%–78%) | 100% (93/93, 96%–100%) | 55% (48/88, 44%–64%) | 100% (48/48, 93%–100%) |

dev misses: d013, d021, d024, d025, d026, d027, d036, d038, d039, d040, d042, d043, d044, d045, d046, d047, d048, d049, d050, d051, d052, d053, d054, d055, d056, d057, d058, d060, d065, d067, d068, d069, d070, d071, d072, d085, d246, d417, d426
dev false alarms: none

holdout misses: d119, d121, d122, d123, d127, d128, d130, d131, d134, d135, d136, d137, d139, d142, d143, d144, d145, d146, d148, d149, d151, d152, d153, d154, d156, d158, d160, d161, d162, d163, d164, d165, d166, d167, d168, d169, d170, d303, d424, d427
holdout false alarms: none
