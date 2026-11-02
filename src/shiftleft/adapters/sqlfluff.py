"""SQLFluff: SQL lint for .sql files and dbt models (jinja templater with dbt builtins, so no warehouse is needed)."""
import json
import tempfile
from pathlib import Path

from ..model import Finding, ScanResult
from ._notebooks import sql_cells
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
    own = any((ctx.project / f).exists() for f in (".sqlfluff", "setup.cfg", "tox.ini", "pyproject.toml"))
    with tempfile.TemporaryDirectory() as d:                   # never write into the repository
        cfg = []
        if not own:
            (Path(d) / "sqlfluff.cfg").write_text(CONFIG)
            cfg = ["--config", str(Path(d) / "sqlfluff.cfg")]
        r = run([exe, "lint", "--format", "json", "--nofail", *cfg, *sql], ctx.project)
    findings, notes = parse(r.stdout, ctx)
    f2, n2 = _notebook_cells(exe, ctx)
    return ScanResult(NAME, findings + f2, notes + n2)


def _notebook_cells(exe, ctx):
    """Lint %sql cells from notebooks: write each cell to a temp .sql file, then map lines back."""
    cells = [(rel(ctx.project, nb), start, sql) for nb in files(ctx.project, "*.py", "*.ipynb") for start, sql in sql_cells(nb)]
    if not cells:
        return [], []
    with tempfile.TemporaryDirectory() as d:
        where = {}
        for i, (file, start, sql) in enumerate(cells):
            tmp = Path(d) / f"cell_{i}.sql"
            tmp.write_text(sql if sql.endswith("\n") else sql + "\n")
            where[tmp.name] = (file, start)
        (Path(d) / ".sqlfluff").write_text(CONFIG)
        r = run([exe, "lint", "--format", "json", "--nofail", *where], d)
    out, notes = [], []
    for f in json.loads(r.stdout or "[]"):
        file, start = where[Path(f["filepath"]).name]
        for v in f.get("violations", []):
            code = v.get("code", "")
            if code.startswith(("PRS", "TMP", "LXR")):
                notes.append(f"{file}: a %sql cell could not be parsed by sqlfluff ({code})")
                continue
            if code in ("LT12", "CV06"):            # trailing newline / semicolon rules mean nothing inside a cell
                continue
            line = start + (v.get("start_line_no") or 1) - 1
            out.append(Finding(ctx.check_for("sqlfluff", code, default="SL-STYLE-03"), file, line, NAME, code, v.get("description", "")))
    return out, sorted(set(notes))
