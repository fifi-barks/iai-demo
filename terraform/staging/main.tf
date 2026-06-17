# Payments staging environment — demo resources (v2: AWS + GCP).
# Regions are configured in providers.tf (LOCKED); do NOT set region on resources.
#
# Gates this file feeds:
#   - Security gate (Checkov/Trivy) will flag aws_security_group.app_tier open
#     SSH ingress (CKV_AWS_24 = FAIL), and confirm IMDSv2 on aws_instance.app_tier
#     (CKV_AWS_79 = PASS) and uniform bucket access on the GCS bucket (CKV_GCP_29 = PASS).
#   - Cost gate (Infracost) reconciles aws_instance.app_tier against the
#     FinOps reference ($9.38/mo ± $1.00 — see research/findings/finops-ec2-app-tier-cost-reference.md).

# Intentionally over-permissive: known-bad form for the security gate to flag.
# Port 22 open to 0.0.0.0/0 is the CKV_AWS_24 finding the gate must catch.
resource "aws_security_group" "app_tier" {
  name        = "payments-app-tier"
  description = "App tier security group for payments staging"

  ingress {
    description = "SSH - intentionally open to internet for security gate demo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}

# App tier: EC2 instance in the default VPC.
# IMDSv2 is enforced (http_tokens = required) — CKV_AWS_79 passes.
# root_block_device declared explicitly for deterministic Infracost estimates.
resource "aws_instance" "app_tier" {
  ami                    = var.app_tier_ami
  instance_type          = "t3.micro"
  vpc_security_group_ids = [aws_security_group.app_tier.id]

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
  }

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}

# GCS export bucket. Uniform bucket-level access is enforced — CKV_GCP_29 passes.
resource "google_storage_bucket" "export_bucket" {
  name          = "iai-export-${var.environment}"
  location      = "ASIA-SOUTHEAST1"
  force_destroy = true

  uniform_bucket_level_access = true

  labels = {
    environment = var.environment
    owner       = "payments-team"
  }
}
