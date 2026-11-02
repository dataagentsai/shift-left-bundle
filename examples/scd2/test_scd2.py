"""Table-driven tests for scd2(): each case is history + batch -> expected history.
Every case is also checked against the kit's properties: idempotent, one current row per key,
no duplicate versions, nothing dropped silently, no cartesian product in the plan."""
from datetime import date

import pytest
from pyspark.testing import assertDataFrameEqual

import testkit as kit
from scd2 import late_rows, scd2

H = "customer_id INT, name STRING, city STRING, valid_from DATE, valid_to DATE, is_current BOOLEAN"
B = "customer_id INT, name STRING, city STRING, updated_at DATE"
d = date.fromisoformat

BASE = [(1, "Asha", "Pune", d("2026-01-01"), None, True),
        (2, "Ravi", "Delhi", d("2026-01-01"), d("2026-02-01"), False),
        (2, "Ravi", "Mumbai", d("2026-02-01"), None, True)]
CUST2 = BASE[1:]

CASES = [
    # name, batch rows, expected history rows
    ("new customer gets a current version",
     [(3, "Meera", "Goa", d("2026-03-01"))],
     BASE + [(3, "Meera", "Goa", d("2026-03-01"), None, True)]),
    ("unchanged row is not a change",
     [(1, "Asha", "Pune", d("2026-03-01"))],
     BASE),
    ("changed city closes the old version",
     [(1, "Asha", "Chennai", d("2026-03-01"))],
     [(1, "Asha", "Pune", d("2026-01-01"), d("2026-03-01"), False),
      (1, "Asha", "Chennai", d("2026-03-01"), None, True)] + CUST2),
    ("two changes in one batch become two versions",
     [(1, "Asha", "Chennai", d("2026-03-01")), (1, "Asha", "Kochi", d("2026-04-01"))],
     [(1, "Asha", "Pune", d("2026-01-01"), d("2026-03-01"), False),
      (1, "Asha", "Chennai", d("2026-03-01"), d("2026-04-01"), False),
      (1, "Asha", "Kochi", d("2026-04-01"), None, True)] + CUST2),
    ("same row twice in a batch counts once",
     [(3, "Meera", "Goa", d("2026-03-01")), (3, "Meera", "Goa", d("2026-03-01"))],
     BASE + [(3, "Meera", "Goa", d("2026-03-01"), None, True)]),
    ("late row older than the current version is not applied",
     [(2, "Ravi", "Agra", d("2026-01-15"))],
     BASE),
    ("replay of an already applied version changes nothing",
     [(2, "Ravi", "Mumbai", d("2026-02-01"))],
     BASE),
    ("change back to an earlier value is a new version",
     [(2, "Ravi", "Delhi", d("2026-03-01"))],
     [BASE[0], BASE[1], (2, "Ravi", "Mumbai", d("2026-02-01"), d("2026-03-01"), False),
      (2, "Ravi", "Delhi", d("2026-03-01"), None, True)]),
]
IDS = [c[0] for c in CASES]


@pytest.mark.parametrize("name, batch, expected", CASES, ids=IDS)
def test_scd2_result(spark, name, batch, expected):
    got = scd2(spark.createDataFrame(BASE, H), spark.createDataFrame(batch, B))
    assertDataFrameEqual(got, spark.createDataFrame(expected, H))


@pytest.mark.parametrize("name, batch, expected", CASES, ids=IDS)
def test_scd2_properties(spark, name, batch, expected):
    hist, b = spark.createDataFrame(BASE, H), spark.createDataFrame(batch, B)
    out = scd2(hist, b)
    kit.assert_idempotent(scd2, hist, b)                              # running the batch twice changes nothing
    kit.assert_unique(out, ["customer_id"], where="is_current")       # one current version per customer
    kit.assert_unique(out, ["customer_id", "valid_from"])             # no duplicate versions
    kit.assert_nothing_dropped(b, out, "customer_id", rejects=late_rows(hist, b))  # every key accounted for
    kit.assert_no_cartesian(scd2(kit.schema_only(hist), kit.schema_only(b)))       # plan check on empty inputs


def test_late_row_is_reported_not_lost(spark):
    hist, b = spark.createDataFrame(BASE, H), spark.createDataFrame([(2, "Ravi", "Agra", d("2026-01-15"))], B)
    assert [r.customer_id for r in late_rows(hist, b).collect()] == [2]
