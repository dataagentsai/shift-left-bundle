# Real repo 2: Project5-DLTStreamingProject (3 Nov 2026)

A metadata-driven streaming framework on Databricks: Lakeflow Declarative Pipelines (DLT) controllers, reader, writer,
processor and reconciliation as plain Python modules under `framework/`, a deploy script that creates pipelines with
the Databricks SDK, SQL that creates and seeds the metadata tables, and a scenario harness under `testing/` (no unit
tests). Different from repo 1, which was notebooks. Scanned with `shiftleft scan . --stage all` in about 4 seconds;
nothing written to the repo.

| | Blocking | Warnings | Report only | Total |
|---|---|---|---|---|
| With the noise rules from repo 1 | 3 | 200 | 25 | 228 |
| After 4 more noise rules learned here | 3 | 83 | 31 | 117 |

The repo 1 rules carried over with almost nothing to do (one one-row collect). This repo's noise was different:

| Rule | What the tools said | Why it was wrong | Done | Count |
|---|---|---|---|---|
| group-per-file (setting) | SQLFluff LT02 / LT05 / LT14: 102 formatting findings in 4 SQL files | the team never adopted a SQL formatter; it is one fix per file (run the formatter), not 102 | one finding per file | 102 → 4 |
| platform-only-import | Ruff PLC0415: import inside a function | `import dlt` and `databricks.sdk` exist only on the platform; importing them late is deliberate | drop | 7 |
| print-in-cli | Ruff T201: print | the deploy script is a command-line tool; print is its output | report | 6 |
| collect-small-table (setting) | SparkDoctor SDK002: collect without limit | metadata `*_config` and `*_master` tables are collected whole on purpose; the team declares them in `refine_settings.small_tables` | drop | 6 |

## What is left, and is it right

- **Blocking (3), all correct by the spec.** The deploy script puts its `--source` command-line value inside quotes in
  a WHERE clause (the SDK's statement API takes parameters). Reconciliation builds a JDBC query from schema and table
  names read from metadata. The metadata seed starts with `DELETE FROM ... platform_config` with no WHERE: meant as
  "truncate then insert" for a demo, but the same file run against production clears the config; `TRUNCATE TABLE`
  or an allow marker with that reason states the intent.
- **Warnings (83), correct by the spec:** functions with more than 5 arguments (19 with the positional variant),
  `pyspark` imported inside functions in 9 places (unlike `dlt`, pyspark is always installed, so this is habit, not
  need), 9 pure functions with no unit test, 8 readers that could take the DataFrame as a parameter, prints in library
  modules (6), broad `except Exception` (4), naive datetimes (3).
- **Setup gaps (6, report):** no pre-commit, no CI, no coverage gate, no secret scan, SQL not linted, no tests folder.
  The scenario harness under `testing/` runs on a cluster; it is not a unit test suite.

## Lessons

- **Each new repo brings its own noise.** Repo 1's ten rules removed one finding here; four new rules were needed. Two
  of them need team knowledge (which modules exist only on the platform, which tables are small), so they read
  settings from the binding instead of guessing.
- **Formatting is one fix, so it should be one finding.** Without grouping, formatting was 45% of all findings and
  would bury everything else on a pull request.
- **The blockers on both real repos are the same kind:** values or names put into SQL text. Both repos' authors knew
  the inputs were trusted; neither said so in the code. The allow marker with a reason is the right answer when that
  is true.

## Update 3 Nov: values traced (SL-069)

The deploy blocker now says "untrusted input reaches the SQL text: command-line at deploy/create_dlt_pipelines.py:142". `recon.py` is not traced (its rows are a dict built field by field in another module), so it keeps the tool's wording and stays blocking.
