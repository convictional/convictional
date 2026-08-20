import pytest
from fastapi import status

from app.jobs.mailers import SendNewUserEmailJob
from app.models.accounts import User
from config import settings
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_api_auth_google_creates_user_and_session(client: AppClient):
    # Exercises the same path the production /api/auth/google runs post-Google
    # exchange: get_or_create_user + the session middleware's Set-Cookie. The
    # /fake twin (gated by settings.enable_fake_auth, on in .env.test) lets us
    # skip the real OAuth round-trip the same way /login/fake does in
    # app/routers/auth.py.
    with client.logged_out():
        response = await client.post(
            "/api/auth/google/fake",
            json={"email": "test@example.com"},
        )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert client.session.get("user_id")
    assert await User.get_or_none(email="test@example.com") is not None


@pytest.mark.asyncio
async def test_invited_user_new_user_email_fires_on_first_login(client: AppClient, background_jobs: InlineJobs):
    # An invite pre-creates the account, but the internal "new user" notification must wait until
    # the invitee accepts by logging in — otherwise the team hears about accounts nobody ever used.
    admin = await create_user(is_admin=True)
    client.current_user = admin
    response = await client.post("/api/organization/users", json={"email": "invitee@example.com"})
    assert response.status_code == status.HTTP_201_CREATED
    assert background_jobs.has_completed_job(SendNewUserEmailJob, count=0)

    # First login accepts the invite — now the notification fires exactly once.
    with client.logged_out():
        response = await client.post("/api/auth/google/fake", json={"email": "invitee@example.com"})
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert background_jobs.has_completed_job(SendNewUserEmailJob, count=1)


@pytest.mark.asyncio
async def test_signup_freeze_blocks_new_accounts_but_not_logins_or_invites(
    client: AppClient, background_jobs: InlineJobs
):
    # The freeze has to be surgical: it exists to stop strangers creating accounts, not to
    # lock out the people who already have one or leave invitees stranded.
    admin = await create_user(is_admin=True)
    client.current_user = admin
    response = await client.post("/api/organization/users", json={"email": "invitee@example.com"})
    assert response.status_code == status.HTTP_201_CREATED

    with settings.override():
        settings.signups_enabled = False

        with client.logged_out():
            response = await client.post("/api/auth/google/fake", json={"email": "stranger@example.com"})
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert not client.session.get("user_id")
        assert await User.get_or_none(email="stranger@example.com") is None

        # An invite pre-created the row, so accepting it is a login and still succeeds —
        # including the internal new-user notification that fires on first login.
        with client.logged_out():
            response = await client.post("/api/auth/google/fake", json={"email": "invitee@example.com"})
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert background_jobs.has_completed_job(SendNewUserEmailJob, count=1)

        with client.logged_out():
            response = await client.post("/api/auth/google/fake", json={"email": admin.email})
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert client.session.get("user_id") == str(admin.id)


@pytest.mark.asyncio
async def test_api_auth_google_rejects_short_code_verifier(client: AppClient):
    with settings.override():
        settings.google_oauth_ios_client_id = "fake-ios-client-id"
        with client.logged_out():
            response = await client.post(
                "/api/auth/google",
                json={"code": "ok", "code_verifier": "too-short"},
            )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_api_auth_google_returns_503_when_not_configured(client: AppClient):
    # Don't leak missing-config as a generic 500 — the mobile client uses 503
    # to surface "this env hasn't enabled native OAuth yet" distinctly.
    with settings.override():
        settings.google_oauth_ios_client_id = ""
        with client.logged_out():
            response = await client.post(
                "/api/auth/google",
                json={"code": "fake-code", "code_verifier": "x" * 64},
            )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
