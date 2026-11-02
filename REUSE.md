# REUSE.md — what we take off the shelf, and what we build

Existence check done 2 Nov 2026, before any design. Rule: reuse what the industry already uses, build only the delta, and record the reason either way.

## Checked and verdict

| Tool | What it does | Licence / health (checked 2 Nov 2026) | Verdict | Reason |
|---|---|---|---|---|
| SonarQube Community | General code quality server | Needs server + database; PR analysis is paid | **Drop** | Heavy to run, knows nothing about Spark cost. We emit SARIF, so a client who already runs Sonar can import our findings. |
| MegaLinter | Docker image bundling ~100 linters | Image is several GB | **Drop** | Too heavy. We borrow its idea (one config, many tools). |
| pre-commit (framework) | Runs hooks locally and in CI from one file | MIT, standard | **Pursue** | Same checks on the laptop and in CI with one config. |
| Ruff | Python lint + format, includes Bandit's security rules (`S`) | MIT, very active, very fast | **Pursue** | Replaces flake8, isort, black and most of Bandit in one tool. |
| Bandit | Python security lint | Apache-2.0, 1.9.4 Feb 2026 | **Drop (optional)** | Ruff `S` rules cover most of it. |
| Opengrep | Pattern rules in YAML (Semgrep-compatible fork) | LGPL-2.1 engine | **Pursue** | Engine for our own PySpark cost and security rules. |
| Semgrep registry rules | Ready-made rules | Semgrep Rules License: internal, non-competing use only | **Drop for shipping** | Can't ship them in an open bundle. Write our own rules. |
| SQLFluff | SQL lint, has a `databricks` dialect | MIT, 4.5.0 on 30 Oct 2026 | **Pursue** | SQL style and custom cost rules. Gap: it can't read `%sql` cells or SQL strings inside Python. |
| pyspark-antipattern | PySpark performance lint, pre-commit hook | MIT, 0.4.1 Apr 2026, 15 releases | **Borrow (trial)** | Closest fit. Young, one maintainer. Adopt behind an adapter; drop if the trial scores badly. |
| SparkDoctor | Spark performance / correctness lint | Apache-2.0, 0.1.8 Mar 2026 | **Borrow (trial)** | Trial against the sample repo alongside pyspark-antipattern. |
| cylint | PySpark lint, zero dependencies | Apache-2.0, 0.1.5 Mar 2026 | **Borrow ideas** | Small rule set; take ideas, not the tool. |
| spark-perf-lint | 93 Spark anti-patterns, optional LLM audit | Custom licence, 1 release | **Drop** | Licence unclear. Its pattern list is worth reading. |
| databricks-labs-pylint | dbutils / Spark testability rules | Last release 0.5.0, Oct 2024 | **Borrow (optional)** | Useful "spark outside function" rule; needs pylint (slow). |
| Databricks UCX code linter | Unity Catalog compatibility of code | Databricks Labs | **Check** | Possible Databricks-binding adapter; confirm status in P3. |
| gitleaks | Secrets in code and git history | MIT, single binary | **Pursue** | Standard, fast. |
| detect-secrets | Secrets | Last release May 2024 | **Drop** | Stale. |
| pip-audit | Known vulnerabilities in Python dependencies | PyPA, 2.10.1 Jun 2026 | **Pursue** | Python first. Move to osv-scanner when more languages arrive. |
| Checkov | Infrastructure-as-code misconfiguration | Apache-2.0, 3.4.0 Oct 2026 | **Pursue (Terraform only)** | Doesn't understand Databricks bundle YAML, so we build those rules. |
| `databricks bundle validate` | Validates bundle config | Databricks CLI | **Pursue (binding)** | Free schema check. |
| pytest + `pyspark.testing.assertDataFrameEqual` | Unit tests on small DataFrames | Built into Spark 3.5 | **Pursue** | No extra library needed. |
| chispa | DataFrame equality | MIT | **Drop** | Spark 3.5 has this built in. |
| coverage.py | Test coverage | Apache-2.0, 7.17.0 Oct 2026 | **Pursue** | Line + branch coverage. |
| diff-cover | Coverage and lint on changed lines only | Apache-2.0, 11.0.0 Oct 2026 | **Pursue** | Gate new code ("clean as you code") without Sonar. |
| mutmut | Mutation testing: changes code, checks tests fail | BSD-3, 3.8.1 Oct 2026 | **Pursue (pure functions, nightly)** | Coverage shows a line ran, not that a test would catch a bug. Run on pure functions only, so it stays fast. |
| Hypothesis | Property-based tests | MPL-2.0, very active | **Pursue** | Best fit for pure functions. |
| deal | Contracts, `@pure` marker, side-effect linter, generates tests for pure functions | 4.24.6 Nov 2025 | **Borrow** | Generic side-effect detection (print, open, global, random). Knows nothing about Spark reads/writes or `dbutils`, so we build the Spark-aware part. |
| radon / xenon | Cyclomatic complexity, maintainability index / CI gate | MIT; radon last release 2023 | **Drop** | Stale. Ruff `C901` gives the same McCabe number. |
| Ruff `C901` (McCabe) | Cyclomatic complexity per function | MIT | **Pursue** | Already in Ruff. |
| complexipy | Cognitive complexity per function (Rust, fast) | MIT, 8.3.0 Oct 2026 | **Pursue** | Cognitive complexity matches "hard to read" better than cyclomatic. |
| lizard | Complexity for many languages | MIT, 1.24.3 Oct 2026 | **Borrow (later)** | When Scala/Java/other languages arrive. |
| wily | Complexity trend over git history | Last release 2023 | **Drop** | Stale. We store per-run scores instead. |
| import-linter | Architecture rules: "module A may not import B" | BSD-2, 2.15 Sep 2026 | **Pursue** | Enforces "pure core must not import IO/dbutils" across modules. |
| vulture | Dead code | MIT, 2.16 Mar 2026 | **Pursue (warn)** | Cheap. |
| repo-review | Framework for "is this repo set up right?" checks as plugins | BSD-3, 1.3.0 Oct 2026 | **Pursue** | Engine for the missing-setup report. We write the data-engineering plugins. |
| sp-repo-review | Scientific Python's checks on repo-review | BSD-3 | **Borrow** | Its pyproject / pre-commit / Ruff checks reused as-is. |
| OpenSSF Scorecard | Scores repo security practices (pinned deps, SAST, branch protection, CI tests…) | Apache-2.0, active (Oct 2026) | **Pursue** | Covers the security-practice part of "what is missing". |
| nbQA | Run linters on `.ipynb` | MIT | **Pursue** | Databricks source-format `.py` notebooks need nothing extra. |
| SARIF + GitHub code scanning / Azure DevOps SARIF tab | Show findings on the PR | Open standard | **Pursue** | Gives us Sonar's dashboard for free, with no server. |
| DefectDojo | Findings aggregation server | Heavy | **Drop** | Server again. |

