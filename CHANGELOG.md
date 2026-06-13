cat << 'EOF' > CHANGELOG.md
# Changelog — iai-demo

All notable changes to this project will be documented in this file.

## [0.1.0] — 2026-06-09

### Added
- Phase 1: OpenTofu stack (not Terraform), immutable pre-baked image, Checkov+Trivy (config+image)
- Phase 2: Keyless credentials (AWS EC2 instance role + Workload Identity Federation to GCP)
- Phase 3: Multi-cloud apply, data-aware rollback (RDS snapshots), manifest auto-update
- Three-gate validation: plan, security (Checkov+Trivy), cost (Infracost)
- Telegram interface for intent input
- Approval synthesizer (no raw output to human)
- Demo scenario: Payments staging environment (AWS VPC+RDS+app tier, GCP bucket)

### Locked Design Decisions
- Manifest-driven tool selection
- Criticality tagging (transitive through dependency graph)
- No clarification engine in v1
- No Ansible in v1 (declared out-of-scope)

### Demo Scenario
- Intent: Stand up staging environment for payments service
- Clouds: AWS ap-southeast-5 (KL) + GCP asia-southeast1 (Singapore)
- Resources: ~7-8 (VPC, subnet, RDS, app tier, security groups, bucket)
- Security catch: app-tier SG open to 0.0.0.0/0 on port 22 (CKV_AWS_24)

---

## [Unreleased] — Future releases
- Phase 4: Demo video recording
- WP#2 (SecOps deep dive)
- WP#3 (FinOps deep dive)
- Full autonomous apply (progressive autonomy)
- Clarification engine
- Physical hardware (Cisco) support
EOF