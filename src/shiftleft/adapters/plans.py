"""Plan check on empty tables (SL-COST-PLAN-01..05). Needs `shiftleft-plans.yaml` at the project root:

    schemas:   {orders: "order_id INT, store_id INT, amount DOUBLE", stores: "store_id INT, region STRING"}
    cases:     [{function: "src/shop/gold_kpis.py:daily_kpis", inputs: {orders: orders, returns: orders}}]   # optional

Functions whose every parameter is named after a schema are planned automatically. The harness runs in a Python
with PySpark: SHIFTLEFT_SPARK_PYTHON, or this Python if it has pyspark."""
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from ..model import Finding, ScanResult
from ._util import files, rel

NAME = "plan-harness"
STAGES = ("pr", "nightly")
HARNESS = Path(__file__).resolve().parent.parent / "plan_harness.py"
LINE_HINT = {"SL-COST-PLAN-01": ("crossJoin", ".join("), "SL-COST-PLAN-02": ("crossJoin", ".join("), "SL-COST-PLAN-03": ("udf",),
             "SL-COST-PLAN-05": ("groupBy", ".join(", "orderBy")}


def spark_python():
    env = os.environ.get("SHIFTLEFT_SPARK_PYTHON")
    if env:
        return env
    return sys.executable if importlib.util.find_spec("pyspark") else None


def module_name(path: Path, project: Path):
    """src/shop/gold_kpis.py -> (root '/abs/src', 'shop.gold_kpis'): the root is the first folder above the top package."""
    parts = list(path.relative_to(project).with_suffix("").parts)
    i = len(parts) - 1
    while i > 0 and (project.joinpath(*parts[:i]) / "__init__.py").exists():
        i -= 1
    return str(project.joinpath(*parts[:i])), ".".join(parts[i:])


def auto_cases(project, schemas):
    cases = []
    for p in files(project, "*.py"):
        if "tests" in p.parts or p.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(p.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                params = [a.arg for a in node.args.args]
                if params and all(a in schemas for a in params):
                    cases.append({"path": p, "function": node.name, "line": node.lineno,
                                  "inputs": {a: schemas[a] for a in params}})
    return cases


def line_in_function(path, start, needles):
    lines = path.read_text(errors="ignore").splitlines()
    for i in range(start, min(len(lines), start + 80)):
        if any(n in lines[i] for n in needles):
            return i + 1
        if i > start and lines[i].startswith("def "):
            break
    return start


def scan(ctx):
    cfg_path = ctx.project / "shiftleft-plans.yaml"
    if not cfg_path.exists():
        return ScanResult(NAME, notes=["plan check skipped: no shiftleft-plans.yaml with table schemas"])
    py = spark_python()
    if not py:
        return ScanResult(NAME, missing=True)
    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    schemas = cfg.get("schemas") or {}
    cases = auto_cases(ctx.project, schemas)
    for c in cfg.get("cases") or []:
        f, fn = c["function"].split(":")
        cases.append({"path": ctx.project / f, "function": fn, "line": 1,
                      "inputs": {k: schemas.get(v, v) for k, v in (c.get("inputs") or {}).items()}})
    if not cases:
        return ScanResult(NAME, notes=["plan check: no function matched the schemas in shiftleft-plans.yaml"])
    req = {"roots": sorted({module_name(c["path"], ctx.project)[0] for c in cases}), "cases": []}
    for c in cases:
        c["module"] = module_name(c["path"], ctx.project)[1]
        req["cases"].append({"module": c["module"], "function": c["function"], "inputs": c["inputs"]})
    with tempfile.TemporaryDirectory() as d:
        rq, rs = Path(d) / "req.json", Path(d) / "res.json"
        rq.write_text(json.dumps(req))
        env = {k: v for k, v in os.environ.items() if k != "SPARK_HOME"}
        r = subprocess.run([py, "-I", str(HARNESS), str(rq), str(rs)], capture_output=True, text=True, env=env, check=False)
        if not rs.exists():
            return ScanResult(NAME, notes=[f"plan harness failed: {(r.stderr or r.stdout).strip().splitlines()[-1][:160] if (r.stderr or r.stdout).strip() else 'no output'}"])
        results = json.loads(rs.read_text())
    out, notes = [], []
    max_ex = 5
    for c, res in zip(cases, results):
        file = rel(ctx.project, c["path"])
        where = f"{c['module']}.{c['function']}"
        if res.get("skipped"):
            continue
        if not res.get("ok"):
            notes.append(f"plan check could not run {where}: {res.get('error')}")
            continue
        hits = [("SL-COST-PLAN-01", res["cartesian"], "cartesian product in the plan"),
                ("SL-COST-PLAN-02", res["nested_loop"] and not res["cartesian"], "nested-loop join in the plan"),
                ("SL-COST-PLAN-03", res["python_udf"], "row-by-row Python UDF evaluation in the plan"),
                ("SL-COST-PLAN-05", res["exchanges"] > max_ex, f"{res['exchanges']} shuffles in one plan")]
        for check, hit, msg in hits:
            if hit:
                out.append(Finding(check, file, line_in_function(c["path"], c["line"], LINE_HINT[check]), NAME, check.lower(),
                                   f"{where}: {msg} (EXPLAIN on empty inputs)"))
    notes.append(f"plan check ran {sum(1 for r in results if r.get('ok'))} functions on empty tables "
                 f"({sum(1 for r in results if r.get('skipped'))} skipped: they do not return a DataFrame)")
    return ScanResult(NAME, out, notes)
