from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from app.models.accounts import (
    EmailAlias,
    Group,
    Invite,
    OAuthToken,
    Organization,
    SignupBlockedError,
    SignupsDisabledError,
    User,
)
from config.enums import AuthenticationProvider
from config.settings import settings
from infra.oauth import Token
from integrations.google.oauth import GOOGLE_DEFAULT_SCOPES, GOOGLE_GMAIL_SCOPES
from tests.helpers.factories import create_group, create_organization, create_user


@pytest.mark.asyncio
async def test_first_user():
    organization = await Organization.create(domain="example.com")
    user1 = await create_user(email="foo@example.com", organization_id=organization.id)
    await create_user(email="foo2@example.com", organization_id=organization.id)

    first_user = await organization.first_user()
    assert first_user == user1


@pytest.mark.asyncio
async def test_email_aliases():
    organization = await Organization.create(domain="example.com")
    user1 = await create_user(email="dave@example.com", organization_id=organization.id)
    await EmailAlias.create(address="dave.daverson@example.com", user_id=user1.id)
    user2 = await create_user(email="alice@example.com", organization_id=organization.id)

    user = await User.filter(User.filters.by_email("dave@example.com")).first()
    assert user == user1

    user = await User.filter(User.filters.by_email("dave.daverson@example.com")).first()
    assert user == user1

    user = await User.filter(User.filters.by_email("alice@example.com")).first()
    assert user == user2

    user = await User.filter(User.filters.by_email("bruce@big.corp")).first()
    assert user is None


@pytest.mark.asyncio
async def test_email_alias_syncing():
    user = await create_user(email="bob@example.com")
    await user.fetch_related("email_aliases")
    assert len(user.email_aliases) == 1
    assert user.email_aliases[0].address == "bob@example.com"

    await user.sync_email_aliases(["bob@example.com", "bob.clams@example.com", "bob@example.com"])
    await user.fetch_related("email_aliases")
    assert len(user.email_aliases) == 2
    assert "bob@example.com" in [alias.address for alias in user.email_aliases]
    assert "bob.clams@example.com" in [alias.address for alias in user.email_aliases]

    await user.sync_email_aliases(["bob@example.com", "bob.alternate@example.com"])
    await user.fetch_related("email_aliases")
    assert len(user.email_aliases) == 2
    assert "bob@example.com" in [alias.address for alias in user.email_aliases]
    assert "bob.alternate@example.com" in [alias.address for alias in user.email_aliases]


@pytest_asyncio.fixture
async def untouched_control_user():
    token = Token.fake("dev@control.com")
    user, is_new_login, organization_was_created, _ = await User.get_or_create_by_oauth(token)
    assert is_new_login
    assert organization_was_created

    yield user

    await user.refresh_from_db()
    await user.fetch_related("oauth_tokens", "organization")

    assert user.email == "dev@control.com"
    assert user.oauth_authentication_token.access_token.startswith("fake-access")
    assert user.oauth_authentication_token.refresh_token.startswith("fake-refresh")
    assert user.oauth_authentication_token.expires_at > datetime.now(UTC)
    assert user.oauth_authentication_token.client_id.startswith("user")
    assert user.oauth_authentication_token.provider.is_testing
    assert user.oauth_authentication_token.scope == "openid email profile"
    assert user.organization.oidc_token == "hd:control.com"


@pytest.mark.asyncio
async def test_migrating_user_and_organization_to_oauth(untouched_control_user: User):
    # Logging in as a user that has not backfilled OIDC or Organization Code
    organization = await create_organization(name="Legacy Org", domain="convictional.com")
    user = await create_user(email="user@convictional.com", organization_id=organization.id)
    token = Token.fake("user@convictional.com")

    _, is_new_login, org_is_new, _ = await User.get_or_create_by_oauth(token)
    assert not is_new_login
    assert not org_is_new

    await user.refresh_from_db()
    await user.fetch_related("oauth_tokens", "organization")

    assert user.email == "user@convictional.com"
    assert user.oauth_authentication_token.access_token.startswith("fake-access")
    assert user.oauth_authentication_token.refresh_token.startswith("fake-refresh")
    assert user.oauth_authentication_token.expires_at > datetime.now(UTC)
    assert user.oauth_authentication_token.client_id.startswith("user")
    assert user.oauth_authentication_token.provider.is_testing
    assert user.oauth_authentication_token.scope == "openid email profile"
    assert user.organization.oidc_token == "hd:convictional.com"


