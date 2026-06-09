resource "aws_security_group" "app_tier_good" {
  name        = "payments-app-tier"
  description = "App tier - SSH restricted to VPC"
  vpc_id      = "vpc-placeholder"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
}
