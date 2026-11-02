"""Small helpers shared by adapters: find a tool, run it, find a line."""
import os
import shutil
import subprocess
from pathlib import Path


def which(name, ctx):
    path = os.pathsep.join([*map(str, ctx.tool_paths), os.environ.get("PATH", "")])
    return shutil.which(name, path=path)


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def files(project: Path, *patterns, exclude=(".git", ".venv", "node_modules", "target")):
    out = []
    for pat in patterns:
        for p in project.rglob(pat):
            if not any(part in exclude for part in p.parts):
                out.append(p)
    return sorted(set(out))


def rel(project: Path, p) -> str:
    p = Path(p)
    p = p if p.is_absolute() else (project / p)
    try:
        return str(p.resolve().relative_to(project.resolve()))
    except ValueError:
        return str(p)


def line_of(project: Path, file: str, needle: str):
    try:
        for i, ln in enumerate((project / file).read_text().splitlines(), 1):
            if needle.lower() in ln.lower():
                return i
    except OSError:
        pass
    return None
