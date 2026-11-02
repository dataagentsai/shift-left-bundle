"""Table-driven tests for scripts/lint.py.  Run: uv run --with pytest --with pyyaml pytest -q"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lint  # noqa: E402

VOCAB = lint.load_vocab()
DROP = object()

GOOD = {
    "_file": "COST-CODE", "id": "SL-COST-CODE-01", "status": "draft", "since": "0.1.0",
    "title": "Whole dataset pulled into one process", "level": "MUST",
    "statement": "Code MUST NOT collect a whole dataset.", "why": "It crashed.", "fix": "Limit first.",
    "stage": "commit", "gate": "warn", "found_by": "static", "applies_to": ["pyspark"], "cost_impact": "high",
    "dac": ["COST-02"], "cites": [{"standard": "CWE", "ref": "CWE-89"}], "related": [],
}


def with_(**changes):
    r = copy.deepcopy(GOOD)
    for k, v in changes.items():
        if v is DROP:
            r.pop(k)
        else:
            r[k] = v
    return r


CASES = [
    # (name, record, expected error fragment, or None for clean)
    ("valid record", with_(), None),
    ("null cost impact is allowed", with_(cost_impact=None), None),
    ("empty lists are allowed", with_(dac=[], cites=[]), None),
    ("SHOULD may warn", with_(level="SHOULD", statement="Code SHOULD NOT collect."), None),
    ("MAY may report", with_(level="MAY", statement="Code MAY collect.", gate="report"), None),
    ("missing statement", with_(statement=DROP), "missing 'statement'"),
    ("missing fix", with_(fix=""), "missing 'fix'"),
    ("missing cost_impact key", with_(cost_impact=DROP), "missing 'cost_impact'"),
    ("dac not a list", with_(dac="COST-02"), "'dac' must be a list"),
    ("id without prefix", with_(id="COST-CODE-01"), "id must look like"),
    ("id with unknown family", with_(id="SL-FOO-01"), "id must look like"),
    ("id with one digit", with_(id="SL-COST-CODE-1"), "id must look like"),
    ("family in wrong file", with_(_file="SEC"), "is in file SEC.yaml"),
    ("unknown status", with_(status="final"), "unknown status"),
    ("unknown level", with_(level="MUST NOT"), "level must be"),
    ("statement lacks level word", with_(statement="Code should not collect."), "does not use its level word"),
    ("unknown stage", with_(stage="deploy"), "unknown stage"),
    ("unknown gate", with_(gate="fail"), "unknown gate"),
    ("SHOULD can't start at block", with_(level="SHOULD", statement="Code SHOULD NOT collect.", gate="block"), "only MUST checks"),
    ("MUST may block", with_(gate="block"), None),
    ("unknown found_by", with_(found_by="ai"), "unknown found_by"),
    ("bad cost impact", with_(cost_impact="huge"), "cost_impact must be"),
    ("unknown DAC id", with_(dac=["COST-99"]), "not in core/dac_ids.yaml"),
    ("cite unknown standard", with_(cites=[{"standard": "NIST", "ref": "x"}]), "unknown standard"),
    ("cite without ref", with_(cites=[{"standard": "CWE"}]), "has no ref"),
    ("related missing", with_(related=["SL-SEC-99"]), "does not exist"),
    ("related to itself", with_(related=["SL-COST-CODE-01"]), "relates to itself"),
    ("platform name in statement", with_(statement="Code MUST NOT call collect on a Spark dataset."), "product name 'spark'"),
    ("tool name in fix", with_(fix="Run ruff."), "product name 'ruff'"),
    ("product name in title", with_(title="Databricks job"), "product name 'databricks'"),
    ("missing applies_to", with_(applies_to=[]), "missing 'applies_to'"),
    ("applies_to not a list", with_(applies_to="sql"), "'applies_to' must be a list"),
    ("unknown artifact", with_(applies_to=["cobol"]), "unknown artifact"),
    ("dbt is fine in applies_to", with_(applies_to=["dbt", "metric-view"]), None),
    ("dbt in statement is a product name", with_(statement="Code MUST NOT skip dbt tests."), "product name 'dbt'"),
    ("part of a longer word is fine", with_(why="A sparkline chart was slow; the queue grew."), None),
]


@pytest.mark.parametrize("name, rec, expect", CASES, ids=[c[0] for c in CASES])
def test_lint_record(name, rec, expect):
    errs = lint.lint([rec], VOCAB)
    if expect is None:
        assert errs == []
    else:
        assert any(expect in e for e in errs), errs


def test_duplicate_id():
    errs = lint.lint([with_(), with_()], VOCAB)
    assert any("duplicate id" in e for e in errs)


TOOLS = {"ruff": {}, "costlens": {}}
BIND_CASES = [
    ("valid binding", {"SL-COST-CODE-01": {"tool": "ruff", "rules": ["S608"], "status": "adopt"}}, None),
    ("check not bound", {}, "no entry for SL-COST-CODE-01"),
    ("unknown check bound", {"SL-COST-CODE-01": {"tool": "ruff", "rules": ["x"], "status": "adopt"},
                             "SL-SEC-77": {"tool": "ruff", "rules": ["x"], "status": "adopt"}}, "not a check in the catalog"),
    ("undeclared tool", {"SL-COST-CODE-01": {"tool": "sonar", "rules": ["x"], "status": "adopt"}}, "not declared under tools"),
    ("no rules", {"SL-COST-CODE-01": {"tool": "ruff", "rules": [], "status": "adopt"}}, "no rules"),
    ("unknown status", {"SL-COST-CODE-01": {"tool": "ruff", "rules": ["x"], "status": "maybe"}}, "status must be one of"),
    ("entry not a mapping", {"SL-COST-CODE-01": "ruff"}, "must be a mapping"),
]


@pytest.mark.parametrize("name, checks, expect", BIND_CASES, ids=[c[0] for c in BIND_CASES])
def test_lint_bindings(name, checks, expect):
    errs = lint.lint_bindings([with_()], {"test": {"tools": TOOLS, "checks": checks}})
    if expect is None:
        assert errs == []
    else:
        assert any(expect in e for e in errs), errs


RUFF_CASES = [
    ("valid profiles", {"starter": ["S"], "strict": ["S", "D"]}, {"S": "SL-COST-CODE-01", "D": "SL-COST-CODE-01", "S608": "SL-COST-CODE-01"}, None),
    ("starter wider than strict", {"starter": ["S", "X"], "strict": ["S"]}, {"S": "SL-COST-CODE-01"}, "starter profile has groups not in strict"),
    ("group without a mapping", {"starter": ["S"], "strict": ["S", "D"]}, {"S": "SL-COST-CODE-01"}, "Ruff group D has no ruff_map entry"),
    ("mapping to a missing check", {"starter": ["S"], "strict": ["S"]}, {"S": "SL-SEC-99"}, "is not a check"),
    ("mapping outside the profile", {"starter": ["S"], "strict": ["S"]}, {"S": "SL-COST-CODE-01", "ANN001": "SL-COST-CODE-01"}, "outside the strict profile"),
]


@pytest.mark.parametrize("name, prof, rmap, expect", RUFF_CASES, ids=[c[0] for c in RUFF_CASES])
def test_lint_ruff(name, prof, rmap, expect):
    errs = lint.lint_ruff([with_()], {"test": {"ruff_profiles": prof, "ruff_map": rmap}})
    if expect is None:
        assert errs == []
    else:
        assert any(expect in e for e in errs), errs


def test_real_catalog_is_clean():
    recs = lint.load_checks()
    assert len(recs) >= 60
    assert lint.lint(recs, VOCAB) == []
    b = lint.load_bindings()
    assert lint.lint_bindings(recs, b) == []
    assert lint.lint_ruff(recs, b) == []


def test_every_family_has_checks():
    have = {r["_file"] for r in lint.load_checks()}
    assert have == set(VOCAB["families"])
