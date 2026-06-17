# Inputs for the staging environment (v2: AWS + GCP).
# Regions are locked in providers.tf.
# Credentials sourced from EC2 instance role (AWS IMDSv2) and WIF (GCP) — no static keys.

variable "environment" {
  description = "Environment name for resource tagging."
  type        = string
  default     = "staging"
}

variable "gcp_project" {
  description = "GCP project ID for the Google provider."
  type        = string
}

variable "app_tier_ami" {
  description = "Pre-baked AMI ID for the app tier (built upstream by CI/Packer)."
  type        = string
}

variable "app_tier_image_uri" {
  description = "Container image URI for Trivy security scanning (e.g., ubuntu:22.04)."
  type        = string
  default     = "ubuntu:22.04"
}
