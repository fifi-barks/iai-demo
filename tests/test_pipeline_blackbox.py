"""Black-box pipeline tests for IAI.

Drives the full pipeline (intent in -> gate findings -> approval card) as a
user would, then verifies that the card is a faithful reflection of what the
gates actually found. No drift between the card the human reads and the raw
gate outputs is the central trust claim.

Pattern: prints PASS/FAIL per test with actual vs expected on failure.
Exits 0 if all tests pass, exits 1 if any fail.

Run from repo root with the venv Python:
    .venv/bin/python tests/test_pipeline_blackbox.py
"""

import os
import re
import sys
import traceback

# Ensure the repo root is on sys.path so `agent` and `gates` are importable.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from agent.pipeline import run_pipeline
from agent.manifest_reader import ManifestReader

MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest.yaml")
FIXTURE_PATH = os.path.join(REPO_ROOT, "tests", "fixtures", "infracost_payments_db_pass.json")

results = []  # list of (test_name, passed, message)

# Run the pipeline once; all tests share this result.
_pipeline_result = None
_pipeline_error = None

def _get_pipeline_result():
    global _pipeline_result, _pipeline_error
    if _pipeline_result is not None:
        return _pipeline_result, None
    if _pipeline_error is not None:
        return None, _pipeline_error
    try:
        _pipeline_result = run_pipeline(
            MANIFEST_PATH,
            infracost_fixture=FIXTURE_PATH,
        )
        return _pipeline_result, None
    except Exception as e:
        _pipeline_error = traceback.format_exc()
        return None, _pipeline_error


def record(name, passed, message=""):
    results.append((name, passed, message))
    status = "PASS" if passed else "FAIL"
    if passed:
        print(f"  {status}  {name}")
    else:
        print(f"  {status}  {name}")
        if message:
            # Indent multi-line messages for readability.
            for line in message.splitlines():
                print(f"         {line}")


# ---------------------------------------------------------------------------
# Test 1 — Security: card reports the exact number of issues found by the gate
# ---------------------------------------------------------------------------
def test_1_security_issue_count():
    name = "Test 1 — Security: card reports the exact number of issues found by the gate"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        raw = result["raw"]
        gate_finding_count = len(raw["security"]["findings"])

        if gate_finding_count == 1:
            passed = "1 issue caught" in card
            if not passed:
                record(name, False,
                       f"Expected '1 issue caught' in card but not found.\n"
                       f"gate_finding_count={gate_finding_count}\n"
                       f"Card security line: {[l for l in card.splitlines() if 'Security' in l or 'issue' in l or 'check' in l]}")
            else:
                record(name, True)
        elif gate_finding_count == 0:
            passed = "All security checks pass" in card
            if not passed:
                record(name, False,
                       f"Expected 'All security checks pass' in card but not found.\n"
                       f"gate_finding_count=0\n"
                       f"Card excerpt: {card[:300]}")
            else:
                record(name, True)
        else:
            passed = f"{gate_finding_count} issues" in card
            if not passed:
                record(name, False,
                       f"Expected '{gate_finding_count} issues' in card but not found.\n"
                       f"gate_finding_count={gate_finding_count}")
            else:
                record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 2 — Security: card names the finding in plain English (no check IDs)
