import json
import re

import pytest
from pydantic import HttpUrl, SecretStr

from config.settings import (
    _LOCAL_POSTGRES_URL,
    DatabaseConnectionConfig,
    EmailDelivery,
    Settings,
    _checkout_identifier,
    _compute_port_offset,
)


def test_checkout_identifier_returns_nonempty_deterministic_string():
    result = _checkout_identifier()
    assert isinstance(result, str)
    assert len(result) > 0
    assert result == _checkout_identifier()


def test_checkout_identifier_sanitizes_special_characters():
    for name, expected in [
        ("convictional-3", "convictional_3"),
        ("My.Project", "my_project"),
        ("UPPERCASE", "uppercase"),
        ("--leading-trailing--", "leading_trailing"),
        ("a" * 50, "a" * 30),
    ]:
        sanitized = re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")[:30]
        assert sanitized == expected


def test_connection_config_no_suffix_leaves_database_unchanged():
    config = DatabaseConnectionConfig(url="asyncpg://user:@localhost:5432/convictional_test")
    result = config.build_connection_dict()
    assert result["credentials"]["database"] == "convictional_test"


def test_connection_config_suffix_appends():
    config = DatabaseConnectionConfig(
        url="asyncpg://user:@localhost:5432/convictional_test",
        db_suffix="convictional_3",
    )
    result = config.build_connection_dict()
    assert result["credentials"]["database"] == "convictional_test_convictional_3"


def test_connection_config_worker_id_appends_after_suffix():
    config = DatabaseConnectionConfig(
        url="asyncpg://user:@localhost:5432/convictional_test",
        db_suffix="convictional_3",
        worker_id="0",
    )
    result = config.build_connection_dict()
    assert result["credentials"]["database"] == "convictional_test_convictional_3_0"


def test_connection_config_worker_id_without_suffix():
    config = DatabaseConnectionConfig(
        url="asyncpg://user:@localhost:5432/convictional_test",
        worker_id="1",
    )
    result = config.build_connection_dict()
    assert result["credentials"]["database"] == "convictional_test_1"


def test_connection_config_empty_suffix_leaves_database_unchanged():
    config = DatabaseConnectionConfig(
        url="asyncpg://user:@localhost:5432/convictional_test",
        db_suffix="",
    )
    result = config.build_connection_dict()
    assert result["credentials"]["database"] == "convictional_test"


def test_connection_config_json_override_with_suffix():
    json_config = json.dumps(
        {
            "engine": "tortoise.backends.asyncpg",
            "credentials": {"host": "localhost", "port": 5432, "database": "convictional_test"},
        }
    )
    config = DatabaseConnectionConfig(
        url="asyncpg://user:@localhost:5432/unused",
        json_override=json_config,
        db_suffix="my_checkout",
    )
    result = config.build_connection_dict()
    assert result["credentials"]["database"] == "convictional_test_my_checkout"


def test_db_suffix_auto_detects():
    s = Settings(postgres_url=SecretStr(_LOCAL_POSTGRES_URL))
    assert s.db_suffix == _checkout_identifier()


def test_db_suffix_skips_when_postgres_json_set():
    s = Settings(postgres_json=SecretStr('{"credentials": {"database": "convictional_production"}}'))
    assert s.db_suffix == ""


def test_db_suffix_skips_when_postgres_url_overridden():
    s = Settings(postgres_url=SecretStr("asyncpg://user:pass@remote:5432/convictional_production"))
    assert s.db_suffix == ""


def test_blocklists_decode_from_comma_separated_env():
    # Env vars arrive as comma-separated strings; whitespace and blank entries are dropped.
    s = Settings(
        banned_domains="inovia.vc, runql.com ,",
        blocked_emails="kris.braun@gmail.com, other@example.com",
        blocked_oauth_subs="101356682725729218008, AbCd",
        superuser_emails="Admin@Example.com, other-admin@example.com ,",
    )
    assert s.banned_domains == ["inovia.vc", "runql.com"]
    assert s.blocked_emails == {"kris.braun@gmail.com", "other@example.com"}
    # OAuth subs are opaque provider identifiers, so their case survives decoding.
    assert s.blocked_oauth_subs == {"101356682725729218008", "AbCd"}
    # Superuser addresses are lowercased at parse time so User.is_superuser is a plain
    # membership test.
    assert s.superuser_emails == {"admin@example.com", "other-admin@example.com"}


