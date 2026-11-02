"""Table-driven tests for our own pattern rules (SL-064, adapters/patterns.py)."""
import json
import textwrap

import pytest

from shiftleft import catalog
from shiftleft.adapters import patterns
from shiftleft.model import Context

CHECKS, GATES, BINDING = catalog.load("databricks")
NB = "# Databricks notebook source\n"


def scan(tmp_path, tree):
    for name, body in tree.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body if name.endswith(".ipynb") else textwrap.dedent(body))
    ctx = Context(tmp_path, "all", BINDING, CHECKS, GATES)
    return sorted(f.check for f in patterns.scan(ctx).findings)


def ipynb(*cells):
    return json.dumps({"cells": [{"cell_type": "code", "source": [c]} for c in cells]})


CASES = [
    # name, files, expected checks
    # ---- SL-SEC-06 secret printed
    ("secret printed in an f-string", {"nb.py": NB + 't = dbutils.secrets.get(scope="s", key="k")\nprint(f"tok {t}")\n'},
     ["SL-SEC-06"]),
    ("secret logged directly", {"m.py": 'log.info(dbutils.secrets.get("s", "k"))\n'}, ["SL-SEC-06"]),
    ("secret used, not printed", {"m.py": 't = dbutils.secrets.get("s", "k")\nconnect(token=t)\nprint("connected")\n'}, []),
    # ---- SL-SEC-07 personal columns shown
    ("personal columns displayed", {"nb.py": NB + 'display(c.select("email", "phone").limit(20))\n'},
     ["SL-SEC-07"]),
    ("personal column shown with show()", {"m.py": 'c.select(F.col("customer_email")).show()\n'}, ["SL-SEC-07"]),
    ("non-personal columns shown", {"m.py": 'c.select("order_id", "amount").show()\n'}, []),
    ("count of personal column is not shown", {"m.py": 'print(c.select("email").count())\n'}, []),
    # ---- SL-TEST-04 offline tests
    ("remote session in conftest", {"tests/conftest.py": 'SparkSession.builder.remote("sc://ws").getOrCreate()\n'},
     ["SL-TEST-04"]),
    ("cluster master in tests", {"tests/conftest.py": 'SparkSession.builder.master("spark://h:7077").getOrCreate()\n'},
     ["SL-TEST-04"]),
    ("local master is fine", {"tests/conftest.py": 'SparkSession.builder.master("local[1]").getOrCreate()\n'}, []),
    ("databricks connect import", {"tests/conftest.py": "from databricks.connect import DatabricksSession\n"},
     ["SL-TEST-04"]),
    ("shared table read in a test", {"tests/test_a.py": 'def test_a(spark):\n    assert spark.table("silver.o") is not None\n'},
     ["SL-TEST-04"]),
    ("remote session outside tests is not a test problem", {"src/s.py": 'SparkSession.builder.remote("sc://ws")\n'}, []),
    # ---- SL-TEST-06 count-only tests
    ("count-only test", {"tests/test_a.py": "def test_a(df):\n    assert f(df).count() == 1\n"}, ["SL-TEST-06"]),
    ("len-only test", {"tests/test_a.py": "def test_a(df):\n    assert len(f(df).collect()) == 2\n"}, ["SL-TEST-06"]),
    ("count plus value check", {"tests/test_a.py": "def test_a(df):\n    r = f(df)\n    assert r.count() == 1\n"
                                                  "    assert r.first().amount == 10\n"}, []),
    ("value comparison (trap T11)", {"tests/test_a.py": "def test_a(df):\n    assert got == {1: True}\n"}, []),
    ("count assertion outside tests is ignored", {"src/a.py": "def test_a(df):\n    assert df.count() == 1\n"}, []),
    # ---- SL-CLEAN-08 thin notebooks
    ("notebook defines functions (one finding)", {"nb.py": NB + "def a():\n    pass\n\ndef b():\n    pass\n"},
     ["SL-CLEAN-08"]),
    ("module defines functions", {"src/m.py": "def a():\n    pass\n"}, []),
    ("jupyter notebook defines a function", {"nb.ipynb": ipynb("%pip install x\n", "def a():\n    return 1\n")},
     ["SL-CLEAN-08"]),
    # ---- SL-CLEAN-14 column as attribute
    ("join on attributes", {"m.py": "o.join(c, o.customer_id == c.customer_id, \"inner\")\n"}, ["SL-CLEAN-14"]),
    ("filter on attribute", {"m.py": "o.filter(o.amount > 0)\n"}, ["SL-CLEAN-14"]),
    ("join on names", {"m.py": 'o.join(c, "customer_id", "inner")\n'}, []),
    ("F.col is fine", {"m.py": 'o.filter(F.col("amount") > 0)\n'}, []),
    ("columns property and alias call are fine", {"m.py": 'o.select(o.columns)\no.join(c.alias("c"), "id", "left")\n'}, []),
    # ---- SL-CLEAN-23 notebook chains
    ("%run magic", {"nb.py": NB + "# MAGIC %run ./helpers\n"}, ["SL-CLEAN-23"]),
    ("dbutils.notebook.run", {"nb.py": NB + 'dbutils.notebook.run("./child", 60)\n'}, ["SL-CLEAN-23"]),
    ("%run in a jupyter cell", {"nb.ipynb": ipynb("%run ./helpers\n")}, ["SL-CLEAN-23"]),
    ("%run text in a module is ignored", {"m.py": 'HELP = "use %run in notebooks"\n'}, []),
    # ---- SL-CLEAN-26 inline conditions
    ("four inline conditions", {"m.py": 'o.filter((a > 0) & (b == 1) & c.isNotNull() & (d != "x"))\n'}, ["SL-CLEAN-26"]),
    ("three inline conditions are fine", {"m.py": "o.filter((a > 0) & (b == 1) | c.isNotNull())\n"}, []),
    ("long when condition", {"m.py": 'F.when((a > 0) & (b > 0) & (c > 0) & (d > 0), 1)\n'}, ["SL-CLEAN-26"]),
    # ---- SL-CLEAN-29 null column with no type
    ("lit(None) as a new column", {"m.py": 'df.withColumn("x", F.lit(None))\n'}, ["SL-CLEAN-29"]),
    ("lit(None) aliased in select", {"m.py": 'df.select("a", F.lit(None).alias("x"))\n'}, ["SL-CLEAN-29"]),
    ("lit(None) in withColumns", {"m.py": 'df.withColumns({"x": F.lit(None)})\n'}, ["SL-CLEAN-29"]),
    ("lit(None) cast", {"m.py": 'df.withColumn("x", F.lit(None).cast("string"))\n'}, []),
    ("lit(None) inside when is typed by otherwise", {"m.py": 'df.withColumn("x", F.when(c, F.lit(None)).otherwise(1))\n'}, []),
    # ---- SL-CLEAN-30 ordered window with no frame
    ("sum over ordered window", {"m.py": 'w = Window.partitionBy("c").orderBy("d")\ndf.withColumn("t", F.sum("a").over(w))\n'},
     ["SL-CLEAN-30"]),
    ("inline ordered window", {"m.py": 'df.withColumn("t", F.max("a").over(Window.orderBy("d")))\n'}, ["SL-CLEAN-30", "SL-COST-CODE-25"]),
    ("frame stated", {"m.py": "w = Window.partitionBy('c').orderBy('d').rowsBetween(Window.unboundedPreceding, 0)\n"
                              "df.withColumn('t', F.sum('a').over(w))\n"}, []),
    ("frame added to a named spec", {"m.py": "w = Window.partitionBy('c').orderBy('d')\nw2 = w.rowsBetween(-2, 0)\n"
                                             "df.withColumn('t', F.avg('a').over(w2))\n"}, []),
    ("ranking needs no frame (SCD2 pattern)", {"m.py": "w = Window.partitionBy('k').orderBy(F.col('ts').desc())\n"
                                                       "df.withColumn('rn', F.row_number().over(w))\n"}, []),
    ("unordered window is the whole partition", {"m.py": "w = Window.partitionBy('c')\ndf.withColumn('t', F.sum('a').over(w))\n"}, []),
    # ---- SL-COST-CODE-25 window with no partition
    ("rank over the whole table", {"m.py": "w = Window.orderBy(F.col('rev').desc())\ndf.withColumn('r', F.ntile(5).over(w))\n"},
     ["SL-COST-CODE-25"]),
    ("running sum over the whole table (both checks)", {"m.py": "df.withColumn('t', F.sum('a').over(Window.orderBy('d')))\n"},
     ["SL-CLEAN-30", "SL-COST-CODE-25"]),
    ("partitioned rank is fine", {"m.py": "w = Window.partitionBy('c').orderBy('d')\ndf.withColumn('r', F.row_number().over(w))\n"}, []),
    ("SQL OVER ORDER BY", {"q.sql": "SELECT a,\n  row_number() OVER (ORDER BY a) AS r\nFROM t\n"}, ["SL-COST-CODE-25"]),
    ("SQL OVER PARTITION BY is fine", {"q.sql": "SELECT row_number() OVER (PARTITION BY c ORDER BY a) FROM t\n"}, []),
    ("SQL OVER ORDER BY in a comment is ignored", {"q.sql": "-- row_number() OVER (ORDER BY a)\nSELECT 1\n"}, []),
    ("%sql cell OVER ORDER BY", {"nb.py": NB + "# MAGIC %sql\n# MAGIC SELECT rank() OVER (ORDER BY x) FROM t\n"},
     ["SL-COST-CODE-25"]),
    # ---- SL-CLEAN-31 join type
    ("join with no how", {"m.py": 'o.join(c, "customer_id")\n'}, ["SL-CLEAN-31"]),
    ("join with on= and no how", {"m.py": 'o.join(c, on="customer_id")\n'}, ["SL-CLEAN-31"]),
    ("join with how", {"m.py": 'o.join(c, "customer_id", "left")\no.join(c, on="id", how="inner")\n'}, []),
    ("string and path joins are not data joins", {"m.py": '", ".join(names)\nos.path.join(a, b)\n'}, []),
    # ---- SL-CLEAN-32 whole-row dedupe
    ("dropDuplicates with no columns", {"m.py": "df.dropDuplicates()\n"}, ["SL-CLEAN-32"]),
    ("dropDuplicates on a key", {"m.py": 'df.dropDuplicates(["order_id"])\ndf.dropDuplicates(subset=["k"])\n'}, []),
    # ---- SL-COST-CODE-24 withColumn chain
    ("four chained withColumn (one finding)", {"m.py": "df.withColumn('a', x).withColumn('b', x).withColumn('c', x).withColumn('d', x)\n"},
     ["SL-COST-CODE-24"]),
    ("three chained withColumn", {"m.py": "df.withColumn('a', x).withColumn('b', x).withColumn('c', x)\n"}, []),
    # ---- SL-DEP-05 runtime match
    ("pyspark not pinned to the runtime", {"resources/j.yml": "spark_version: 15.4.x-scala2.12\n", "requirements.txt": "pyspark>=3\n"},
     ["SL-DEP-05"]),
    ("pyspark pinned to the runtime", {"resources/j.yml": "spark_version: 15.4.x-scala2.12\n", "requirements.txt": "pyspark==3.5.1\n"},
     []),
    ("pyspark pinned to the wrong minor", {"databricks.yml": "spark_version: 13.3.x-scala2.12\n", "requirements.txt": "pyspark==3.5.1\n"},
     ["SL-DEP-05"]),
    ("databricks-connect matches", {"resources/j.yml": "spark_version: 15.4.x-scala2.12\n",
                                    "pyproject.toml": 'dependencies = [\n  "databricks-connect==15.4.*",\n]\n'}, []),
    ("python version differs", {"resources/j.yml": "spark_version: 15.4.x-scala2.12\n", "requirements.txt": "pyspark==3.5.1\n",
                                ".python-version": "3.12.4\n"}, ["SL-DEP-05"]),
    ("tests but no pin at all", {"resources/j.yml": "spark_version: 16.4.x-scala2.12\n", "tests/test_a.py": "x = 1\n"},
     ["SL-DEP-05"]),
    ("no runtime named: nothing to compare", {"requirements.txt": "pyspark>=3\n"}, []),
]


@pytest.mark.parametrize("name, tree, expected", CASES, ids=[c[0] for c in CASES])
def test_pattern_rules(tmp_path, name, tree, expected):
    assert scan(tmp_path, tree) == expected


def test_every_rule_maps_to_a_catalog_check():
    for check in ("SL-SEC-06", "SL-SEC-07", "SL-TEST-04", "SL-TEST-06", "SL-CLEAN-08", "SL-CLEAN-14", "SL-CLEAN-23",
                  "SL-CLEAN-26", "SL-DEP-05", "SL-CLEAN-29", "SL-CLEAN-30", "SL-CLEAN-31", "SL-CLEAN-32",
                  "SL-COST-CODE-24"):
        assert check in CHECKS
        assert BINDING["checks"][check]["tool"] == "patterns"
