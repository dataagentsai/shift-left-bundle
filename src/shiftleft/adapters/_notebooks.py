"""Pull SQL cells out of notebooks so SQL checks see them.

Databricks source format (.py): a cell starting with `# MAGIC %sql`; every line of the cell starts with `# MAGIC`.
Jupyter (.ipynb): a cell whose first line is `%sql` or `%%sql`.
Returns (file, first_line_of_sql, sql_text); for .ipynb the line is the cell number (no file lines exist).
"""
import json
from pathlib import Path

CELL = "# COMMAND ----------"


def source_sql_cells(path: Path):
    lines = path.read_text(errors="ignore").splitlines()
    if not lines or not lines[0].startswith("# Databricks notebook source"):
        return []
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip().startswith("# MAGIC %sql"):
            start, body = i + 2, []                                  # SQL starts on the line after the magic
            j = i + 1
            while j < len(lines) and lines[j].startswith("# MAGIC") and lines[j].strip() != CELL:
                body.append(lines[j][len("# MAGIC"):].lstrip(" ") if len(lines[j]) > 7 else "")
                j += 1
            if any(b.strip() for b in body):
                out.append((start, "\n".join(body)))
            i = j
        else:
            i += 1
    return out


def ipynb_sql_cells(path: Path):
    try:
        nb = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for n, cell in enumerate(nb.get("cells", []), 1):
        src = "".join(cell.get("source", []))
        first, _, rest = src.partition("\n")
        if cell.get("cell_type") == "code" and first.strip() in ("%sql", "%%sql") and rest.strip():
            out.append((n, rest))
    return out


def sql_cells(path: Path):
    return ipynb_sql_cells(path) if path.suffix == ".ipynb" else source_sql_cells(path)
