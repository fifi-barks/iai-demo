"""Intent handler — Telegram-free core of the IAI bot.

Receives a plain-language intent string and runs the full pipeline:
manifest read → IaC generate → three gates → synthesized approval card.

Kept separate from telegram_bot.py so it can be imported and tested
without a live Telegram connection or bot token.
"""

import os

MANIFEST_PATH = os.environ.get("IAI_MANIFEST", "manifest.yaml")
INFRACOST_FIXTURE = os.environ.get(
    "IAI_INFRACOST_FIXTURE",
    "tests/fixtures/infracost_payments_db_pass.json",
)

APPROVE_LABEL = "✅ Approve"
DECLINE_LABEL = "❌ Decline"


def process_intent(
    intent_text: str,
    manifest_path: str = MANIFEST_PATH,
    infracost_fixture: str | None = INFRACOST_FIXTURE,
) -> dict:
    """Process a plain-language intent and return the pipeline result.

    Returns:
        {
            "card": str,          # the full approval card text
            "raw": dict,          # raw gate results (security, cost, plan)
            "approve_label": str, # button label for Approve
            "decline_label": str, # button label for Decline
            "intent": str,        # the original intent text, echoed back
        }
    """
    from agent.pipeline import run_pipeline
    result = run_pipeline(manifest_path, infracost_fixture=infracost_fixture)
    return {
        "card": result["card"],
        "raw": result["raw"],
        "approve_label": APPROVE_LABEL,
        "decline_label": DECLINE_LABEL,
        "intent": intent_text,
    }
