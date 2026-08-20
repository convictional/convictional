import hashlib
from datetime import UTC, datetime, timedelta
from time import time
from urllib.parse import urlencode

import aiohttp
import jwt
from fastapi import status
from pydantic import BaseModel, Field, model_validator

from config import settings
from config.enums import AuthenticationProvider

FAKE_TOKEN_TTL = 3600  # 1 hour


def login_redirect_uri(provider: str, local_url: str) -> str:
    """OAuth callback URI for an SSO login.

    The provider path is always appended here so a new provider can never inherit
    another's callback path. In demo, callbacks route through the shared oauth-proxy
    (`oauth_proxy_url`); elsewhere the app's own `local_url` is used unchanged.
    """
    if settings.oauth_proxy_url:
        return f"{settings.oauth_proxy_url.rstrip('/')}/auth/{provider}"
    return local_url


class IDToken(BaseModel):
    provider: AuthenticationProvider = Field(default=AuthenticationProvider.TESTING)
    aud: str
    exp: int
    iat: int
    iss: str
    sub: str

    name: str | None = None
    email: str | None = None
    email_verified: bool | None = None
    picture: str | None = None
    # Microsoft Entra (work/school) accounts frequently omit the `email` claim
    # and carry the address in `preferred_username` (the UPN) instead. Google
    # never sends this claim, so the fallback below only affects Microsoft.
    preferred_username: str | None = None

    # Organization Codes
    hd: str | None = None  # Google provides Hosted Domain
    tid: str | None = None  # Microsoft provides Tenant ID

    @model_validator(mode="after")
    def _fall_back_to_preferred_username_for_email(self):
        if not self.email and self.preferred_username:
            self.email = self.preferred_username
        return self

    @classmethod
    def from_jwt(cls, id_token: str):
        token_dict = jwt.decode(id_token, options={"verify_signature": False})
        return cls(**token_dict)

    @property
    def organization_code(self):
        """
        If present, the organization code is used to tie the user to an external organization.
        """
        if self.hd:
            return f"hd:{self.hd}"
        if self.tid:
            return f"tid:{self.tid}"
        return None


class Token(BaseModel):
    provider: AuthenticationProvider = Field(default=AuthenticationProvider.TESTING)
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    scope: str
    id_token: str | None = None
    created_at: float = Field(default_factory=time)

    @classmethod
    def fake(cls, email: str, scopes: list[str] | None = None):
        now = int(time())
        name, domain = email.split("@")
        deterministic_user_id = hashlib.md5(email.encode("utf-8")).hexdigest()

        id_token_payload = {
            "aud": "fake-client-id",
            "iat": now,
            "exp": now + FAKE_TOKEN_TTL,
            "iss": "https://fake-issuer.example.com",
            "sub": f"user-{deterministic_user_id}",
            "name": name,
            "email": email,
            "email_verified": True,
            "hd": domain,
        }

        return cls(
            provider=AuthenticationProvider.TESTING,
            access_token=f"fake-access-{deterministic_user_id}",
            token_type="Bearer",
            expires_in=3600,
            refresh_token=f"fake-refresh-{deterministic_user_id}",
            scope=" ".join(scopes) if scopes else "openid email profile",
            id_token=jwt.encode(id_token_payload, "fake-secret-key-for-testing-only!", algorithm="HS256"),
        )

    @property
    def id_token_model(self):
        if not self.id_token:
            return None

        result = IDToken.from_jwt(self.id_token)
        result.provider = self.provider
        return result

    @property
    def expires_at(self):
        return datetime.fromtimestamp(self.created_at, tz=UTC) + timedelta(seconds=self.expires_in)


class InvalidGrantError(Exception):
    pass


class OAuthAuthenticator:
    """
    Base class for all authenticators.
    Authenticators handle OAuth2 authentication.
    """

    provider: AuthenticationProvider
    auth_url: str
    token_url: str

    client_id: str
    client_secret: str
    redirect_uri: str
    default_scopes: list[str] = ["openid", "email", "profile"]

    def get_authorization_url(self, scopes: list[str] | None = None, **kwargs) -> str:
        if scopes is None:
            scopes = self.default_scopes

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            **kwargs,
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def get_token(
        self,
        code: str,
        *,
        code_verifier: str | None = None,
        client_id: str | None = None,
        redirect_uri: str | None = None,
    ) -> Token:
        """
        Get the token from the OAuth2 flow.

        When ``code_verifier`` is provided, the request is treated as a PKCE
        exchange and ``client_secret`` is omitted — that's the only valid
        shape for public clients like our iOS native app. ``client_id`` and
        ``redirect_uri`` can be overridden per call so the same authenticator
        class can serve both the web client (default fields) and a native
        client (overrides) without subclassing.
        """
        data: dict[str, str] = {
            "code": code,
            "client_id": client_id or self.client_id,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        else:
            data["client_secret"] = self.client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=data) as response:
                response_data = await response.json()
                if response.status != status.HTTP_200_OK:
                    await self.handle_error(response_data)
                return Token(provider=self.provider, **response_data)

    async def handle_error(self, data: dict):
        """
        Handle errors from the OAuth2 flow.
        """
        # https://tools.ietf.org/html/rfc6749#section-5.2
        error = data.get("error")
        # This indicates that the authorization code is invalid.
        # This can happen if the user tries to use the same code twice.
        if error == "invalid_grant":
            raise InvalidGrantError(data.get("error_description"))
        else:
            raise Exception(data)
