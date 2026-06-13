"""End-to-end gate pipeline for IAI.

Wires the whole vertical slice together: generate IaC from the manifest, run
the three gates (security, cost, plan) against the generated module, and fold
the results into one human-readable approval card.

This is the entry point for both the agent (which then waits for the human to
push the button) and the Tester (which feeds fixtures and asserts on outputs).

Library scope: stdlib + the repo's own modules. No CLI required, though one is
provided for convenience.

Note: the cost gate's `evaluate()` returns a compact dict and does not surface
the per-line cost components. The card needs those sub-figures (compute /
storage), so the pipeline extracts them from the raw Infracost data and
attaches them to the cost result under `components` before synthesis. The
cost gate file itself is left untouched.
"""

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

import boto3

from agent.approval_synthesizer import ApprovalSynthesizer
from agent.iac_generator import IaCGenerator
from agent.manifest_reader import ManifestReader
from gates import plan_gate, security_gate
from gates.cost_gate import evaluate as cost_evaluate
from gates.cost_gate import load_fixture, run_infracost, TARGET_RESOURCE

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GENERATED_DIR = os.path.join(_REPO_ROOT, "terraform", "generated")
_STAGING_DIR = os.path.join(_REPO_ROOT, "terraform", "staging")

# Public paths used by the bot's approval handler.
TERRAFORM_GENERATED_DIR = _GENERATED_DIR
TERRAFORM_SNAPSHOT_DIR = os.path.join(_REPO_ROOT, "terraform", "snapshots")

# Files copied from the staging module so checkov / terraform see a complete
# module (providers + variables) alongside the generated main.tf.
_SUPPORT_FILES = ["providers.tf", "variables.tf"]


def _prepare_generated_module(manifest_path: str, env: str) -> str:
    """Generate main.tf into terraform/generated/ with supporting files.

    Returns the absolute path to the generated main.tf.
    """
    os.makedirs(_GENERATED_DIR, exist_ok=True)
    main_tf = os.path.join(_GENERATED_DIR, "main.tf")
    IaCGenerator(manifest_path, env).generate(main_tf)

    for fname in _SUPPORT_FILES:
        src = os.path.join(_STAGING_DIR, fname)
        dst = os.path.join(_GENERATED_DIR, fname)
        if os.path.exists(src):
            shutil.copyfile(src, dst)
    return main_tf


def _extract_cost_components(infracost_data: dict) -> list:
    """Pull compute + storage sub-figures from raw Infracost data.

    Returns a list of {"label": str, "monthly": float} for the target
    resource's cost components. Labels are normalized to the short forms the
    card uses (e.g. "db.t3.small", "storage").
    """
    components = []
    for project in infracost_data.get("projects", []):
        breakdown = project.get("breakdown") or {}
        for resource in breakdown.get("resources", []):
            if resource.get("name") != TARGET_RESOURCE:
                continue
            for comp in resource.get("costComponents", []):
                name = comp.get("name", "")
                monthly = comp.get("monthlyCost")
                if monthly is None:
                    continue
                components.append(
                    {"label": _short_component_label(name), "monthly": float(monthly)}
                )
    return components


def _short_component_label(name: str) -> str:
    """Map an Infracost component name to the short label the card uses."""
    lowered = name.lower()
    if "storage" in lowered:
        return "storage"
    # Try to surface the instance class (e.g. db.t3.small) if present.
    for token in name.replace("(", " ").replace(")", " ").replace(",", " ").split():
        if token.startswith("db."):
            return token
    if "instance" in lowered:
        return "instance"
    return name


