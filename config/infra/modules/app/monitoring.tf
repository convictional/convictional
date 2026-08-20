locals {
  # Console and repository links embedded in the alert documentation, so an
  # on-call responder can jump straight from the notification to the evidence.
  app_url      = "https://${var.domain}"
  commits_url  = "https://github.com/${var.github_repository}/commits/main/"
  sql_console  = "https://console.cloud.google.com/sql/instances/${google_sql_database_instance.convictional.name}"
  app_console  = "https://console.cloud.google.com/run/detail/${var.region}/${google_cloud_run_v2_service.convictional.name}"
  jobs_console = "https://console.cloud.google.com/run/detail/${var.region}/${google_cloud_run_v2_service.convictional_jobs.name}"
  console_qs   = "?project=${var.project_id}"
}

# Uptime check for Convictional production
resource "google_monitoring_uptime_check_config" "convictional_uptime" {
  display_name = "Convictional Uptime"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path           = "/login"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"

    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = "${var.app_subdomain}.${var.domain}"
    }
  }

  checker_type = "STATIC_IP_CHECKERS"
}

# Alert policy for oldest unacked message age
resource "google_monitoring_alert_policy" "gmail_notifications_oldest_unacked_age" {
  display_name = "Cloud Pub/Sub Subscription - Oldest unacked message age (filtered) [MAX]"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Pub/Sub Subscription - Oldest unacked message age (filtered) [MAX]"

    condition_threshold {
      filter          = "resource.type = \"pubsub_subscription\" AND resource.labels.subscription_id = \"gmail-notifications-sub\" AND metric.type = \"pubsub.googleapis.com/subscription/oldest_unacked_message_age\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 180.0

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "Oldest unacked message has exceeded 180s for 5+ minutes — the app may be down or the gmail webhook is unavailable."
    mime_type = "text/markdown"
    subject   = "gmail-notifications PubSub oldest unacked message"
  }

  depends_on = [google_pubsub_subscription.gmail_notifications]
}

# Alert policy for undelivered messages
resource "google_monitoring_alert_policy" "gmail_notifications_undelivered_messages" {
  display_name = "Unacked messages for gmail-notifications-sub [SUM]"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Unacked messages for gmail-notifications-sub [SUM]"

    condition_threshold {
      filter          = "resource.type = \"pubsub_subscription\" AND resource.labels.subscription_id = \"gmail-notifications-sub\" AND metric.type = \"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10.0

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "There are unacked messages in the gmail-notifications for 5 minutes or longer."
    mime_type = "text/markdown"
    subject   = "gmail-notifications - Unacked pubsub messages for 5 minutes"
  }

  depends_on = [google_pubsub_subscription.gmail_notifications]
}

# Alert policy for Cloud Tasks queue size - UI queue
resource "google_monitoring_alert_policy" "cloud_tasks_ui_queue_size" {
  display_name = "Cloud Tasks UI Queue - High queue size [MAX]"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Tasks UI Queue - High queue size [MAX]"

    condition_threshold {
      filter          = "resource.type = \"cloud_tasks_queue\" AND resource.labels.queue_id = \"convictional-ui\" AND metric.type = \"cloudtasks.googleapis.com/queue/depth\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5000.0

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "The convictional-ui Cloud Tasks queue has over 5000 pending tasks for 10+ minutes. This may indicate processing issues or high load."
    mime_type = "text/markdown"
    subject   = "convictional-ui Cloud Tasks queue - High queue size"
  }

  depends_on = [google_cloud_tasks_queue.convictional_ui]
}

# Alert policy for Cloud Tasks queue size - Email queue
resource "google_monitoring_alert_policy" "cloud_tasks_email_queue_size" {
  display_name = "Cloud Tasks Email Queue - High queue size [MAX]"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Tasks Email Queue - High queue size [MAX]"

    condition_threshold {
      filter          = "resource.type = \"cloud_tasks_queue\" AND resource.labels.queue_id = \"convictional-email\" AND metric.type = \"cloudtasks.googleapis.com/queue/depth\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5000.0

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "The convictional-email Cloud Tasks queue has over 5000 pending tasks for 10+ minutes. This may indicate email delivery issues or high volume."
    mime_type = "text/markdown"
    subject   = "convictional-email Cloud Tasks queue - High queue size"
  }

  depends_on = [google_cloud_tasks_queue.convictional_email]
}

