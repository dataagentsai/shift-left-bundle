# Runs against the sample project

The sample (`examples/sample-project`, a small clothing shop) has **101 planted problems** in 12 of the 13 families
(style is left out on purpose) and **16 traps**: code that looks wrong but isn't. The key is `tests/sample-key.yaml`.
Score any run with `uv run scripts/score.py findings.json`.

| Run | Date | What ran | Caught (strict) | Caught (family) | False alarms | Unplanned |
|---|---|---|---|---|---|---|
| 0 | 2 Nov 2026 | Ruff 0.17.3, starter profile, default settings | 17/101 | 19/101 | 0/16 | 33 |
| 0b | 2 Nov 2026 | Ruff 0.17.3, starter profile, `templates/ruff.toml` | 17/101 | 19/101 | 0/16 | 8 |
| 1 | 2 Nov 2026 | `shiftleft scan --stage all`: Ruff, SQLFluff, gitleaks (+ our rules), osv-scanner, vulture, complexipy, nbstripout, repo checks | 34/101 | 39/101 | 0/16 | 56 |
| 3 | 2 Nov 2026 | run 2 + purity classifier (own) joined with the tests folder | 72/101 | 74/101 | 0/16 | 79 |
| 5 | 2 Nov 2026 | run 3 + metric view checks, dbt parse + dbt-bouncer, empty-table plan check, dead code grouped by module | 88/101 | 90/101 | 0/16 | 64 |
| 6 | 2 Nov 2026 | run 5 + our own pattern rules (secret printed, personal data shown, remote test session, count-only test, logic in notebooks, column as attribute, %run chain, inline condition, runtime match) | 97/101 | 98/101 | 0/16 | 66 |
| 7 | 2 Nov 2026 | run 6 + noise rules learned on the first real repo (refine.py) | 97/101 | 98/101 | 0/16 | 66 |
| 8 | 3 Nov 2026 | run 7 + five PySpark checks from the Sonar comparison; key grown to 106 planted and 19 traps | 102/106 | 103/106 | 0/19 | 77 |
| 2 | 2 Nov 2026 | run 1 + CostLens oss-core, SparkDoctor and 2 pyspark-antipattern rules, our materialized-view, grant and bundle rules, notebook %sql extraction | 64/101 | 66/101 | 0/16 | 65 |

Details: `runs/run-0-ruff-only.md`, `runs/run-0b-ruff-tuned.md`, `runs/run-1-runner.md`, `runs/run-2-cost.md`, `runs/run-3-purity.md`, `runs/run-5-tier5.md`, `runs/run-6-patterns.md`. Real repos: `runs/real-1-ecom.md`, `runs/real-2-dlt.md`. Run 1 took under 8 seconds on a laptop, run 2 about 10.

## What run 0 taught us

- **Ruff alone covers clean code and Python security, and nothing data-specific.** It caught 11 of 20 clean-code and
  6 of 10 security problems; 0 of the cost, config, plan, dependency, purity, test, metric and setup problems.
  That gap is what Tiers 3–5 fill (SQL rules, cost adapter, bundle config rules, purity, test kit, metric views).
- **Default settings are noisy on PySpark.** 25 of 53 findings were noise: line length at 88 (13), notebook globals
  `spark`, `dbutils`, `display` reported as undefined (6), `functions as F` flagged by N812 (3), `assert` in tests (2),
  a local import in a test (1). `templates/ruff.toml` removes them without losing a catch.
- **The 8 unplanned findings left are real** (an unused import, unsorted imports, prints, naive datetimes on lines the
  key doesn't list). Unplanned findings are reported, not counted as false alarms.

## What run 1 taught us

- **Off-the-shelf tools behind one runner double the catch** (17 to 34) with still no false alarms. Secrets 2/2,
  dependencies 4/5, setup 6/7, security 7/10, complexity 2/2.
- **gitleaks' default rules caught neither planted password** (one inside a JDBC string, one as a YAML variable
  default). Three rules in `templates/gitleaks.toml` on top of the defaults caught both, and the same secret in git
  history.
- **vulture is noise on library code**: 28 findings, 1 planted. A library's public functions look unused because
  jobs call them from config. SL-CPLX-04 moved to a nightly report until entry points are read from the bundle (SL-058).
- **SQLFluff found the style issues it should** (about 20, all warnings) plus SELECT * (AM04) and bare UNION (AM02).
  It can't parse `SCHEDULE EVERY` in a materialized view; the report shows that as a note, not a finding.
- **Still missing, as planned**: cost rules in Python and SQL strings, job config, plans, purity, tests, metric views.
  These are Tiers 4 and 5.
- **Baseline works**: on a copy of the sample, recording 58 findings let the repo pass; a new `eval` then blocked.
- **The pre-commit hook works end to end** (`pre-commit try-repo`): it installed the bundle and blocked the commit.

## What run 2 taught us

- **Cost in code went from 2 of 24 to 22 of 24, job config from 0 of 9 to 8 of 9**, with no false alarms.
- **CostLens needed three things around it, none inside it**: it reads only the root `databricks.yml` (the adapter
  merges `include:` files first), it does not read `%sql` cells in Databricks source notebooks (the bundle extracts
  them and sends them to CostLens and SQLFluff), and its SQL findings carry no line (the adapter finds the keyword).