def run_pipeline(
    manifest_path: str,
    env: str = "staging",
    infracost_fixture: str | None = None,
) -> dict:
    """Run the full gate pipeline against the generated HCL.

    Returns:
        {
          "card": "<plain-text approval card>",
          "raw": {
            "security": <security_gate result dict>,
            "cost": <cost_gate result dict>,
            "plan": <plan_gate result dict>,
          },
          "hcl_path": "<path to generated main.tf>",
        }
    """
    main_tf = _prepare_generated_module(manifest_path, env)

    # --- Security gate (direct import) ---
    security_result = security_gate.run_file(main_tf)

    # --- Cost gate (fixture or live infracost) ---
    if infracost_fixture is not None:
        infracost_data = load_fixture(infracost_fixture)
    else:
        infracost_data = run_infracost(_GENERATED_DIR)
    cost_result = cost_evaluate(infracost_data)
    # Attach per-line components for the card (does not alter the gate verdict).
    cost_result = dict(cost_result)
    cost_result["components"] = _extract_cost_components(infracost_data)

    # --- Plan gate ---
    plan_result = plan_gate.run_path(_GENERATED_DIR)

    # --- Synthesize ---
    card = ApprovalSynthesizer().synthesize(
        plan_result, security_result, cost_result, manifest_path, env
    )

    return {
        "card": card,
        "raw": {
            "security": security_result,
            "cost": cost_result,
            "plan": plan_result,
        },
        "hcl_path": main_tf,
    }


def apply_infrastructure(terraform_dir: str, snapshot_dir: str) -> dict:
    """Save a pre-apply state snapshot, then run tofu plan + apply.

    Args:
        terraform_dir: Directory containing .tf files and any existing state.
        snapshot_dir: Directory where the pre-apply state snapshot is written.

    Returns:
        {"status": "success", "output": str, "state_snapshot_path": str}

    Raises:
        RuntimeError: if plan or apply exits non-zero; message contains stderr.
    """
    terraform_dir = os.path.abspath(terraform_dir)
    snapshot_dir = os.path.abspath(snapshot_dir)
    os.makedirs(snapshot_dir, exist_ok=True)

    # Snapshot existing state before touching anything.
    state_src = os.path.join(terraform_dir, "terraform.tfstate")
    state_snapshot = os.path.join(snapshot_dir, "before_apply.tfstate")
    if os.path.exists(state_src):
        shutil.copyfile(state_src, state_snapshot)
    else:
        # No prior state — write an empty sentinel so the path is always valid.
        with open(state_snapshot, "w") as fh:
            json.dump({}, fh)

    combined_output: list[str] = []

    # --- plan (surface changes; fail fast before touching real infra) ---
    plan = subprocess.run(
        ["tofu", "plan", "-no-color"],
        cwd=terraform_dir,
        capture_output=True,
        text=True,
    )
    combined_output.append(plan.stdout)
    if plan.returncode != 0:
        raise RuntimeError(
            f"tofu plan failed (exit {plan.returncode}):\n{plan.stderr}"
        )

    # --- apply ---
    apply = subprocess.run(
        ["tofu", "apply", "-auto-approve", "-no-color"],
        cwd=terraform_dir,
        capture_output=True,
        text=True,
    )
    combined_output.append(apply.stdout)
    if apply.returncode != 0:
        raise RuntimeError(
            f"tofu apply failed (exit {apply.returncode}):\n{apply.stderr}"
        )

    return {
        "status": "success",
        "output": "\n".join(combined_output),
        "state_snapshot_path": state_snapshot,
    }


