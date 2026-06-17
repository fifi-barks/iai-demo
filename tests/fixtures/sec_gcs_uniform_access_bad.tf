# Known-bad: GCS bucket without uniform bucket-level access.
# uniform_bucket_level_access defaults to false — ACLs are enabled (insecure).
# Checkov CKV_GCP_29 must FAIL on this file.

resource "google_storage_bucket" "example" {
  name     = "example-bucket-bad"
  location = "ASIA-SOUTHEAST1"
}
