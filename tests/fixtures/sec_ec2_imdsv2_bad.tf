# Known-bad: EC2 instance without IMDSv2 enforcement.
# metadata_options not set — defaults to http_tokens = "optional" (insecure).
# Checkov CKV_AWS_79 must FAIL on this file.

resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"

  tags = {
    environment = "staging"
  }
}
