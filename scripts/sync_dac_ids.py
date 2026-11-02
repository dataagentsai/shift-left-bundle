# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Refresh core/dac_ids.yaml from a local checkout of data-platform-catalog.

    uv run scripts/sync_dac_ids.py [path-to-data-platform-catalog]
"""
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "data-platform-catalog")
    ids = {}
    for f in sorted((src / "dac" / "obligations").glob("*.yaml")):
        for r in yaml.safe_load(f.read_text()) or []:
            ids[r["id"]] = r["title"]
    commit = subprocess.run(["git", "-C", str(src), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    head = ("# DAC obligation ids this catalog may link to, copied from dataagentsai/data-platform-catalog.\n"
            f"# Source commit: {commit or 'unknown'}. Refresh with: uv run scripts/sync_dac_ids.py\n")
    (ROOT / "core" / "dac_ids.yaml").write_text(head + yaml.safe_dump(dict(sorted(ids.items())), sort_keys=False, allow_unicode=True, width=200))
    print(f"{len(ids)} DAC ids from {src} @ {commit}")


if __name__ == "__main__":
    main()
