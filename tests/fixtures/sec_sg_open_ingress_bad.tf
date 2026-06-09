resource "aws_security_group" "app_tier_bad" {
  name        = "payments-app-tier"
  description = "App tier - SSH open to internet (bad)"
  vpc_id      = "vpc-placeholder"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
