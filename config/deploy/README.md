# Cloud Run service definitions

Knative service manifests for the two Cloud Run services the app runs as:

| File                  | Service             | Ingress            |
| --------------------- | ------------------- | ------------------ |
| `production.yml`      | `convictional`      | Load balancer only |
| `production_jobs.yml` | `convictional-jobs` | Internal only      |

They pair with the Terraform in `../infra`, which creates the services, the
database, the buckets, and the service accounts these manifests reference.
Terraform sets `ignore_changes` on the whole Cloud Run template, so applying a
manifest from here is what actually determines what runs.

## Templates, not literal config

Every deployment-specific value is a `${VARIABLE}` placeholder, so the same
manifest works for any project and domain. Render with `envsubst`:

```sh
cp deploy.env.example production.env     # then fill it in
set -a && . ./production.env && set +a
envsubst < production.yml > /tmp/convictional.yml
gcloud run services replace /tmp/convictional.yml --region "$GCP_REGION"
```

`deploy.env.example` documents every variable. `production.env` matches the
gitignored `.env.*` pattern, so it will not be committed. A second environment
is the same manifests rendered from a second env file — there is nothing
environment-specific left in the YAML.

`envsubst` renders unset variables as an empty string, which for most of these
is a silent misconfiguration rather than a visible failure. Fail loudly instead:

```sh
: "${GCP_PROJECT_ID:?}" "${GCP_PROJECT_NUMBER:?}" "${GCP_REGION:?}" \
  "${CONTAINER_IMAGE:?}" "${REVISION_NAME:?}" "${SERVING_REVISION_NAME:?}" \
  "${APP_DOMAIN:?}" "${CDN_DOMAIN:?}" "${GCS_BUCKET:?}" \
  "${EMAIL_FROM:?}" "${RESEARCH_EMAIL_FROM:?}" "${MAILGUN_DOMAIN:?}" \
  "${FEEDBACK_EMAIL:?}" "${SIGNUP_EMAIL:?}" "${NEW_USER_NOTIFICATION_EMAILS:?}"
```

The policy-page URLs, third-party account IDs, and native-app identifiers are
deliberately absent from that list — empty is a valid choice for each, and
`deploy.env.example` says what empty means.

## Deploying without a traffic gap

`REVISION_NAME` and `SERVING_REVISION_NAME` are separate so a revision can be
created and health-checked before traffic moves to it. A safe deploy renders
each manifest twice:

1. `REVISION_NAME` = the new revision, `SERVING_REVISION_NAME` = the revision
   currently serving. Apply. The new revision starts and must pass its startup
   probe; traffic is untouched. Read the current value from
   `gcloud run services describe convictional --region "$GCP_REGION" --format='value(status.traffic[0].revisionName)'`.
2. Run database migrations against the new image.
3. Both variables = the new revision. Apply again. Traffic moves.

Cloud Run rejects a revision whose startup probe never passes, so a broken
image fails at step 1 with the old revision still serving.

The startup budget is `failureThreshold × periodSeconds` = 180s, set
generously: cold start is slow and variable, and with `minScale` above 1 a
single instance exceeding the budget fails the whole revision's deploy.

## Secrets

Anything sensitive is a `secretKeyRef` pointing at Secret Manager, resolved by
Cloud Run at start. Create each secret named in the manifests before the first
deploy, and grant the app's service account `roles/secretmanager.secretAccessor`
— the Terraform already does that for `convictional-app`.

Three of them are blocklists (`BANNED_DOMAINS`, `BLOCKED_EMAILS`,
`BLOCKED_OAUTH_SUBS`) and one is `SUPERUSER_EMAILS`. They come from Secret
Manager rather than inline values specifically so no blocked identity or named
individual lands in git history. An absent secret means empty, which means no
blocking and no superuser — and with no superuser, the `/api` docs,
`/background_jobs`, and the organization system prompt stay locked.

## Settings worth reviewing before you deploy

Not deployment identity, so not templated, but unlikely to be what you want:

- `SIGNUPS_ENABLED` is `"false"` in `production.yml`. Self-serve account
  creation is off until you flip it.
- `minScale: "2"` holds two warm instances per service. Cheaper at `"0"`, at
  the cost of cold starts.
- `EMAIL_DELIVERY: mailgun` and `EMAIL_CLIENT: gmail` assume a Mailgun account
  and Google Workspace.
