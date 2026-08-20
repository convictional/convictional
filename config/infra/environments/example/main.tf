/*
  A complete, working environment for one deployment of Convictional.

  Copy this directory, replace every value in the locals block below, and see
  the README in the parent directory for the order of operations. Everything
  outside the locals block should work unmodified.
*/

locals {
  project_id = "your-gcp-project-id"
  region     = "us-central1"
  zone       = "us-central1-b"

  # The apex domain the app is served from. DNS for this domain, and for
  # www and the app subdomain, must point at module.app's static IP before
  # Google will issue the managed certificates.
  domain = "example.com"

  # owner/name of the GitHub repository that deploys this app, and the numeric
  # ID of that owner (https://api.github.com/users/<owner>). Workload Identity
  # Federation trusts this repository to impersonate the deploy accounts.
  github_repository = "your-org/convictional"
  github_owner_id   = "000000"

  # GCS bucket names are globally unique across all of GCP, so these need a
  # prefix nobody else has taken.
  uploads_bucket = "your-org-convictional-uploads"
  assets_bucket  = "your-org-convictional-assets"
}

module "app" {
  source = "../../modules/app"

  project_id          = local.project_id
  region              = local.region
  zone                = local.zone
  domain              = local.domain
  storage_bucket_name = local.uploads_bucket
  db_name             = "convictional_production"

  github_repository = local.github_repository
  github_owner_id   = local.github_owner_id

  # Sized down from the module defaults, which are tuned for production
  # traffic and cost roughly ten times as much. Raise these before you have
  # real users on the instance; tier and edition can be changed in place,
  # and the disk grows on its own but never shrinks.
  db_tier      = "db-custom-2-7680"
  db_edition   = "ENTERPRISE"
  db_disk_size = 50

  # Alerts are created either way, but they go nowhere until they have a
  # channel. Create the channels in the console (Monitoring → Alerting →
  # Notification channels), then look them up here by display name:
  #
  #   data "google_monitoring_notification_channel" "oncall" {
  #     display_name = "Engineering"
  #     type         = "email"
  #   }
  #
  # alert_notification_channels    = [data.google_monitoring_notification_channel.oncall.name]
  # critical_notification_channels = [data.google_monitoring_notification_channel.oncall.name]

  # A Google Group whose members get read-only database access via IAM auth,
  # and the individuals who may escalate to read/write. Both are optional.
  # engineering_group_email = "engineering@example.com"
  # eng_write_impersonators = ["user:you@example.com"]

  # Alternate hostnames that permanently redirect to the apex domain.
  canonical_redirect_hostnames = ["www.${local.domain}"]
}

module "cdn" {
  source = "../../modules/cdn"

  project_id          = local.project_id
  region              = local.region
  domain              = local.domain
  storage_bucket_name = local.assets_bucket
  cdn_subdomain       = "cdn"
}

output "app_ip_address" {
  value       = module.app.static_ip_address
  description = "Point the apex, www, and app-subdomain A records at this address."
}

output "cdn_ip_address" {
  value       = module.cdn.cdn_ip_address
  description = "Point the CDN subdomain's A record at this address."
}
