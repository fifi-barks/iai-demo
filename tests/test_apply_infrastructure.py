"""White-box tests for agent.pipeline.apply_infrastructure() / _run_tofu().

Locks in the Phase 1 apply-hang fix: every `tofu plan` / `tofu apply` call
goes through _run_tofu(), which enforces a timeout and converts both a
non-zero exit and a subprocess.TimeoutExpired into a RuntimeError with a
clear message — never a silent hang (the original bug).

subprocess.run is mocked throughout; no real `tofu` binary is invoked and no
files under terraform/generated/ are touched — a fresh tempdir stands in for
terraform_dir/snapshot_dir on each test.

Pattern: prints PASS/FAIL per test with actual vs expected on failure.
Exits 0 if all tests pass, exits 1 if any fail.
Run from repo root with the venv Python:
    .venv/bin/python tests/test_apply_infrastructure.py
"""

import os
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch

# Ensure the repo root is on sys.path so `agent` is importable.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from agent.pipeline import apply_infrastructure, APPLY_TIMEOUT_SECONDS

results = []  # list of (test_name, passed, message)


def record(name, passed, message=""):
    results.append((name, passed, message))
    status = "PASS" if passed else "FAIL"
    if passed:
        print(f"  {status}  {name}")
    else:
        print(f"  {status}  {name}")
        if message:
            for line in message.splitlines():
                print(f"         {line}")


