# Example: SCD type 2 tested offline

A pure SCD2 function (`scd2.py`), a small kit of reusable checks (`testkit.py`, the prototype of the bundle's
test kit, SL-TEST-09), and table-driven tests. Runs on local Spark: no cluster, no tables, under 30 seconds.

| Question | Where it's answered |
|---|---|
| Does SCD2 do the right thing? | `test_scd2.py::test_scd2_result`, 8 cases (new key, no change, change, two changes in one batch, duplicate row, late row, replay, change back) |
| Is it idempotent? | `kit.assert_idempotent`: apply the batch twice, the second run changes nothing |
| Duplicates? | `kit.assert_unique`: one current row per key, no duplicate versions |
| Records dropped? | `kit.assert_nothing_dropped`: every input key is in the output or in an explicit rejects set |
| Cartesian join? | `kit.assert_no_cartesian`: reads the plan on **empty** inputs |
| Does the kit actually catch bugs? | `test_testkit.py` and `test_kit_catches_scd2_bugs.py`: planted bugs that must fail |

Run:

```
pip install -r requirements-test.txt     # needs Java 17
pytest -q
```

Recorded 2 Nov 2026 on Spark 3.5.1, Python 3.9, macOS: 27 passed in about 26 seconds.

Lessons from making it run:
- An empty input made with `df.limit(0)` or an empty local list lets Spark fold the whole join away, which hides a
  cartesian product. `testkit.schema_only()` builds empty inputs from an empty RDD instead.
- Set `PYSPARK_PYTHON` to the test's own Python, always (not only when unset); a value from the shell made workers
  start a different Python version.
- `pyspark.testing` in Spark 3.5 imports pandas and pyarrow.
