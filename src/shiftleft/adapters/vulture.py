"""vulture: dead code (SL-CPLX-04). Tests are scanned too, so a function used only by a test is not dead.

A library's public functions look unused when jobs call them from config, so (run 1, 2 Nov 2026: 28 findings, 1 real):
  - names called from outside Python are entry points: bundle task entry points and notebook paths, [project.scripts]
    and entry points in pyproject.toml, and any name listed in `.shiftleft-entrypoints` (one per line);
  - private functions (leading underscore), classes, methods and unreachable code are reported one by one;
  - unused public functions are reported as ONE finding per module, listing them, for a person to confirm.
"""
import re
from collections import defaultdict

from ..model import Finding, ScanResult
from ._util import files, rel, run, which

NAME = "vulture"
STAGES = ("pr", "nightly")
KEEP = ("unused function", "unused class", "unused method", "unreachable code")   # imports and variables: Ruff has them
LINE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+): (?P<msg>.+?) \((?P<conf>\d+)% confidence")
NAMEQ = re.compile(r"'(?P<name>[^']+)'")


def entry_points(project):
    names = set()
    ep = project / ".shiftleft-entrypoints"
    if ep.exists():
        names |= {ln.strip() for ln in ep.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    for p in files(project, "*.yml", "*.yaml", "pyproject.toml"):
        text = p.read_text(errors="ignore")
        names |= set(re.findall(r"entry_point:\s*[\"']?(\w+)", text))
        names |= set(re.findall(r"[\w.]+:(\w+)[\"']", text)) if p.name == "pyproject.toml" else set()
    return names


def parse(stdout, ctx, entry=frozenset()):
    out, public = [], defaultdict(list)
    for ln in (stdout or "").splitlines():
        m = LINE.match(ln)
        if not m or not m["msg"].startswith(KEEP):
            continue
        name = (NAMEQ.search(m["msg"]) or {"name": ""})["name"] if NAMEQ.search(m["msg"]) else ""
        if name in entry:
            continue
        file = rel(ctx.project, m["file"])
        if m["msg"].startswith("unused function") and not name.startswith("_"):
            public[file].append(name)
            continue
        out.append(Finding("SL-CPLX-04", file, int(m["line"]), NAME, f"vulture-{m['conf']}", m["msg"]))
    for file, names in public.items():
        out.append(Finding("SL-CPLX-04", file, None, NAME, "unused-public",
                           f"{len(names)} public functions are not called anywhere in the repository: {', '.join(names[:8])}"
                           f"{' ...' if len(names) > 8 else ''}. If jobs call them, list them in .shiftleft-entrypoints"))
    return out


def scan(ctx):
    exe = which("vulture", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    r = run([exe, ".", "--min-confidence", "60", "--exclude", ".venv"], ctx.project)
    return ScanResult(NAME, parse(r.stdout, ctx, entry_points(ctx.project)))
