#!/usr/bin/env python3
"""Security gate for the IAI demo.

Primary scanner: Checkov (IaC config). Secondary (belt-and-suspenders): Trivy config.
Tertiary: Trivy image scanning (supply-chain).

Checkov filters its findings down to WATCHED_CHECKS so the synthesized approval
card can speak plainly about exactly the issues that matter — and about the
checks that *passed* (the on-camera "discrimination beat": the gate is doing
real work, not stamping everything green).

Trivy config is run as secondary when available. Its findings for the same
watched checks are surfaced in `trivy_config_findings` on the result dict. Trivy
config findings do not affect the gate's PASS/FAIL verdict (driven by Checkov alone)
but provide belt-and-suspenders confirmation that the primary scanner's result
is sound.

Trivy image scanning is run if an image URI is provided. Image findings are
surfaced separately in `trivy_image_findings` and also do not affect the PASS/FAIL
verdict (Checkov IaC config is primary).

The human never reads raw Checkov or Trivy output. This gate emits a small
structured dict; the approval synthesizer turns it into prose.

Modes:
  --path <terraform_dir>   run `checkov --directory <dir>`
  --file <hcl_file>        run `checkov --file <file>`

Exit codes:
  0  pass  (no watched Checkov check failed)
  1  fail  (at least one watched Checkov check failed)
  2  checkov not installed

Note on the Checkov invocation: we do NOT pass `--quiet`. `--quiet` suppresses
the `passed_checks` block from Checkov's JSON, but the demo's approval card
requires the passing watched checks (EC2 IMDSv2 enforced, GCS uniform bucket
access enabled) to be reported. Accuracy of the passed-checks line is a locked
requirement (see docs/demo-scenario.md, the "discrimination" beat), so the
full JSON is required.
"""

import argparse
import json
import shutil
import subprocess
import sys

# --- Checks in scope for the demo (Checkov IDs). Source of truth: the
# Researcher's SecOps spec + docs/demo-scenario.md. Everything Checkov reports
# outside this set is filtered out so the card stays focused. ---
#   CKV_AWS_24 — security group allows ingress from 0.0.0.0/0 to port 22 (SSH)
#   CKV_AWS_79 — EC2 instance does not enforce IMDSv2 (http_tokens = "required")
#   CKV_GCP_29 — GCS bucket does not use uniform bucket-level access
WATCHED_CHECKS = ["CKV_AWS_24", "CKV_AWS_79", "CKV_GCP_29"]

# Open-source Checkov reports `severity: null` (severities are a Bridgecrew /
# Prisma platform feature). We pin severities for the watched checks here so
# the gate output is deterministic and platform-independent.
_WATCHED_SEVERITY = {
    "CKV_AWS_24": "CRITICAL",
    "CKV_AWS_79": "HIGH",
    "CKV_GCP_29": "HIGH",
}

# --- Trivy config AVDID equivalents for the same watched checks.
# Trivy (Aqua's successor to tfsec) uses AVD identifiers.
#   AVD-AWS-0018 — security group allows unrestricted public ingress
#   AVD-AWS-0028 — EC2 IMDSv2 not enforced (http_tokens optional)
WATCHED_TRIVY_CHECKS = {
    "AVD-AWS-0018": "CRITICAL",
    "AVD-AWS-0028": "HIGH",
}

# Exit codes
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_NO_CHECKOV = 2


def _checkov_available() -> bool:
    return shutil.which("checkov") is not None


def _trivy_available() -> bool:
    return shutil.which("trivy") is not None


def _run_checkov(args):
    """Run checkov with the given trailing args; return parsed JSON.

    Returns a plain dict. Checkov emits either a single dict (one check_type)
    or a list of dicts (multiple check_types); this normalizes a list into a
    merged-results dict so callers always see one shape.
    """
    proc = subprocess.run(
        ["checkov", *args, "--output", "json"],
        capture_output=True,
        text=True,
    )
    # Checkov returns non-zero when checks fail; that is expected, not an error.
    # Parse stdout regardless of return code.
    stdout = proc.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"checkov produced no JSON output (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:400]}"
        )
    data = json.loads(stdout)
    return _normalize(data)


def _normalize(data) -> dict:
    """Collapse Checkov's dict-or-list output into a single results dict."""
    if isinstance(data, list):
        failed, passed = [], []
        for entry in data:
            results = entry.get("results", {}) if isinstance(entry, dict) else {}
            failed.extend(results.get("failed_checks", []) or [])
            passed.extend(results.get("passed_checks", []) or [])
        return {"results": {"failed_checks": failed, "passed_checks": passed}}
    # Single dict.
    results = data.get("results", {}) if isinstance(data, dict) else {}
    return {
        "results": {
            "failed_checks": results.get("failed_checks", []) or [],
            "passed_checks": results.get("passed_checks", []) or [],
        }
    }


