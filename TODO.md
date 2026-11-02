# TODO: Shift-Left Bundle

The working list, by tier. The plan and its reasons live in `PLAN.html`; the reuse ledger in `REUSE.md`.
Every progress report opens with the "Start here" table. A tier starts when the one before it is done,
except Tier 7 (teaching), which runs alongside.

## Start here

| Tier | What | Status |
|---|---|---|
| 0 | Ground: reuse check, decisions, plan, public repo, site guide | done 2 Nov |
| 1 | Spec v0.1: the checks, written once, no product names | done 2 Nov: 90 checks, linter clean, 41 tests |
| 1b | Spec 0.2: notebooks, dbt, materialized views, metric views (new SEM family), 20 more clean-code habits, Ruff profiles (404 / 600 rules), osv-scanner; SCD2 example with test kit; CI and container templates | done 2 Nov: 131 checks, 51 lint tests, example 27 tests |
| 2 | Proof material: sample repo with planted problems and a hidden answer key | done 2 Nov: 101 planted, 16 traps; run 0 (Ruff only) 17/101, 0 false alarms |
| 3 | Wire the off-the-shelf tools through one runner; run 1 on the sample | done 2 Nov: 8 adapters, run 1 = 34/101, 0 false alarms, hook and baseline proven |
| 4 | Cost adapter: existing cost rules behind the cost port; trial the young PySpark linters | done 2 Nov: run 2 = 64/101, 0 false alarms |
| 5 | The delta: purity report, empty-table plan harness, gap report | done 2 Nov: run 5 = 88/101; with our own pattern rules (SL-064) run 6 = 97/101, 0 false alarms |
| 6 | Real repo, cut the noise, run 2 | in progress: e-commerce repo scanned, 10 noise rules (276 → 172 findings, 19 → 4 blocking, all 4 correct); sample still 97/101, 0 false alarms; Sonar gaps: SL-065 done (spec 0.3, 136 checks, run 8 = 102/106, 0/19 false alarms), SL-066 pyright dropped after trial; repo 2 (DLT framework) done: 4 more noise rules, 228 → 117 findings, 3 blocking, all correct; SL-067–069 and SL-065b next |
| 7 | Teach and release: site pages, Claude skill, v0.1 tag | alongside |
| 8 | Azure binding | later |

## Tier 0: ground

| Id | Task | Status |
|---|---|---|
| SL-001 | Reuse check into REUSE.md (tools, licences, release dates, verdicts) | done 2 Nov |
| SL-002 | Decisions D1–D8 | done 2 Nov: all as recommended |
| SL-003 | Plan page (PLAN.html) | done 2 Nov |
| SL-004 | Public repo dataagentsai/shift-left-bundle | done 2 Nov |
| SL-005 | Site guide /learn/shift-left/ (hub + 9 pages, code samples run on Spark 3.5.1) | done 2 Nov |

## Tier 1: spec v0.1

| Id | Task | Status |
|---|---|---|
| SL-010 | Check record format: id, family, title, level, statement, why (a failure story), fix, stage (commit / PR / nightly / pre-deploy), gate (block / warn / report), cost impact, `dac:` links, `cites:` | done 2 Nov |
| SL-011 | Family list and id scheme (COST-CODE, COST-PLAN, COST-CONFIG, SEC, SECRET, DEP, PURE, TEST, CPLX, CLEAN, STYLE, SETUP) | done 2 Nov |
| SL-012 | 90 checks (planned about 60) across the 12 families, each linked to DAC ids (COST-02/03/04, SEC-02, REL-01/02/05, TEST-03) | done 2 Nov |
| SL-013 | Purity spec: the impure list (reads, writes, dbutils, clock, random, env, globals, actions), the known-pure list, the unknown rule, the `@pure` marker | done 2 Nov |
| SL-014 | Gate policy as data: what blocks at start, baseline file format, changed-lines coverage at 80% | done 2 Nov |
| SL-015 | Databricks binding v0: check id → tool + rule id + config | done 2 Nov |
| SL-016 | Catalog linter (required fields, no product names outside bindings, ids unique, DAC links resolve) + table-driven tests | done 2 Nov |

## Tier 1b: spec 0.2 (2 Nov)

