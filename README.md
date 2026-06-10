# iai-demo

A proof-of-concept of **Infrastructure as Intent (IAI)** — an AI agent that takes a plain-language business request, generates multi-cloud infrastructure code, validates it through three automated gates, and asks a human to approve a plain-English summary before applying anything.

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

## The demo scenario

**Intent prompt:**
> "Stand up a staging environment for the payments service: a managed Postgres, an app compute tier, and a private network in AWS, plus an object-storage bucket in GCP for export files. Tag it staging, owner payments-team."

**Resources provisioned:** AWS VPC · private subnet · RDS Postgres (data-bearing, critical) · EC2 app tier (inherits critical via dependency) · GCP storage bucket · IAM + security groups (~7–8 resources total)

**What the gates catch:**
- Security: the generated app-tier security group allows inbound from `0.0.0.0/0` — flagged (CKV_AWS_24); summary states ingress restricted to the VPC CIDR. RDS encryption-at-rest on, not publicly accessible — both pass.
- Cost: Infracost estimate with RDS as the dominant line item; one number, one driver named.
- Plan: 7 resources to add, 0 to change, 0 to destroy; critical resources flagged.

**The approval card the human sees:**
> 7 resources across AWS + GCP · ~$X/mo · 1 issue caught and fixed — app tier restricted to VPC · payments-db + app-tier tagged critical, snapshot before apply · **[ Approve ] [ Decline ]**

## Clouds & regions

| Cloud | Region | Auth |
|-------|--------|------|
| AWS | `ap-southeast-5` (Kuala Lumpur) | EC2 instance role via IMDSv2 |
| GCP | `asia-southeast1` (Singapore) | Workload Identity Federation |

No static credentials anywhere in the codebase.

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
