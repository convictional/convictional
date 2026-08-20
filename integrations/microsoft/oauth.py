from config import settings
from config.enums import AuthenticationProvider
from infra.oauth import OAuthAuthenticator

# SSO identity only — these are OpenID Connect scopes that populate ID-token
# claims and grant NO Microsoft Graph access. Do not add more:
#   openid  → required; returns the ID token + sub/aud/iss/iat/exp (and `tid`).
#   email   → the `email` claim, which login requires.
#   profile → `name` / `picture` claims.
# Deliberately excluded: offline_access, User.Read, any Mail/Files/Calendar scope.
MICROSOFT_DEFAULT_SCOPES = ["openid", "email", "profile"]


class MicrosoftAuthenticator(OAuthAuthenticator):
    auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    default_scopes = MICROSOFT_DEFAULT_SCOPES

    def __init__(self, redirect_uri: str):
        self.provider = AuthenticationProvider.MICROSOFT
        self.client_id = settings.microsoft_oauth_client_id
        self.client_secret = settings.microsoft_oauth_client_secret.get_secret_value()
        self.redirect_uri = redirect_uri
