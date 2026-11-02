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
    dp = sub.add_parser("draft-tests", help="starter tests for pure functions that have none")
    dp.add_argument("path")
    dp.add_argument("--binding", default="databricks")
    dp.add_argument("--out", help="folder for the drafts (default: PATH/tests/drafts)")
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
            p.add_argument("--summary", help="short pull-request comment (markdown)")
            p.add_argument("--html", help="repo health page (static HTML)")
            p.add_argument("--previous", help="findings JSON from the previous run, for the trend")
        else:
            p.add_argument("--out", default=".shiftleft-baseline.json")
    a = ap.parse_args(argv)
    if a.cmd == "purity":
        return _purity(a)
    if a.cmd == "draft-tests":
        from .drafts import draft
        _, _, binding = catalog.load(a.binding)
        project = Path(a.path).resolve()
        written, n = draft(project, purity_rows(project, binding), Path(a.out) if a.out else project / "tests" / "drafts")
        print(f"{n} pure functions without tests; drafts written: " + ", ".join(str(w) for w in written))
        return 0
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
    if a.summary:
        from . import health
        Path(a.summary).write_text(health.pr_summary(findings, ctx.checks, a.stage, failed))
    if a.html:
        from . import health
        prev = json.loads(Path(a.previous).read_text()) if a.previous and Path(a.previous).exists() else None
        Path(a.html).write_text(health.health_page(ctx.project.name, findings, ctx.checks, purity_rows(ctx.project, ctx.binding),
                                                   notes, missing, a.stage, failed, prev))
    print(md.splitlines()[2])
    return 1 if failed else 0


def purity_rows(project, binding):
    from . import purity as P
    from .adapters.purity_adapter import report
    fns, tests, notebooks, _ = report(project, binding)
    return [{"module": f.module, "function": f.name, "line": f.line, "verdict": f.verdict,
             "reasons": [{"category": c, "call": t, "line": ln} for c, t, ln in f.reasons],
             "unknown_calls": [t for t, _ in f.unknown][:5], "chain": f.chain,
             "could_be_pure": bool(P.could_be_pure(f)), "hint": P.hint(f) if P.could_be_pure(f) else "",
             "tested": f.name.split(".")[-1] in tests, "notebook": f.module in notebooks} for f in fns]


def _purity(a):
    _, _, binding = catalog.load(a.binding)
    rows = purity_rows(Path(a.path).resolve(), binding)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
    tot = {k: sum(r["verdict"] == k for r in rows) for k in ("pure", "impure", "unknown")}
    print(f"{len(rows)} functions: {tot['pure']} pure, {tot['impure']} impure, {tot['unknown']} unknown; "
          f"{sum(r['could_be_pure'] for r in rows)} impure could be pure; "
          f"{sum(r['verdict'] == 'pure' and not r['tested'] and not r['notebook'] for r in rows)} pure functions untested")
    return 0


if __name__ == "__main__":
    sys.exit(main())
