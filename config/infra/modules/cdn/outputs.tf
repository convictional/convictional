output "cdn_domain" {
  value       = "${var.cdn_subdomain}.${var.domain}"
  description = "The full CDN domain name"
}

output "cdn_ip_address" {
  value       = google_compute_global_address.cdn_ip.address
  description = "The CDN static IP address"
}

output "bucket_name" {
  value       = google_storage_bucket.assets.name
  description = "The GCS bucket name for assets"
}
