variable "project_id" {
  type        = string
  description = "The GCP project ID"
}

variable "region" {
  type        = string
  description = "The GCP region"
}

variable "storage_bucket_name" {
  type        = string
  description = "The GCS bucket name for assets"
}

variable "domain" {
  type        = string
  description = "The root domain name (e.g. example.com)"
}

variable "cdn_subdomain" {
  type        = string
  default     = "cdn"
  description = "The subdomain for CDN assets (e.g. 'cdn' for cdn.example.com)"
}

variable "additional_cors_origins" {
  type        = list(string)
  default     = []
  description = "Extra origins allowed to read from the assets bucket, in addition to the apex domain. Include the scheme."
}
