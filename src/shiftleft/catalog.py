"""Load the catalog, gates and a binding from the bundle folder."""
from pathlib import Path

import yaml

_PKG = Path(__file__).resolve().parent / "_bundle"      # installed: data shipped inside the package
BUNDLE = _PKG if _PKG.exists() else Path(__file__).resolve().parents[2]   # source checkout: the repository root


def _y(p):
    return yaml.safe_load(Path(p).read_text())


def load(binding: str = "databricks", root: Path = BUNDLE):
    checks = {}
    for f in sorted((root / "catalog" / "checks").glob("*.yaml")):
        for r in _y(f) or []:
            checks[r["id"]] = r
    return checks, _y(root / "core" / "gates.yaml"), _y(root / "bindings" / f"{binding}.yaml")
