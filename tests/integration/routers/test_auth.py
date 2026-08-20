from http.cookies import Morsel, SimpleCookie

import httpx
import pytest
from fastapi import status
from pydantic import HttpUrl, SecretStr

from app.models.accounts import User
from app.models.collaboration.workspace import SubscriptionPreference
from app.routers.dependencies import INBOX_SORT_PREFERENCE_COOKIE
from config import settings
from config.enums import SubscriptionLevel
from infra.email import FakeDelivery
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


def _parse_set_cookie(response: httpx.Response, name: str) -> Morsel | None:
    jar: SimpleCookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        jar.load(header)
    return jar.get(name)


@pytest.mark.asyncio
async def test_fake_auth_flow(client: AppClient):
    response = await client.get("/login")
    assert response.status_code == status.HTTP_200_OK

    # Test new users can login
    response = await client.post("/login/fake", data={"email": "test@example.com"}, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert client.session["user_id"]

    # Login sets the JS-readable logged-in marker (value "1", not HttpOnly) so
    # the client-side bfcache guard can detect a stale authenticated page.
    marker = _parse_set_cookie(response, "logged_in")
    assert marker is not None
    assert marker.value == "1"
    assert marker["httponly"] == ""

    response = await client.post("/logout", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "/login" in response.headers["location"]
    assert "user_id" not in client.session

    # Logout must not freeze the origin network in Safari: no Clear-Site-Data.
    assert "clear-site-data" not in response.headers

    # The logged-in marker is expired/cleared on logout.
    marker = _parse_set_cookie(response, "logged_in")
    assert marker is not None
    assert marker.value in ("", "null")
    assert marker["max-age"] == "0" or marker["expires"] != ""

    # Confirm existing users can login
    user = await create_user(email="other@example.com")
    response = await client.post("/login/fake", data={"email": user.email}, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert client.session["user_id"]


@pytest.mark.asyncio
async def test_first_login(client: AppClient, email_delivery: FakeDelivery):
    # First login
    email = "test_user@example.com"
    response = await client.post("/login/fake", data={"email": email}, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER

    user = await User.get(email=email)
    preferences = await SubscriptionPreference.filter(subscriber_id=user.id).all()
    assert len(preferences) > 0
    expected_levels = {
        "Chat": SubscriptionLevel.ALL,
        "Post": SubscriptionLevel.BROADCASTS,
    }
    assert all(
        p.default_level == expected_levels.get(p.resource_type, SubscriptionLevel.RELEVANT_ONLY) for p in preferences
    )


@pytest.mark.asyncio
async def test_new_organization(client: AppClient, email_delivery: FakeDelivery):
    with settings.override():
        settings.signup_email = "signups@example.com"

        # Test first user
        response = await client.post("/login/fake", data={"email": "test_user@example.net"}, follow_redirects=False)
        assert response.status_code == status.HTTP_303_SEE_OTHER
        first_user = await User.get(email="test_user@example.net").select_related("organization")
        assert first_user.organization is not None
        assert first_user.is_admin
        emails = email_delivery.by_recipient(settings.signup_email)
        assert len(emails) == 1

        # Test another user
        response = await client.post("/login/fake", data={"email": "other_user@example.net"}, follow_redirects=False)
        second_user = await User.get(email="other_user@example.net").select_related("organization")
        assert second_user.organization == first_user.organization
        assert not second_user.is_admin
        assert response.status_code == status.HTTP_303_SEE_OTHER
        emails = email_delivery.by_recipient(settings.signup_email)
        assert len(emails) == 1


@pytest.mark.asyncio
async def test_return_to(client: AppClient):
    with client.logged_out():
        # Visiting the login page doesn't change anything
        response = await client.get("/login")
        assert response.status_code == status.HTTP_200_OK
        assert "redirect_to" not in client.session

        # Visiting a protected page redirects to login.
        response = await client.get("/meetings", follow_redirects=False)
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert response.headers["location"].endswith("/login")

        # Session state now holds the originally intended page
        assert client.session["redirect_to"] == "/meetings"

        # Logging in should redirect to it
        response = await client.post("/login/fake", data={"email": "dev@example.com"}, follow_redirects=False)
        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert client.session["user_id"]
        assert "redirect_to" not in client.session
        assert response.headers["location"] == "/meetings"

    with client.logged_out():
        # Hitting an authenticated API path returns a JSON 401, not a redirect
        response = await client.get("/api/users/me", follow_redirects=False)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # The API path must not be remembered as the post-login destination
        assert "redirect_to" not in client.session

        # Logging in should not bounce the user to the raw API endpoint; with no
        # remembered destination it lands on the default post-login page instead.
        response = await client.post("/login/fake", data={"email": "dev@example.com"}, follow_redirects=False)
        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert response.headers["location"] == "http://testserver/"


@pytest.mark.asyncio
async def test_logout_clears_inbox_preference(client: AppClient):
    response = await client.post(
        "/logout",
        cookies={INBOX_SORT_PREFERENCE_COOKIE: "sort=oldest"},
        follow_redirects=False,
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER
    morsel = _parse_set_cookie(response, INBOX_SORT_PREFERENCE_COOKIE)
    assert morsel is not None
    assert morsel.value == ""
    assert morsel["max-age"] == "0" or morsel["expires"] != ""


@pytest.mark.asyncio
async def test_csrf_token_rotates_on_logout(client: AppClient):
    response = await client.post("/logout", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    first_token = client.session["csrf_token"]

    response = await client.post("/logout", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    second_token = client.session["csrf_token"]

    assert second_token != first_token


@pytest.mark.asyncio
async def test_unauthenticated_login_get_preserves_csrf_token(client: AppClient):
    # Seed a csrf_token via /logout (which explicitly rotates it). The CSRF
    # middleware is disabled in tests, so we can't rely on it to auto-generate.
    await client.post("/logout", follow_redirects=False)
    seeded_token = client.session["csrf_token"]
    assert seeded_token

    with client.logged_out():
        response = await client.get("/login")
        assert response.status_code == status.HTTP_200_OK
        assert client.session["csrf_token"] == seeded_token

        response = await client.get("/login")
        assert response.status_code == status.HTTP_200_OK
        assert client.session["csrf_token"] == seeded_token


@pytest.mark.asyncio
async def test_login_response_is_not_stored(client: AppClient):
    with client.logged_out():
        response = await client.get("/login")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["Cache-Control"] == "no-store"

        response = await client.get("/signup")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["Cache-Control"] == "no-store"


PAUSED_HEADING = "We've paused new signups"
# The OAuth buttons are conditional on provider credentials, which .env.test doesn't set, so
# the sign-in affordance is asserted through the fake-login form that ENABLE_FAKE_AUTH renders
# in the same slot. Asserting on the Google button would only pass on a machine with real
# OAuth secrets in .env.secrets.
SIGN_IN_FORM = "fake-login-form"


@pytest.mark.asyncio
async def test_signup_freeze_pauses_signup_page_and_refuses_new_accounts(client: AppClient):
    # /signup is the URL the marketing site links to, so during a freeze it explains the
    # pause rather than offering a button that only fails after a trip through the identity
    # provider. /login keeps its buttons — existing users and invitees sign in through it.
    with client.logged_out():
        with settings.override():
            settings.signups_enabled = False
            paused = await client.get("/signup")
            login = await client.get("/login")
            refused = await client.post("/login/fake", data={"email": "stranger@example.org"}, follow_redirects=False)

        assert PAUSED_HEADING in paused.text
        assert SIGN_IN_FORM not in paused.text

        assert PAUSED_HEADING not in login.text
        assert SIGN_IN_FORM in login.text
        assert "Create a free account" not in login.text

        # A refused signup is an explanation, not a 500: back to /login with a flash and no
        # session, and no account left behind.
        assert refused.status_code == status.HTTP_302_FOUND
        assert refused.headers["location"].endswith("/login")
        assert "user_id" not in client.session
        assert [flash["content"] for flash in client.session["flashes"]] == [
            "New signups are paused right now. If you already have an account, "
            "log in with the address you used before."
        ]
        assert await User.get_or_none(email="stranger@example.org") is None

    # Signups open again with no code change — the page and the flow both come back.
    with client.logged_out():
        response = await client.get("/signup")
        assert PAUSED_HEADING not in response.text
        assert "Create a free account" in response.text


@pytest.mark.asyncio
async def test_logout_does_not_revoke_other_sessions(client: AppClient):
    response = await client.post("/login/fake", data={"email": "dev@example.com"}, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    user_id = client.session["user_id"]

    response = await client.get("/meetings", follow_redirects=False)
    assert response.status_code == status.HTTP_200_OK

    response = await client.post("/logout", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    # The current device's session cookie is cleared...
    assert "user_id" not in client.session

    # ...but logout writes no server-side state that would invalidate the user's
    # sessions on other devices. last_logout_at is reserved for account deactivation.
    user = await User.get(id=user_id)
    assert user.last_logout_at is None


LINKEDIN_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36 LinkedInApp"
)
ANDROID_WEBVIEW_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12; Pixel 6 Build/SD1A.210817.036; wv)"
    " AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
)
CHROME_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


@pytest.mark.asyncio
async def test_login_shows_embedded_browser_notice_for_linkedin(client: AppClient):
    with settings.override():
        settings.google_oauth_client_id = "fake-client-id"
        settings.google_oauth_client_secret = SecretStr("fake-secret")

        with client.logged_out():
            response = await client.get(
                "/login",
                headers={"User-Agent": LINKEDIN_USER_AGENT},
            )
    assert response.status_code == status.HTTP_200_OK
    assert "Copy link to open in browser" in response.text
    assert "Sign in with Google" not in response.text


@pytest.mark.asyncio
async def test_login_shows_embedded_browser_notice_for_android_webview(client: AppClient):
    with settings.override():
        settings.google_oauth_client_id = "fake-client-id"
        settings.google_oauth_client_secret = SecretStr("fake-secret")

        with client.logged_out():
            response = await client.get(
                "/login",
                headers={"User-Agent": ANDROID_WEBVIEW_USER_AGENT},
            )
    assert response.status_code == status.HTTP_200_OK
    assert "Copy link to open in browser" in response.text
    assert "Sign in with Google" not in response.text


@pytest.mark.asyncio
async def test_login_shows_google_button_for_normal_browser(client: AppClient):
    with settings.override():
        settings.google_oauth_client_id = "fake-client-id"
        settings.google_oauth_client_secret = SecretStr("fake-secret")

        with client.logged_out():
            response = await client.get(
                "/login",
                headers={"User-Agent": CHROME_USER_AGENT},
            )
    assert response.status_code == status.HTTP_200_OK
    assert "Sign in with Google" in response.text
    assert "Copy link to open in browser" not in response.text


@pytest.mark.asyncio
async def test_login_already_logged_in_redirects_to_mailbox(client: AppClient):
    user = await create_user()
    client.current_user = user

    response = await client.get("/login", follow_redirects=False)

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"].endswith("/")


@pytest.mark.asyncio
async def test_policy_routes_and_links_follow_configured_urls(client: AppClient):
    # Unset by default: no page of ours to send anyone to, so the redirects 404 and
    # the sign-in footer omits the links rather than pointing off to someone else's site.
    assert (await client.get("/policies/terms_of_use")).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get("/policies/privacy_policy")).status_code == status.HTTP_404_NOT_FOUND

    with client.logged_out():
        assert (await client.get("/policies/terms_of_use")).status_code == status.HTTP_404_NOT_FOUND
        assert (await client.get("/policies/privacy_policy")).status_code == status.HTTP_404_NOT_FOUND
        login = await client.get("/login")
    assert ">Terms of Service</a>" not in login.text
    assert ">Privacy</a>" not in login.text
    assert ">Security</a>" not in login.text

    with settings.override():
        settings.terms_of_service_url = HttpUrl("https://example.com/terms")
        settings.privacy_policy_url = HttpUrl("https://example.com/privacy")
        settings.security_policy_url = HttpUrl("https://example.com/security")

        # The policy pages are public: the redirects follow the configured URL whether
        # or not anyone is signed in.
        terms = await client.get("/policies/terms_of_use", follow_redirects=False)
        privacy = await client.get("/policies/privacy_policy", follow_redirects=False)

        with client.logged_out():
            terms_logged_out = await client.get("/policies/terms_of_use", follow_redirects=False)
            privacy_logged_out = await client.get("/policies/privacy_policy", follow_redirects=False)
            login = await client.get("/login")

    assert terms.headers["location"] == terms_logged_out.headers["location"] == "https://example.com/terms"
    assert privacy.headers["location"] == privacy_logged_out.headers["location"] == "https://example.com/privacy"
    assert "https://example.com/security" in login.text