| Id | Task | Status |
|---|---|---|
| SL-017 | `applies_to` on every check (python, pyspark, notebook, sql, dbt, metric-view, materialized-view, bundle-config, iac, repo) | done 2 Nov |
| SL-018 | SEM family: metric definitions (parse, aggregate, ratio, fan-out, one definition, descriptions, known-answer tests) | done 2 Nov |
| SL-019 | Clean code to 37 habits; Ruff starter (404 rules) and strict (600) profiles; ruff_map to check ids; lint rule R12 | done 2 Nov |
| SL-024 | Notebooks (outputs, %run chains, %pip), dbt (tests, references, layers, descriptions), materialized views (incremental refresh, chains) | done 2 Nov |
| SL-025 | osv-scanner as main vulnerability tool; Scorecard report-only | done 2 Nov |
| SL-026 | examples/scd2: pure SCD2, test kit (idempotent, unique, nothing dropped, no fan-out, no cartesian), planted-bug tests | done 2 Nov: 27 passed on Spark 3.5.1 |
| SL-027 | templates: pre-commit, dev container, GitHub Actions, Azure DevOps | written, not yet run (SL-072) |

## Tier 2: proof material

| Id | Task | Status |
|---|---|---|
| SL-020 | Sample repo (a small shop pipeline: bronze → silver → gold, notebooks, SQL, bundle YAML) | done 2 Nov: Harbour Threads, Python + notebooks + SQL + MVs + metric views + dbt + bundle |
| SL-021 | Planted problems: one or more per check family, including impure-could-be-pure and untested pure functions | done 2 Nov: 101 planted in 12 families |
| SL-022 | False-positive traps: code that looks wrong but isn't | done 2 Nov: 16 traps |
| SL-023 | Hidden answer key + scoring script (caught, missed, false alarms per family) | done 2 Nov: tests/sample-key.yaml + scripts/score.py + 14 tests |

## Tier 3: off-the-shelf tools through one runner

| Id | Task | Status |
|---|---|---|
| SL-030 | Runner skeleton: ports (Scanner, Reporter, Gate, Baseline), adapter registry chosen by the binding YAML | done 2 Nov: src/shiftleft (ports, registry, engine, cli) |
| SL-031 | Adapters (Ruff settings in templates/ruff.toml from run 0): Ruff (lint, clean code, security, C901), SQLFluff, sqlglot, Opengrep, gitleaks, pip-audit, Checkov | done 2 Nov for Ruff, SQLFluff, gitleaks (+3 rules), osv-scanner. Opengrep with our rules moves to Tier 5; Checkov waits for a repo with Terraform; sqlglot rules come with the cost adapter (Tier 4) |
| SL-032 | Adapters: pytest + coverage.py + diff-cover, complexipy, import-linter, vulture | partly 2 Nov: complexipy, vulture done. pytest + coverage + diff-cover and import-linter move to Tier 5 with the test kit |
| SL-033 | Findings normalised to SARIF with our check ids; REVIEW.md in fix-first order | done 2 Nov: SARIF 2.1.0, JSON, REVIEW.md |
| SL-034 | Gate + baseline: block list, warn the rest, only new findings fail | done 2 Nov: gates from the catalog, suppression with reason, baseline by fingerprint |
| SL-035 | `.pre-commit-hooks.yaml` and the commit / PR / nightly / pre-deploy split | done 2 Nov: .pre-commit-hooks.yaml; proven with pre-commit try-repo |
| SL-036 | Run 1 on the sample; record the score | done 2 Nov: 34/101 strict, 39/101 by family, 0/16 traps (tests/RESULTS.md) |

## Tier 4: cost adapter

| Id | Task | Status |
|---|---|---|
| SL-040 | Existing cost rules (CostLens oss-core: SQL, Python, plan, bundle config) behind the cost port; map their rule ids to our check ids; optional until published as a package | done 2 Nov: costlens adapter (optional import), bundle includes merged, notebook %sql cells extracted, keyword line lookup; select_star left unmapped (false alarm) |
| SL-041 | Trial pyspark-antipattern and SparkDoctor on the sample; keep only rules the existing set lacks | done 2 Nov: SparkDoctor adopted (11 rules), pyspark-antipattern (2 rules), cylint dropped (REUSE.md) |
| SL-042 | Add missing plan rules: CartesianProduct, Python UDF evaluation (from CostIntelligence1) | done 2 Nov: CartesianProduct, nested-loop, Python UDF, shuffles in the plan harness |

