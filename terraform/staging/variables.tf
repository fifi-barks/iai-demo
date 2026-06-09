# Inputs the providers need that should not be hardcoded.
# Note: regions are deliberately NOT variables — they are locked in providers.tf.
# Note: aws_profile removed — credentials come from the EC2 instance role (IMDSv2).

variable "gcp_project" {
  description = "GCP project ID. Must be supplied — no default."
  type        = string
}

variable "environment" {
  description = "Environment name, used for tagging/labelling resources."
  type        = string
  default     = "staging"
}

variable "app_tier_ami" {
  description = "Pre-baked AMI ID for the app tier. Built by CI/Packer upstream (out of scope for demo)."
  type        = string
}

variable "app_tier_image_uri" {
  description = "Container/OCI image URI for the app tier (used by security gate for image scanning)."
  type        = string
  default     = ""
}
