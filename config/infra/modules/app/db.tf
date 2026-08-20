resource "google_sql_database_instance" "convictional" {
  database_version = "POSTGRES_18"
  instance_type    = "CLOUD_SQL_INSTANCE"
  name             = "convictional"
  project          = var.project_id
  region           = var.region

  # disk_autoresize grows disk_size over time; ignore drift so tofu
  # doesn't plan a destroy-and-recreate to shrink it back. prevent_destroy
  # is a tofu-level guardrail on top of GCP's deletion_protection_enabled.
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [settings[0].disk_size]
  }

  settings {
    activation_policy = "ALWAYS"
    availability_type = "ZONAL"

    backup_configuration {
      backup_retention_settings {
        retained_backups = 15
        retention_unit   = "COUNT"
      }

      enabled                        = true
      location                       = var.db_backup_location
      point_in_time_recovery_enabled = true
      start_time                     = "02:00"
      transaction_log_retention_days = 14
    }

    connector_enforcement = "NOT_REQUIRED"

    database_flags {
      name  = "cloudsql.logical_decoding"
      value = "on"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    database_flags {
      name  = "cloudsql.enable_pgaudit"
      value = "on"
    }

    database_flags {
      name  = "max_connections"
      value = "2100" # up to 100 conns/instance * 10 instances * 2 services, with margin
    }

    database_flags {
      # Log any statement over 1s. Low enough to catch the slow full-text and
      # trigram searches that dominate this app's tail latency, high enough
      # that ordinary request queries don't flood the log.
      name  = "log_min_duration_statement"
      value = "1000"
    }

    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }

    database_flags {
      name  = "cloudsql.enable_auto_explain"
      value = "on"
    }

    database_flags {
      name  = "auto_explain.log_min_duration"
      value = "1000"
    }

    database_flags {
      name  = "auto_explain.log_analyze"
      value = "on"
    }

    database_flags {
      name  = "pg_stat_statements.track"
      value = "all"
    }

    database_flags {
      name  = "work_mem"
      value = "65536" # 64MB in KB - for expensive trigram/full-text operations
    }

    database_flags {
      name  = "effective_cache_size"
      value = "2936012" # ~22GB in 8KB pages (~70% of 32GB RAM on N-4); Cloud SQL caps this at the upper bound for the tier
    }

    database_flags {
      name  = "autovacuum_vacuum_scale_factor"
      value = "0.05" # more aggressive autovacuuming - 5% of table size, default is 20%
    }

    database_flags {
      name  = "autovacuum_vacuum_cost_limit"
      value = "2000" # higher cost limit to allow more work per autovacuum run, default is 200
    }

    database_flags {
      name  = "random_page_cost"
      value = "1.1" # PD_SSD; default 4.0 is HDD-era and biases the planner toward seq scans
    }

    database_flags {
      name  = "track_io_timing"
      value = "on" # required for meaningful EXPLAIN (BUFFERS) timings and pg_stat_statements I/O metrics
    }

    database_flags {
      name  = "maintenance_work_mem"
      value = "1048576" # 1GB in KB - speeds the post-upgrade REINDEX
    }

    database_flags {
      name  = "idle_in_transaction_session_timeout"
      value = "60000" # 60s - pool-starvation defense; complements the 4-hour oldest-transaction alert
    }

    deletion_protection_enabled = true
    disk_autoresize             = true
    disk_autoresize_limit       = 0
    disk_size                   = var.db_disk_size
    disk_type                   = "PD_SSD"
    edition                     = var.db_edition

    # The data cache is an ENTERPRISE_PLUS-only feature; setting it on any other
    # edition is rejected at apply time.
    dynamic "data_cache_config" {
      for_each = var.db_edition == "ENTERPRISE_PLUS" ? [1] : []
      content {
        data_cache_enabled = true
      }
    }

    ip_configuration {
      dynamic "authorized_networks" {
        for_each = var.db_authorized_networks
        content {
          name  = authorized_networks.value.name
          value = authorized_networks.value.value
        }
      }

      ipv4_enabled = true
    }

    location_preference {
      zone = var.zone
    }

    insights_config {
      query_insights_enabled = true
      # Defaults are 5/min and 1024 chars. The 1024 cap truncates our
      # CTE-heavy search queries (~2.5-3k chars) so they're hard to
      # locate in the Insights UI, and 5 plans/min is sampled across
      # the entire database so rare slow events almost never show up.
      # Both raised to the documented maximums; SIGHUP-applied (no
      # restart).
      query_plans_per_minute = 20
      query_string_length    = 4500
    }

    pricing_plan = "PER_USE"
    tier         = var.db_tier
  }
}

resource "google_sql_database" "convictional_production_db" {
  name            = var.db_name
  instance        = google_sql_database_instance.convictional.name
  deletion_policy = "ABANDON"
}

resource "google_sql_user" "eng_iam_group" {
  count           = var.engineering_group_email == null ? 0 : 1
  name            = var.engineering_group_email
  instance        = google_sql_database_instance.convictional.name
  type            = "CLOUD_IAM_GROUP"
  deletion_policy = "ABANDON"
}

resource "google_sql_user" "convictional_eng_write" {
  name            = trimsuffix(google_service_account.convictional_eng_write.email, ".gserviceaccount.com")
  instance        = google_sql_database_instance.convictional.name
  type            = "CLOUD_IAM_SERVICE_ACCOUNT"
  deletion_policy = "ABANDON"
}

resource "google_sql_user" "convictional_deploy" {
  name            = trimsuffix(google_service_account.convictional_deploy.email, ".gserviceaccount.com")
  instance        = google_sql_database_instance.convictional.name
  type            = "CLOUD_IAM_SERVICE_ACCOUNT"
  deletion_policy = "ABANDON"
}

resource "google_sql_user" "convictional_app" {
  name            = trimsuffix(google_service_account.convictional_app.email, ".gserviceaccount.com")
  instance        = google_sql_database_instance.convictional.name
  type            = "CLOUD_IAM_SERVICE_ACCOUNT"
  deletion_policy = "ABANDON"
}

resource "google_sql_user" "tofu_applier" {
  name            = trimsuffix(google_service_account.tofu_applier.email, ".gserviceaccount.com")
  instance        = google_sql_database_instance.convictional.name
  type            = "CLOUD_IAM_SERVICE_ACCOUNT"
  deletion_policy = "ABANDON"
}
