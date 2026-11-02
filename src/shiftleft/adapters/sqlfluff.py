"""SQLFluff: SQL lint for .sql files and dbt models (jinja templater with dbt builtins, so no warehouse is needed)."""
import json

from ..model import Finding, ScanResult
from ._util import files, rel, run, which

NAME = "sqlfluff"
STAGES = ("commit", "pr", "nightly")
CONFIG = "[sqlfluff]\ndialect = databricks\ntemplater = jinja\n[sqlfluff:templater:jinja]\napply_dbt_builtins = True\n"


def parse(stdout, ctx):
    out, notes = [], []
    for f in json.loads(stdout or "[]"):
        path = rel(ctx.project, f["filepath"])
        for v in f.get("violations", []):
            code = v.get("code", "")
            if code.startswith(("PRS", "TMP", "LXR")):          # the file could not be parsed: a note, not a finding
                notes.append(f"{path}:{v.get('start_line_no')}: sqlfluff could not parse ({code})")
                continue
            out.append(Finding(ctx.check_for("sqlfluff", code, default="SL-STYLE-03"), path, v.get("start_line_no"), NAME, code, v.get("description", "")))
    return out, sorted(set(notes))


def scan(ctx):
    exe = which("sqlfluff", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    sql = [rel(ctx.project, p) for p in files(ctx.project, "*.sql")]
    if not sql:
        return ScanResult(NAME)
    cfg = ctx.project / ".sqlfluff"
    made = not cfg.exists()
    if made:
        cfg.write_text(CONFIG)
    try:
        r = run([exe, "lint", "--format", "json", "--nofail", *sql], ctx.project)
    finally:
        if made:
            cfg.unlink()
    findings, notes = parse(r.stdout, ctx)
    return ScanResult(NAME, findings, notes)
