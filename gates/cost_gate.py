#!/usr/bin/env python3
"""Cost gate for the IAI demo.

Reconciles the Infracost monthly estimate for the payments staging RDS instance
against the FinOps reference figure. The agent surfaces a synthesized result;
the human never reads raw Infracost output.

Spec: research/findings/finops-rds-postgres-cost-reference.md
  Reference: $39.71/mo for db.t3.small (PostgreSQL, ap-southeast-5, Single-AZ)
  Tolerance: +/- $4.00 (~10%)
  Acceptable range: [$35.71, $43.71]

Modes:
  --path <terraform_dir>   run `infracost breakdown` and validate its output
  --fixture <json_file>    validate a pre-captured Infracost JSON file

Exit codes:
  0  pass (cost within range)
  1  fail (cost out of range, or target resource not found)
  2  Infracost not installed (only when --path is used)
"""

import argparse
import json
import shutil
import subprocess
import sys

# --- Constants from the FinOps spec. Do NOT bury these in logic. ---
# Source: research/findings/finops-rds-postgres-cost-reference.md
TARGET_RESOURCE = "aws_db_instance.payments_db"
REFERENCE_COST = 39.71          # USD/month reference (db.t3.small, ap-southeast-5)
TOLERANCE = 4.00                # +/- USD/month (~10%)
RANGE_LOW = REFERENCE_COST - TOLERANCE   # 35.71
RANGE_HIGH = REFERENCE_COST + TOLERANCE  # 43.71

# Exit codes
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_NO_INFRACOST = 2


def run_infracost(terraform_dir):
    """Run `infracost breakdown` and return parsed JSON.

    Exits with EXIT_NO_INFRACOST if the infracost binary is unavailable.
    """
    if shutil.which("infracost") is None:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "infracost is not installed; cannot run --path mode.",
                }
            )
        )
        sys.exit(EXIT_NO_INFRACOST)

    proc = subprocess.run(
        ["infracost", "breakdown", "--path", terraform_dir, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "infracost breakdown failed.",
                    "stderr": proc.stderr.strip(),
                }
            )
        )
        sys.exit(EXIT_FAIL)
    return json.loads(proc.stdout)


def load_fixture(fixture_path):
    """Load a pre-captured Infracost JSON file."""
    with open(fixture_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_resource_cost(infracost_data, resource_name):
    """Return the monthlyCost (float) for the named resource, or None if absent.

    Infracost schema: projects[].breakdown.resources[] with `name` and
    `monthlyCost` fields.
    """
    for project in infracost_data.get("projects", []):
        breakdown = project.get("breakdown") or {}
        for resource in breakdown.get("resources", []):
            if resource.get("name") == resource_name:
                cost = resource.get("monthlyCost")
                if cost is None:
                    return None
                return float(cost)
    return None


def evaluate(infracost_data):
    """Evaluate the cost gate and return a result dict."""
    monthly_cost = find_resource_cost(infracost_data, TARGET_RESOURCE)

    if monthly_cost is None:
        return {
            "status": "fail",
            "resource": TARGET_RESOURCE,
            "monthly_cost": None,
            "reference": REFERENCE_COST,
            "tolerance": TOLERANCE,
            "range": [RANGE_LOW, RANGE_HIGH],
            "message": (
                f"Resource {TARGET_RESOURCE} not found in Infracost output, "
                "or it has no monthlyCost."
            ),
        }

    if RANGE_LOW <= monthly_cost <= RANGE_HIGH:
        status = "pass"
        message = (
            f"RDS instance cost ${monthly_cost:.2f}/mo is within acceptable "
            f"range [${RANGE_LOW:.2f}–${RANGE_HIGH:.2f}]."
        )
    else:
        status = "fail"
        message = (
            f"RDS instance cost ${monthly_cost:.2f}/mo is OUTSIDE acceptable "
            f"range [${RANGE_LOW:.2f}–${RANGE_HIGH:.2f}] "
            f"(reference ${REFERENCE_COST:.2f} ± ${TOLERANCE:.2f})."
        )

    return {
        "status": status,
        "resource": TARGET_RESOURCE,
        "monthly_cost": round(monthly_cost, 2),
        "reference": REFERENCE_COST,
        "tolerance": TOLERANCE,
        "range": [RANGE_LOW, RANGE_HIGH],
        "message": message,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="IAI cost gate (Infracost reconciliation).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="Terraform directory to run infracost against.")
    group.add_argument("--fixture", help="Pre-captured Infracost JSON file to validate.")
    args = parser.parse_args(argv)

    if args.path:
        infracost_data = run_infracost(args.path)
    else:
        infracost_data = load_fixture(args.fixture)

    result = evaluate(infracost_data)
    print(json.dumps(result, indent=2))
    sys.exit(EXIT_PASS if result["status"] == "pass" else EXIT_FAIL)


if __name__ == "__main__":
    main()
