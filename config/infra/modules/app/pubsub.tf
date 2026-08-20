# Pub/Sub topic for Gmail push notifications
resource "google_pubsub_topic" "gmail_notifications" {
  name = "gmail-notifications"

  depends_on = [google_project_service.pubsub_googleapis_com]
}

# Subscription that pushes Gmail notifications to our webhook endpoint
resource "google_pubsub_subscription" "gmail_notifications" {
  name  = "gmail-notifications-sub"
  topic = google_pubsub_topic.gmail_notifications.name

  # Configure push delivery to our webhook endpoint
  push_config {
    push_endpoint = "${local.deterministic_app_url}/integrations/gmail/webhook"

    # Use OIDC token for authentication
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.deterministic_app_url}/"
    }
  }

  # Acknowledgment deadline - how long Pub/Sub waits for ack
  ack_deadline_seconds = 20

  # Retry policy for failed deliveries
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  # Expire messages after 7 days if not delivered
  message_retention_duration = "604800s"

  depends_on = [google_project_service.pubsub_googleapis_com]
}

# Allow Gmail API to publish messages to our topic
resource "google_pubsub_topic_iam_member" "gmail_publisher" {
  topic  = google_pubsub_topic.gmail_notifications.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:gmail-api-push@system.gserviceaccount.com"

  depends_on = [google_pubsub_topic.gmail_notifications]
}
