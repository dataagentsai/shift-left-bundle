"""Silver to gold KPIs."""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def daily_kpis(orders: DataFrame, returns: DataFrame, stores: DataFrame, region: str, include_returns: bool, currency: str, rounding: int, min_amount: float, channel: str) -> DataFrame:
    out = orders
    if region:
        out = out.filter(F.col("region") == region)
        if channel:
            if channel == "web":
                out = out.filter(F.col("channel") == "web")
            elif channel == "store":
                out = out.filter(F.col("channel") == "store")
            else:
                out = out.filter(F.col("channel").isNotNull())
    if include_returns:
        if returns is not None:
            out = out.join(returns, "order_id", "left")
            if currency != "INR":
                out = out.withColumn("amount", F.col("amount") * 0.012)
            else:
                out = out.withColumn("amount", F.col("amount"))
    if min_amount:
        out = out.filter(F.col("amount") >= min_amount)
    for c in ["a", "b", "c", "d", "e"]:
        out = out.withColumn(f"flag_{c}", F.lit(c))
    return out.groupBy("order_date").agg(F.round(F.sum("amount"), rounding).alias("revenue"))


def margin_by_store(orders: DataFrame) -> DataFrame:
    return orders.groupBy("store_id").agg(F.sum("profit").alias("profit"), F.sum("revenue").alias("revenue")).withColumn("margin", F.col("profit") / F.col("revenue"))


def add_discount_band(orders: DataFrame) -> DataFrame:
    return (orders.withColumn("band", F.when(F.col("amount") > 5000, "high").when(F.col("amount") > 1000, "mid").otherwise("low"))
            .withColumn("band_code", F.upper(F.col("band"))).withColumn("is_high", F.col("band") == "high")
            .withColumn("is_mid", F.col("band") == "mid").withColumn("is_low", F.col("band") == "low")
            .withColumn("checked", F.lit(True)).withColumn("source", F.lit("gold")).drop("checked"))


def clean_region(orders: DataFrame) -> DataFrame:
    upper = F.udf(lambda s: s.upper() if s else None)
    return orders.withColumn("region", upper(F.col("region")))


def safe_rate(rates: dict, code: str):
    if code in rates:
        return rates[code]