def snapshot_data_bearing_resources(manifest_path: str, before_state: dict) -> dict:
    """Take native RDS snapshots for data-bearing resources that already exist.

    Greenfield resources (absent from before_state's resources list) are silently
    skipped — there is nothing to snapshot on first provision.

    Args:
        manifest_path: Path to the platform manifest YAML.
        before_state: Parsed terraform.tfstate JSON captured before the apply
                      (the dict written by apply_infrastructure's snapshot step).

    Returns:
        {
            "snapshots": [
                {"resource": str, "snapshot_id": str, "snapshot_arn": str}
            ],
            "status": "success" | "skipped",
        }

    Raises:
        boto3 ClientError propagated directly if the RDS API call fails.
    """
    reader = ManifestReader(manifest_path)

    # Build lookup: TF resource name (underscores) → instance attributes.
    # TF state uses underscores; the manifest uses hyphens.
    tf_attrs: dict[str, dict] = {}
    for tf_res in before_state.get("resources", []):
        instances = tf_res.get("instances", [])
        if instances:
            tf_attrs[tf_res.get("name", "")] = instances[0].get("attributes", {})

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    snapshots: list[dict] = []

    for env in reader.get_environments():
        resources = reader.get_resources(env)
        # pylint: disable=protected-access  # same package, no public region accessor
        env_data = reader._environment(env)
        aws_region = env_data.get("regions", {}).get("aws", "ap-southeast-5")

        for resource_name, resource in resources.items():
            if not resource.get("data_bearing"):
                continue
            if resource.get("type") != "aws_db_instance":
                continue

            # Manifest "payments-db" → TF state name "payments_db".
            tf_name = resource_name.replace("-", "_")
            if tf_name not in tf_attrs:
                # Not yet provisioned — greenfield, nothing to snapshot.
                continue

            attrs = tf_attrs[tf_name]
            # TF stores the DBInstanceIdentifier as the "id" attribute.
            db_instance_id = attrs.get("id") or attrs.get("identifier")
            if not db_instance_id:
                continue

            snapshot_id = f"{resource_name}-before-apply-{timestamp}"
            rds = boto3.client("rds", region_name=aws_region)
            resp = rds.create_db_snapshot(
                DBInstanceIdentifier=db_instance_id,
                DBSnapshotIdentifier=snapshot_id,
            )
            snapshots.append(
                {
                    "resource": resource_name,
                    "snapshot_id": snapshot_id,
                    "snapshot_arn": resp["DBSnapshot"]["DBSnapshotArn"],
                }
            )

    return {
        "snapshots": snapshots,
        "status": "success" if snapshots else "skipped",
    }


def update_manifest_after_apply(manifest_path: str, tfstate_path: str) -> None:
    """Stamp each provisioned resource in the manifest with its TF resource ID and apply time.

    Reads the post-apply tfstate and updates only the state: block fields
    (status, resource_id, last_applied) via ManifestReader so all human
    comments survive. Environments marked out-of-scope-v1 are skipped.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    tf_resources: dict[str, dict] = {}
    if os.path.exists(tfstate_path):
        with open(tfstate_path) as fh:
            tfstate = json.load(fh)
        for res in tfstate.get("resources", []):
            instances = res.get("instances", [])
            if instances:
                tf_resources[res.get("name", "")] = instances[0].get("attributes", {})

    reader = ManifestReader(manifest_path)
    for env in reader.get_environments():
        # pylint: disable=protected-access
        env_data = reader._environment(env)
        if env_data.get("scope") == "out-of-scope-v1":
            continue
        resources = reader.get_resources(env)
        for resource_name, resource_data in resources.items():
            if "state" not in resource_data:
                continue
            tf_name = resource_name.replace("-", "_")
            updates: dict = {"status": "applied", "last_applied": timestamp}
            attrs = tf_resources.get(tf_name, {})
            resource_id = attrs.get("id") or attrs.get("identifier")
            if resource_id:
                updates["resource_id"] = resource_id
            if "endpoint" in resource_data.get("state", {}):
                endpoint = attrs.get("endpoint") or attrs.get("address")
                if endpoint:
                    updates["endpoint"] = endpoint
            reader.update_resource_state(env, resource_name, updates)

    reader.write()


def main(argv=None):
    parser = argparse.ArgumentParser(description="IAI end-to-end gate pipeline.")
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--env", default="staging")
    parser.add_argument(
        "--infracost-fixture",
        default=None,
        help="Pre-captured Infracost JSON (skips live infracost).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the full result dict as JSON."
    )
    args = parser.parse_args(argv)

    result = run_pipeline(args.manifest, args.env, args.infracost_fixture)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["card"])


if __name__ == "__main__":
    main()
