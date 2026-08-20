"""
API endpoints for the mobile/native Google flow.

Lives in `integrations/google/` because the handlers reach
`GoogleAuthenticator`, and the .importlinter contract forbids
`app -> integrations`. Mounted under `/api/...` from `app/main.py` so its
routes land alongside the rest of the `/api` surface.

The browser-redirect `/auth/google` flow stays in `router.py`; everything
mobile/native lands here. `sync_google_email_aliases` continues to live in
`router.py` since both flows use it.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.routers.dependencies import Authentication, get_authentication, get_or_create_user
from config import settings
from infra.oauth import InvalidGrantError, Token
from integrations.google.oauth import GoogleAuthenticator
from integrations.google.router import sync_google_email_aliases

# Three sources of truth for this string — no shared package yet, so drift
# breaks auth silently. If you change one, change the others:
#   1. This constant.
#   2. The identically-named `IOS_OAUTH_REDIRECT_URI` in
#      `app/mobile/lib/auth.ts` (sent by expo-auth-session as the OAuth
#      redirect_uri parameter, must equal what we send to Google's token endpoint).
#   3. The "Custom URI scheme" / authorized redirect URI configured on the iOS
#      OAuth client in Google Cloud Console (Google validates the redirect URI
#      at exchange time and rejects mismatches with `invalid_grant`).
# The shape (`com.<reverse-DNS-bundle-id>:/oauth2redirect`) is Google's iOS
# convention; see https://developers.google.com/identity/protocols/oauth2/native-app.
IOS_OAUTH_REDIRECT_URI = "com.convictional.app:/oauth2redirect"


api_router = APIRouter(tags=["auth", "skip_onboarding"])


class GoogleNativeAuthRequest(BaseModel):
    # Both fields are bearer credentials — wrapping in SecretStr keeps them
    # out of Pydantic ValidationError reprs and any structured logging the
    # middleware emits on errors.
    code: SecretStr = Field(..., min_length=1, max_length=2048)
    code_verifier: SecretStr = Field(..., min_length=43, max_length=128)


# See app/main.py CSRF exemption list for why this endpoint is exempt
# (PKCE code_verifier replaces the CSRF token).
@api_router.post("/api/auth/google", status_code=status.HTTP_204_NO_CONTENT)
async def api_auth_google(
    body: GoogleNativeAuthRequest,
    authentication: Authentication = Depends(get_authentication),
) -> None:
    if not settings.google_oauth_ios_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native OAuth is not configured on this environment.",
        )

    authenticator = GoogleAuthenticator(redirect_uri=IOS_OAUTH_REDIRECT_URI)

    try:
        token = await authenticator.get_token(
            body.code.get_secret_value(),
            code_verifier=body.code_verifier.get_secret_value(),
            client_id=settings.google_oauth_ios_client_id,
            redirect_uri=IOS_OAUTH_REDIRECT_URI,
        )
    except InvalidGrantError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code was invalid or expired.",
        ) from exc

    if not token.id_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID token not found in response.",
        )

    user = await get_or_create_user(authentication, token)
    await sync_google_email_aliases(token, user)


# Test-only twin of /api/auth/google. Mirrors the /login/fake pattern in
# app/routers/auth.py: gated by settings.enable_fake_auth so it never
# registers in production. Tests POST {"email": "..."} and get the same
# session-cookie outcome as the real endpoint, without needing a real
# Google authorization code.
if settings.enable_fake_auth:

    class NativeAuthFakeRequest(BaseModel):
        email: EmailStr

    @api_router.post("/api/auth/google/fake", status_code=status.HTTP_204_NO_CONTENT)
    async def api_auth_google_fake(
        body: NativeAuthFakeRequest,
        authentication: Authentication = Depends(get_authentication),
    ) -> None:
        await get_or_create_user(authentication, Token.fake(body.email))
