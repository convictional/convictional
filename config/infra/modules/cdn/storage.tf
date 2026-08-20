resource "google_storage_bucket" "assets" {
  cors {
    max_age_seconds = 3600
    method          = ["GET", "HEAD", "OPTIONS"]
    origin          = concat(["https://${var.domain}"], var.additional_cors_origins)
    response_header = ["*"]
  }

  force_destroy               = false
  location                    = "US"
  name                        = var.storage_bucket_name
  public_access_prevention    = "inherited"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "assets_public_read" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
