resource "google_cloud_tasks_queue" "convictional_ui" {
  name     = "convictional-ui"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 1000
    max_dispatches_per_second = 500
  }

  retry_config {
    max_attempts  = 100
    max_backoff   = "3600s"
    max_doublings = 8 # 5s, 10s, 20s, 40s, 80s, 160s, 320s, 640s, 1280s, 3600s, 3600s...
    min_backoff   = "5s"
  }
}

resource "google_cloud_tasks_queue" "convictional_email" {
  name     = "convictional-email"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 1000
    max_dispatches_per_second = 500
  }

  retry_config {
    max_attempts  = 100
    max_backoff   = "3600s"
    max_doublings = 8
    min_backoff   = "5s"
  }
}

resource "google_cloud_tasks_queue" "convictional_push" {
  name     = "convictional-push"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 1000
    max_dispatches_per_second = 500
  }

  retry_config {
    max_attempts  = 100
    max_backoff   = "3600s"
    max_doublings = 8
    min_backoff   = "5s"
  }
}

resource "google_cloud_tasks_queue" "convictional_indexing" {
  name     = "convictional-indexing"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 100
    max_dispatches_per_second = 50
  }

  retry_config {
    max_attempts  = 100
    max_backoff   = "3600s"
    max_doublings = 8
    min_backoff   = "5s"
  }
}

resource "google_cloud_tasks_queue" "convictional_miscellaneous" {
  name     = "convictional-miscellaneous"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 500
    max_dispatches_per_second = 250
  }

  retry_config {
    max_attempts  = 100
    max_backoff   = "3600s"
    max_doublings = 8
    min_backoff   = "5s"
  }
}


resource "google_cloud_tasks_queue" "convictional_onboarding_sync" {
  name     = "convictional-onboarding-sync"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 100
    max_dispatches_per_second = 50
  }

  retry_config {
    max_attempts  = 100
    max_backoff   = "3600s"
    max_doublings = 8
    min_backoff   = "5s"
  }
}


resource "google_cloud_tasks_queue" "convictional_maintenance" {
  name     = "convictional-maintenance"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 100
    max_dispatches_per_second = 50
  }

  retry_config {
    max_attempts  = 100
    max_backoff   = "3600s"
    max_doublings = 8
    min_backoff   = "5s"
  }
}
