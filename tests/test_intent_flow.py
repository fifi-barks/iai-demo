"""Black-box intent-flow tests for IAI.

Drives the system exactly as a user would — feeds intent in via
process_intent() and verifies the card that comes back.

No Telegram connection is required. The bot's Telegram transport layer is kept
fully out of scope; process_intent() is the entry point under test.

Pattern: prints PASS/FAIL per test with actual vs expected on failure.
Exits 0 if all tests pass, exits 1 if any fail.

Run from repo root with the venv Python:
    .venv/bin/python tests/test_intent_flow.py
"""

import os
import re
import sys
import traceback

# Ensure the repo root is on sys.path so `agent`, `gates`, and `bot` are importable.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from bot.intent_handler import process_intent, APPROVE_LABEL, DECLINE_LABEL

FIXTURE_PATH = os.path.join(REPO_ROOT, "tests", "fixtures", "infracost_payments_db_pass.json")

# The locked demo intent from docs/demo-scenario.md — must not be altered.
DEMO_INTENT = (
    "Stand up a staging environment for the payments service: "
    "a managed Postgres, an app compute tier, and a private network in AWS, "
    "plus an object-storage bucket in GCP for export files. "
    "Tag it staging, owner payments-team."
)

results = []  # list of (test_name, passed, message)

# Run the pipeline once through process_intent; all tests share this result.
_intent_result = None
_intent_error = None


def _get_intent_result():
    global _intent_result, _intent_error
    if _intent_result is not None:
        return _intent_result, None
    if _intent_error is not None:
        return None, _intent_error
    try:
        _intent_result = process_intent(
            DEMO_INTENT,
            infracost_fixture=FIXTURE_PATH,
        )
        return _intent_result, None
    except Exception:
        _intent_error = traceback.format_exc()
        return None, _intent_error


def record(name, passed, message=""):
    results.append((name, passed, message))
    status = "PASS" if passed else "FAIL"
    print(f"  {status}  {name}")
    if not passed and message:
        for line in message.splitlines():
            print(f"         {line}")


