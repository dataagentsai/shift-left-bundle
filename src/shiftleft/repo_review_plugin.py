"""repo-review plugin: the bundle's "what is missing" checks inside repo-review (SL-053).

Teams that already run repo-review or sp-repo-review get the data-repo checks in the same report and web page.
The logic is shared with the built-in adapter (adapters/repo_checks.py), so both always agree.
Registered through the `repo_review.checks` and `repo_review.families` entry points."""
from functools import lru_cache
from pathlib import Path

from .adapters.repo_checks import dependency_findings, setup_findings

TITLES = {
    "SL-SETUP-01": "Has commit-time checks (.pre-commit-config.yaml)",
    "SL-SETUP-02": "CI runs the tests on pull requests",
    "SL-SETUP-03": "CI enforces a coverage threshold",
    "SL-SETUP-04": "Secrets are scanned on commit or in CI",
    "SL-SETUP-06": "The Databricks bundle is validated before deploy",
    "SL-SETUP-07": "SQL files are linted",
    "SL-SETUP-08": "Has a tests folder",
    "SL-DEP-02": "Library versions are pinned",
}


@lru_cache(maxsize=8)
def _results(root: str):
    p = Path(root).resolve()
    by = {}
    for f in setup_findings(p) + dependency_findings(p):
        by.setdefault(f.check, []).append(f)
    return by


def _make(cid, title):
    def check(root) -> bool | str:
        found = _results(str(root)).get(cid)
        if not found:
            return True
        return "; ".join(f"{f.file}{':' + str(f.line) if f.line else ''} {f.message}" for f in found[:5])
    cls = type(cid.replace("-", "_"), (), {"__doc__": title, "family": "shiftleft", "requires": set(),
                                          "url": "https://cleandataengineering.ai/learn/shift-left/whats-missing/",
                                          "check": staticmethod(check)})
    return cls()


def repo_review_checks(list_all: bool = True, root=None) -> dict:
    return {cid: _make(cid, t) for cid, t in TITLES.items()}


def repo_review_families(pyproject=None) -> dict:
    return {"shiftleft": {"name": "Shift-left: data repository setup", "order": 50}}