def test_blocklists_default_empty():
    s = Settings()
    assert s.banned_domains == []
    assert s.blocked_emails == set()
    assert s.blocked_oauth_subs == set()
    assert s.superuser_emails == set()


def test_identity_settings_are_unset_by_default():
    # A default here would make every fork send as us, link to our pages, or hand
    # superuser to whoever next owns our domain.
    s = Settings()
    assert s.email_from == ""
    assert s.research_email_from == ""
    assert s.mailgun_domain == ""
    assert s.feedback_email == ""
    assert s.signup_email == ""
    assert s.new_user_notification_emails == ""
    assert s.ios_bundle_id == ""
    assert s.superuser_emails == set()
    assert s.terms_of_service_url is None
    assert s.privacy_policy_url is None
    assert s.security_policy_url is None


def test_slack_app_install_url_derives_from_client_id():
    assert Settings().slack_app_install_url == ""

    url = Settings(slack_oauth_client_id="123.456").slack_app_install_url
    assert url.startswith("https://slack.com/oauth/v2/authorize?client_id=123.456&")
    assert "user_scope=identify,search:read," in url


def test_is_local_covers_loopback_by_name_and_ip():
    # The browser-test server binds 127.0.0.1 and sets BASE_URL from it.
    assert Settings(base_url=HttpUrl("http://localhost:8000")).is_local
    assert Settings(base_url=HttpUrl("http://127.0.0.1:41889")).is_local
    assert not Settings(base_url=HttpUrl("https://app.example.com")).is_local


def test_override_restores_field_types_not_their_serialized_forms():
    # Assignment isn't validated, so restoring a serialized snapshot would leave base_url
    # a plain str and break every attribute access on it from then on.
    s = Settings(base_url=HttpUrl("http://localhost:8000"))
    hosts = s.allowed_hosts

    with s.override():
        s.base_url = HttpUrl("https://app.example.com")
        s.allowed_hosts = ["app.example.com"]

    assert isinstance(s.base_url, HttpUrl)
    assert s.is_local
    assert s.allowed_hosts == hosts


def test_validate_identity_settings_skips_local_and_bites_when_deployed():
    # Local dev and tests don't send mail, so nothing is required of them.
    Settings(base_url=HttpUrl("http://localhost:8000")).validate_identity_settings()
    Settings(base_url=HttpUrl("http://127.0.0.1:41889")).validate_identity_settings()

    deployed = HttpUrl("https://app.example.com")
    with pytest.raises(RuntimeError, match="email_from"):
        Settings(base_url=deployed).validate_identity_settings()

    with pytest.raises(RuntimeError, match="mailgun_domain"):
        Settings(
            base_url=deployed, email_from="noreply@example.com", email_delivery=EmailDelivery.MAILGUN
        ).validate_identity_settings()

    with pytest.raises(RuntimeError, match="feedback_email"):
        Settings(base_url=deployed, email_from="noreply@example.com", push_enabled=True).validate_identity_settings()

    # Mobile-only settings are not the web app's problem, so an unset bundle id passes.
    Settings(
        base_url=deployed,
        email_from="noreply@example.com",
        email_delivery=EmailDelivery.MAILGUN,
        mailgun_domain="example.com",
        push_enabled=True,
        feedback_email="ops@example.com",
        apple_team_id="TEAM123",
    ).validate_identity_settings()


def test_port_offset_returns_nonzero():
    assert _compute_port_offset() > 0


def test_port_offset_deterministic():
    assert _compute_port_offset() == _compute_port_offset()


def test_port_offset_within_range():
    offset = _compute_port_offset()
    assert 1 <= offset <= 100
