# Local integration setup

Third-party integrations are all optional and feature-gated — each stays hidden until its credentials are
set, so you only need to configure the one you're working on. This is how to get each one running against a
local server.

---

## A public HTTPS URL

Several integrations can't talk to `localhost`. Google OAuth's redirect, Microsoft OAuth (its callback is
HTTPS-only), Gmail Pub/Sub push, Recall.ai webhooks, and Cloud Tasks callbacks all need a public HTTPS URL
that reaches your machine. A tunnel with a stable hostname is how you develop against them.

[ngrok](https://ngrok.com) is what the Makefile targets assume. Set a reserved domain in `.env.secrets`:

```
NGROK_HOST=example.ngrok.dev
```

Then `make server_ngrok` serves your local app at `https://$NGROK_HOST`. It expects a paid ngrok plan — a
reserved domain, an internal endpoint for Vite, and a traffic policy file. `make server_ngrok_static` needs
only the reserved domain, at the cost of no hot reload. Any tunnel that gives you a stable hostname works
just as well; you'd point `BASE_URL` at it yourself.

When you're tunnelling, **access the app through the tunnel URL**, not `localhost`. OAuth callbacks land on
the tunnel, and a session started on `localhost` won't match.

## Google OAuth

Google OAuth is how signing in works in a deployed environment. Create OAuth credentials in your own Google
Cloud project ([APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)), add your
tunnel's `/auth/google` path as an authorized redirect URI, and set:

```
GOOGLE_OAUTH_CLIENT_ID=your-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
```

For day-to-day local work you don't need any of this: `ENABLE_FAKE_AUTH` lists the seeded users on the
sign-in screen and lets you click one to sign in. Configure real OAuth only when you're working on
authentication itself, or on Gmail and Calendar sync.

### Gmail and Calendar

Mail and calendar sync run on the same Google credentials. `EMAIL_CLIENT=gmail` switches the mail client
from the fake one to Gmail. `ENABLE_GMAIL_WATCH=True` subscribes to Gmail push events — if you turn it on,
run `make script ARGS="scripts/reset_gmail_integration.py --yes"` before you finish for the day, or you'll
be greeted by a flood of queued events next time you start the server.

## Microsoft OAuth

For Microsoft SSO, register an application in the [Entra portal](https://entra.microsoft.com/) (App
registrations → New registration), then create a client secret under **Certificates & secrets**. The secret
value is shown only once at creation — copy it immediately.

```
MICROSOFT_OAUTH_CLIENT_ID=your-client-id
MICROSOFT_OAUTH_CLIENT_SECRET=your-client-secret
```

Add your tunnel's `/auth/microsoft` path as a Redirect URI. Microsoft requires HTTPS for the callback, so
this one has no localhost path at all.

## Recall.ai

Recall.ai supplies the meeting bots that join calls and produce transcripts. You'll need your own Recall.ai
account and access to its [webhook dashboard](https://api.recall.ai/dashboard/webhooks/) to point webhooks
at your tunnel.

1. Configure OAuth and a tunnel, as above.
2. Set the forwarding URL for webhooks in the Recall dashboard.
3. In `.env.secrets`:

   ```
   RECALL_AI_API_KEY=your-api-key
   RECALL_AI_WEBHOOK_SIGNING_SECRET=your-signing-secret
   ```

4. Set `BASE_URL=https://example.ngrok.dev` for your environment.
5. Run `make server_ngrok`.

When re-recording Recall cassettes or writing new tests, unset `RECALL_AI_WEBHOOK_SIGNING_SECRET` to
disable webhook validation, disable OAuth, and follow the `NOTE` comments in the test module you're working
in — some need a valid token supplied by hand.

## Background jobs on Cloud Tasks

Jobs run in-process by default (`JOB_RUNNER=asyncio`), which is what you want locally. To exercise the
[Google Cloud Tasks](https://cloud.google.com/tasks) path instead, the queue has to be able to reach your
app, so this needs a tunnel too.

1. Authenticate to your Google Cloud project: `gcloud auth application-default login`.
2. Set these for your environment, pointing at your own project and queue:

   ```
   JOB_RUNNER=cloud_tasks
   BASE_URL=https://example.ngrok.dev
   GCP_PROJECT=your-project
   GCP_LOCATION=us-central1
   CLOUD_TASKS_SERVICE_ACCOUNT=your-service-account@your-project.iam.gserviceaccount.com
   ```

3. Run `make server_ngrok`, trigger the job, and watch it in the Cloud Tasks console.

Don't commit these — they belong in `.env.secrets` or your shell, not in the committed `.env.development`.

## Everything else

| Integration | Settings | Notes |
| --- | --- | --- |
| Slack | `SLACK_OAUTH_CLIENT_ID`, `SLACK_OAUTH_CLIENT_SECRET` | |
| Notion | Configured per-workspace through the app | |
| Mailgun | `MAILGUN_DOMAIN`, `MAILGUN_API_KEY`, `MAILGUN_WEBHOOK_SIGNING_KEY`, `EMAIL_FROM` | Set `EMAIL_DELIVERY=mailgun` to send for real. The default, `development`, opens outbound mail in your browser and drops it into the recipient's in-app inbox; `fake` captures it for tests |
| Klipy | `KLIPY_API_KEY` | GIF search in the composer |
| Sentry | `SENTRY_DSN` | Backend and frontend error reporting |

See `config/settings.py` for the authoritative list, and [self-hosting](self-hosting.md) for what a
deployment needs.
