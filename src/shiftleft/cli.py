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
    pp = sub.add_parser("purity", help="the purity report: every function with its verdict, reasons and hint")
    pp.add_argument("path")
    pp.add_argument("--binding", default="databricks")
    pp.add_argument("--json")
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
    if a.cmd == "purity":
        return _purity(a)
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


def _purity(a):
    from . import purity as P
    from .adapters.purity_adapter import report
    _, _, binding = catalog.load(a.binding)
    fns, tests, notebooks, _ = report(Path(a.path).resolve(), binding)
    rows = [{"module": f.module, "function": f.name, "line": f.line, "verdict": f.verdict,
             "reasons": [{"category": c, "call": t, "line": ln} for c, t, ln in f.reasons],
             "unknown_calls": [t for t, _ in f.unknown][:5], "chain": f.chain,
             "could_be_pure": bool(P.could_be_pure(f)), "hint": P.hint(f) if P.could_be_pure(f) else "",
             "tested": f.name.split(".")[-1] in tests, "notebook": f.module in notebooks} for f in fns]
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
    tot = {k: sum(r["verdict"] == k for r in rows) for k in ("pure", "impure", "unknown")}
    print(f"{len(rows)} functions: {tot['pure']} pure, {tot['impure']} impure, {tot['unknown']} unknown; "
          f"{sum(r['could_be_pure'] for r in rows)} impure could be pure; "
          f"{sum(r['verdict'] == 'pure' and not r['tested'] and not r['notebook'] for r in rows)} pure functions untested")
    return 0


if __name__ == "__main__":
    sys.exit(main())
