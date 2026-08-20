from integrations.microsoft.oauth import MicrosoftAuthenticator


def test_microsoft_authenticator():
    authenticator = MicrosoftAuthenticator("http://localhost")

    # scenario: provider identity and redirect wiring mirror GoogleAuthenticator
    assert authenticator.provider.is_microsoft
    assert authenticator.redirect_uri == "http://localhost"

    # scenario: class-level endpoints point at Microsoft's identity platform
    assert "login.microsoftonline.com" in MicrosoftAuthenticator.auth_url
    assert "login.microsoftonline.com" in MicrosoftAuthenticator.token_url

    # scenario: default scopes match the base OIDC set
    assert MicrosoftAuthenticator.default_scopes == ["openid", "email", "profile"]
