"""Our own rules on Databricks bundle config that CostLens does not have: cost tags, timeouts, worker limits."""
import re
from pathlib import Path

import yaml

from ..model import Finding, ScanResult
from ._util import rel

NAME = "bundle-rules"
STAGES = ("predeploy",)


def resource_files(project: Path):
    root = project / "databricks.yml"
    if not root.exists():
        return []
    doc = yaml.safe_load(root.read_text()) or {}
    out = [root]
    for pat in doc.get("include") or []:
        out += sorted(project.glob(pat))
    return out


def _line(text, key):
    m = re.search(rf"^\s*{re.escape(key)}:", text, re.M)
    return text[: m.start()].count("\n") + 1 if m else None


def findings(project: Path):
    out = []
    for p in resource_files(project):
        text = p.read_text()
        res = (yaml.safe_load(text) or {}).get("resources") or {}
        file = rel(project, p)
        for key, job in (res.get("jobs") or {}).items():
            ln = _line(text, key)
            if not job.get("tags"):
                out.append(Finding("SL-COST-CONFIG-03", file, ln, NAME, "job-no-tags", f"job {key} has no tags (team, product)"))
            if not job.get("timeout_seconds"):
                out.append(Finding("SL-COST-CONFIG-08", file, ln, NAME, "job-no-timeout", f"job {key} has no timeout_seconds"))
            for jc in job.get("job_clusters") or []:
                nc = jc.get("new_cluster") or {}
                auto = nc.get("autoscale")
                if auto and not auto.get("max_workers"):
                    out.append(Finding("SL-COST-CONFIG-04", file, _line(text, "autoscale"), NAME, "autoscale-no-max",
                                       f"job {key}: autoscale has no max_workers"))
        for key, cl in (res.get("clusters") or {}).items():
            if not cl.get("autotermination_minutes"):
                out.append(Finding("SL-COST-CONFIG-01", file, _line(text, key), NAME, "cluster-no-autotermination",
                                   f"cluster {key} never shuts itself down"))
            if not cl.get("custom_tags"):
                out.append(Finding("SL-COST-CONFIG-03", file, _line(text, key), NAME, "cluster-no-tags", f"cluster {key} has no custom_tags"))
    return out


def scan(ctx):
    return ScanResult(NAME, findings(ctx.project))
