"""Table-driven tests for the runner: mapping, stages, fingerprints, suppression, gates, adapters, SARIF."""
import json
from pathlib import Path

import pytest

from shiftleft import catalog, engine, report
from shiftleft.adapters import complexipy, gitleaks, osv, ruff, sqlfluff, vulture
from shiftleft.model import Context, Finding

CHECKS, GATES, BINDING = catalog.load("databricks")


def ctx(tmp_path, stage="all"):
    return Context(tmp_path, stage, BINDING, CHECKS, GATES)


MAP_CASES = [
    # tool, rule, expected check
    ("ruff", "S608", "SL-SEC-01"),
    ("ruff", "S105", "SL-SECRET-01"),
    ("ruff", "S324", "SL-SEC-10"),          # unmapped S rule falls back to the group
    ("ruff", "PLR0913", "SL-CLEAN-02"),     # specific PLR beats PLR beats PL
    ("ruff", "PLR1714", "SL-CLEAN-12"),
    ("ruff", "PLW0603", "SL-CLEAN-20"),
    ("ruff", "F403", "SL-CLEAN-15"),
    ("ruff", "F821", "SL-STYLE-02"),
    ("sqlfluff", "AM04", "SL-COST-CODE-13"),
    ("sqlfluff", "AM08", "SL-COST-CODE-14"),
    ("sqlfluff", "LT02", None),             # no map entry: the adapter's default applies
]


@pytest.mark.parametrize("tool, rule, expected", MAP_CASES, ids=[f"{c[0]} {c[1]}" for c in MAP_CASES])
def test_rule_to_check(tmp_path, tool, rule, expected):
    assert ctx(tmp_path).check_for(tool, rule) == expected


STAGE_CASES = [
    # run stage, check stage, reported?
    ("commit", "commit", True), ("commit", "pr", False), ("pr", "commit", True), ("pr", "nightly", False),
    ("nightly", "pr", True), ("nightly", "predeploy", False), ("predeploy", "predeploy", True),
    ("predeploy", "commit", False), ("all", "predeploy", True), ("all", "nightly", True),
]


@pytest.mark.parametrize("run, chk, expected", STAGE_CASES, ids=[f"{a} runs {b}" for a, b, _ in STAGE_CASES])
def test_stage_includes(run, chk, expected):
    assert engine.stage_includes(run, chk) is expected


def test_fingerprint_survives_moves_not_edits():
    a = engine.fingerprint("SL-SEC-01", "a.py", "  x = eval(s)")
    assert a == engine.fingerprint("SL-SEC-01", "a.py", "x=eval(s)")         # whitespace and line number don't matter
    assert a != engine.fingerprint("SL-SEC-01", "a.py", "x = eval(t)")       # the code changed
    assert a != engine.fingerprint("SL-SEC-02", "a.py", "  x = eval(s)")     # another check


SUPPRESS_CASES = [
    # source lines, finding line, check, allowed?
    (["x = eval(s)  # shiftleft: allow SL-SEC-02 -- rules come from our own config"], 1, "SL-SEC-02", True),
    (["# shiftleft: allow SL-SEC-02 -- trusted input", "x = eval(s)"], 2, "SL-SEC-02", True),
    (["x = eval(s)  # shiftleft: allow SL-SEC-02"], 1, "SL-SEC-02", False),              # no reason: not allowed
    (["x = eval(s)  # shiftleft: allow SL-SEC-03 -- wrong id"], 1, "SL-SEC-02", False),
    (["x = eval(s)  # shiftleft: allow SL-SEC-02, SL-SEC-03 -- two ids"], 1, "SL-SEC-03", True),
    (["# shiftleft: allow SL-SEC-02 -- too far", "", "x = eval(s)"], 3, "SL-SEC-02", False),
]


@pytest.mark.parametrize("lines, line, check, allowed", SUPPRESS_CASES, ids=range(len(SUPPRESS_CASES)))
def test_suppression(tmp_path, lines, line, check, allowed):
    (tmp_path / "a.py").write_text("\n".join(lines) + "\n")
    assert engine.suppression(tmp_path, Finding(check, "a.py", line, "t", "r", ""))[0] is allowed


def F(check, file="a.py", line=1, gate=""):
    return Finding(check, file, line, "t", "r", "m", gate=gate)


FINAL_CASES = [
    # name, stage, findings, baseline?, expected (check, gate, status) list, should fail
    ("block finding fails", "pr", [F("SL-SEC-01")], False, [("SL-SEC-01", "block", "new")], True),
    ("warn finding passes", "pr", [F("SL-CLEAN-01")], False, [("SL-CLEAN-01", "warn", "new")], False),
    ("baselined block passes", "pr", [F("SL-SEC-01")], True, [("SL-SEC-01", "block", "baseline")], False),
    ("unknown check dropped", "pr", [F("SL-NOPE-01")], False, [], False),
    ("pr check not run on commit", "commit", [F("SL-DEP-01")], False, [], False),
    ("adapter may lower a gate", "pr", [F("SL-DEP-01", gate="warn")], False, [("SL-DEP-01", "warn", "new")], False),
    ("adapter may not raise a gate", "pr", [F("SL-CLEAN-01", gate="block")], False, [("SL-CLEAN-01", "warn", "new")], False),
    ("duplicates collapse", "pr", [F("SL-SEC-01"), F("SL-SEC-01")], False, [("SL-SEC-01", "block", "new")], True),
]