# ---------------------------------------------------------------------------
def test_2_security_no_check_ids_plain_english():
    name = "Test 2 — Security: card names the finding in plain English (no check IDs)"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        raw = result["raw"]
        failures = []

        # Raw check IDs must never appear in the card.
        for check_id in ("CKV_AWS_24", "CKV_AWS_16", "CKV_AWS_17"):
            if check_id in card:
                failures.append(f"card must not expose check ID '{check_id}'")

        # If CKV_AWS_24 is in the findings, the card must use SSH language
        # and describe open-internet exposure.
        findings = raw["security"]["findings"]
        if any(f["check_id"] == "CKV_AWS_24" for f in findings):
            if "SSH" not in card:
                failures.append(
                    "card must mention SSH for CKV_AWS_24 finding (not found)"
                )
            if "0.0.0.0/0" not in card and "entire internet" not in card:
                failures.append(
                    "card must describe open-internet exposure "
                    "('0.0.0.0/0' or 'entire internet') for CKV_AWS_24 (neither found)"
                )

        if failures:
            record(name, False,
                   "\n".join(failures) + f"\nCard excerpt: {card[:400]}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 3 — Security: passed checks appear in the card as confirmations
# ---------------------------------------------------------------------------
def test_3_security_passed_checks_confirmed():
    name = "Test 3 — Security: passed checks appear in the card as confirmations"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        raw = result["raw"]
        passed = raw["security"]["passed_checks"]
        failures = []

        if "CKV_AWS_16" in passed:
            encryption_mentioned = any(
                phrase in card for phrase in ["Encryption at rest", "encryption"]
            )
            if not encryption_mentioned:
                failures.append(
                    "CKV_AWS_16 passed but card does not confirm encryption "
                    "(expected 'Encryption at rest' or 'encryption')"
                )

        if "CKV_AWS_17" in passed:
            public_access_mentioned = any(
                phrase in card for phrase in ["Public access", "publicly accessible"]
            )
            if not public_access_mentioned:
                failures.append(
                    "CKV_AWS_17 passed but card does not confirm public-access block "
                    "(expected 'Public access' or 'publicly accessible')"
                )

        if failures:
            record(name, False,
                   "\n".join(failures) +
                   f"\npassed_checks={passed}" +
                   f"\nCard security section: {[l for l in card.splitlines() if 'Security' in l or 'Encryption' in l or 'Public' in l or 'check' in l]}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 4 — Cost: card cost figure traces to gate output
# ---------------------------------------------------------------------------
def test_4_cost_figure_traces_to_gate():
    name = "Test 4 — Cost: card cost figure traces to gate output"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        raw = result["raw"]
        gate_cost = raw["cost"]["monthly_cost"]  # e.g. 39.71

        # The card must contain a dollar figure within $5 of the gate output.
        card_costs = re.findall(r'\$(\d+)', card)
        card_cost_ints = [int(x) for x in card_costs]

        within_range = any(abs(c - gate_cost) <= 5 for c in card_cost_ints)
        if not within_range:
            record(name, False,
                   f"No card cost within $5 of gate cost {gate_cost}.\n"
                   f"Card costs found: {card_cost_ints}\n"
                   f"Card cost line: {[l for l in card.splitlines() if 'Cost' in l or '$' in l]}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 5 — Plan: card resource count matches gate count
# ---------------------------------------------------------------------------
def test_5_plan_resource_count():
    name = "Test 5 — Plan: card resource count matches gate count"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        raw = result["raw"]
        gate_count = raw["plan"]["resource_count"]

        if str(gate_count) not in card:
            record(name, False,
                   f"Card must mention resource count {gate_count}.\n"
                   f"Card excerpt (first 300 chars): {card[:300]}\n"
                   f"Full plan result: {raw['plan']}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 6 — Criticality: card lists every critical resource from the reader
# ---------------------------------------------------------------------------
def test_6_criticality_all_critical_resources_listed():
    name = "Test 6 — Criticality: card lists every critical resource from the reader"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        reader = ManifestReader(MANIFEST_PATH)
        effective = reader.resolve_criticality("staging")
        critical_resources = [name for name, crit in effective.items() if crit == "critical"]

        failures = []
        for resource_name in critical_resources:
            # Resource name may appear with hyphens or underscores in the card.
            name_variants = [resource_name, resource_name.replace("-", "_")]
            if not any(v in card for v in name_variants):
                failures.append(
                    f"Critical resource '{resource_name}' (variants: {name_variants}) "
                    f"not mentioned in card"
                )

        if failures:
            record(name, False,
                   "\n".join(failures) +
                   f"\ncritical_resources={critical_resources}" +
                   f"\nCard critical section: {[l for l in card.splitlines() if 'Critical' in l or 'critical' in l or 'payments' in l or 'app' in l]}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 7 — Data-bearing: snapshot intent in card for data-bearing resources
# ---------------------------------------------------------------------------
def test_7_data_bearing_snapshot_language():
    name = "Test 7 — Data-bearing: snapshot intent in card for data-bearing resources"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        reader = ManifestReader(MANIFEST_PATH)
        resources = reader.get_resources("staging")
        data_bearing = [rname for rname, r in resources.items() if r.get("data_bearing")]

        failures = []
        snapshot_in_card = "snapshot" in card.lower()

        for resource_name in data_bearing:
            name_variants = [resource_name, resource_name.replace("-", "_")]
            resource_in_card = any(v in card for v in name_variants)

            if not resource_in_card:
                failures.append(
                    f"Data-bearing resource '{resource_name}' not mentioned in card"
                )
            if not snapshot_in_card:
                failures.append(
                    f"Card has no snapshot language for data-bearing resource '{resource_name}' "
                    f"(searched for 'snapshot' case-insensitively)"
                )

        if failures:
            record(name, False,
                   "\n".join(failures) +
                   f"\ndata_bearing={data_bearing}" +
                   f"\nCard critical section: {[l for l in card.splitlines() if 'Critical' in l or 'snapshot' in l.lower() or 'payments' in l]}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 8 — No raw tool output in card
# ---------------------------------------------------------------------------
def test_8_no_raw_tool_output_in_card():
    name = "Test 8 — No raw tool output in card"
    result, err = _get_pipeline_result()
    if err:
        record(name, False, f"Pipeline failed: {err}")
        return
    try:
        card = result["card"]
        # Things that must NEVER appear in the card.
        forbidden = [
            "checkov",                  # tool name
            "infracost",                # tool name
            "CKV_",                     # check ID prefix
            "monthlyCost",              # Infracost JSON field
            "aws_security_group_rule",  # Terraform resource type
            "FAILED for",               # Checkov raw output
            "Passed checks",            # Checkov raw section header
        ]
        failures = []
        for term in forbidden:
            if term.lower() in card.lower():
                # Find the surrounding context for a helpful failure message.
                idx = card.lower().find(term.lower())
                context = card[max(0, idx - 30):idx + len(term) + 30]
                failures.append(
                    f"Card contains forbidden raw-output term: '{term}' — context: ...{context!r}..."
                )

        if failures:
            record(name, False, "\n".join(failures))
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running pipeline black-box tests...")
    print()

    # Pre-flight: confirm the pipeline can be invoked.
    result, err = _get_pipeline_result()
    if err:
        print(f"  FATAL  Pipeline raised an exception before tests could run:")
        for line in err.splitlines():
            print(f"         {line}")
        sys.exit(1)

    test_1_security_issue_count()
    test_2_security_no_check_ids_plain_english()
    test_3_security_passed_checks_confirmed()
    test_4_cost_figure_traces_to_gate()
    test_5_plan_resource_count()
    test_6_criticality_all_critical_resources_listed()
    test_7_data_bearing_snapshot_language()
    test_8_no_raw_tool_output_in_card()

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    # Print the full card text so the orchestrator can review it.
    print()
    print("=" * 60)
    print("FULL CARD TEXT (for orchestrator review):")
    print("=" * 60)
    print(result["card"])
    print("=" * 60)

    # Print a summary of raw gate findings for traceability.
    print()
    print("RAW GATE FINDINGS SUMMARY:")
    raw = result["raw"]
    print(f"  Security: status={raw['security']['status']}, "
          f"findings={[f['check_id'] for f in raw['security']['findings']]}, "
          f"passed_checks={raw['security']['passed_checks']}")
    print(f"  Cost:     status={raw['cost']['status']}, "
          f"monthly_cost={raw['cost']['monthly_cost']}")
    print(f"  Plan:     status={raw['plan']['status']}, "
          f"resource_count={raw['plan']['resource_count']}, "
          f"to_add={raw['plan']['to_add']}, "
          f"to_change={raw['plan']['to_change']}, "
          f"to_destroy={raw['plan']['to_destroy']}")
    print()

    if passed == total:
        print("Overall: PASS")
        sys.exit(0)
    else:
        failed_names = [n for n, ok, _ in results if not ok]
        print(f"Overall: FAIL — failing tests: {', '.join(failed_names)}")
        sys.exit(1)