- **CostLens `select_star` flags every `SELECT *`**, including one over a three-column CTE (trap T04). SQLFluff AM04
  knows the CTE's columns, so SL-COST-CODE-13 comes from SQLFluff and `select_star` is left unmapped.
- **Young PySpark linters**: SparkDoctor adopted for 11 mapped rules; pyspark-antipattern for 2; cylint dropped (all
  duplicates). Unmapped rules are ignored and counted in a note, so their noise never reaches a pull request.
- **The scorer gave a correct finding next to a trap to both.** It now gives each finding to its nearest key entry,
  and ignores suppressed and baselined findings.
- **Still missing, as planned**: plans (needs the empty-table harness), purity, tests, metric views, dbt structure.
  That is Tier 5. Two left in cost: a SELECT * inside an f-string query (no tool reads f-strings) and the
  dependency-runtime match (SL-DEP-05).

## What run 3 taught us

- **Purity is detectable from the syntax tree for this kind of code**: 31 functions, 15 pure, 13 impure, 3 unknown.
  All 4 planted purity problems and 4 test problems (pure but untested, module with no test file) were caught, with
  no false alarms; the 2 tested pure functions in the traps were left alone.
- **Unknown is rare and honest here**: an inner UDF variable, `eval`, `subprocess`. None was wrongly called pure.
- **Three rules sharpened the classifier**: a chained call is judged by its own final method (so the `filter` in
  `spark.table(t).filter(...)` counts as logic); changing an argument in place is impure but building a local list is
  not; "could be pure" needs both a read or write and some logic, so a pure writer shell is not flagged.
- **Unplanned findings grew to 79**, mostly real by the catalog's own rules (12 pure functions untested, actions in
  logic). They are warnings, and the baseline absorbs them on adoption.

## What run 5 taught us

- **Every planted metric-view problem (7/7), plan problem (2/2), purity problem (4/4) and setup gap (7/7) is caught.**
  The metric view checks also found real problems nobody planted: Revenue and Margin summed across the same
  one-to-many join, and Margin defined differently in two views.
- **dbt works fully offline**: `dbt parse` (no warehouse) then dbt-bouncer on the manifest. It runs in a temporary
  folder; a first version left dbt's `.user.yml` in the repo, now fixed. dbt-score and dbt-project-evaluator were not
  needed.
- **The plan check needs only a schemas file**: functions whose parameters are named after a schema are planned on
  empty tables automatically. 8 ran; functions that return counts or lists are skipped.
- **Drafted tests catch the planted cartesian join on day one**: `shiftleft draft-tests` wrote 12 drafts; the
  runnable ones passed except the planted bug, and the intended cross join (marked `shiftleft: allow`) is respected.
- **Grouping dead code by module** cut unplanned findings from 88 to 64 without losing the planted one.
- **Never write into the repository**: a run killed by low memory left SQLFluff's temporary config behind. SQLFluff now
  reads its config from a temporary folder.
- **Still missed (13)**: mostly checks we planned as our own pattern rules (secret printed, personal data displayed,
  count-only test, remote test session, `%run` chain, column as attribute, inline condition, logic in notebooks,
  built-in shadowed by a wildcard import), plus a SELECT * inside an f-string, a debug count inside a print, a
  boolean flag argument (strict profile) and the runtime-version match. Next small batch: SL-064.

## What run 6 taught us

- **Nine pattern rules in one adapter, about 300 lines, no new tool.** The binding planned five of them as Opengrep
  rules; Python's own syntax tree was enough, so Opengrep stays unused. Personal column names, the inline-condition
  limit and the runtime table (Databricks Runtime to Spark and Python) are data in the binding.
- **All 9 planted problems caught, 0 traps hit.** The value-comparing test (trap T11) is not called count-only.
- **Two unplanned findings, both correct**: the helper notebook pulled in by `%run` also defines a function, and
  `explore.ipynb` shows customer names, emails and phone numbers, with that output saved in the file.
- **Still missed (4)**: a row count inside a print (P010), a SELECT * inside an f-string (P014), a boolean flag
  argument (P074, strict profile only) and `sum` shadowed by a wildcard import (P078, flagged on the import line,
  not the use). None need a new tool; leave them for Tier 6 unless a real repo shows them.

## What run 8 taught us (3 Nov)

- **The key grew for the first time**: 5 planted problems (P102–P106) and 3 traps (T17–T19) in
  `src/shop/customer_report.py`, one each for the five new checks. Scores before run 8 are out of 101 and 16 traps.
- **All 5 caught, 0 traps hit.** The traps are the look-alikes: a ranking window (needs no frame), a de-duplication on
  a key, a typed null column.
- **The new rules found 3 problems already in the shop that the key never listed**: a typeless null column in
  `wide_orders`, a join with no type in the notebook, and a long withColumn chain in `gold_kpis`.
- **On the real e-commerce repo the five rules added 3 findings, all report level and all true** (chains of 4–7
  withColumn calls). Its author states every join type and only uses ranking windows.