@pytest.mark.asyncio
async def test_migrating_user_to_oauth(untouched_control_user: User):
    # Logging in as a user that has not backfilled OIDC
    organization = await create_organization(
        name="Legacy Org", domain="convictional.com", oidc_token="hd:convictional.com"
    )
    user = await create_user(email="user@convictional.com", organization_id=organization.id)
    token = Token.fake("user@convictional.com")

    _, is_new_login, org_is_new, _ = await User.get_or_create_by_oauth(token)
    assert not is_new_login
    assert not org_is_new

    await user.refresh_from_db()
    await user.fetch_related("oauth_tokens", "organization")

    assert user.email == "user@convictional.com"
    assert user.oauth_authentication_token.access_token.startswith("fake-access")
    assert user.oauth_authentication_token.refresh_token.startswith("fake-refresh")
    assert user.oauth_authentication_token.expires_at > datetime.now(UTC)
    assert user.oauth_authentication_token.client_id.startswith("user")
    assert user.oauth_authentication_token.provider.is_testing
    assert user.oauth_authentication_token.scope == "openid email profile"
    assert user.organization.oidc_token == "hd:convictional.com"


@pytest.mark.asyncio
async def test_get_or_create_by_oauth_rejects_blocked_login():
    # A blocked identity is rejected before any user row is created, so deletion +
    # blocklist keeps them out even though a login would otherwise recreate the account.
    settings.blocked_emails = {"kris.braun@gmail.com"}

    with pytest.raises(SignupBlockedError):
        await User.get_or_create_by_oauth(Token.fake("kris.braun@gmail.com"))

    assert await User.filter(User.filters.by_email_exact("kris.braun@gmail.com")).count() == 0


@pytest.mark.asyncio
async def test_get_or_create_by_oauth_honors_signup_freeze():
    organization = await create_organization(domain="frozen-example.com")
    existing = await create_user(email="existing@frozen-example.com", organization_id=organization.id)
    user_count = await User.all().count()
    organization_count = await Organization.all().count()

    with settings.override():
        settings.signups_enabled = False

        # A brand-new identity is refused before anything is written, so the freeze can't
        # leave a half-built account behind.
        with pytest.raises(SignupsDisabledError):
            await User.get_or_create_by_oauth(Token.fake("newcomer@brand-new-example.com"))

        # A colleague on a domain that already has an organization would otherwise be
        # auto-joined without an invite — that is a signup too, and it is frozen as well.
        with pytest.raises(SignupsDisabledError):
            await User.get_or_create_by_oauth(Token.fake("colleague@frozen-example.com"))

        assert await User.all().count() == user_count
        assert await Organization.all().count() == organization_count

        # Existing accounts are untouched by the freeze, including a deactivated user
        # logging back in — the row already exists, so no signup is happening.
        user, _, org_is_new, user_is_new = await User.get_or_create_by_oauth(Token.fake("existing@frozen-example.com"))
        assert user.id == existing.id
        assert not org_is_new
        assert not user_is_new

        await user.soft_delete()
        restored, _, _, _ = await User.get_or_create_by_oauth(Token.fake("existing@frozen-example.com"))
        assert restored.id == existing.id
        assert not restored.is_deleted


