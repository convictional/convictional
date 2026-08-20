from google.auth.exceptions import RefreshError

from integrations.google.oauth import GoogleAuthenticator, is_reauth_required_error


def test_google_authenticator():
    authenticator = GoogleAuthenticator("http://localhost")
    assert authenticator.provider.is_google
    assert authenticator.redirect_uri == "http://localhost"


def test_is_reauth_required_error_with_invalid_grant():
    error = RefreshError("invalid_grant: Token has been expired or revoked")
    assert is_reauth_required_error(error) is True


def test_is_reauth_required_error_with_invalid_scope():
    error = RefreshError("invalid_scope: Bad Request")
    assert is_reauth_required_error(error) is True


def test_is_reauth_required_error_with_unauthorized_client():
    error = RefreshError("('unauthorized_client: Unauthorized', {'error': 'unauthorized_client'})")
    assert is_reauth_required_error(error) is True


def test_is_reauth_required_error_with_server_error():
    error = RefreshError("server_error: Internal Server Error")
    assert is_reauth_required_error(error) is False


def test_is_reauth_required_error_with_network_error():
    error = RefreshError("network_error: Failed to connect")
    assert is_reauth_required_error(error) is False


def test_is_reauth_required_error_with_multiple_errors_containing_invalid_grant():
    error = RefreshError("Multiple issues: invalid_grant and other problems")
    assert is_reauth_required_error(error) is True


def test_is_reauth_required_error_with_multiple_errors_containing_invalid_scope():
    error = RefreshError("Error occurred: invalid_scope in request")
    assert is_reauth_required_error(error) is True


def test_is_reauth_required_error_with_empty_message():
    error = RefreshError("")
    assert is_reauth_required_error(error) is False
