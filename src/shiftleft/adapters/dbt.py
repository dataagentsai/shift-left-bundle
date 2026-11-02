"""dbt structure via dbt's own parser and dbt-bouncer (SL-TEST-07/08, SL-CLEAN-27/28, SL-SETUP-10).

`dbt parse` needs no warehouse. It runs with --target-path and --log-path in a temporary folder, so nothing is written
into the repository. env_var() names used by the profile get dummy values, because parsing never connects.
A finding points where the fix goes: the model's properties file if it has one, else the model's SQL file."""
import json
import os
import re
import tempfile
from pathlib import Path

from ..model import Finding, ScanResult
from ._util import files, line_of, rel, run, which

NAME = "dbt-bouncer"
STAGES = ("pr", "nightly")


def projects(project: Path):
    return [p.parent for p in files(project, "dbt_project.yml")]


def parse_results(items, manifest, dbt_dir, project, rmap):
    nodes = manifest.get("nodes", {})
    out = []
    for it in items or []:
        if it.get("outcome") != "failed":
            continue
        check_name = it["check_run_id"].split(":")[0]
        cid = rmap.get(check_name)
        if not cid:
            continue
        node = nodes.get(it.get("unique_id"), {})
        sql_file = rel(project, dbt_dir / (it.get("file_path") or node.get("original_file_path", "")))
        file, line = sql_file, None
        if cid in ("SL-TEST-07", "SL-SETUP-10") and node.get("patch_path"):
            file = rel(project, dbt_dir / node["patch_path"].split("://", 1)[-1])
            line = line_of(project, file, f"- name: {node.get('name')}")
        elif cid in ("SL-CLEAN-27", "SL-CLEAN-28"):
            line = line_of(project, sql_file, "source(" if cid == "SL-CLEAN-28" else "from ")
        out.append(Finding(cid, file, line, NAME, check_name, it.get("failure_message") or check_name))
    return out


def scan(ctx):
    dbt, bouncer = which("dbt", ctx), which("dbt-bouncer", ctx)
    found = projects(ctx.project)
    if not found:
        return ScanResult(NAME)
    if not dbt or not bouncer:
        return ScanResult(NAME, missing=True)
    from ..catalog import BUNDLE
    cfg_template = (BUNDLE / "templates" / "dbt-bouncer.yml").read_text()
    out, notes = [], []
    for d in found:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, DBT_SEND_ANONYMOUS_USAGE_STATS="false")
            prof = d / "profiles.yml"
            for var in re.findall(r"env_var\(\s*['\"](\w+)['\"]", prof.read_text() if prof.exists() else ""):
                env.setdefault(var, "dummy")
            target = Path(tmp) / "target"
            cmd = [dbt, "parse", "--target-path", str(target), "--log-path", str(Path(tmp) / "logs")]
            if prof.exists():                                   # copy, so dbt writes .user.yml into tmp, not the repo
                (Path(tmp) / "profiles.yml").write_text(prof.read_text())
                cmd += ["--profiles-dir", tmp]
            import subprocess
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, env=env, check=False)
            if not (target / "manifest.json").exists():
                notes.append(f"{rel(ctx.project, d)}: dbt parse failed, dbt checks skipped ({(r.stdout + r.stderr).strip().splitlines()[-1][:120] if (r.stdout + r.stderr).strip() else 'no output'})")
                continue
            cfg = Path(tmp) / "bouncer.yml"
            cfg.write_text(re.sub(r"^dbt_artifacts_dir:.*$", f"dbt_artifacts_dir: {target}", cfg_template, flags=re.M))
            res = Path(tmp) / "res.json"
            run([bouncer, "run", "--config-file", str(cfg), "--output-file", str(res), "--output-format", "json"], d)
            if not res.exists():
                notes.append(f"{rel(ctx.project, d)}: dbt-bouncer produced no results")
                continue
            out += parse_results(json.loads(res.read_text()), json.loads((target / "manifest.json").read_text()), d,
                                 ctx.project, ctx.binding.get("dbt_bouncer_map") or {})
    return ScanResult(NAME, out, notes)
