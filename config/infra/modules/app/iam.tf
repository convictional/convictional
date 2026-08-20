/*
  Service Accounts
*/

data "google_compute_default_service_account" "default" {}

resource "google_service_account" "convictional_background_jobs" {
  account_id   = "convictional-background-jobs"
  description  = "Runs Cloud Tasks background jobs from the Convictional app"
  display_name = "Convictional Background Jobs"
}

resource "google_service_account" "convictional_app" {
  account_id   = "convictional-app"
  description  = "Service account for the Convictional app"
  display_name = "Convictional App"
}

resource "google_service_account" "convictional_deploy" {
  account_id   = "convictional-deploy"
  description  = "Account to deploy the convictional app to production"
  display_name = "Convictional deploy"
}

resource "google_service_account" "convictional_eng_write" {
  account_id   = "convictional-eng-write"
  description  = "Write access to the Convictional database for engineering"
  display_name = "Convictional Eng Write"
}

resource "google_service_account" "tofu_planner" {
  account_id   = "tofu-planner"
  description  = "Service account for running Tofu Plans"
  display_name = "Tofu Planner"
}

resource "google_service_account" "tofu_applier" {
  account_id   = "tofu-applier"
  description  = "Service account for applying Tofu Plans"
  display_name = "Tofu Applier"
}

/*
  IAM Roles
*/

resource "google_project_iam_member" "compute_default_roles" {
  project = var.project_id
  member  = data.google_compute_default_service_account.default.member
  for_each = toset([
    "roles/secretmanager.secretAccessor",
    "roles/iam.serviceAccountTokenCreator"
  ])
  role = each.key
}

resource "google_project_iam_member" "convictional_background_jobs_roles" {
  project = var.project_id
  member  = google_service_account.convictional_background_jobs.member
  for_each = toset([
    "roles/run.invoker"
  ])
  role = each.key
}

resource "google_project_iam_member" "convictional_app_roles" {
  project = var.project_id
  member  = google_service_account.convictional_app.member
  for_each = toset([
    "roles/secretmanager.secretAccessor",
    "roles/iam.serviceAccountTokenCreator",
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser",
    "roles/cloudtasks.admin",
    "roles/iam.serviceAccountUser",
    "roles/storage.admin",
    "roles/run.invoker",
    "roles/pubsub.subscriber"
  ])
  role = each.key
}

resource "google_project_iam_member" "convictional_deploy_roles" {
  project = var.project_id
  member  = google_service_account.convictional_deploy.member
  for_each = toset([
    "roles/artifactregistry.writer",
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser",
    "roles/run.developer",
    "roles/iam.serviceAccountUser",
    "roles/storage.objectUser"
  ])
  role = each.key
}

resource "google_project_iam_member" "convictional_eng_roles" {
  project = var.project_id
  member  = "group:${var.engineering_group_email}"
  for_each = var.engineering_group_email == null ? toset([]) : toset([
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser"
  ])
  role = each.key
}

resource "google_project_iam_member" "convictional_eng_write_roles" {
  project = var.project_id
  member  = google_service_account.convictional_eng_write.member
  for_each = toset([
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser"
  ])
  role = each.key
}

resource "google_project_iam_member" "tofu_planner_roles" {
  project = var.project_id
  member  = google_service_account.tofu_planner.member
  for_each = toset([
    "roles/viewer",
    "roles/storage.objectUser",
    "roles/pubsub.admin",
  ])
  role = each.key
}

# Owner, because this module grants IAM roles, and granting a role requires
# holding it. Narrowing the applier means enumerating every role the module
# hands out and re-editing that list whenever the module changes — the reason
# it is owner rather than an oversight.
#
# What keeps it from being a standing risk is that nothing holds this account's
# keys: it is reachable only by impersonation through the Workload Identity
# Federation pool below, whose attribute_condition admits tokens from
# var.github_owner_id's repositories alone. Copying this module means inheriting
# that tradeoff, so make sure the pool is scoped to an owner you control.
resource "google_project_iam_member" "tofu_applier_roles" {
  project = var.project_id
  member  = google_service_account.tofu_applier.member
  for_each = toset([
    "roles/owner",
    "roles/pubsub.admin",
  ])
  role = each.key
}


# Users who can impersonate the convictional_eng_write service account to write to the database
resource "google_service_account_iam_binding" "convictional_eng_impersonators" {
  count              = length(var.eng_write_impersonators) > 0 ? 1 : 0
  service_account_id = google_service_account.convictional_eng_write.name
  role               = "roles/iam.serviceAccountTokenCreator"
  members            = var.eng_write_impersonators
}

/*
  Workload Identity Federation
*/

module "oidc" {
  source  = "terraform-google-modules/github-actions-runners/google//modules/gh-oidc"
  version = "~> 4.0"

  project_id          = var.project_id
  pool_id             = "convictional-wif-pool"
  provider_id         = "gh-identity-provider"
  attribute_condition = "assertion.repository_owner_id=='${var.github_owner_id}'"
  sa_mapping          = {}
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.aud"        = "assertion.aud"
    "attribute.repository" = "assertion.repository"
    "attribute.event_name" = "assertion.event_name"
  }
}

resource "google_service_account_iam_member" "convictional_deploy_wif" {
  service_account_id = google_service_account.convictional_deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${module.oidc.pool_name}/subject/repo:${var.github_repository}:ref:refs/heads/main"
}

resource "google_service_account_iam_member" "convictional_deploy_wif_pr" {
  service_account_id = google_service_account.convictional_deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${module.oidc.pool_name}/subject/repo:${var.github_repository}:pull_request"
}

resource "google_service_account_iam_member" "convictional_deploy_wif_merge_queue" {
  service_account_id = google_service_account.convictional_deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${module.oidc.pool_name}/attribute.event_name/merge_group"
}

resource "google_service_account_iam_member" "tofu_planner_wif" {
  service_account_id = google_service_account.tofu_planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${module.oidc.pool_name}/subject/repo:${var.github_repository}:pull_request"
}

resource "google_service_account_iam_member" "tofu_applier_wif" {
  service_account_id = google_service_account.tofu_applier.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${module.oidc.pool_name}/subject/repo:${var.github_repository}:ref:refs/heads/main"
}
