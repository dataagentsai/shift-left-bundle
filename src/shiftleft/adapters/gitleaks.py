"""gitleaks: secrets in files (commit, PR) and in git history (nightly)."""
import json
import tempfile
from pathlib import Path

from ..model import Finding, ScanResult
from ._util import rel, run, which

NAME = "gitleaks"
STAGES = ("commit", "pr", "nightly")
CONFIG_EXT = (".yml", ".yaml", ".json", ".toml", ".conf", ".ini", ".cfg", ".properties")


def parse(items, ctx, history=False, git_root=None):
    out = []
    for it in items or []:
        raw = it.get("File", ".")
        path = rel(ctx.project, (git_root / raw) if history and git_root else raw)
        check = "SL-SECRET-02" if history else ("SL-SECRET-03" if path.endswith(CONFIG_EXT) else "SL-SECRET-01")
        out.append(Finding(check, path, it.get("StartLine"), NAME, it.get("RuleID", ""), it.get("Description", "secret")))
    return out


def _config(ctx):
    from ..catalog import BUNDLE
    own = ctx.project / ".gitleaks.toml"
    return own if own.exists() else BUNDLE / "templates" / "gitleaks.toml"


def scan(ctx):
    exe = which("gitleaks", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    cfg = ["--config", str(_config(ctx))]
    with tempfile.TemporaryDirectory() as d:
        rep = Path(d) / "r.json"
        run([exe, "dir", ".", *cfg, "--no-banner", "--exit-code", "0", "--report-format", "json", "--report-path", str(rep)], ctx.project)
        found = parse(json.loads(rep.read_text() or "[]") if rep.exists() else [], ctx)
        if ctx.stage in ("nightly", "all"):
            top = run(["git", "rev-parse", "--show-toplevel"], ctx.project).stdout.strip()
            rep2 = Path(d) / "h.json"
            run([exe, "git", ".", *cfg, "--no-banner", "--exit-code", "0", "--report-format", "json", "--report-path", str(rep2)], ctx.project)
            found += parse(json.loads(rep2.read_text() or "[]") if rep2.exists() else [], ctx, history=True, git_root=Path(top) if top else None)
    return ScanResult(NAME, found)
