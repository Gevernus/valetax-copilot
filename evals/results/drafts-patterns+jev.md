# Reply checks on labelled drafts: patterns+jev

465 rows (evals/drafts.jsonl). Cells: value (hits/n, Wilson 95% CI). Model jev-1.14.0, reply-v1, threshold 0.5.

| label | dev recall | dev precision | holdout recall | holdout precision |
|---|---|---|---|---|
| decision | 100% (72/72, 95%–100%) | 100% (72/72, 95%–100%) | 100% (29/29, 88%–100%) | 83% (29/35, 67%–92%) |
| check | 87% (13/15, 62%–96%) | 100% (13/13, 77%–100%) | 100% (13/13, 77%–100%) | 100% (13/13, 77%–100%) |
| handover | 100% (46/46, 92%–100%) | 90% (46/51, 79%–96%) | 100% (46/46, 92%–100%) | 92% (46/50, 81%–97%) |
| any | 100% (131/131, 97%–100%) | 99% (131/132, 96%–100%) | 100% (88/88, 96%–100%) | 97% (88/91, 91%–99%) |

dev misses: d044, d045
dev false alarms: d014, d044, d045, d103, d253

holdout misses: none
holdout false alarms: d147, d149, d150, d156, d158, d159, d174, d218, d317, d375