# ---------------------------------------------------------------------------
# Test 1 — Success path: plan + apply both exit 0, expected dict returned
# ---------------------------------------------------------------------------
def test_1_success_path_returns_expected_dict():
    name = "Test 1 — Success path: plan + apply both exit 0, expected dict returned"
    try:
        plan_proc = subprocess.CompletedProcess(
            args=["tofu", "plan", "-no-color", "-lock=false"],
            returncode=0,
            stdout="Plan: 1 to add, 0 to change, 0 to destroy.",
            stderr="",
        )
        apply_proc = subprocess.CompletedProcess(
            args=["tofu", "apply", "-auto-approve", "-no-color"],
            returncode=0,
            stdout="Apply complete! Resources: 1 added, 0 changed, 0 destroyed.",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as terraform_dir, \
                tempfile.TemporaryDirectory() as snapshot_dir:
            with patch(
                "agent.pipeline.subprocess.run", side_effect=[plan_proc, apply_proc]
            ) as mock_run:
                result = apply_infrastructure(terraform_dir, snapshot_dir)

            failures = []
            if result.get("status") != "success":
                failures.append(f"status: expected 'success', got {result.get('status')!r}")
            if "Plan: 1 to add" not in result.get("output", ""):
                failures.append("output missing plan stdout")
            if "Apply complete!" not in result.get("output", ""):
                failures.append("output missing apply stdout")

            snap_path = result.get("state_snapshot_path", "")
            if not os.path.exists(snap_path):
                failures.append(f"state_snapshot_path does not exist: {snap_path!r}")

            if mock_run.call_count != 2:
                failures.append(
                    f"expected subprocess.run called twice (plan, apply), got {mock_run.call_count}"
                )
            else:
                plan_args = mock_run.call_args_list[0].args[0]
                apply_args = mock_run.call_args_list[1].args[0]
                if plan_args != ["tofu", "plan", "-no-color", "-lock=false"]:
                    failures.append(f"unexpected plan args: {plan_args!r}")
                if apply_args != ["tofu", "apply", "-auto-approve", "-no-color"]:
                    failures.append(f"unexpected apply args: {apply_args!r}")
                # Both calls must pass a timeout — the entire point of the fix.
                for call in mock_run.call_args_list:
                    if call.kwargs.get("timeout") != APPLY_TIMEOUT_SECONDS:
                        failures.append(
                            f"call missing timeout={APPLY_TIMEOUT_SECONDS}: kwargs={call.kwargs!r}"
                        )

            if failures:
                record(name, False, "\n".join(failures))
            else:
                record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 2 — Non-zero exit: RuntimeError raised, message contains stderr
# ---------------------------------------------------------------------------
def test_2_nonzero_exit_raises_runtimeerror_with_stderr():
    name = "Test 2 — Non-zero exit: RuntimeError raised, message contains stderr"
    try:
        plan_proc = subprocess.CompletedProcess(
            args=["tofu", "plan", "-no-color", "-lock=false"],
            returncode=1,
            stdout="",
            stderr="Error: invalid credentials",
        )

        with tempfile.TemporaryDirectory() as terraform_dir, \
                tempfile.TemporaryDirectory() as snapshot_dir:
            with patch("agent.pipeline.subprocess.run", return_value=plan_proc):
                try:
                    apply_infrastructure(terraform_dir, snapshot_dir)
                    record(name, False, "apply_infrastructure() did not raise for a non-zero exit")
                    return
                except RuntimeError as exc:
                    msg = str(exc)
                    failures = []
                    if "Error: invalid credentials" not in msg:
                        failures.append(f"RuntimeError message missing stderr.\n  message: {msg}")
                    if "tofu plan" not in msg:
                        failures.append(f"RuntimeError message missing failing command.\n  message: {msg}")
                    if failures:
                        record(name, False, "\n".join(failures))
                    else:
                        record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 3 — Timeout: subprocess.TimeoutExpired converted to clear RuntimeError
# ---------------------------------------------------------------------------
def test_3_timeout_raises_runtimeerror_not_hang():
    name = "Test 3 — Timeout: subprocess.TimeoutExpired converted to clear RuntimeError"
    try:
        timeout_exc = subprocess.TimeoutExpired(
            cmd=["tofu", "plan", "-no-color", "-lock=false"],
            timeout=APPLY_TIMEOUT_SECONDS,
            output="partial plan output...",
            stderr="partial stderr...",
        )

        with tempfile.TemporaryDirectory() as terraform_dir, \
                tempfile.TemporaryDirectory() as snapshot_dir:
            with patch("agent.pipeline.subprocess.run", side_effect=timeout_exc):
                try:
                    apply_infrastructure(terraform_dir, snapshot_dir)
                    record(
                        name, False,
                        "apply_infrastructure() did not raise on TimeoutExpired "
                        "(this is the original hang bug)",
                    )
                    return
                except RuntimeError as exc:
                    msg = str(exc)
                    failures = []
                    if "timed out" not in msg:
                        failures.append(f"message missing 'timed out': {msg}")
                    if str(APPLY_TIMEOUT_SECONDS) not in msg:
                        failures.append(
                            f"message missing timeout value {APPLY_TIMEOUT_SECONDS}: {msg}"
                        )
                    if "partial plan output" not in msg and "partial stderr" not in msg:
                        failures.append(f"message missing partial output: {msg}")
                    if failures:
                        record(name, False, "\n".join(failures))
                    else:
                        record(name, True)
                except subprocess.TimeoutExpired:
                    record(
                        name, False,
                        "subprocess.TimeoutExpired propagated uncaught — this is the original hang bug",
                    )
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Test 4 — Existing terraform.tfstate is snapshotted before plan/apply run
# ---------------------------------------------------------------------------
def test_4_existing_state_is_snapshotted_before_apply():
    name = "Test 4 — Existing terraform.tfstate is snapshotted before plan/apply run"
    try:
        plan_proc = subprocess.CompletedProcess(
            args=["tofu", "plan", "-no-color", "-lock=false"], returncode=0, stdout="", stderr=""
        )
        apply_proc = subprocess.CompletedProcess(
            args=["tofu", "apply", "-auto-approve", "-no-color"], returncode=0, stdout="", stderr=""
        )

        with tempfile.TemporaryDirectory() as terraform_dir, \
                tempfile.TemporaryDirectory() as snapshot_dir:
            state_path = os.path.join(terraform_dir, "terraform.tfstate")
            with open(state_path, "w") as fh:
                fh.write('{"version": 4, "resources": []}')

            with patch("agent.pipeline.subprocess.run", side_effect=[plan_proc, apply_proc]):
                result = apply_infrastructure(terraform_dir, snapshot_dir)

            snap_path = result["state_snapshot_path"]
            with open(snap_path) as fh:
                snap_contents = fh.read()

            if '"version": 4' not in snap_contents:
                record(name, False, f"snapshot missing pre-apply state.\n  snapshot: {snap_contents}")
            else:
                record(name, True)
    except Exception:
        record(name, False, traceback.format_exc())


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running apply_infrastructure() white-box tests...")
    print()

    test_1_success_path_returns_expected_dict()
    test_2_nonzero_exit_raises_runtimeerror_with_stderr()
    test_3_timeout_raises_runtimeerror_not_hang()
    test_4_existing_state_is_snapshotted_before_apply()

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
