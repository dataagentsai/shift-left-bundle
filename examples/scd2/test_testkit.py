"""The kit must catch what it claims to catch: each case is a transform and the kit check it must fail or pass."""
import pytest
from pyspark.sql import functions as F

import testkit as kit

ORDERS = ("order_id INT, store_id INT, amount DOUBLE", [(1, 10, 5.0), (2, 10, 7.0), (3, 20, 9.0)])
STORES = ("store_id INT, region STRING", [(10, "North"), (20, "South")])
STORES_MISSING = ("store_id INT, region STRING", [(10, "North")])          # store 20 not in the lookup
STORES_DUP = ("store_id INT, region STRING", [(10, "North"), (10, "N. region"), (20, "South")])


def join_ok(o, s):
    return o.join(s, "store_id", "left")


def join_inner(o, s):
    return o.join(s, "store_id")                           # inner join: orders with no store vanish


def join_without_key(o, s):
    return o.crossJoin(s)                                  # the bug: no join condition


def join_wrong_column(o, s):
    return o.join(s, F.lit(True))                          # condition that is always true


CASES = [
    # name, join function, stores data, which kit check, should it fail?
    ("correct join passes the cartesian check", join_ok, STORES, "cartesian", False),
    ("missing join key is caught on empty inputs", join_without_key, STORES, "cartesian", True),
    ("always-true condition is caught on empty inputs", join_wrong_column, STORES, "cartesian", True),
    ("correct join does not multiply rows", join_ok, STORES, "fanout", False),
    ("duplicate key in the lookup multiplies rows", join_ok, STORES_DUP, "fanout", True),
    ("duplicate key in the lookup is caught as a duplicate", join_ok, STORES_DUP, "unique", True),
    ("left join keeps every order", join_ok, STORES_MISSING, "dropped", False),
    ("inner join silently drops orders with no store", join_inner, STORES_MISSING, "dropped", True),
]


@pytest.mark.parametrize("name, fn, stores, check, should_fail", CASES, ids=[c[0] for c in CASES])
def test_kit_catches(spark, name, fn, stores, check, should_fail):
    o = spark.createDataFrame(ORDERS[1], ORDERS[0])
    s = spark.createDataFrame(stores[1], stores[0])
    run = {
        "cartesian": lambda: kit.assert_no_cartesian(fn(kit.schema_only(o), kit.schema_only(s))),
        "fanout": lambda: kit.assert_no_fanout(o, fn(o, s)),
        "unique": lambda: kit.assert_unique(s, ["store_id"]),
        "dropped": lambda: kit.assert_nothing_dropped(o, fn(o, s), "order_id"),
    }[check]
    if should_fail:
        with pytest.raises(AssertionError):
            run()
    else:
        run()
