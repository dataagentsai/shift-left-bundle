"""jscpd: copied blocks of code (SL-CPLX-05), Python and SQL. Nightly; report only.

Comments are ignored (mode weak), so Databricks markdown cells never count as copies. The report goes to a temporary
folder; nothing is written into the scanned repository. Settings: binding `duplicates:`.
"""
import json
import tempfile
from pathlib import Path

from ..model import Finding, ScanResult
from ._util import rel, run, which

NAME = "jscpd"
STAGES = ("nightly",)
IGNORE = "**/.git/**,**/.venv/**,**/node_modules/**,**/target/**,**/dbt_packages/**"


def parse(report, project):
    """One finding per copy, on the second copy, naming where the first one is."""
    out = []
    for c in report.get("duplicates", []):
        first, second = c["firstFile"], c["secondFile"]
        a, b = rel(project, first["name"]), rel(project, second["name"])
        out.append(Finding("SL-CPLX-05", b, second.get("start"), NAME, c.get("format", "clone"),
                           f"{c.get('lines', '?')} lines copied from {a}:{first.get('start')}; keep one shared function"))
    return out


def scan(ctx):
    exe = which("jscpd", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    cfg = ctx.binding.get("duplicates") or {}
    with tempfile.TemporaryDirectory() as d:
        res = run([exe, ".", "--format", ",".join(cfg.get("formats", ["python", "sql"])), "--mode", "weak",
                   "--min-lines", str(cfg.get("min_lines", 6)), "--min-tokens", str(cfg.get("min_tokens", 50)),
                   "--ignore", IGNORE, "--reporters", "json", "--output", d, "--silent"], ctx.project)
        rep = Path(d) / "jscpd-report.json"
        if not rep.exists():
            why = (res.stderr or res.stdout or "").strip().splitlines()[:1]
            return ScanResult(NAME, notes=[f"jscpd wrote no report: {why[0] if why else 'no output'}"])
        return ScanResult(NAME, parse(json.loads(rep.read_text()), ctx.project))
