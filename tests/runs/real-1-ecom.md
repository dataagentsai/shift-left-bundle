# Real repo 1: ecomsimpledataplatformusingdatabricks (2 Nov 2026)

A teaching e-commerce platform on Databricks: 13 source-format PySpark notebooks (bronze → silver → gold, SCD1/SCD2,
watermarks, data-quality checks), shared helpers pulled in with `%run ../common/_utils`, one `databricks.yml`. No tests
folder and no CI. Scanned with `shiftleft scan . --stage all`, in about 3.5 seconds. Nothing was written to the repo.

| | Blocking | Warnings | Report only | Total |
|---|---|---|---|---|
| Before the noise rules | 19 | 244 | 13 | 276 |
| After the noise rules (`refine:` in the binding) | 4 | 66 | 102 | 172 |

## Where the noise came from

| Rule | What the tools said | Why it was wrong | Done | Count |
|---|---|---|---|---|
| run-target-names | Ruff F821: undefined name (`CONFIG`, `audit`, `get_watermark`, ...) | every name comes from `%run ../common/_utils`, which Ruff cannot follow | drop | 117 (before de-duplication) |
| sql-identifiers-only | SparkDoctor SDK026 and Ruff S608: SQL injection (block) | the f-strings insert only table names from `CONFIG` or ALL_CAPS constants, or a loop over them | report; one finding per statement | 14 |
| print-in-notebook | Ruff T201: print | a notebook's print is its output | report (modules still warn) | 50 |
| random-not-security | Ruff S311: weak random | random picks for a synthetic-data generator | report | 16 |
| collect-one-row | SparkDoctor SDK002: collect without limit | `df.agg(F.max(...)).collect()` returns one row | drop | 10 |
| display-cell-sort | costlens: ORDER BY without LIMIT | SELECT-only `%sql` cells that show a sorted result at the end of a notebook | report | 10 |
| merge-builder-chain | SparkDoctor SDK009: chain too long | `DeltaTable.forName().alias().merge().whenMatched...execute()` is how a merge is written | drop | 4 |
| markdown-unicode | Ruff RUF003: ambiguous character | `×` and `–` in `# MAGIC` markdown prose | drop | 3 |
| display-is-output | costlens: action result discarded | `display(...)` is the notebook's output | drop | 2 |
| ddl-in-loop | costlens: spark.sql in a loop | `CREATE SCHEMA IF NOT EXISTS` per layer | drop | 1 |

## What is left, and is it right

- **Blocking (4), all correct by the spec.** `00_setup.py:173` puts two notebook widget values (`date_start`,
  `date_end`) straight into SQL: anyone who can set a widget or a job parameter can change the query. This is the most
  useful finding of the run. The other three put the watermark value `'{wm}'` into SQL. The author's comment says the
  value is controlled; the fix is a parameter marker (`spark.sql(q, args={"wm": wm})`) or an allow marker with that
  reason.
- **Warnings (66), correct by the spec, some opinionated:** `%run` chains in 12 notebooks plus one
  `dbutils.notebook.run` (13), I/O helpers that could take a DataFrame instead of reading it (12), functions with more
  than 5 arguments in the data-quality helpers (12), notebooks that define functions (4, `_utils` defines 16), a
  profile function that runs one query per column in a loop (5 across loop and collect checks), `uuid` and `random`
  inside logic (3), the job with no timeout (1).
- **Setup gaps (6, report):** no pre-commit, no CI, no coverage gate, no secret scan, no `bundle validate`, no tests.
  All true.

## Lessons

- **On a real repo, the noise was in the adopted tools, not our own rules.** Our 9 pattern rules gave 13 `%run`
  findings, all true by the spec. Ruff, SparkDoctor and costlens gave all the false alarms.
- **Notebooks change what a rule means.** print, display and sorted SELECT cells are output in a notebook; names come
  from `%run`. Each noise rule checks "is this a notebook" rather than switching the rule off everywhere.
- **"SQL built from variables" needs to know where the variable comes from.** Config and constants are safe; widgets,
  parameters and table values are not. The split cut 19 blockers to 4 without losing any of the sample's planted
  injection problems (sample run 7: still 97/101, 0 false alarms).

## Update 3 Nov: values traced (SL-069)

With `taint.py`, blocking drops from 4 to 1: `00_setup.py:173` now says "untrusted input reaches the SQL text: widget at line 165; widget at line 166". The three watermark queries are warnings that point at the table read in `_utils.py:109`.

## Update 3 Nov: two more checks

SL-COST-CODE-25 finds the three RFM `ntile` scores in `61_gold_customer_ltv.py`, each ranked over every customer with no partition. jscpd finds `40_silver_products_sparksql.py` repeating 23 lines of `40_silver_products.py` (the Spark SQL teaching variant; report only).
