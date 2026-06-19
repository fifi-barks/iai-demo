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
import logging
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

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GENERATED_DIR = os.path.join(_REPO_ROOT, "terraform", "generated")
_STAGING_DIR = os.path.join(_REPO_ROOT, "terraform", "staging")

# Hard ceiling on how long a single `tofu plan` / `tofu apply` is allowed to
# run before apply_infrastructure() gives up and raises. Without this, a hung
# subprocess (stale state lock, a credential call that never returns, an
# unexpected interactive prompt, etc.) blocks forever with no error and no
# log line — which is exactly the failure mode this constant exists to kill.
# Override with IAI_APPLY_TIMEOUT for slower stacks (e.g. RDS provisioning).
APPLY_TIMEOUT_SECONDS = int(os.environ.get("IAI_APPLY_TIMEOUT", "600"))

# Public paths used by the bot's approval handler.
TERRAFORM_GENERATED_DIR = _GENERATED_DIR
TERRAFORM_SNAPSHOT_DIR = os.path.join(_REPO_ROOT, "terraform", "snapshots")

# Files copied from the staging module so checkov / terraform see a complete
# module (providers + variables + variable values) alongside the generated main.tf.
_SUPPORT_FILES = ["providers.tf", "variables.tf", "terraform.tfvars"]


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

    # --- Cost gate (live Infracost by default; fixture only when opted in) ---
    # run_infracost()/load_fixture() exit CLI-style on failure. Called in-process
    # (bot/CLI), convert that into a graceful gate error so a bad INFRACOST_API_KEY,
    # a missing binary, or an absent fixture cannot crash the long-running agent.
    try:
        if infracost_fixture is not None:
            infracost_data = load_fixture(infracost_fixture)
        else:
            infracost_data = run_infracost(_GENERATED_DIR)
        cost_result = dict(cost_evaluate(infracost_data))
        cost_result["components"] = _extract_cost_components(infracost_data)
    except (SystemExit, OSError, ValueError) as exc:
        logger.error("Cost gate failed (%s) — surfacing as unavailable, not crashing", exc)
        cost_result = {
            "status": "error",
            "resource": TARGET_RESOURCE,
            "monthly_cost": None,
            "components": [],
            "message": (
                "Live Infracost estimate failed — check INFRACOST_API_KEY and that "
                "infracost is installed (or set IAI_INFRACOST_FIXTURE to run offline)."
            ),
        }

    # --- Plan gate ---
    plan_result = plan_gate.run_path(_GENERATED_DIR)

    # --- Synthesize ---
    card_result = ApprovalSynthesizer().synthesize(
        plan_result, security_result, cost_result, manifest_path, env
    )

    return {
        "card": card_result["text"],
        "keyboard": card_result["keyboard"],
        "raw": {
            "security": security_result,
            "cost": cost_result,
            "plan": plan_result,
        },
        "hcl_path": main_tf,
    }


