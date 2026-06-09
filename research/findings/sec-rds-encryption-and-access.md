---
domain: SecOps
topic: RDS Postgres — encryption-at-rest and not publicly accessible
status: ready
confidence: high
whitepaper: WP2
---

# RDS PostgreSQL: Encryption-at-Rest and Public Accessibility Controls

Two rules. Both must produce clean passes in the demo. Together they demonstrate the gate has discrimination: it flags the app-tier SG (see sec-sg-open-ingress.md) but correctly passes these RDS controls.

---

## Rule A — Encryption at Rest

An `aws_db_instance` resource must have `storage_encrypted = true`. RDS data at rest must be encrypted using AWS-managed or customer-managed keys; plaintext storage is not permitted.

## Rule B — No Public Accessibility

An `aws_db_instance` resource must have `publicly_accessible = false`. The RDS instance must not be reachable from the public internet; it must reside in a private subnet and accept connections only from within the VPC.

---

## Source

**Rule A — Encryption at Rest**

1. **CIS Amazon Web Services Foundations Benchmark v3.0.0** (2024-01-31) — broadly requires encryption of data at rest. While RDS-specific controls appear in the CIS AWS Foundations Benchmark and AWS Security Hub, the direct control is surfaced through AWS Config rule `rds-storage-encrypted`. https://www.cisecurity.org/benchmark/amazon_web_services

2. **AWS Well-Architected Framework — Security Pillar**, SEC08-BP01 "Implement secure key management" and SEC08-BP02 "Enforce encryption at rest". States: "Implement encryption at rest for all data stores." Current as of 2024. https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_protect_data_rest_key_mgmt.html

3. **NIST SP 800-53 Rev. 5**, SC-28 (Protection of Information at Rest): "The information system protects the confidentiality and integrity of information at rest." Directly maps to RDS storage encryption. https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final

4. **AWS Config managed rule**: `rds-storage-encrypted` — flags RDS instances where `StorageEncrypted` is false. https://docs.aws.amazon.com/config/latest/developerguide/rds-storage-encrypted.html

**Rule B — No Public Accessibility**

1. **CIS Amazon Web Services Foundations Benchmark v3.0.0** (2024-01-31). Public database access violates network boundary controls embedded throughout Section 5 (Networking). https://www.cisecurity.org/benchmark/amazon_web_services

2. **AWS Well-Architected Framework — Security Pillar**, SEC05-BP01 "Create network layers" and SEC05-BP02 "Control traffic flow within your network layers". Explicitly recommends placing databases in private subnets with no public route. https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_layered.html

3. **NIST SP 800-53 Rev. 5**, SC-7 (Boundary Protection) and AC-3 (Access Enforcement). Requires network boundary controls that prohibit unnecessary public exposure of information systems. https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final

---

## Gate mapping

### Rule A — Encryption at Rest

- Engine: **Checkov** (primary) + **Trivy config** (secondary)
- Check IDs:
  - `CKV_AWS_16` — "Ensure all data stored in the RDS is securely encrypted at rest". Applies to `aws_db_instance`. Confirmed in Checkov main branch; implemented in `checkov/terraform/checks/resource/aws/RDSEncryption.py`.
  - `AVD-AWS-0077` (Trivy) — "Instance does not have storage encryption enabled." Aqua AVD identifier; replaces the retired tfsec check `aws-rds-encrypt-instance-storage-data`. https://avd.aquasec.com/misconfig/avd-aws-0077
- Severity in approval summary: **HIGH** (data-bearing resource; demo tags this instance as `critical`)

### Rule B — No Public Accessibility

- Engine: **Checkov** (primary) + **Trivy config** (secondary)
- Check IDs:
  - `CKV_AWS_17` — "Ensure all data stored in RDS is not publicly accessible". Applies to `aws_db_instance` and `aws_rds_cluster_instance`. Confirmed in Checkov main branch.
  - `AVD-AWS-0076` (Trivy) — "A database resource is publicly accessible." Aqua AVD identifier; replaces the retired tfsec check `aws-rds-no-public-db-access`. https://avd.aquasec.com/misconfig/avd-aws-0076
