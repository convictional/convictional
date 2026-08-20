resource "google_cloud_scheduler_job" "convictional_create_upcoming_meetings" {
  name             = "convictional-create-upcoming-meetings"
  description      = "Create meetings for upcoming calendar events"
  schedule         = "*/15 * * * *" # Every 15 minutes
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/create_upcoming_meetings"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_check_updates" {
  name             = "convictional-check-organization-updates"
  description      = "Check and create organization updates based on configured schedules"
  schedule         = "0 * * * *" # Every hour at the top of the hour
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/check_scheduled_updates"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_check_scheduled_research" {
  name             = "convictional-check-scheduled-research"
  description      = "Check and enqueue scheduled research runs due this hour"
  schedule         = "0 * * * *" # Every hour at the top of the hour
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/check_scheduled_research"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}


resource "google_cloud_scheduler_job" "convictional_cache_cleanup" {
  name             = "convictional-cache-cleanup"
  description      = "Clean up expired cache entries"
  schedule         = "*/15 * * * *" # Every 15 minutes
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/cache_cleanup"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}


resource "google_cloud_scheduler_job" "convictional_renew_gmail_watches" {
  name             = "convictional-renew-gmail-watches"
  description      = "Renew expiring Gmail watch subscriptions"
  schedule         = "0 * * * *" # Every hour
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/renew_gmail_watches"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_merge_and_notify_live_documents" {
  name             = "convictional-merge-and-notify-live-documents"
  description      = "Merge stable live document updates and send notifications"
  schedule         = "*/15 * * * *" # Every 15 minutes
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/merge_and_notify_live_documents"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_refresh_gmail_contacts" {
  name             = "convictional-refresh-gmail-contacts"
  description      = "Refresh Gmail contacts for all users"
  schedule         = "0 */2 * * *" # Every 2 hours
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/refresh_gmail_contacts"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_update_all_contact_interactions" {
  name             = "convictional-update-all-contact-interactions"
  description      = "Update last_interacted_at for all email contacts"
  schedule         = "0 1-23/2 * * *" # Every 2 hours starting at hour 1
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/update_all_contact_interactions"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_enqueue_outbox_jobs" {
  name             = "convictional-enqueue-outbox-jobs"
  description      = "Enqueue jobs that haven't been enqueued by the Jobs Outbox"
  schedule         = "*/10 * * * *" # Every 10 minutes
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/enqueue_outbox"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_terminate_dead_cloud_tasks" {
  name             = "convictional-terminate-dead-cloud-tasks"
  description      = "Reconcile jobs table with Cloud Tasks API"
  schedule         = "15 * * * *" # Every hour at minute 15
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/terminate_dead_cloud_tasks"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_sweep_overdue_scheduled_drafts" {
  name             = "convictional-sweep-overdue-scheduled-drafts"
  description      = "Re-fire scheduled draft sends whose Cloud Task was lost"
  schedule         = "*/15 * * * *" # Every 15 minutes
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/sweep_overdue_scheduled_drafts"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}


resource "google_cloud_scheduler_job" "convictional_enqueue_gmail_health_check" {
  name             = "convictional-enqueue-gmail-health-check"
  description      = "Reconcile jobs table with Cloud Tasks API"
  schedule         = "*/15 * * * *" # Every 15 minutes
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/enqueue_gmail_health_check"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}


resource "google_cloud_scheduler_job" "convictional_check_snoozed_mailbox_entries" {
  name             = "convictional-check-snoozed-mailbox-entries"
  description      = "Check snoozed mailbox entries for unsnoozing"
  schedule         = "*/15 * * * *" # Every 15 minutes
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/check_snoozed_mailbox_entries"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}



resource "google_cloud_scheduler_job" "convictional_cleanup_orphaned_recall_bot" {
  name             = "convictional-cleanup-orphaned-recall-bot"
  description      = "Clean up orphaned Recall.AI bots"
  schedule         = "0 * * * *" # Every hour
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/cleanup_orphaned_recall_bot"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_cleanup_unclaimed_attachments" {
  name             = "convictional-cleanup-unclaimed-attachments"
  description      = "Clean up unclaimed attachments after 7-day grace period"
  schedule         = "0 * * * *" # Every hour
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/cleanup_unclaimed_attachments"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_enqueue_goal_alignment" {
  name             = "convictional-enqueue-goal-alignment"
  description      = "Enqueue goal alignment scoring for all organizations"
  schedule         = "0 4 * * 1" # Weekly on Monday at 4:00 AM UTC (Sunday night)
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/enqueue_goal_alignment"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_cleanup_old_jobs" {
  name             = "convictional-cleanup-old-jobs"
  description      = "Clean up job records older than 90 days"
  schedule         = "0 3 * * *" # Daily at 3:00 AM UTC
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/cleanup_old_jobs"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_cleanup_push_subscriptions" {
  name             = "convictional-cleanup-push-subscriptions"
  description      = "Hard-delete push subscription rows soft-deleted >30 days ago"
  schedule         = "30 3 * * *" # Daily at 3:30 AM UTC
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/cleanup_push_subscriptions"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}

resource "google_cloud_scheduler_job" "convictional_schedule_chat_history_indexing" {
  name             = "convictional-schedule-chat-history-indexing"
  description      = "Find chats with unindexed messages and schedule chat history indexing"
  schedule         = "0 */2 * * *" # Every 2 hours
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.jobs_service_url}/jobs/recurring/schedule_chat_history_indexing"
    oidc_token {
      service_account_email = data.google_compute_default_service_account.default.email
      audience              = "${local.jobs_service_url}/"
    }
  }
}
