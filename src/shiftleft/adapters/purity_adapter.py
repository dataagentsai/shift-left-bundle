"""Purity report as findings (SL-PURE-*), joined with the tests folder for SL-TEST-02 and SL-TEST-03."""
from ..model import Finding, ScanResult
from .. import purity as P
from ._util import files, rel

NAME = "purity"
STAGES = ("pr", "nightly")


def is_test(path):
    return "tests" in path.parts or path.name.startswith("test_") or path.name == "conftest.py"


def is_notebook(path):
    try:
        with open(path, errors="ignore") as fh:
            return fh.readline().startswith("# Databricks notebook source")
    except OSError:
        return False


def report(project, binding):
    paths = [p for p in files(project, "*.py") if not is_test(p)]
    fns = P.analyse(project, binding.get("purity") or {}, paths)
    tests = "\n".join(p.read_text(errors="ignore") for p in files(project, "*.py") if is_test(p))
    notebooks = {rel(project, p) for p in paths if is_notebook(p)}
    return fns, tests, notebooks, paths


def findings(project, binding):
    fns, tests, notebooks, paths = report(project, binding)
    out = []
    counts = P.summary(fns)
    tot = {k: sum(m[k] for m in counts.values()) for k in ("pure", "impure", "unknown")}
    out.append(Finding("SL-PURE-01", ".", None, NAME, "classify",
                       f"{len(fns)} functions: {tot['pure']} pure, {tot['impure']} impure, {tot['unknown']} unknown"))
    for f in fns:
        cats = f.categories
        shell = bool(cats & {"table_read", "table_write"})
        if f.marked_pure and f.verdict == "impure":
            out.append(Finding("SL-PURE-05", f.module, f.line, NAME, "false-pure-mark",
                               f"{f.name} is marked pure but {f.reasons[0][0]} at line {f.reasons[0][2]}"))
        if P.could_be_pure(f) and shell:
            out.append(Finding("SL-PURE-02", f.module, f.line, NAME, "could-be-pure", f"{f.name}: {P.hint(f)}"))
        if cats & {"clock", "randomness"} and not shell:
            r = next(r for r in f.reasons if r[0] in ("clock", "randomness"))
            out.append(Finding("SL-PURE-03", f.module, f.line, NAME, "non-repeatable", f"{f.name} calls {r[1]} (line {r[2]}); pass it in"))
        if "engine_action" in cats and not shell:
            r = next(r for r in f.reasons if r[0] == "engine_action")
            out.append(Finding("SL-PURE-06", f.module, f.line, NAME, "action-in-logic", f"{f.name} runs {r[1]} (line {r[2]}); return the lazy result"))
        if f.verdict == "pure" and f.module not in notebooks and f.name.split(".")[-1] not in tests:
            out.append(Finding("SL-TEST-02", f.module, f.line, NAME, "pure-untested", f"{f.name} is pure and no test calls it"))
    for p in paths:
        r = rel(project, p)
        col = P.Collector(r, p.read_text(errors="ignore"))
        for name, line in col.session_lines:
            out.append(Finding("SL-PURE-07", r, line, NAME, "global-session", f"module-level session `{name}` used by functions"))
        if r not in notebooks and p.name != "__init__.py" and any(f.module == r for f in fns) and p.stem not in tests:
            out.append(Finding("SL-TEST-03", r, None, NAME, "no-test-file", f"no test refers to module {p.stem}"))
    return out


def scan(ctx):
    return ScanResult(NAME, findings(ctx.project, ctx.binding))
