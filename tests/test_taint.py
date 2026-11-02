"""Table-driven tests for the SQL value-source trace (taint.py, SL-069)."""
import ast
import textwrap

import pytest

from shiftleft import refine, taint
from shiftleft.model import Finding

CASES = [
    # name, files, (file, line of the SQL), expected verdict, expected source kinds
    ("widget value into SQL", {"nb.py": """\
        d = dbutils.widgets.get("d")
        spark.sql(f"SELECT * FROM t WHERE d = '{d}'")
        """}, ("nb.py", 2), "block", {"widget"}),
    ("widget used inside a function", {"nb.py": """\
        d = dbutils.widgets.get("d")
        def load():
            return spark.sql(f"SELECT * FROM t WHERE d = '{d}'")
        """}, ("nb.py", 3), "block", {"widget"}),
    ("command-line value through one call", {"deploy.py": """\
        def find(source):
            sql = f"SELECT g FROM m WHERE source_id = '{source}'"
            return run(sql)
        def main(argv=None):
            args = ap.parse_args(argv)
            find(args.source)
        """}, ("deploy.py", 2), "block", {"command-line"}),
    ("environment value", {"m.py": """\
        import os
        spark.sql(f"SELECT * FROM {os.environ['SCHEMA']}.t")
        """}, ("m.py", 2), "block", {"environment"}),
    ("watermark read from a table, through a helper", {"utils.py": """\
        LOW = "0000-00-00"
        def get_watermark(layer, table, default=LOW):
            rows = spark.table(WM).where(c).collect()
            return rows[0][0] if rows else default
        """, "job.py": """\
        wm = get_watermark("silver", "orders")
        spark.sql(f"SELECT * FROM {SOURCE} WHERE load_date > '{wm}'")
        """}, ("job.py", 2), "warn", {"table", "config"}),
    ("metadata rows through a loop and a call", {"recon.py": """\
        def count(schema, table):
            query = f"(SELECT COUNT(*) FROM {schema}.{table}) t"
            return spark.read.jdbc(url=U, table=query)
        def run():
            rows = spark.table(META).collect()
            for d in rows:
                count(d["schema"], d["table"])
        """}, ("recon.py", 2), "warn", {"table"}),
    ("config names only", {"m.py": """\
        for layer in (CONFIG.bronze, CONFIG.silver):
            spark.sql(f"CREATE SCHEMA {CONFIG.schema(layer)}")
        """}, ("m.py", 2), "report", {"config"}),
    ("parameter with no caller stays as found", {"m.py": """\
        def orders_for_day(run_date):
            return spark.sql(f"SELECT * FROM t WHERE d = '{run_date}'")
        """}, ("m.py", 2), None, {"parameter"}),
    ("one untrusted caller among trusted ones blocks", {"m.py": """\
        def q(d):
            return spark.sql(f"SELECT * FROM t WHERE d = '{d}'")
        q("2026-01-01")
        q(dbutils.widgets.get("d"))
        """}, ("m.py", 2), "block", {"constant", "widget"}),
    ("SQL kept in a variable", {"m.py": """\
        d = dbutils.widgets.get("d")
        q = "SELECT * FROM t WHERE d = '" + d + "'"
        spark.sql(q)
        """}, ("m.py", 3), "block", {"widget"}),
    ("method call binds past self", {"m.py": """\
        class R:
            def run(self, d):
                return spark.sql(f"SELECT * FROM t WHERE d = '{d}'")
        R().run(sys.argv[1])
        """}, ("m.py", 3), "block", {"command-line"}),
    ("unknown library value stays as found", {"m.py": """\
        d = some_lib.next_date()
        spark.sql(f"SELECT * FROM t WHERE d = '{d}'")
        """}, ("m.py", 2), None, {"unknown"}),
]


def trace(tmp_path, files, file, line):
    for name, body in files.items():
        (tmp_path / name).write_text(textwrap.dedent(body))
    ix = taint.Index.build(tmp_path, list(files))
    stmt = [n for n in ast.walk(ix.trees[file]) if isinstance(n, ast.stmt) and n.lineno <= line <= n.end_lineno]
    stmt = min(stmt, key=lambda n: n.end_lineno - n.lineno)
    t = taint.Tracer(ix)
    labels = set()
    for e in t.interpolations(stmt, file):
        labels |= t.sources(e, file)
    return labels


@pytest.mark.parametrize("name, files, at, verdict, kinds", CASES, ids=[c[0] for c in CASES])
def test_trace(tmp_path, name, files, at, verdict, kinds):
    labels = trace(tmp_path, files, *at)
    assert {k for k, _ in labels} >= kinds
    assert taint.verdict(labels) == verdict


def test_refine_names_the_source_on_block(tmp_path):
    (tmp_path / "nb.py").write_text('d = dbutils.widgets.get("d")\nspark.sql(f"SELECT * FROM t WHERE d = \'{d}\'")\n')
    f = Finding("SL-SEC-01", "nb.py", 2, "ruff", "S608", "injection")
    kept, _ = refine.apply([f], tmp_path, ["sql-value-source"])
    assert kept[0].gate == "" and kept[0].message.startswith("untrusted input reaches the SQL text: widget at nb.py:1")


def test_refine_lowers_table_values_to_warn(tmp_path):
    (tmp_path / "m.py").write_text('wm = spark.table(W).collect()[0][0]\nspark.sql(f"SELECT * FROM t WHERE d > \'{wm}\'")\n')
    f = Finding("SL-SEC-01", "m.py", 2, "sparkdoctor", "SDK026", "dynamic")
    kept, notes = refine.apply([f], tmp_path, ["sql-value-source"])
    assert kept[0].gate == "warn" and notes == ["refine sql-value-source: lowered 1 finding(s) to warn"]
