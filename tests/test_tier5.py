"""Table-driven tests for Tier 5: metric views, dbt results, plan cases, test drafts, reports, repo-review plugin."""
import json
import textwrap
from pathlib import Path

import pytest

from shiftleft import catalog, health
from shiftleft.adapters import dbt, metricview, plans
from shiftleft.drafts import draft
from shiftleft.model import Finding

CHECKS, GATES, BINDING = catalog.load("databricks")


def mv(body, name="gold.m"):
    return f"CREATE OR REPLACE VIEW {name}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{textwrap.dedent(body)}$$;\n"


GOOD = """\
version: 1.1
source: silver.orders
dimensions:
  - name: Month
    expr: date_trunc('MONTH', order_date)
    comment: order month
measures:
  - name: Revenue
    expr: SUM(amount)
    comment: gross
"""
MV_CASES = [
    # name, sql, expected checks (sorted, SEM-07 excluded unless asked)
    ("clean view", mv(GOOD), []),
    ("yaml does not parse", mv("version: 1.1\nsource: [unclosed\n"), ["SL-SEM-01"]),
    ("unknown field", mv(GOOD + "colour: red\n"), ["SL-SEM-01"]),
    ("expression does not parse (nothing else is judged on it)", mv(GOOD.replace("SUM(amount)", "SUM(amount")), ["SL-SEM-01"]),
    ("measure without aggregate", mv(GOOD.replace("SUM(amount)", "amount")), ["SL-SEM-02"]),
    ("average of a ratio", mv(GOOD.replace("SUM(amount)", "AVG(profit / amount)")), ["SL-SEM-03"]),
    ("ratio of sums is fine", mv(GOOD.replace("SUM(amount)", "SUM(profit) / SUM(amount)")), []),
    ("missing description", mv(GOOD.replace("    comment: gross\n", "")), ["SL-SEM-06"]),
    ("join without cardinality fans out a measure", mv(GOOD.replace("dimensions:", "joins:\n  - name: lines\n    source: silver.lines\n"
                                                                     "    on: source.id = lines.id\ndimensions:")), ["SL-SEM-04", "SL-SEM-04"]),
    ("many-to-one join is fine", mv(GOOD.replace("dimensions:", "joins:\n  - name: st\n    source: silver.stores\n    on: source.s = st.s\n"
                                                 "    cardinality: many_to_one\ndimensions:")), []),
]


@pytest.mark.parametrize("name, sql, expected", MV_CASES, ids=[c[0] for c in MV_CASES])
def test_metric_view_rules(tmp_path, name, sql, expected):
    (tmp_path / "m.sql").write_text(sql)
    got = sorted(f.check for f in metricview.findings(tmp_path) if f.check != "SL-SEM-07")
    assert got == expected


def test_metric_defined_twice_and_known_answer_test(tmp_path):
    (tmp_path / "a.sql").write_text(mv(GOOD, "gold.a"))
    (tmp_path / "b.sql").write_text(mv(GOOD.replace("SUM(amount)", "SUM(amount) FILTER (WHERE ok)"), "gold.b"))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "metrics.yml").write_text("- view: a\n  expect: 10\n")
    got = sorted((f.check, f.file) for f in metricview.findings(tmp_path) if f.check in ("SL-SEM-05", "SL-SEM-07"))
    assert got == [("SL-SEM-05", "a.sql"), ("SL-SEM-05", "b.sql"), ("SL-SEM-07", "b.sql")]


def test_dbt_results_point_where_the_fix_goes(tmp_path):
    d = tmp_path / "dbt"
    (d / "models").mkdir(parents=True)
    (d / "models" / "schema.yml").write_text("models:\n  - name: fct\n")
    (d / "models" / "fct.sql").write_text("select 1\nfrom {{ source('b', 'o') }}\n")
    manifest = {"nodes": {"model.p.fct": {"name": "fct", "patch_path": "p://models/schema.yml", "original_file_path": "models/fct.sql"}}}
    items = [{"check_run_id": "check_model_has_unique_test:0:fct", "outcome": "failed", "file_path": "models/fct.sql", "unique_id": "model.p.fct"},
             {"check_run_id": "check_lineage_source_cannot_be_used:0:fct", "outcome": "failed", "file_path": "models/fct.sql", "unique_id": "model.p.fct"},
             {"check_run_id": "check_model_description_populated:0:fct", "outcome": "success", "file_path": "models/fct.sql", "unique_id": "model.p.fct"},
             {"check_run_id": "check_not_adopted:0:fct", "outcome": "failed", "file_path": "models/fct.sql", "unique_id": "model.p.fct"}]
    got = [(f.check, f.file, f.line) for f in dbt.parse_results(items, manifest, d, tmp_path, BINDING["dbt_bouncer_map"])]
    assert got == [("SL-TEST-07", "dbt/models/schema.yml", 2), ("SL-CLEAN-28", "dbt/models/fct.sql", 2)]


MODULE_CASES = [
    # files to create, path, expected (root relative to tmp, module)
    (["src/shop/__init__.py", "src/shop/x.py"], "src/shop/x.py", ("src", "shop.x")),
    (["jobs/x.py"], "jobs/x.py", ("jobs", "x")),
    (["a/__init__.py", "a/b/__init__.py", "a/b/c.py"], "a/b/c.py", ("", "a.b.c")),
]


