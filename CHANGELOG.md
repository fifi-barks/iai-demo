# Changelog — iai-demo

All notable changes to this project are documented here.

## [1.0.0] — 2026-06-20

First public release.

### Added
- **Intent layer** — an AI agent that turns plain-language intent into validated, multi-cloud infrastructure under a single human approval. Not a Terraform wrapper.
- **Manifest-grounded reasoning** — Groq (Llama 3.3 70B) by default, with a local Ollama (Phi 3.8B) fallback and a keyword passthrough, so it stays fast, self-hostable, and never hard-fails. Asks a clarifying question when a request is ambiguous, and remembers the dialogue across turns.
- **Manifest-driven generation** to OpenTofu; the annotated-YAML manifest is a self-updating source of truth (comments preserved via `ruamel.yaml`).
- **Three-gate validation** before any human sees a change — plan, security (Checkov + Trivy), live cost (Infracost) — synthesized into one approval card.
- **State-aware teardown** — reads OpenTofu state to report exactly what will be destroyed (with monthly savings), and refuses to "destroy" when nothing is provisioned.
- **Keyless execution** — AWS via EC2 instance role (IMDSv2), GCP via Workload Identity Federation. No static cloud keys anywhere.
- **Two front-ends** over the same pipeline: a Telegram bot and a CLI (`run_intent.py`).
- Demo scenario: payments staging — AWS EC2 instance + security group, GCP Cloud Storage bucket.

### Scope (v1.0.0)
- Two clouds (AWS + GCP). The Ansible / physical-hardware engine is declared in the manifest but out of scope.
- Clarification resolves over a few turns within a session rather than holding long-term memory.

## [Unreleased]

Future: resource-scoped destroy, provision-side state awareness, a richer estate (managed databases with data-aware rollback), and tool self-discovery.
