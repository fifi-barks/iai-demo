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
from bot.intent_handler import (
    MAX_CLARIFY_ROUNDS,
    clarify_question,
    compose_dialogue,
    handle_approval,
    process_intent,
)

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
    msg = update.message.text
    logger.info("Message received: %s...", msg[:60])

    # If we're mid-clarification, this message is an ANSWER — fold it into the
    # running dialogue and re-resolve the whole conversation, not just this line.
    history = context.user_data.get("clarify_history")
    if history:
        history.append(f"User: {msg}")
        intent_for_agent = compose_dialogue(history)
    else:
        history = [f"User: {msg}"]
        intent_for_agent = msg

    ack = await update.message.reply_text("Reading the manifest and running the gates…")

    # process_intent does blocking work (LLM call, OpenTofu plan, Checkov, Infracost).
    # Run it OFF the event loop so the bot stays responsive and a slow gate can't
    # freeze every other update. Any failure becomes a clean message, not a stuck ack.
    try:
        result = await asyncio.to_thread(process_intent, intent_for_agent)
    except Exception:
        logger.exception("Intent processing failed")
        context.user_data.pop("clarify_history", None)
        context.user_data.pop("clarify_rounds", None)
        await ack.edit_text(
            "⚠️ Something went wrong while processing that request. "
            "Check the agent logs (most often a missing INFRACOST_API_KEY or "
            "LLM key in .env)."
        )
        return

    action = result.get("action", "provision")

    # Still ambiguous — ask a follow-up, remembering the dialogue so the next
    # answer composes with it. Cap the rounds so it can never loop forever.
    if action == "clarify":
        rounds = context.user_data.get("clarify_rounds", 0) + 1
        if rounds >= MAX_CLARIFY_ROUNDS:
            context.user_data.pop("clarify_history", None)
            context.user_data.pop("clarify_rounds", None)
            await ack.edit_text(
                "I'm still not sure what you need. Let's restart — describe it in "
                "one sentence, e.g. \"tear down the payments staging environment.\""
            )
            return
        history.append(f"Agent: {clarify_question(result)}")
        context.user_data["clarify_history"] = history
        context.user_data["clarify_rounds"] = rounds
        await ack.edit_text(result["card"])
        return

    # Resolved — clear the dialogue state and proceed to the approval card.
    context.user_data.pop("clarify_history", None)
    context.user_data.pop("clarify_rounds", None)
    context.user_data["pending_action"] = action

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
