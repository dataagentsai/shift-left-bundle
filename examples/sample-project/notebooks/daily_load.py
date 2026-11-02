# Databricks notebook source
# MAGIC %pip install great-tables

# COMMAND ----------

# MAGIC %run ./shared_helpers

# COMMAND ----------

from pyspark.sql import functions as F

token = dbutils.secrets.get(scope="shop", key="api-token")
print(f"using token {token}")

# COMMAND ----------

orders = spark.read.format("csv").option("header", "true").option("inferSchema", "true").load("/Volumes/shop/landing/orders/")
customers = spark.table("silver.customers")

# COMMAND ----------

def build_daily(orders, customers):
    joined = orders.join(customers, orders.customer_id == customers.customer_id)
    for row in joined.collect():
        spark.sql(f"UPDATE silver.customers SET last_seen = current_date() WHERE customer_id = {row.customer_id}")
    return joined

daily = build_daily(orders, customers)
daily.show()
display(customers.select("email", "phone").limit(20))

# COMMAND ----------

daily.coalesce(1).write.mode("overwrite").saveAsTable("gold.daily_orders")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM gold.daily_orders o, silver.stores s ORDER BY o.amount DESC
