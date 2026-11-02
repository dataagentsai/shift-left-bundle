import os
import sys

import pytest

# Workers must use the same Python as the tests (lesson from 2 Nov 2026: version mismatch otherwise).
os.environ["PYSPARK_PYTHON"] = sys.executable  # always override: a shell value breaks workers
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
os.environ.setdefault("TZ", "UTC")


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession
    s = (SparkSession.builder.master("local[1]").appName("shift-left-tests")
         .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "1")
         .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    yield s
    s.stop()
