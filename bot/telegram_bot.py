"""Telegram bot for IAI — Infrastructure as Intent.

Start with:
    TELEGRAM_BOT_TOKEN=<token> .venv/bin/python -m bot.telegram_bot

The bot accepts any plain-language message as an intent. It reads the
manifest, generates IaC, runs all three gates (security, cost, plan),
and replies with a synthesized approval card + Approve/Decline buttons.
"""

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent.llm_client import active_config
from bot.intent_handler import handle_approval, process_intent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WELCOME = (
    "IAI — Infrastructure as Intent\n\n"
    "Describe what you need in plain language. I'll read the manifest, "
    "generate the infrastructure, run security and cost checks, and come "
    "back with a summary for you to approve or decline.\n\n"
    "Try: \"Stand up a staging environment for the payments service: an EC2 "
    "app tier in AWS and an export bucket in GCP. Tag it staging, owner "
    "payments-team.\""
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    intent = update.message.text
    logger.info("Intent received: %s...", intent[:60])
    # Acknowledge immediately so the user knows we're working
    ack = await update.message.reply_text("Reading the manifest and running the gates…")

    # process_intent does blocking work (LLM call, OpenTofu plan, Checkov, Infracost).
    # Run it OFF the event loop so the bot stays responsive and a slow gate can't
    # freeze every other update. Any failure becomes a clean message, not a stuck ack.
    try:
        result = await asyncio.to_thread(process_intent, intent)
    except Exception:
        logger.exception("Intent processing failed")
        await ack.edit_text(
            "⚠️ Something went wrong while processing that request. "
            "Check the agent logs (most often a missing INFRACOST_API_KEY or "
            "LLM key in .env)."
        )
        return

    action = result.get("action", "provision")
    context.user_data["pending_action"] = action

    # The agent decided the request is ambiguous — ask and stop. No buttons,
    # nothing generated. The user replies with a clearer message to proceed.
    if action == "clarify":
        await ack.edit_text(result["card"])
        return

    # Edit the ack message to show the card (keeps chat tidy; the ack becomes the card)
    await ack.edit_text(
        f"```\n{result['card']}\n```",
        reply_markup=result["keyboard"],
        parse_mode="MarkdownV2",
    )


async def handle_decline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Cancelled.")
    await query.edit_message_text("🚫 Declined — no changes applied.")


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_approval, pattern="^approve$"))
    app.add_handler(CallbackQueryHandler(handle_decline, pattern="^decline$"))
    logger.info("IAI bot polling… LLM %s", active_config())
    app.run_polling()


if __name__ == "__main__":
    main()
