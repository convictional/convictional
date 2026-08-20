# Convictional Infrastructure

OpenTofu (or Terraform) definitions for running Convictional on Google Cloud. Applying
them gives you the database, networking, storage, queues, schedules, permissions,
and alerting the app expects, with a placeholder container on Cloud Run that your
deploy pipeline then replaces.

## What gets created

The `app` module provisions:

- **Cloud Run** — a public `convictional` service and an internal `convictional-jobs` service
- **Cloud SQL** — a Postgres instance with `pgvector` and `pg_trgm`, IAM database
  authentication, and daily backups with point-in-time recovery
- **Cloud Storage** — a private bucket for user uploads
- **Cloud Tasks** — the queues the app dispatches background work to
- **Cloud Scheduler** — the recurring jobs, each calling an endpoint on `convictional-jobs`
- **Pub/Sub** — the topic and push subscription behind Gmail webhook delivery
- **Load balancing** — a global HTTPS load balancer with managed certificates,
  Cloud Armor rate limiting, and CDN caching in front of Cloud Run
- **IAM** — service accounts for the app, background jobs, deploys, and Terraform
  itself, plus Workload Identity Federation so GitHub Actions can deploy without
  long-lived keys
- **Monitoring** — an uptime check and alert policies for queue depth, database
  health, backup failures, and worker timeouts

The `cdn` module provisions a public bucket for static assets, fronted by its own
load balancer and CDN on a subdomain.

Both are parameterized; nothing about them is specific to any one deployment.
`environments/example` is a complete, working configuration to copy.

## Cost

The module defaults are sized for production traffic, and the database dominates
the bill — a `db-perf-optimized-N-4` ENTERPRISE_PLUS instance runs into four
figures a month. `environments/example` overrides `db_tier`, `db_edition`, and
`db_disk_size` down to something reasonable to start with. The Cloud Run services
also hold warm instances (`min_instance_count`), which you can drop to zero for a
non-production deployment once your pipeline is managing the service template.

## Standing up a new environment

You will need: a GCP project with billing enabled, a domain you control, a GCS
bucket for Terraform state, and the `gcloud` and `tofu` CLIs.

1. Copy `environments/example` to a new directory and replace every value in its
   `locals` block.
2. `tofu init -backend-config="bucket=your-state-bucket" -backend-config="prefix=convictional-production"`
3. `tofu plan`, then `tofu apply`. Budget around 15 minutes — Cloud SQL and the
   managed certificates are the slow parts.
4. Point DNS at the addresses in the `app_ip_address` and `cdn_ip_address`
   outputs: A records for the apex domain, `www`, your app subdomain, and the CDN
   subdomain. Certificates stay in `PROVISIONING` until these resolve, and can
   take up to an hour afterward.

At this point the infrastructure exists and Cloud Run serves a placeholder until
your pipeline pushes a real revision.

## Initializing the database

Terraform creates the instance, the database, and the IAM users, but it cannot
grant privileges inside Postgres — that has to happen over a Postgres connection.

1. In the console, find the new Cloud SQL instance and set a password on the
   `postgres` user.
2. Proxy to the instance:
   `cloud-sql-proxy --port 6000 <project-id>:<region>:convictional`
3. Edit `bootstrap_cloud_sql.sql`, replacing the placeholders at the top with your
   project ID, database name, and engineering group.
4. Run it as `postgres` against the new database:
   `psql -h localhost -p 6000 -U postgres -d convictional_production -f bootstrap_cloud_sql.sql`
5. Clear the `postgres` password. Everything else authenticates through IAM.

The app then connects as `convictional-app@<project-id>.iam` with no password, and
`make db_upgrade` from a deploy job creates the schema.

## Deploying with GitHub Actions

`github_repository` and `github_owner_id` configure Workload Identity Federation:
the OIDC provider only accepts tokens minted for repositories under that owner,
and only the named repository can impersonate the `convictional-deploy`, `tofu-planner`,
and `tofu-applier` service accounts. Point your workflow at the pool with
`google-github-actions/auth` and no key material is involved.

## Notes

- Cloud SQL carries both `prevent_destroy` in Terraform and
  `deletion_protection_enabled` in GCP. Removing the instance takes deliberately
  more than one step.
- The Cloud Run services set `ignore_changes` on their whole template, so your
  deploy pipeline owns the image, environment, and scaling. Terraform only makes
  sure the service exists for the load balancer to attach to.
- Alert policies are created whether or not you supply notification channels, so
  they will fire silently until `alert_notification_channels` is set. Channels are
  not created here because their delivery settings are usually managed elsewhere;
  look them up with the `google_monitoring_notification_channel` data source.