## Parsers: every language already has a syntax tree (added after the user's point, 2 Nov)

| Layer | Parser (syntax tree) | Licence / health | Verdict | Who else builds on it |
|---|---|---|---|---|
| SQL | **sqlglot**, with a `databricks` dialect, lineage and optimiser | MIT, 30.27.0 on 30 Oct 2026 | **Pursue** | Databricks UCX, Databricks Lakebridge, CostLens `sql_lint.py` |
| Python | stdlib `ast` | built in | **Pursue** | CostLens `code_structure.py`, cylint, SparkDoctor |
| Python (rewrite) | **LibCST**: keeps formatting, so it can rewrite code safely | MIT-style, 1.9.0 Jul 2026 | **Pursue (refactor hints → auto-fix later)** | Instagram codemods |
| Python (types/inference) | astroid (pylint's tree, knows what a name refers to) | LGPL-2.1, 4.3.4 Oct 2026 | **Borrow** | Databricks UCX |
| PySpark | **Spark's own plan (Catalyst)** from `EXPLAIN` on local Spark with empty tables: the real "AST" of DataFrame code | Apache-2.0 | **Pursue** | CostLens `plan_lint.py` |
| Databricks config | bundle JSON schema + `databricks bundle validate` | Databricks CLI | **Pursue** | CostLens `orchestration/dabs.py` |

## Our own code: CostLens (CostSherlock) already built most of the cost layer

`~/CostLens/costlens-core` (marked "oss-core, Apache 2.0" in the code, repo private today) already ships:

- `sql_lint.py`: about 35 sqlglot rules (select star, cross join, non-sargable predicate, function on partition column, MERGE without partition predicate, repeated scan…)
- `code_structure.py`: about 11 Python AST rules (spark.sql in a loop, collect in a loop, toPandas without limit, broadcast in a loop, UDF proliferation…)
- `inputs/python_source.py`, `inputs/notebook.py`: pulls SQL out of `spark.sql(...)` strings, f-strings and notebook cells
- `plan_lint.py`: offline EXPLAIN plan rules (broadcast missed, too many shuffles, pushdown gap)
- `orchestration/dabs.py`: Databricks bundle rules (cluster routing, schedule frequency, continuous vs triggered, autoscale)
- `azure_data_factory/`: ADF rules, a start on the Azure binding
- `.pre-commit-hooks.yaml` with `costlens hook`

**Verdict: Pursue as the cost adapter.** The bundle calls CostLens behind a port and maps its rule ids to our check ids. We don't copy its rules. Until costlens-core is published as a package, the cost adapter is optional (D2).

## The delta (what nobody ships, so we build it)

1. **The catalog** (the spec): check ids that name no product, plus the reason, stage, gate level, cost impact and link to DAC obligations.
2. **Cost rules**: done in CostLens. The delta is only gaps found by the sample repo (cartesian product and Python UDF evaluation in the plan, from CostIntelligence1).
3. **Offline plan check**: done in CostLens (`plan_lint.py`). The delta is a harness that builds empty DataFrames from real schemas so any job can be EXPLAINed without data.
4. **Job and cluster config cost rules**: done in CostLens (DABs, ADF).
5. **SQL extraction**: done in CostLens.
6. **One runner**: adapters per tool, findings normalised to SARIF with our check ids, gate by level, a baseline so old code isn't blocked.
7. **Spark-aware purity report**: for every function, pure or impure and why (reads a table, writes, uses `dbutils`, global `spark`, `datetime.now`, env vars, random). Shows counts, a refactor hint for each impure function that could be pure ("take the DataFrame in, return a DataFrame, move the read to the caller"), and joins with coverage and complexity to list "pure but untested" and "complex and untested".
8. **Gap report ("what is missing")**: repo-review plugins for data repos (no tests folder, no pre-commit, no lockfile, no CI, no coverage threshold, no SQL lint, no bundle validation, no contract files) plus Scorecard plus the per-function gaps above, combined into one REVIEW.md.
9. **Planted-problem sample repo + answer key**, to measure catch rate and false alarms (same method as data-project-review).

## Added 2 Nov 2026 (Tier 1b): notebooks, dbt, materialized views, metric views, security, test drafting

| Tool | What it does | Licence / health | Verdict | Reason |
|---|---|---|---|---|
| osv-scanner | Known vulnerabilities from lockfiles, OSV database | Apache-2.0 | **Pursue (main)** | Same database OpenSSF Scorecard uses; many ecosystems. pip-audit stays as the fallback. |
| OpenSSF Scorecard | Repo security practices | Apache-2.0 | **Pursue (report only)** | Scores practices; does not read code, can't block a single change, GitHub-first (no Azure DevOps). Not sufficient alone. |
| OpenSSF Allstar | Enforces repo settings on GitHub | Apache-2.0 | **Optional** | Keeps branch protection on instead of only scoring it. |
| nbQA | Run linters on notebooks | MIT, last release Nov 2024 | **Drop** | Ruff lints .ipynb natively. |
| nbstripout | Strip notebook outputs on commit | MIT, 0.9.1 Feb 2026 | **Pursue** | Outputs leak data samples (SL-SEC-09). |
| dbt-bouncer | Rules over manifest.json from `dbt parse` (offline) | MIT, 4.5.1 Oct 2026 | **Pursue** | Model tests, references, conventions. Check names confirmed in Tier 3. |
| dbt-score | Scores dbt model metadata (offline) | MIT, 0.19.0 Oct 2026 | **Pursue** | Descriptions and metadata. |
| sqlfluff-templater-dbt | Lint dbt models with Jinja rendered | MIT, 4.5.0 Oct 2026 | **Pursue** | Calls `dbt compile`, which may need a connection; SQLFluff's jinja templater is the offline fallback. |
| dbt-project-evaluator | dbt Labs DAG rules | Apache-2.0 | **Trial** | 1.x builds models in the warehouse (not offline). A 2.x running as native `dbt check` is reported for dbt 2; not confirmed. |
| EXPLAIN CREATE MATERIALIZED VIEW | Databricks says if an MV can refresh incrementally, and why not | Databricks SQL, Runtime 17.3+ | **Pursue (pre-deploy)** | Not offline (a few seconds on a dev warehouse), but the only authority. Docs pages disagree on non-deterministic functions. |
| Metric view validator | — | — | **Build** | No outside linter exists; Databricks validates YAML spec 1.1 only inside its own tools. |
| Palantir PySpark style guide | Written guide | — | **Borrow** | Source for SL-CLEAN-14, -25, -26. |
| syrupy | Snapshot (characterisation) tests for pytest | MIT, 6.1.1 Sep 2026 | **Pursue** | Fastest way to pin an untested pure function's current behaviour before refactoring. |
| Hypothesis ghostwriter | Writes property-test skeletons from function signatures | MPL-2.0 | **Pursue** | Part of Hypothesis; DataFrame inputs need our schema-to-strategy helper. |
| Pynguin | Automated unit-test generation for Python | MIT, 0.48.0 Oct 2026 | **Trial** | Research tool; expect weak results on DataFrame code. |

Ruff 0.17.3 has 973 rules (832 stable) from 60 linters. Starter profile 404 rules, strict 600 (bindings/databricks.yaml).

## Trial of the young PySpark linters (2 Nov 2026, on the sample; SL-041)

| Tool | Findings on the sample | Verdict | Reason |
|---|---|---|---|
| SparkDoctor 0.1.8 | 26 | **Adopt (mapped rules only)** | JSON output, Apache-2.0. Adds count-to-test-emptiness, withColumn in a loop, Python UDF, long chains, collect in a loop. Its magic-literal rule (11 findings) is not mapped. |
| pyspark-antipattern 0.4.1 | 37 | **Adopt two rules** | S011 (join with no condition) and F019 (inferSchema) add coverage. Many other rules are opinions (avoid spark.sql, avoid collect, avoid drop) and two hit traps. Text output only, written to stderr. |
| cylint 0.1.5 | 10 | **Drop** | Every finding duplicates SparkDoctor or pyspark-antipattern. |

## Tier 5 reuse decisions (2 Nov 2026)

| Need | Took | Built | Why |
|---|---|---|---|
| dbt structure | `dbt parse` (offline) + dbt-bouncer 4.5.1, five checks | a 60-line adapter | dbt-score and dbt-project-evaluator were not needed; bouncer covers all five checks |
| Metric views | PyYAML, sqlglot | the seven SEM rules | no outside linter exists |
| Plan check | Spark's own planner | the empty-table harness | nothing reads a plan on empty, schema-only inputs |
| Missing setup | repo-review (as a plugin host) | the data-repo checks | teams already on repo-review see them in one report |
| Test guard and kit | pytest, pyspark.testing | the `pure` marker, five property checks | nothing blocks table I/O inside unit tests |
| Test drafts | pytest parametrize | the draft generator | Hypothesis ghostwriter and Pynguin don't build DataFrames from schemas |
