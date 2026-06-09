# iai-demo — Build Playbook (Claude Code)

This file is the working memory and orchestration contract for the IAI proof-of-concept. Read it fully at the start of every session.

## What we are building

A proof-of-concept of **Infrastructure as Intent (IAI)**: an AI agent that receives plain-language business intent, reads a manifest to decide which IaC engine owns each environment, generates the IaC (OpenTofu / Ansible), runs a three-gate validation, synthesizes one human-readable approval summary, waits for a human to push the button, applies, and then updates the manifest.

**The agent is the orchestrator. The tools are execution engines.** This is *not* a Terraform wrapper.

The deliverable is **one LinkedIn demo video**, not a product. Every technical decision serves that single end-to-end narrative. Scope ruthlessly.

## The non-negotiable: gate accuracy

The IAI thesis is that a human can trust the agent's synthesized summary enough to approve infrastructure without reading raw tool output. That trust is only earned if **the security and cost gates are accurate.** A gate that misses a known-bad config, or misstates cost, breaks the entire premise — on camera.

Therefore: gate accuracy is a **tested property**, not an aspiration. The Tester maintains golden fixtures (known-bad must flag, known-good must pass, cost estimates must reconcile against a reference). No gate ships without passing fixtures.

## Locked design decisions (from the IAI idea record — do not relitigate)

- **Tool selection is manifest-driven.** The manifest declares which IaC tool manages each environment/resource type. The agent reads it at runtime — no guessing. (Tool self-discovery is a future evolution, out of scope for the demo.)
- **Manifest is human-readable, ADR-style** — captures motivation, not just specs. Self-maintaining: manifest → agent generates IaC → applied → agent updates manifest. Format decision in `docs/manifest-spec.md`.
- **Three-gate validation before any human sees a change:** plan (what changes / what's at risk) + security scan (Checkov/Trivy config) + cost estimate (Infracost). The agent presents a **synthesized** assessment, never raw output.
- **Approval UX:** agent synthesizes all three gates into one summary; human says yes/no.
- **Criticality tagging:** greenfield-only; resources can't be provisioned without criticality tags. Criticality is **transitive** through the dependency graph (if B is referenced by critical A, B inherits critical).
- **Rollback:** infra = state snapshot before every apply; data = native provider snapshot before any apply touching data-bearing resources. Schema migrations are out of scope (human responsibility).
- **Autonomy:** human pushes the button now. Progressive autonomy is the long-term vision, not in the demo.

## Default cloud regions & accounts (locked 2026-06-04)

- **AWS:** `ap-southeast-5` — Asia Pacific (Kuala Lumpur, Malaysia)
- **GCP:** `asia-southeast1` — Singapore
- **Accounts:** El's personal AWS + GCP accounts (not enterprise). Budget alerts are a Milestone 1 task.

All IaC, cost estimates, and fixture data targets these regions unless explicitly noted otherwise. Cost reference figures in `research/findings/` must use ap-southeast-5 pricing, not us-east-1.

## Real tools (revealed in the demo, kept generic in the whitepaper)

OpenTofu (cloud + VMware vCenter), Ansible (physical networking), Telegram (intent input), Checkov/Trivy config (security gate), Infracost (cost gate). For v1 of the demo, prefer two clouds done well; the physical-Cisco leg may be omitted or simulated (switches can't be filmed).

## Agent host & credentials (locked 2026-06-08)

The IAI agent runs on a cloud VM — no laptop dependency during the demo.

- **AWS:** the agent EC2 instance carries an IAM instance role; the IAI code picks up credentials from IMDSv2 automatically. **No static AWS access keys anywhere in the codebase or environment.**
- **GCP:** the agent authenticates via Workload Identity Federation (WIF) — the EC2 instance role is federated to a GCP service account using AWS as the identity provider. **No GCP service-account key files anywhere.**
- Every tool in the chain (OpenTofu, Infracost, Trivy) inherits the instance-role credentials automatically. Nothing to rotate; nothing to leak on camera.

## Orchestration model — human as PM

You (El) are the **orchestrator/PM**. The main Claude Code session is the orchestration layer: it holds the plan, sequences work, and dispatches three specialist subagents defined in `.claude/agents/`:

- **researcher** — current best practices in IaC, FinOps, SecOps → delivers *verifiable specs* that feed the gates and the whitepapers.
- **developer** — builds the agent, IaC modules, and gates; encodes the Researcher's specs.
- **tester** — black-box + white-box; proves gate accuracy via golden fixtures; stays independent of implementation.

### Why no standalone PM agent (yet)

The main session already *is* the orchestrator. An autonomous agent whose job is to manage other agents adds an indirection layer where errors compound across agent-to-agent handoffs and plan state drifts — and for a credibility-critical demo you want a human at the orchestration layer. There's also an on-brand symmetry: IAI itself is a human pushing the button over an agent that orchestrates engines, so the build mirrors the product.

**Add a `pm` agent only when** you find yourself wanting hands-off multi-step runs and re-explaining plan state every session. It's a cheap change to make later: drop a `.claude/agents/pm.md` that owns `TASKS.md` and sequencing, and demote the main session to "review the PM's plan." Slot reserved.

### The core loop

For anything touching the gates (the high-rigor path):

1. **Researcher** produces a verifiable spec in `research/findings/` (named benchmarks, concrete rules, cited sources, expected pass/fail cases).
2. **Developer** encodes the spec into the security/cost gate.
3. **Tester** turns the spec's pass/fail cases into golden fixtures in `tests/` and proves the gate flags known-bad, passes known-good, and reconciles cost.
4. Orchestrator integrates and updates `TASKS.md`.

## Tracking protocol

- **`TASKS.md` in this repo is the source of truth for granular build tasks.**
- **Milestones mirror back to the IAI command center.** When a milestone completes, report it to the command-center session; the command-center tracker reflects status. This repo never edits command-center files directly.
- **Research findings mirror back too** — the Researcher's SecOps/FinOps specs are raw material for Whitepapers #2 and #3. Keep `research/findings/` clean and citable so it can be lifted into the papers.

## Agent definition note

Subagents live in `.claude/agents/*.md` with YAML frontmatter (`name`, `description`, `tools`, optional `model`) followed by the system prompt. Keep each agent's tools scoped to its role — least privilege. Tool scoping can't restrict by path, so role boundaries (e.g., Tester not modifying implementation) are enforced in the prompt and by review.
