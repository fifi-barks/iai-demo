# Changelog — iai-demo

All notable changes to this project are documented here.

## [0.1.0] — 2026-06-09

### Added

- **Phase 1 — IaC stack:** OpenTofu (not Terraform), immutable pre-baked image, Checkov + Trivy (config + image scan)
- **Phase 2 — Keyless credentials:** AWS EC2 instance role (IMDSv2) + Workload Identity Federation to GCP — no static keys anywhere
- **Phase 3 — Apply + safety:** Multi-cloud `tofu apply`, state snapshot before every apply, native RDS snapshot for data-bearing resources, manifest auto-update after apply
- **Three-gate validation:** plan gate (resource count + risk) · security gate (Checkov primary + Trivy config secondary) · cost gate (Infracost monthly estimate)
- **Approval synthesizer:** all three gate results collapsed into one plain-English card — no raw tool output shown to the human
- **Telegram interface:** any plain-language message → pipeline → approval card with Approve / Decline buttons

### Demo scenario

- **Intent:** "Stand up a staging environment for the payments service: managed Postgres, app compute tier, private network in AWS, object-storage bucket in GCP for export files."
- **Clouds:** AWS `ap-southeast-5` (Kuala Lumpur) + GCP `asia-southeast1` (Singapore)
- **Resources:** ~7–8 total — VPC, private subnet, RDS Postgres (data-bearing, critical), EC2 app tier (inherits critical), GCP storage bucket, security groups, IAM glue
- **Security catch:** app-tier security group open to `0.0.0.0/0` on port 22 — flagged (CKV_AWS_24), ingress restricted to VPC CIDR before the summary is shown
- **Cost:** Infracost estimate with RDS as the dominant line item; one number, one driver named in the card

### Locked design decisions

- Manifest-driven tool selection — the manifest declares which IaC engine owns each environment; the agent reads it at runtime
- Criticality tagging is transitive through the dependency graph
- Greenfield-only provisioning in v1; no clarification engine
- Ansible / physical hardware declared out of scope for v1

---

## [Unreleased]

- Demo video
- Clarification engine (ask before assuming on ambiguous intent)
- Physical hardware support (Cisco)
