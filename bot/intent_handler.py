"""Intent handler — Telegram-free core of the IAI bot.

Receives a plain-language intent string, sends it to an LLM (a fast hosted model
by default — Groq — with a local Ollama model and a keyword passthrough as
fallbacks) to extract structured infrastructure requirements, then runs the full
pipeline: manifest read → IaC generate → three gates → synthesized approval card.

LLM provider selection and the parsing logic live in agent/llm_client.py; this
module stays transport-agnostic so it can be imported and tested without a live
Telegram connection or bot token.
"""

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from agent.llm_client import parse_intent

logger = logging.getLogger(__name__)

MANIFEST_PATH = os.environ.get("IAI_MANIFEST", "manifest.yaml")
INFRACOST_FIXTURE = os.environ.get(
    "IAI_INFRACOST_FIXTURE",
    "tests/fixtures/infracost_app_tier_pass.json",
)

APPROVE_LABEL = "✅ Approve"
DECLINE_LABEL = "❌ Decline"


def process_intent_with_ollama(user_message: str) -> dict:
    """Backward-compatible alias.

    Intent parsing is now provider-agnostic (Groq / Cerebras / OpenAI-compatible
    / Ollama / passthrough) and lives in agent.llm_client.parse_intent. This
    wrapper is retained so existing imports keep working; new code should call
    parse_intent directly.
    """
    return parse_intent(user_message)


def process_intent(
    intent_text: str,
    manifest_path: str = MANIFEST_PATH,
    infracost_fixture: str | None = INFRACOST_FIXTURE,
) -> dict:
    """Process a plain-language intent and return the pipeline result.

    Sends the intent through the LLM first to extract structured requirements,
    then routes to the appropriate pipeline based on intent_type
    ("provision" | "modify" → provision; "destroy" → teardown).

    Returns:
        {
            "card": str,            # the full approval card text
            "action": str,          # "provision" or "destroy"
            "raw": dict | None,     # raw gate results (provision only)
            "approve_label": str,   # button label for Approve
            "decline_label": str,   # button label for Decline
            "intent": str,          # the original intent text, echoed back
            "parsed_intent": dict,  # structured requirements from the LLM
        }
    """
    parsed_intent = parse_intent(intent_text, manifest_path=manifest_path)
    intent_type = parsed_intent.get("intent_type", "provision")

    # The agent reasoned that the request is ambiguous — ask, don't guess.
    # Nothing is generated or applied; the user answers and re-sends.
    if parsed_intent.get("needs_clarification") or intent_type == "clarify":
        question = parsed_intent.get("question") or "Could you clarify what you'd like me to do?"
        return {
            "card": f"❓ {question}",
            "keyboard": None,
            "raw": None,
            "action": "clarify",
            "approve_label": APPROVE_LABEL,
            "decline_label": DECLINE_LABEL,
            "intent": intent_text,
            "parsed_intent": parsed_intent,
        }

    if intent_type == "destroy":
        from agent.pipeline import run_destroy_pipeline
        result = run_destroy_pipeline(manifest_path)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(APPROVE_LABEL, callback_data="approve"),
            InlineKeyboardButton(DECLINE_LABEL, callback_data="decline"),
        ]])
        return {
            "card": result["card"],
            "keyboard": keyboard,
            "raw": None,
            "action": "destroy",
            "approve_label": APPROVE_LABEL,
            "decline_label": DECLINE_LABEL,
            "intent": intent_text,
            "parsed_intent": parsed_intent,
        }

    # "provision" or "modify" — both handled by the provision pipeline.
    from agent.pipeline import run_pipeline
    result = run_pipeline(manifest_path, infracost_fixture=infracost_fixture)
    return {
        "card": result["card"],
        "keyboard": result.get("keyboard"),
        "raw": result["raw"],
        "action": "provision",
        "approve_label": APPROVE_LABEL,
        "decline_label": DECLINE_LABEL,
        "intent": intent_text,
        "parsed_intent": parsed_intent,
    }


async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram callback handler for the Approve button (callback_data="approve").

    Register with:
        application.add_handler(CallbackQueryHandler(handle_approval, pattern="^approve$"))

    Routes to apply_and_finalize() or destroy_and_reset() depending on the
    pending_action stored in context.user_data during handle_message().

    Both apply_and_finalize() and destroy_and_reset() are synchronous and can
    run for several minutes. Run via asyncio.to_thread() so they don't block
    the bot's event loop.
    """
    query = update.callback_query
    await query.answer()

    action = context.user_data.get("pending_action", "provision")
    logger.info("Approval callback received; action=%s", action)

    if action == "destroy":
        from agent.pipeline import TERRAFORM_GENERATED_DIR, destroy_and_reset
        await query.edit_message_text("🔴 Tearing down infrastructure… this takes 1–2 minutes.")
        try:
            await asyncio.to_thread(destroy_and_reset, TERRAFORM_GENERATED_DIR, MANIFEST_PATH)
            await query.edit_message_text("✅ Done — infrastructure destroyed. Manifest reset to pending.")
        except Exception as exc:
            logger.error("Destroy handler failed: %s", exc)
            await query.edit_message_text(f"❌ Destroy failed: {exc}")
    else:
        from agent.pipeline import (
            TERRAFORM_GENERATED_DIR,
            TERRAFORM_SNAPSHOT_DIR,
            apply_and_finalize,
        )
        await query.edit_message_text("⚙️ Applying infrastructure… this takes 1–2 minutes.")
        try:
            await asyncio.to_thread(
                apply_and_finalize, TERRAFORM_GENERATED_DIR, TERRAFORM_SNAPSHOT_DIR, MANIFEST_PATH
            )
            await query.edit_message_text("✅ Done — infrastructure applied. Manifest updated.")
        except Exception as exc:
            logger.error("Approval handler failed: %s", exc)
            await query.edit_message_text(f"❌ Apply failed: {exc}")