# ---------------------------------------------------------------------------
# Test 1 — Intent flows through: card is returned
# ---------------------------------------------------------------------------
def test_1_card_returned():
    name = "Test 1 — Intent flows through: card is returned"
    result, err = _get_intent_result()
    if err:
        record(name, False, f"process_intent() raised an exception:\n{err}")
        return
    try:
        card = result["card"]
        failures = []

        if not isinstance(card, str):
            failures.append(f"card is not a str, got {type(card)}")
        elif len(card) == 0:
            failures.append("card is an empty string")

        if result["intent"] != DEMO_INTENT:
            failures.append(
                f"intent not echoed back correctly.\n"
                f"  expected: {DEMO_INTENT!r}\n"
                f"  got:      {result['intent']!r}"
            )

        if failures:
            record(name, False, "\n".join(failures))
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 2 — Approve/Decline labels are present (in result dict and in card text)
# ---------------------------------------------------------------------------
def test_2_approve_decline_labels():
    name = "Test 2 — Approve/Decline labels are present in result and card"
    result, err = _get_intent_result()
    if err:
        record(name, False, f"process_intent() raised an exception:\n{err}")
        return
    try:
        card = result["card"]
        failures = []

        if result["approve_label"] != APPROVE_LABEL:
            failures.append(
                f"approve_label mismatch: expected {APPROVE_LABEL!r}, "
                f"got {result['approve_label']!r}"
            )

        if result["decline_label"] != DECLINE_LABEL:
            failures.append(
                f"decline_label mismatch: expected {DECLINE_LABEL!r}, "
                f"got {result['decline_label']!r}"
            )

        # The card text itself must end with the action buttons section.
        if "Approve" not in card:
            failures.append("'Approve' not found in card text")
        if "Decline" not in card:
            failures.append("'Decline' not found in card text")

        if failures:
            record(name, False, "\n".join(failures) + f"\nCard tail: {card[-200:]!r}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 3 — Card covers all five required narrative sections
# ---------------------------------------------------------------------------
def test_3_card_five_sections():
    name = "Test 3 — Card covers all five required narrative sections"
    result, err = _get_intent_result()
    if err:
        record(name, False, f"process_intent() raised an exception:\n{err}")
        return
    try:
        card = result["card"]
        failures = []

        # 1. Resources line
        if not ("Resources" in card or "resource" in card.lower()):
            failures.append(
                "Section 1 (Resources) missing: neither 'Resources' nor 'resource' found in card"
            )

        # 2. Cost line
        if not ("Cost" in card or "month" in card.lower()):
            failures.append(
                "Section 2 (Cost) missing: neither 'Cost' nor 'month' found in card"
            )

        # 3. Security line — must mention the finding
        if not ("Security" in card or "issue" in card.lower()):
            failures.append(
                "Section 3 (Security) missing: neither 'Security' nor 'issue' found in card"
            )

        # 4. Critical line
        if not ("Critical" in card or "critical" in card.lower()):
            failures.append(
                "Section 4 (Critical) missing: neither 'Critical' nor 'critical' found in card"
            )

        # 5. Action buttons
        if "Approve" not in card:
            failures.append("Section 5 (Action) missing: 'Approve' not found in card")
        if "Decline" not in card:
            failures.append("Section 5 (Action) missing: 'Decline' not found in card")

        if failures:
            record(name, False, "\n".join(failures) + f"\nCard:\n{card}")
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 4 — Bot is intent-agnostic: any message produces a card
# ---------------------------------------------------------------------------
def test_4_intent_agnostic():
    name = "Test 4 — Bot is intent-agnostic: any message produces a card"
    alt_intent = "Provision whatever is needed for our payment processing workload."
    try:
        result2 = process_intent(
            alt_intent,
            infracost_fixture=FIXTURE_PATH,
        )
        failures = []

        if not isinstance(result2["card"], str) or len(result2["card"]) == 0:
            failures.append(
                f"card for alt intent is not a non-empty string, got {result2['card']!r}"
            )

        if result2["intent"] != alt_intent:
            failures.append(
                f"intent not echoed back for alt intent.\n"
                f"  expected: {alt_intent!r}\n"
                f"  got:      {result2['intent']!r}"
            )

        if failures:
            record(name, False, "\n".join(failures))
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 5 — Gate findings surface correctly in the card
# ---------------------------------------------------------------------------
def test_5_gate_findings_in_card():
    name = "Test 5 — Gate findings surface correctly in the card"
    result, err = _get_intent_result()
    if err:
        record(name, False, f"process_intent() raised an exception:\n{err}")
        return
    try:
        card = result["card"]
        raw = result["raw"]
        failures = []

        # SSH finding must be named in plain English.
        if "SSH" not in card:
            failures.append(
                "SSH finding not named in plain English: 'SSH' not found in card"
            )

        # Raw check IDs must never appear in the card.
        for check_id in ("CKV_AWS_24", "CKV_AWS_16", "CKV_AWS_17"):
            if check_id in card:
                failures.append(
                    f"Raw check ID '{check_id}' exposed in card — must be suppressed"
                )

        # Cost figure must be traceable: within $5 of gate output.
        gate_cost = raw["cost"]["monthly_cost"]
        card_costs = [int(x) for x in re.findall(r'\$(\d+)', card)]
        if not any(abs(c - gate_cost) <= 5 for c in card_costs):
            failures.append(
                f"No card cost figure within $5 of gate cost {gate_cost}.\n"
                f"  Card dollar figures: {card_costs}\n"
                f"  Cost lines: {[l for l in card.splitlines() if 'Cost' in l or '$' in l]}"
            )

        # Snapshot language required for data-bearing resources.
        if "snapshot" not in card.lower():
            failures.append(
                "Snapshot language absent from card — expected 'snapshot' "
                "(case-insensitive) for data-bearing resource"
            )

        if failures:
            record(name, False, "\n".join(failures))
        else:
            record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 6 — Telegram module is importable without a live token
# ---------------------------------------------------------------------------
def test_6_telegram_importable():
    name = "Test 6 — Telegram module is importable without a live token"
    try:
        import bot.telegram_bot  # noqa: F401 — import side-effect is the test
        importable = True
    except ImportError as e:
        importable = False
        record(name, False, f"Import error: {e}")
        return
    except Exception as e:
        # Any other exception (e.g., RuntimeError on token access) would indicate
        # the module is running code at import time that it shouldn't.
        record(name, False, f"Unexpected exception on import: {type(e).__name__}: {e}")
        return

    record(name, True)


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running intent-flow black-box tests...")
    print()

    # Pre-flight: confirm process_intent() can be invoked.
    result, err = _get_intent_result()
    if err:
        print("  FATAL  process_intent() raised an exception before tests could run:")
        for line in err.splitlines():
            print(f"         {line}")
        sys.exit(1)

    test_1_card_returned()
    test_2_approve_decline_labels()
    test_3_card_five_sections()
    test_4_intent_agnostic()
    test_5_gate_findings_in_card()
    test_6_telegram_importable()

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

    # Print raw gate findings for one-line trace.
    print()
    print("RAW GATE FINDINGS SUMMARY:")
    raw = result["raw"]
    print(
        f"  Security: status={raw['security']['status']}, "
        f"findings={[f['check_id'] for f in raw['security']['findings']]}, "
        f"passed_checks={raw['security']['passed_checks']}"
    )
    print(
        f"  Cost:     status={raw['cost']['status']}, "
        f"monthly_cost={raw['cost']['monthly_cost']}"
    )
    print(
        f"  Plan:     status={raw['plan']['status']}, "
        f"resource_count={raw['plan']['resource_count']}, "
        f"to_add={raw['plan']['to_add']}, "
        f"to_change={raw['plan']['to_change']}, "
        f"to_destroy={raw['plan']['to_destroy']}"
    )
    print()
    # Build the cost-traceable flag separately to avoid f-string escaping issues.
    _card_dollar_ints = [int(x) for x in re.findall(r'\$(\d+)', result["card"])]
    _cost_traceable = any(
        abs(c - raw["cost"]["monthly_cost"]) <= 5 for c in _card_dollar_ints
    )
    print(
        "Trace: intent in → card sections present "
        f"(Resources={'resource' in result['card'].lower()}, "
        f"Cost={'month' in result['card'].lower() or 'Cost' in result['card']}, "
        f"Security={'SSH' in result['card']}, "
        f"Critical={'critical' in result['card'].lower()}, "
        f"Actions={'Approve' in result['card'] and 'Decline' in result['card']}) "
        f"→ gate findings correct "
        f"(SSH={'SSH' in result['card']}, "
        f"snapshot={'snapshot' in result['card'].lower()}, "
        f"cost_traceable={_cost_traceable})"
    )
    print()

    if passed == total:
        print("Overall: PASS")
        sys.exit(0)
    else:
        failed_names = [n for n, ok, _ in results if not ok]
        print(f"Overall: FAIL — failing tests: {', '.join(failed_names)}")
        sys.exit(1)
