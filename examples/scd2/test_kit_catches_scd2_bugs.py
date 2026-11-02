"""Planted SCD2 bugs: each must be caught by a kit property, or the kit isn't worth having."""
from datetime import date

import pytest
from pyspark.sql import functions as F

import testkit as kit
from scd2 import HISTORY_COLS
from test_scd2 import BASE, B, H

d = date.fromisoformat


def naive_append(history, batch):
    """Bug: every batch row becomes a new current version; nothing is closed, nothing is compared."""
    new = (batch.withColumnRenamed("updated_at", "valid_from")
           .withColumn("valid_to", F.lit(None).cast("date")).withColumn("is_current", F.lit(True)))
    return history.unionByName(new.select(*HISTORY_COLS))


CASES = [
    # name, function, batch, property that must fail
    ("append-only history is not idempotent", naive_append, [(3, "Meera", "Goa", d("2026-03-01"))], "idempotent"),
    ("append-only history gives two current rows", naive_append, [(1, "Asha", "Chennai", d("2026-03-01"))], "one_current"),
]


@pytest.mark.parametrize("name, fn, batch, prop", CASES, ids=[c[0] for c in CASES])
def test_kit_catches_bug(spark, name, fn, batch, prop):
    hist, b = spark.createDataFrame(BASE, H), spark.createDataFrame(batch, B)
    out = fn(hist, b)
    check = {
        "idempotent": lambda: kit.assert_idempotent(fn, hist, b),
        "one_current": lambda: kit.assert_unique(out, ["customer_id"], where="is_current"),
    }[prop]
    with pytest.raises(AssertionError):
        check()
