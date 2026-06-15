# iai-demo — v1 (AWS-only)

A proof-of-concept of **Infrastructure as Intent (IAI)** — an AI agent that takes a plain-language business request, generates infrastructure-as-code, validates it through three automated gates, and asks a human to approve a plain-English summary before applying anything.

**v1 focuses on AWS** for a clean, polished demo. Multi-cloud support (GCP, Ansible) deferred to v2.

## What it does

One sentence in via Telegram → the agent:

1. Reads `manifest.yaml` to know which IaC engine owns each environment
2. Generates OpenTofu (HCL) for the requested resources
3. Runs three gates in sequence:
   - **Plan** — what changes, what's at risk, resource count
   - **Security** — Checkov + Trivy config scan; flags misconfigurations
   - **Cost** — Infracost monthly estimate with per-resource breakdown
4. Synthesizes all three into one human-readable approval card (no raw tool output)
5. Waits for **[ Approve ] / [ Decline ]**
6. On approval: takes a state snapshot, takes a native RDS snapshot for data-bearing resources, runs `tofu apply`, updates the manifest

## The demo scenario (v1: AWS-only)

**Intent prompt:**
> "Set up a staging environment for the payments service: a managed Postgres database, an app tier, and a private VPC. Tag it staging, owner payments-team."

**Resources provisioned:** AWS VPC · 2 private subnets (multi-AZ) · RDS Postgres (data-bearing, critical) · EC2 app tier (inherits critical via dependency) · security groups (~6 resources total)

**What the gates catch:**
- **Security:** App-tier security group allows SSH inbound from `0.0.0.0/0` — flagged (CKV_AWS_24); approval summary states ingress restricted to VPC CIDR. RDS encryption-at-rest and private access both pass.
- **Cost:** Infracost estimate with RDS as the dominant monthly cost driver.
- **Plan:** 6 resources to add, 0 to change, 0 to destroy; critical resources highlighted.

**The approval card the human sees:**
```
Staging environment for payments — ready to build
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Resources: 6 across AWS (6 to add · 0 to change · 0 to destroy)
• Cost: ~$45/month (db.t3.small)
• Security: 1 issue caught — app tier would have been open to 0.0.0.0/0 on SSH.
            Ingress restricted to the VPC CIDR.
• Critical: payments-db [data-bearing — snapshot before apply]
            app-tier [depends on payments-db]
```

**On approve:** State snapshot → RDS snapshot → `tofu apply` → manifest auto-updates.

## Cloud & region

| Cloud | Region | Auth |
|-------|--------|------|
| AWS | `ap-southeast-5` (Kuala Lumpur, Malaysia) | EC2 instance role via IMDSv2 |

**v1 is AWS-only.** Multi-cloud support (GCP, physical hardware) planned for v2.

No static credentials anywhere in the codebase; all auth via instance metadata service.

## Repo layout

```
agent/
  pipeline.py           end-to-end gate runner + apply_infrastructure + snapshot_data_bearing_resources
  iac_generator.py      manifest → OpenTofu HCL
  manifest_reader.py    YAML reader with transitive criticality resolution
  approval_synthesizer.py  three gate results → one approval card

gates/
  security_gate.py      Checkov (primary) + Trivy config (secondary)
  cost_gate.py          Infracost wrapper + budget threshold check
  plan_gate.py          resource count + tofu validate

bot/
  telegram_bot.py       Telegram interface + Approve/Decline buttons
  intent_handler.py     routes intent → pipeline → card

terraform/staging/      reference OpenTofu module (VPC, RDS, EC2, GCP bucket)
manifest.yaml           platform manifest — human-authored, agent-maintained state blocks
docs/                   manifest spec, demo scenario detail
research/findings/      verifiable SecOps + FinOps specs that back the gates
tests/                  golden fixtures (known-bad must flag, known-good must pass)
scripts/                infra setup scripts (EC2 launch)
```

## Running locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run the full gate pipeline against the manifest (no apply)
python -m agent.pipeline --manifest manifest.yaml --env staging

# Run with a pre-captured Infracost fixture (no live infracost needed)
python -m agent.pipeline --manifest manifest.yaml --infracost-fixture tests/fixtures/infracost_payments_db_pass.json

# Run the test suite
python -m pytest tests/
```

Requires: `checkov`, `trivy`, `tofu` (OpenTofu), `infracost` on PATH for live runs. Fixtures cover all gates for offline testing.
