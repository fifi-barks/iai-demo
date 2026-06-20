# Tasks — iai-demo

*Source of truth for granular build tasks.*

> Orchestrator = El (human). Specialists = researcher · developer · tester (`.claude/agents/`).
> Core loop for anything touching the gates: Researcher spec → Developer encodes → Tester proves with fixtures.

---

## Milestone 0 — Scope & scaffold *(do before any cloud account)*
- [x] Lock the demo scenario (intent prompt, clouds in scope, resources, magic moment) — 2026-06-04
- [x] Decide manifest format (annotated YAML, ruamel.yaml for round-trip) — `docs/manifest-spec.md` — 2026-06-04
- [x] `git init`, move seed out of command center, confirm agents load in Claude Code

## Milestone 1 — Setup / infrastructure
- [x] Cloud accounts + projects, with budget alerts
- [ ] Server/host for the agent (EC2 instance — pending AWS Console launch)
- [x] Repo structure + README finalized

## Milestone 2 — Gate accuracy spine *(highest rigor)*
- [x] Researcher: first SecOps specs → `research/findings/` — 2026-06-04
  - `sec-sg-open-ingress.md` — CKV_AWS_24 (primary) + AVD-AWS-0018 Trivy (secondary); CRITICAL
  - `sec-rds-encryption-and-access.md` — CKV_AWS_16 + CKV_AWS_17 (Checkov); AVD-AWS-0077/0076 (Trivy); HIGH
- [x] Researcher: first FinOps specs (+ cost reference figures) — 2026-06-04
  - `finops-rds-postgres-cost-reference.md` — db.t3.small, ~$39.71/mo ±$4.00, ap-southeast-5
- [x] Developer: wire security gate (Checkov primary + Trivy config secondary) — `gates/security_gate.py` — 2026-06-08
- [x] Developer: wire cost gate (Infracost) — `gates/cost_gate.py` — 2026-06-04
- [x] Tester: golden fixtures written and run — `tests/fixtures/` (9 files: 6 HCL security + 3 Infracost JSON) — 2026-06-04
- [x] Gate coverage report green — all 6 criteria pass — `tests/gate-coverage-report.md` — 2026-06-04

## Milestone 3 — Agent core
- [x] Lock provider regions in OpenTofu stubs — `terraform/staging/providers.tf` (AWS ap-southeast-5, GCP asia-southeast1; keyless: EC2 instance role + WIF) — 2026-06-04
- [x] Demo OpenTofu resources — `terraform/staging/main.tf` (VPC, subnet, subnet group, RDS, SG, GCP bucket) — 2026-06-04
- [x] Manifest instance — `manifest.yaml` — 2026-06-06
- [x] Manifest reader + engine resolution — `agent/manifest_reader.py` — 2026-06-06
- [x] Tester: white-box tests for manifest reader — `tests/test_manifest_reader.py` (6/6 pass) — 2026-06-06
- [x] Multi-cloud Terraform generator — `agent/iac_generator.py` — 2026-06-06
- [x] Tester: white-box tests for IaC generator — `tests/test_iac_generator.py` (4/4 pass) — 2026-06-06
- [x] Plan gate — `gates/plan_gate.py` — 2026-06-06
- [x] Security gate — `gates/security_gate.py` — 2026-06-08
- [x] Gate pipeline + approval synthesizer — `agent/pipeline.py` + `agent/approval_synthesizer.py` — 2026-06-06
- [x] Tester: black-box card tests — `tests/test_pipeline_blackbox.py` (8/8 pass) — 2026-06-06
- [x] Conversational interface (Telegram) — `bot/intent_handler.py` + `bot/telegram_bot.py` — 2026-06-06
- [x] Tester: intent flow black-box — `tests/test_intent_flow.py` (6/6 pass) — 2026-06-06
- [x] Apply logic — `agent/pipeline.py::apply_infrastructure` (state snapshot + tofu plan + tofu apply) — 2026-06-09
- [x] Data-aware snapshot — `agent/pipeline.py::snapshot_data_bearing_resources` (RDS snapshot before apply for data-bearing resources) — 2026-06-09
- [ ] Manifest auto-update after apply


