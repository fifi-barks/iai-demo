"""Security remediation for the IAI demo.

The security gate DETECTS misconfigurations; this module ACTS on them. After the
gate flags an issue, the agent rewrites the generated OpenTofu to fix it — and
the pipeline then RE-RUNS the gate to confirm the fix actually cleared the
finding. The approval card reports only what that re-scan confirms, so "caught
and fixed" is a true statement about the configuration that will be applied, not
a claim about the configuration that was generated.

This is the difference between an agent that reports risk and one that removes
it — the whole point of an intent layer that you can approve without reading raw
tool output.

v1.0.0 remediates the one watched network-exposure finding:
  CKV_AWS_24 — SSH (port 22) ingress open to 0.0.0.0/0 → narrowed to a private
  CIDR (default 10.0.0.0/8; override with IAI_SSH_ALLOWED_CIDR), so the app tier
  is reachable only from inside the network, never the public internet.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# Open SSH ingress is narrowed to this CIDR. A private (RFC1918) range by
# default — reachable from inside the network, not the public internet.
SSH_ALLOWED_CIDR = os.environ.get("IAI_SSH_ALLOWED_CIDR", "10.0.0.0/8")

_OPEN_CIDR_RE = re.compile(r'cidr_blocks\s*=\s*\[\s*"0\.0\.0\.0/0"\s*\]')


def _note_ckv_aws_24(cidr: str) -> str:
    return (
        "the app tier would have been reachable via SSH from the entire internet "
        f"(port 22 open to 0.0.0.0/0); ingress narrowed to {cidr} (a private range)"
    )


def remediate(hcl_path: str, findings: list) -> list:
    """Fix the flagged findings by rewriting the generated HCL in place.

    Only acts on findings the gate actually raised — nothing is changed
    speculatively. Returns a list of applied remediations, each
    ``{"check_id": str, "note": str}``; empty if there was nothing to fix.
    """
    check_ids = {f.get("check_id") for f in (findings or [])}
    applied = []

    if "CKV_AWS_24" in check_ids:
        try:
            with open(hcl_path, "r", encoding="utf-8") as fh:
                hcl = fh.read()
            new_hcl, n = _OPEN_CIDR_RE.subn(
                f'cidr_blocks = ["{SSH_ALLOWED_CIDR}"]', hcl
            )
            if n:
                # Keep the generated HCL's own comment honest about what happened.
                new_hcl = new_hcl.replace(
                    "SSH - intentionally open to internet for security gate demo",
                    f"SSH - ingress narrowed to {SSH_ALLOWED_CIDR} by the agent",
                )
                with open(hcl_path, "w", encoding="utf-8") as fh:
                    fh.write(new_hcl)
                logger.info(
                    "[REMEDIATE] CKV_AWS_24: narrowed open SSH ingress to %s (%d rule(s))",
                    SSH_ALLOWED_CIDR, n,
                )
                applied.append(
                    {"check_id": "CKV_AWS_24", "note": _note_ckv_aws_24(SSH_ALLOWED_CIDR)}
                )
        except OSError as exc:
            logger.warning("[REMEDIATE] could not patch %s (%s)", hcl_path, exc)

    return applied
