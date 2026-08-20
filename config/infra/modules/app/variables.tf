variable "project_id" {
  type        = string
  description = "The GCP project ID"
}

variable "region" {
  type        = string
  description = "The GCP region"
}

variable "zone" {
  type        = string
  description = "The GCP zone. Must be inside var.region; sets the Cloud SQL instance's preferred zone."
}

variable "storage_bucket_name" {
  type        = string
  description = "The GCS bucket name for user-uploaded files. Bucket names are globally unique across all of GCP."
}

variable "domain" {
  type        = string
  description = "The apex domain the app is served from, without scheme (e.g. example.com)"
}

variable "db_name" {
  type        = string
  description = "The Postgres database name"
}

variable "app_subdomain" {
  type        = string
  default     = "convictional"
  description = "Subdomain that also resolves to the app. A managed certificate is issued for it in addition to the apex and www, and it is the host the uptime check probes."
}

/*
  GitHub Actions deployment
*/

variable "github_repository" {
  type        = string
  description = "The owner/name of the GitHub repository that deploys this app. Workload Identity Federation grants it permission to impersonate the deploy and tofu service accounts."
}

variable "github_owner_id" {
  type        = string
  description = "Numeric GitHub account ID of the repository owner. The OIDC provider only accepts tokens minted for repositories under this owner, so a fork cannot assume the deploy identity. Find it at https://api.github.com/users/<owner>."
}

/*
  Human and machine database access
*/

variable "engineering_group_email" {
  type        = string
  default     = null
  description = "Google Group granted read-only Cloud SQL IAM access (e.g. engineering@example.com). Leave null to skip creating the group grant."
}

variable "eng_write_impersonators" {
  type        = list(string)
  default     = []
  description = "IAM principals allowed to impersonate the read/write database service account, in `user:` or `group:` form. Every impersonation fires the 'Notify on Prod RW Login' alert."
}

/*
  Monitoring
*/

variable "alert_notification_channels" {
  type        = list(string)
  default     = []
  description = "Notification channel IDs for routine alerts. Channels are not created here because their delivery settings (email, SMS, mobile) are usually managed outside Terraform; look them up with the google_monitoring_notification_channel data source and pass the names in."
}

variable "critical_notification_channels" {
  type        = list(string)
  default     = []
  description = "Notification channel IDs for the uptime-failure alert, which should reach someone out of hours."
}

/*
  Load balancer routing
*/

variable "path_redirects" {
  type = list(object({
    priority        = number
    full_path_match = optional(string)
    prefix_match    = optional(string)
    host_redirect   = string
    path_redirect   = optional(string)
    https_redirect  = optional(bool)
  }))
  default     = []
  description = "Permanent redirects applied to requests on the apex domain, for paths served by something other than this app (a marketing site, a docs site). Set exactly one of full_path_match or prefix_match per entry; omit path_redirect to preserve the incoming path."

  validation {
    condition     = alltrue([for r in var.path_redirects : (r.full_path_match == null) != (r.prefix_match == null)])
    error_message = "Each path_redirect must set exactly one of full_path_match or prefix_match."
  }
}

variable "canonical_redirect_hostnames" {
  type        = list(string)
  default     = []
  description = "Hostnames that permanently redirect to the apex domain, e.g. www.example.com. They must resolve to the app's static IP and be covered by a certificate to redirect over HTTPS."
}

variable "unauthenticated_landing_url" {
  type        = string
  default     = null
  description = "Where to send logged-out visitors who request the root path, for deployments that front the app with a separate marketing site. Enforced by Cloud Armor ahead of the backend. Leave null to serve the app's own login page."
}

variable "additional_cors_origins" {
  type        = list(string)
  default     = []
  description = "Extra origins allowed to read from the uploads bucket, in addition to the apex domain. Include the scheme."
}

/*
  Database sizing
*/

variable "db_tier" {
  type        = string
  default     = "db-perf-optimized-N-4"
  description = "Cloud SQL machine type. The default is sized for production traffic and costs accordingly; db-custom-2-7680 on the ENTERPRISE edition is a reasonable starting point."
}

variable "db_edition" {
  type        = string
  default     = "ENTERPRISE_PLUS"
  description = "Cloud SQL edition. ENTERPRISE is cheaper; the data cache is only provisioned on ENTERPRISE_PLUS."
}

variable "db_disk_size" {
  type        = number
  default     = 250
  description = "Initial disk size in GB. The disk autoresizes upward and never shrinks, so this is a floor rather than a limit."
}

variable "db_backup_location" {
  type        = string
  default     = null
  description = "Where automated backups are stored — a multi-region such as \"us\" or \"eu\", or a specific region. Null lets Cloud SQL pick the multi-region containing the instance, which keeps backups in the same jurisdiction as the data. Set it explicitly where residency has to be provable."
}

variable "db_authorized_networks" {
  type = list(object({
    name  = string
    value = string
  }))
  default     = []
  description = "CIDR ranges allowed to reach the database over its public IP, for services that cannot use the Cloud SQL connector. The app itself connects via IAM auth and does not need an entry."
}
