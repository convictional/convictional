resource "google_project_service" "secretmanager_googleapis_com" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false # Prevents disabling APIs on destroy
}
resource "google_project_service" "cloudtasks_googleapis_com" {
  service            = "cloudtasks.googleapis.com"
  disable_on_destroy = false
}
resource "google_project_service" "compute_googleapis_com" {
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}
resource "google_project_service" "run_googleapis_com" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}
resource "google_project_service" "sqladmin_googleapis_com" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}
resource "google_project_service" "iam_credentials_googleapis_com" {
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}
resource "google_project_service" "cloudscheduler_googleapis_com" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}
resource "google_project_service" "gmail_googleapis_com" {
  service            = "gmail.googleapis.com"
  disable_on_destroy = false
}
resource "google_project_service" "pubsub_googleapis_com" {
  service            = "pubsub.googleapis.com"
  disable_on_destroy = false
}