@pytest.mark.asyncio
async def test_new_user_and_organization(untouched_control_user: User):
    token = Token.fake("user@convictional.com")
    user, is_new_login, org_is_new, _ = await User.get_or_create_by_oauth(token)
    assert is_new_login
    assert org_is_new

    await user.refresh_from_db()
    await user.fetch_related("oauth_tokens", "organization")

    assert user.email == "user@convictional.com"
    assert user.oauth_authentication_token.access_token.startswith("fake-access")
    assert user.oauth_authentication_token.refresh_token.startswith("fake-refresh")
    assert user.oauth_authentication_token.expires_at > datetime.now(UTC)
    assert user.oauth_authentication_token.client_id.startswith("user")
    assert user.oauth_authentication_token.provider.is_testing
    assert user.oauth_authentication_token.scope == "openid email profile"
    assert user.organization.oidc_token == "hd:convictional.com"


@pytest.mark.asyncio
async def test_banned_domain_detection():
    # Test the is_domain_banned method
    assert not Organization.is_domain_banned("")
    assert not Organization.is_domain_banned("invalid-email")
    assert not Organization.is_domain_banned("user@allowed-domain.com")

    # Test with custom banned domains list
    test_banned_domains: list[str] = ["banned-domain.com", "another-banned.org"]
    assert Organization.is_domain_banned("user@banned-domain.com", test_banned_domains)
    assert Organization.is_domain_banned("user@another-banned.org", test_banned_domains)
    assert not Organization.is_domain_banned("user@allowed-domain.com", test_banned_domains)

    # Test oauth signup rejection with custom banned domains
    test_banned_domains = ["banned-domain.com"]
    token = Token.fake("user@banned-domain.com")

    with pytest.raises(SignupBlockedError):
        await User.get_or_create_by_oauth(token, test_banned_domains)

    # Test invite rejection with custom banned domains
    organization = await create_organization()
    inviter = await create_user(organization_id=organization.id)
    invite = Invite(inviter=inviter, email="someone@banned-domain.com", banned_domains=test_banned_domains)
    result = await invite.process()

    assert not result.success
    assert result.error == "This signup is banned"
    assert result.invited is None

    # Make sure non-banned domains still work (with empty banned domains list)
    test_banned_domains = []
    token = Token.fake("user@allowed-domain.com")
    user, is_new_login, org_is_new, _ = await User.get_or_create_by_oauth(token, test_banned_domains)

    assert is_new_login
    assert org_is_new
    assert user is not None
    assert user.email == "user@allowed-domain.com"

    # Test invite works for non-banned domains
    organization = await create_organization()
    inviter = await create_user(organization_id=organization.id)
    invite = Invite(inviter=inviter, email="someone@allowed-domain.com", banned_domains=test_banned_domains)
    result = await invite.process()

    assert result.success


@pytest.mark.asyncio
async def test_oauth_authentication_token_returns_token_with_client_id():
    user = await create_user(email="test@example.com")

    # Create a Google OAuth token (with client_id - provides identity)
    await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.GOOGLE,
        client_id="google-client-123",
        access_token="google-access-token",
        scope="openid email profile",
    )

    # Create a Slack OAuth token (without client_id - authorization only)
    await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        client_id=None,
        access_token="slack-access-token",
        scope="channels:read users:read",
    )

    await user.fetch_related("oauth_tokens")

    # oauth_authentication_token should return the Google token (has client_id)
    assert user.oauth_authentication_token is not None
    assert user.oauth_authentication_token.provider == AuthenticationProvider.GOOGLE
    assert user.oauth_authentication_token.client_id == "google-client-123"


@pytest.mark.asyncio
async def test_oauth_authentication_token_returns_newest_identity_token():
    user = await create_user(email="test@example.com")

    # Create an older Google token
    older_token = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.GOOGLE,
        client_id="old-google-client",
        access_token="old-google-token",
        scope="openid email",
    )

    # Manually set created_at to be in the past
    await OAuthToken.filter(id=older_token.id).update(created_at=datetime.now(UTC) - timedelta(days=1))

    # Create a newer TESTING token
    newer_token = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.TESTING,
        client_id="new-testing-client",
        access_token="new-testing-token",
        scope="openid email profile",
    )

    await user.fetch_related("oauth_tokens")

    # oauth_authentication_token should return the newer TESTING token
    assert user.oauth_authentication_token is not None
    assert user.oauth_authentication_token.id == newer_token.id
    assert user.oauth_authentication_token.provider == AuthenticationProvider.TESTING


