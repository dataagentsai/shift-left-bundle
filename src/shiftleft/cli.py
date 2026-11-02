"""shiftleft scan PATH [--stage pr] [--json f] [--sarif f] [--md f] [--baseline f]; shiftleft baseline PATH --out f"""
import argparse
import json
import sys
from pathlib import Path

from . import catalog, engine, report
from .model import Context


def _ctx(a):
    checks, gates, binding = catalog.load(a.binding)
    tools = [Path(p) for p in (a.tools or "").split(":") if p]
    return Context(Path(a.path).resolve(), a.stage, binding, checks, gates, tools)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shiftleft")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "baseline"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--stage", default="pr", choices=["commit", "pr", "nightly", "predeploy", "all"])
        p.add_argument("--binding", default="databricks")
        p.add_argument("--tools", help="extra folders with tool binaries, separated by ':'")
        if name == "scan":
            p.add_argument("--baseline")
            p.add_argument("--json")
            p.add_argument("--sarif")
            p.add_argument("--md")
        else:
            p.add_argument("--out", default=".shiftleft-baseline.json")
    a = ap.parse_args(argv)
    ctx = _ctx(a)
    if a.cmd == "baseline":
        findings, _, missing = engine.run(ctx)
        Path(a.out).write_text(json.dumps({"stage": a.stage, "fingerprints": sorted({f.fingerprint for f in findings})}, indent=1))
        print(f"baseline: {len(findings)} findings recorded in {a.out}" + (f" (tools missing: {', '.join(missing)})" if missing else ""))
        return 0
    findings, notes, missing = engine.run(ctx, engine.load_baseline(a.baseline))
    failed = engine.should_fail(findings)
    md = report.to_markdown(findings, ctx.checks, notes, missing, a.stage, failed)
    if a.json:
        Path(a.json).write_text(json.dumps(report.to_json(findings), indent=1))
    if a.sarif:
        Path(a.sarif).write_text(json.dumps(report.to_sarif(findings, ctx.checks), indent=1))
    if a.md:
        Path(a.md).write_text(md)
    print(md.splitlines()[2])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
