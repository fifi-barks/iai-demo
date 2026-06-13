# Provider configuration — payments staging environment (OpenTofu).
# Regions are LOCKED (2026-06-04) and intentionally hardcoded, not variables:
#   AWS: ap-southeast-5 (Kuala Lumpur, Malaysia)
#   GCP: asia-southeast1 (Singapore)
# Credentials: AWS via EC2 instance role (IMDSv2); GCP via Workload Identity Federation.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # TODO (Milestone 1): configure remote backend when the agent host is provisioned.
}

provider "aws" {
  region = "ap-southeast-5"
  # No profile: credentials come from the EC2 instance role (IMDSv2).
}

provider "google" {
  project = var.gcp_project
  region  = "asia-southeast1"
}
