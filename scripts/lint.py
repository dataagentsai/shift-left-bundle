# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Check the catalog and bindings follow the spec rules. Exit 1 on any error.

    uv run scripts/lint.py

Rules:
  R1  required fields present; lists are lists
  R2  id is SL-<FAMILY>-NN, the family matches the file, ids are unique
  R3  status, level, stage, gate, found_by and cost_impact use the vocabulary
  R4  the statement uses its own level word (MUST, SHOULD, MAY)
  R5  only MUST checks may start at gate "block" (noise kills adoption, decision D5)
  R6  dac links exist in core/dac_ids.yaml; cites name a known standard and give a ref
  R7  related ids exist and don't point to themselves
  R8  no product or tool names in normative text (they belong in bindings/)
  R9  every check has exactly one binding entry per binding file, and nothing else is bound
  R10 binding entries name a declared tool, at least one rule, and a known status
  R11 applies_to is a non-empty list of artifacts from core/artifacts.yaml
  R12 every Ruff profile group is mapped to a check, every mapped check exists, and every
      ruff_map key falls inside the strict profile
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

PRODUCTS = [
    # platforms and data products (same list as data-platform-catalog/scripts/lint.py)
    "databricks", "spark", "pyspark", "delta lake", "delta table", "unity catalog", "lakeflow", "auto loader",
    "autoloader", "dlt", "snowflake", "snowpipe", "bigquery", "redshift", "synapse", "fabric", "onelake",
    "power bi", "tableau", "looker", "adf", "data factory", "airflow", "dbt", "kafka", "kinesis", "event hub",
    "glue", "emr", "dataproc", "aws", "azure", "gcp", "google cloud", "s3", "adls", "iceberg", "hudi",
    "great expectations", "deequ", "soda", "terraform", "github", "gitlab", "jenkins", "jira", "confluence",
    # tools this bundle binds to
    "ruff", "sqlfluff", "sqlglot", "opengrep", "semgrep", "gitleaks", "pip-audit", "pip-licenses", "checkov",
    "pytest", "coverage.py", "diff-cover", "complexipy", "mutmut", "hypothesis", "vulture", "pylint", "flake8",
    "bandit", "import-linter", "repo-review", "scorecard", "sonarqube", "sonar", "pre-commit", "costlens",
    "pandas", "pyarrow", "dbutils", "uv", "poetry",
]
TEXT_FIELDS = ["title", "statement", "why", "fix"]
REQUIRED = ["id", "status", "since", "title", "level", "statement", "why", "fix", "stage", "gate", "found_by", "applies_to"]
LISTS = ["dac", "cites", "related", "applies_to"]
STATUSES = {"draft", "active", "deprecated"}
LEVELS = {"MUST", "SHOULD", "MAY"}
FOUND_BY = {"static", "plan", "test", "repo"}
COST_IMPACT = {"high", "medium", "low", None}
BIND_STATUS = {"adopt", "cost", "build", "trial"}


def y(p):
    return yaml.safe_load(Path(p).read_text())


def load_vocab(root=ROOT):
    return {"families": y(root / "core/families.yaml"), "stages": y(root / "core/stages.yaml"),
            "gates": set(y(root / "core/gates.yaml")["levels"]), "standards": y(root / "core/standards.yaml"),
            "dac": set(y(root / "core/dac_ids.yaml")), "artifacts": set(y(root / "core/artifacts.yaml"))}


def load_checks(root=ROOT):
    recs = []
    for f in sorted((root / "catalog" / "checks").glob("*.yaml")):
        for r in y(f) or []:
            r["_file"] = f.stem
            recs.append(r)
    return recs


def load_bindings(root=ROOT):
    return {f.stem: y(f) for f in sorted((root / "bindings").glob("*.yaml"))}


def id_re(families):
    return re.compile(r"^SL-(" + "|".join(re.escape(f) for f in families) + r")-(\d{2})$")


