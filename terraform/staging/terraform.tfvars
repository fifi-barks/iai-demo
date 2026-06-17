# Terraform variables for payments staging environment (v2: AWS + GCP).
#
# Note: Regions are locked in providers.tf (ap-southeast-5 for AWS, asia-southeast1 for GCP).
# Do NOT override region variables — they are intentionally hardcoded.

environment = "staging"

# GCP project ID. Replace with your actual project ID.
# Find yours: gcloud config get-value project
gcp_project = "project-6a1faf58-bbc3-43f3-a40"

# Pre-baked AMI ID for the app tier. Built upstream by CI/Packer.
# This is a placeholder; use a real Ubuntu 22.04 AMI in ap-southeast-5.
# To find a valid AMI:
#   aws ec2 describe-images --region ap-southeast-5 \
#     --owners 099720109477 \
#     --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04*" \
#     --query 'Images[0].ImageId' --output text
app_tier_ami = "ami-0cbc168e73ba94e0a"

# Container image URI for Trivy image scanning (security gate).
app_tier_image_uri = "ubuntu:22.04"
