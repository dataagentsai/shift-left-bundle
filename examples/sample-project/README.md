# Sample project: Harbour Threads (a small clothing shop)

A deliberately flawed data project used to measure the bundle. It has **planted problems** across all 13 check
families and **traps**: code that looks wrong but isn't, which a good check must not flag.

The answer key is not in this folder. It lives in `tests/sample-key.yaml` at the repository root, so a reviewer
or a tool run on this folder can't read it. Score a run with:

```
uv run scripts/score.py <findings.json>      # findings: [{"check": "SL-...", "file": "...", "line": 12}, ...]
```

Do not fix the problems here. Fixes belong in a copy.

Layout: `src/shop` (PySpark modules), `notebooks` (Databricks source format and one .ipynb), `sql` (queries, a
materialized view, a metric view), `dbt_shop` (a small dbt project), `databricks.yml` and `resources/` (bundle
config), `tests` (the project's own, weak, tests).
