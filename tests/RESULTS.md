# Runs against the sample project

The sample (`examples/sample-project`, a small clothing shop) has **101 planted problems** in 12 of the 13 families
(style is left out on purpose) and **16 traps**: code that looks wrong but isn't. The key is `tests/sample-key.yaml`.
Score any run with `uv run scripts/score.py findings.json`.

| Run | Date | What ran | Caught (strict) | Caught (family) | False alarms | Unplanned |
|---|---|---|---|---|---|---|
| 0 | 2 Nov 2026 | Ruff 0.17.3, starter profile, default settings | 17/101 | 19/101 | 0/16 | 33 |
| 0b | 2 Nov 2026 | Ruff 0.17.3, starter profile, `templates/ruff.toml` | 17/101 | 19/101 | 0/16 | 8 |
| 1 | 2 Nov 2026 | `shiftleft scan --stage all`: Ruff, SQLFluff, gitleaks (+ our rules), osv-scanner, vulture, complexipy, nbstripout, repo checks | 34/101 | 39/101 | 0/16 | 56 |

Details: `runs/run-0-ruff-only.md`, `runs/run-0b-ruff-tuned.md`, `runs/run-1-runner.md`. Run 1 took under 8 seconds on a laptop.

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
