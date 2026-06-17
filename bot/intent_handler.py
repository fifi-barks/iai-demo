"""Intent handler — Telegram-free core of the IAI bot.

Receives a plain-language intent string, sends it to a local phi 7B model
via Ollama to extract structured infrastructure requirements, then runs the full
pipeline: manifest read → IaC generate → three gates → synthesized approval card.

Kept separate from telegram_bot.py so it can be imported and tested without a
live Telegram connection or bot token.
"""

import asyncio
import json
import logging
import os

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MANIFEST_PATH = os.environ.get("IAI_MANIFEST", "manifest.yaml")
INFRACOST_FIXTURE = os.environ.get(
    "IAI_INFRACOST_FIXTURE",
    "tests/fixtures/infracost_app_tier_pass.json",
)

APPROVE_LABEL = "✅ Approve"
DECLINE_LABEL = "❌ Decline"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi")

_INTENT_SYSTEM_PROMPT = """\
You are an infrastructure assistant. Parse the user's request and extract the \
infrastructure requirements as JSON.

Return ONLY valid JSON — no explanation, no markdown — with exactly this structure:
{{
  "intent_type": "provision",
  "resources": ["vpc", "rds_postgres", "ec2", "gcs_bucket"],
  "clouds": ["aws", "gcp"],
  "requirements": {{
    "environment": "staging",
    "criticality": "critical",
    "data_bearing": true,
    "tags": {{"owner": "payments-team", "environment": "staging"}}
  }}
}}

Rules:
- intent_type: "provision" | "modify" | "destroy"
- resources: include all inferred resources (vpc, subnet, rds_postgres, ec2, \
gcs_bucket, security_group, iam_role, etc.)
- clouds: ["aws"] or ["gcp"] or ["aws", "gcp"]
- criticality: infer from context ("critical" for payment/finance/data workloads, \
"high" for production, "medium" for staging, "low" for dev/test)
- data_bearing: true if the request involves a database or persistent data store
- tags: extract owner/environment/team from the request if mentioned

User request: {user_message}"""


def process_intent_with_ollama(user_message: str) -> dict:
    """Send a plain-language intent to Ollama/phi and extract structured requirements.

    Args:
        user_message: The raw intent text from the user.

    Returns:
        {
            "intent_type": "provision" | "modify" | "destroy",
            "resources": ["vpc", "rds_postgres", ...],
            "clouds": ["aws", "gcp"],
            "requirements": {
                "environment": str,
                "criticality": str,
                "data_bearing": bool,
                "tags": dict,
            },
        }

    Falls back to a passthrough dict if Ollama is unreachable or returns
    unparseable output — so the pipeline can still run in offline/test mode.
    """
    prompt = _INTENT_SYSTEM_PROMPT.format(user_message=user_message)
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=120,
        )
        resp.raise_for_status()
        raw_response = resp.json().get("response", "")
        parsed = json.loads(raw_response)
        logger.info("Ollama parsed intent: %s", parsed)
        return parsed
    except requests.exceptions.ConnectionError:
        logger.warning("Ollama not reachable at %s — using passthrough intent", OLLAMA_URL)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Ollama response unparseable (%s) — using passthrough intent", exc)
    except requests.exceptions.RequestException as exc:
        logger.warning("Ollama request failed (%s) — using passthrough intent", exc)

    # Fallback: infer intent_type from keywords in the raw message so that
    # "tear down" / "destroy" still routes correctly even when Ollama fails.
    _DESTROY_KEYWORDS = {"tear down", "teardown", "destroy", "decommission", "delete", "remove", "clean up", "cleanup"}
    lower = user_message.lower()
    fallback_type = "destroy" if any(kw in lower for kw in _DESTROY_KEYWORDS) else "provision"
    return {
        "intent_type": fallback_type,
        "resources": [],
        "clouds": [],
        "requirements": {"environment": "staging", "criticality": "high", "data_bearing": False, "tags": {}},
    }


def process_intent(
    intent_text: str,
    manifest_path: str = MANIFEST_PATH,
    infracost_fixture: str | None = INFRACOST_FIXTURE,
) -> dict:
    """Process a plain-language intent and return the pipeline result.

    Sends the intent through Ollama/phi first to extract structured
    requirements, then routes to the appropriate pipeline based on
    intent_type ("provision" | "modify" → provision; "destroy" → teardown).

    Returns:
        {
            "card": str,            # the full approval card text
            "action": str,          # "provision" or "destroy"
            "raw": dict | None,     # raw gate results (provision only)
            "approve_label": str,   # button label for Approve
            "decline_label": str,   # button label for Decline
            "intent": str,          # the original intent text, echoed back
            "parsed_intent": dict,  # structured requirements from phi
        }
    """
    parsed_intent = process_intent_with_ollama(intent_text)
    intent_type = parsed_intent.get("intent_type", "provision")

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
