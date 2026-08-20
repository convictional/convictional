import copy
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, HttpUrl, SecretStr, field_serializer, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from tortoise.backends.base.config_generator import expand_db_url

current_env = (os.environ.get("ENV") or "development").lower()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CHECKOUT_ROOT = _PROJECT_ROOT.parent.parent
_LOCAL_POSTGRES_URL = f"asyncpg://convictional:@localhost:5432/convictional_{current_env}"

SLACK_INSTALL_USER_SCOPES = (
    "identify",
    "search:read",
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "users:read",
    "team:read",
    "users:read.email",
)

DEFAULT_APP_PORT = 8000
DEFAULT_VITE_PORT = 5173
DEFAULT_HOST = "localhost"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
PORT_OFFSET_RANGE = 100

DEV_COLORS = {
    "red": "#ef4444",
    "orange": "#f97316",
    "yellow": "#eab308",
    "green": "#22c55e",
    "blue": "#3b82f6",
    "purple": "#a855f7",
    "pink": "#ec4899",
    "cyan": "#06b6d4",
    "teal": "#14b8a6",
}


def _compute_port_offset() -> int:
    checkout_id = _checkout_identifier()
    return (sum(ord(c) for c in checkout_id) % PORT_OFFSET_RANGE) + 1


def _default_app_port() -> int:
    if port := os.environ.get("PORT"):
        return int(port)
    if port := os.environ.get("APP_PORT"):
        return int(port)
    return DEFAULT_APP_PORT + _compute_port_offset()


def _default_vite_port() -> int:
    return DEFAULT_VITE_PORT + _compute_port_offset()


def _default_base_url() -> HttpUrl:
    return HttpUrl(f"http://{DEFAULT_HOST}:{_default_app_port()}")


def _default_vite_url() -> HttpUrl:
    return HttpUrl(f"http://{DEFAULT_HOST}:{_default_vite_port()}")


def _checkout_identifier() -> str:
    sanitized = re.sub(r"[^a-z0-9]", "_", _CHECKOUT_ROOT.name.lower()).strip("_")
    return sanitized[:30]


class JobRunner(StrEnum):
    ASYNCIO = "asyncio"
    INLINE = "inline"
    CLOUD_TASKS = "cloud_tasks"


class StorageService(StrEnum):
    LOCAL = "local"
    GCS = "gcs"


class CacheStore(StrEnum):
    NULL = "null"
    POSTGRES = "postgres"


class EmbeddingBackend(StrEnum):
    OPENAI = "openai"
    CACHED_OPENAI = "cached_openai"
    # FAKE returns deterministic in-process vectors so tests that only index
    # content as a side effect don't record OpenAI embedding calls.
    FAKE = "fake"


class EmailDelivery(StrEnum):
    FAKE = "fake"
    DEVELOPMENT = "development"
    MAILGUN = "mailgun"


class EmailClient(StrEnum):
    FAKE = "fake"
    GMAIL = "gmail"


class PushDelivery(StrEnum):
    # FAKE captures sends into an in-process buffer for tests; NETWORK runs the
    # real per-protocol dispatcher (pywebpush for web push, Expo Push for APNs).
    FAKE = "fake"
    NETWORK = "network"


class GmailAPIClient(StrEnum):
    PRODUCTION = "production"
    MOCK = "mock"


