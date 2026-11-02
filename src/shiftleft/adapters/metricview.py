"""Metric view checks (SL-SEM-01..07). No outside linter exists; Databricks validates YAML spec 1.1 only inside its
own tools. We pull the YAML out of `CREATE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$`, check its shape,
and parse every expression with sqlglot (optional: without it, expression checks are skipped and noted)."""
import re

import yaml

from ..model import Finding, ScanResult
from ._util import files, rel

NAME = "metricview"
STAGES = ("commit", "pr", "nightly")
BLOCK = re.compile(r"create\s+(?:or\s+replace\s+)?view\s+(?P<name>[\w.`]+)\s+with\s+metrics\s+language\s+yaml\s+as\s+\$\$(?P<body>.*?)\$\$",
                   re.I | re.S)
MANY = {None, "", "one_to_many", "many_to_many"}
TOP_KEYS = {"version", "source", "joins", "dimensions", "measures", "filter", "comment"}


def views(project):
    """-> list of (file, view name, first line of the YAML body, parsed spec or None, error)."""
    out = []
    for p in files(project, "*.sql"):
        text = p.read_text(errors="ignore")
        for m in BLOCK.finditer(text):
            start = text[: m.start("body")].count("\n") + 1
            try:
                spec, err = yaml.safe_load(m["body"]), None
            except yaml.YAMLError as e:
                spec, err = None, str(e).splitlines()[0]
            out.append((rel(project, p), m["name"].strip("`").lower(), start, m["body"], spec, err))
    return out


def _line(body, start, needle):
    for i, ln in enumerate(body.splitlines()):
        if needle in ln:
            return start + i
    return start


def expr_tree(expr):
    try:
        import sqlglot
        return sqlglot.parse_one(expr, dialect="databricks"), None
    except ImportError:
        return None, "sqlglot not installed"
    except Exception as e:                                                  # sqlglot raises several error types
        return None, str(e).splitlines()[0][:120]


def _aggregates(tree):
    from sqlglot import expressions as exp
    return list(tree.find_all(exp.AggFunc)) if tree is not None else []


def _avg_of_ratio(tree):
    from sqlglot import expressions as exp
    return any(a.find(exp.Div) for a in tree.find_all(exp.Avg)) if tree is not None else False


def _unqualified_columns(tree, join_names):
    from sqlglot import expressions as exp
    return [c for c in tree.find_all(exp.Column) if not c.table or c.table not in join_names] if tree is not None else []


def check_view(file, name, start, body, spec, err, project_tests):
    out = []

    def add(check, needle, msg, line=None):
        out.append(Finding(check, file, line or (_line(body, start, needle) if needle else start), NAME, check.lower(), msg))

    if err or not isinstance(spec, dict):
        add("SL-SEM-01", None, f"{name}: YAML does not parse ({err or 'not a mapping'})")
        return out
    for key in sorted(set(spec) - TOP_KEYS):
        add("SL-SEM-01", f"{key}:", f"{name}: unknown field '{key}' for spec {spec.get('version')}")
    if not spec.get("source"):
        add("SL-SEM-01", None, f"{name}: no source")
    joins = spec.get("joins") or []
    join_names = {j.get("name") for j in joins if isinstance(j, dict)}
    fanout = [j for j in joins if isinstance(j, dict) and j.get("cardinality") in MANY]
    for j in fanout:
        add("SL-SEM-04", f"- name: {j.get('name')}", f"{name}: join '{j.get('name')}' has no cardinality "
            f"({j.get('cardinality') or 'not declared'}); measures from the other side can be counted more than once")
    for kind in ("dimensions", "measures"):
        for item in spec.get(kind) or []:
            if not isinstance(item, dict) or "expr" not in item or "name" not in item:
                add("SL-SEM-01", None, f"{name}: a {kind[:-1]} has no name or expr")
                continue
            tree, perr = expr_tree(str(item["expr"]))
            if perr and perr != "sqlglot not installed":
                add("SL-SEM-01", f"expr: {item['expr']}", f"{name}.{item['name']}: expression does not parse ({perr})")
            if not item.get("comment"):
                add("SL-SEM-06", f"- name: {item['name']}", f"{name}.{item['name']}: no description (comment)")
            if kind != "measures" or tree is None:
                continue
            if not _aggregates(tree):
                add("SL-SEM-02", f"expr: {item['expr']}", f"{name}.{item['name']}: measure has no aggregate")
            if _avg_of_ratio(tree):
                add("SL-SEM-03", f"expr: {item['expr']}", f"{name}.{item['name']}: average of a per-row ratio; use SUM(a) / SUM(b)")
            if fanout and _aggregates(tree) and _unqualified_columns(tree, join_names):
                add("SL-SEM-04", f"expr: {item['expr']}", f"{name}.{item['name']}: sums source columns across a join that can repeat rows")
    if name.split(".")[-1] not in project_tests:
        add("SL-SEM-07", None, f"{name}: no test with known answers refers to this metric view", line=start)
    return out


def findings(project):
    vs = views(project)
    tests = "\n".join(p.read_text(errors="ignore") for p in files(project, "*.py", "*.yml", "*.yaml", "*.sql")
                      if "tests" in p.parts)
    out = []
    for v in vs:
        out += check_view(*v, tests)
    # one definition per metric name across the repository (SL-SEM-05)
    defs = {}
    for file, name, start, body, spec, _ in vs:
        for m in (spec or {}).get("measures") or [] if isinstance(spec, dict) else []:
            if isinstance(m, dict) and "name" in m:
                defs.setdefault(m["name"].lower(), []).append((file, name, start, body, re.sub(r"\s+", " ", str(m.get("expr"))).strip().lower(), m["name"]))
    for mname, ds in defs.items():
        if len({d[4] for d in ds}) > 1:
            for file, vname, start, body, _, orig in ds:
                others = ", ".join(sorted({d[1] for d in ds if d[1] != vname}))
                out.append(Finding("SL-SEM-05", file, _line(body, start, f"- name: {orig}"), NAME, "sl-sem-05",
                                   f"{vname}.{orig} is defined differently in {others}"))
    return out


def scan(ctx):
    notes = []
    try:
        import sqlglot  # noqa: F401
    except ImportError:
        notes.append("metricview: sqlglot not installed, so expression checks (SEM-02, -03, -04) did not run")
    return ScanResult(NAME, findings(ctx.project), notes)
