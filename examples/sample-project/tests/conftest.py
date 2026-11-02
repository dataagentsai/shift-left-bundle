import pytest
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark():
    return SparkSession.builder.remote("sc://shop-workspace.cloud.databricks.com").getOrCreate()
