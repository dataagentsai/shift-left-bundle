"""Our own SQL rules: materialized views and permission grants.

v0 uses text patterns, not the sqlglot syntax tree: sqlglot (and so CostLens) cannot parse Databricks'
`SCHEDULE EVERY ...` clause or metric-view YAML. Moving these rules onto the tree, with the schedule clause cut out
first, comes with the SQL complexity score in Tier 5 (SL-CPLX-07). The adapter keeps the name `sqlglot` because the
binding assigns these checks to it.
"""
import re

from ..model import Finding, ScanResult
from ._notebooks import sql_cells
from ._util import files, line_of, rel

NAME = "sqlglot"
STAGES = ("commit", "pr", "nightly", "predeploy")
MV = re.compile(r"create\s+(?:or\s+replace\s+)?materialized\s+view\s+(?P<name>[\w.`]+)", re.I)
SCHEDULE = re.compile(r"schedule\s+every\s+(?P<n>\d+)\s+(?P<unit>minute|minutes|hour|hours|day|days|week|weeks)", re.I)
NONDET = ("rand(", "randn(", "uuid(", "random(", "shuffle(")
GRANT = re.compile(r"grant\s+all\b|to\s+`?(account users|users|everyone|public)`?", re.I)


def mv_defs(project):
    """name -> (file, line, query text) for every materialized view in .sql files."""
    out = {}
    for p in files(project, "*.sql"):
        text = p.read_text(errors="ignore")
        for m in MV.finditer(text):
            name = m["name"].strip("`").lower()
            out[name] = (rel(project, p), text[: m.start()].count("\n") + 1, text[m.start():])
    return out


def mv_findings(project, gates):
    defs, out = mv_defs(project), []
    max_depth = gates.get("materialized_views", {}).get("chain_depth_max", 2)

    def deps(q):
        return {n for n in defs if re.search(rf"\b(from|join)\s+{re.escape(n)}\b", q, re.I)}

    def depth(n, seen=()):
        return 1 + max((depth(d, (*seen, n)) for d in deps(defs[n][2].split(" as ", 1)[-1]) if d not in seen), default=0)

    for name, (file, line, q) in defs.items():
        low = q.lower()
        for fn in NONDET:
            if fn in low:
                out.append(Finding("SL-COST-CODE-22", file, line_of(project, file, fn) or line, NAME, "mv-nondeterministic",
                                   f"{name} uses {fn[:-1]}(): every refresh recomputes everything"))
                out.append(Finding("SL-COST-CONFIG-09", file, line_of(project, file, fn) or line, NAME, "mv-not-incremental",
                                   f"{name} is not eligible for incremental refresh ({fn[:-1]}); confirm with EXPLAIN CREATE MATERIALIZED VIEW"))
                break
        s = SCHEDULE.search(q)
        if s and s["unit"].lower().startswith("minute") and int(s["n"]) < 60:
            out.append(Finding("SL-COST-CONFIG-06", file, line_of(project, file, s.group(0)), NAME, "mv-schedule",
                               f"{name} refreshes every {s['n']} minutes; check the freshness the consumers need"))
        d = depth(name)
        if d > max_depth:
            out.append(Finding("SL-COST-CODE-23", file, line, NAME, "mv-chain", f"{name} is {d} materialized views deep (limit {max_depth})"))
    return out


def grant_findings(project):
    out = []
    for p in files(project, "*.sql"):
        file = rel(project, p)
        for i, ln in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if ln.strip().lower().startswith("grant") and GRANT.search(ln):
                out.append(Finding("SL-SEC-08", file, i, NAME, "grant-broad", "grant of all privileges, or to everyone"))
    for nb in files(project, "*.py", "*.ipynb"):
        for start, sql in sql_cells(nb):
            for i, ln in enumerate(sql.splitlines()):
                if ln.strip().lower().startswith("grant") and GRANT.search(ln):
                    out.append(Finding("SL-SEC-08", rel(project, nb), start + i, NAME, "grant-broad", "grant of all privileges, or to everyone"))
    return out


def scan(ctx):
    return ScanResult(NAME, mv_findings(ctx.project, ctx.gates) + grant_findings(ctx.project))