def _run_tofu(args: list[str], cwd: str, timeout: int = APPLY_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Run a tofu subcommand with [APPLY] logging and a hard timeout.

    Raises RuntimeError (not a bare subprocess exception) on either a
    non-zero exit or a timeout, with enough detail for the synthesizer /
    Telegram error message to be useful. A timeout is the case the original
    implementation silently hung on — subprocess.run(..., timeout=...) kills
    the child process and raises TimeoutExpired, which we convert here.
    """
    cmd_str = " ".join(args)
    logger.info("[APPLY] Running: %s (cwd=%s, timeout=%ss)", cmd_str, cwd, timeout)
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "")
        stderr = (exc.stderr or "")
        logger.error(
            "[APPLY] TIMED OUT after %ss: %s\nstdout (partial):\n%s\nstderr (partial):\n%s",
            timeout, cmd_str, stdout, stderr,
        )
        raise RuntimeError(
            f"'{cmd_str}' timed out after {timeout}s with no result. "
            "This usually means a stuck process, a stale state lock "
            "(check for .terraform.tfstate.lock.info), or a hung "
            "credential/network call. Partial output:\n"
            f"{(stdout + stderr)[-2000:]}"
        ) from exc

    logger.info("[APPLY] Completed: %s (exit %s)", cmd_str, proc.returncode)
    if proc.stdout:
        logger.debug("[APPLY] stdout for %s:\n%s", cmd_str, proc.stdout)
    if proc.returncode != 0:
        logger.error("[APPLY] FAILED: %s (exit %s)\nstderr:\n%s", cmd_str, proc.returncode, proc.stderr)
        raise RuntimeError(f"'{cmd_str}' failed (exit {proc.returncode}):\n{proc.stderr}")

    return proc


def apply_infrastructure(terraform_dir: str, snapshot_dir: str) -> dict:
    """Save a pre-apply state snapshot, then run tofu plan + apply.

    Args:
        terraform_dir: Directory containing .tf files and any existing state.
        snapshot_dir: Directory where the pre-apply state snapshot is written.

    Returns:
        {"status": "success", "output": str, "state_snapshot_path": str}

    Raises:
        RuntimeError: if plan/apply exits non-zero OR times out (see
        APPLY_TIMEOUT_SECONDS / IAI_APPLY_TIMEOUT). Message contains stderr
        (or partial output, for a timeout) for the caller to surface.
    """
    terraform_dir = os.path.abspath(terraform_dir)
    snapshot_dir = os.path.abspath(snapshot_dir)
    os.makedirs(snapshot_dir, exist_ok=True)
    logger.info("[APPLY] Starting apply_infrastructure: terraform_dir=%s", terraform_dir)

    # Snapshot existing state before touching anything.
    state_src = os.path.join(terraform_dir, "terraform.tfstate")
    state_snapshot = os.path.join(snapshot_dir, "before_apply.tfstate")
    if os.path.exists(state_src):
        shutil.copyfile(state_src, state_snapshot)
        logger.info("[APPLY] State snapshot created: %s", state_snapshot)
    else:
        # No prior state — write an empty sentinel so the path is always valid.
        with open(state_snapshot, "w") as fh:
            json.dump({}, fh)
        logger.info("[APPLY] No prior state found; wrote empty snapshot: %s", state_snapshot)

    combined_output: list[str] = []

    # --- init (downloads providers; -upgrade picks up new providers like google) ---
    # Safe to re-run on an already-initialised directory.
    _run_tofu(["tofu", "init", "-upgrade", "-no-color"], terraform_dir, timeout=180)

    # --- plan (surface changes; fail fast before touching real infra) ---
    plan = _run_tofu(["tofu", "plan", "-no-color", "-lock=false"], terraform_dir)
    combined_output.append(plan.stdout)

    # --- apply ---
    apply = _run_tofu(["tofu", "apply", "-auto-approve", "-no-color"], terraform_dir)
    combined_output.append(apply.stdout)

    logger.info("[APPLY] apply_infrastructure complete.")
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


def _total_monthly_cost(infracost_data: dict) -> float | None:
    """Best-effort total monthly cost across the project — used as the teardown
    savings figure (what stops being billed once these resources are destroyed)."""
    total = infracost_data.get("totalMonthlyCost")
    if total is not None:
        try:
            return float(total)
        except (TypeError, ValueError):
            pass
    summed, found = 0.0, False
    for project in infracost_data.get("projects", []):
        breakdown = project.get("breakdown") or {}
        tmc = breakdown.get("totalMonthlyCost")
        if tmc is not None:
            try:
                summed += float(tmc)
                found = True
            except (TypeError, ValueError):
                pass
    return summed if found else None


def _synthesize_destroy_card(
    resources: list[dict], tf_resource_count: int, env: str, savings: float | None = None
) -> str:
    """Build a plain-text destroy preview card.

    Uses tf_resource_count (from plan_gate, same source as the provision card)
    so the numbers are consistent with what the user saw during provisioning.
    `savings` is the monthly cost that stops being billed after teardown.
    """
    title = f"{env.capitalize()} environment — teardown plan"
    sep = "━" * len(title)

    clouds = sorted({r["cloud"].upper() for r in resources})
    cloud_str = " + ".join(clouds) if clouds else "unknown"

    lines = [
        title,
        sep,
        f"• Resources:  {tf_resource_count} across {cloud_str} "
        f"(0 to add · 0 to change · {tf_resource_count} to destroy)",
    ]
    for r in resources:
        rid = r.get("resource_id") or "not recorded"
        lines.append(
            f"  ↳ {r['name']}  [{r['criticality']}]  ·  {r['cloud'].upper()}  ·  {rid}"
        )
    # Cost savings — round to the nearest $5 to match the provision card's figure.
    if savings is not None:
        shown = int(round(savings / 5.0) * 5) if savings >= 2.5 else round(savings, 2)
        lines.append(f"• Savings:    ~${shown}/month no longer billed once destroyed.")
    else:
        lines.append("• Savings:    monthly cost estimate unavailable.")
    critical = [r["name"] for r in resources if r.get("criticality") == "critical"]
    if critical:
        names = ", ".join(critical)
        lines.append(
            f"• ⚠ Critical: {names} {'is' if len(critical) == 1 else 'are'} tagged "
            "CRITICAL — teardown is irreversible."
        )
    lines.append("• Rollback:   None. Infrastructure cannot be recovered after destroy.")
    return "\n".join(lines)


def run_destroy_pipeline(
    manifest_path: str, env: str = "staging", infracost_fixture: str | None = None
) -> dict:
    """Build a destroy preview card from manifest state + generated HCL count.

    Uses plan_gate.count_resources() on the generated dir for the TF resource
    count — same source as the provision card — so the numbers are consistent.
    Also estimates the monthly cost that stops being billed (teardown savings),
    using the same Infracost source as provisioning (live by default; fixture
    when IAI_INFRACOST_FIXTURE is set).
    """
    reader = ManifestReader(manifest_path)
    resources = reader.get_resources(env)
    criticality = reader.resolve_criticality(env)

    to_destroy = []
    for name, res in resources.items():
        state = res.get("state", {})
        to_destroy.append({
            "name": name,
            "resource_id": state.get("resource_id"),
            "criticality": criticality.get(name, "unknown"),
            "cloud": res.get("cloud", "unknown"),
        })

    # Count actual TF resources from the generated HCL so the number matches
    # what was shown on the provision card. Fall back to manifest count if
    # the generated dir is empty or missing (e.g. first-time destroy).
    tf_count = plan_gate.count_resources(_GENERATED_DIR)
    if tf_count == 0:
        tf_count = len(to_destroy)

    # Teardown savings = the monthly cost of what's currently deployed. Same
    # graceful handling as the provision cost gate: a missing key / binary /
    # fixture shows "unavailable" rather than blocking the teardown.
    savings = None
    try:
        if infracost_fixture is not None:
            infracost_data = load_fixture(infracost_fixture)
        else:
            infracost_data = run_infracost(_GENERATED_DIR)
        savings = _total_monthly_cost(infracost_data)
        if savings is None:
            savings = cost_evaluate(infracost_data).get("monthly_cost")
    except (SystemExit, OSError, ValueError) as exc:
        logger.warning("Teardown savings estimate unavailable (%s)", exc)

    card = _synthesize_destroy_card(to_destroy, tf_count, env, savings)
    return {"card": card, "to_destroy": to_destroy, "savings": savings}


def destroy_and_reset(terraform_dir: str, manifest_path: str) -> dict:
    """Run tofu destroy and reset all resource states in the manifest to pending.

    Args:
        terraform_dir: Directory containing .tf files and terraform.tfstate.
        manifest_path: Path to the platform manifest YAML.

    Returns:
        {"status": "success", "output": str}

    Raises:
        RuntimeError: if tofu destroy exits non-zero or times out.
    """
    terraform_dir = os.path.abspath(terraform_dir)
    logger.info("[DESTROY] Starting destroy_and_reset: terraform_dir=%s", terraform_dir)

    # init first — providers must be available for destroy to work.
    _run_tofu(["tofu", "init", "-upgrade", "-no-color"], terraform_dir, timeout=180)

    proc = _run_tofu(
        ["tofu", "destroy", "-auto-approve", "-no-color"],
        terraform_dir,
    )

    # Reset every resource state back to pending.
    reader = ManifestReader(manifest_path)
    for env in reader.get_environments():
        env_data = reader._environment(env)  # pylint: disable=protected-access
        if env_data.get("scope") == "out-of-scope-v1":
            continue
        for resource_name in reader.get_resources(env):
            reader.update_resource_state(
                env,
                resource_name,
                {"status": "pending", "resource_id": None, "last_applied": None},
            )
    reader.write()

    logger.info("[DESTROY] destroy_and_reset complete.")
    return {"status": "success", "output": proc.stdout}


def apply_and_finalize(terraform_dir: str, snapshot_dir: str, manifest_path: str) -> dict:
    """Run apply_infrastructure(), then snapshot data-bearing resources and
    update the manifest with the post-apply state.

    This bundles every blocking step of the approve flow (subprocess calls,
    boto3 calls, file I/O) into one synchronous call so the caller — the
    Telegram bot's async callback — can run the whole thing via
    `asyncio.to_thread()` without leaving the event loop blocked partway
    through if a later step is slow.

    Returns the apply_infrastructure() result dict on success.
    Raises whatever the underlying steps raise (RuntimeError for tofu
    failures/timeouts, boto3 ClientError for snapshot failures, etc.) — the
    caller is responsible for turning that into a user-facing message.
    """
    logger.info("[APPLY] apply_and_finalize starting")
    apply_result = apply_infrastructure(terraform_dir, snapshot_dir)

    logger.info("[APPLY] Snapshotting data-bearing resources (if any)…")
    with open(apply_result["state_snapshot_path"]) as fh:
        before_state = json.load(fh)
    snapshot_data_bearing_resources(manifest_path, before_state)

    logger.info("[APPLY] Updating manifest with applied resource state…")
    tfstate_path = os.path.join(os.path.abspath(terraform_dir), "terraform.tfstate")
    update_manifest_after_apply(manifest_path, tfstate_path)

    logger.info("[APPLY] apply_and_finalize complete")
    return apply_result


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
