# iai-demo — Build Playbook (Claude Code)

This file is the working memory and orchestration contract for the IAI proof-of-concept. Read it fully at the start of every session.

## What we are building

A proof-of-concept of **Infrastructure as Intent (IAI)**: an AI agent that receives plain-language business intent, reads a manifest to decide which IaC engine owns each environment, generates the IaC (OpenTofu), runs a three-gate validation, synthesizes one human-readable approval summary, waits for a human to push the button, applies, and then updates the manifest.

**The agent is the orchestrator. The tools are execution engines.** This is *not* a Terraform wrapper.

The deliverable is **one LinkedIn demo video**, not a product. Every technical decision serves that single end-to-end narrative. Scope ruthlessly.

## The non-negotiable: gate accuracy

The IAI thesis is that a human can trust the agent's synthesized summary enough to approve infrastructure without reading raw tool output. That trust is only earned if **the security and cost gates are accurate.** A gate that misses a known-bad config, or misstates cost, breaks the entire premise — on camera.

Gate accuracy is a **tested property**, not an aspiration. The Tester maintains golden fixtures (known-bad must flag, known-good must pass, cost estimates must reconcile against a reference). No gate ships without passing fixtures.

## Locked design decisions (do not relitigate)

- **Tool selection is manifest-driven.** The manifest declares which IaC tool manages each environment/resource type. The agent reads it at runtime — no guessing.
- **Manifest is human-readable, ADR-style** — captures motivation, not just specs. Self-maintaining: manifest → agent generates IaC → applied → agent updates manifest. Format: `docs/manifest-spec.md`.
- **Three-gate validation before any human sees a change:** plan (what changes / what's at risk) + security scan (Checkov/Trivy config) + cost estimate (Infracost). The agent presents a **synthesized** assessment, never raw output.
- **Approval UX:** agent synthesizes all three gates into one summary; human says yes/no.
- **Criticality tagging:** greenfield-only; resources can't be provisioned without criticality tags. Criticality is **transitive** through the dependency graph (if B is referenced by critical A, B inherits critical).
- **Rollback:** infra = state snapshot before every apply; data = native provider snapshot before any apply touching data-bearing resources. Schema migrations are out of scope (human responsibility).
- **Autonomy:** human pushes the button now. Progressive autonomy is the long-term vision, not in the demo.

## Default cloud regions & accounts (locked 2026-06-04)

- **AWS:** `ap-southeast-5` — Asia Pacific (Kuala Lumpur, Malaysia)
- **GCP:** `asia-southeast1` — Singapore

All IaC, cost estimates, and fixture data targets these regions unless explicitly noted otherwise. Cost reference figures in `research/findings/` must use ap-southeast-5 pricing, not us-east-1.

## Real tools

OpenTofu (cloud), Ansible (physical networking — out of scope v1), Telegram (intent input), Checkov/Trivy config (security gate), Infracost (cost gate). For v1 of the demo, two clouds done well; the physical-Cisco leg is omitted.

## Agent host & credentials (locked 2026-06-08)

The IAI agent runs on a cloud VM — no laptop dependency during the demo.

- **AWS:** the agent EC2 instance carries an IAM instance role; the IAI code picks up credentials from IMDSv2 automatically. **No static AWS access keys anywhere in the codebase or environment.**
- **GCP:** the agent authenticates via Workload Identity Federation (WIF) — the EC2 instance role is federated to a GCP service account using AWS as the identity provider. **No GCP service-account key files anywhere.**
- Every tool in the chain (OpenTofu, Infracost, Trivy) inherits the instance-role credentials automatically.

## Orchestration model

El is the **orchestrator/PM**. The main Claude Code session holds the plan, sequences work, and dispatches three specialist subagents defined in `.claude/agents/`:

- **researcher** — current best practices in IaC, FinOps, SecOps → delivers *verifiable specs* that feed the gates.
- **developer** — builds the agent, IaC modules, and gates; encodes the Researcher's specs.
- **tester** — black-box + white-box; proves gate accuracy via golden fixtures; stays independent of implementation.

### The core loop (for anything touching the gates)

1. **Researcher** produces a verifiable spec in `research/findings/` (named benchmarks, concrete rules, cited sources, expected pass/fail cases).
2. **Developer** encodes the spec into the security/cost gate.
3. **Tester** turns the spec's pass/fail cases into golden fixtures in `tests/` and proves the gate flags known-bad, passes known-good, and reconciles cost.

## Task tracking

`.claude/TASKS.md` is the source of truth for granular build tasks.

## Agent definition note

Subagents live in `.claude/agents/*.md` with YAML frontmatter (`name`, `description`, `tools`, optional `model`) followed by the system prompt. Keep each agent's tools scoped to its role — least privilege. Tool scoping can't restrict by path, so role boundaries are enforced in the prompt and by review.
