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
| 2 | 2 Nov 2026 | run 1 + CostLens oss-core, SparkDoctor and 2 pyspark-antipattern rules, our materialized-view, grant and bundle rules, notebook %sql extraction | 64/101 | 66/101 | 0/16 | 65 |

Details: `runs/run-0-ruff-only.md`, `runs/run-0b-ruff-tuned.md`, `runs/run-1-runner.md`, `runs/run-2-cost.md`, `runs/run-3-purity.md`. Run 1 took under 8 seconds on a laptop, run 2 about 10.

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
