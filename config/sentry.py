from urllib.parse import urlencode, urlsplit

from config import settings

# Field names that contain encrypted/sensitive data.
# Keep in sync with app/mobile/config/sentry.ts SENSITIVE_FIELD_NAMES.
SENSITIVE_FIELD_NAMES = {
    "access_token",
    "body",
    "body_html",
    "body_html_sanitized",
    "body_markdown",
    "body_plain",
    "headers_list",
    "index_content",
    "last_comment",
    "lookup_content",
    "lookup_search",
    "normalized_subject",
    "preview",
    "preview_content",
    "preview_content_normalized",
    "raw_data",
    "refresh_token",
    "response",
    "subject",
    "text_search",
    "title",
    "title_normalized",
}


def scrub_sensitive_data(data):
    """Recursively scrub sensitive data from any data structure."""
    if isinstance(data, dict):
        scrubbed = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_FIELD_NAMES:
                scrubbed[key] = "[REDACTED]"
            else:
                scrubbed[key] = scrub_sensitive_data(value)
        return scrubbed
    elif isinstance(data, list):
        return [scrub_sensitive_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(scrub_sensitive_data(item) for item in data)
    else:
        return data


def sentry_environment_name() -> str:
    if settings.is_jobs_service:
        return f"{settings.env}-jobs"

    return settings.env


def sentry_security_report_url() -> str | None:
    # Sentry exposes a CSP/security-report ingestion endpoint derived from the
    # DSN: https://<host>/api/<project_id>/security/?sentry_key=<public_key>.
    # Tagging with environment + release lets Sentry group reports the same
    # way it groups errors.
    if not settings.sentry_dsn:
        return None

    parsed = urlsplit(str(settings.sentry_dsn))
    public_key = parsed.username
    project_id = parsed.path.strip("/")
    if not (parsed.hostname and public_key and project_id):
        return None

    query = urlencode(
        {
            "sentry_key": public_key,
            "sentry_environment": sentry_environment_name(),
            "sentry_release": settings.github_sha,
        }
    )
    return f"{parsed.scheme}://{parsed.hostname}/api/{project_id}/security/?{query}"


def setup_sentry():
    if settings.sentry_dsn:
        import sentry_sdk  # noqa: PLC0415
        from sentry_sdk.integrations.asyncpg import AsyncPGIntegration  # noqa: PLC0415
        from sentry_sdk.types import Event, Hint  # noqa: PLC0415

        def before_send_hook(event: Event, hint: Hint) -> Event | None:
            """Sentry before_send hook to scrub sensitive encrypted field data."""
            return scrub_sensitive_data(event)

        sentry_sdk.init(
            dsn=str(settings.sentry_dsn),
            release=settings.github_sha,
            environment=sentry_environment_name(),
            traces_sample_rate=0.2,
            profiles_sample_rate=0.0,
            integrations=[AsyncPGIntegration()],
            before_send=before_send_hook,
        )
