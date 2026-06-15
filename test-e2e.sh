#!/bin/bash
cd ~/iai-demo
source venv/bin/activate

echo "=== Restarting bot with debug logging ==="
pkill -f telegram_bot
sleep 1

export TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
export OLLAMA_URL="http://localhost:11434/api/generate"
export OLLAMA_MODEL="phi"
export IAI_MANIFEST="manifest.yaml"

echo "Starting bot..."
python3 -m bot.telegram_bot 2>&1 | tee bot-debug.log &
BOT_PID=$!

echo "Bot PID: $BOT_PID"
echo ""
echo "Bot is running. Send intent via Telegram, then click Approve."
echo "Watch this log for [MSG], [CARD], and [APPROVE] entries."
echo ""
echo "Ctrl+C to stop."

wait $BOT_PID
