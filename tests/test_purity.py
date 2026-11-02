"""Table-driven tests for the purity classifier: each case is a tiny module and the verdict expected per function."""
import textwrap

import pytest

from shiftleft import catalog, purity
from shiftleft.adapters import purity_adapter

_, _, BINDING = catalog.load("databricks")
PUR = BINDING["purity"]

CASES = [
    # name, module source, {function: (verdict, could_be_pure, categories)}
    ("lazy transform is pure", """
        def clean(df):
            return df.filter(F.col("a") > 0).dropDuplicates(["id"])
     """, {"clean": ("pure", False, set())}),
    ("reading a table is impure, and could be pure when it holds logic", """
        def load(spark):
            return spark.table("t").filter("a > 0")
     """, {"load": ("impure", True, {"table_read"})}),
    ("a read with no logic is a shell, not could-be-pure", """
        def read(spark):
            return spark.table("t")
     """, {"read": ("impure", False, {"table_read"})}),
    ("the clock makes it impure", """
        def stamp(df):
            return df.withColumn("ts", F.lit(datetime.now()))
     """, {"stamp": ("impure", True, {"clock"})}),
    ("a column function from the clock list is impure", """
        def stamp(df):
            return df.withColumn("ts", F.current_timestamp())
     """, {"stamp": ("impure", True, {"clock"})}),
    ("a module-level session used inside is impure", """
        spark = SparkSession.builder.getOrCreate()
        def get():
            return spark.range(3).select("id")
     """, {"get": ("impure", True, {"global_session"})}),
    ("a session passed in is not global", """
        spark = SparkSession.builder.getOrCreate()
        def get(spark):
            return spark.range(3).select("id")
     """, {"get": ("unknown", False, set())}),
    ("calling an impure repository function spreads", """
        def write(df):
            df.write.saveAsTable("t")
        def run(df):
            write(df.select("a"))
     """, {"write": ("impure", False, {"table_write"}), "run": ("impure", False, {"calls_impure"})}),
    ("calling a pure repository function stays pure", """
        def a(df):
            return df.select("x")
        def b(df):
            return a(df).filter("x > 1")
     """, {"a": ("pure", False, set()), "b": ("pure", False, set())}),
    ("an unknown library call gives unknown, never pure", """
        def enrich(df):
            return some_lib.enrich(df)
     """, {"enrich": ("unknown", False, set())}),
    ("changing an argument in place is impure", """
        def add(cols):
            cols.append("x")
            return cols
     """, {"add": ("impure", False, {"global_state"})}),
    ("building a local list is pure", """
        def names(n):
            out = []
            out.append(n.strip().title())
            return out
     """, {"names": ("pure", False, set())}),
    ("an action inside logic is impure", """
        def any_rows(df):
            return df.count() > 0
     """, {"any_rows": ("impure", False, {"engine_action"})}),
    ("a global statement is impure", """
        N = 0
        def bump():
            global N
            N += 1
     """, {"bump": ("impure", False, {"global_state"})}),
]


@pytest.mark.parametrize("name, src, expected", CASES, ids=[c[0] for c in CASES])
def test_classify(tmp_path, name, src, expected):
    (tmp_path / "m.py").write_text(textwrap.dedent(src))
    fns = {f.name: f for f in purity.analyse(tmp_path, PUR, [tmp_path / "m.py"])}
    got = {n: (f.verdict, bool(purity.could_be_pure(f)), f.categories) for n, f in fns.items()}
    assert got == expected


FINDING_CASES = [
    # name, module source, test file source, expected checks (sorted, PURE-01 summary excluded)
    ("untested pure function", "def f(df):\n    return df.select('a')\n", "", ["SL-TEST-02", "SL-TEST-03"]),
    ("tested pure function", "def f(df):\n    return df.select('a')\n", "from m import f\n", []),
    ("false pure mark", "@pure\ndef f(spark):\n    return spark.table('t')\n", "import m\n", ["SL-PURE-05"]),
    ("clock in logic", "def f(df):\n    return df.withColumn('d', F.lit(date.today()))\n", "import m\n", ["SL-PURE-03"]),
    ("action in logic", "def f(df):\n    return df.count() > 0\n", "import m\n", ["SL-PURE-06"]),
    ("module session", "spark = SparkSession.builder.getOrCreate()\n", "import m\n", ["SL-PURE-07"]),
]


@pytest.mark.parametrize("name, src, test_src, expected", FINDING_CASES, ids=[c[0] for c in FINDING_CASES])
def test_purity_findings(tmp_path, name, src, test_src, expected):
    (tmp_path / "m.py").write_text(src)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_m.py").write_text(test_src)
    got = sorted(f.check for f in purity_adapter.findings(tmp_path, BINDING) if f.check != "SL-PURE-01")
    assert got == expected
