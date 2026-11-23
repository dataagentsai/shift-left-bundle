"""pyspark-antipattern: only the rules other tools lack are adopted (binding pyspark_antipattern_map).
It has no JSON output; its text report is parsed. It writes the report to stderr."""
import ast
import re
from pathlib import Path

from ..model import Finding, ScanResult
from ._util import rel, run, which

NAME = "pyspark-antipattern"
STAGES = ("commit", "pr", "nightly")
ITEM = re.compile(r"error\[(?P<rule>\w+)\]\[\w+\]: (?P<msg>.+)\n\s+--> (?P<file>[^:\n]+):(?P<line>\d+):")


JOIN_RULE = "S011"   # "Join without join conditions": matches any `.join(`, whatever the receiver is


def _not_a_dataframe_join(call, imports_pyspark):
    """True for a `.join(` call that cannot be a DataFrame join: str.join, bytes.join, Thread.join, a join over a literal."""
    recv = call.func.value
    if not imports_pyspark:
        return True   # a DataFrame join needs pyspark (or a pyspark-shaped library) in the file
    if not call.args and not call.keywords:
        return True   # Thread.join(), Process.join()
    if isinstance(recv, ast.Constant) and isinstance(recv.value, (str, bytes)):
        return True
    if isinstance(recv, ast.Call) and isinstance(recv.func, ast.Name) and recv.func.id in ("chr", "str", "bytes"):
        return True
    return bool(call.args) and isinstance(call.args[0], (ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.List, ast.Tuple))


def plain_join(project, file, line):
    """True when every `.join(` call on that line is provably not a DataFrame join. An unreadable file keeps the finding."""
    try:
        text = (Path(project) / file).read_text()
        tree = ast.parse(text)
    except (OSError, SyntaxError, ValueError):
        return False
    uses_pyspark = re.search(r"^\s*(from|import)\s+(pyspark|sqlframe)", text, flags=re.M) is not None
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "join" and n.lineno <= line <= (n.end_lineno or n.lineno)]
    return bool(calls) and all(_not_a_dataframe_join(c, uses_pyspark) for c in calls)


def parse(text, ctx):
    rmap = ctx.binding.get("pyspark_antipattern_map") or {}
    out = []
    for m in ITEM.finditer(text or ""):
        cid = rmap.get(m["rule"])
        if not cid:
            continue
        file, line = rel(ctx.project, m["file"]), int(m["line"])
        if m["rule"] == JOIN_RULE and plain_join(ctx.project, file, line):
            continue
        out.append(Finding(cid, file, line, NAME, m["rule"], m["msg"]))
    return out


def scan(ctx):
    exe = which("pyspark-antipattern", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    r = run([exe, "check", "."], ctx.project)
    return ScanResult(NAME, parse((r.stdout or "") + "\n" + (r.stderr or ""), ctx))
