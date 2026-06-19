# Infrastructure as Intent — Demo (v1)

**One plain-language sentence in → governed, multi-cloud infrastructure out, with a single human decision in the middle and zero static cloud credentials.**

A working proof of concept for **Infrastructure as Intent (IAI)**: an AI agent that interprets a business outcome stated in plain language, reasons about it against a living manifest, generates the infrastructure as code, validates it through three gates, synthesizes one human-readable approval card, and applies it on approval — driven from a Telegram message or the CLI.

It is **not a Terraform wrapper.** It is an *intent layer* that sits above the execution engines: it decides which engine owns what, reasons about the request, and checks the result before anything touches real infrastructure. The concept is laid out in the companion whitepaper, *Infrastructure as Intent: Concept and Architecture*.

---

## The demo in one sentence

Send this to the bot (or pass it to `run_intent.py`):

> *"Stand up a staging environment for the payments service: an EC2 app tier in AWS and an export bucket in GCP. Tag it staging, owner payments-team."*

About a second later the agent returns one card (real synthesized output):

```
Staging environment for payments — ready to build
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Resources:  3 across AWS + GCP (3 to add · 0 to change · 0 to destroy)
• Cost:       ~$10/month
• Security:   1 issue caught — the app tier would have been reachable via SSH
              from the entire internet (port 22 open to 0.0.0.0/0). Ingress
              restricted to the VPC CIDR.  IMDSv2 enforced: ✓  Uniform bucket access: ✓
• Critical:   app-tier [directly critical]
• Rollback:   Infra state snapshot saved before apply.
              [ Approve ]   [ Decline ]
```

Tap **Approve** → it provisions across both clouds (keyless) → the manifest rewrites itself with the new resource IDs. Under two minutes, end to end.

## The agent reasons — and asks when it isn't sure

The intent layer doesn't pattern-match keywords. It interprets the request **against the manifest** (the source of truth for what exists and which engine owns it) and decides an action: provision, modify, destroy — or **clarify**. If a request is ambiguous or under-specified, the agent asks one short question instead of guessing, and nothing is generated until you answer:

```
$ python run_intent.py "set something up for payments"
❓ Did you mean the existing 'staging' environment, or a new one?
(what I understood so far: the user wants infrastructure for payments but didn't specify the environment)
```

A fully specified request is acted on directly; only genuinely unclear ones are sent to clarify. This is the IAI thesis in miniature — the agent reasons about intent and earns trust by asking at the edges rather than guessing.

---

## Architecture

![IAI demo architecture](docs/architecture.png)

1. **Intent** — a plain-language request arrives via Telegram or the CLI.
2. **Parse + reason** — an LLM interprets the request against the manifest and decides the action (or asks to clarify). Runs on a fast hosted model (**Groq**, sub-second) by default, with Ollama and a keyword passthrough as fallbacks, so it still runs offline.
3. **Read the manifest** — resolve which engine owns each resource and the org's standards.
4. **Generate** — write **OpenTofu** for the requested resources (EC2 instance + security group on AWS, a GCS bucket on GCP).
5. **Three gates** — **plan** (what changes), **security** (Checkov + Trivy config), **cost** (Infracost). The security gate catches the app-tier SG open to `0.0.0.0/0` and restricts it, while genuine good practice passes (IMDSv2, uniform bucket access).
6. **One card** — all three gates folded into a single plain-language summary.
7. **Human approves** — nothing is applied before the tap.
8. **Apply, keyless** — snapshot first, then OpenTofu applies. AWS via the EC2 instance role; GCP via Workload Identity Federation. No static cloud credentials anywhere.
9. **Self-updating manifest** — after a clean apply the agent rewrites the manifest with the new reality and the reasoning behind it.

---

## What's in scope (and what isn't)

**In scope (v1):** multi-cloud provisioning of **AWS EC2 + security group** (`ap-southeast-5`) and a **GCP Cloud Storage bucket** (`asia-southeast1`); manifest-grounded reasoning with a clarify path; three-gate validation with a genuine security catch; the synthesized approval UX; keyless apply; the self-updating manifest; cross-cloud normalization (AWS tags vs GCP labels).

**Out of scope (declared in the manifest, not built):** the Ansible / physical-hardware engine; image baking / CI (the demo consumes a pre-baked AMI); a full multi-turn clarification conversation (v1 asks once and stops — you re-send a clearer request).

---

## Quickstart

```bash
# 1. Clone
git clone git@github.com:fifi-barks/iai-demo.git && cd iai-demo

# 2. Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure — copy the template and fill in your keys
cp .env.example .env
$EDITOR .env                 # set GROQ_API_KEY (free, no card: console.groq.com/keys)
set -a && source .env && set +a

# 4. Run via CLI (no messaging infrastructure required)
python run_intent.py "Stand up a staging environment for the payments service: an EC2 app tier in AWS and an export bucket in GCP."
#   → prints the approval card, prompts Approve? [y/N], then applies + updates the manifest

# 5. Run via Telegram instead (needs TELEGRAM_BOT_TOKEN)
python -m bot.telegram_bot

# Tear down
tofu -chdir=terraform/generated destroy   # or re-run with a destroy intent
```

**Prerequisites:** OpenTofu ≥ 1.7, Checkov, Trivy, Infracost (with API key), Python ≥ 3.10 on PATH. A **Groq API key** (free, no card) for fast reasoning — or set `IAI_LLM_PROVIDER=ollama` for a local model, or `none` to run on the keyword passthrough. AWS + GCP are **keyless**: an EC2 instance role and GCP Workload Identity Federation provide credentials at runtime — there are no static cloud keys in this project. The cost gate runs **Infracost live by default** (it prices the resources actually generated, so it needs a valid `INFRACOST_API_KEY`). To run offline — tests, CI, or a recorded demo where you want a deterministic figure and no network call — set `IAI_INFRACOST_FIXTURE=tests/fixtures/infracost_app_tier_pass.json`.

---

## Repository layout

```
agent/   llm_client (intent reasoning), pipeline (gates + apply), iac_generator,
         manifest_reader, approval_synthesizer
gates/   plan / security (Checkov + Trivy) / cost (Infracost)
bot/     telegram_bot, intent_handler
run_intent.py      CLI entry point
manifest.yaml      platform manifest — human-authored, agent-maintained state
docs/              how-it-works, architecture + stack diagrams, manifest spec
tests/             golden fixtures: known-bad must flag, known-good must pass
```

---

## Documentation

- **[GETTING_STARTED.md](GETTING_STARTED.md)** — prerequisites, how to get each API key, and a full clone-to-running walkthrough with troubleshooting.
- **[docs/how-it-works.md](docs/how-it-works.md)** — the end-to-end flow, the tool stack, and why each technology was chosen.

---

## Security posture

The agent runs **keyless** to the clouds — AWS via the EC2 instance role (IMDSv2), GCP via Workload Identity Federation. The only secret is the **LLM API key**, which is a SaaS inference key (not a cloud credential) and lives strictly in the environment via `.env` — never in source. `.env` is gitignored. The security gate runs on every generation, and nothing applies without explicit human approval.

---

## Roadmap

Richer estate (managed databases with data-aware rollback and transitive criticality), the Ansible / physical-hardware engine, a full multi-turn clarification conversation, and tool self-discovery (selecting an engine without manifest guidance). The whitepaper series goes deeper — II on SecOps, III on FinOps.

---

*"Infrastructure as Intent" is a concept coined in this work. © Elaia Raj.*