@dataclass
class DatabaseConnectionConfig:
    url: str
    json_override: str = ""
    db_suffix: str = ""
    worker_id: str | None = None

    def build_connection_dict(self) -> dict[str, Any]:
        connection: dict[str, Any] = expand_db_url(self.url)

        if self.json_override:
            connection = json.loads(self.json_override)

        if self.db_suffix and "credentials" in connection:
            db: str = connection["credentials"].get("database", "")
            if db:
                connection["credentials"]["database"] = f"{db}_{self.db_suffix}"

        if self.worker_id and "credentials" in connection:
            db = connection["credentials"].get("database", "")
            if db and not db.endswith(f"_{self.worker_id}"):
                connection["credentials"]["database"] = f"{db}_{self.worker_id}"

        return connection


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", f".env.{current_env}", ".env.secrets"), extra="ignore")
    env: str = Field(default=current_env)
    github_sha: str = Field(default="")  # In production, the built git commit
    log_level: str = Field(default="info")
    # The product's name as users see it: page titles, the outbound email display name.
    product_name: str = "Convictional"
    app_port: int = Field(default_factory=_default_app_port)
    base_url: HttpUrl = Field(default_factory=_default_base_url)
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: SecretStr = Field(default=SecretStr(""))
    microsoft_oauth_client_id: str = Field(default="")
    microsoft_oauth_client_secret: SecretStr = Field(default=SecretStr(""))
    slack_oauth_client_id: str = Field(default="")
    slack_oauth_client_secret: SecretStr = Field(default=SecretStr(""))
    # Base URL of the shared oauth-proxy (demo only). Demo spins up many ephemeral
    # per-PR services whose URLs can't all be pre-registered with each IdP, so SSO
    # callbacks route through one proxy with a stable registered URI. Empty in
    # production/staging, which hit each IdP directly at their own /auth/{provider}.
    # The provider path is appended per-route (see infra.oauth.login_redirect_uri).
    oauth_proxy_url: str = ""
    enable_fake_auth: bool = False
    enable_mcp_fake_auth: bool = False
    sentry_dsn: HttpUrl | None = None
    sentry_org: str = ""
    sentry_project: str = ""
    sentry_project_id: str = ""
    secret_key: SecretStr = Field(default=SecretStr("secret_key"))
    gcp_project: str = ""
    gcp_project_number: str = ""
    gcp_location: str = ""
    cloud_tasks_low_priority_queue: str = ""
    cloud_tasks_service_account: str = ""
    openai_organization: str = ""
    openai_api_key: SecretStr = Field(default=SecretStr(""))
    job_runner: JobRunner = JobRunner.ASYNCIO
    job_timeout_seconds: int = 1800
    dead_job_interval_hours: int = 104  # Full retry cycle
    worker_count: int = 1
    shutdown_timeout: int = 10
    cache_store: CacheStore = CacheStore.NULL
    embedding_backend: EmbeddingBackend = EmbeddingBackend.OPENAI
    gcs_bucket: str = ""
    gcs_key_prefix: str = ""
    email_delivery: EmailDelivery = EmailDelivery.DEVELOPMENT
    # Outbound sender identities and the Mailgun sending domain, all operator-supplied:
    # a default here would make every deployment send as somebody else's domain.
    email_from: str = ""
    research_email_from: str = ""
    mailgun_domain: str = ""
    mailgun_api_key: SecretStr = Field(default=SecretStr(""))
    mailgun_webhook_signing_key: SecretStr = Field(default=SecretStr(""))
    postgres_url: SecretStr = Field(default=SecretStr(_LOCAL_POSTGRES_URL))
    # Comma-separated database roles whose SELECT access is limited to non-protected
    # columns (see scripts/db/update_column_permissions.py). Role names are
    # deployment-specific, so they are operator-supplied rather than committed.
    restricted_db_users: Annotated[list[str], NoDecode] = []
    postgres_json: SecretStr = Field(default=SecretStr(""))
    auxiliary_postgres_url: SecretStr = Field(default=SecretStr(""))
    auxiliary_postgres_json: SecretStr = Field(default=SecretStr(""))
    hnsw_max_candidates_examined: int = Field(default=1000)
    hnsw_iterative_scan: Literal["relaxed_order", "strict_order"] = Field(default="relaxed_order")
    hnsw_max_scan_tuples: int = Field(default=20000)
    content_search_max_vector_matches: int = Field(default=500)
    content_search_max_text_matches: int = Field(default=300)
    # Operator contact addresses: feedback_email is shown to users on the error page and
    # is the VAPID subject; signup_email and new_user_notification_emails (comma-separated)
    # receive signup notices. Unset means those mails are not sent — see the mailers.
    feedback_email: str = ""
    signup_email: str = ""
    new_user_notification_emails: str = ""
    anthropic_api_key: SecretStr = Field(default=SecretStr("anthropic_api_key"))
    mailbox_retry_wait_seconds: int = Field(default=1)
    is_hot_reload: bool = False
    allowed_hosts: Annotated[list[str], NoDecode] = []
    # Signup blocklists, env-backed (comma-separated) so no personal identifier or
    # named company domain is committed to source history and each can be changed
    # per environment. banned_domains blocks whole domains; blocked_emails and
    # blocked_oauth_subs block individual identities (see accounts.py enforcement).
    banned_domains: Annotated[list[str], NoDecode] = []
    blocked_emails: Annotated[set[str], NoDecode] = set()
    blocked_oauth_subs: Annotated[set[str], NoDecode] = set()
    # Comma-separated addresses granted superuser (see User.is_superuser). Empty means
    # no superuser exists, which is the safe default for a fresh deployment: privilege
    # is granted per address by the operator rather than inferred from an email domain.
    superuser_emails: Annotated[set[str], NoDecode] = set()
    # Kill-switch for self-serve account creation. Signup has no flow of its own — an
    # account is created as a side effect of a first successful OAuth login — so this is
    # enforced where accounts are created (User.get_or_create_by_oauth), not by hiding a
    # form. Existing users keep logging in, and invitees keep accepting invites because
    # an invite pre-creates the User row and so never reaches the create path.
    signups_enabled: bool = Field(default=True)
    has_csrf_protection: bool = Field(default=True)
    session_cookie_name: str = Field(default="convictional_session")
    recall_ai_api_key: SecretStr = Field(default=SecretStr(""))
    recall_ai_webhook_signing_secret: SecretStr = Field(default=SecretStr(""))
    klipy_api_key: str = Field(default="")
    sse_connection_timeout: int = 4 * 60
    show_debug_exceptions: bool = False
    debug_exceptions_filters: list[str] = Field(default=["site-packages", "lib/python"])
    jobs_service_name: str = Field(default="")
    asset_host: HttpUrl | None = Field(default=None)
    asset_building_enabled: bool = False
    vite_url: HttpUrl = Field(default_factory=_default_vite_url)
    vite_port: int = Field(default_factory=_default_vite_port)
    static_asset_url_prefix: str = Field(default="/static/")
    marketing_site_url: HttpUrl = Field(default=HttpUrl("https://get.convictional.com"))
    # Externally hosted legal and security pages, linked from the sign-in screen and
    # served by the /policies/* redirects. Unset means the operator has published no
    # such page: the link is omitted and the redirect 404s rather than sending a user
    # somewhere that isn't ours.
    terms_of_service_url: HttpUrl | None = None
    privacy_policy_url: HttpUrl | None = None
    security_policy_url: HttpUrl | None = None
    pagination_default_per_page: int = 30
    email_client: EmailClient = Field(default=EmailClient.FAKE)
    gmail_api_client: GmailAPIClient = Field(default=GmailAPIClient.PRODUCTION)
    email_messages_onboarding_sync_limit: int = 100
    # enable_gmail_watch for Gmail accounts to receive email webhook events.
    # When using this locally, be sure to run `make script ARGS="scripts/reset_gmail_integration.py --yes"`
    # to stop the watch before end-of-day otherwise you will receive a slew of emails when you start
    # your local server again.
    enable_gmail_watch: bool = False
    # oauth_include_granted_scopes_on_login controls whether OAuth requests include previously granted scopes.
    # Set to False in development to allow fresh logins without accumulated scopes for easier testing.
    oauth_include_granted_scopes_on_login: bool = True
    mailbox_sync_debounce_seconds: int = Field(default=30)
    browser_test_default_timeout: int = Field(default=5000)
    # CookieAuthAsyncWebClient slack env vars - DO NOT USE IN PRODUCTION
    slack_xoxc_token: SecretStr = Field(default=SecretStr(""))
    slack_xoxd_token: SecretStr = Field(default=SecretStr(""))

    # MCP (Model Context Protocol) server configuration
    mcp_server_name: str = "Convictional MCP"
    mcp_jwt_signing_key: SecretStr | None = None
    mcp_storage_encryption_key: SecretStr | None = None

    # Web Push (VAPID). Real keys live in .env.secrets (dev) or deploy-time
    # secrets (prod) — never committed. Empty defaults keep settings load
    # tolerant in dev/test. The VAPID subject (RFC 8292 §2) is derived from
    # feedback_email below — same audience (operator contact), no separate knob.
    vapid_public_key: str = Field(default="")
    vapid_private_key: SecretStr = Field(default=SecretStr(""))
    # Kill-switch for the push dispatch path. The API endpoints stay reachable
    # so the UI doesn't fail oddly when the flag is off; only the trigger that
    # enqueues a push job short-circuits.
    push_enabled: bool = Field(default=False)
    # Selects the relay used by `infra.push.send_push`. Tests override to FAKE
    # to record sends without touching the real FCM/Mozilla/APNs endpoints.
    push_delivery: PushDelivery = Field(default=PushDelivery.NETWORK)

    #
    # Mobile client (app/mobile) only
    #
    # Nothing the web app serves to a browser reads these. They exist so the iOS build can
    # sign in, claim Universal Links, and receive APNs pushes, and they are reached only
    # from `/.well-known/` and the APNs branch of the push dispatcher. The block travels
    # with the mobile client and can be dropped whole alongside it.
    #
    # iOS-type Google OAuth client. Distinct from the web client because Google requires a
    # separate client per platform (PKCE-only, no client secret) and a different redirect
    # URI (the app's reverse-DNS bundle ID). Populated via env in EAS Cloud builds.
    google_oauth_ios_client_id: str = Field(default="")
    # Apple Developer Team ID, used to build the AASA `appID` for Universal Links
    # (`<TEAM_ID>.<ios_bundle_id>`). The `/.well-known/apple-app-site-association` route
    # returns 404 when unset, which iOS treats as "no association" (no app link binding).
    apple_team_id: str = Field(default="")
    # The iOS bundle identifier, as registered with Apple.
    ios_bundle_id: str = Field(default="")
    # APNs gateway endpoint. Today this is Expo Push Service (wraps APNs);
    # an Expo Enterprise tenant or a direct-APNs migration would override.
    expo_push_url: HttpUrl = Field(default=HttpUrl("https://exp.host/--/api/v2/push/send"))
    # Access token for authenticated sends to the Expo Push Service. With Expo's
    # "enhanced push security" enabled, every send must carry this as a Bearer
    # token or Expo rejects it with UNAUTHORIZED. Empty sends unauthenticated.
    expo_access_token: SecretStr = Field(default=SecretStr(""))

    def is_env(self, *environments: str) -> bool:
        return self.env in environments

    def validate_identity_settings(self) -> None:
        """Fail startup when a deployed environment hasn't supplied its own identity.

        None of these carry a default, so an unset value is not a fallback to something
        workable — it is a send with no sender, or a Mailgun call with no domain. Local runs
        skip the check: dev and test don't send mail, and a hard failure there would only
        be noise. Mobile-only settings are deliberately absent; they are the mobile client's
        problem, not the web app's.
        """
        if self.is_local:
            return

        required = {"email_from": self.email_from}
        if self.email_delivery == EmailDelivery.MAILGUN:
            required["mailgun_domain"] = self.mailgun_domain
        if self.push_enabled:
            # The VAPID subject (RFC 8292 §2) is the operator contact a push relay uses.
            required["feedback_email"] = self.feedback_email

        if missing := sorted(name for name, value in required.items() if not value):
            raise RuntimeError(f"Required identity settings are unset: {', '.join(missing)}")

    @contextmanager
    def override(self):
        # Snapshot the live field values rather than model_dump()'s, which runs the field
        # serializers: restoring from a dump would rebind base_url to a plain str, and
        # assignment isn't validated, so every later HttpUrl access would break.
        original = copy.deepcopy({name: getattr(self, name) for name in type(self).model_fields})
        try:
            yield
        finally:
            for key, value in original.items():
                setattr(self, key, value)

    @field_serializer("base_url")
    def serialize_base_url(self, value: HttpUrl) -> str:
        # Always serialize to string
        return str(value)

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def decode_allowed_hosts(cls, v: str) -> list[str]:
        if isinstance(v, list):
            return v
        return [x for x in v.split(",")]

    @field_validator("banned_domains", "restricted_db_users", mode="before")
    @classmethod
    def decode_banned_domains(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, list):
            return v
        return [item.strip() for item in v.split(",") if item.strip()]

    @field_validator("blocked_emails", "blocked_oauth_subs", mode="before")
    @classmethod
    def decode_identifier_set(cls, v: str | set[str] | list[str]) -> set[str]:
        # Case is preserved: blocked_oauth_subs holds opaque provider identifiers that
        # compare case-sensitively, and blocked_emails is matched through
        # canonicalize_email at the call site rather than by plain equality.
        if isinstance(v, (set, list)):
            return set(v)
        return {item.strip() for item in v.split(",") if item.strip()}

    @field_validator("superuser_emails", mode="before")
    @classmethod
    def decode_superuser_emails(cls, v: str | set[str] | list[str]) -> set[str]:
        # Lowercased once here so every read is a plain set membership test.
        if isinstance(v, (set, list)):
            return {item.lower() for item in v}
        return {item.strip().lower() for item in v.split(",") if item.strip()}

    @property
    def vapid_subject(self) -> str:
        # RFC 8292 §2 contact URI for push relays (FCM, AutoPush, APNs) to reach
        # us about traffic issues. The audience is operators, not end users —
        # the same inbox we use for product feedback.
        return f"mailto:{self.feedback_email}"

    @property
    def db_suffix(self) -> str:
        if self.is_running_on_gcp:
            return ""
        if self.postgres_json.get_secret_value():
            return ""
        if self.postgres_url.get_secret_value() != _LOCAL_POSTGRES_URL:
            return ""
        return _checkout_identifier()

    @property
    def default_postgres_config(self) -> dict[str, Any]:
        config = DatabaseConnectionConfig(
            url=self.postgres_url.get_secret_value(),
            json_override=self.postgres_json.get_secret_value(),
            db_suffix=self.db_suffix,
            worker_id=self.worker_id,
        )
        return config.build_connection_dict()

    @property
    def auxiliary_postgres_config(self) -> dict[str, Any]:
        auxiliary_url = self.auxiliary_postgres_url.get_secret_value()
        if auxiliary_url:
            config = DatabaseConnectionConfig(
                url=auxiliary_url,
                json_override=self.auxiliary_postgres_json.get_secret_value(),
                db_suffix=self.db_suffix,
                worker_id=self.worker_id,
            )
            return config.build_connection_dict()
        else:
            return self.default_postgres_config

    @property
    def tortoise_config(self):
        return {
            "connections": {
                "default": self.default_postgres_config,
                "auxiliary": self.auxiliary_postgres_config,
            },
            "apps": {
                "convictional": {
                    "default_connection": "default",
                    "models": [
                        "app.models.workspaces.goals",
                        "app.models.workspaces.meetings",
                        "app.models.workspaces.posts",
                        "app.models.workspaces.documents",
                        "app.models.workspaces.email.contact",
                        "app.models.workspaces.email.mailbox",
                        "app.models.collaboration.mailbox",
                        "app.models.workspaces.email.thread",
                        "app.models.commands",
                        "app.models.collaboration.content",
                        "app.models.collaboration.workspace",
                        "app.models.collaboration.live",
                        "app.models.workspaces.chat",
                        "app.models.accounts",
                        "integrations.google.models",
                        "integrations.notion.models",
                        "integrations.recall_ai.models",
                        "integrations.slack.models",
                        "infra.storage",
                        "infra.jobs",
                        "infra.cache",
                    ],
                },
                "migrations": {"models": ["aerich.models"]},
            },
        }

    @property
    def fastapi_config(self) -> dict[str, Any]:
        # FastAPI's built-in /docs, /redoc, /openapi.json are disabled; the spec
        # and UIs are served under /api/ by app/routers/api/docs.py, gated by
        # admin auth.
        return {
            "title": "Convictional API",
            "openapi_url": None,
            "docs_url": None,
            "redoc_url": None,
        }

    @property
    def postgres_dict(self) -> dict[str, Any]:
        default_connection_config = settings.tortoise_config["connections"]["default"]
        if isinstance(default_connection_config, str):
            default_connection_config = expand_db_url(default_connection_config)
        return default_connection_config.get("credentials", {})

    @property
    def is_running_on_gcp(self):
        # This is the check recommeded by Google here:
        # https://cloud.google.com/run/docs/testing/local#confirm_that_your_code_is_running_locally
        return os.environ.get("K_REVISION", None) is not None

    @property
    def has_cloud_tasks(self):
        return bool(self.gcp_project) and bool(self.gcp_location)

    @property
    def is_debug(self) -> bool:
        return self.log_level == "debug"

    @property
    def has_google_oauth(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret.get_secret_value())

    @property
    def has_slack_oauth(self) -> bool:
        return bool(self.slack_oauth_client_id and self.slack_oauth_client_secret.get_secret_value())

    @property
    def has_microsoft_oauth(self) -> bool:
        return bool(self.microsoft_oauth_client_id and self.microsoft_oauth_client_secret.get_secret_value())

    @property
    def slack_app_install_url(self) -> str:
        # Workspace-admin install link for our own Slack app, derived from the OAuth
        # client id so the app identity lives in one setting. Empty when Slack isn't
        # configured, which hides the link (see SlackSection).
        if not self.slack_oauth_client_id:
            return ""
        scopes = ",".join(SLACK_INSTALL_USER_SCOPES)
        return (
            f"https://slack.com/oauth/v2/authorize?client_id={self.slack_oauth_client_id}&scope=&user_scope={scopes}"
        )

    @property
    def is_ssl(self) -> bool:
        return self.base_url.scheme == "https"

    @property
    def root(self):
        return _PROJECT_ROOT

    @property
    def checkout_name(self) -> str:
        return _CHECKOUT_ROOT.name

    @property
    def local_storage_path(self) -> Path:
        """Return the local storage path, scoped by environment."""
        return self.root / "tmp" / "storage" / self.env

    @property
    def storage_service(self):
        return StorageService.GCS if self.gcs_bucket else StorageService.LOCAL

    @property
    def has_mailgun(self):
        return bool(self.mailgun_domain and self.mailgun_api_key.get_secret_value())

    @property
    def recall_ai_providers(self) -> dict[str, str]:
        return {
            "Google Meet": "meet.google.com",
            "Microsoft Teams": "teams.microsoft.com",
            "Microsoft Teams Live": "teams.live.com",
            "Zoom": "zoom.us",
        }

    @property
    def recall_ai_meeting_platforms(self) -> dict[str, str]:
        """
        This is similar to the recall_ai_providers property, but it returns a list of meeting platforms.
        These match the platform values that recall AI returns for calendar events.
        We need both because we have to handle links from the user as well as events from the calendar.
        """
        return {
            "Google Meet": "google_meet",
            "Microsoft Teams": "microsoft_teams",
            "Microsoft Teams Live": "microsoft_teams_live",  # This is the personal version of Teams
            "Zoom": "zoom",
        }

    @property
    def internal_base_url(self) -> HttpUrl:
        """If running in GCP, this will return the internal URL for the Cloud Run service."""
        # https://cloud.google.com/run/docs/triggering/https-request#deterministic
        if self.is_running_on_gcp:
            service_name = os.environ.get("K_SERVICE", "")

            return HttpUrl(f"https://{service_name}-{self.gcp_project_number}.{self.gcp_location}.run.app")

        return self.base_url

    @property
    def jobs_service_url(self) -> HttpUrl:
        """Returns the URL for the jobs service."""
        # If we're running in the jobs service, return our own URL
        if self.is_running_on_gcp and self.is_jobs_service:
            return self.internal_base_url

        # If we're in a different service and jobs_service_name is set, return the jobs service URL
        if self.is_running_on_gcp and self.jobs_service_name:
            result = HttpUrl(f"https://{self.jobs_service_name}-{self.gcp_project_number}.{self.gcp_location}.run.app")
            return result

        return self.base_url

    @property
    def is_jobs_service(self) -> bool:
        return bool(self.jobs_service_name and os.environ.get("K_SERVICE", "") == self.jobs_service_name)

    @property
    def has_klipy(self) -> bool:
        return bool(self.klipy_api_key)

    @property
    def has_sentry(self) -> bool:
        return bool(self.sentry_org and self.sentry_project and self.sentry_project_id)

    @property
    def is_local(self) -> bool:
        # Loopback by IP counts: the browser-test server binds 127.0.0.1 and sets BASE_URL
        # from it, and treating that as deployed would demand operator identity settings.
        return self.base_url.host in LOOPBACK_HOSTS

    @property
    def dev_color(self) -> str | None:
        name = _CHECKOUT_ROOT.name.lower()
        for color_name, hex_val in DEV_COLORS.items():
            if name.endswith(f"-{color_name}") or name.endswith(f"_{color_name}"):
                return hex_val
        return None

    @property
    def dev_label(self) -> str:
        name = _CHECKOUT_ROOT.name
        prefix = "convictional"
        if name.lower().startswith(f"{prefix}-") or name.lower().startswith(f"{prefix}_"):
            label = name[len(prefix) + 1 :]
        else:
            label = name
        return label.upper()

    @property
    def cors_origins(self) -> list[str]:
        if self.is_local:
            return ["*"]
        # Generate CORS origins from allowed_hosts, filtering out internal URLs
        origins = []
        for host in self.allowed_hosts:
            # Skip internal Cloud Run URLs - they don't need CORS
            if ".run.app" not in host:
                origins.append(f"https://{host}")
        return origins if origins else [str(self.base_url)]

    @property
    def worker_id(self) -> str:
        worker_id = os.environ.get("WORKER_ID", "")
        if worker_id:
            return worker_id

        # Handle pytest-xdist format (e.g., 'gw0', 'gw1', etc.)
        pytest_worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
        if pytest_worker_id and pytest_worker_id.startswith("gw"):
            return pytest_worker_id[2:]  # Extract the number part

        return ""


settings = Settings()
