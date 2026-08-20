output "wif_pool_name" {
  value       = module.oidc.pool_name
  description = "Workload Identity Federation pool, for granting additional repositories permission to impersonate service accounts in this project"
}

output "static_ip_address" {
  value       = google_compute_global_address.convictional_static_ip_address.address
  description = "The load balancer's static IP. DNS must point here before the managed certificates can be issued."
}

output "database_instance_name" {
  value       = google_sql_database_instance.convictional.name
  description = "Cloud SQL instance name, for cloud-sql-proxy connection strings"
}
