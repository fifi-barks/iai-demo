"""Standalone white-box tests for agent/iac_generator.py.

Pattern: prints PASS/FAIL per test with actual vs expected on failure.
Exits 0 if all tests pass, exits 1 if any fail.
Run from repo root with the venv Python:
    .venv/bin/python tests/test_iac_generator.py
"""

import os
import sys
import tempfile
import traceback

# Ensure the repo root is on sys.path so `agent` is importable.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from agent.iac_generator import IaCGenerator
from agent.manifest_reader import ManifestReader
from ruamel.yaml import YAML

MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest.yaml")

results = []  # list of (test_name, passed, message)


def record(name, passed, message=""):
    results.append((name, passed, message))
    status = "PASS" if passed else "FAIL"
    if passed:
        print(f"  {status}  {name}")
    else:
        print(f"  {status}  {name}")
        print(f"         {message}")


# ---------------------------------------------------------------------------
# Test 1 — Demo scenario: correct criticality tags in generated HCL
# ---------------------------------------------------------------------------
def test_1_demo_criticality_tags():
    name = "Test 1 — Demo scenario: correct criticality tags in generated HCL"
    try:
        g = IaCGenerator(MANIFEST_PATH)
        hcl = g.generate_to_string()

        failures = []

        # app-tier is directly critical → criticality="critical" must appear
        if 'criticality = "critical"' not in hcl:
            failures.append(
                'criticality = "critical" not found anywhere in generated HCL'
            )

        # Check aws_security_group "app_tier" block for criticality = "critical"
        if 'resource "aws_security_group" "app_tier"' not in hcl:
            failures.append('aws_security_group "app_tier" resource block not found')
        else:
            sg_block_start = hcl.index('resource "aws_security_group" "app_tier"')
            sg_block_end = hcl.index("\n}", sg_block_start) + 2
            sg_block = hcl[sg_block_start:sg_block_end]
            if 'criticality = "critical"' not in sg_block:
                failures.append(
                    f"aws_security_group app_tier block missing criticality=critical; "
                    f"block content:\n{sg_block}"
                )

        # export-bucket stays high and uses labels
        if 'resource "google_storage_bucket" "export_bucket"' not in hcl:
            failures.append('google_storage_bucket "export_bucket" resource block not found')
        else:
            bucket_start = hcl.index('resource "google_storage_bucket" "export_bucket"')
            bucket_end = hcl.index("\n}", bucket_start) + 2
            bucket_block = hcl[bucket_start:bucket_end]
            if 'criticality = "high"' not in bucket_block:
                failures.append(
                    f"export_bucket block missing criticality=high; "
                    f"block content:\n{bucket_block}"
                )

        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 2 — Transitivity in a synthetic manifest
