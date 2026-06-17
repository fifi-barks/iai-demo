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
    name = "Test 3 — Resource access: staging has exactly 2 expected resources"
    try:
        r = ManifestReader(MANIFEST_PATH)
        resources = r.get_resources("staging")
        expected_keys = {"app-tier", "export-bucket"}
        actual_keys = set(resources.keys())
        failures = []
        if actual_keys != expected_keys:
            failures.append(
                f"resource keys: expected {sorted(expected_keys)}, "
                f"got {sorted(actual_keys)}"
            )
        if len(resources) != 2:
            failures.append(f"resource count: expected 2, got {len(resources)}")
        if not failures:
            record(name, True)
        else:
            record(name, False, "; ".join(failures))
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 4 — Criticality: direct critical + high, no transitivity needed
# ---------------------------------------------------------------------------
def test_4_criticality():
    name = "Test 4 — Criticality: app-tier=critical (direct), export-bucket=high, edge-network={}"
    try:
        r = ManifestReader(MANIFEST_PATH)
        crit = r.resolve_criticality("staging")

        failures = []

        # app-tier is declared 'critical' directly (depends_on=[])
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
        if "# Why: compute tier serving" not in content:
            failures.append(
                "missing comment '# Why: compute tier serving' in round-tripped output"
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
            "app-tier",
            {
                "status": "applied",
                "resource_id": "i-0abc1234",
                "last_applied": "2026-06-17T00:00:00Z",
            },
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            tmp = f.name
        r2.write_to(tmp)

        # Reload and verify state was updated
        r3 = ManifestReader(tmp)
        app_tier_state = r3.get_resources("staging")["app-tier"]["state"]

        failures = []
        if app_tier_state.get("status") != "applied":
            failures.append(
                f"app-tier state.status: expected 'applied', got {app_tier_state.get('status')!r}"
            )
        if app_tier_state.get("resource_id") != "i-0abc1234":
            failures.append(
                f"app-tier state.resource_id: expected 'i-0abc1234', "
                f"got {app_tier_state.get('resource_id')!r}"
            )
        if app_tier_state.get("last_applied") != "2026-06-17T00:00:00Z":
            failures.append(
                f"app-tier state.last_applied: expected '2026-06-17T00:00:00Z', "
                f"got {app_tier_state.get('last_applied')!r}"
            )

        # Verify other resources are untouched
        bucket_state = r3.get_resources("staging")["export-bucket"]["state"]
        if bucket_state.get("status") != "pending":
            failures.append(
                f"export-bucket state.status (untouched): expected 'pending', "
                f"got {bucket_state.get('status')!r}"
            )

        # Verify comments survived the write
        with open(tmp) as f:
            written = f.read()
        os.unlink(tmp)

        if "# Why: compute tier serving" not in written:
            failures.append(
                "missing comment '# Why: compute tier serving' after state update write"
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
    test_4_criticality()
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
