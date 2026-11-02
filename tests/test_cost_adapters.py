"""Table-driven tests for Tier 4 adapters: notebook SQL extraction, materialized-view and grant rules,
bundle rules, SparkDoctor and pyspark-antipattern parsers, and the CostLens adapter when it is installed."""
import json
from pathlib import Path

import pytest

from shiftleft import catalog
from shiftleft.adapters import _notebooks, bundle_rules, pyspark_antipattern, sparkdoctor, sqlglot_rules
from shiftleft.model import Context

CHECKS, GATES, BINDING = catalog.load("databricks")
SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample-project"


def ctx(p):
    return Context(p, "all", BINDING, CHECKS, GATES)


NB_CASES = [
    # name, file name, content, expected [(first line, sql)]
    ("source notebook %sql cell", "n.py",
     "# Databricks notebook source\nx = 1\n\n# COMMAND ----------\n\n# MAGIC %sql\n# MAGIC SELECT *\n# MAGIC FROM t\n",
     [(7, "SELECT *\nFROM t")]),
    ("plain python file has no cells", "n.py", "# MAGIC %sql\n# MAGIC SELECT 1\n", []),
    ("empty sql cell ignored", "n.py", "# Databricks notebook source\n# MAGIC %sql\n\n# COMMAND ----------\n", []),
    ("ipynb %%sql cell", "n.ipynb", json.dumps({"cells": [{"cell_type": "code", "source": ["%%sql\n", "SELECT 1"]},
                                                          {"cell_type": "code", "source": ["print(1)"]}]}), [(1, "SELECT 1")]),
]


@pytest.mark.parametrize("name, fname, content, expected", NB_CASES, ids=[c[0] for c in NB_CASES])
def test_notebook_sql_cells(tmp_path, name, fname, content, expected):
    p = tmp_path / fname
    p.write_text(content)
    assert _notebooks.sql_cells(p) == expected


SQL_CASES = [
    # name, files {name: text}, expected checks (sorted)
    ("random in a materialized view", {"a.sql": "CREATE MATERIALIZED VIEW m AS SELECT rand() r FROM t"},
     ["SL-COST-CODE-22", "SL-COST-CONFIG-09"]),
    ("deterministic view is clean", {"a.sql": "CREATE MATERIALIZED VIEW m AS SELECT a, sum(b) FROM t GROUP BY a"}, []),
    ("refresh every 5 minutes", {"a.sql": "CREATE MATERIALIZED VIEW m SCHEDULE EVERY 5 MINUTES AS SELECT a FROM t"}, ["SL-COST-CONFIG-06"]),
    ("refresh every 2 hours is fine", {"a.sql": "CREATE MATERIALIZED VIEW m SCHEDULE EVERY 2 HOURS AS SELECT a FROM t"}, []),
    ("three views stacked", {"a.sql": "CREATE MATERIALIZED VIEW m1 AS SELECT a FROM t",
                             "b.sql": "CREATE MATERIALIZED VIEW m2 AS SELECT a FROM m1",
                             "c.sql": "CREATE MATERIALIZED VIEW m3 AS SELECT a FROM m2"}, ["SL-COST-CODE-23"]),
    ("two views stacked is within the limit", {"a.sql": "CREATE MATERIALIZED VIEW m1 AS SELECT a FROM t",
                                               "b.sql": "CREATE MATERIALIZED VIEW m2 AS SELECT a FROM m1"}, []),
    ("grant all", {"g.sql": "GRANT ALL PRIVILEGES ON SCHEMA s TO `data team`;"}, ["SL-SEC-08"]),
    ("grant to everyone", {"g.sql": "GRANT SELECT ON TABLE t TO `account users`;"}, ["SL-SEC-08"]),
    ("narrow grant is fine", {"g.sql": "GRANT SELECT ON TABLE t TO `finance readers`;"}, []),
]


@pytest.mark.parametrize("name, files, expected", SQL_CASES, ids=[c[0] for c in SQL_CASES])
def test_sqlglot_rules(tmp_path, name, files, expected):
    for n, text in files.items():
        (tmp_path / n).write_text(text)
    assert sorted(f.check for f in sqlglot_rules.scan(ctx(tmp_path)).findings) == expected


BUNDLE_ROOT = "bundle: {name: b}\ninclude: [resources/*.yml]\n"
BUNDLE_CASES = [
    # name, resources yaml, expected checks
    ("job with no tags and no timeout", "resources:\n  jobs:\n    j:\n      name: j\n", ["SL-COST-CONFIG-03", "SL-COST-CONFIG-08"]),
    ("job with tags and timeout", "resources:\n  jobs:\n    j:\n      tags: {team: a}\n      timeout_seconds: 60\n", []),
    ("autoscale without max", "resources:\n  jobs:\n    j:\n      tags: {team: a}\n      timeout_seconds: 60\n      job_clusters:\n"
     "        - job_cluster_key: k\n          new_cluster:\n            autoscale: {min_workers: 1}\n", ["SL-COST-CONFIG-04"]),
    ("cluster with no autotermination and no tags", "resources:\n  clusters:\n    c:\n      num_workers: 2\n", ["SL-COST-CONFIG-01", "SL-COST-CONFIG-03"]),
    ("cluster with both", "resources:\n  clusters:\n    c:\n      autotermination_minutes: 30\n      custom_tags: {team: a}\n", []),
]


@pytest.mark.parametrize("name, res, expected", BUNDLE_CASES, ids=[c[0] for c in BUNDLE_CASES])
def test_bundle_rules(tmp_path, name, res, expected):
    (tmp_path / "databricks.yml").write_text(BUNDLE_ROOT)
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "r.yml").write_text(res)
    assert sorted(f.check for f in bundle_rules.findings(tmp_path)) == expected


def test_sparkdoctor_maps_adopted_rules_and_ignores_the_rest(tmp_path):
    items = [{"rule_id": "SDK003", "filename": "a.py", "line": 3, "message": "count"},
             {"rule_id": "SDK011", "filename": "a.py", "line": 4, "message": "magic literal"}]
    found, notes = sparkdoctor.parse(items, ctx(tmp_path))
    assert [(f.check, f.line) for f in found] == [("SL-COST-CODE-06", 3)]
    assert notes == ["sparkdoctor: 1 findings from rules not adopted were ignored"]


def test_pyspark_antipattern_text_is_parsed_and_filtered(tmp_path):
    text = ("error[S011][HIGH]: Join without join conditions causes a nested-loop scan\n  --> src/a.py:12:5\n   |\n"
            "error[F004][LOW]: Avoid spark.sql(); prefer native DataFrame API\n  --> src/a.py:20:1\n")
    assert [(f.check, f.file, f.line) for f in pyspark_antipattern.parse(text, ctx(tmp_path))] == [("SL-COST-CODE-14", "src/a.py", 12)]


def test_every_mapped_rule_points_at_a_real_check():
    for m in ("sparkdoctor_map", "pyspark_antipattern_map", "sqlfluff_map", "ruff_map"):
        assert all(c in CHECKS for c in BINDING[m].values()), m


def test_costlens_adapter_on_the_sample():
    pytest.importorskip("costlens")
    from shiftleft.adapters import costlens
    res = costlens.scan(ctx(SAMPLE))
    got = {(f.check, f.file) for f in res.findings}
    assert ("SL-COST-CONFIG-02", "resources/jobs.yml") in got          # bundle includes are followed
    assert ("SL-COST-CODE-17", "notebooks/daily_load.py") in got       # %sql cell in a source notebook is read
    assert all(f.check in CHECKS for f in res.findings)
