"""The test-time guard: inside a test marked pure, table access fails; outside, nothing changes."""
import pytest

from scd2 import scd2
from shiftleft.pytest_plugin import ImpureCallError, assert_repeatable
from test_scd2 import BASE, B, H


def reads_a_table(spark):
    return spark.table("silver.orders")


def writes_a_table(df):
    df.write.mode("append").saveAsTable("silver.orders")


@pytest.mark.pure
def test_pure_function_passes_the_guard_and_is_repeatable(spark):
    hist, batch = spark.createDataFrame(BASE, H), spark.createDataFrame([], B)
    assert_repeatable(scd2, hist, batch)


@pytest.mark.pure
@pytest.mark.parametrize("fn", [reads_a_table, lambda s: writes_a_table(s.range(1))], ids=["read", "write"])
def test_guard_stops_table_access(spark, fn):
    with pytest.raises(ImpureCallError):
        fn(spark)


def test_unmarked_tests_are_not_guarded(spark):
    with pytest.raises(Exception) as e:             # a real call happens and fails for a normal reason
        reads_a_table(spark)
    assert not isinstance(e.value, ImpureCallError)