# Alert policy for Cloud Tasks queue size - Indexing queue
resource "google_monitoring_alert_policy" "cloud_tasks_indexing_queue_size" {
  display_name = "Cloud Tasks Indexing Queue - High queue size [MAX]"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Tasks Indexing Queue - High queue size [MAX]"

    condition_threshold {
      filter          = "resource.type = \"cloud_tasks_queue\" AND resource.labels.queue_id = \"convictional-indexing\" AND metric.type = \"cloudtasks.googleapis.com/queue/depth\""
      duration        = "900s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2000.0

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "The convictional-indexing Cloud Tasks queue has over 2000 pending tasks for 15+ minutes. This may indicate search indexing performance issues."
    mime_type = "text/markdown"
    subject   = "convictional-indexing Cloud Tasks queue - High queue size"
  }

  depends_on = [google_cloud_tasks_queue.convictional_indexing]
}

# Alert policy for Cloud Tasks queue size - Miscellaneous queue
resource "google_monitoring_alert_policy" "cloud_tasks_miscellaneous_queue_size" {
  display_name = "Cloud Tasks Miscellaneous Queue - High queue size [MAX]"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Tasks Miscellaneous Queue - High queue size [MAX]"

    condition_threshold {
      filter          = "resource.type = \"cloud_tasks_queue\" AND resource.labels.queue_id = \"convictional-miscellaneous\" AND metric.type = \"cloudtasks.googleapis.com/queue/depth\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2500.0

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "The convictional-miscellaneous Cloud Tasks queue has over 2500 pending tasks for 10+ minutes. This may indicate general background task processing issues."
    mime_type = "text/markdown"
    subject   = "convictional-miscellaneous Cloud Tasks queue - High queue size"
  }

  depends_on = [google_cloud_tasks_queue.convictional_miscellaneous]
}

# Alert policy for Cloud Tasks queue size - Onboarding Sync queue
resource "google_monitoring_alert_policy" "cloud_tasks_onboarding_sync_queue_size" {
  display_name = "Cloud Tasks Onboarding Sync Queue - High queue size [MAX]"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Tasks Onboarding Sync Queue - High queue size [MAX]"

    condition_threshold {
      filter          = "resource.type = \"cloud_tasks_queue\" AND resource.labels.queue_id = \"convictional-onboarding-sync\" AND metric.type = \"cloudtasks.googleapis.com/queue/depth\""
      duration        = "900s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2000.0

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "The convictional-onboarding-sync Cloud Tasks queue has over 2000 pending tasks for 15+ minutes. This may indicate onboarding mailbox sync processing issues."
    mime_type = "text/markdown"
    subject   = "convictional-onboarding-sync Cloud Tasks queue - High queue size"
  }

  depends_on = [google_cloud_tasks_queue.convictional_onboarding_sync]
}

# Alert policy for Cloud SQL oldest transaction age
resource "google_monitoring_alert_policy" "cloud_sql_oldest_transaction_age" {
  display_name = "Old Transaction"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL Database - Oldest transaction age"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/postgresql/vacuum/oldest_transaction_age\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 14400.0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = <<-EOT
      A transaction has been running for more than 4 hours. You probably don't want this.

      Long-running transactions are likely to cause headaches. They block other transactions and hog connections from pools. Normal batch jobs and analytics replication can run for tens of minutes; 4+ hours is genuinely stuck.

      - Verify [convictional](${local.app_url}) is accessible. Check multiple pages. Is performance degraded?
      - Are any recent [commits](${local.commits_url}) related?
      - Check the [Cloud SQL System Insights Page](${local.sql_console}/system-insights${local.console_qs}) for related symptoms. Consider the oldest transaction age, CPU usage, memory, storage.

      ## Actions

      If the app is inaccessible or performance is notably degraded, *restart the [Cloud SQL instance](${local.sql_console}/overview${local.console_qs})*.
    EOT
    mime_type = "text/markdown"
    subject   = "Old Transaction"
  }
}

# Alert policy for load balancer 429 responses
resource "google_monitoring_alert_policy" "load_balancer_429s" {
  display_name = "429s from Load Balancer"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Load Balancer 429s"

    condition_threshold {
      filter          = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code = \"429\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 100.0

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_COUNT"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "3600s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    mime_type = "text/markdown"
    subject   = "429s from Load Balancer"
  }
}

# Alert policy for Cloud SQL memory usage
resource "google_monitoring_alert_policy" "cloud_sql_memory_usage" {
  display_name = "Cloud SQL - Memory Usage High"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL Database - Memory utilization"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/memory/utilization\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.90

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "Cloud SQL memory utilization has been above 90% for 10+ minutes. Postgres normally trends high (shared_buffers + OS page cache); sustained 90%+ indicates real memory pressure worth investigating."
    mime_type = "text/markdown"
    subject   = "Cloud SQL Memory Usage High"
  }
}

