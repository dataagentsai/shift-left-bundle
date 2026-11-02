"""Cut known noise from tool findings before gating (SL-061, learned on the first real repo).

Each rule looks at one finding plus the source around it and returns:
    None      keep it as it is
    "drop"    the tool is wrong here (a false alarm)
    a gate    the finding is right but should not stop a pull request ("report")
The binding switches rules on by name (`refine:`). Every drop or lowered gate is counted in the run notes, never silent.
"""
import ast
import collections
import re
from functools import lru_cache
from pathlib import Path

from .adapters._notebooks import source_sql_cells

NB_HEADER = "# Databricks notebook source"
RUN = re.compile(r"^\s*(?:#\s*MAGIC\s+)?%run\s+(\S+)")
DDL = re.compile(r"^\s*(CREATE|DROP|ALTER|GRANT|REVOKE|COMMENT|USE)\b", re.I)
ONE_ROW_BREAKERS = {"groupBy", "groupby", "rollup", "cube", "pivot", "explode"}


# ---------------------------------------------------------------- source helpers (cached per run)

@lru_cache(maxsize=512)
def _text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


@lru_cache(maxsize=512)
def _tree(path: Path):
    try:
        return ast.parse(_text(path))
    except (SyntaxError, ValueError):
        return None


def _is_notebook(path: Path) -> bool:
    return path.suffix == ".ipynb" or _text(path).startswith(NB_HEADER)


def _line(path: Path, n):
    lines = _text(path).splitlines()
    return lines[n - 1] if n and 0 < n <= len(lines) else ""


def _nodes_at(tree, line, kind):
    """Nodes of a kind whose span covers the line, smallest span first."""
    hits = [n for n in ast.walk(tree) if isinstance(n, kind) and n.lineno <= line <= (n.end_lineno or n.lineno)]
    return sorted(hits, key=lambda n: (n.end_lineno or n.lineno) - n.lineno)


def _chain(node):
    out = []
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Name):
            return [node.id, *out[::-1]]
        else:
            return out[::-1]


def _defined_names(tree):
    names = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                names |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in n.names}
    return names


def run_target_names(path: Path, seen=None):
    """Names a notebook gets from the notebooks it pulls in with %run (followed transitively)."""
    seen = seen if seen is not None else set()
    names = set()
    for ln in _text(path).splitlines():
        m = RUN.match(ln)
        if not m:
            continue
        target = (path.parent / m[1]).resolve()
        target = target if target.suffix == ".py" else target.with_suffix(".py")
        if target in seen or not target.exists():
            continue
        seen.add(target)
        tree = _tree(target)
        if tree:
            names |= _defined_names(tree)
        names |= run_target_names(target, seen)
    return names


def _constant_like(expr, config_names=frozenset()) -> bool:
    """An interpolated value that is configuration, not data: an ALL_CAPS name, or a call or attribute on one,
    or a loop variable that only walks over such values (config_names)."""
    root = _chain(expr)
    if root and (root[0].replace("_", "").isupper() or root[0] in config_names):
        calls = [n for n in ast.walk(expr) if isinstance(n, ast.Call)]
        return all(isinstance(a, ast.Constant) or _constant_like(a, config_names) for c in calls for a in c.args)
    return isinstance(expr, ast.Constant)


def _config_loop_names(tree, line):
    """Loop variables of enclosing `for x in (CONFIG.a, CONFIG.b)` loops."""
    names = set()
    for loop in _nodes_at(tree, line, ast.For):
        if isinstance(loop.target, ast.Name) and isinstance(loop.iter, (ast.Tuple, ast.List)) \
                and all(_constant_like(e) for e in loop.iter.elts):
            names.add(loop.target.id)
    return frozenset(names)


# ---------------------------------------------------------------- rules: (finding, project) -> None | "drop" | gate

def r_run_target_names(f, project):
    """F821 'undefined name' for a name that comes from a %run notebook."""
    if f.tool_rule != "F821":
        return None
    m = re.search(r"`([^`]+)`", f.message)
    return "drop" if m and m[1] in run_target_names(project / f.file) else None


def r_sql_identifiers_only(f, project):
    """SQL built with f-strings that insert only configuration (table names), never values: report, not block.
    Also moves the finding to the start of the statement, so two tools on one statement count once."""
    if f.check != "SL-SEC-01" or not f.line:
        return None
    tree = _tree(project / f.file)
    if not tree:
        return None
    calls = [c for c in _nodes_at(tree, f.line, ast.Call) if _chain(c)[-1:] == ["sql"]]
    if not calls:
        return None
    call = calls[0]
    f.line = call.lineno
    parts = [v.value for s in ast.walk(call) if isinstance(s, ast.JoinedStr)
             for v in s.values if isinstance(v, ast.FormattedValue)]
    config = _config_loop_names(tree, call.lineno)
    return "report" if parts and all(_constant_like(p, config) for p in parts) else None


