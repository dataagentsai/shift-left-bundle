"""Customer report: running spend, latest address, report columns."""
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


def running_spend(orders: DataFrame) -> DataFrame:
    by_customer = Window.partitionBy("customer_id").orderBy("order_date")
    return orders.withColumn("spend_to_date", F.sum("amount").over(by_customer))


def latest_address(addresses: DataFrame) -> DataFrame:
    newest_first = Window.partitionBy("customer_id").orderBy(F.col("updated_at").desc())
    return (addresses.withColumn("rn", F.row_number().over(newest_first))
            .filter(F.col("rn") == 1).drop("rn"))


def with_customer(orders: DataFrame, customers: DataFrame) -> DataFrame:
    return orders.join(customers, "customer_id")


def unique_orders(orders: DataFrame) -> DataFrame:
    return orders.dropDuplicates()


def unique_customers(customers: DataFrame) -> DataFrame:
    return customers.dropDuplicates(["customer_id"])


def report_columns(orders: DataFrame) -> DataFrame:
    return (orders
            .withColumn("discount_code", F.lit(None))
            .withColumn("channel_note", F.lit(None).cast("string"))
            .withColumn("net", F.col("amount") - F.col("discount"))
            .withColumn("tax", F.col("net") * 0.18))


def spend_rank(customers: DataFrame) -> DataFrame:
    by_spend = Window.orderBy(F.col("lifetime_spend").desc())
    return customers.withColumn("spend_rank", F.dense_rank().over(by_spend))
