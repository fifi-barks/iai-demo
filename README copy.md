# iai-demo

Proof-of-concept for **Infrastructure as Intent (IAI)** — an AI agent that takes plain-language business intent and orchestrates the right IaC engines (OpenTofu for cloud, Ansible declared-out-of-scope for v1) to deliver it, under a human approval gate.

> This repo is **Track B** of the IAI effort. The concept, whitepapers, and GTM live in the separate **IAI command center**. This repo never holds thought-leadership work; the command center never points here. The two stay linked only through milestone status and mirrored research findings.

## What this demo proves

One end-to-end story, told on camera:

> Business intent (plain English) → agent reads the manifest → generates multi-cloud OpenTofu → three-gate validation (plan + security + cost) → one human-readable summary → human pushes the button → apply → manifest auto-updates.

The credibility of the whole thing rests on **one thing being true: the security and cost summary the human approves must be accurate.** If a gate lies, the "trust the agent" thesis dies on camera. Treat gate accuracy as the highest-rigor part of the build.

## The demo scenario (locked 2026-06-04)

Full narrative in `docs/demo-scenario.md`. Summary:

- **Intent prompt:** "Stand up a staging environment for the payments service: a managed Postgres, an app compute tier, and a private network in AWS, plus an object-storage bucket in GCP for export files. Tag it staging, owner payments-team."
- **Clouds in scope:** AWS (VPC + RDS Postgres + app tier + IAM/security-group glue) and GCP (object-storage bucket for export files). The pair is deliberate: GCP uses _labels_ where AWS uses _tags_, so the agent normalising both metadata models is visible on camera. Physical-hardware leg declared in the manifest as out-of-scope for v1. **App tier:** immutable pre-baked image (Packer/Docker, built upstream by CI, out of scope); OpenTofu provisions from it.
- **Resources provisioned:** AWS VPC + private subnet · AWS RDS Postgres (data-bearing, critical) · AWS EC2 instance (app tier, runs pre-baked image, inherits critical via dependency on Postgres) · GCP object-storage bucket · supporting IAM + security groups + SG rules (~7–8 resources total).
- **What each gate should catch:** security: *config* — the generated app-tier security group allows inbound from `0.0.0.0/0` — gate flags it (CKV_AWS_24); summary states "the app tier would have been reachable from the entire internet — ingress restricted to the VPC." Postgres not publicly accessible (passes CKV_AWS_17), encryption-at-rest on (passes CKV_AWS_16). *Image* — Trivy scans the pre-baked app image (supply-chain); demo image passes clean. cost: Infracost monthly estimate with Postgres as dominant line item; summary gives one number and names the driver. plan: 7 resources to add, 0 to change, 0 to destroy; critical resources flagged.
- **The "magic moment" on camera:** One Telegram sentence in → synthesized approval card back ("7 resources across AWS + GCP · ~$X/mo · 1 issue caught and fixed — app tier restricted to VPC · payments-db + app-tier tagged critical, I'll snapshot before applying · **[ Approve ] [ Decline ]**") → human taps Approve → multi-cloud apply → manifest rewrites itself with the new state.

## How this repo is built — the agent team

A human orchestrator (you) drives three specialist subagents (see `.claude/agents/`):

| Agent | Role | Key contract |
|-------|------|--------------|
| **Researcher** | Finds current best practices across IaC, FinOps, SecOps | Delivers **verifiable specs** (named benchmarks, concrete rules, sources) — not essays. Output feeds the gates *and* Whitepapers #2/#3. |
| **Developer** | Builds the agent, IaC modules, and the three gates | Encodes the Researcher's specs into real policy/cost checks. |
| **Tester** | Black-box + white-box; **proves the gates are accurate** | Owns golden fixtures: known-bad must flag, known-good must pass, costs must reconcile. Stays independent of implementation. |

You are the orchestrator/PM. A standalone PM agent is intentionally *not* included yet — see `CLAUDE.md` for when to add one.

## Getting started in Claude Code

1. Move this folder out of the command center to wherever you keep repos, and `git init`.
2. Lock the demo scenario above.
3. Open in Claude Code. The main session is your orchestrator; it dispatches the three subagents.
4. Start the loop: **Researcher** drafts gate specs → **Developer** implements → **Tester** writes fixtures and proves accuracy.
5. Report milestone completions back to the command center so the tracker stays current.

## Layout

```
.claude/agents/    developer.md · tester.md · researcher.md
docs/              manifest-spec.md (manifest format)
research/          findings/ — verifiable specs; mirrored back to feed WP#2/#3
tests/             golden fixtures for gate-accuracy proofs
CLAUDE.md          orchestration playbook + locked design decisions
TASKS.md           granular build tasks; milestones mirror to the command center
```
