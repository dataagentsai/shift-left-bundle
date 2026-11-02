# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Score a findings file against the hidden answer key for examples/sample-project.

    uv run scripts/score.py findings.json [--key tests/sample-key.yaml] [--md out.md]

findings.json is either a list of {"check": "SL-...", "file": "src/shop/x.py", "line": 12}
or a SARIF 2.1.0 log whose result.ruleId is a catalog check id. File paths are relative to the
sample project (a leading "examples/sample-project/" is stripped).

Strict = the finding names the planted check. Lenient = it names any check in the same family.
A trap is hit when a finding with one of the trap's checks lands on the trap.
Findings that match nothing are "unplanned": reported, not counted against the run, because a
realistic sample can have real problems nobody planted.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "examples/sample-project/"


def family(check):
    return check.rsplit("-", 1)[0].removeprefix("SL-") if check else ""


def resolve(key, project):
    """Give every planted entry and trap a `line` (None for whole-file or repo entries). Errors if an anchor is missing or not unique."""
    errs = []
    for e in key["planted"] + key["traps"]:
        e["line"] = None
        if e["file"] == "." or e["anchor"] is None:
            if e["file"] != "." and not (project / e["file"]).exists():
                errs.append(f"{e['id']}: file {e['file']} not found")
            continue
        path = project / e["file"]
        if not path.exists():
            errs.append(f"{e['id']}: file {e['file']} not found")
            continue
        text = path.read_text()
        n = text.count(e["anchor"])
        if n != 1:
            errs.append(f"{e['id']}: anchor found {n} times in {e['file']}: {e['anchor']!r}")
            continue
        e["line"] = text[: text.index(e["anchor"])].count("\n") + 1
    return errs


def load_findings(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "runs" in data:
        out = []
        for run in data["runs"]:
            for r in run.get("results", []):
                loc = (r.get("locations") or [{}])[0].get("physicalLocation", {})
                out.append({"check": r.get("ruleId"), "file": loc.get("artifactLocation", {}).get("uri", "."),
                            "line": loc.get("region", {}).get("startLine")})
        data = out
    for f in data:
        f["file"] = (f.get("file") or ".").removeprefix(PREFIX)
    return data


def hits(entry_file, entry_line, f, window):
    if f["file"] != entry_file:
        return False
    if entry_line is None or f.get("line") is None:
        return True
    return abs(f["line"] - entry_line) <= window


def score(key, findings):
    w = key["match"]["line_window"]
    used = set()
    rows = defaultdict(lambda: {"planted": 0, "strict": 0, "lenient": 0})
    missed = []
    for e in key["planted"]:
        r = rows[family(e["check"])]
        r["planted"] += 1
        strict = [i for i, f in enumerate(findings) if f["check"] == e["check"] and hits(e["file"], e["line"], f, w)]
        lenient = [i for i, f in enumerate(findings) if family(f["check"]) == family(e["check"]) and hits(e["file"], e["line"], f, w)]
        used.update(strict or lenient)
        r["strict"] += bool(strict)
        r["lenient"] += bool(strict or lenient)
        if not strict:
            missed.append(e)
    trap_hits = []
    for t in key["traps"]:
        bad = [i for i, f in enumerate(findings) if f["check"] in t["checks"] and hits(t["file"], t["line"], f, w)]
        used.update(bad)
        if bad:
            trap_hits.append(t)
    unplanned = [f for i, f in enumerate(findings) if i not in used]
    return {"by_family": dict(rows), "missed": missed, "trap_hits": trap_hits, "unplanned": unplanned,
            "planted": len(key["planted"]), "strict": sum(r["strict"] for r in rows.values()),
            "lenient": sum(r["lenient"] for r in rows.values()), "traps": len(key["traps"])}


def report(s):
    lines = [f"Caught {s['strict']}/{s['planted']} planted problems strictly, {s['lenient']}/{s['planted']} by family. "
             f"False alarms: {len(s['trap_hits'])}/{s['traps']} traps. Unplanned findings: {len(s['unplanned'])}.", "",
             "| Family | Planted | Caught (strict) | Caught (family) |", "|---|---|---|---|"]
    for fam, r in sorted(s["by_family"].items()):
        lines.append(f"| {fam} | {r['planted']} | {r['strict']} | {r['lenient']} |")
    if s["trap_hits"]:
        lines += ["", "Traps hit (false alarms):"] + [f"- {t['id']} {t['file']}: {t['note']}" for t in s["trap_hits"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("findings")
    ap.add_argument("--key", default=str(ROOT / "tests" / "sample-key.yaml"))
    ap.add_argument("--project", default=str(ROOT / "examples" / "sample-project"))
    ap.add_argument("--md")
    a = ap.parse_args()
    key = yaml.safe_load(Path(a.key).read_text())
    errs = resolve(key, Path(a.project))
    if errs:
        print("\n".join("KEY ERROR " + e for e in errs))
        sys.exit(2)
    s = score(key, load_findings(a.findings))
    text = report(s)
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n")


if __name__ == "__main__":
    main()
