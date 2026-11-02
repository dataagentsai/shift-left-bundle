"""complexipy: cognitive complexity per function (its JSON has no line numbers, so we find the def)."""
import json
import tempfile
from pathlib import Path

from ..model import Finding, ScanResult
from ._util import line_of, rel, run, which

NAME = "complexipy"
STAGES = ("commit", "pr", "nightly")


def parse(items, ctx):
    limit = ctx.gates["complexity"]["cognitive_max"]
    out = []
    for it in items or []:
        if it.get("complexity", 0) > limit:
            path = rel(ctx.project, it["path"])
            fn = it["function_name"]
            out.append(Finding("SL-CPLX-02", path, line_of(ctx.project, path, f"def {fn}("), NAME, "cognitive",
                               f"{fn}: cognitive complexity {it['complexity']} (limit {limit})"))
    return out


def scan(ctx):
    exe = which("complexipy", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    with tempfile.TemporaryDirectory() as d:
        rep = Path(d) / "c.json"
        run([exe, ".", "--output-format", "json", "--output", str(rep), "-q", "-i"], ctx.project)
        items = json.loads(rep.read_text()) if rep.exists() else []
    return ScanResult(NAME, parse(items, ctx))
