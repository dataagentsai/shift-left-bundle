"""Our own pattern rules (SL-064): nine checks no adopted tool covers, read from Python syntax trees and plain text.

    SL-SEC-06    a secret is printed, logged or displayed
    SL-SEC-07    personal columns are shown or displayed (report only)
    SL-TEST-04   unit tests reach a remote engine or a shared table
    SL-TEST-06   a test's only assertions are on row counts
    SL-CLEAN-08  a notebook defines functions instead of calling them from modules
    SL-CLEAN-14  a column is read as an attribute of a dataset variable
    SL-CLEAN-23  a notebook pulls in code with %run or dbutils.notebook.run
    SL-CLEAN-26  a long condition is written inline in filter / where / when
    SL-DEP-05    the test Spark or Python version does not match the deploy runtime

Settings live in the binding under `patterns:` (personal column names, condition limit, runtime table).
Notebooks: Databricks source .py files are plain Python; .ipynb code cells are parsed one by one and the cell
number is reported as the line (as the notebook SQL extractor does).
"""
import ast
import json
import re

from ..model import Finding, ScanResult
from ._notebooks import sql_cells
from ._util import files, rel

NAME = "patterns"
STAGES = ("commit", "pr", "nightly")

NB_HEADER = "# Databricks notebook source"
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
DF_PROPERTIES = {"columns", "dtypes", "schema", "rdd", "na", "stat", "write", "writeStream", "storageLevel",
                 "isStreaming", "sparkSession", "sql_ctx"}
CONDITION_CALLS = {"filter", "where", "when"}
RUN_MAGIC = re.compile(r"^\s*(#\s*MAGIC\s+)?%run\s")
NB_RUN = re.compile(r"dbutils\.notebook\.run\(")
SPARK_VERSION = re.compile(r"spark_version:\s*[\"']?(\d+\.\d+)\.")
REQ_LINE = re.compile(r"^\s*[\"']?(pyspark|databricks-connect)\s*(\[[^\]]*\])?\s*([<>=!~][^\"';#]*)?", re.I)
EXACT = re.compile(r"(?:==|~=)\s*(\d+)\.(\d+)")


# ---------------------------------------------------------------- reading files

def _is_notebook(path, text):
    return path.suffix == ".ipynb" or text.startswith(NB_HEADER)


def _is_test(rel_path):
    name = rel_path.rsplit("/", 1)[-1]
    return rel_path.startswith("tests/") or "/tests/" in rel_path or name.startswith("test_") or name == "conftest.py"


def _python_units(path):
    """Yield (tree, line_offset_or_cell, text). Source files give one unit; .ipynb gives one per code cell."""
    text = path.read_text(errors="ignore")
    if path.suffix != ".ipynb":
        try:
            yield ast.parse(text), None, text
        except SyntaxError:
            return
        return
    try:
        cells = json.loads(text).get("cells", [])
    except ValueError:
        return
    for n, cell in enumerate(cells, 1):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        body = "\n".join("" if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines())
        try:
            yield ast.parse(body), n, src
        except SyntaxError:
            continue


def _line(node, cell):
    return cell if cell is not None else node.lineno


# ---------------------------------------------------------------- small syntax helpers

def _attr_chain(node):
    """Names along a call chain, receiver first: spark.read.table(...) -> ['spark', 'read', 'table']."""
    out = []
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Name):
            out.append(node.id)
            return out[::-1]
        else:
            return out[::-1]


def _is_secret_get(node):
    return isinstance(node, ast.Call) and _attr_chain(node)[-2:] == ["secrets", "get"]


def _strings(node):
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _is_personal(col, tokens):
    c = col.lower().strip("`")
    return any(c == t or c.endswith("_" + t) or c.startswith(t + "_") for t in tokens)


