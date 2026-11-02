"""pytest plugin: the test-time purity guard (SL-PURE-05, SL-051).

    @pytest.mark.pure
    def test_clean_orders(spark): ...

Inside a test marked `pure`, any table read, table write, catalog SQL or dbutils call raises ImpureCallError, so a
function that claims to be pure but touches a table fails its own unit test. `assert_repeatable(fn, *args)` runs a
function twice on the same input and checks the outputs match. Registered through the `pytest11` entry point;
or load it with `-p shiftleft.pytest_plugin`. PySpark is imported only when a marked test runs.
"""
import pytest


class ImpureCallError(AssertionError):
    pass


def _blocker(what):
    def blocked(*_a, **_k):
        raise ImpureCallError(f"{what} was called inside a test marked pure")
    return blocked


def pytest_configure(config):
    config.addinivalue_line("markers", "pure: the code under test must not read, write or change tables")


@pytest.fixture(autouse=True)
def _shiftleft_pure_guard(request, monkeypatch):
    if request.node.get_closest_marker("pure") is None:
        yield
        return
    from pyspark.sql import DataFrame, DataFrameReader, DataFrameWriter, SparkSession
    for name in ("table", "sql"):
        monkeypatch.setattr(SparkSession, name, _blocker(f"SparkSession.{name}"))
    monkeypatch.setattr(SparkSession, "read", property(_blocker("SparkSession.read")))
    monkeypatch.setattr(SparkSession, "readStream", property(_blocker("SparkSession.readStream")))
    monkeypatch.setattr(DataFrame, "write", property(_blocker("DataFrame.write")))
    monkeypatch.setattr(DataFrame, "writeTo", _blocker("DataFrame.writeTo"))
    for name in ("load", "table", "csv", "json", "parquet"):
        monkeypatch.setattr(DataFrameReader, name, _blocker(f"DataFrameReader.{name}"))
    for name in ("save", "saveAsTable", "insertInto"):
        monkeypatch.setattr(DataFrameWriter, name, _blocker(f"DataFrameWriter.{name}"))
    try:
        from delta.tables import DeltaTable
        for name in ("forName", "forPath"):
            monkeypatch.setattr(DeltaTable, name, _blocker(f"DeltaTable.{name}"))
    except ImportError:
        pass
    yield


def assert_repeatable(fn, *args, **kwargs):
    """Run fn twice on the same input; the two results must be equal (a pure function gives the same answer)."""
    from pyspark.testing import assertDataFrameEqual
    first, second = fn(*args, **kwargs), fn(*args, **kwargs)
    if hasattr(first, "_jdf"):
        assertDataFrameEqual(first, second)
    else:
        assert first == second, f"{getattr(fn, '__name__', fn)} gave different results on the same input"
