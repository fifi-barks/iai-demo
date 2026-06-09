# Edge-case fixture: aws_vpc_security_group_ingress_rule with 0.0.0.0/0.
# Purpose: observational test to document whether CKV_AWS_277 fires on this
# newer resource type. Researcher spec (sec-sg-open-ingress.md) notes a known
# partial-coverage gap (Checkov issue #6624, open as of 2024).
resource "aws_vpc_security_group_ingress_rule" "app_tier_open" {
  security_group_id = "sg-placeholder"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 8080
  to_port           = 8080
  ip_protocol       = "tcp"
}
