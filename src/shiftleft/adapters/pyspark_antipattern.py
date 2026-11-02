"""pyspark-antipattern: only the rules other tools lack are adopted (binding pyspark_antipattern_map).
It has no JSON output; its text report is parsed. It writes the report to stderr."""
import re

from ..model import Finding, ScanResult
from ._util import rel, run, which

NAME = "pyspark-antipattern"
STAGES = ("commit", "pr", "nightly")
ITEM = re.compile(r"error\[(?P<rule>\w+)\]\[\w+\]: (?P<msg>.+)\n\s+--> (?P<file>[^:\n]+):(?P<line>\d+):")


def parse(text, ctx):
    rmap = ctx.binding.get("pyspark_antipattern_map") or {}
    out = []
    for m in ITEM.finditer(text or ""):
        cid = rmap.get(m["rule"])
        if cid:
            out.append(Finding(cid, rel(ctx.project, m["file"]), int(m["line"]), NAME, m["rule"], m["msg"]))
    return out


def scan(ctx):
    exe = which("pyspark-antipattern", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    r = run([exe, "check", "."], ctx.project)
    return ScanResult(NAME, parse((r.stdout or "") + "\n" + (r.stderr or ""), ctx))
