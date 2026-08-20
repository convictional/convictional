resource "google_cloud_run_v2_service" "convictional" {
  ingress      = "INGRESS_TRAFFIC_ALL"
  launch_stage = "GA"
  location     = var.region
  name         = "convictional"

  lifecycle {
    ignore_changes = [
      template,
      ingress,
      traffic,
      client
    ]
  }

  # Deploys a placeholder service to ensure the Cloud Run service is created
  # Needed to ensure networking resources are created
  template {
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/placeholder:latest"
      name  = "convictional-1"

      ports {
        container_port = 8080
        name           = "http1"
      }

      resources {
        cpu_idle = true

        limits = {
          cpu    = "1000m"
          memory = "2Gi"
        }

        startup_cpu_boost = true
      }

      startup_probe {
        failure_threshold     = 1
        initial_delay_seconds = 0
        period_seconds        = 240

        tcp_socket {
          port = 8080
        }

        timeout_seconds = 240
      }
    }

    max_instance_request_concurrency = 80

    scaling {
      max_instance_count = 100
      min_instance_count = 2
    }

    timeout = "60s"
  }
}

resource "google_cloud_run_v2_service" "convictional_jobs" {
  ingress      = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  launch_stage = "GA"
  location     = var.region
  name         = "convictional-jobs"

  lifecycle {
    ignore_changes = [
      template,
      ingress,
      traffic,
      client
    ]
  }

  # Deploys a placeholder service to ensure the Cloud Run service is created
  # Needed to ensure networking resources are created
  template {
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/placeholder:latest"
      name  = "convictional-jobs"

      ports {
        container_port = 8080
        name           = "http1"
      }

      resources {
        cpu_idle = true

        limits = {
          cpu    = "1000m"
          memory = "4Gi"
        }

        startup_cpu_boost = true
      }

      startup_probe {
        failure_threshold     = 1
        initial_delay_seconds = 0
        period_seconds        = 240

        tcp_socket {
          port = 8080
        }

        timeout_seconds = 240
      }
    }

    max_instance_request_concurrency = 80

    scaling {
      max_instance_count = 100
      min_instance_count = 1
    }

    timeout = "1800s"
  }
}

# Required IAM policy to open up app access to all users

data "google_iam_policy" "noauth" {
  binding {
    role = "roles/run.invoker"
    members = [
      "allUsers",
      "serviceAccount:${data.google_compute_default_service_account.default.email}",
      "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com",
    ]
  }
}

# IAM policy for authorized service accounts to invoke jobs service
data "google_iam_policy" "jobs_auth" {
  binding {
    role = "roles/run.invoker"
    members = [
      "serviceAccount:${google_service_account.convictional_background_jobs.email}",
    ]
  }
}

resource "google_cloud_run_service_iam_policy" "noauth" {
  location = google_cloud_run_v2_service.convictional.location
  project  = google_cloud_run_v2_service.convictional.project
  service  = google_cloud_run_v2_service.convictional.name

  policy_data = data.google_iam_policy.noauth.policy_data
}

resource "google_cloud_run_service_iam_policy" "jobs_auth" {
  location = google_cloud_run_v2_service.convictional_jobs.location
  project  = google_cloud_run_v2_service.convictional_jobs.project
  service  = google_cloud_run_v2_service.convictional_jobs.name

  policy_data = data.google_iam_policy.jobs_auth.policy_data
}

locals {
  deterministic_app_url = "https://${google_cloud_run_v2_service.convictional.name}-${data.google_project.project.number}.${google_cloud_run_v2_service.convictional.location}.run.app"
  jobs_service_url      = "https://${google_cloud_run_v2_service.convictional_jobs.name}-${data.google_project.project.number}.${google_cloud_run_v2_service.convictional_jobs.location}.run.app"
}
