"""Refund and exchange summaries per store and day."""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def refund_summary(refunds: DataFrame) -> DataFrame:
    return (refunds
            .filter(F.col("status") == "approved")
            .groupBy("store_id", "event_date")
            .agg(F.sum("amount").alias("total"),
                 F.count("*").alias("events"),
                 F.max("amount").alias("largest"))
            .withColumnRenamed("event_date", "day"))


def exchange_summary(exchanges: DataFrame) -> DataFrame:
    return (exchanges
            .filter(F.col("status") == "approved")
            .groupBy("store_id", "event_date")
            .agg(F.sum("amount").alias("total"),
                 F.count("*").alias("events"),
                 F.max("amount").alias("largest"))
            .withColumnRenamed("event_date", "day"))
