"""Bronze orders to silver orders."""
import logging
from datetime import date, datetime

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

log = logging.getLogger(__name__)
spark = SparkSession.builder.getOrCreate()


def load_silver_orders():
    df = spark.table("bronze.orders")
    df = df.dropDuplicates(["order_id"]).withColumn("load_ts", F.lit(datetime.now()))
    print(f"loading {df.count()} rows")
    df.write.mode("append").saveAsTable("silver.orders")


def clean_orders(orders: DataFrame) -> DataFrame:
    return orders.filter(F.col("amount") > 0).dropDuplicates(["order_id"])


def add_order_month(orders: DataFrame) -> DataFrame:
    return orders.withColumn("order_month", F.date_trunc("month", F.col("order_ts")))


def tag_big_orders(orders: DataFrame, limit: float) -> DataFrame:
    return orders.withColumn("is_big", F.col("amount") > limit)


def orders_for_day(run_date: date) -> DataFrame:
    return spark.sql(f"SELECT * FROM silver.orders WHERE order_date = '{run_date}'")


def orders_for_day_safe(spark: SparkSession, run_date: date) -> DataFrame:
    return spark.sql("SELECT order_id, amount FROM silver.orders WHERE order_date = :d", args={"d": run_date})


def store_totals(spark: SparkSession, store_ids: list) -> list:
    totals = []
    for store_id in store_ids:
        totals.append(spark.sql(f"SELECT sum(amount) AS t FROM silver.orders WHERE store_id = {store_id}").collect())
    return totals


def wide_orders(orders: DataFrame, extra: list) -> DataFrame:
    for name in extra:
        orders = orders.withColumn(name, F.lit(None))
    return orders


def has_new_orders(orders: DataFrame) -> bool:
    return orders.count() > 0


def top_orders_preview(orders: DataFrame) -> list:
    return orders.orderBy(F.col("amount").desc()).limit(10).collect()


def to_local(orders: DataFrame):
    return orders.toPandas()


def enrich_with_stores(orders: DataFrame, stores: DataFrame) -> DataFrame:
    return orders.join(stores)


def enrich_with_calendar(orders: DataFrame, calendar_flags: DataFrame) -> DataFrame:
    # shiftleft: allow SL-COST-CODE-14 -- calendar_flags is one row of run-wide flags
    return orders.crossJoin(F.broadcast(calendar_flags))


def is_valid(orders: DataFrame) -> DataFrame:
    return orders.filter((F.col("amount") > 0) & (F.col("status").isin("P", "R")) & F.col("store_id").isNotNull() & (F.col("currency") == "INR") & (F.col("channel") != "test") & F.col("customer_id").isNotNull())


def safe_load(df: DataFrame) -> None:
    try:
        df.write.mode("append").saveAsTable("silver.orders")
    except Exception:
        log.info("skipped")
