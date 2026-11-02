# TODO: Shift-Left Bundle

The working list, by tier. The plan and its reasons live in `PLAN.html`; the reuse ledger in `REUSE.md`.
Every progress report opens with the "Start here" table. A tier starts when the one before it is done,
except Tier 7 (teaching), which runs alongside.

## Start here

| Tier | What | Status |
|---|---|---|
| 0 | Ground: reuse check, decisions, plan, public repo, site guide | done 2 Nov |
| 1 | Spec v0.1: the checks, written once, no product names | done 2 Nov: 90 checks, linter clean, 41 tests |
| 2 | Proof material: sample repo with planted problems and a hidden answer key | next |
| 3 | Wire the off-the-shelf tools through one runner; run 1 on the sample | later |
| 4 | Cost adapter: existing cost rules behind the cost port; trial the young PySpark linters | later |
| 5 | The delta: purity report, empty-table plan harness, gap report | later |
| 6 | Real repo, cut the noise, run 2 | later |
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

## Tier 2: proof material

| Id | Task | Status |
|---|---|---|
| SL-020 | Sample repo (a small shop pipeline: bronze → silver → gold, notebooks, SQL, bundle YAML) | — |
| SL-021 | Planted problems: one or more per check family, including impure-could-be-pure and untested pure functions | — |
| SL-022 | False-positive traps: code that looks wrong but isn't | — |
| SL-023 | Hidden answer key + scoring script (caught, missed, false alarms per family) | — |

## Tier 3: off-the-shelf tools through one runner

| Id | Task | Status |
|---|---|---|
| SL-030 | Runner skeleton: ports (Scanner, Reporter, Gate, Baseline), adapter registry chosen by the binding YAML | — |
| SL-031 | Adapters: Ruff (lint, clean code, security, C901), SQLFluff, sqlglot, Opengrep, gitleaks, pip-audit, Checkov | — |
| SL-032 | Adapters: pytest + coverage.py + diff-cover, complexipy, import-linter, vulture | — |
| SL-033 | Findings normalised to SARIF with our check ids; REVIEW.md in fix-first order | — |
| SL-034 | Gate + baseline: block list, warn the rest, only new findings fail | — |
| SL-035 | `.pre-commit-hooks.yaml` and the commit / PR / nightly / pre-deploy split | — |
| SL-036 | Run 1 on the sample; record the score | — |

## Tier 4: cost adapter

| Id | Task | Status |
|---|---|---|
| SL-040 | Existing cost rules (CostLens oss-core: SQL, Python, plan, bundle config) behind the cost port; map their rule ids to our check ids; optional until published as a package | — |
| SL-041 | Trial pyspark-antipattern and SparkDoctor on the sample; keep only rules the existing set lacks | — |
| SL-042 | Add missing plan rules: CartesianProduct, Python UDF evaluation (from CostIntelligence1) | — |

## Tier 5: the delta

| Id | Task | Status |
|---|---|---|
| SL-050 | Purity report: pure / impure / unknown per function, call chain, counts, refactor hint per impure-could-be-pure | — |
| SL-051 | Test-time purity fixture: Spark reads, writes and catalog calls fail inside pure-function tests; run-twice check | — |
| SL-052 | Empty-table plan harness: build empty DataFrames from schemas (contracts or DDL) and EXPLAIN each job's transforms | — |
| SL-053 | Gap report: repo-review plugins for data repos + sp-repo-review + OpenSSF Scorecard + per-function gaps | — |
| SL-054 | Joined view: complex-and-untested, pure-but-untested | — |
| SL-055 | Run 2 on the sample with the delta; record the score | — |

## Tier 6: real repo

| Id | Task | Status |
|---|---|---|
| SL-060 | Run on a real repo (data-platform-framework or Project5-DLTStreamingProject) | — |
| SL-061 | Cut noise: fix or drop any rule with many false alarms | — |
| SL-062 | Feed gaps back into the spec; run 3 | — |

## Tier 7: teach and release (runs alongside)

| Id | Task | Status |
|---|---|---|
| SL-070 | Keep /learn/shift-left/ in step with each tier (status, real scores) | ongoing |
| SL-071 | Claude skill: reads REVIEW.md, explains findings, drafts refactors of impure functions (never decides pass or fail) | — |
| SL-072 | CI templates: GitHub Actions reusable workflow, Azure DevOps template | — |
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

## Open questions

- CostLens oss-core: publish as a package? Until then the cost adapter is optional (D2).
- Databricks UCX code linter: still maintained? Last PyPI release Oct 2025. Check in Tier 3.
- Gate list (D5 said: block only security, secrets and cartesian joins). The spec also starts these at block, because they rarely give false alarms: the four job-config checks (pre-deploy), DELETE/UPDATE with no WHERE, known-vulnerable libraries (high and above), a wrong `@pure` mark, and coverage on changed lines (D7). Lower any of them to warn in `catalog/checks/` if you prefer.
