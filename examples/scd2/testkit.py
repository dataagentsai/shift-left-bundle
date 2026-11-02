"""Reusable checks for data transforms (prototype of the bundle's test kit, SL-TEST-09).

Each one answers a question people usually only find out in production:
  assert_idempotent      run it twice: does the second run change anything?
  assert_unique          are the keys unique where they must be (e.g. one current row per customer)?
  assert_nothing_dropped does every input key end up in the output or in an explicit rejects set?
  assert_no_fanout       did a join multiply rows?
  assert_no_cartesian    does the plan contain a cartesian product? (empty inputs are enough)
"""
from pyspark.sql import DataFrame
from pyspark.testing import assertDataFrameEqual


def assert_idempotent(fn, state: DataFrame, batch: DataFrame) -> None:
    once = fn(state, batch)
    twice = fn(once, batch)
    assertDataFrameEqual(twice, once)


def assert_unique(df: DataFrame, keys: list, where: str = None) -> None:
    rows = df.filter(where) if where else df
    dups = rows.groupBy(*keys).count().filter("count > 1").collect()
    assert not dups, f"duplicate keys {keys}{' where ' + where if where else ''}: {dups[:5]}"


def assert_nothing_dropped(inputs: DataFrame, output: DataFrame, key: str, rejects: DataFrame = None) -> None:
    landed = output.select(key)
    if rejects is not None:
        landed = landed.unionByName(rejects.select(key))
    lost = inputs.select(key).distinct().join(landed.distinct(), key, "left_anti").collect()
    assert not lost, f"{len(lost)} input keys are in neither the output nor the rejects: {lost[:5]}"


def assert_no_fanout(left: DataFrame, joined: DataFrame) -> None:
    n_left, n_out = left.count(), joined.count()
    assert n_out <= n_left, f"join multiplied rows: {n_left} in, {n_out} out"


def assert_no_cartesian(df: DataFrame) -> None:
    plan = df._jdf.queryExecution().executedPlan().toString()
    for bad in ("CartesianProduct", "BroadcastNestedLoopJoin"):
        assert bad not in plan, f"plan contains {bad}"


def schema_only(df: DataFrame) -> DataFrame:
    """An empty DataFrame with the same columns: enough to read a plan without data.

    Built from an empty RDD on purpose. df.limit(0) or an empty local list lets the optimiser see the input
    is empty and fold the whole join away, which hides a cartesian product from the plan.
    """
    spark = df.sparkSession
    return spark.createDataFrame(spark.sparkContext.emptyRDD(), df.schema)
