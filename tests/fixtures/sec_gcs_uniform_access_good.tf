# Known-good: GCS bucket with uniform bucket-level access enabled.
# Checkov CKV_GCP_29 must PASS on this file.

resource "google_storage_bucket" "example" {
  name                        = "example-bucket-good"
  location                    = "ASIA-SOUTHEAST1"
  uniform_bucket_level_access = true
}
