"""Write findings as JSON, SARIF 2.1.0 and a REVIEW.md people can read."""
import json
from collections import Counter

from . import __version__

LEVEL = {"block": "error", "warn": "warning", "report": "note"}


def to_json(findings):
    return [{"check": f.check, "file": f.file, "line": f.line, "gate": f.gate, "status": f.status, "tool": f.tool,
             "tool_rule": f.tool_rule, "message": f.message, "fingerprint": f.fingerprint} for f in findings]


def to_sarif(findings, checks):
    used = sorted({f.check for f in findings})
    rules = [{"id": c, "name": checks[c]["title"], "shortDescription": {"text": checks[c]["title"]},
              "fullDescription": {"text": checks[c]["statement"]}, "help": {"text": checks[c]["fix"]},
              "properties": {"family": c.rsplit("-", 1)[0], "gate": checks[c]["gate"]}} for c in used]
    results = []
    for f in findings:
        loc = {"physicalLocation": {"artifactLocation": {"uri": f.file}}}
        if f.line:
            loc["physicalLocation"]["region"] = {"startLine": f.line}
        r = {"ruleId": f.check, "level": LEVEL[f.gate], "message": {"text": f"{f.message} [{f.tool} {f.tool_rule}]"},
             "locations": [loc], "partialFingerprints": {"shiftleft/v1": f.fingerprint}}
        if f.status == "suppressed":
            r["suppressions"] = [{"kind": "inSource", "justification": f.suppress_reason}]
        elif f.status == "baseline":
            r["baselineState"] = "unchanged"
        results.append(r)
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "shiftleft", "version": __version__, "rules": rules}}, "results": results}]}


def to_markdown(findings, checks, notes, missing, stage, failed):
    new = [f for f in findings if f.status == "new"]
    g = Counter(f.gate for f in new)
    lines = [f"# Shift-left review ({stage})", "",
             f"**{'FAIL' if failed else 'PASS'}**: {g['block']} blocking, {g['warn']} warnings, {g['report']} reported. "
             f"{sum(f.status == 'baseline' for f in findings)} already in the baseline, {sum(f.status == 'suppressed' for f in findings)} suppressed.", ""]
    if missing:
        lines += [f"Tools not installed, so their checks did not run: {', '.join(missing)}.", ""]
    for gate, title in (("block", "Fix before merge"), ("warn", "Warnings"), ("report", "For the record")):
        rows = [f for f in new if f.gate == gate]
        if not rows:
            continue
        lines += [f"## {title} ({len(rows)})", "", "| Check | Where | What | Found by |", "|---|---|---|---|"]
        for f in rows:
            where = f.file + (f":{f.line}" if f.line else "")
            lines.append(f"| {f.check} {checks[f.check]['title']} | {where} | {f.message.replace('|', '/')} | {f.tool} {f.tool_rule} |")
        lines.append("")
    sup = [f for f in findings if f.status == "suppressed"]
    if sup:
        lines += ["## Suppressed (review these)", ""] + [f"- {f.check} at {f.file}:{f.line}: {f.suppress_reason}" for f in sup] + [""]
    if notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(lines)
