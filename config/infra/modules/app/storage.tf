resource "google_storage_bucket" "convictional_storage_production" {
  cors {
    max_age_seconds = 3600
    # POST lets the browser upload meeting recordings direct-to-bucket via a
    # signed POST policy, so large videos never transit the app.
    method          = ["GET", "POST", "OPTIONS"]
    origin          = concat(["https://${var.domain}"], var.additional_cors_origins)
    response_header = ["*"]
  }

  force_destroy               = false
  location                    = "US"
  name                        = var.storage_bucket_name
  public_access_prevention    = "enforced"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
}
