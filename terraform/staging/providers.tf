# Provider configuration — payments staging environment (OpenTofu).
# Region LOCKED (2026-06-04): AWS ap-southeast-5 (Kuala Lumpur, Malaysia)
# Credentials: AWS EC2 instance role (IMDSv2) — no static keys.
# Note: GCP support deferred to v2; v1 focuses on AWS-only clean demo.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # TODO: configure remote backend when agent host is provisioned.
}

provider "aws" {
  region = "ap-southeast-5"
  # No profile: credentials come from EC2 instance role (IMDSv2).
}
