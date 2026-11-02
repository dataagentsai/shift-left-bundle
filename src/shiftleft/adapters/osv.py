"""osv-scanner: libraries with known vulnerabilities, from lockfiles and requirements files."""
import json

from ..model import Finding, ScanResult
from ._util import line_of, rel, run, which

NAME = "osv-scanner"
STAGES = ("pr", "nightly")


def parse(stdout, ctx, block_at=7.0):
    out = []
    for res in (json.loads(stdout or "{}").get("results") or []):
        path = rel(ctx.project, res.get("source", {}).get("path", "."))
        for pkg in res.get("packages") or []:
            name = pkg.get("package", {}).get("name", "?")
            ver = pkg.get("package", {}).get("version", "?")
            ids = [v.get("id") for v in pkg.get("vulnerabilities") or []]
            sev = max([float(g.get("max_severity") or 0) for g in pkg.get("groups") or []] or [0])
            msg = f"{name} {ver}: {len(ids)} known vulnerabilities (max CVSS {sev}): {', '.join(ids[:5])}"
            f = Finding("SL-DEP-01", path, line_of(ctx.project, path, name) or line_of(ctx.project, path, name.lower()), NAME, "osv", msg)
            if sev < block_at:
                f.gate = "warn"           # below high: the engine keeps this lower gate
            out.append(f)
    return out


def scan(ctx):
    exe = which("osv-scanner", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    r = run([exe, "scan", "source", "-r", "--format", "json", "."], ctx.project)
    return ScanResult(NAME, parse(r.stdout, ctx))