def _condition_leaves(node):
    """Count conditions joined by & or | (and Python and/or)."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
        return _condition_leaves(node.left) + _condition_leaves(node.right)
    if isinstance(node, ast.BoolOp):
        return sum(_condition_leaves(v) for v in node.values)
    return 1


def _is_count_call(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "count" \
        and not node.args


def _count_only_assert(a):
    t = a.test
    if not isinstance(t, ast.Compare):
        return False
    sides = [t.left, *t.comparators]
    return any(_is_count_call(s) for s in sides) or any(
        isinstance(s, ast.Call) and isinstance(s.func, ast.Name) and s.func.id == "len" for s in sides)


# ---------------------------------------------------------------- rules over one Python unit

def _rules_python(tree, cell, rp, is_nb, is_test, cfg):
    out = []
    personal = [t.lower() for t in cfg.get("personal_columns") or []]
    limit = int(cfg.get("max_inline_conditions", 3))

    def add(check, node, rule, msg):
        out.append(Finding(check, rp, _line(node, cell), NAME, rule, msg))

    secrets = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) and _is_secret_get(n.value)
               for t in n.targets if isinstance(t, ast.Name)}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _attr_chain(node)
        last = chain[-1] if chain else ""
        func = node.func

        # SL-SEC-06: print / display / log of a secret
        is_print = isinstance(func, ast.Name) and func.id in ("print", "display")
        is_log = isinstance(func, ast.Attribute) and func.attr in LOG_METHODS and "log" in ".".join(chain[:-1]).lower()
        if is_print or is_log:
            args = [*node.args, *(k.value for k in node.keywords)]
            hit = any(isinstance(n, ast.Name) and n.id in secrets or _is_secret_get(n) for a in args for n in ast.walk(a))
            if hit:
                add("SL-SEC-06", node, "sl-secret-printed", "a secret read from the secret store is printed or logged")

        # SL-SEC-07: personal columns shown
        target = None
        if isinstance(func, ast.Name) and func.id == "display" and node.args:
            target = node.args[0]
        elif isinstance(func, ast.Attribute) and func.attr == "show":
            target = func.value
        if target is not None and personal:
            cols = [s for s in _strings(target) if _is_personal(s, personal)]
            if cols:
                add("SL-SEC-07", node, "sl-pii-sample-logged",
                    f"personal columns shown on screen or in logs: {', '.join(sorted(set(cols)))}")

        # SL-CLEAN-14: column as attribute of a dataset variable, inside join / filter / where / select
        if isinstance(func, ast.Attribute) and last in ("join", "filter", "where", "select", "withColumn", "groupBy",
                                                         "orderBy", "sort"):
            dfs = {chain[0]} if chain else set()
            if last == "join" and node.args and isinstance(node.args[0], ast.Name):
                dfs.add(node.args[0].id)
            called = {id(n.func) for a in node.args for n in ast.walk(a) if isinstance(n, ast.Call)}
            for a in node.args[1:] if last == "join" else node.args:
                for n in ast.walk(a):
                    if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in dfs
                            and n.attr not in DF_PROPERTIES and id(n) not in called):
                        add("SL-CLEAN-14", n, "sl-df-attribute-column",
                            f"column '{n.attr}' read as {n.value.id}.{n.attr}; refer to it by name (F.col)")
                        break

        # SL-CLEAN-26: long inline condition
        if last in CONDITION_CALLS and node.args:
            k = _condition_leaves(node.args[0])
            if k > limit:
                add("SL-CLEAN-26", node, "sl-inline-complex-condition",
                    f"{k} conditions written inline in {last}(); name the condition (limit {limit})")

        # SL-TEST-04: tests that need a remote engine or shared tables
        if is_test:
            if last == "remote" and "builder" in chain:
                add("SL-TEST-04", node, "offline-tests", "test session connects to a remote workspace")
            elif last == "master" and node.args and isinstance(node.args[0], ast.Constant) \
                    and not str(node.args[0].value).startswith("local"):
                add("SL-TEST-04", node, "offline-tests", f"test session uses cluster {node.args[0].value!r}")
            elif last == "table" and node.args and isinstance(node.args[0], ast.Constant) \
                    and "." in str(node.args[0].value):
                add("SL-TEST-04", node, "offline-tests", f"test reads shared table {node.args[0].value!r}")

    out += _rules_pyspark(tree, cell, rp, cfg)

    if is_test:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("databricks.connect"):
                add("SL-TEST-04", node, "offline-tests", "tests import Databricks Connect; they need a workspace")
            # SL-TEST-06: count-only assertions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
                if asserts and all(_count_only_assert(a) for a in asserts):
                    add("SL-TEST-06", asserts[0], "sl-test-count-only",
                        f"{node.name} only checks a row count; compare the rows themselves")

    # SL-CLEAN-08: functions defined in a notebook (one finding per notebook unit)
    if is_nb:
        defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        if defs:
            names = ", ".join(d.name for d in defs[:5])
            add("SL-CLEAN-08", defs[0], "sl-thin-notebooks",
                f"notebook defines {len(defs)} function(s) or class(es) ({names}); move them into a module")
    return out


AGGREGATES = {"sum", "avg", "mean", "min", "max", "count", "countDistinct", "count_distinct", "first", "last",
              "collect_list", "collect_set", "stddev", "stddev_samp", "stddev_pop", "variance", "var_samp", "var_pop",
              "sum_distinct", "sumDistinct", "approx_count_distinct", "product", "max_by", "min_by", "any_value",
              "median", "percentile_approx", "array_agg"}
FRAME_CALLS = {"rowsBetween", "rangeBetween"}


def _rules_pyspark(tree, cell, rp, cfg):
    """SL-065 (from the Sonar comparison): typeless nulls, window frames, join type, whole-row dedupe, withColumn chains."""
    out = []
    chain_max = int(cfg.get("max_chained_withcolumn", 3))
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}

    def add(check, node, rule, msg):
        out.append(Finding(check, rp, _line(node, cell), NAME, rule, msg))

    # window specs by name; a spec built from another spec inherits its calls
    specs = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and isinstance(n.value, ast.Call):
            ch = _attr_chain(n.value)
            if ch and ch[0] == "Window":
                specs[n.targets[0].id] = ch
            elif ch and ch[0] in specs:
                specs[n.targets[0].id] = specs[ch[0]] + ch[1:]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        ch = _attr_chain(node)
        last = ch[-1] if ch else ""
        parent = parents.get(node)

        # SL-CLEAN-29: lit(None) with no type, where it becomes a column
        if last == "lit" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant) and node.args[0].value is None:
            pc = parents.get(parent)
            as_value = isinstance(parent, ast.Call) and _attr_chain(parent)[-1:] == ["withColumn"] \
                and len(parent.args) > 1 and parent.args[1] is node
            as_alias = isinstance(parent, ast.Attribute) and parent.attr == "alias"
            in_withcolumns = isinstance(parent, ast.Dict) and isinstance(pc, ast.Call) \
                and _attr_chain(pc)[-1:] == ["withColumns"]
            if as_value or as_alias or in_withcolumns:
                add("SL-CLEAN-29", node, "sl-null-no-type", "null column added with no type; cast it, e.g. F.lit(None).cast('string')")

        # SL-CLEAN-30: aggregate over an ordered window with no frame
        if last == "over" and node.args and isinstance(node.func, ast.Attribute):
            agg = _attr_chain(node.func.value)[-1:] or [""]
            w = node.args[0]
            spec = specs.get(w.id) if isinstance(w, ast.Name) else (_attr_chain(w) if isinstance(w, ast.Call) else None)
            if agg[0] in AGGREGATES and spec and "orderBy" in spec and not FRAME_CALLS & set(spec):
                add("SL-CLEAN-30", node, "sl-window-no-frame",
                    f"{agg[0]}() over an ordered window with no frame is a running total; state rowsBetween or rangeBetween")
            # SL-COST-CODE-25: ordered window with no partition (every row goes through one task)
            if spec and spec[0] == "Window" and "orderBy" in spec and "partitionBy" not in spec:
                add("SL-COST-CODE-25", node, "sl-window-no-partition",
                    f"{agg[0] or 'function'}() over a window ordered with no partitionBy: every row goes through one task")

        # SL-CLEAN-31: join type left to the default
        if last == "join" and "path" not in ch and isinstance(node.func, ast.Attribute) \
                and not isinstance(node.func.value, ast.Constant):
            kws = {k.arg for k in node.keywords}
            has_on = len(node.args) >= 2 or "on" in kws
            if has_on and len(node.args) < 3 and "how" not in kws:
                add("SL-CLEAN-31", node, "sl-join-no-how", "join type not stated; pass how= (inner, left, ...)")

        # SL-CLEAN-32: dedupe on every column
        if last in ("dropDuplicates", "drop_duplicates") and not node.args and not node.keywords:
            add("SL-CLEAN-32", node, "sl-dedupe-all-columns", f"{last}() with no columns de-duplicates whole rows; name the key")

        # SL-COST-CODE-24: long withColumn chain, reported once at the top of the chain
        top = not (isinstance(parent, ast.Attribute) and parent.value is node)
        k = ch.count("withColumn")
        if top and k > chain_max:
            add("SL-COST-CODE-24", node, "sl-chained-withcolumn",
                f"{k} withColumn calls in one chain; add them in one withColumns or select (limit {chain_max})")
    return out


def _rules_text(text, rp, is_nb, cell):
    """SL-CLEAN-23: %run and dbutils.notebook.run in notebooks."""
    if not is_nb:
        return []
    out = []
    for i, ln in enumerate(text.splitlines(), 1):
        if RUN_MAGIC.search(ln):
            out.append(Finding("SL-CLEAN-23", rp, cell or i, NAME, "sl-notebook-run-chain",
                               "%run pulls another notebook's definitions in; import a module instead"))
        elif NB_RUN.search(ln):
            out.append(Finding("SL-CLEAN-23", rp, cell or i, NAME, "sl-notebook-run-chain",
                               "dbutils.notebook.run chains notebooks; call module functions or use job tasks"))
    return out


# ---------------------------------------------------------------- SL-DEP-05: runtime match

def runtime_versions(project):
    """Databricks Runtime versions (major.minor) named in the bundle config."""
    found = set()
    for p in files(project, "databricks.yml", "databricks.yaml", "*.yml", "*.yaml"):
        r = rel(project, p)
        if r.startswith(("databricks.y", "resources/")):
            found |= set(SPARK_VERSION.findall(p.read_text(errors="ignore")))
    return sorted(found)


def runtime_findings(project, cfg):
    table = cfg.get("runtimes") or {}
    versions = [v for v in runtime_versions(project) if v in table]
    if not versions:
        return []
    want = {v: table[v] for v in versions}
    sparks = sorted({str(w["spark"]) for w in want.values()})
    out, pinned = [], False
    for p in files(project, "requirements*.txt", "pyproject.toml", "environment*.yml"):
        rp = rel(project, p)
        for i, ln in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            m = REQ_LINE.match(ln)
            if not m:
                continue
            pinned = True
            lib, spec = m[1].lower(), (m[3] or "").strip()
            exact = EXACT.search(spec)
            got = f"{exact[1]}.{exact[2]}" if exact else None
            ok = sparks if lib == "pyspark" else versions
            if got not in ok:
                need = " or ".join(ok)
                out.append(Finding("SL-DEP-05", rp, i, NAME, "sl-runtime-match",
                                   f"{lib} '{spec or 'any'}' does not pin {need}, the version of the deploy runtime "
                                   f"({', '.join(versions)})"))
    pyv = project / ".python-version"
    if pyv.exists():
        got = ".".join(pyv.read_text().strip().split(".")[:2])
        pys = sorted({str(w["python"]) for w in want.values()})
        if got not in pys:
            out.append(Finding("SL-DEP-05", ".python-version", 1, NAME, "sl-runtime-match",
                               f"tests run on Python {got}; the deploy runtime uses {' or '.join(pys)}"))
    if not pinned and (project / "tests").exists():
        out.append(Finding("SL-DEP-05", ".", None, NAME, "sl-runtime-match",
                           f"no pyspark or databricks-connect pin; tests should use Spark {' or '.join(sparks)}"))
    return out


# ---------------------------------------------------------------- entry point

def scan(ctx):
    cfg = ctx.binding.get("patterns") or {}
    out, notes = [], []
    for p in files(ctx.project, "*.py", "*.ipynb"):
        rp = rel(ctx.project, p)
        head = p.read_text(errors="ignore")[:200]
        is_nb, is_test = _is_notebook(p, head), _is_test(rp)
        parsed = False
        for tree, cell, text in _python_units(p):
            parsed = True
            out += _rules_python(tree, cell, rp, is_nb, is_test, cfg)
            out += _rules_text(text, rp, is_nb, cell)
        if not parsed and p.suffix == ".py":
            notes.append(f"{rp}: could not parse")
    out += runtime_findings(ctx.project, cfg)
    out += sql_window_findings(ctx.project)
    return ScanResult(NAME, out, notes)


SQL_OVER_ORDER = re.compile(r"\bOVER\s*\(\s*ORDER\s+BY\b", re.I)


def _sql_window_hits(sql):
    """Line offsets (0-based) of OVER (ORDER BY ...) with no PARTITION BY, comments ignored."""
    code = re.sub(r"--[^\n]*", lambda m: " " * len(m[0]), sql)
    code = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m[0]), code, flags=re.S)
    return [code.count("\n", 0, m.start()) for m in SQL_OVER_ORDER.finditer(code)]


def sql_window_findings(project):
    """SL-COST-CODE-25 in SQL: .sql files and notebook %sql cells."""
    out = []
    msg = "window ordered with no PARTITION BY: every row goes through one task"
    for p in files(project, "*.sql"):
        for k in _sql_window_hits(p.read_text(errors="ignore")):
            out.append(Finding("SL-COST-CODE-25", rel(project, p), k + 1, NAME, "sl-window-no-partition", msg))
    for p in files(project, "*.py", "*.ipynb"):
        for start, body in sql_cells(p):
            for k in _sql_window_hits(body):
                line = start if p.suffix == ".ipynb" else start + k
                out.append(Finding("SL-COST-CODE-25", rel(project, p), line, NAME, "sl-window-no-partition", msg))
    return out
