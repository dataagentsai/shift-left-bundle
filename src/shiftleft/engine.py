"""Run the scanners for a stage and turn their output into gated, de-duplicated findings."""
import hashlib
import json
import re
from pathlib import Path

from . import refine
from .adapters import REGISTRY
from .model import STAGE_ORDER, Context

GATE_RANK = {"report": 0, "warn": 1, "block": 2}
ALLOW = re.compile(r"shiftleft:\s*allow\s+(?P<ids>[A-Z0-9,\s-]+?)\s*(?:--\s*(?P<reason>.*))?$")


def stage_includes(run_stage: str, check_stage: str) -> bool:
    """Does a run at `run_stage` report a check that first runs at `check_stage`?"""
    if run_stage == "all":
        return True
    if run_stage == "predeploy" or check_stage == "predeploy":
        return run_stage == check_stage
    return STAGE_ORDER[check_stage] <= STAGE_ORDER[run_stage]


def scanners_for(stage: str):
    return [m for m in REGISTRY.values() if stage == "all" or stage in m.STAGES]


def line_text(project: Path, file: str, line):
    if file == "." or not line:
        return ""
    try:
        lines = (project / file).read_text(errors="ignore").splitlines()
        return lines[line - 1] if 0 < line <= len(lines) else ""
    except OSError:
        return ""


def fingerprint(check: str, file: str, text: str) -> str:
    """Stable when code moves to another line; changes when the code itself changes."""
    norm = re.sub(r"\s+", "", text)
    return hashlib.sha1(f"{check}|{file}|{norm}".encode()).hexdigest()[:16]


def suppression(project: Path, f):
    """Return (allowed, reason) from a `shiftleft: allow <id> -- <reason>` marker on the line or the line above."""
    if f.file == "." or not f.line:
        return False, ""
    for ln in (f.line, f.line - 1):
        m = ALLOW.search(line_text(project, f.file, ln))
        if m and f.check in re.split(r"[,\s]+", m["ids"].strip()):
            return bool(m["reason"]), (m["reason"] or "").strip()
    return False, ""


def finalise(findings, ctx: Context, baseline=frozenset()):
    """Pure apart from reading source lines: map, filter by stage, gate, suppress, baseline, de-duplicate."""
    out, notes, seen = [], [], set()
    for f in findings:
        chk = ctx.checks.get(f.check)
        if not chk:
            notes.append(f"{f.tool} {f.tool_rule}: mapped to unknown check {f.check}; dropped")
            continue
        if not stage_includes(ctx.stage, chk["stage"]):
            continue
        key = (f.check, f.file, f.line)
        if key in seen:
            continue
        seen.add(key)
        cat_gate = chk["gate"]
        f.gate = f.gate if f.gate and GATE_RANK[f.gate] < GATE_RANK[cat_gate] else cat_gate
        f.fingerprint = fingerprint(f.check, f.file, line_text(ctx.project, f.file, f.line))
        allowed, reason = suppression(ctx.project, f)
        if allowed:
            f.status, f.suppress_reason = "suppressed", reason
        elif f.fingerprint in baseline:
            f.status = "baseline"
        out.append(f)
    order = {"block": 0, "warn": 1, "report": 2}
    out.sort(key=lambda x: (order[x.gate], x.check, x.file, x.line or 0))
    return out, notes


def should_fail(findings) -> bool:
    return any(f.gate == "block" and f.status == "new" for f in findings)


def load_baseline(path):
    p = Path(path) if path else None
    return frozenset(json.loads(p.read_text())["fingerprints"]) if p and p.exists() else frozenset()


def run(ctx: Context, baseline=frozenset()):
    raw, notes, missing = [], [], []
    for m in scanners_for(ctx.stage):
        res = m.scan(ctx)
        if res.missing:
            missing.append(m.NAME)
        raw += res.findings
        notes += res.notes
    raw, refined = refine.apply(raw, ctx.project, ctx.binding.get("refine") or [])
    notes += refined
    findings, more = finalise(raw, ctx, baseline)
    return findings, notes + more, missing
