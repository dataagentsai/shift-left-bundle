"""Ruff: Python lint, clean code, security, complexity. Rules map to checks through the binding's ruff_map."""
import json

from ..model import Finding, ScanResult
from ._util import rel, run, which

NAME = "ruff"
STAGES = ("commit", "pr", "nightly")


def parse(stdout, ctx):
    out = []
    for it in json.loads(stdout or "[]"):
        code = it.get("code") or "syntax"
        check = ctx.check_for("ruff", code, default="SL-STYLE-02")
        out.append(Finding(check, rel(ctx.project, it["filename"]), it["location"]["row"], NAME, code, it.get("message", "")))
    return out


def scan(ctx):
    exe = which("ruff", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    from ..catalog import BUNDLE
    own = any((ctx.project / f).exists() for f in ("ruff.toml", ".ruff.toml", "pyproject.toml"))
    settings = ctx.binding.get("ruff_settings")
    cfg = [] if own or not settings else ["--config", str(BUNDLE / settings)]
    r = run([exe, "check", "--no-cache", "--exit-zero", "--output-format", "json", *cfg, "."], ctx.project)
    return ScanResult(NAME, parse(r.stdout, ctx))
