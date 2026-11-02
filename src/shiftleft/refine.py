"""Cut known noise from tool findings before gating (SL-061, learned on the first real repo).

Each rule looks at one finding plus the source around it and returns:
    None      keep it as it is
    "drop"    the tool is wrong here (a false alarm)
    a gate    the finding is right but should not stop a pull request ("report")
The binding switches rules on by name (`refine:`). Every drop or lowered gate is counted in the run notes, never silent.
"""
import ast
import collections
import fnmatch
import re
from functools import lru_cache
from pathlib import Path

from . import taint
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


IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))")


def r_platform_only_import(f, project, settings):
    """PLC0415 for modules that exist only on the platform (dlt, databricks.sdk): importing them inside the function is deliberate."""
    if f.tool_rule != "PLC0415":
        return None
    m = IMPORT.match(_line(project / f.file, f.line))
    mod = (m[1] or m[2]) if m else ""
    roots = settings.get("platform_modules") or []
    return "drop" if any(mod == r or mod.startswith(r + ".") for r in roots) else None


def r_print_in_cli(f, project, settings):
    """T201 in a command-line script (has a __main__ guard): print is its output."""
    if f.tool_rule != "T201":
        return None
    return "report" if re.search(r"""^if\s+__name__\s*==\s*["']__main__["']""", _text(project / f.file), re.M) else None


def _table_name(call):
    """Constant text of the table argument of spark.table(...) / read.table(...), with interpolations removed."""
    if not call.args:
        return ""
    a = call.args[0]
    return "".join(v.value for v in ast.walk(a) if isinstance(v, ast.Constant) and isinstance(v.value, str))


def _source_tables(node, tree, before, depth=0):
    """Table names a chain reads, following a name back through up to three earlier assignments
    (df = spark.table(...); df = df.filter(...); df.collect())."""
    names = []
    n = node
    while isinstance(n, (ast.Call, ast.Attribute, ast.Subscript)):
        if isinstance(n, ast.Call) and _chain(n)[-1:] == ["table"]:
            names.append(_table_name(n))
        n = n.func if isinstance(n, ast.Call) else n.value
    if isinstance(n, ast.Name) and depth < 3:
        assigns = [a for a in ast.walk(tree) if isinstance(a, ast.Assign) and a.lineno < before
                   and any(isinstance(t, ast.Name) and t.id == n.id for t in a.targets)]
        if assigns:
            last = max(assigns, key=lambda a: a.lineno)
            names += _source_tables(last.value, tree, last.lineno, depth + 1)
    return names


def r_collect_small_table(f, project, settings):
    """collect() of a table the team declared small (control and config tables), via `small_tables` patterns."""
    if f.check != "SL-COST-CODE-01" or not f.line:
        return None
    pats = settings.get("small_tables") or []
    tree = _tree(project / f.file)
    if not pats or not tree:
        return None
    for c in _nodes_at(tree, f.line, ast.Call):
        if _chain(c)[-1:] == ["collect"]:
            tables = [t.rsplit(".", 1)[-1] for t in _source_tables(c, tree, c.lineno)]
            return "drop" if tables and all(any(fnmatch.fnmatch(t, p) for p in pats) for t in tables) else None
    return None


_INDEX = {}


def _index(project):
    """One parse of every Python file in the project, shared by all findings of a run."""
    if project not in _INDEX:
        files = [str(p.relative_to(project)) for p in project.rglob("*.py")
                 if not any(part in (".git", ".venv", "node_modules", "target") for part in p.parts)]
        _INDEX.clear()
        _INDEX[project] = taint.Index.build(project, files)
    return _INDEX[project]


def r_sql_value_source(f, project):
    """SL-SEC-01: follow each value put into the SQL text to where it comes from (taint.py, up to two function hops).
    Untrusted input (widget, command line, environment) keeps block and names the source; data read from tables
    lowers to warn; config only lowers to report; anything not traced stays as the tool said."""
    if f.check != "SL-SEC-01" or not f.line:
        return None
    ix = _index(project)
    tree = ix.trees.get(f.file)
    if tree is None:
        return None
    stmts = _nodes_at(tree, f.line, ast.stmt)
    if not stmts:
        return None
    tracer = taint.Tracer(ix)
    labels = set()
    for expr in tracer.interpolations(stmts[0], f.file):
        labels |= tracer.sources(expr, f.file)
    v = taint.verdict(labels)
    if v == "block":
        src = sorted(f"{k} at {w}" for k, w in labels if k in taint.UNTRUSTED)
        f.message = f"untrusted input reaches the SQL text: {'; '.join(src[:3])}. Pass it as a parameter, not text"
        return None
    if v == "warn":
        src = sorted(w for k, w in labels if k == "table")
        f.message = (f"SQL text built from values read from a table ({', '.join(src[:3])}); lower risk than user "
                     "input, still pass them as parameters")
    return v


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
    "platform-only-import": r_platform_only_import,
    "print-in-cli": r_print_in_cli,
    "collect-small-table": r_collect_small_table,
    "sql-value-source": r_sql_value_source,
}
WITH_SETTINGS = {r_platform_only_import, r_print_in_cli, r_collect_small_table}


def group_per_file(findings, checks):
    """One finding per file for checks like formatting, where 100 lines out of format is one fix: run the formatter."""
    groups = collections.defaultdict(list)
    out = []
    for f in findings:
        (groups[(f.check, f.file)] if f.check in checks and f.file != "." else out).append(f)
    merged = 0
    for (_, _), fs in groups.items():
        fs.sort(key=lambda x: x.line or 0)
        first = fs[0]
        if len(fs) > 1:
            first.message = f"{len(fs)} formatting differences in this file, first: {first.message}"
            merged += len(fs) - 1
        out.append(first)
    return out, merged


def apply(findings, project: Path, enabled, settings=None):
    """Return (kept findings, notes). A lowered gate is set on the finding; the engine keeps the lower of the two."""
    settings = settings or {}
    _text.cache_clear()
    _tree.cache_clear()
    _INDEX.clear()
    rules = [(n, RULES[n]) for n in enabled if n in RULES]
    kept, dropped, lowered = [], collections.Counter(), collections.Counter()
    for f in findings:
        verdict = None
        for name, rule in rules:
            if f.file == "." or Path(f.file).is_absolute():
                break
            verdict = rule(f, project, settings) if rule in WITH_SETTINGS else rule(f, project)
            if verdict:
                break
        if verdict == "drop":
            dropped[name] += 1
            continue
        if verdict:
            f.gate = verdict
            lowered[(name, verdict)] += 1
        kept.append(f)
    kept, merged = group_per_file(kept, set(settings.get("group_per_file") or []))
    notes = [f"refine {n}: dropped {c} false alarm(s)" for n, c in sorted(dropped.items())]
    notes += [f"refine group-per-file: merged {merged} finding(s) into one per file"] if merged else []
    notes += [f"refine {n}: lowered {c} finding(s) to {g}" for (n, g), c in sorted(lowered.items())]
    unknown = [n for n in enabled if n not in RULES]
    notes += [f"refine: unknown rule {n} in the binding; ignored" for n in unknown]
    return kept, notes
