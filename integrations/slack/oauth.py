from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk.web.async_client import AsyncWebClient

from app.models.accounts import OAuthToken, User
from config.enums import AuthenticationProvider
from config.settings import settings
from infra.oauth import InvalidGrantError, OAuthAuthenticator, Token

SLACK_DEFAULT_SCOPES = [
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "users:read",
    "users:read.email",
    "team:read",
    "search:read",
]


class SlackAuthenticator(OAuthAuthenticator):
    provider = AuthenticationProvider.SLACK
    auth_url = "https://slack.com/oauth/v2/authorize"
    token_url = "https://slack.com/api/oauth.v2.access"
    default_scopes = SLACK_DEFAULT_SCOPES

    def __init__(self, redirect_uri: str):
        self.client_id = settings.slack_oauth_client_id
        self.client_secret = settings.slack_oauth_client_secret.get_secret_value()
        self.redirect_uri = redirect_uri

    def get_authorization_url(self, scopes: list[str] | None = None, **kwargs) -> str:
        return AuthorizeUrlGenerator(
            client_id=self.client_id,
            user_scopes=scopes or self.default_scopes,
            redirect_uri=self.redirect_uri,
        ).generate(self.redirect_uri)

    # Slack uses its own SDK (oauth.v2.access), not the generic token endpoint
    # the base class targets — PKCE overrides don't apply here. The narrow
    # signature is intentional; mypy's override warning is silenced.
    async def get_token(self, code: str) -> Token:  # type: ignore[override]
        client = AsyncWebClient()
        oauth_response = await client.oauth_v2_access(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            code=code,
        )

        if not isinstance(oauth_response.data, dict):
            raise Exception("Unexpected response format from Slack OAuth")

        data: dict = oauth_response.data

        if not data.get("ok"):
            error = data.get("error")
            if error == "invalid_grant":
                raise InvalidGrantError(data.get("error_description", "Invalid authorization code"))
            else:
                raise Exception(f"Slack OAuth error: {error}")

        authed_user = data.get("authed_user", {})
        access_token = authed_user.get("access_token")
        scope = authed_user.get("scope", "")

        token = Token(
            provider=self.provider,
            access_token=access_token,
            token_type="Bearer",
            expires_in=0,
            scope=scope,
        )

        return token


async def get_slack_oauth_token(user: User) -> OAuthToken | None:
    await user.fetch_related("oauth_tokens")
    return user.oauth_token_for_provider(AuthenticationProvider.SLACK)
