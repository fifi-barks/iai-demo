#!/usr/bin/env python3
"""IAI CLI — run the full intent pipeline without Telegram.

Usage:
    python run_intent.py "Stand up a staging environment for the payments service: \
an EC2 app tier in AWS and an export bucket in GCP."

Environment variables (all optional):
    IAI_MANIFEST          Path to manifest.yaml (default: manifest.yaml)
    IAI_INFRACOST_FIXTURE Path to a pre-captured Infracost JSON file.
                          If unset, live `infracost breakdown` is run against
                          the generated HCL (requires infracost on PATH).

The pipeline:
    intent text → Ollama/phi parse (or passthrough if Ollama not running)
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
        print(
            '  python run_intent.py "Stand up a staging environment for the payments '
            'service: an EC2 app tier in AWS and an export bucket in GCP."'
        )
        sys.exit(1)

    manifest = os.environ.get("IAI_MANIFEST", "manifest.yaml")
    fixture = os.environ.get("IAI_INFRACOST_FIXTURE") or None

    from agent.llm_client import active_config
    print(f"\nIntent: {intent!r}")
    print(f"LLM:    {active_config()}")
    print("\nRunning gate pipeline…\n")

    try:
        result = process_intent(intent, manifest_path=manifest, infracost_fixture=fixture)
    except Exception as exc:
        print(f"✗ Pipeline failed: {exc}")
        sys.exit(1)

    # The agent reasoned the request is ambiguous — surface its question and stop.
    # Nothing was generated or applied; re-run with a clearer request.
    if result.get("action") == "clarify":
        print(result["card"])
        understanding = (result.get("parsed_intent") or {}).get("understanding")
        if understanding:
            print(f"\n(what I understood so far: {understanding})")
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
