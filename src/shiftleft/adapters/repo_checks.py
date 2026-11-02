"""Built-in repository checks (what is missing, unpinned libraries, notebook installs).
Plain file reads, no tool. To move onto repo-review plugins in Tier 5 (SL-053)."""
import re

from ..model import Finding, ScanResult
from ._util import files, rel

NAME = "repo-checks"
STAGES = ("commit", "pr", "nightly")
PIN = re.compile(r"^[A-Za-z0-9_.\-\[\]]+==[^=]")
PIP_IN_NB = re.compile(r"%pip install(?P<rest>.*)")


def _text(paths):
    return "\n".join(p.read_text(errors="ignore") for p in paths)


def ci_text(project):
    paths = files(project, "*.yml", "*.yaml")
    ci = [p for p in paths if ".github/workflows" in str(p) or p.name.startswith(("azure-pipelines", ".gitlab-ci"))]
    return _text(ci), bool(ci)


def setup_findings(project):
    """Repository-level gaps. Pure apart from reading files."""
    pre = project / ".pre-commit-config.yaml"
    pre_text = pre.read_text() if pre.exists() else ""
    ci, has_ci = ci_text(project)
    both = ci + pre_text
    out = []

    def gap(check, msg):
        out.append(Finding(check, ".", None, NAME, check.lower(), msg))

    if not pre.exists():
        gap("SL-SETUP-01", "no .pre-commit-config.yaml: nothing runs on commit")
    if not has_ci or "pytest" not in ci:
        gap("SL-SETUP-02", "no CI pipeline runs the tests on pull requests")
    if not re.search(r"diff-cover|--cov-fail-under|fail_under", ci):
        gap("SL-SETUP-03", "no coverage threshold enforced in CI")
    if not re.search(r"gitleaks|trufflehog|secret", both, re.I):
        gap("SL-SETUP-04", "no secret scanning on commit or in CI")
    if (project / "databricks.yml").exists() and "bundle validate" not in ci:
        gap("SL-SETUP-06", "databricks.yml exists but CI never runs `databricks bundle validate`")
    if files(project, "*.sql") and "sqlfluff" not in both:
        gap("SL-SETUP-07", "SQL files are not linted on commit or in CI")
    if not (project / "tests").exists():
        gap("SL-SETUP-08", "no tests folder")
    return out


def dependency_findings(project):
    out = []
    locks = [n for n in ("uv.lock", "poetry.lock", "Pipfile.lock", "requirements.lock") if (project / n).exists()]
    for req in files(project, "requirements*.txt"):
        for i, ln in enumerate(req.read_text().splitlines(), 1):
            s = ln.split("#")[0].strip()
            if s and not s.startswith("-") and not PIN.match(s):
                out.append(Finding("SL-DEP-02", rel(project, req), i, NAME, "unpinned",
                                   f"'{s}' is not pinned to an exact version" + ("" if locks else "; no lockfile either")))
    for nb in files(project, "*.py", "*.ipynb"):
        for i, ln in enumerate(nb.read_text(errors="ignore").splitlines(), 1):
            m = PIP_IN_NB.search(ln)
            if m and "==" not in m["rest"]:
                out.append(Finding("SL-DEP-06", rel(project, nb), i, NAME, "pip-in-notebook", "library installed in a notebook without a version"))
    return out


def scan(ctx):
    return ScanResult(NAME, setup_findings(ctx.project) + dependency_findings(ctx.project))
