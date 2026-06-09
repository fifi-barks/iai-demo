# Tasks — iai-demo (Track B)

*Source of truth for granular build tasks. Milestones mirror back to the IAI command center.*

> Orchestrator = El (human). Specialists = researcher · developer · tester (`.claude/agents/`).
> Core loop for anything touching the gates: Researcher spec → Developer encodes → Tester proves with fixtures.

---

## Milestone 0 — Scope & scaffold *(do before any cloud account)*
- [x] Lock the demo scenario (intent prompt, clouds in scope, resources, magic moment) — see README — 2026-06-04
- [x] Decide manifest format (annotated YAML, ruamel.yaml for round-trip) — `docs/manifest-spec.md` — 2026-06-04
- [ ] `git init`, move seed out of command center, confirm agents load in Claude Code

## Milestone 1 — Setup / infrastructure
- [ ] Cloud accounts (in-scope clouds) + projects, with budget alerts
- [ ] Server/host for the agent
- [ ] Repo structure + README finalized

## Milestone 2 — Gate accuracy spine *(highest rigor)*
- [x] Researcher: first SecOps specs → `research/findings/` (verifiable) — 2026-06-04
  - `sec-sg-open-ingress.md` — CKV_AWS_24 (primary) + AVD-AWS-0018 Trivy (secondary); CRITICAL
  - `sec-rds-encryption-and-access.md` — CKV_AWS_16 + CKV_AWS_17 (Checkov); AVD-AWS-0077/0076 (Trivy); HIGH
- [x] Researcher: first FinOps specs (+ cost reference figures) — 2026-06-04
  - `finops-rds-postgres-cost-reference.md` — db.t3.small, ~$39.71/mo ±$4.00, ap-southeast-5 (confidence: medium; upgrade via `aws pricing get-products`)
- [x] Developer: wire security gate (Checkov primary + Trivy config secondary) — `gates/security_gate.py` — 2026-06-08
- [x] Developer: wire cost gate (Infracost) — `gates/cost_gate.py`; figures match spec ($39.71 ±$4.00, range [$35.71–$43.71], ap-southeast-5) — 2026-06-04
- [x] Tester: golden fixtures written and run — `tests/fixtures/` (9 files: 6 HCL security + 3 Infracost JSON) — 2026-06-04
- [x] Gate coverage report green — all 6 criteria pass; spine CLOSED — `tests/gate-coverage-report.md` — 2026-06-04
  - Note: CKV_AWS_277 (all-traffic) does NOT fire on port-specific rules; demo catch corrected to CKV_AWS_24 (SSH port 22)

## Milestone 3 — Agent core
- [x] Lock provider regions in OpenTofu stubs — `terraform/staging/providers.tf` (AWS ap-southeast-5, GCP asia-southeast1; keyless: EC2 instance role + WIF) — 2026-06-04
- [x] Demo OpenTofu resources — `terraform/staging/main.tf` (VPC, subnet, subnet group, RDS, SG, GCP bucket) — 2026-06-04
- [x] Manifest instance — `manifest.yaml` (annotated YAML, all comments preserved, ruamel.yaml round-trip) — 2026-06-06
- [x] Manifest reader + engine resolution — `agent/manifest_reader.py` (`ManifestReader`: parse, get_engine, get_resources, resolve_criticality, update_resource_state, write) — 2026-06-06
- [x] Tester: white-box tests for manifest reader — `tests/test_manifest_reader.py` (6/6 pass: parse, engine resolution, resource access, criticality transitivity, round-trip, state update) — 2026-06-06
- [x] Multi-cloud Terraform generator — `agent/iac_generator.py` (`IaCGenerator`: greenfield enforcement, transitive criticality tags, AWS tags / GCP labels, name-dispatched renderers) — 2026-06-06
- [x] Tester: white-box tests for IaC generator — `tests/test_iac_generator.py` (4/4 pass: demo criticality, transitivity, greenfield, tag normalisation) — 2026-06-06
- [x] Plan gate — `gates/plan_gate.py` (resource count from HCL, tofu validate when available, always exits 0) — 2026-06-06
- [x] Security gate — `gates/security_gate.py` (Checkov primary CKV_AWS_24/16/17 + Trivy config secondary AVD-AWS-0018/0077/0076, structured JSON, exits 0/1/2) — 2026-06-08
- [x] Gate pipeline + approval synthesizer — `agent/pipeline.py` + `agent/approval_synthesizer.py` (all three gates → one plain-language card, no raw output, no check IDs) — 2026-06-06
- [x] Tester: black-box card vs raw findings — `tests/test_pipeline_blackbox.py` (8/8 pass: finding count, plain-English language, passed-check confirmations, cost traceability, resource count, criticality, snapshot intent, no raw output) — 2026-06-06
- [x] Conversational interface (Telegram) — `bot/intent_handler.py` + `bot/telegram_bot.py`; any plain-language message → pipeline → card + Approve/Decline buttons — 2026-06-06
- [x] Tester: intent flow black-box — `tests/test_intent_flow.py` (6/6 pass: card returned, labels correct, five sections present, intent-agnostic, gate findings correct, bot importable) — 2026-06-06
- [ ] Apply + rollback (infra snapshot; data snapshot for data-bearing) 
- [ ] Manifest auto-update after apply

## Milestone 4 — Demo video
- [ ] Tester: full black-box run green end to end
- [ ] Record: manifest setup → bot prompt → multi-cloud apply → manifest update

---

## Mirror to command center
When a milestone completes, report it so the command-center tracker updates. Also mirror finished SecOps/FinOps findings — they feed Whitepapers #2 and #3.

## Completed
- [x] Seed kit generated (CLAUDE.md, 3 agents, manifest stub, research/tests scaffolding) — 2026-06-04
