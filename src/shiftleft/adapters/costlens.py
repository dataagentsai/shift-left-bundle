"""CostLens (CostSherlock) oss-core cost rules: SQL, Python code structure, notebooks, bundle orchestration.

Optional: if costlens-core is not installed, the report says so and these checks are skipped.
Only this module imports costlens. Rule names map to checks through the binding's `checks` entries
whose tool is `costlens`; rules with no catalog check are listed as notes, so gaps are visible.
"""
import tempfile
from pathlib import Path

import yaml

from ..model import Finding, ScanResult
from ._notebooks import sql_cells
from ._util import files, line_of, rel

NAME = "costlens"
STAGES = ("commit", "pr", "nightly", "predeploy")

# CostLens SQL findings carry no line; find the line by the construct the rule is about.
KEYWORD = {"select_star": "select *", "select_distinct_star": "select distinct *", "union_instead_of_union_all": "union",
           "not_in_with_subquery": "not in (", "cross_join": "cross join", "delete_without_where": "delete from",
           "update_without_where": "update ", "ordering_without_limit": "order by", "like_with_leading_wildcard": "like '%",
           "merge_without_partition_predicate": "merge into", "function_on_partition_column": "where",
           "count_distinct_unbounded": "count(distinct"}


def rule_map(binding):
    out = {}
    for cid, e in (binding.get("checks") or {}).items():
        if isinstance(e, dict) and e.get("tool") == NAME:
            for r in e.get("rules") or []:
                out.setdefault(r, cid)
    return out


def _line(project, file, f, offset=None, text=None):
    loc = f.location or ""
    if ":L" in loc:
        try:
            return int(loc.rsplit(":L", 1)[1].split(":")[0])
        except ValueError:
            pass
    kw = KEYWORD.get(f.rule_name)
    if kw and text is not None and offset is not None:                     # inside an extracted cell
        for i, ln in enumerate(text.splitlines()):
            if kw in ln.lower():
                return offset + i
        return offset
    return line_of(project, file, kw) if kw else None


def merged_bundle(project: Path):
    """databricks.yml with `include:` files merged in, because CostLens reads only the root file."""
    root = project / "databricks.yml"
    doc = yaml.safe_load(root.read_text()) or {}
    res = doc.setdefault("resources", {})
    for pat in doc.get("include") or []:
        for p in sorted(project.glob(pat)):
            for kind, items in ((yaml.safe_load(p.read_text()) or {}).get("resources") or {}).items():
                res.setdefault(kind, {}).update(items or {})
    return doc


RULE_KEY = {"job_on_existing_cluster": "existing_cluster_id", "cron_too_frequent": "quartz_cron_expression",
            "dlt_continuous_for_batch_workload": "continuous:", "oversized_autoscale_max": "max_workers"}


def bundle_line(project, finding_target, kinds=("resources/*.yml", "resources/*.yaml", "databricks.yml"), rule=None):
    """Find the bundle file and line of the resource a finding names (targets look like `job:daily_load/task:load`),
    then, for rules about one setting, the line of that setting inside the resource."""
    import re
    m = re.match(r"(?:job|pipeline|cluster|warehouse):([\w-]+)", finding_target or "")
    name = m.group(1) if m else ""
    for pat in kinds:
        for p in sorted(project.glob(pat)):
            ln = line_of(project, rel(project, p), f"{name}:") if name else None
            if ln:
                key = RULE_KEY.get(rule)
                if key:
                    lines = p.read_text(errors="ignore").splitlines()
                    for i in range(ln, min(len(lines), ln + 40)):
                        if key in lines[i]:
                            return rel(project, p), i + 1
                return rel(project, p), ln
    return "databricks.yml", None


def scan(ctx):
    try:
        from costlens.cli import _findings_for_file, _lint_snippets  # noqa: F401
        from costlens.core.code_structure import CodeStructureEngine
        from costlens.core.orchestration.rules import OrchestrationEngine
        from costlens.core.sql_lint import SqlLintEngine
    except ImportError:
        return ScanResult(NAME, missing=True)
    import logging
    logging.getLogger("sqlglot").setLevel(logging.ERROR)                   # it warns on every MV and metric view
    engines = (SqlLintEngine(), CodeStructureEngine(), OrchestrationEngine())
    rmap, out, notes = rule_map(ctx.binding), [], set()

    def add(f, file, line):
        cid = rmap.get(f.rule_name)
        if not cid:
            notes.add(f"costlens rule {f.rule_name} has no catalog check yet")
            return
        out.append(Finding(cid, file, line, NAME, f.rule_name, f.message))

    for p in files(ctx.project, "*.sql", "*.py", "*.ipynb"):
        file = rel(ctx.project, p)
        try:
            found = _findings_for_file(p, *engines)
        except Exception as e:                                              # one bad file must not stop the run
            notes.add(f"{file}: costlens could not read it ({type(e).__name__})")
            continue
        for f in found:
            add(f, file, _line(ctx.project, file, f))
        for start, sql in sql_cells(p):
            for f in engines[0].lint(sql).findings:
                add(f, file, _line(ctx.project, file, f, offset=start, text=sql))
    if (ctx.project / "databricks.yml").exists():
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "databricks.yml"
            tmp.write_text(yaml.safe_dump(merged_bundle(ctx.project)))
            for f in _findings_for_file(tmp, *engines):
                file, line = bundle_line(ctx.project, f.target, rule=f.rule_name)
                add(f, file, line)
    return ScanResult(NAME, out, sorted(notes))
