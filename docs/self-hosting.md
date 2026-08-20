# Self-hosting

What it takes to run your own deployment: the one service you must provide, the settings that identify your
instance, and the container that serves it. If you only want the app running on your laptop, start with the
[README](../README.md) instead.

---

## What you need

**Postgres 18 with [pgvector](https://github.com/pgvector/pgvector), and nothing else.** There's no Redis,
no message broker, and no separate search service. The database carries the cache, the job queue, full-text
search, and vector search, which keeps a self-hosted deployment down to two moving parts: this app and
Postgres.

You'll also want API keys for the two model providers:

| Setting | Used for | Without it |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | All inference | AI features fail |
| `OPENAI_API_KEY` | Embeddings | Semantic search degrades to text-only |

Everything beyond that is optional. Each integration is feature-gated on its own credentials and stays
hidden until you set them — see [integrations](integrations.md).

## Settings

Configuration is entirely environment-driven. `config/settings.py` is the single authoritative list; these
are the ones a deployment has to think about.

### Identity

| Setting | Notes |
| --- | --- |
| `SECRET_KEY` | Signs sessions. Generate one with `make secret`. **Change this.** |
| `BASE_URL` | The public URL of your instance. Drives OAuth redirects, email links, and webhooks. |
| `ALLOWED_HOSTS` | Comma-separated hostnames to serve. Also derives the CORS origins. |
| `PRODUCT_NAME` | The name users see in page titles and outbound mail. Defaults to `Convictional`. |
| `ENV` | Set to something other than a local environment so production behaviour applies. |

Startup deliberately fails when a non-local `BASE_URL` is paired with missing sender identity —
`EMAIL_FROM`, plus `MAILGUN_DOMAIN` when Mailgun is the delivery mechanism, plus `FEEDBACK_EMAIL` when push
is enabled. None of those have defaults, because a default would make your deployment send as somebody
else's domain. The error names exactly what's unset.

### Access

| Setting | Notes |
| --- | --- |
| `SUPERUSER_EMAILS` | Comma-separated addresses granted superuser. Empty means no superuser exists — the safe default. |
| `SIGNUPS_ENABLED` | Self-serve account creation. An account is created as a side effect of a first successful OAuth login, so this is the kill-switch for that path. Existing users and invitees are unaffected. |
| `BANNED_DOMAINS`, `BLOCKED_EMAILS`, `BLOCKED_OAUTH_SUBS` | Signup blocklists, comma-separated. |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | How users sign in. Configure at least one identity provider, or nobody can get in. |
| `ENABLE_FAKE_AUTH` | Lists seeded users on the sign-in screen and signs you in as one, with no password. **Development only — never enable this on a reachable deployment.** |

### Services

| Setting | Default | Notes |
| --- | --- | --- |
| `POSTGRES_URL` | local | `asyncpg://user:password@host:5432/database`. `POSTGRES_JSON` configures a connector-based engine instead. |
| `CACHE_STORE` | `null` | Set to `postgres` for a real cache. |
| `JOB_RUNNER` | `asyncio` | `asyncio` runs jobs in-process, which is fine for a single instance. `cloud_tasks` hands them to Google Cloud Tasks. |
| `GCS_BUCKET` | unset | Unset stores uploads on local disk under `tmp/storage/{ENV}`. Set it to use Google Cloud Storage — which you'll want for more than one instance, since local disk isn't shared. |
| `EMAIL_DELIVERY` | `development` | `mailgun` to actually send. |
| `SENTRY_DSN` | unset | Backend and frontend error reporting. |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | unset | Web push. Generate a keypair per deployment; never reuse the development pair. |

### Policy links

`TERMS_OF_SERVICE_URL`, `PRIVACY_POLICY_URL`, and `SECURITY_POLICY_URL` are linked from the sign-in screen
and served by the `/policies/*` redirects. Unset means you've published no such page: the link is omitted
and the redirect returns 404, rather than sending your users somewhere that isn't yours.
`MARKETING_SITE_URL` and `FEEDBACK_EMAIL` are similar operator-supplied pointers.

## Docker

The `Dockerfile` builds a multi-stage image on `python:3.13-slim` and serves the app with gunicorn via
`docker-entrypoint.sh`.

```bash
docker build -t convictional .

docker run -p 8000:8080 \
  -e APP_PORT=8080 \
  -e POSTGRES_URL=asyncpg://convictional:@host.docker.internal:5432/convictional_development \
  -e WORKER_COUNT=1 \
  --name convictional-dev convictional
```

That's the shape of a real run too — supply the settings above as environment variables. Migrations are not
run by the entrypoint; apply them with `make db_upgrade` against your database before rolling out new code.
See [database](database.md) for why that ordering matters.

## Assets

`make assets` builds the frontend bundle with Vite into `static/build`. The Docker build does this for you.
To serve a prebuilt bundle without Vite or hot reload — useful for reproducing a production asset problem
locally — use `make server_static`.

`ASSET_HOST` serves static assets from a CDN, and `ASSET_BUILDING_ENABLED` controls whether the app expects
a live Vite server.

## Reference deployment

The deployment this app was built for runs on Google Cloud Run with Cloud SQL, Cloud Tasks, and Cloud
Storage. That configuration is checked in and may be a useful starting point, though none of it is
required:

- `config/infra/` — OpenTofu/Terraform modules that provision the whole environment: Cloud SQL, both Cloud
  Run services, the buckets, queues, schedules, load balancer, and alerting. Copy `environments/example`,
  replace the values in its `locals` block, then drive it with `make infra_plan INFRA_ENV=<your-env>` and
  `make infra_apply INFRA_ENV=<your-env>`. Its [README](../config/infra/README.md) covers the full
  sequence, including database bootstrap and the DNS records the certificates wait on.
- `config/deploy/` — the Cloud Run service manifests, as `envsubst` templates. Copy `deploy.env.example`,
  fill it in, render, and apply. Its [README](../config/deploy/README.md) documents every variable and the
  two-pass deploy that health-checks a new revision before traffic moves to it.

No deploy pipeline ships with the repo. The workflows that drove this deployment were tied to one GCP
project, so they've been removed; the two READMEs give you the commands, and wiring them into CI is yours.

A plain container against a managed Postgres works just as well.
