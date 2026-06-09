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

from agent.approval_synthesizer import ApprovalSynthesizer
from agent.iac_generator import IaCGenerator
from gates import plan_gate, security_gate
from gates.cost_gate import evaluate as cost_evaluate
from gates.cost_gate import load_fixture, run_infracost, TARGET_RESOURCE

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GENERATED_DIR = os.path.join(_REPO_ROOT, "terraform", "generated")
_STAGING_DIR = os.path.join(_REPO_ROOT, "terraform", "staging")

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
