"""SCD type 2 as a pure function: history + batch in, new history out. No reads, no writes, no clock.

The impure shell (read the target, call this, MERGE or overwrite the result) stays outside, so every
rule below can be unit tested on tiny DataFrames in seconds.

Rules:
  - a key not seen before gets a current version
  - a row whose attributes equal the version before it is not a change
  - a change closes the previous version (valid_to = the new version's valid_from)
  - several changes for one key in one batch become several versions, in time order
  - the same row twice in a batch, or a batch replayed, changes nothing (idempotent)
  - a row older than the key's current version is late: it is not applied, and late_rows() returns it
"""
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

HISTORY_COLS = ["customer_id", "name", "city", "valid_from", "valid_to", "is_current"]
ATTRS = ["name", "city"]
KEY = "customer_id"


def _with_current_from(history: DataFrame, batch: DataFrame) -> DataFrame:
    cur_from = history.filter("is_current").select(KEY, F.col("valid_from").alias("_cur_from"))
    return batch.withColumnRenamed("updated_at", "valid_from").join(cur_from, KEY, "left")


def late_rows(history: DataFrame, batch: DataFrame) -> DataFrame:
    """Batch rows older than the key's current version. Not applied; returned so nothing drops silently."""
    return (_with_current_from(history, batch)
            .filter(F.col("valid_from") < F.col("_cur_from"))
            .drop("_cur_from")
            .withColumnRenamed("valid_from", "updated_at"))


def scd2(history: DataFrame, batch: DataFrame) -> DataFrame:
    """Return the full new history after applying `batch` (customer_id, name, city, updated_at)."""
    incoming = (_with_current_from(history, batch.dropDuplicates([KEY, "updated_at"]))
                .filter(F.col("_cur_from").isNull() | (F.col("valid_from") > F.col("_cur_from")))
                .drop("_cur_from"))
    current = history.filter("is_current").select(KEY, *ATTRS, "valid_from")
    by_time = Window.partitionBy(KEY).orderBy("valid_from")
    versions = (current.withColumn("_existing", F.lit(True))
                .unionByName(incoming.withColumn("_existing", F.lit(False)))
                .withColumn("_h", F.xxhash64(*ATTRS))
                .withColumn("_prev_h", F.lag("_h").over(by_time))
                .filter(F.col("_existing") | F.col("_prev_h").isNull() | (F.col("_h") != F.col("_prev_h")))
                .withColumn("valid_to", F.lead("valid_from").over(by_time))
                .withColumn("is_current", F.col("valid_to").isNull())
                .select(*HISTORY_COLS))
    return history.filter(~F.col("is_current")).select(*HISTORY_COLS).unionByName(versions)