# Alert policy for Cloud SQL disk read IO
resource "google_monitoring_alert_policy" "cloud_sql_disk_read_io" {
  display_name = "Cloud SQL Disk Read IO"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL Database - Disk read IO"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/disk/read_ops_count\""
      duration        = "1800s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2000.0

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "Cloud SQL disk read IO has been above 2000 ops/sec for 30+ minutes — sustained anomaly worth investigating (e.g. missing index, runaway query, replication backfill)."
    mime_type = "text/markdown"
    subject   = "Cloud SQL Disk Read IO High"
  }
}

# Alert policy for Cloud SQL disk usage
resource "google_monitoring_alert_policy" "cloud_sql_disk_usage" {
  display_name = "Cloud SQL Disk Usage"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL Database - Disk utilization"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/disk/utilization\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.95

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "Cloud SQL disk utilization is over 95%. `disk_autoresize` is enabled and normally keeps disk in the 50–90% sawtooth — sustained 95%+ suggests autoresize itself is failing (quota cap?) and warrants immediate investigation."
    mime_type = "text/markdown"
    subject   = "Cloud SQL Disk Usage >95%"
  }
}

# Alert policy for Cloud SQL disk write IO
resource "google_monitoring_alert_policy" "cloud_sql_disk_write_io" {
  display_name = "Cloud SQL Disk Write IO High"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL Database - Disk write IO"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/disk/write_ops_count\""
      duration        = "1800s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2500.0

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "Cloud SQL disk write IO has been above 2500 ops/sec for 30+ minutes — sustained anomaly worth investigating (e.g. write amplification, runaway batch job, replication catch-up)."
    mime_type = "text/markdown"
    subject   = "Cloud SQL Disk Write IO High"
  }
}

# Alert policy for Cloud SQL CPU usage
resource "google_monitoring_alert_policy" "cloud_sql_cpu_usage" {
  display_name = "Postgres CPU Usage High"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL Database - CPU utilization"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.85

      aggregations {
        alignment_period   = "600s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "The Postgres Instance CPU usage has been above 85% for 10+ minutes.\n\nThis can cause slow queries, but is more likely a symptom of another problem.\n\n- Verify [convictional](${local.app_url}) is accessible. Check multiple pages. Is performance degraded?\n- Are any recent [commits](${local.commits_url}) related?\n- Check the [Cloud SQL System Insights Page](${local.sql_console}/system-insights${local.console_qs}) for related symptoms. Consider the oldest transaction age, CPU usage, memory, storage.\n\n## Actions\n\nIf the app is inaccessible or performance is notably degraded, *restart the [Cloud SQL instance](${local.sql_console}/overview${local.console_qs})*."
    mime_type = "text/markdown"
    subject   = "Postgres CPU Usage High"
  }
}

# Alert policy for Convictional uptime check failure
resource "google_monitoring_alert_policy" "convictional_uptime_failure" {
  display_name = "Convictional Uptime uptime failure"
  enabled      = true
  severity     = "CRITICAL"
  combiner     = "OR"

  conditions {
    display_name = "Failure of uptime check_id ${google_monitoring_uptime_check_config.convictional_uptime.uptime_check_id}"

    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.convictional_uptime.uptime_check_id}\" AND resource.type=\"uptime_url\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1.0

      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.*"]
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.critical_notification_channels

  documentation {
    content   = "Google Cloud detected downtime on `${local.app_url}`.\n\nThis could be due to any number of reasons. Confirm symptoms and respond accordingly.\n\n- Was there a recent [deploy](${local.commits_url})? Did it introduce infra configuration changes?\n- Are there any known outages from [Google Cloud](https://status.cloud.google.com)?"
    mime_type = "text/markdown"
    subject   = "Convictional Production Downtime"
  }

  depends_on = [google_monitoring_uptime_check_config.convictional_uptime]
}

