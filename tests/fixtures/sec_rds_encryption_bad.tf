resource "aws_db_instance" "payments_db_bad" {
  identifier          = "payments-staging-bad"
  engine              = "postgres"
  engine_version      = "16"
  instance_class      = "db.t3.small"
  allocated_storage   = 20
  storage_encrypted   = false
  publicly_accessible = false
  skip_final_snapshot = true
}
