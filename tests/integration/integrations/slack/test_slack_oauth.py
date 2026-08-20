import pytest
from fastapi import status

from app.models.accounts import OAuthToken, Organization, User
from config.enums import AuthenticationProvider
from integrations.slack.oauth import get_slack_oauth_token
from tests.helpers.app import AppClient


@pytest.mark.asyncio
async def test_slack_oauth_connect_redirects_to_slack(client: AppClient):
    """Test that visiting the connect endpoint redirects to Slack's authorization URL."""
    response = await client.get("/integrations/slack/connect", follow_redirects=False)

    assert response.status_code == status.HTTP_303_SEE_OTHER
    redirect_url = response.headers["location"]
    assert redirect_url.startswith("https://slack.com/oauth/v2/authorize")
    assert "client_id" in redirect_url
    assert "user_scope" in redirect_url
    assert "redirect_uri" in redirect_url


@pytest.mark.asyncio
async def test_slack_oauth_callback_error_from_slack(client: AppClient):
    """Test handling when Slack returns an error."""
    response = await client.get(
        "/auth/slack/callback?error=access_denied",
        follow_redirects=False,
    )

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"].endswith("/profile/edit")


@pytest.mark.asyncio
async def test_slack_oauth_callback_missing_code(client: AppClient):
    """Test handling when no authorization code is provided."""
    response = await client.get("/auth/slack/callback", follow_redirects=False)

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"].endswith("/profile/edit")


@pytest.mark.asyncio
async def test_get_slack_oauth_token_helper(client: AppClient):
    """Test the get_slack_oauth_token helper function."""
    user = await client.get_default_user()

    # No token initially
    oauth_token = await get_slack_oauth_token(user)
    assert oauth_token is None

    # Create a Slack OAuth token
    created_token = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        client_id="slack_user_123",
        access_token="xoxp-test-token",
        scope="channels:read,users:read",
        expires_at=None,
    )

    # Should retrieve the token
    oauth_token = await get_slack_oauth_token(user)
    assert oauth_token is not None
    assert oauth_token.id == created_token.id
    assert oauth_token.provider == AuthenticationProvider.SLACK
    assert oauth_token.access_token == "xoxp-test-token"

    # Different user should not get the first user's token
    other_org = await Organization.create(name="Other Org", domain="other.com")
    other_user = await User.create(
        email="other@example.com",
        name="Other User",
        provider=AuthenticationProvider.TESTING,
        organization_id=other_org.id,
    )
    other_token = await get_slack_oauth_token(other_user)
    assert other_token is None