@pytest.mark.asyncio
async def test_oauth_authentication_token_returns_none_when_no_identity_tokens():
    organization = await Organization.create(domain="example.com")
    user = await User.create(email="test@example.com", organization_id=organization.id)

    # Create only Slack tokens (no client_id - authorization only)
    await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        client_id=None,
        access_token="slack-access-token-1",
        scope="channels:read",
    )

    await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        client_id=None,
        access_token="slack-access-token-2",
        scope="users:read",
    )

    await user.fetch_related("oauth_tokens")

    # oauth_authentication_token should return None (no tokens with client_id)
    assert user.oauth_authentication_token is None


@pytest.mark.asyncio
async def test_oauth_token_for_provider_returns_correct_token():
    organization = await Organization.create(domain="example.com")
    user = await User.create(email="test@example.com", organization_id=organization.id)

    # Create tokens for different providers
    google_token = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.GOOGLE,
        client_id="google-client",
        access_token="google-token",
        scope="openid email profile",
    )

    slack_token = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        client_id=None,
        access_token="slack-token",
        scope="channels:read",
    )

    testing_token = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.TESTING,
        client_id="testing-client",
        access_token="testing-token",
        scope="openid email",
    )

    await user.fetch_related("oauth_tokens")

    # Should return the Google token when requested
    google_result = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert google_result is not None
    assert google_result.id == google_token.id
    assert google_result.provider == AuthenticationProvider.GOOGLE

    # Should return the Slack token when requested
    slack_result = user.oauth_token_for_provider(AuthenticationProvider.SLACK)
    assert slack_result is not None
    assert slack_result.id == slack_token.id
    assert slack_result.provider == AuthenticationProvider.SLACK

    # Should return the TESTING token when requested
    testing_result = user.oauth_token_for_provider(AuthenticationProvider.TESTING)
    assert testing_result is not None
    assert testing_result.id == testing_token.id
    assert testing_result.provider == AuthenticationProvider.TESTING


@pytest.mark.asyncio
async def test_oauth_token_for_provider_returns_none_when_no_tokens():
    organization = await Organization.create(domain="example.com")
    user = await User.create(email="test@example.com", organization_id=organization.id)
    await user.fetch_related("oauth_tokens")

    # Should return None when user has no tokens
    assert user.oauth_token_for_provider(AuthenticationProvider.GOOGLE) is None
    assert user.oauth_token_for_provider(AuthenticationProvider.SLACK) is None


@pytest.mark.asyncio
async def test_oauth_token_for_provider_returns_newest_token_for_provider():
    user = await create_user(email="test@example.com")

    # Create an older Google token
    older_google = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.GOOGLE,
        client_id="old-google",
        access_token="old-token",
        scope="openid email",
    )

    await OAuthToken.filter(id=older_google.id).update(created_at=datetime.now(UTC) - timedelta(hours=2))

    # Create a newer Google token
    newer_google = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.GOOGLE,
        client_id="new-google",
        access_token="new-token",
        scope="openid email profile",
    )

    await user.fetch_related("oauth_tokens")

    # Should return the newer Google token
    result = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert result is not None
    assert result.id == newer_google.id
    assert result.client_id == "new-google"


