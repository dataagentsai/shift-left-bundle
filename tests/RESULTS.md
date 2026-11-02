# Runs against the sample project

The sample (`examples/sample-project`, a small clothing shop) has **101 planted problems** in 12 of the 13 families
(style is left out on purpose) and **16 traps**: code that looks wrong but isn't. The key is `tests/sample-key.yaml`.
Score any run with `uv run scripts/score.py findings.json`.

| Run | Date | What ran | Caught (strict) | Caught (family) | False alarms | Unplanned |
|---|---|---|---|---|---|---|
| 0 | 2 Nov 2026 | Ruff 0.17.3, starter profile, default settings | 17/101 | 19/101 | 0/16 | 33 |
| 0b | 2 Nov 2026 | Ruff 0.17.3, starter profile, `templates/ruff.toml` | 17/101 | 19/101 | 0/16 | 8 |

Details: `runs/run-0-ruff-only.md`, `runs/run-0b-ruff-tuned.md`.

## What run 0 taught us

- **Ruff alone covers clean code and Python security, and nothing data-specific.** It caught 11 of 20 clean-code and
  6 of 10 security problems; 0 of the cost, config, plan, dependency, purity, test, metric and setup problems.
  That gap is what Tiers 3–5 fill (SQL rules, cost adapter, bundle config rules, purity, test kit, metric views).
- **Default settings are noisy on PySpark.** 25 of 53 findings were noise: line length at 88 (13), notebook globals
  `spark`, `dbutils`, `display` reported as undefined (6), `functions as F` flagged by N812 (3), `assert` in tests (2),
  a local import in a test (1). `templates/ruff.toml` removes them without losing a catch.
- **The 8 unplanned findings left are real** (an unused import, unsorted imports, prints, naive datetimes on lines the
  key doesn't list). Unplanned findings are reported, not counted as false alarms.
