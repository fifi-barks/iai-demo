# Getting started

This guide takes you from a fresh `git clone` to a working Infrastructure as Intent (IAI) demo. For *what the demo does and why these tools*, see [`docs/how-it-works.md`](docs/how-it-works.md).

There are two levels of "working":

- **Reason + validate (no cloud needed).** Run the full pipeline — intent → reasoning → generate → three gates → approval card — with just a Groq key and an Infracost key. Nothing is applied. This is the quickest way to see the agent work.
- **Full apply.** Actually provision to AWS + GCP on approval. This additionally needs cloud credentials (the demo is built for a keyless VM — see [Cloud credentials](#5-cloud-credentials-for-apply-only)).

---

## 1. Install the tools

You need these on your `PATH`. Versions shown are minimums.

| Tool | Purpose | Install |
|---|---|---|
| Python ≥ 3.10 | runs the agent | your OS package manager, or python.org |
| OpenTofu ≥ 1.7 | generates & applies IaC | <https://opentofu.org/docs/intro/install/> |
| Infracost | cost gate | <https://www.infracost.io/docs/#quick-start> |
| Trivy | security gate | <https://trivy.dev/latest/getting-started/installation/> |
| Checkov | security gate | installed via `requirements.txt` (pip) |

Each tool's install page covers Linux, macOS, and Windows — follow whichever matches your machine. The demo's reference host is Ubuntu 22.04.

Quick check once installed:

```bash
python3 --version && tofu version && infracost --version && trivy --version
```

---

## 2. Get your API keys

You'll put all of these in a `.env` file in step 4. None require a paid plan.

### Groq (LLM reasoning) — required
1. Go to <https://console.groq.com> and sign up (no credit card).
2. Open **API Keys** → **Create API Key**, name it, and copy the value (starts with `gsk_`).

> Prefer a different model host? Any OpenAI-compatible provider works — set `IAI_LLM_PROVIDER` to `cerebras` or `openai` and supply that key instead, or `ollama` to run a local model. See the [env reference](#env-reference).

### Infracost (cost gate) — required for live cost
1. Go to <https://www.infracost.io> and sign up, or run `infracost auth login` (it opens a browser and provisions a key).
2. Find the key at <https://dashboard.infracost.io> → **Org Settings → API key** (starts with `ico-`).

> Don't want to set this up yet? Skip it and use the bundled estimate instead — set `IAI_INFRACOST_FIXTURE=tests/fixtures/infracost_app_tier_pass.json` in `.env`. The cost gate then returns a deterministic figure with no live call.

### Telegram bot token — only for the Telegram interface
1. In Telegram, open a chat with **@BotFather** (the verified one).
2. Send `/newbot`, give it a name, then a username ending in `bot`.
3. BotFather replies with a token like `8123456789:AA...`. That's your `TELEGRAM_BOT_TOKEN`.

The CLI needs no Telegram token, so you can skip this entirely if you only use `run_intent.py`.

---

## 3. Clone and set up Python

```bash
git clone git@github.com:fifi-barks/iai-demo.git
cd iai-demo

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # includes python-dotenv, which loads your .env
```

> `python-dotenv` matters: it's what loads `.env` into the process. If you skip `pip install`, the app falls back to the ambient environment and your keys in `.env` will look "missing."

---

## 4. Configure `.env`

`.env` is the single place your keys live. It is gitignored — never commit it.

```bash
cp .env.example .env
$EDITOR .env
```

Fill in at least:

```bash
IAI_LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here
INFRACOST_API_KEY=ico-your_key_here       # or set IAI_INFRACOST_FIXTURE instead
TELEGRAM_BOT_TOKEN=8123456789:AA...        # only if you use the Telegram bot
```

Paste keys **without surrounding quotes or trailing spaces**. `.env` is the source of truth — don't also run `infracost configure set` (see [Troubleshooting](#troubleshooting)).

---

## 5. Cloud credentials (for apply only)

You can run everything up to the approval card without this. To actually **apply**, OpenTofu needs AWS and GCP credentials.

The demo is designed to run **keyless** on a cloud VM: an AWS EC2 instance role provides AWS credentials via IMDSv2, and GCP is reached via Workload Identity Federation federated to that same role — no static keys anywhere. If you're running on such a VM, there's nothing to configure here; confirm both resolve:

```bash
aws sts get-caller-identity
gcloud auth application-default print-access-token
```

If you're running locally and just want to see the reasoning and gates, you don't need this — decline the apply, or stop at the card.

---

## 6. Run it

### CLI (quickest)

```bash
python run_intent.py "Set up the payments staging environment."
```

You'll see a startup line confirming the active model, e.g. `LLM: provider=groq model=llama-3.3-70b-versatile key=set`, then the approval card and an `Approve? [y/N]` prompt. The agent fills in the multi-cloud detail from the manifest — you don't have to spell it out. Try an ambiguous request like `"delete"` and it will ask a clarifying question and remember your answer.

### Telegram bot

```bash
python -m bot.telegram_bot
```

The startup log prints the active model. Open your bot in Telegram, send `/start`, then describe what you need and tap **Approve** / **Decline** on the card. To keep it running after you log out, launch it inside `tmux`.

### Tear down

Re-run with a destroy intent (e.g. *"tear down the payments staging environment"*) and approve — the card shows the monthly savings — or directly:

```bash
tofu -chdir=terraform/generated destroy
```

---

## 7. Run the tests

The suite is **hermetic** — it uses golden fixtures and the offline passthrough, so it needs only the Python dependencies. No cloud tools, no API keys, no network:

```bash
source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests/
```

You should see **35 passed**. They cover the manifest reader (parsing, criticality, comment-preserving round-trip), the IaC generator (tagging, criticality transitivity, greenfield enforcement), the gates' output handling and golden security fixtures (known-bad must flag, known-good must pass), and the full black-box flow (intent → card, cost figure traces back to the gate, no raw tool output leaks into the summary). To exercise the gates against the *live* tools instead of fixtures, install OpenTofu, Checkov, Trivy, and Infracost (step 1) and run the pipeline via the CLI.

---

## Troubleshooting

**Card says "cost estimate unavailable."** The live Infracost call failed. The real error is printed in the log as `{"status": "error", ... "stderr": "..."}`. Usually a missing/invalid `INFRACOST_API_KEY`. Verify with `infracost breakdown --path terraform/generated --format json | head`. Or set `IAI_INFRACOST_FIXTURE=tests/fixtures/infracost_app_tier_pass.json` to use the bundled estimate.

**Infracost says "Invalid API Key" even after you set a new one.** The `INFRACOST_API_KEY` environment variable **overrides** `infracost configure set`. If you have a stale value exported in your shell, it shadows everything — including the good key. Fix: `echo "$INFRACOST_API_KEY"` to see what's loaded; `unset INFRACOST_API_KEY` to drop a stale one; and make sure the *correct* key is in `.env` (which is what the app uses). Pick one source of truth — for this project, that's `.env`.

**It's slow / the log shows "Intent parse via ollama failed (read timeout)."** The process doesn't have your LLM key, so it fell back to a local model. Check the startup line — if it says `provider=ollama` or `key=MISSING`, your `.env` isn't being read. Confirm `python-dotenv` is installed (`pip show python-dotenv`), that `.env` is at the repo root, and that no stale `IAI_LLM_PROVIDER`/`GROQ_API_KEY` is exported in the shell shadowing it.

**Keys in `.env` look "missing."** Almost always `python-dotenv` isn't installed (`pip install -r requirements.txt`), or `.env` isn't at the repo root, or a stale shell export is shadowing it (real environment variables take precedence over `.env`).

**`tofu`/`infracost`/`checkov`/`trivy`: command not found** when run as a service. systemd gives a minimal `PATH`. Add the directories from `which tofu infracost checkov trivy` to an `Environment=PATH=...` line in the unit.

---

## Env reference

| Variable | Required | Default | Notes |
|---|---|---|---|
| `IAI_LLM_PROVIDER` | recommended | auto | `groq` \| `cerebras` \| `openai` \| `ollama` \| `none` |
| `GROQ_API_KEY` | for Groq | — | free at console.groq.com |
| `CEREBRAS_API_KEY` / `OPENAI_API_KEY` | per provider | — | only the selected provider's key is needed |
| `IAI_LLM_MODEL` | no | per-provider | e.g. `llama-3.3-70b-versatile` |
| `INFRACOST_API_KEY` | for live cost | — | free at infracost.io |
| `IAI_INFRACOST_FIXTURE` | no | unset (live) | path to a saved Infracost JSON to run the cost gate offline |
| `TELEGRAM_BOT_TOKEN` | for the bot | — | from @BotFather |
| `IAI_MANIFEST` | no | `manifest.yaml` | manifest path |

Cloud credentials are **never** environment variables here — AWS uses the instance role, GCP uses Workload Identity Federation.