@pytest.mark.parametrize("create, path, expected", MODULE_CASES, ids=[c[1] for c in MODULE_CASES])
def test_module_name(tmp_path, create, path, expected):
    for f in create:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("")
    root, mod = plans.module_name(tmp_path / path, tmp_path)
    assert (str(Path(root).relative_to(tmp_path)) if root != str(tmp_path) else "", mod) == expected


def test_auto_cases_need_every_parameter_to_have_a_schema(tmp_path):
    (tmp_path / "m.py").write_text("def a(orders, stores):\n    pass\ndef b(orders, limit):\n    pass\n")
    got = [c["function"] for c in plans.auto_cases(tmp_path, {"orders": "x INT", "stores": "y INT"})]
    assert got == ["a"]


def test_drafts(tmp_path):
    (tmp_path / "m.py").write_text("def clean(orders):\n    return orders.select('a')\n"
                                   "def cross(orders, flags):\n    # shiftleft: allow SL-COST-PLAN-02 -- one row\n    return orders.crossJoin(flags)\n"
                                   "def rate(rates, code):\n    return rates.get(code)\n")
    (tmp_path / "shiftleft-plans.yaml").write_text("schemas: {orders: 'a INT', flags: 'f BOOLEAN'}\n")
    rows = [{"module": "m.py", "function": f, "line": 1, "verdict": "pure", "tested": False, "notebook": False} for f in ("clean", "cross", "rate")]
    written, n = draft(tmp_path, rows, tmp_path / "drafts")
    text = written[0].read_text()
    assert n == 3 and (tmp_path / "drafts" / "conftest.py").exists()
    assert "def test_clean(spark" in text and "kit.assert_no_cartesian(clean(" in text
    assert "kit.assert_no_cartesian(cross(" not in text and "marked as intended" in text
    assert "def test_rate(name, kwargs, expected)" in text
    compile(text, "draft", "exec")


def F(check, gate, status="new", file="a.py", line=3, msg="m"):
    return Finding(check, file, line, "t", "r", msg, gate=gate, status=status)


SUMMARY_CASES = [
    # name, findings, failed, must contain
    ("blocking first", [F("SL-SEC-01", "block"), F("SL-CLEAN-01", "warn")], True, ["fix before merge", "**Blocking**", "SL-SEC-01"]),
    ("warnings when nothing blocks", [F("SL-CLEAN-01", "warn")], False, ["no blocking problems", "Top warnings"]),
    ("baseline is counted, not listed", [F("SL-SEC-01", "block", "baseline")], False, ["1 already known", "no blocking"]),
]


@pytest.mark.parametrize("name, findings, failed, want", SUMMARY_CASES, ids=[c[0] for c in SUMMARY_CASES])
def test_pr_summary(name, findings, failed, want):
    text = health.pr_summary(findings, CHECKS, "pr", failed)
    assert all(w in text for w in want), text


def test_health_page_escapes_and_trends():
    rows = [{"module": "m.py", "function": "f", "line": 1, "verdict": "pure", "tested": False, "notebook": False, "could_be_pure": False, "hint": ""}]
    page = health.health_page("demo<x>", [F("SL-SEC-01", "block", msg="<script>")], CHECKS, rows, [], [], "pr", True,
                              previous=[{"check": "SL-SEC-01", "status": "new"}, {"check": "SL-SEC-02", "status": "new"}])
    assert '<span class="down">-1</span>' in page                  # two security findings before, one now
    assert "<script>" not in page and "&lt;script&gt;" in page and "demo&lt;x&gt;" in page
    assert "Pure but untested" in page and "FAIL" in page


def test_repo_review_plugin_matches_the_builtin_checks(tmp_path):
    from shiftleft import repo_review_plugin as plug
    (tmp_path / "tests").mkdir()
    (tmp_path / "q.sql").write_text("select 1")
    checks = plug.repo_review_checks()
    results = {k: c.check(tmp_path) for k, c in checks.items()}
    assert results["SL-SETUP-08"] is True                       # tests folder exists
    assert isinstance(results["SL-SETUP-07"], str)              # SQL present, not linted
    assert plug.repo_review_families()["shiftleft"]["name"].startswith("Shift-left")


JSCPD_CASES = [
    # name, report, expected (check, file, line, message start)
    ("no copies", {"duplicates": []}, []),
    ("one copy, reported on the second file", {"duplicates": [{"format": "python", "lines": 23,
        "firstFile": {"name": "nb/a.py", "start": 32}, "secondFile": {"name": "nb/b.py", "start": 24}}]},
     [("SL-CPLX-05", "nb/b.py", 24, "23 lines copied from nb/a.py:32")]),
    ("SQL copy", {"duplicates": [{"format": "sql", "lines": 8,
        "firstFile": {"name": "sql/x.sql", "start": 1}, "secondFile": {"name": "sql/y.sql", "start": 5}}]},
     [("SL-CPLX-05", "sql/y.sql", 5, "8 lines copied from sql/x.sql:1")]),
]


@pytest.mark.parametrize("name, report, expected", JSCPD_CASES, ids=[c[0] for c in JSCPD_CASES])
def test_jscpd_parse(tmp_path, name, report, expected):
    from shiftleft.adapters import jscpd
    got = [(f.check, f.file, f.line, f.message[:len(e[3])]) for f, e in zip(jscpd.parse(report, tmp_path), expected)]
    assert got == expected and len(jscpd.parse(report, tmp_path)) == len(expected)
