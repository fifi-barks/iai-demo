# Provider configuration — payments staging environment (OpenTofu).
# Regions LOCKED (2026-06-04):
#   AWS: ap-southeast-5 (Kuala Lumpur, Malaysia)
#   GCP: asia-southeast1 (Singapore)
# Credentials:
#   AWS: EC2 instance role (IMDSv2) — no static keys.
#   GCP: Workload Identity Federation (WIF) — no service-account key files.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # TODO: configure remote backend when agent host is provisioned.
}

provider "aws" {
  region = "ap-southeast-5"
  # No profile: credentials come from EC2 instance role (IMDSv2).
}

provider "google" {
  project = var.gcp_project
  region  = "asia-southeast1"
  # No key file: credentials come from Workload Identity Federation (WIF).
}