## Tier 5: the delta

| Id | Task | Status |
|---|---|---|
| SL-050 | Purity report: pure / impure / unknown per function, call chain, counts, refactor hint per impure-could-be-pure | done 2 Nov: src/shiftleft/purity.py + `shiftleft purity`; run 3 PURE 4/4 |
| SL-051 | Test-time purity fixture: Spark reads, writes and catalog calls fail inside pure-function tests; run-twice check | done 2 Nov: shiftleft.pytest_plugin, @pytest.mark.pure, assert_repeatable |
| SL-052 | Empty-table plan harness: build empty DataFrames from schemas (contracts or DDL) and EXPLAIN each job's transforms | done 2 Nov: plan_harness.py + shiftleft-plans.yaml schemas; functions planned automatically by parameter name |
| SL-053 | Gap report: repo-review plugins for data repos + sp-repo-review + OpenSSF Scorecard + per-function gaps | done 2 Nov: repo-review plugin (entry points) sharing logic with the built-in adapter; OpenSSF Scorecard still GitHub-only |
| SL-054 | Joined view: complex-and-untested, pure-but-untested | partly 2 Nov: pure-but-untested and module-without-tests done; complex-and-untested waits for coverage data |
| SL-055 | Run 2 on the sample with the delta; record the score | done 2 Nov: run 5 = 88/101 |
| SL-056 | Draft tests for untested pure functions: snapshot tests (syrupy) from small dev samples, Hypothesis ghostwriter skeletons with schema-to-strategy helper, Claude-drafted case tables; keep a drafted test only if mutation testing shows it catches bugs. Pynguin on trial | done 2 Nov: shiftleft draft-tests (runnable drafts when schemas match); the mutation gate and Claude drafting come with the skill (SL-071) |
| SL-058 | Dead code with entry points: read job entry points and notebook calls from databricks.yml so vulture stops flagging library functions | done 2 Nov: entry points from bundle, pyproject and .shiftleft-entrypoints; unused public functions grouped per module |
| SL-059 | Pull-request summary comment: blocking count and the top 5 to fix, posted by the CI templates (D9 level 1) | done 2 Nov: --summary; GitHub template posts it |
| SL-060a | Repo health page: static HTML per repo as a CI artifact; purity, untested pure functions, coverage, complexity hot spots, what is missing, findings by family, trend vs last run (D9 level 2) | done 2 Nov: --html health page with trend (--previous) |
| SL-061a | Metric view checks (SEM family): extract the YAML, validate against spec 1.1, parse expressions, the seven SEM rules | done 2 Nov: adapters/metricview.py; SEM 7/7 |
| SL-062a | dbt structure: dbt-bouncer and dbt-score on `dbt parse` output (offline) for TEST-07/08, CLEAN-27/28, SETUP-10 | done 2 Nov: dbt parse + dbt-bouncer (5 checks); TEST-07/08, CLEAN-27/28, SETUP-10 |
| SL-064 | Our own pattern rules for the 9 remaining build checks (SEC-06, SEC-07, TEST-04, TEST-06, CLEAN-08, CLEAN-14, CLEAN-23, CLEAN-26, DEP-05) | done 2 Nov: adapters/patterns.py over syntax trees (no Opengrep needed), settings in the binding; run 6 = 97/101, 0 false alarms; 217 tests |
| SL-057 | Test kit from examples/scd2 into the package: idempotency, uniqueness, nothing dropped, fan-out, cartesian; case tables for SCD2, dedupe, incremental, late data | done 2 Nov: shiftleft.testkit |

## Tier 6: real repo