@pytest.mark.asyncio
async def test_soft_deleted_user_respects_banned_domains():
    test_domain = "example-test.com"

    # Test basic user creation
    token = Token.fake(f"user@{test_domain}")
    user, _, _, _ = await User.get_or_create_by_oauth(token, [])
    assert user is not None
    assert user.email == f"user@{test_domain}"

    # Test soft-deleted user with banned domain
    await user.soft_delete()
    token = Token.fake(f"user@{test_domain}")
    with pytest.raises(SignupBlockedError):
        await User.get_or_create_by_oauth(token, [test_domain])

    # Test soft-deleted user with non-banned domain
    user, _, _, _ = await User.get_or_create_by_oauth(token, [])
    assert user is not None
    assert not user.is_deleted
    assert user.email == f"user@{test_domain}"


@pytest.mark.asyncio
async def test_get_or_create_by_oauth_with_null_refresh_token():
    # Create a fake token and modify it to have null refresh_token
    token = Token.fake("test@example.com")
    token.refresh_token = None

    # Verify token has null refresh_token
    assert token.refresh_token is None
    assert token.id_token_model.email == "test@example.com"

    # This should not raise an exception despite null refresh_token
    user, is_new_login, org_is_new, _ = await User.get_or_create_by_oauth(token)
    assert user is not None
    assert is_new_login
    assert org_is_new
    assert user.email == "test@example.com"

    # Verify the user's OAuth token was created properly with null refresh_token
    await user.fetch_related("oauth_tokens")
    assert len(user.oauth_tokens) == 1
    oauth_token = user.oauth_tokens[0]
    assert oauth_token.refresh_token is None
    assert oauth_token.access_token == token.access_token


@pytest.mark.asyncio
async def test_group_add_and_remove_member():
    user = await create_user()
    group = await create_group(organization_id=user.organization_id)

    group_member = await group.add_member(user)
    assert group_member.user_id == user.id

    with pytest.raises(ValueError, match="already a member"):
        await group.add_member(user)

    await group.remove_member(user)

    with pytest.raises(ValueError, match="not a member"):
        await group.remove_member(user)


@pytest.mark.asyncio
async def test_group_filters():
    alice = await create_user(name="Alice")
    bob = await create_user(name="Bob", organization_id=alice.organization_id)

    group1 = await create_group(name="Group 1", organization_id=alice.organization_id)
    group2 = await create_group(name="Group 2", organization_id=alice.organization_id)
    await group1.add_member(alice)
    await group2.add_member(alice)
    await group2.add_member(bob)

    org_groups = await Group.filter(Group.filters.by_organization(alice.organization_id))
    assert len(org_groups) == 2

    alice_groups = await Group.filter(Group.filters.by_member(alice.id))
    assert len(alice_groups) == 2

    bob_groups = await Group.filter(Group.filters.by_member(bob.id))
    assert len(bob_groups) == 1


@pytest.mark.asyncio
async def test_group_soft_delete():
    user = await create_user()
    group = await create_group(organization_id=user.organization_id)
    group_id = group.id

    await group.soft_delete()

    assert await Group.get_or_none(id=group_id) is None

    deleted_group = await Group.unscoped.get_or_none(id=group_id)
    assert deleted_group is not None
    assert deleted_group.is_deleted is True


@pytest.mark.asyncio
async def test_user_deactivate_and_reactivate():
    # The roster broadcast each of these fires is asserted end-to-end (over a real channel) in
    # tests/integration/channels/test_organization_members.py; here we pin the state machine and
    # its idempotent return contract.
    user = await create_user()

    assert await user.deactivate() is True
    assert user.is_deleted and user.last_logout_at is not None
    deactivated_at = user.deleted_at

    # Already deactivated: no-op (returns False) without re-stamping deleted_at.
    assert await user.deactivate() is False
    assert user.deleted_at == deactivated_at

    assert await user.reactivate() is True
    assert not user.is_deleted

    # Already active: no-op.
    assert await user.reactivate() is False


