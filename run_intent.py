#!/usr/bin/env python3
"""IAI CLI — run the full intent pipeline without Telegram.

Usage:
    python run_intent.py "Set up the payments staging environment."

Environment variables (all optional):
    IAI_MANIFEST          Path to manifest.yaml (default: manifest.yaml)
    IAI_INFRACOST_FIXTURE Path to a pre-captured Infracost JSON file.
                          If unset, live `infracost breakdown` is run against
                          the generated HCL (requires infracost on PATH).

The pipeline:
    intent text → LLM parse (Groq by default; passthrough fallback)
               → manifest read → IaC generate → three-gate validation
               → synthesized approval card → y/n prompt → apply (if approved)
               → manifest state update

This entry point is the open-source alternative to the Telegram bot — zero
messaging infrastructure required. All blocking work (tofu plan + apply) runs
synchronously; the Telegram path uses asyncio.to_thread() for the same calls.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO_ROOT)

from bot.intent_handler import APPROVE_LABEL, DECLINE_LABEL, process_intent
from agent.pipeline import (
    TERRAFORM_GENERATED_DIR,
    TERRAFORM_SNAPSHOT_DIR,
    apply_and_finalize,
)


def main() -> None:
    intent = " ".join(sys.argv[1:]).strip()
    if not intent:
        print("Usage: python run_intent.py \"<intent text>\"")
        print()
        print("Example:")
        print('  python run_intent.py "Set up the payments staging environment."')
        sys.exit(1)

    manifest = os.environ.get("IAI_MANIFEST", "manifest.yaml")
    fixture = os.environ.get("IAI_INFRACOST_FIXTURE") or None

    from agent.llm_client import active_config
    print(f"\nIntent: {intent!r}")
    print(f"LLM:    {active_config()}")
    print("\nRunning gate pipeline…\n")

    from bot.intent_handler import MAX_CLARIFY_ROUNDS, clarify_question, compose_dialogue

    def _resolve(text):
        return process_intent(text, manifest_path=manifest, infracost_fixture=fixture)

    try:
        result = _resolve(intent)
        # If the agent needs clarification, answer it interactively and re-resolve
        # the accumulated dialogue — same multi-turn behavior as the Telegram bot.
        history = [f"User: {intent}"]
        rounds = 0
        while result.get("action") == "clarify" and rounds < MAX_CLARIFY_ROUNDS:
            print(result["card"])
            try:
                answer = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                sys.exit(0)
            history.append(f"Agent: {clarify_question(result)}")
            history.append(f"User: {answer}")
            result = _resolve(compose_dialogue(history))
            rounds += 1
    except Exception as exc:
        print(f"✗ Pipeline failed: {exc}")
        sys.exit(1)

    if result.get("action") == "clarify":
        print("\nStill ambiguous — try restating it in one sentence "
              "(e.g. \"tear down the payments staging environment\").")
        sys.exit(0)

    print("=" * 60)
    print(result["card"])
    print("=" * 60)
    print()

    try:
        answer = input(f"Approve? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nDeclined.")
        sys.exit(0)

    if answer in ("y", "yes"):
        action = result.get("action", "provision")
        if action == "destroy":
            print("\nDestroying infrastructure…")
            try:
                from agent.pipeline import destroy_and_reset
                destroy_and_reset(TERRAFORM_GENERATED_DIR, manifest)
                print("✓ Resources destroyed. Manifest reset to pending.")
            except Exception as exc:
                print(f"✗ Destroy failed: {exc}")
                sys.exit(1)
        else:
            print("\nApplying infrastructure…")
            try:
                apply_and_finalize(TERRAFORM_GENERATED_DIR, TERRAFORM_SNAPSHOT_DIR, manifest)
                print("✓ Infrastructure applied. Manifest updated.")
            except Exception as exc:
                print(f"✗ Apply failed: {exc}")
                sys.exit(1)
    else:
        print("Declined — no changes applied.")


if __name__ == "__main__":
    main()
