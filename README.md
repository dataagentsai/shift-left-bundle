# shift-left-bundle

Fail fast on PySpark, Python and Databricks SQL code before it runs: cost, security, vulnerable libraries, purity, tests, complexity, clean code, and what the repo is missing. Built from open-source tools, with no servers. The spec names no product; Databricks is the first binding, then Azure.

Guide: <https://cleandataengineering.ai/learn/shift-left/>

**Status:** the spec (0.2) is written: 131 checks in 13 families, for Python, PySpark, notebooks, SQL, dbt, materialized views and metric views. `examples/scd2` shows SCD2, idempotency, duplicates, dropped records and cartesian joins tested offline. `examples/sample-project` is a shop with 101 planted problems and 16 traps; `scripts/score.py` scores any run against the hidden key (`tests/RESULTS.md`). The runner works: `shiftleft scan PATH --stage pr` (64 of 101 caught on the sample, no false alarms; see below). See `TODO.md`.

## Use it

```
pip install "shiftleft[tools] @ git+https://github.com/dataagentsai/shift-left-bundle"   # gitleaks and osv-scanner: install separately
pip install sparkdoctor==0.1.8 pyspark-antipattern==0.4.1                            # optional PySpark rules; costlens-core optional too
shiftleft scan . --stage pr --sarif shiftleft.sarif --md shiftleft-review.md          # exit 1 if a blocking finding is new
shiftleft baseline . --out .shiftleft-baseline.json                                   # adopt on an existing repo
shiftleft scan . --stage pr --baseline .shiftleft-baseline.json
```

Or as a pre-commit hook: see `.pre-commit-hooks.yaml`. Stages: `commit`, `pr`, `nightly`, `predeploy`, `all`.
Mark an intended exception with `# shiftleft: allow <check-id> -- <reason>` (a reason is required).

## Layout

```
core/families.yaml      the 13 check families
core/artifacts.yaml     what a check reads (applies_to)
core/stages.yaml        commit, pull request, nightly, pre-deploy
core/gates.yaml         block / warn / report, baseline, thresholds (coverage, complexity, mutation)
core/purity.yaml        what makes a function pure, impure or unknown (categories, no product names)
core/standards.yaml     standards a check may cite (CWE, OWASP Top 10, OpenSSF Scorecard, SARIF, PEP 8, SPDX)
core/dac_ids.yaml       Data Assurance Catalog ids a check may link to (copied, with source commit)
catalog/checks/*.yaml   the checks, one file per family     ← the spec; edit here
catalog/INDEX.md        generated list of every check with its binding
bindings/databricks.yaml  check → tool + rule + status; purity categories → concrete PySpark calls
src/shiftleft/          the runner: ports, adapters (one per tool), engine, reports, cli
scripts/lint.py         spec rules R1–R12
tests/                  table-driven tests
examples/scd2/          pure SCD2 + test kit + table-driven tests, runs on local Spark
templates/              pre-commit, dev container, GitHub Actions, Azure DevOps (not yet run)
```

## Commands

```
uv run scripts/lint.py                               # check the catalog and bindings
uv run scripts/index.py                              # rebuild catalog/INDEX.md
uv run --with pytest --with pyyaml pytest -q tests   # spec, scorer and runner tests (examples/scd2 has its own, needs pyspark)
uv run scripts/sync_dac_ids.py ../data-platform-catalog   # refresh DAC ids
uv run scripts/score.py findings.json                # score a run against the sample's hidden key
```

## A check record

```yaml
- id: SL-COST-CODE-14          # SL-<FAMILY>-NN
  status: draft
  since: 0.1.0
  title: Join with no join condition
  level: MUST                   # MUST / SHOULD / MAY, and the statement uses the word
  statement: A query MUST NOT join two tables without a join condition unless ...
  why: A missing join key matched every order with every customer ...   # a short failure story
  fix: Add the join key ...
  stage: commit                 # where it first runs
  gate: block                   # starting gate; only MUST checks may block
  found_by: static              # static / plan / test / repo
  cost_impact: high             # high / medium / low / null
  dac: [COST-02]                # Data Assurance Catalog obligations it gives evidence for
  cites: []                     # CWE, OWASP and others, by id
  related: [SL-COST-PLAN-01]
```

No product or tool names in `title`, `statement`, `why` or `fix`. They belong in `bindings/`.
