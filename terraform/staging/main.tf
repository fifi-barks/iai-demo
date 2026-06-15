# Payments staging environment — demo resources.
# Regions are configured in providers.tf (LOCKED); do NOT set region on resources.
#
# This file gives the gates real HCL to analyze:
#   - Cost gate (Infracost) reconciles aws_db_instance.payments_db against the
#     FinOps reference ($39.71/mo ± $4.00 — see research/findings/finops-rds-postgres-cost-reference.md).
#   - Security gate (Checkov/tfsec) will flag aws_security_group.app_tier open ingress.

resource "aws_vpc" "payments_vpc" {
  cidr_block = "10.0.0.0/16"

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}

resource "aws_subnet" "payments_private_az1" {
  vpc_id                  = aws_vpc.payments_vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "ap-southeast-5a"
  map_public_ip_on_launch = false

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}

resource "aws_subnet" "payments_private_az2" {
  vpc_id                  = aws_vpc.payments_vpc.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "ap-southeast-5b"
  map_public_ip_on_launch = false

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}

resource "aws_db_subnet_group" "payments" {
  name       = "payments-staging"
  subnet_ids = [aws_subnet.payments_private_az1.id, aws_subnet.payments_private_az2.id]

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}

resource "aws_db_instance" "payments_db" {
  identifier           = "payments-staging"
  engine               = "postgres"
  engine_version       = "16"
  instance_class       = "db.t3.small"
  allocated_storage    = 20
  storage_type         = "gp3"
  storage_encrypted    = true
  publicly_accessible  = false
  skip_final_snapshot  = true
  db_subnet_group_name = aws_db_subnet_group.payments.name

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}

# Intentionally over-permissive: known-bad form for the security gate to flag.
# The cost gate ignores this resource.
resource "aws_security_group" "app_tier" {
  name        = "payments-app-tier"
  description = "App tier security group for payments staging"
  vpc_id      = aws_vpc.payments_vpc.id

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

# App tier: runs pre-baked image provisioned by CI/Packer upstream (out of scope).
# The AMI variable must be supplied at runtime (e.g., via terraform.tfvars or -var).
# For demo purposes, this is a placeholder; the real AMI ID comes from the build pipeline.
resource "aws_instance" "app_tier" {
  ami                    = var.app_tier_ami
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.payments_private_az1.id
  vpc_security_group_ids = [aws_security_group.app_tier.id]

  tags = {
    environment = var.environment
    owner       = "payments-team"
  }
}