def lint(recs, vocab):
    errs = []
    ids = [r.get("id") for r in recs]
    pat = id_re(vocab["families"])
    for r in recs:
        w = f"{r.get('_file', '?')}:{r.get('id', '?')}"
        for k in REQUIRED:
            if r.get(k) in (None, "", []):
                errs.append(f"{w}: missing '{k}'")
        for k in LISTS:
            if not isinstance(r.get(k), list):
                errs.append(f"{w}: '{k}' must be a list (empty is allowed)")
        if "cost_impact" not in r:
            errs.append(f"{w}: missing 'cost_impact' (use null when it has none)")
        m = pat.match(r.get("id") or "")
        if r.get("id") and not m:
            errs.append(f"{w}: id must look like SL-<FAMILY>-01 with a family from core/families.yaml")
        elif m and r.get("_file") and m.group(1) != r["_file"]:
            errs.append(f"{w}: family {m.group(1)} is in file {r['_file']}.yaml")
        if r.get("id") and ids.count(r["id"]) > 1:
            errs.append(f"{w}: duplicate id")
        if r.get("status") and r["status"] not in STATUSES:
            errs.append(f"{w}: unknown status '{r['status']}'")
        lv = r.get("level")
        if lv and lv not in LEVELS:
            errs.append(f"{w}: level must be MUST, SHOULD or MAY")
        elif lv and lv not in (r.get("statement") or ""):
            errs.append(f"{w}: statement does not use its level word '{lv}'")
        if r.get("stage") and r["stage"] not in vocab["stages"]:
            errs.append(f"{w}: unknown stage '{r['stage']}'")
        if r.get("gate") and r["gate"] not in vocab["gates"]:
            errs.append(f"{w}: unknown gate '{r['gate']}'")
        if r.get("gate") == "block" and lv != "MUST":
            errs.append(f"{w}: only MUST checks may start at gate 'block'")
        if r.get("found_by") and r["found_by"] not in FOUND_BY:
            errs.append(f"{w}: unknown found_by '{r['found_by']}'")
        if r.get("cost_impact") not in COST_IMPACT:
            errs.append(f"{w}: cost_impact must be high, medium, low or null")
        for a in r.get("applies_to") or [] if isinstance(r.get("applies_to"), list) else []:
            if a not in vocab["artifacts"]:
                errs.append(f"{w}: unknown artifact '{a}' in applies_to")
        for d in r.get("dac") or []:
            if d not in vocab["dac"]:
                errs.append(f"{w}: DAC id '{d}' not in core/dac_ids.yaml")
        for c in r.get("cites") or []:
            if not isinstance(c, dict) or c.get("standard") not in vocab["standards"]:
                errs.append(f"{w}: cite to unknown standard {c!r}")
            elif not c.get("ref"):
                errs.append(f"{w}: cite to {c['standard']} has no ref")
        for x in r.get("related") or []:
            if x == r.get("id"):
                errs.append(f"{w}: relates to itself")
            elif x not in ids:
                errs.append(f"{w}: related id '{x}' does not exist")
        for k in TEXT_FIELDS:
            low = (r.get(k) or "").lower()
            for p in PRODUCTS:
                if re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", low):
                    errs.append(f"{w}: product name '{p}' in {k}")
    return errs


def lint_bindings(recs, bindings):
    errs = []
    ids = {r.get("id") for r in recs}
    for name, b in bindings.items():
        tools = set((b or {}).get("tools") or {})
        checks = (b or {}).get("checks") or {}
        for i in sorted(ids - set(checks)):
            errs.append(f"binding {name}: no entry for {i}")
        for i, e in checks.items():
            w = f"binding {name}:{i}"
            if i not in ids:
                errs.append(f"{w}: not a check in the catalog")
                continue
            if not isinstance(e, dict):
                errs.append(f"{w}: entry must be a mapping")
                continue
            if e.get("tool") not in tools:
                errs.append(f"{w}: tool '{e.get('tool')}' not declared under tools")
            if not e.get("rules"):
                errs.append(f"{w}: no rules")
            if e.get("status") not in BIND_STATUS:
                errs.append(f"{w}: status must be one of {sorted(BIND_STATUS)}")
    return errs


def lint_ruff(recs, bindings):
    errs = []
    ids = {r.get("id") for r in recs}
    for name, b in bindings.items():
        for mk, mv in (b or {}).items():
            if mk.endswith("_map") and mk != "ruff_map":
                for code, cid in (mv or {}).items():
                    if cid not in ids:
                        errs.append(f"binding {name}: {mk} {code} -> {cid} is not a check")
        prof = (b or {}).get("ruff_profiles")
        rmap = (b or {}).get("ruff_map") or {}
        if not prof:
            continue
        strict = set(prof.get("strict") or [])
        if not set(prof.get("starter") or []) <= strict:
            errs.append(f"binding {name}: starter profile has groups not in strict")
        for g in sorted(strict - set(rmap)):
            errs.append(f"binding {name}: Ruff group {g} has no ruff_map entry")
        for code, cid in rmap.items():
            if cid not in ids:
                errs.append(f"binding {name}: ruff_map {code} -> {cid} is not a check")
            if not any(code.startswith(g) for g in strict):
                errs.append(f"binding {name}: ruff_map {code} is outside the strict profile")
    return errs


def main():
    recs = load_checks()
    b = load_bindings()
    errs = lint(recs, load_vocab()) + lint_bindings(recs, b) + lint_ruff(recs, b)
    for e in errs:
        print("ERROR", e)
    print(f"{len(recs)} checks, {len(errs)} errors")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