# Alert policy for Cloud SQL automated backup failures
resource "google_monitoring_alert_policy" "cloud_sql_backup_failure" {
  display_name = "Cloud SQL Backup Failure"
  enabled      = true
  severity     = "CRITICAL"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL automated backup failed"

    condition_matched_log {
      filter = "resource.type=\"cloudsql_database\"\nlog_name=\"projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Fsystem_event\"\nprotoPayload.methodName=\"cloudsql.instances.automatedBackup\"\nseverity>=ERROR"
    }
  }

  alert_strategy {
    auto_close = "3600s"
    notification_rate_limit {
      period = "300s"
    }
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "An automated Cloud SQL backup failed.\n\nReview the [Cloud SQL Backups page](${local.sql_console}/backups${local.console_qs}) and the failing audit log entry to diagnose. Confirm subsequent backups succeed before closing.\n\nIf failures persist, the database may be in a state that prevents backups (e.g., long-running transactions, replication lag, storage issues). Check the [Cloud SQL System Insights Page](${local.sql_console}/system-insights${local.console_qs})."
    mime_type = "text/markdown"
    subject   = "Cloud SQL Backup Failure"
  }
}

# Alert policy for production database RW login
resource "google_monitoring_alert_policy" "prod_rw_login" {
  display_name = "Notify on Prod RW Login"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Log match condition"

    condition_matched_log {
      filter = "resource.type=\"cloudsql_database\"\nprotoPayload.methodName=\"cloudsql.instances.login\"\nprotoPayload.@type=\"type.googleapis.com/google.cloud.audit.AuditLog\"\nprotoPayload.authenticationInfo.principalEmail=\"${google_service_account.convictional_eng_write.email}\""

      label_extractors = {
        User = "EXTRACT(protoPayload.authenticationInfo.serviceAccountDelegationInfo.firstPartyPrincipal.principalEmail)"
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
    notification_rate_limit {
      period = "300s"
    }
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "Someone has logged in as the eng R/W Postgres user.\n\nIf this was you, record the reason for your usage here:"
    mime_type = "text/markdown"
  }
}

# Alert policy for gunicorn worker timeouts in the convictional-jobs service
resource "google_monitoring_alert_policy" "convictional_jobs_worker_timeout" {
  display_name = "convictional-jobs - Gunicorn Worker Timeout"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Gunicorn worker timeout in convictional-jobs"

    condition_matched_log {
      filter = "resource.type=\"cloud_run_revision\"\nresource.labels.service_name=\"convictional-jobs\"\n(textPayload=~\"WORKER TIMEOUT\" OR jsonPayload.message=~\"WORKER TIMEOUT\")\nlogName=\"projects/${var.project_id}/logs/run.googleapis.com%2Fstderr\""
    }
  }

  alert_strategy {
    auto_close = "1800s"
    notification_rate_limit {
      period = "300s"
    }
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "A gunicorn worker in the `convictional-jobs` Cloud Run service was killed for exceeding its timeout (`[CRITICAL] WORKER TIMEOUT`).\n\nThis usually means a job hung — likely a slow external call, a deadlock, or an infinite loop. Open the [convictional-jobs logs](${local.jobs_console}/logs${local.console_qs}) and look for the request/job ID immediately preceding the timeout to identify which job was running.\n\nA single timeout doesn't require action; sustained or repeated timeouts indicate a regression that needs investigation."
    mime_type = "text/markdown"
    subject   = "convictional-jobs Gunicorn Worker Timeout"
  }
}

# Alert policy for gunicorn worker timeouts in the client-facing convictional service
resource "google_monitoring_alert_policy" "convictional_worker_timeout" {
  display_name = "convictional - Gunicorn Worker Timeout"
  enabled      = true
  severity     = "WARNING"
  combiner     = "OR"

  conditions {
    display_name = "Gunicorn worker timeout in convictional"

    condition_matched_log {
      filter = "resource.type=\"cloud_run_revision\"\nresource.labels.service_name=\"convictional\"\n(textPayload=~\"WORKER TIMEOUT\" OR jsonPayload.message=~\"WORKER TIMEOUT\")\nlogName=\"projects/${var.project_id}/logs/run.googleapis.com%2Fstderr\""
    }
  }

  alert_strategy {
    auto_close = "1800s"
    notification_rate_limit {
      period = "300s"
    }
  }

  notification_channels = var.alert_notification_channels

  documentation {
    content   = "A gunicorn worker in the client-facing `convictional` Cloud Run service was killed for exceeding its timeout (`[CRITICAL] WORKER TIMEOUT`).\n\nThis is on the synchronous request path — the user whose request was running saw a 5xx in their browser. Open the [convictional logs](${local.app_console}/logs${local.console_qs}) and look for the request immediately preceding the timeout to identify the slow endpoint.\n\nCommon causes: an unbounded query, a slow external call without a timeout, a missing index. A single timeout is worth a quick look; sustained or repeated timeouts mean real users are getting errors and warrant immediate investigation."
    mime_type = "text/markdown"
    subject   = "convictional Gunicorn Worker Timeout"
  }
}
