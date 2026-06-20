---
domain: SecOps
topic: Over-permissive ingress (0.0.0.0/0) on AWS security groups
status: ready
confidence: high
whitepaper: WP2
---

# Over-Permissive Security Group Ingress from 0.0.0.0/0

## Rule

An AWS security group must not contain an ingress rule that permits SSH traffic (port 22) from `0.0.0.0/0` (or `::/0`). The demo scenario is SSH (port 22) open to the entire internet. Every ingress rule must specify a narrower CIDR (e.g. the VPC CIDR) or a source security group ID.

## Source

1. **CIS Amazon Web Services Foundations Benchmark v3.0.0** — published 2024-01-31. Controls 5.2 ("Ensure no security groups allow ingress from 0.0.0.0/0 or ::/0 to remote server administration ports") and 5.4 ("Ensure the default security group of every VPC restricts all traffic"). v3.0 announced in AWS Security Hub on 2024-05-13.
   - Download: https://www.cisecurity.org/benchmark/amazon_web_services
   - AWS Security Hub v3.0 announcement: https://aws.amazon.com/about-aws/whats-new/2024/05/aws-security-hub-3-0-cis-foundations-benchmark/

2. **AWS Well-Architected Framework — Security Pillar**, SEC05-BP02 "Control traffic flow within your network layers". Recommends point-to-point flows, least-privilege ingress, and purpose-built security groups per tier (e.g. DB tier accepts traffic only from the app tier SG). Current as of 2024; page: https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_layered.html

3. **NIST SP 800-53 Rev. 5**, SC-7 (Boundary Protection) and AC-6 (Least Privilege). Published September 2020, updated 2022. Requires boundary controls that restrict network traffic to only what is explicitly required. https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final

## Gate mapping

- Engine: **Checkov** (primary) + **Trivy config** (secondary, belt-and-suspenders)
- Check IDs:
  - `CKV_AWS_24` — "Ensure no security groups allow ingress from 0.0.0.0/0 to port 22 (SSH)". Implemented in `checkov/terraform/checks/resource/aws/SecurityGroupUnrestrictedIngress22.py`. **This is the primary demo check.** Applies to `aws_security_group`, `aws_security_group_rule`, `aws_vpc_security_group_ingress_rule`.
  - `CKV_AWS_25` — "Ensure no security groups allow ingress from 0.0.0.0/0 to port 3389 (RDP)". Companion check for completeness; same resource types as CKV_AWS_24. Not the focus of this demo scenario but listed as belt-and-suspenders coverage for remote administration ports.
  - `CKV_AWS_277` — "Ensure no security groups allow ingress from 0.0.0.0/0 to port -1 (all protocols/ports)". This check fires ONLY on rules where `protocol = "-1"` (all-traffic). It does NOT fire on specific-port rules such as port 22 or port 8080. It is NOT the primary check for this demo scenario; it is noted here for completeness as coverage for blanket all-traffic rules.
  - `AVD-AWS-0018` (Trivy config) — "An ingress security group rule allows traffic from /0." Aqua AVD identifier; replaces the retired tfsec check `aws-ec2-no-public-ingress-sgr`. Severity: CRITICAL. https://avd.aquasec.com/misconfig/avd-aws-0018

- **Primary check for the demo gate: `CKV_AWS_24`**. The demo scenario is an app-tier SG with SSH (port 22) open to `0.0.0.0/0`. CKV_AWS_24 is the authoritative check that fires on this configuration. CKV_AWS_277 will NOT fire here because the rule specifies `protocol = "tcp"` with `from_port = 22`, not `protocol = "-1"`.

- Supported Terraform resource types for CKV_AWS_24:
  - `aws_security_group` (inline `ingress` blocks) — **confirmed to fire reliably; preferred form for demo fixtures**
  - `aws_security_group_rule` (type = "ingress")
  - `aws_vpc_security_group_ingress_rule` — has a known partial-coverage gap in some Checkov versions (originally documented in Checkov issue #6624 in the context of CKV_AWS_277; use `aws_security_group` with inline blocks in demo fixtures to guarantee CKV_AWS_24 fires reliably)

- Severity in approval summary: **CRITICAL**

## Expected cases (for the Tester's fixtures)

**Known-bad** (must be flagged by CKV_AWS_24):

```hcl
resource "aws_security_group" "app_tier_bad" {
  name        = "payments-app-tier"
  description = "App tier - SSH open to internet (bad)"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]   # VIOLATION: SSH open to the entire internet
  }
}
```

Expected Checkov output: `FAILED for resource: aws_security_group.app_tier_bad` on check `CKV_AWS_24`.

**Known-good** (must pass CKV_AWS_24):

```hcl
resource "aws_security_group" "app_tier_good" {
  name        = "payments-app-tier"
  description = "App tier - restricted to VPC"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]   # PASS: restricted to VPC CIDR
  }
}
```

Alternative good form (source SG):

```hcl
resource "aws_security_group" "app_tier_good_sg" {
  name   = "payments-app-tier"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]   # PASS: source SG, no CIDR
  }
}
```

## Notes

**Why CKV_AWS_24 is the right check for this demo:** The demo's security catch is SSH (port 22) open to `0.0.0.0/0`. CKV_AWS_24 is purpose-built for exactly this case: it checks for unrestricted internet ingress on port 22 specifically. CKV_AWS_277 is a separate check that covers `protocol = "-1"` (all-traffic) rules only; the tester confirmed it does NOT fire on specific-port rules including port 22. The Developer must ensure the demo Terraform uses `aws_security_group` with an inline ingress block, not `aws_vpc_security_group_ingress_rule`, to avoid any partial-coverage edge cases.

**Demo narrative:** The approval summary should state plainly: "The app tier security group would have been reachable via SSH from the entire internet (0.0.0.0/0 on port 22). Ingress has been restricted to the VPC CIDR." This is framed as the kind of default humans miss, not a planted bug. The contrast with passing RDS checks (see sec-rds-encryption-and-access.md) is what makes the gate read as discrimination rather than noise.

**Trivy note:** `AVD-AWS-0018` (Trivy config) covers `aws_security_group` inline blocks and `aws_security_group_rule`. Trivy absorbed tfsec (Aqua acquisition); the AVD IDs are the canonical successors to tfsec rule IDs. Use Checkov CKV_AWS_24 as the authoritative gate check; Trivy provides secondary confirmation. Running both tools is belt-and-suspenders and recommended for the whitepaper narrative.

**Check ID stability note:** CKV_AWS_24 is a long-standing Checkov check for SSH ingress, confirmed current in the Checkov main branch. Check IDs do not change once assigned; the risk is that a new check may be added in future that supersedes this one. Flag for re-verification if Checkov is upgraded past a major version boundary.

**CIS Benchmark note:** CIS AWS Foundations Benchmark v3.0.0 (2024-01-31) is the current version. v2.0.0 (2023) remains widely referenced; both cover security group ingress restrictions. The Tester should cite v3.0.0.

Sources confirmed: Checkov GitHub (https://github.com/bridgecrewio/checkov), Trivy AVD (https://avd.aquasec.com/misconfig/), CIS (https://www.cisecurity.org/benchmark/amazon_web_services), AWS Well-Architected (https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/).