# ---------------------------------------------------------------------------
def test_2_synthetic_transitivity():
    name = "Test 2 — Transitivity: resource-a inherits critical from resource-b via depends_on"
    tmp = None
    try:
        yaml = YAML()
        manifest_data = {
            "manifest_version": "1",
            "environments": {
                "test": {
                    "engine": "terraform",
                    "clouds": ["aws"],
                    "regions": {"aws": "ap-southeast-5"},
                    "tags": {"environment": "test"},
                    "resources": {
                        "resource-a": {
                            "cloud": "aws",
                            "type": "aws_vpc",
                            "criticality": "high",
                            "depends_on": [],
                            "state": {
                                "status": "pending",
                                "resource_id": None,
                                "last_applied": None,
                            },
                        },
                        "resource-b": {
                            "cloud": "aws",
                            "type": "aws_db_instance",
                            "criticality": "critical",
                            "depends_on": ["resource-a"],
                            "state": {
                                "status": "pending",
                                "resource_id": None,
                                "last_applied": None,
                            },
                        },
                    },
                }
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(manifest_data, f)
            tmp = f.name

        reader = ManifestReader(tmp)
        crit = reader.resolve_criticality("test")

        failures = []
        if crit.get("resource-a") != "critical":
            failures.append(
                f"resource-a: expected 'critical' (inherited from resource-b), "
                f"got {crit.get('resource-a')!r}"
            )
        if crit.get("resource-b") != "critical":
            failures.append(
                f"resource-b: expected 'critical', got {crit.get('resource-b')!r}"
            )

        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Test 3 — Greenfield enforcement: missing criticality tag raises ValueError
# ---------------------------------------------------------------------------
def test_3_greenfield_enforcement():
    name = "Test 3 — Greenfield enforcement: missing criticality raises ValueError"
    tmp = None
    try:
        yaml = YAML()
        manifest_data = {
            "manifest_version": "1",
            "environments": {
                "test": {
                    "engine": "terraform",
                    "clouds": ["aws"],
                    "regions": {"aws": "ap-southeast-5"},
                    "tags": {"environment": "test"},
                    "resources": {
                        "payments-vpc": {
                            "cloud": "aws",
                            "type": "aws_vpc",
                            # NO criticality field here — should trigger ValueError
                            "depends_on": [],
                            "state": {
                                "status": "pending",
                                "resource_id": None,
                                "last_applied": None,
                            },
                        }
                    },
                }
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(manifest_data, f)
            tmp = f.name

        g = IaCGenerator(tmp, env="test")
        try:
            g.validate_greenfield()
            # Should have raised — if we get here, it's a FAIL
            record(
                name,
                False,
                "validate_greenfield() did NOT raise ValueError for resource missing criticality",
            )
        except ValueError as e:
            if "payments-vpc" in str(e):
                record(name, True)
            else:
                record(
                    name,
                    False,
                    f"ValueError raised but did not mention 'payments-vpc'; error: {e}",
                )
    except Exception:
        record(name, False, traceback.format_exc())
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Test 4 — AWS uses `tags`, GCP uses `labels`
# ---------------------------------------------------------------------------
def test_4_aws_tags_gcp_labels():
    name = "Test 4 — Tag normalisation: AWS uses `tags`, GCP uses `labels`"
    try:
        g = IaCGenerator(MANIFEST_PATH)
        hcl = g.generate_to_string()

        failures = []

        # GCP bucket must use 'labels', not 'tags'
        if 'resource "google_storage_bucket" "export_bucket"' not in hcl:
            failures.append('google_storage_bucket "export_bucket" resource block not found')
        else:
            bucket_start = hcl.index('resource "google_storage_bucket" "export_bucket"')
            bucket_end = hcl.index("\n}", bucket_start) + 2
            bucket_block = hcl[bucket_start:bucket_end]

            if "labels" not in bucket_block:
                failures.append(
                    f"GCP bucket must use 'labels'; not found in block:\n{bucket_block}"
                )
            if "tags" in bucket_block:
                failures.append(
                    f"GCP bucket must NOT use 'tags'; found in block:\n{bucket_block}"
                )

        # AWS security group must use 'tags', not 'labels'
        if 'resource "aws_security_group" "app_tier"' not in hcl:
            failures.append('aws_security_group "app_tier" resource block not found')
        else:
            sg_start = hcl.index('resource "aws_security_group" "app_tier"')
            sg_end = hcl.index("\n}", sg_start) + 2
            sg_block = hcl[sg_start:sg_end]

            if "tags" not in sg_block:
                failures.append(
                    f"AWS security group must use 'tags'; not found in block:\n{sg_block}"
                )
            if "labels" in sg_block:
                failures.append(
                    f"AWS security group must NOT use 'labels'; found in block:\n{sg_block}"
                )

        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running iac_generator white-box tests...")
    print()

    test_1_demo_criticality_tags()
    test_2_synthetic_transitivity()
    test_3_greenfield_enforcement()
    test_4_aws_tags_gcp_labels()

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    if passed == total:
        print("Overall: PASS")
        sys.exit(0)
    else:
        failed_names = [n for n, ok, _ in results if not ok]
        print(f"Overall: FAIL — failing tests: {', '.join(failed_names)}")
        sys.exit(1)