- Severity in approval summary: **HIGH**

---

## Expected cases (for the Tester's fixtures)

### Rule A — Encryption at Rest

**Known-bad** (must be flagged by CKV_AWS_16):

```hcl
resource "aws_db_instance" "payments_db_bad" {
  identifier        = "payments-staging"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.small"
  allocated_storage = 20
  db_name           = "payments"
  username          = "dbadmin"
  password          = var.db_password
  storage_encrypted = false   # VIOLATION: plaintext storage
  publicly_accessible = false
  skip_final_snapshot = true
}
```

Expected output: `FAILED for resource: aws_db_instance.payments_db_bad` on `CKV_AWS_16`.

**Known-good** (must pass CKV_AWS_16):

```hcl
resource "aws_db_instance" "payments_db_good" {
  identifier        = "payments-staging"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.small"
  allocated_storage = 20
  db_name           = "payments"
  username          = "dbadmin"
  password          = var.db_password
  storage_encrypted   = true   # PASS: encrypted at rest
  publicly_accessible = false
  skip_final_snapshot = true
}
```

### Rule B — No Public Accessibility

**Known-bad** (must be flagged by CKV_AWS_17):

```hcl
resource "aws_db_instance" "payments_db_public_bad" {
  identifier        = "payments-staging"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.small"
  allocated_storage = 20
  db_name           = "payments"
  username          = "dbadmin"
  password          = var.db_password
  storage_encrypted   = true
  publicly_accessible = true    # VIOLATION: public internet access enabled
  skip_final_snapshot = true
}
```

Expected output: `FAILED for resource: aws_db_instance.payments_db_public_bad` on `CKV_AWS_17`.

**Known-good** (must pass CKV_AWS_17):

```hcl
resource "aws_db_instance" "payments_db_private_good" {
  identifier        = "payments-staging"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.small"
  allocated_storage = 20
  db_name           = "payments"
  username          = "dbadmin"
  password          = var.db_password
  storage_encrypted   = true
  publicly_accessible = false   # PASS: private only
  db_subnet_group_name = aws_db_subnet_group.private.name
  skip_final_snapshot = true
}
```

---

## Notes

**Demo narrative role:** These two checks produce clean passes alongside the SG catch. The approval summary states: "Postgres encryption-at-rest: enabled (pass). Postgres public accessibility: disabled (pass)." This is the gate showing discrimination — not everything fails, only the genuine misconfiguration does.

**Omitting `storage_encrypted` defaults to false.** If the key is absent from the Terraform resource block, Checkov treats it as the AWS default (`false`) and CKV_AWS_16 will fire. The known-bad fixture may therefore omit the key entirely rather than explicitly setting it false — both forms should be tested.

**Omitting `publicly_accessible` defaults to false** for instances in a VPC. However, explicitly setting `publicly_accessible = false` is a defensible practice (intent is visible) and is what the known-good fixtures should use. The Tester should confirm CKV_AWS_17 passes when the key is omitted AND when it is explicitly false.

**`aws_rds_cluster_instance`:** CKV_AWS_17 also covers Aurora cluster instances. The demo uses `aws_db_instance` (standard RDS), not Aurora; the cluster fixture is out of scope for this demo but noted for the whitepaper.

**Trivy note:** `AVD-AWS-0077` and `AVD-AWS-0076` are the corresponding Trivy config AVD identifiers (Aqua's successor to tfsec). Running both tools (Checkov + Trivy config) in the gate provides redundant coverage and is the defensible posture for the whitepaper.

**Check ID stability:** CKV_AWS_16 and CKV_AWS_17 are low-numbered, original Checkov checks (introduced in early 2020) and are stable. They are extremely unlikely to be retired or renumbered. Verify against https://www.checkov.io/5.Policy%20Index/terraform.html if Checkov is upgraded.

**Engine version note:** PostgreSQL 16 is current as of 2024. The demo fixtures use `engine_version = "16"`. The Tester should confirm the engine version string is accepted by the AWS provider version in use.
