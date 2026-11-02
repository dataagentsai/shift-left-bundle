"""`shiftleft draft-tests`: starter tests for pure functions that have none (SL-056).

For each pure, untested function it writes a table-driven test file. When a parameter's name matches a schema in
shiftleft-plans.yaml, the draft builds DataFrames and runs at once: an empty-input case, the repeatability check, the
purity guard and the cartesian check. People (or the Claude skill) then add real cases. A draft counts as done only
when mutation testing shows it catches deliberate bugs; the tool never decides that on its own."""
import ast
import datetime as _dt
from collections import defaultdict
from pathlib import Path

import yaml

from .adapters.plans import module_name

CONFTEST = '''import os
import sys

import pytest

for root in {roots!r}:
    sys.path.insert(0, root)
os.environ["PYSPARK_PYTHON"] = sys.executable        # always override: a shell value starts workers on another Python
os.environ.setdefault("TZ", "UTC")


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession
    return (SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false")
            .config("spark.sql.shuffle.partitions", "1").getOrCreate())
'''


def _params(path: Path, fn: str):
    for node in ast.parse(path.read_text(errors="ignore")).body:
        if isinstance(node, ast.FunctionDef) and node.name == fn:
            return [a.arg for a in node.args.args]
    return []


def _allows_cartesian(path: Path, fn: str):
    """True when the function carries a `shiftleft: allow SL-COST-PLAN-01/02 -- reason` marker (an intended cross join)."""
    for node in ast.parse(path.read_text(errors="ignore")).body:
        if isinstance(node, ast.FunctionDef) and node.name == fn:
            body = "\n".join(path.read_text(errors="ignore").splitlines()[node.lineno - 1: node.end_lineno])
            return "shiftleft: allow" in body and ("SL-COST-PLAN-01" in body or "SL-COST-PLAN-02" in body)
    return False


def _spark_test(fn, params, cross_ok=False):
    empty = ", ".join(f"{p!r}: []" for p in params)
    example = ", ".join(f"{p!r}: [(...)]" for p in params)
    return ["# name, input rows per parameter, expected row count (None = run only the property checks)",
            f"CASES_{fn} = [", f'    ("empty input gives empty output", {{{empty}}}, 0),',
            f'    # ("<what this case shows>", {{{example}}}, <rows out>),', "]", "", "",
            "@pytest.mark.pure",
            f'@pytest.mark.parametrize("name, rows, expected", CASES_{fn}, ids=[c[0] for c in CASES_{fn}])',
            f"def test_{fn}(spark, name, rows, expected):",
            "    args = {p: spark.createDataFrame(r, SCHEMAS[p]) for p, r in rows.items()}",
            f"    got = {fn}(**args)",
            "    if expected is not None:",
            "        assert got.count() == expected     # then compare whole rows with assertDataFrameEqual",
            f"    assert_repeatable({fn}, **args)",
            (f"    # cross join marked as intended in the code (shiftleft: allow), so no cartesian check" if cross_ok else
             f"    kit.assert_no_cartesian({fn}(**{{p: kit.schema_only(a) for p, a in args.items()}}))"), "", ""]


def _plain_test(fn, params):
    kw = ", ".join(f"{p!r}: ..." for p in params)
    return ["# name, keyword arguments, expected result. No schema matched these parameters, so no case runs yet.",
            f"CASES_{fn} = [", f'    # ("<what this case shows>", {{{kw}}}, <expected>),', "]", "", "",
            f'@pytest.mark.parametrize("name, kwargs, expected", CASES_{fn}, ids=[c[0] for c in CASES_{fn}])',
            f"def test_{fn}(name, kwargs, expected):", f"    assert {fn}(**kwargs) == expected", "", ""]


def draft(project: Path, rows, out: Path):
    cfg = project / "shiftleft-plans.yaml"
    schemas = (yaml.safe_load(cfg.read_text()) or {}).get("schemas", {}) if cfg.exists() else {}
    todo = [r for r in rows if r["verdict"] == "pure" and not r["tested"] and not r["notebook"]]
    by_module = defaultdict(list)
    for r in todo:
        by_module[r["module"]].append(r)
    out.mkdir(parents=True, exist_ok=True)
    roots, written = set(), []
    for mod_path, fns in by_module.items():
        root, mod = module_name(project / mod_path, project)
        roots.add(root)
        lines = [f'"""Drafted by `shiftleft draft-tests` on {_dt.date.today()}. Add real cases; delete what you do not need.',
                 'A draft is done when mutation testing (mutmut) shows it catches deliberate bugs."""',
                 "import pytest", "", "from shiftleft import testkit as kit", "from shiftleft.pytest_plugin import assert_repeatable",
                 f"from {mod} import {', '.join(r['function'] for r in fns)}", ""]
        used = sorted({p for r in fns for p in _params(project / mod_path, r["function"]) if p in schemas})
        if used:
            lines += ["SCHEMAS = {"] + [f"    {p!r}: {schemas[p]!r}," for p in used] + ["}", "", ""]
        for r in fns:
            fn, params = r["function"], _params(project / mod_path, r["function"])
            lines += _spark_test(fn, params, _allows_cartesian(project / mod_path, fn)) if params and all(p in schemas for p in params) else _plain_test(fn, params)
        target = out / f"test_{Path(mod_path).stem}_drafts.py"
        target.write_text("\n".join(lines).rstrip() + "\n")
        written.append(target)
    if written and not (out / "conftest.py").exists():
        (out / "conftest.py").write_text(CONFTEST.format(roots=sorted(roots)))
    return written, len(todo)
