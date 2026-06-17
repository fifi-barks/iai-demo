# Known-good: EC2 instance with IMDSv2 enforced (http_tokens = "required").
# Checkov CKV_AWS_79 must PASS on this file.

resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = {
    environment = "staging"
  }
}