def r_random_not_security(f, project):
    """S311: random numbers in data code are for samples and synthetic data; keep visible, do not block or warn."""
    return "report" if f.tool_rule == "S311" else None


def r_print_in_notebook(f, project):
    """T201: a notebook's print is its output; keep the warning for modules."""
    return "report" if f.tool_rule == "T201" and _is_notebook(project / f.file) else None


def r_collect_one_row(f, project):
    """collect() after a whole-table aggregate returns one row; no limit needed."""
    if f.check != "SL-COST-CODE-01" or not f.line:
        return None
    tree = _tree(project / f.file)
    if not tree:
        return None
    for c in _nodes_at(tree, f.line, ast.Call):
        ch = _chain(c)
        if ch[-1:] == ["collect"]:
            return "drop" if "agg" in ch and not ONE_ROW_BREAKERS & set(ch) else None
    return None


def r_merge_builder_chain(f, project):
    """A Delta merge is written as one builder chain (forName.alias.merge.whenMatched...execute); not too long."""
    if f.check != "SL-CLEAN-25":
        return None
    return "drop" if "DeltaTable.for" in _line(project / f.file, f.line) else None


def r_display_cell_sort(f, project):
    """ORDER BY with no LIMIT in a notebook %sql cell that only selects: a sorted display, not a pipeline step."""
    if f.check != "SL-COST-CODE-17" or not f.line:
        return None
    for start, body in source_sql_cells(project / f.file):
        if start - 1 <= f.line <= start + body.count("\n"):
            code = re.sub(r"--[^\n]*|/\*.*?\*/", "", body, flags=re.S)        # leading comments are common
            return "report" if re.match(r"^\s*(SELECT|WITH)\b", code, re.I) else None
    return None


def r_ddl_in_loop(f, project):
    """spark.sql in a loop that only runs DDL (CREATE SCHEMA IF NOT EXISTS ...) costs nothing."""
    if f.tool_rule != "loop_calling_spark_sql" or not f.line:
        return None
    tree = _tree(project / f.file)
    loops = _nodes_at(tree, f.line, (ast.For, ast.While)) if tree else []
    if not loops:
        return None
    sqls = [c for c in ast.walk(loops[0]) if isinstance(c, ast.Call) and _chain(c)[-1:] == ["sql"] and c.args]
    texts = ["".join(v.value for v in ast.walk(c.args[0]) if isinstance(v, ast.Constant) and isinstance(v.value, str))
             for c in sqls]
    return "drop" if texts and all(DDL.match(t) for t in texts) else None


def r_display_is_output(f, project):
    """display(...) in a notebook is the notebook's output, not a discarded action."""
    return "drop" if f.check == "SL-COST-CODE-11" and "inside display(" in f.message else None


def r_markdown_unicode(f, project):
    """RUF001-003 on notebook markdown lines (# MAGIC): typographic dashes and signs in prose are fine."""
    if f.tool_rule not in ("RUF001", "RUF002", "RUF003"):
        return None
    return "drop" if _line(project / f.file, f.line).lstrip().startswith("# MAGIC") else None


RULES = {
    "run-target-names": r_run_target_names,
    "sql-identifiers-only": r_sql_identifiers_only,
    "random-not-security": r_random_not_security,
    "print-in-notebook": r_print_in_notebook,
    "collect-one-row": r_collect_one_row,
    "merge-builder-chain": r_merge_builder_chain,
    "display-cell-sort": r_display_cell_sort,
    "ddl-in-loop": r_ddl_in_loop,
    "display-is-output": r_display_is_output,
    "markdown-unicode": r_markdown_unicode,
}


def apply(findings, project: Path, enabled):
    """Return (kept findings, notes). A lowered gate is set on the finding; the engine keeps the lower of the two."""
    _text.cache_clear()
    _tree.cache_clear()
    rules = [(n, RULES[n]) for n in enabled if n in RULES]
    kept, dropped, lowered = [], collections.Counter(), collections.Counter()
    for f in findings:
        verdict = None
        for name, rule in rules:
            if f.file == "." or Path(f.file).is_absolute():
                break
            verdict = rule(f, project)
            if verdict:
                break
        if verdict == "drop":
            dropped[name] += 1
            continue
        if verdict:
            f.gate = verdict
            lowered[name] += 1
        kept.append(f)
    notes = [f"refine {n}: dropped {c} false alarm(s)" for n, c in sorted(dropped.items())]
    notes += [f"refine {n}: lowered {c} finding(s) to report" for n, c in sorted(lowered.items())]
    unknown = [n for n in enabled if n not in RULES]
    notes += [f"refine: unknown rule {n} in the binding; ignored" for n in unknown]
    return kept, notes
