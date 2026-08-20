resource "google_compute_backend_bucket" "cdn" {
  name        = "${google_storage_bucket.assets.name}-backend"
  bucket_name = google_storage_bucket.assets.name
  enable_cdn  = true

  cdn_policy {
    cache_mode        = "CACHE_ALL_STATIC"
    client_ttl        = 3600
    default_ttl       = 3600
    max_ttl           = 3600
    negative_caching  = true
    serve_while_stale = 86400
  }
  compression_mode = "AUTOMATIC"
}

resource "google_compute_global_address" "cdn_ip" {
  name         = "${google_storage_bucket.assets.name}-cdn-ip"
  address_type = "EXTERNAL"
  ip_version   = "IPV4"
}

resource "google_compute_managed_ssl_certificate" "cdn" {
  name        = "${google_storage_bucket.assets.name}-cdn-cert"
  description = "SSL certificate for CDN subdomain"

  lifecycle {
    create_before_destroy = true
  }

  managed {
    domains = [
      "${var.cdn_subdomain}.${var.domain}.",
    ]
  }
}

resource "google_compute_url_map" "cdn" {
  name            = "${google_storage_bucket.assets.name}-cdn"
  default_service = google_compute_backend_bucket.cdn.id
}

resource "google_compute_url_map" "cdn_http_redirect" {
  name = "${google_storage_bucket.assets.name}-cdn-http-redirect"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_ssl_policy" "cdn" {
  name            = "${google_storage_bucket.assets.name}-cdn-ssl-policy"
  min_tls_version = "TLS_1_2"
  profile         = "RESTRICTED"
}

resource "google_compute_target_https_proxy" "cdn" {
  name             = "${google_storage_bucket.assets.name}-cdn-https-proxy"
  url_map          = google_compute_url_map.cdn.id
  ssl_certificates = [google_compute_managed_ssl_certificate.cdn.id]
  ssl_policy       = google_compute_ssl_policy.cdn.self_link
}

resource "google_compute_target_http_proxy" "cdn" {
  name    = "${google_storage_bucket.assets.name}-cdn-http-proxy"
  url_map = google_compute_url_map.cdn_http_redirect.id
}

resource "google_compute_global_forwarding_rule" "cdn_https" {
  name                  = "${google_storage_bucket.assets.name}-cdn-https"
  ip_address            = google_compute_global_address.cdn_ip.id
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "443"
  target                = google_compute_target_https_proxy.cdn.id
}

resource "google_compute_global_forwarding_rule" "cdn_http" {
  name                  = "${google_storage_bucket.assets.name}-cdn-http"
  ip_address            = google_compute_global_address.cdn_ip.id
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "80"
  target                = google_compute_target_http_proxy.cdn.id
}
