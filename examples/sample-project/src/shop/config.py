"""Settings for the shop pipeline."""
import os

WAREHOUSE_URL = "jdbc:sqlserver://shop-db.internal:1433;database=shop;user=etl;password=Harbour2026!Threads"
FRAUD_LIMIT = 100


def run_env() -> str:
    return os.environ.get("SHOP_ENV", "dev")