@pytest.mark.asyncio
async def test_oauth_token_is_expired_and_credentials_expiry():
    now = datetime.now(UTC)

    # A token comfortably in the future is not expired; one in the past is.
    assert OAuthToken(expires_at=now + timedelta(hours=1)).is_expired is False
    assert OAuthToken(expires_at=now - timedelta(hours=1)).is_expired is True

    # Within the proactive-refresh buffer, we treat it as expired so we refresh
    # rather than hand out a token that could die mid-request.
    assert OAuthToken(expires_at=now + timedelta(minutes=1)).is_expired is True

    # Unknown expiry is treated as expired, and has no google-auth expiry.
    unknown = OAuthToken(expires_at=None)
    assert unknown.is_expired is True
    assert unknown.credentials_expiry is None

    # credentials_expiry converts to the naive UTC datetime google-auth requires,
    # normalizing away any non-UTC tzinfo first.
    aware = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    expiry = OAuthToken(expires_at=aware).credentials_expiry
    assert expiry == datetime(2026, 1, 1, 17, 0)
    assert expiry.tzinfo is None


def _google_login_token(email: str, scopes: list[str], *, access_token: str, refresh_token: str | None) -> Token:
    # All OAuth clients for the same Google account share one `sub`, so building
    # the token from the same email reproduces the single shared token row.
    token = Token.fake(email, scopes=scopes)
    token.provider = AuthenticationProvider.GOOGLE
    token.access_token = access_token
    token.refresh_token = refresh_token
    return token


async def _google_token(user: User) -> OAuthToken:
    return await OAuthToken.get(user_id=user.id, provider=AuthenticationProvider.GOOGLE)


@pytest.mark.asyncio
async def test_create_or_update_by_token_reconciles_scopes_across_logins():
    all_scopes = GOOGLE_DEFAULT_SCOPES + GOOGLE_GMAIL_SCOPES

    # A narrower login (e.g. an identity-only sign in from another client) must not
    # drop the broader client's scopes or swap in its access/refresh token.
    downgrade_user = await create_user(email="downgrade@example.com")
    await OAuthToken.create_or_update_by_token(
        downgrade_user, _google_login_token(downgrade_user.email, all_scopes, access_token="web", refresh_token="web")
    )
    await OAuthToken.create_or_update_by_token(
        downgrade_user,
        _google_login_token(
            downgrade_user.email, GOOGLE_DEFAULT_SCOPES, access_token="mobile", refresh_token="mobile"
        ),
    )
    token = await _google_token(downgrade_user)
    assert token.has_scopes(GOOGLE_GMAIL_SCOPES) is True
    assert token.access_token == "web"
    assert token.refresh_token == "web"

    # A broader login (connecting Gmail after an identity-only sign in) adopts the
    # new credential, including the freshly issued refresh token.
    upgrade_user = await create_user(email="upgrade@example.com")
    await OAuthToken.create_or_update_by_token(
        upgrade_user,
        _google_login_token(upgrade_user.email, GOOGLE_DEFAULT_SCOPES, access_token="signin", refresh_token="signin"),
    )
    await OAuthToken.create_or_update_by_token(
        upgrade_user,
        _google_login_token(upgrade_user.email, all_scopes, access_token="connect", refresh_token="connect"),
    )
    token = await _google_token(upgrade_user)
    assert token.has_scopes(GOOGLE_GMAIL_SCOPES) is True
    assert token.access_token == "connect"
    assert token.refresh_token == "connect"

    # A repeat login with the same scopes refreshes the access token; Google omits
    # the refresh token on repeat logins, so the stored one must be preserved.
    repeat_user = await create_user(email="repeat@example.com")
    await OAuthToken.create_or_update_by_token(
        repeat_user,
        _google_login_token(repeat_user.email, all_scopes, access_token="access-1", refresh_token="refresh-1"),
    )
    await OAuthToken.create_or_update_by_token(
        repeat_user, _google_login_token(repeat_user.email, all_scopes, access_token="access-2", refresh_token=None)
    )
    token = await _google_token(repeat_user)
    assert token.has_scopes(GOOGLE_GMAIL_SCOPES) is True
    assert token.access_token == "access-2"
    assert token.refresh_token == "refresh-1"
