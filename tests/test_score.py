"""Table-driven tests for scripts/score.py, plus a check that the real answer key resolves."""
import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import lint  # noqa: E402
import score  # noqa: E402

KEY = {
    "match": {"line_window": 3},
    "planted": [
        {"id": "P1", "check": "SL-SEC-01", "file": "a.py", "anchor": "x", "line": 10},
        {"id": "P2", "check": "SL-TEST-03", "file": "b.py", "anchor": None, "line": None},
        {"id": "P3", "check": "SL-SETUP-01", "file": ".", "anchor": None, "line": None},
    ],
    "traps": [{"id": "T1", "checks": ["SL-SEC-01"], "file": "a.py", "anchor": "y", "line": 40}],
}

CASES = [
    # name, findings, strict caught, family caught, traps hit, unplanned
    ("no findings", [], 0, 0, 0, 0),
    ("exact line", [{"check": "SL-SEC-01", "file": "a.py", "line": 10}], 1, 1, 0, 0),
    ("within the window", [{"check": "SL-SEC-01", "file": "a.py", "line": 13}], 1, 1, 0, 0),
    ("outside the window", [{"check": "SL-SEC-01", "file": "a.py", "line": 14}], 0, 0, 0, 1),
    ("wrong file", [{"check": "SL-SEC-01", "file": "c.py", "line": 10}], 0, 0, 0, 1),
    ("same family, other check", [{"check": "SL-SEC-05", "file": "a.py", "line": 10}], 0, 1, 0, 0),
    ("whole-file entry, any line", [{"check": "SL-TEST-03", "file": "b.py", "line": 99}], 1, 1, 0, 0),
    ("repo entry", [{"check": "SL-SETUP-01", "file": ".", "line": None}], 1, 1, 0, 0),
    ("trap hit", [{"check": "SL-SEC-01", "file": "a.py", "line": 41}], 0, 0, 1, 0),
    ("other check on a trap is not a false alarm", [{"check": "SL-CLEAN-01", "file": "a.py", "line": 40}], 0, 0, 0, 1),
    ("duplicate findings count once", [{"check": "SL-SEC-01", "file": "a.py", "line": 10}] * 2, 1, 1, 0, 0),
]


@pytest.mark.parametrize("name, findings, strict, lenient, traps, unplanned", CASES, ids=[c[0] for c in CASES])
def test_score(name, findings, strict, lenient, traps, unplanned):
    s = score.score(copy.deepcopy(KEY), findings)
    assert (s["strict"], s["lenient"], len(s["trap_hits"]), len(s["unplanned"])) == (strict, lenient, traps, unplanned)


def test_sarif_input(tmp_path):
    sarif = {"runs": [{"results": [{"ruleId": "SL-SEC-01", "locations": [{"physicalLocation": {
        "artifactLocation": {"uri": "examples/sample-project/a.py"}, "region": {"startLine": 11}}}]}]}]}
    p = tmp_path / "f.sarif"
    p.write_text(__import__("json").dumps(sarif))
    assert score.load_findings(p) == [{"check": "SL-SEC-01", "file": "a.py", "line": 11}]


def test_resolve_flags_missing_and_repeated_anchors(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\nx = 1\n")
    key = {"planted": [{"id": "P1", "file": "a.py", "anchor": "x = 1"}, {"id": "P2", "file": "a.py", "anchor": "zzz"},
                       {"id": "P3", "file": "nope.py", "anchor": "x"}], "traps": []}
    errs = score.resolve(key, tmp_path)
    assert any("P1: anchor found 2 times" in e for e in errs)
    assert any("P2: anchor found 0 times" in e for e in errs)
    assert any("P3: file nope.py not found" in e for e in errs)


def test_real_key_resolves_and_uses_real_checks():
    key = yaml.safe_load((ROOT / "tests" / "sample-key.yaml").read_text())
    assert score.resolve(key, ROOT / "examples" / "sample-project") == []
    ids = {r["id"] for r in lint.load_checks()}
    used = {e["check"] for e in key["planted"]} | {c for t in key["traps"] for c in t["checks"]}
    assert used <= ids, used - ids
    families = {score.family(e["check"]) for e in key["planted"]}
    assert families >= set(lint.load_vocab()["families"]) - {"STYLE"}   # every family but style has a planted problem
    assert len(key["traps"]) >= 10
