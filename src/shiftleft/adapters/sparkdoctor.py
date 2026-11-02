"""SparkDoctor: PySpark performance and correctness rules. Only rules in the binding's sparkdoctor_map report;
the rest are counted in a note (trial on the sample, 2 Nov 2026: the magic-literal rule alone gave 11 noisy findings)."""
import json

from ..model import Finding, ScanResult
from ._util import rel, run, which

NAME = "sparkdoctor"
STAGES = ("commit", "pr", "nightly")


def parse(items, ctx):
    rmap = ctx.binding.get("sparkdoctor_map") or {}
    out, skipped = [], 0
    for it in items or []:
        cid = rmap.get(it.get("rule_id"))
        if not cid:
            skipped += 1
            continue
        out.append(Finding(cid, rel(ctx.project, it["filename"]), it.get("line"), NAME, it["rule_id"], it.get("message", "")))
    return out, ([f"sparkdoctor: {skipped} findings from rules not adopted were ignored"] if skipped else [])


def scan(ctx):
    exe = which("sparkdoctor", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    r = run([exe, "lint", ".", "--format", "json"], ctx.project)
    try:
        items = json.loads(r.stdout or "[]")
    except ValueError:
        return ScanResult(NAME, notes=["sparkdoctor: output was not JSON"])
    findings, notes = parse(items, ctx)
    return ScanResult(NAME, findings, notes)
