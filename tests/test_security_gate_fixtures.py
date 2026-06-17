"""White-box golden fixture tests for gates/security_gate.py.

For every watched check, asserts:
  - known-bad file => status="fail" (no false negatives)
  - known-good file => status="pass" (no false positives)
  - result dict always contains `trivy_config_findings` key (even when Trivy absent)
  - result dict always contains `trivy_available` key

These tests are independent of the pipeline; they call the gate's library
entry point (run_file) directly.

Watched checks (v2):
  CKV_AWS_24 — security group allows ingress from 0.0.0.0/0 to port 22 (SSH)
  CKV_AWS_79 — EC2 instance does not enforce IMDSv2 (http_tokens = "required")
  CKV_GCP_29 — GCS bucket does not use uniform bucket-level access

Run from repo root:
    .venv/bin/python tests/test_security_gate_fixtures.py
"""

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from gates.security_gate import run_file

FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures")

results = []


def record(name, passed, message=""):
    results.append((name, passed, message))
    status = "PASS" if passed else "FAIL"
    print(f"  {status}  {name}")
    if not passed and message:
        for line in message.splitlines():
            print(f"         {line}")


def _check(fixture_filename, expected_status, label):
    """Run run_file on fixture_filename, assert expected_status and trivy keys."""
    path = os.path.join(FIXTURES, fixture_filename)
    name = f"{label} [{fixture_filename}]"
    try:
        result = run_file(path)

        failures = []

        # Status assertion
        if result.get("status") != expected_status:
            failures.append(
                f"expected status={expected_status!r}, got {result.get('status')!r}"
            )

        # trivy_config_findings must exist (may be empty list when Trivy absent)
        if "trivy_config_findings" not in result:
            failures.append("result dict missing 'trivy_config_findings' key")
        elif not isinstance(result["trivy_config_findings"], list):
            failures.append(
                f"trivy_config_findings must be a list, got {type(result['trivy_config_findings'])}"
            )

        # trivy_available must exist and be a bool
        if "trivy_available" not in result:
            failures.append("result dict missing 'trivy_available' key")
        elif not isinstance(result["trivy_available"], bool):
            failures.append(
                f"trivy_available must be bool, got {type(result['trivy_available'])}"
            )

        if failures:
            record(name, False, "\n".join(failures) + f"\nFull result: {result}")
        else:
            record(name, True)
    except RuntimeError as e:
        # checkov not installed is a setup failure, not a gate failure
        record(name, False, f"RuntimeError (checkov not installed?): {e}")
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Known-bad fixtures — must produce status="fail"
# ---------------------------------------------------------------------------
def test_sg_open_ingress_bad():
    _check("sec_sg_open_ingress_bad.tf", "fail",
           "KNOWN-BAD: SG SSH open ingress => must FAIL (CKV_AWS_24)")


def test_ec2_imdsv2_bad():
    _check("sec_ec2_imdsv2_bad.tf", "fail",
           "KNOWN-BAD: EC2 IMDSv2 not enforced => must FAIL (CKV_AWS_79)")


def test_gcs_uniform_access_bad():
    _check("sec_gcs_uniform_access_bad.tf", "fail",
           "KNOWN-BAD: GCS bucket without uniform bucket access => must FAIL (CKV_GCP_29)")


# ---------------------------------------------------------------------------
# Known-good fixtures — must produce status="pass"
# ---------------------------------------------------------------------------
def test_sg_open_ingress_good():
    _check("sec_sg_open_ingress_good.tf", "pass",
           "KNOWN-GOOD: SG SSH restricted to VPC => must PASS (CKV_AWS_24)")


def test_ec2_imdsv2_good():
    _check("sec_ec2_imdsv2_good.tf", "pass",
           "KNOWN-GOOD: EC2 IMDSv2 enforced => must PASS (CKV_AWS_79)")


def test_gcs_uniform_access_good():
    _check("sec_gcs_uniform_access_good.tf", "pass",
           "KNOWN-GOOD: GCS bucket with uniform bucket access => must PASS (CKV_GCP_29)")


# ---------------------------------------------------------------------------
# Edge case: newer resource type (observational — documents known gap)
# ---------------------------------------------------------------------------
def test_sg_new_resource_type_trivy_keys():
    """sec_sg_new_resource_type.tf may or may not fail (known coverage gap).
    This test only asserts the trivy_config_findings and trivy_available keys exist."""
    path = os.path.join(FIXTURES, "sec_sg_new_resource_type.tf")
    name = "EDGE-CASE: aws_vpc_security_group_ingress_rule — trivy_config_findings key present"
    try:
        result = run_file(path)
        failures = []
        if "trivy_config_findings" not in result:
            failures.append("result dict missing 'trivy_config_findings' key")
        if "trivy_available" not in result:
            failures.append("result dict missing 'trivy_available' key")
        if failures:
            record(name, False, "\n".join(failures))
        else:
            record(name, True)
    except RuntimeError as e:
        record(name, False, f"RuntimeError: {e}")
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running security gate golden fixture tests...")
    print()

    test_sg_open_ingress_bad()
    test_ec2_imdsv2_bad()
    test_gcs_uniform_access_bad()
    test_sg_open_ingress_good()
    test_ec2_imdsv2_good()
    test_gcs_uniform_access_good()
    test_sg_new_resource_type_trivy_keys()

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    # Report Trivy availability as observed
    import shutil
    trivy_on_path = shutil.which("trivy") is not None
    print(f"Trivy available on this machine: {trivy_on_path}")

    if passed == total:
        print("Overall: PASS")
        sys.exit(0)
    else:
        failed_names = [n for n, ok, _ in results if not ok]
        print(f"Overall: FAIL — failing tests: {', '.join(failed_names)}")
        sys.exit(1)