@pytest.mark.parametrize("name, stage, findings, base, expected, fails", FINAL_CASES, ids=[c[0] for c in FINAL_CASES])
def test_finalise(tmp_path, name, stage, findings, base, expected, fails):
    (tmp_path / "a.py").write_text("x = eval(s)\n")
    c = ctx(tmp_path, stage)
    baseline = frozenset(engine.fingerprint(f.check, f.file, "x = eval(s)") for f in findings) if base else frozenset()
    out, _ = engine.finalise(findings, c, baseline)
    assert [(f.check, f.gate, f.status) for f in out] == expected
    assert engine.should_fail(out) is fails


# ---- contract test: every adapter parser turns recorded tool output into findings with real catalog ids
RUFF_OUT = json.dumps([{"code": "S608", "filename": "a.py", "location": {"row": 3}, "message": "sql"},
                       {"code": None, "filename": "a.py", "location": {"row": 1}, "message": "syntax error"}])
SQLFLUFF_OUT = json.dumps([{"filepath": "q.sql", "violations": [
    {"code": "AM04", "start_line_no": 2, "description": "star"}, {"code": "LT02", "start_line_no": 3, "description": "indent"},
    {"code": "PRS", "start_line_no": 1, "description": "parse"}]}])
OSV_OUT = json.dumps({"results": [{"source": {"path": "requirements.txt"}, "packages": [
    {"package": {"name": "requests", "version": "2.19.0"}, "vulnerabilities": [{"id": "GHSA-x"}], "groups": [{"max_severity": "7.5"}]},
    {"package": {"name": "pyyaml", "version": "5.3"}, "vulnerabilities": [{"id": "GHSA-y"}], "groups": [{"max_severity": "5.0"}]}]}]})
CONTRACT = [
    ("ruff", lambda c: ruff.parse(RUFF_OUT, c), ["SL-SEC-01", "SL-STYLE-02"]),
    ("sqlfluff", lambda c: sqlfluff.parse(SQLFLUFF_OUT, c)[0], ["SL-COST-CODE-13", "SL-STYLE-03"]),
    ("gitleaks", lambda c: gitleaks.parse([{"File": "a.py", "StartLine": 4, "RuleID": "x"}, {"File": "databricks.yml", "StartLine": 8, "RuleID": "y"}], c),
     ["SL-SECRET-01", "SL-SECRET-03"]),
    ("osv-scanner", lambda c: osv.parse(OSV_OUT, c), ["SL-DEP-01", "SL-DEP-01"]),
    ("vulture", lambda c: vulture.parse("a.py:3: unused function 'f' (60% confidence)\na.py:1: unused import 'os' (90% confidence)", c), ["SL-CPLX-04"]),
    ("complexipy", lambda c: complexipy.parse([{"path": "a.py", "function_name": "f", "complexity": 40}, {"path": "a.py", "function_name": "g", "complexity": 2}], c),
     ["SL-CPLX-02"]),
]


@pytest.mark.parametrize("tool, parse, expected", CONTRACT, ids=[c[0] for c in CONTRACT])
def test_adapter_contract(tmp_path, tool, parse, expected):
    (tmp_path / "a.py").write_text("def f():\n    pass\n")
    (tmp_path / "requirements.txt").write_text("requests==2.19.0\nPyYAML==5.3\n")
    found = parse(ctx(tmp_path))
    assert [f.check for f in found] == expected
    assert all(f.check in CHECKS and f.tool and isinstance(f.file, str) for f in found)


def test_sqlfluff_parse_errors_become_notes(tmp_path):
    _, notes = sqlfluff.parse(SQLFLUFF_OUT, ctx(tmp_path))
    assert notes == ["q.sql:1: sqlfluff could not parse (PRS)"]


def test_osv_medium_is_lowered_to_warn_and_line_found_case_insensitively(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.19.0\nPyYAML==5.3\n")
    hi, med = osv.parse(OSV_OUT, ctx(tmp_path))
    assert (hi.gate, hi.line, med.gate, med.line) == ("", 1, "warn", 2)


def test_sarif_shape(tmp_path):
    (tmp_path / "a.py").write_text("x = eval(s)  # shiftleft: allow SL-SEC-02 -- trusted\n")
    out, _ = engine.finalise([F("SL-SEC-02"), F("SL-CLEAN-01", line=1)], ctx(tmp_path, "pr"))
    s = report.to_sarif(out, CHECKS)
    res = {r["ruleId"]: r for r in s["runs"][0]["results"]}
    assert s["version"] == "2.1.0"
    assert res["SL-SEC-02"]["level"] == "error" and res["SL-SEC-02"]["suppressions"][0]["justification"] == "trusted"
    assert res["SL-CLEAN-01"]["level"] == "warning"
    assert {r["id"] for r in s["runs"][0]["tool"]["driver"]["rules"]} == {"SL-SEC-02", "SL-CLEAN-01"}
    assert not engine.should_fail(out)                     # the only block finding is suppressed with a reason


def test_every_adapter_is_declared_in_the_binding():
    from shiftleft.adapters import REGISTRY
    assert set(REGISTRY) <= set(BINDING["tools"]), set(REGISTRY) - set(BINDING["tools"])
