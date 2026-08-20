resource "google_compute_backend_service" "convictional_backend" {
  connection_draining_timeout_sec = 300
  load_balancing_scheme           = "EXTERNAL_MANAGED"
  locality_lb_policy              = "ROUND_ROBIN"
  compression_mode                = "AUTOMATIC"
  enable_cdn                      = true

  log_config {
    sample_rate = 0
  }

  lifecycle {
    ignore_changes = [
      log_config,
    ]
  }

  name             = "convictional-backend"
  port_name        = "http"
  protocol         = "HTTPS"
  security_policy  = google_compute_security_policy.convictional_production_app.id
  session_affinity = "NONE"
  timeout_sec      = 30

  backend {
    group = google_compute_region_network_endpoint_group.convictional_network_endpoint_group.id
  }
}

resource "google_compute_region_network_endpoint_group" "convictional_network_endpoint_group" {
  name                  = "convictional-network-endpoint-group"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.convictional.name
  }
}

resource "google_compute_target_http_proxy" "convictional_app_frontend_target_proxy" {
  name    = "convictional-app-frontend-target-proxy"
  url_map = google_compute_url_map.convictional_app_frontend_redirect.id
}

resource "google_compute_managed_ssl_certificate" "convictional_certificate" {
  name        = "convictional-ssl-certificate"
  description = "Certificate for the convictional app"

  lifecycle {
    create_before_destroy = true
  }

  managed {
    domains = [
      "${var.app_subdomain}.${var.domain}.",
    ]
  }
}

resource "google_compute_managed_ssl_certificate" "convictional_root_domain_certificate" {
  name        = "convictional-root-domain-certificate"
  description = "Certificate for the root domain and its www alias"

  lifecycle {
    create_before_destroy = true
  }

  managed {
    domains = [

      "${var.domain}.",
      "www.${var.domain}.",
    ]
  }
}

resource "google_compute_ssl_policy" "convictional_ssl_policy" {
  name            = "convictional-ssl-policy"
  min_tls_version = "TLS_1_2"
  profile         = "RESTRICTED"
}

resource "google_compute_target_https_proxy" "convictional_load_balancer_target_proxy" {
  name          = "convictional-load-balancer-target-proxy"
  quic_override = "NONE"
  ssl_certificates = [
    google_compute_managed_ssl_certificate.convictional_certificate.id,
    google_compute_managed_ssl_certificate.convictional_root_domain_certificate.id,
  ]
  url_map    = google_compute_url_map.convictional_load_balancer.id
  ssl_policy = google_compute_ssl_policy.convictional_ssl_policy.self_link
}

resource "google_compute_global_forwarding_rule" "convictional_app_frontend_forwarding_rule" {
  ip_address            = google_compute_global_address.convictional_static_ip_address.id
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  name                  = "convictional-app-frontend-forwarding-rule"
  port_range            = "80-80"
  target                = google_compute_target_http_proxy.convictional_app_frontend_target_proxy.id
}

resource "google_compute_global_forwarding_rule" "convictional_app_frontend" {
  ip_address            = google_compute_global_address.convictional_static_ip_address.id
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  name                  = "convictional-app-frontend"
  port_range            = "443-443"
  target                = google_compute_target_https_proxy.convictional_load_balancer_target_proxy.id
}


resource "google_compute_url_map" "convictional_load_balancer" {
  default_service = google_compute_backend_service.convictional_backend.id
  name            = "convictional-load-balancer"

  # Paths on the apex domain that belong to something other than this app —
  # a marketing site, a docs site. Only created when the deployment declares them.
  dynamic "host_rule" {
    for_each = length(var.path_redirects) > 0 ? [1] : []
    content {
      hosts        = [var.domain]
      path_matcher = "root-redirects"
    }
  }

  dynamic "path_matcher" {
    for_each = length(var.path_redirects) > 0 ? [1] : []
    content {
      name            = "root-redirects"
      default_service = google_compute_backend_service.convictional_backend.id

      dynamic "route_rules" {
        for_each = var.path_redirects
        content {
          priority = route_rules.value.priority

          match_rules {
            full_path_match = route_rules.value.full_path_match
            prefix_match    = route_rules.value.prefix_match
          }

          url_redirect {
            host_redirect          = route_rules.value.host_redirect
            path_redirect          = route_rules.value.path_redirect
            https_redirect         = route_rules.value.https_redirect
            redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
            strip_query            = false
          }
        }
      }
    }
  }

  # Alternate hostnames collapse onto the apex domain so there is one canonical
  # origin. One path matcher serves them all — the redirect target is the same.
  dynamic "host_rule" {
    for_each = length(var.canonical_redirect_hostnames) > 0 ? [1] : []
    content {
      hosts        = var.canonical_redirect_hostnames
      path_matcher = "canonical-redirect"
    }
  }

  dynamic "path_matcher" {
    for_each = length(var.canonical_redirect_hostnames) > 0 ? [1] : []
    content {
      name = "canonical-redirect"
      default_url_redirect {
        host_redirect          = var.domain
        redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
        strip_query            = false
        https_redirect         = false
      }
    }
  }
}

resource "google_compute_url_map" "convictional_app_frontend_redirect" {
  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }

  description = "Automatically generated HTTP to HTTPS redirect for the convictional-app-frontend forwarding rule"
  name        = "convictional-app-frontend-redirect"
}

resource "google_compute_global_address" "convictional_static_ip_address" {
  address_type = "EXTERNAL"
  ip_version   = "IPV4"
  name         = "convictional-static-ip-address"
}

resource "google_compute_security_policy" "convictional_production_app" {
  advanced_options_config {
    json_parsing = "DISABLED"
  }

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = false
    }
  }

  description = "Policy for public facing Convictional app"
  name        = "convictional-production-app"

  rule {
    action      = "deny(403)"
    description = "Default rule, higher priority overrides it"

    match {
      config {
        src_ip_ranges = ["*"]
      }

      versioned_expr = "SRC_IPS_V1"
    }

    priority = 2147483647
  }

  rule {
    action      = "throttle"
    description = "Throttle requests per IP address"
    priority    = 100

    match {
      config {
        src_ip_ranges = ["*"]
      }

      versioned_expr = "SRC_IPS_V1"
    }

    rate_limit_options {
      conform_action = "allow"

      exceed_action = "deny(429)"

      enforce_on_key = ""

      enforce_on_key_configs {
        enforce_on_key_type = "XFF_IP"
      }

      rate_limit_threshold {
        count        = 600
        interval_sec = 60
      }
    }
  }

  # convictional_session is the app's session cookie (config/settings.py). Matching on
  # it at the edge keeps logged-out root requests off the backend entirely.
  dynamic "rule" {
    for_each = var.unauthenticated_landing_url == null ? [] : [1]
    content {
      action      = "redirect"
      description = "Redirect unauthenticated users at root path to landing page"
      priority    = 1

      match {
        expr {
          expression = "request.path == '/' && (!has(request.headers['cookie']) || !request.headers['cookie'].matches('.*convictional_session=.*'))"
        }
      }

      redirect_options {
        target = var.unauthenticated_landing_url
        type   = "EXTERNAL_302"
      }
    }
  }

  type = "CLOUD_ARMOR"
}
