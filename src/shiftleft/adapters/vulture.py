"""vulture: dead code. Tests are scanned too, so a function used only by a test is not called dead."""
import re

from ..model import Finding, ScanResult
from ._util import rel, run, which

NAME = "vulture"
STAGES = ("pr", "nightly")
KEEP = ("unused function", "unused class", "unused method", "unreachable code")   # imports and variables: Ruff already reports them
LINE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+): (?P<msg>.+?) \((?P<conf>\d+)% confidence")


def parse(stdout, ctx):
    out = []
    for ln in (stdout or "").splitlines():
        m = LINE.match(ln)
        if m and m["msg"].startswith(KEEP):
            out.append(Finding("SL-CPLX-04", rel(ctx.project, m["file"]), int(m["line"]), NAME, f"vulture-{m['conf']}", m["msg"]))
    return out


def scan(ctx):
    exe = which("vulture", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    r = run([exe, ".", "--min-confidence", "60", "--exclude", ".venv"], ctx.project)
    return ScanResult(NAME, parse(r.stdout, ctx))