def _run_trivy_config(path: str) -> list:
    """Run trivy config on path; return list of failing watched-check dicts.

    Returns [] if Trivy is unavailable or produces no parseable output.
    Only WATCHED_TRIVY_CHECKS that have Status == 'FAIL' are returned.
    """
    if not _trivy_available():
        return []
    proc = subprocess.run(
        ["trivy", "config", "--format", "json", "--quiet", path],
        capture_output=True,
        text=True,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    findings = []
    for result in data.get("Results", []):
        for misconfig in result.get("Misconfigurations", []):
            avdid = misconfig.get("AVDID") or misconfig.get("ID", "")
            if avdid in WATCHED_TRIVY_CHECKS and misconfig.get("Status") == "FAIL":
                findings.append(
                    {
                        "check_id": avdid,
                        "resource": (misconfig.get("CauseMetadata") or {}).get(
                            "Resource"
                        ),
                        "severity": misconfig.get("Severity")
                        or WATCHED_TRIVY_CHECKS.get(avdid),
                        "title": misconfig.get("Title"),
                    }
                )
    return findings


def _run_trivy_image(image_uri: str) -> list:
    """Run trivy image on the given URI; return list of vulnerability findings.

    Returns [] if Trivy is unavailable, image_uri is empty, or produces no parseable output.
    This is informational only; failures do not affect the gate's PASS/FAIL verdict.
    """
    if not _trivy_available() or not image_uri:
        return []
    proc = subprocess.run(
        ["trivy", "image", "--format", "json", "--quiet", image_uri],
        capture_output=True,
        text=True,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    findings = []
    for result in data.get("Results", []):
        for vuln in result.get("Vulnerabilities", []):
            findings.append(
                {
                    "vulnerability_id": vuln.get("VulnerabilityID", ""),
                    "severity": vuln.get("Severity", "UNKNOWN"),
                    "title": vuln.get("Title", ""),
                    "source": "trivy_image",
                }
            )
    return findings


def evaluate(checkov_data: dict) -> dict:
    """Filter normalized Checkov data to the watched set; return result dict."""
    results = checkov_data.get("results", {})
    failed = results.get("failed_checks", []) or []
    passed = results.get("passed_checks", []) or []

    findings = []
    failed_ids = set()
    for chk in failed:
        cid = chk.get("check_id")
        if cid in WATCHED_CHECKS:
            failed_ids.add(cid)
            findings.append(
                {
                    "check_id": cid,
                    "resource": chk.get("resource"),
                    "severity": chk.get("severity") or _WATCHED_SEVERITY.get(cid),
                }
            )

    passed_checks = []
    seen = set()
    for chk in passed:
        cid = chk.get("check_id")
        if cid in WATCHED_CHECKS and cid not in seen and cid not in failed_ids:
            seen.add(cid)
            passed_checks.append(cid)

    all_passed = len(findings) == 0
    return {
        "status": "pass" if all_passed else "fail",
        "findings": findings,
        "passed_checks": passed_checks,
        "all_passed": all_passed,
    }


def run_file(path: str, image_uri: str = "") -> dict:
    """Library entry point: scan a single HCL file, return the result dict.

    Runs Checkov (primary) and Trivy config (secondary, if available).
    Optionally scans image (tertiary, if image_uri provided).
    Does not print or exit. Raises RuntimeError if checkov is unavailable.
    """
    if not _checkov_available():
        raise RuntimeError("checkov is not installed")
    result = evaluate(_run_checkov(["--file", path]))
    result["trivy_config_findings"] = _run_trivy_config(path)
    result["trivy_image_findings"] = _run_trivy_image(image_uri)
    result["trivy_available"] = _trivy_available()
    return result


def run_path(path: str, image_uri: str = "") -> dict:
    """Library entry point: scan a directory, return the result dict.

    Runs Checkov (primary) and Trivy config (secondary, if available).
    Optionally scans image (tertiary, if image_uri provided).
    Does not print or exit. Raises RuntimeError if checkov is unavailable.
    """
    if not _checkov_available():
        raise RuntimeError("checkov is not installed")
    result = evaluate(_run_checkov(["--directory", path]))
    result["trivy_config_findings"] = _run_trivy_config(path)
    result["trivy_image_findings"] = _run_trivy_image(image_uri)
    result["trivy_available"] = _trivy_available()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="IAI security gate (Checkov primary, Trivy config secondary, Trivy image tertiary)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="OpenTofu/HCL directory to scan.")
    group.add_argument("--file", help="Single HCL file to scan.")
    parser.add_argument("--image-uri", default="", help="Optional container/OCI image URI for image scanning (Trivy).")
    args = parser.parse_args(argv)

    if not _checkov_available():
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "checkov is not installed.",
                }
            )
        )
        sys.exit(EXIT_NO_CHECKOV)

    if args.path:
        checkov_data = _run_checkov(["--directory", args.path])
        trivy_config_findings = _run_trivy_config(args.path)
    else:
        checkov_data = _run_checkov(["--file", args.file])
        trivy_config_findings = _run_trivy_config(args.file)

    result = evaluate(checkov_data)
    result["trivy_config_findings"] = trivy_config_findings
    result["trivy_image_findings"] = _run_trivy_image(args.image_uri)
    result["trivy_available"] = _trivy_available()
    print(json.dumps(result, indent=2))
    sys.exit(EXIT_PASS if result["all_passed"] else EXIT_FAIL)


if __name__ == "__main__":
    main()