| Id | Task | Status |
|---|---|---|
| SL-060 | Run on a real repo (data-platform-framework or Project5-DLTStreamingProject) | done: repo 1 ecomsimpledataplatformusingdatabricks (13 notebooks, 2 Nov, tests/runs/real-1-ecom.md); repo 2 Project5-DLTStreamingProject (DLT framework modules, 3 Nov, tests/runs/real-2-dlt.md) |
| SL-061 | Cut noise: fix or drop any rule with many false alarms | done: src/shiftleft/refine.py, 13 rules switched on in the binding (`refine:`) plus `refine_settings` (platform-only modules, small tables, formatting grouped per file), counted in run notes; 37 table-driven tests |
| SL-062 | Feed gaps back into the spec; run 3 | partly 2 Nov: the Sonar comparison (REUSE.md) gave SL-065–069 |
| SL-065 | PySpark rules Sonar has and we lack, as pattern rules: `lit(None)` with no cast (a NullType column breaks the write), window ordered with no explicit frame, join with no `how`, `dropDuplicates()` with no columns, chained `withColumn` that could be one `withColumns` | done 3 Nov: SL-CLEAN-29..32 and SL-COST-CODE-24 in patterns.py; 5 planted (P102–P106) and 3 traps (T17–T19) in src/shop/customer_report.py; run 8 = 102/106, 0/19; on the e-commerce repo only 3 report-level chain findings, all true |
| SL-065b | Window with orderBy and no partitionBy (all rows go through one task): found reading the e-commerce repo; Sonar has no rule for it | — |
| SL-066 | Type-flow bugs (wrong argument count, calling a non-callable, attribute that does not exist): trial pyright in basic mode, Databricks globals declared | dropped 3 Nov after trial: pyright 1.1.414 basic, 1.3 s and about 300 MB per repo; 0 real bugs on both repos; false alarms on `SparkSession.builder.getOrCreate()` (PySpark's own types), a Delta merge argument and a mixed-type list; 1 valid deprecated import. Retry on a repo with typed library code |
| SL-067 | Duplicate code: finish the SL-CPLX-05 trial (pylint R0801 or jscpd) | — |
| SL-068 | CI workflow security (unpinned actions, script injection in GitHub Actions): trial zizmor | — |
| SL-069 | Taint across functions (a widget or parameter reaching SQL through a helper): extend sql-identifiers-only to follow one call level | — |
| SL-063 | Portfolio view for leaders across repos (D9 level 3), after the first real repo | — |

## Tier 7: teach and release (runs alongside)

| Id | Task | Status |
|---|---|---|
| SL-070 | Keep /learn/shift-left/ in step with each tier (status, real scores) | ongoing |
| SL-071 | Claude skill: reads REVIEW.md, explains findings, drafts refactors of impure functions (never decides pass or fail) | — |
| SL-072 | Run and fix the templates (pre-commit, dev container, GitHub Actions, Azure DevOps) on the sample repo | — |
| SL-073 | Tag v0.1; README quick start | — |

## Tier 8: Azure binding

| Id | Task | Status |
|---|---|---|
| SL-080 | bindings/azure.yaml: Azure Data Factory pipeline rules, Synapse and Fabric notebooks, Azure DevOps SARIF tab | — |
| SL-081 | Split the catalog into its own repo if checks are stable | — |

## Lessons from running the samples (2 Nov)

- `pyspark.testing` in Spark 3.5 needs pandas and pyarrow (and numpy < 2 with older pandas). The sample repo and templates must list them.
- Set `PYSPARK_PYTHON` to the test's Python in the test fixture, or workers fail with a version mismatch.
- Empty-table EXPLAIN of a keyless join shows `CartesianProduct` (checked on Spark 3.5.1).

- `df.limit(0)` or an empty local list lets Spark fold an empty join away and hide a cartesian product; build empty inputs from an empty RDD (`testkit.schema_only`).
- Set `PYSPARK_PYTHON` unconditionally in the test fixture; this machine's shell sets it to Python 3.11.

## Open questions

- CostLens oss-core: publish as a package? Until then the cost adapter is optional (D2).
- Databricks UCX code linter: still maintained? Last PyPI release Oct 2025. Check in Tier 3.
- Gate list (D5 said: block only security, secrets and cartesian joins). The spec also starts these at block, because they rarely give false alarms: the four job-config checks (pre-deploy), DELETE/UPDATE with no WHERE, known-vulnerable libraries (high and above), a wrong `@pure` mark, and coverage on changed lines (D7). Lower any of them to warn in `catalog/checks/` if you prefer.
