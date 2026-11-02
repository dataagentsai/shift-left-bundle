"""The shapes that move between adapters, the engine and reporters."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

STAGE_ORDER = {"commit": 0, "pr": 1, "nightly": 2}   # predeploy is its own track


@dataclass
class Finding:
    check: str                      # catalog id, e.g. SL-SEC-01
    file: str                       # relative to the project root; "." for the repository
    line: Optional[int]
    tool: str
    tool_rule: str
    message: str
    gate: str = ""                  # "" = take the catalog gate; an adapter may set a lower one
    status: str = "new"             # new | baseline | suppressed
    fingerprint: str = ""
    suppress_reason: str = ""


@dataclass
class ScanResult:
    tool: str
    findings: list = field(default_factory=list)
    notes: list = field(default_factory=list)        # e.g. files a tool could not parse
    missing: bool = False                            # the tool is not installed; reported, never silent


@dataclass
class Context:
    project: Path
    stage: str                      # commit | pr | nightly | predeploy | all
    binding: dict
    checks: dict                    # id -> check record
    gates: dict
    tool_paths: list = field(default_factory=list)  # extra folders to find tool binaries in

    def check_for(self, tool: str, rule: str, default: Optional[str] = None) -> Optional[str]:
        """Map a tool's rule to a catalog check: binding `<tool>_map` (longest prefix wins), else default."""
        rmap = self.binding.get(f"{tool}_map") or {}
        for k in sorted(rmap, key=len, reverse=True):
            if rule.startswith(k):
                return rmap[k]
        return default
