"""Standalone white-box tests for agent/manifest_reader.py.

Pattern: prints PASS/FAIL per test with actual vs expected on failure.
Exits 0 if all tests pass, exits 1 if any fail.
Run from repo root with the venv Python:
    .venv/bin/python tests/test_manifest_reader.py
"""

import os
import sys
import tempfile
import traceback

# Ensure the repo root is on sys.path so `agent` is importable.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from agent.manifest_reader import ManifestReader

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
# Test 1 — Parse: environment list matches manifest declaration order
# ---------------------------------------------------------------------------
def test_1_parse():
    name = "Test 1 — Parse: get_environments() returns correct list"
    try:
        r = ManifestReader(MANIFEST_PATH)
        result = r.get_environments()
        expected = ["staging", "edge-network"]
        if result == expected:
            record(name, True)
        else:
            record(name, False,
                   f"expected {expected!r}, got {result!r}")
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 2 — Engine resolution
# ---------------------------------------------------------------------------
def test_2_engine_resolution():
    name = "Test 2 — Engine resolution: staging=opentofu, edge-network=ansible"
    try:
        r = ManifestReader(MANIFEST_PATH)
        staging_engine = r.get_engine("staging")
        edge_engine = r.get_engine("edge-network")
        failures = []
        if staging_engine != "opentofu":
            failures.append(
                f"staging engine: expected 'opentofu', got {staging_engine!r}"
            )
        if edge_engine != "ansible":
            failures.append(
                f"edge-network engine: expected 'ansible', got {edge_engine!r}"
            )
        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 3 — Resource access: correct keys and count for staging
# ---------------------------------------------------------------------------
def test_3_resource_access():
    name = "Test 3 — Resource access: staging has exactly 4 expected resources"
    try:
        r = ManifestReader(MANIFEST_PATH)
        resources = r.get_resources("staging")
        expected_keys = {"payments-vpc", "payments-db", "app-tier", "export-bucket"}
        actual_keys = set(resources.keys())
        failures = []
        if actual_keys != expected_keys:
            failures.append(
                f"resource keys: expected {sorted(expected_keys)}, "
                f"got {sorted(actual_keys)}"
            )
        if len(resources) != 4:
            failures.append(f"resource count: expected 4, got {len(resources)}")
        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 4 — Criticality transitivity
# ---------------------------------------------------------------------------
def test_4_criticality_transitivity():
    name = "Test 4 — Criticality transitivity: payments-vpc inherits critical via payments-db"
    try:
        r = ManifestReader(MANIFEST_PATH)
        crit = r.resolve_criticality("staging")

        failures = []

        # payments-vpc is declared 'high' but payments-db (critical) depends_on it,
        # so it must emerge 'critical'.
        if crit.get("payments-vpc") != "critical":
            failures.append(
                f"payments-vpc: expected 'critical', got {crit.get('payments-vpc')!r}"
            )
        if crit.get("payments-db") != "critical":
            failures.append(
                f"payments-db: expected 'critical', got {crit.get('payments-db')!r}"
            )
        if crit.get("app-tier") != "critical":
            failures.append(
                f"app-tier: expected 'critical', got {crit.get('app-tier')!r}"
            )
        # export-bucket has no critical dependents; stays 'high'
        if crit.get("export-bucket") != "high":
            failures.append(
                f"export-bucket: expected 'high', got {crit.get('export-bucket')!r}"
            )

        # edge-network has no resources block
        edge_crit = r.resolve_criticality("edge-network")
        if edge_crit != {}:
            failures.append(
                f"edge-network criticality: expected {{}}, got {edge_crit!r}"
            )

        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 5 — Round-trip preserves comments
# ---------------------------------------------------------------------------
def test_5_roundtrip_preserves_comments():
    name = "Test 5 — Round-trip write_to() preserves inline and block comments"
    try:
        r = ManifestReader(MANIFEST_PATH)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            tmp = f.name
        r.write_to(tmp)
        with open(tmp) as f:
            content = f.read()
        os.unlink(tmp)

        failures = []
        if "# Kuala Lumpur, Malaysia" not in content:
            failures.append(
                "missing comment '# Kuala Lumpur, Malaysia' in round-tripped output"
            )
        if "# Why: private network boundary" not in content:
            failures.append(
                "missing comment '# Why: private network boundary' in round-tripped output"
            )
        if "# Agent-maintained" not in content:
            failures.append(
                "missing comment '# Agent-maintained' in round-tripped output"
            )

        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 6 — State update + write preserves comments and correct data
# ---------------------------------------------------------------------------
def test_6_state_update_and_write():
    name = (
        "Test 6 — State update: write_to() persists state changes without losing comments"
    )
    try:
        r2 = ManifestReader(MANIFEST_PATH)
        r2.update_resource_state(
            "staging",
            "payments-vpc",
            {
                "status": "applied",
                "resource_id": "vpc-test123",
                "last_applied": "2026-06-06T00:00:00Z",
            },
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            tmp = f.name
        r2.write_to(tmp)

        # Reload and verify state was updated
        r3 = ManifestReader(tmp)
        vpc_state = r3.get_resources("staging")["payments-vpc"]["state"]

        failures = []
        if vpc_state.get("status") != "applied":
            failures.append(
                f"payments-vpc state.status: expected 'applied', got {vpc_state.get('status')!r}"
            )
        if vpc_state.get("resource_id") != "vpc-test123":
            failures.append(
                f"payments-vpc state.resource_id: expected 'vpc-test123', "
                f"got {vpc_state.get('resource_id')!r}"
            )
        if vpc_state.get("last_applied") != "2026-06-06T00:00:00Z":
            failures.append(
                f"payments-vpc state.last_applied: expected '2026-06-06T00:00:00Z', "
                f"got {vpc_state.get('last_applied')!r}"
            )

        # Verify other resources are untouched
        db_state = r3.get_resources("staging")["payments-db"]["state"]
        if db_state.get("status") != "pending":
            failures.append(
                f"payments-db state.status (untouched): expected 'pending', "
                f"got {db_state.get('status')!r}"
            )

        # Verify comments survived the write
        with open(tmp) as f:
            written = f.read()
        os.unlink(tmp)

        if "# Why: private network boundary" not in written:
            failures.append(
                "missing comment '# Why: private network boundary' after state update write"
            )
        if "# Kuala Lumpur, Malaysia" not in written:
            failures.append(
                "missing comment '# Kuala Lumpur, Malaysia' after state update write"
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
    print("Running manifest_reader white-box tests...")
    print()

    test_1_parse()
    test_2_engine_resolution()
    test_3_resource_access()
    test_4_criticality_transitivity()
    test_5_roundtrip_preserves_comments()
    test_6_state_update_and_write()

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
