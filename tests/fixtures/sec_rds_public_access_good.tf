resource "aws_db_instance" "payments_db_good" {
  identifier          = "payments-staging-bad"
  engine              = "postgres"
  engine_version      = "16"
  instance_class      = "db.t3.small"
  allocated_storage   = 20
  storage_encrypted   = true
  publicly_accessible = false
  skip_final_snapshot = true
}
