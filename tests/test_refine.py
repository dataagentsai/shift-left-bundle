"""Table-driven tests for the noise rules (refine.py, SL-061). Each rule: one false alarm it removes, one real finding it keeps."""
import textwrap

import pytest

from shiftleft import refine
from shiftleft.model import Finding

NB = "# Databricks notebook source\n"
UTILS = NB + "CONFIG = object()\ndef audit():\n    pass\n"

CASES = [
    # name, files, finding (check, file, line, tool_rule, message), expected: "keep" | "drop" | gate
    ("name from a %run notebook", {"nb/a.py": NB + "# MAGIC %run ./utils\naudit()\n", "nb/utils.py": UTILS},
     ("SL-STYLE-02", "nb/a.py", 3, "F821", "Undefined name `audit`"), "drop"),
    ("name that is undefined everywhere", {"nb/a.py": NB + "# MAGIC %run ./utils\nauditt()\n", "nb/utils.py": UTILS},
     ("SL-STYLE-02", "nb/a.py", 3, "F821", "Undefined name `auditt`"), "keep"),
    ("name from a nested %run", {"nb/a.py": NB + "# MAGIC %run ./b\nhelper()\n", "nb/b.py": NB + "# MAGIC %run ./c\n",
                                 "nb/c.py": NB + "def helper():\n    pass\n"},
     ("SL-STYLE-02", "nb/a.py", 3, "F821", "Undefined name `helper`"), "drop"),
    ("SQL with config table names only", {"m.py": 'spark.sql(f"SELECT * FROM {CONFIG.table(\'s\', \'o\')} JOIN {SOURCE}")\n'},
     ("SL-SEC-01", "m.py", 1, "SDK026", "dynamic"), "report"),
    ("SQL with a loop over config", {"m.py": "for layer in (CONFIG.bronze, CONFIG.silver):\n"
                                             '    spark.sql(f"CREATE SCHEMA {CONFIG.schema(layer)}")\n'},
     ("SL-SEC-01", "m.py", 2, "SDK026", "dynamic"), "report"),
    ("SQL with a widget value", {"m.py": 'd = dbutils.widgets.get("d")\nspark.sql(f"SELECT * FROM {SOURCE} WHERE d = \'{d}\'")\n'},
     ("SL-SEC-01", "m.py", 2, "SDK026", "dynamic"), "keep"),
    ("SQL with a function parameter", {"m.py": 'def f(run_date):\n    return spark.sql(f"SELECT * FROM t WHERE d = \'{run_date}\'")\n'},
     ("SL-SEC-01", "m.py", 2, "S608", "injection"), "keep"),
    ("random in data code", {"m.py": "x = random.choice(L)\n"}, ("SL-SEC-10", "m.py", 1, "S311", "random"), "report"),
    ("print in a notebook", {"nb.py": NB + 'print("done")\n'}, ("SL-CLEAN-17", "nb.py", 2, "T201", "print"), "report"),
    ("print in a module", {"m.py": 'print("done")\n'}, ("SL-CLEAN-17", "m.py", 1, "T201", "print"), "keep"),
    ("collect after a whole-table agg", {"m.py": 'm = df.agg(F.max("d")).collect()[0][0]\n'},
     ("SL-COST-CODE-01", "m.py", 1, "SDK002", "collect"), "drop"),
    ("collect after groupBy agg", {"m.py": 'rows = df.groupBy("d").agg(F.count("*")).collect()\n'},
     ("SL-COST-CODE-01", "m.py", 1, "SDK002", "collect"), "keep"),
    ("collect of a whole table", {"m.py": "rows = df.collect()\n"}, ("SL-COST-CODE-01", "m.py", 1, "SDK002", "collect"), "keep"),
    ("Delta merge builder", {"m.py": 'DeltaTable.forName(spark, T).alias("t").merge(s, c).whenMatchedUpdateAll().execute()\n'},
     ("SL-CLEAN-25", "m.py", 1, "SDK009", "chain"), "drop"),
    ("long DataFrame chain", {"m.py": "df.a().b().c().d().e().f()\n"}, ("SL-CLEAN-25", "m.py", 1, "SDK009", "chain"), "keep"),
    ("sorted display cell", {"nb.py": NB + "# MAGIC %sql\n# MAGIC SELECT * FROM t\n# MAGIC ORDER BY x;\n"},
     ("SL-COST-CODE-17", "nb.py", 4, "ordering_without_limit", "order"), "report"),
    ("sorted display cell after a comment", {"nb.py": NB + "# MAGIC %sql\n# MAGIC -- top sellers\n# MAGIC SELECT * FROM t\n# MAGIC ORDER BY x;\n"},
     ("SL-COST-CODE-17", "nb.py", 5, "ordering_without_limit", "order"), "report"),
    ("sort inside CREATE TABLE cell", {"nb.py": NB + "# MAGIC %sql\n# MAGIC CREATE TABLE g AS SELECT * FROM t\n# MAGIC ORDER BY x;\n"},
     ("SL-COST-CODE-17", "nb.py", 4, "ordering_without_limit", "order"), "keep"),
    ("DDL in a loop", {"m.py": 'for s in S:\n    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {s}")\n'},
     ("SL-COST-CODE-02", "m.py", 1, "loop_calling_spark_sql", "loop"), "drop"),
    ("query in a loop", {"m.py": 'for s in S:\n    spark.sql(f"SELECT sum(a) FROM t WHERE s = {s}").collect()\n'},
     ("SL-COST-CODE-02", "m.py", 1, "loop_calling_spark_sql", "loop"), "keep"),
    ("display is output", {"nb.py": NB + "display(df)\n"},
     ("SL-COST-CODE-11", "nb.py", 2, "code_spark_action_result_discarded", ".display() result discarded inside display(...)"), "drop"),
    ("show left in code", {"m.py": "df.show()\n"},
     ("SL-COST-CODE-11", "m.py", 1, "code_spark_action_result_discarded", ".show() result discarded"), "keep"),
    ("dash in notebook markdown", {"nb.py": NB + "# MAGIC scored 1–5\n"}, ("SL-CLEAN-20", "nb.py", 2, "RUF003", "dash"), "drop"),
    ("dash in a code comment", {"m.py": "x = 1  # 1–5\n"}, ("SL-CLEAN-20", "m.py", 1, "RUF003", "dash"), "keep"),
]


@pytest.mark.parametrize("name, tree, finding, expected", CASES, ids=[c[0] for c in CASES])
def test_refine_rules(tmp_path, name, tree, finding, expected):
    for path, body in tree.items():
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body))
    check, file, line, rule, msg = finding
    f = Finding(check, file, line, "tool", rule, msg)
    kept, notes = refine.apply([f], tmp_path, list(refine.RULES))
    got = "drop" if not kept else (kept[0].gate or "keep")
    assert got == expected, notes


def test_rules_off_keep_everything(tmp_path):
    (tmp_path / "m.py").write_text("x = random.choice(L)\n")
    f = Finding("SL-SEC-10", "m.py", 1, "ruff", "S311", "random")
    kept, notes = refine.apply([f], tmp_path, [])
    assert kept == [f] and f.gate == "" and notes == []


def test_unknown_rule_is_reported(tmp_path):
    _, notes = refine.apply([], tmp_path, ["no-such-rule"])
    assert notes == ["refine: unknown rule no-such-rule in the binding; ignored"]


def test_binding_names_only_known_rules():
    from shiftleft import catalog
    _, _, binding = catalog.load("databricks")
    assert set(binding["refine"]) <= set(refine.RULES)
