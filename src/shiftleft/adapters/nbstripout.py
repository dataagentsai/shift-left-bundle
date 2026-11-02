"""nbstripout: notebooks committed with outputs."""
from ..model import Finding, ScanResult
from ._util import files, rel, run, which

NAME = "nbstripout"
STAGES = ("commit", "pr", "nightly")


def scan(ctx):
    exe = which("nbstripout", ctx)
    if not exe:
        return ScanResult(NAME, missing=True)
    out = []
    for nb in files(ctx.project, "*.ipynb"):
        if run([exe, "--verify", str(nb)], ctx.project).returncode != 0:
            out.append(Finding("SL-SEC-09", rel(ctx.project, nb), None, NAME, "outputs", "notebook has outputs; strip them before commit"))
    return ScanResult(NAME, out)
