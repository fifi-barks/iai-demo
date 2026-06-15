# Terraform variables for payments staging environment (v1: AWS-only).
#
# Note: Regions are locked in providers.tf (ap-southeast-5 for AWS).
# Do NOT override region variables — they are intentionally hardcoded.

environment = "staging"

# Pre-baked AMI ID for the app tier. Built upstream by CI/Packer.
# This is a placeholder; use a real Ubuntu 22.04 AMI in ap-southeast-5.
# To find a valid AMI:
#   aws ec2 describe-images --region ap-southeast-5 \
#     --owners 099720109477 \
#     --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04*" \
#     --query 'Images[0].ImageId' --output text
app_tier_ami = "ami-0c55b159cbfafe1f0"

# Container image URI for Trivy image scanning (security gate).
app_tier_image_uri = "ubuntu:22.04"
