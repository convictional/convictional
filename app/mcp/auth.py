from urllib.parse import urljoin

from cryptography.fernet import Fernet
from fastmcp import Context
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.debug import DebugTokenVerifier
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from app.models.accounts import OAuthToken, User
from config import settings
from config.enums import AuthenticationProvider
from infra.cache import CacheKeyValueStore

USER_STATE_KEY = "user"


async def get_current_user(ctx: Context) -> User:
    user = await ctx.get_state(USER_STATE_KEY)
    if not user:
        raise ToolError("Authentication required")
    return user


class FakeUserContextMiddleware(Middleware):
    async def on_request(self, context: MiddlewareContext, call_next):
        access_token = get_access_token()
        if access_token:
            email = access_token.token
            user = await User.get_or_none(email=email).prefetch_related(
                "organization", "group_memberships__group", "avatar_file"
            )
            if not user:
                raise ToolError("No account found. Please sign up at the web app first.")
            if context.fastmcp_context:
                await context.fastmcp_context.set_state(USER_STATE_KEY, user, serializable=False)
        return await call_next(context)


class UserContextMiddleware(Middleware):
    async def on_request(self, context: MiddlewareContext, call_next):
        access_token = get_access_token()
        if access_token:
            sub = access_token.claims.get("sub")
            if not sub:
                raise ToolError("No account found. Please sign up at the web app first.")

            oauth_token = await OAuthToken.get_or_none(
                provider=AuthenticationProvider.GOOGLE,
                client_id=sub,
            ).prefetch_related("user__organization", "user__group_memberships__group", "user__avatar_file")

            if not oauth_token:
                raise ToolError("No account found. Please sign up at the web app first.")

            if context.fastmcp_context:
                await context.fastmcp_context.set_state(USER_STATE_KEY, oauth_token.user, serializable=False)
        return await call_next(context)


def create_auth_provider() -> tuple[AuthProvider, Middleware]:
    if settings.has_google_oauth and not settings.enable_mcp_fake_auth:
        provider_kwargs: dict = {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret.get_secret_value(),
            "base_url": urljoin(str(settings.base_url), "/mcp"),
            "required_scopes": ["openid", "https://www.googleapis.com/auth/userinfo.email"],
        }

        if settings.mcp_jwt_signing_key:
            provider_kwargs["jwt_signing_key"] = settings.mcp_jwt_signing_key.get_secret_value()

        if settings.mcp_storage_encryption_key:
            provider_kwargs["client_storage"] = FernetEncryptionWrapper(
                key_value=CacheKeyValueStore(),
                fernet=Fernet(settings.mcp_storage_encryption_key.get_secret_value()),
            )

        provider = GoogleProvider(**provider_kwargs)
        return provider, UserContextMiddleware()

    # Fall back to fake auth for development without Google OAuth
    return (
        DebugTokenVerifier(client_id="test-client", scopes=["openid", "email"]),
        FakeUserContextMiddleware(),
    )
