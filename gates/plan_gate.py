#!/usr/bin/env python3
"""Plan gate for the IAI demo.

Reports what the apply will change. For greenfield (the only case in demo v1)
everything is new: N to add, 0 to change, 0 to destroy. The gate counts
resources by scanning the generated HCL, and — if tofu (OpenTofu) happens to be
on the host — attempts `tofu validate` as a bonus signal. It never requires
cloud credentials and never blocks: the plan gate is informational.

Modes:
  --path <terraform_dir>

Exit codes:
  0  always (plan gate is informational; it never blocks the pipeline)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

_RESOURCE_RE = re.compile(r'^resource\s+"[^"]+"\s+"[^"]+"', re.MULTILINE)

EXIT_OK = 0


def count_resources(terraform_dir: str) -> int:
    """Count `resource "..." "..."` declarations across *.tf files in dir."""
    total = 0
    if not os.path.isdir(terraform_dir):
        return 0
    for entry in sorted(os.listdir(terraform_dir)):
        if not entry.endswith(".tf"):
            continue
        full = os.path.join(terraform_dir, entry)
        try:
            with open(full, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        total += len(_RESOURCE_RE.findall(text))
    return total


def _tofu_validate(terraform_dir: str) -> str:
    """Return 'pass' | 'fail' | 'unavailable' | 'not_initialized'."""
    if shutil.which("tofu") is None:
        return "unavailable"
    if not os.path.isdir(os.path.join(terraform_dir, ".terraform")):
        # `tofu validate` requires an initialized working dir.
        return "not_initialized"
    proc = subprocess.run(
        ["tofu", "-chdir=" + terraform_dir, "validate"],
        capture_output=True,
        text=True,
    )
    return "pass" if proc.returncode == 0 else "fail"


def run_path(terraform_dir: str) -> dict:
    """Library entry point: evaluate the plan gate, return the result dict."""
    resource_count = count_resources(terraform_dir)
    tofu_val = _tofu_validate(terraform_dir)
    return {
        "status": "pass",  # greenfield: nothing to destroy, never blocks
        "resource_count": resource_count,
        "to_add": resource_count,
        "to_change": 0,
        "to_destroy": 0,
        "tofu_validate": tofu_val,
        "message": f"{resource_count} resources to add",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="IAI plan gate (greenfield, OpenTofu).")
    parser.add_argument("--path", required=True, help="OpenTofu/HCL directory.")
    args = parser.parse_args(argv)

    result = run_path(args.path)
    print(json.dumps(result, indent=2))
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
