# TODO: Shift-Left Bundle

The working list. The plan and its reasons live in `PLAN.html`; the reuse ledger in `REUSE.md`.
Every progress report opens with the "Start here" table.

## Start here

| Step | What | Status |
|---|---|---|
| 0 | Reuse check into `REUSE.md` (SL-001) | done 2 Nov |
| 1 | Decisions D1–D8 in PLAN.html (SL-002) | done 2 Nov: all as recommended |
| 2 | Spec v0.1: check record format, ~60 checks in 12 families, DAC links, linter, table-driven tests (SL-010) | next |
| 3 | Sample repo with planted problems + hidden answer key (SL-011) | next |
| 4 | Runner + Databricks binding over the adopted tools; SARIF + REVIEW.md; run 1 (SL-020) | later |
| 5 | Delta: purity report, empty-table harness, repo-review plugins for data repos (SL-021..023) | later |
| 6 | Real repo run (SL-030) | later |
| 7 | Tutorial page (SL-031) | later |
| 8 | Azure binding (SL-040) | later |

## Open questions

- CostLens oss-core: publish as a package? Until then the cost adapter is optional (D2).
- Databricks UCX code linter: still maintained? Last PyPI release Oct 2025. Check in step 4.
- Trial pyspark-antipattern and SparkDoctor on the sample repo; keep only rules CostLens lacks.
