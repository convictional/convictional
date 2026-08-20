#!/usr/bin/env python3

import asyncio
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from integrations.google.oauth import GOOGLE_DEFAULT_SCOPES, GOOGLE_GMAIL_SCOPES, GoogleAuthenticator
from scripts.helpers import green_text, red_text


class GoogleAuthenticatorWithOfflineAccess(GoogleAuthenticator):
    def get_authorization_url(self, scopes: list[str] | None = None, **kwargs) -> str:
        if scopes is None:
            # Include openid, email, profile scopes to get user info in ID token
            scopes = GOOGLE_DEFAULT_SCOPES + GOOGLE_GMAIL_SCOPES

        kwargs.update(
            {
                "access_type": "offline",
                "prompt": "consent",
            }
        )

        return super().get_authorization_url(scopes, **kwargs)


class CallbackHandler(BaseHTTPRequestHandler):
    def __init__(self, callback_storage, *args, **kwargs):
        self.callback_storage = callback_storage
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if "code" in query_params:
            auth_code = query_params["code"][0]
            self.callback_storage["auth_code"] = auth_code

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            success_html = """
            <html>
                <head><title>Gmail OAuth Success</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: green;">Gmail OAuth Authorization Successful!</h1>
                    <p>Authorization code received successfully.</p>
                    <p>You can close this window and return to the terminal.</p>
                    <script>
                        setTimeout(function() {
                            window.close();
                        }, 3000);
                    </script>
                </body>
            </html>
            """
            self.wfile.write(success_html.encode("utf-8"))
        elif "error" in query_params:
            error = query_params["error"][0]
            self.callback_storage["error"] = error

            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error_html = f"""
            <html>
                <head><title>Gmail OAuth Error</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: red;">Gmail OAuth Authorization Failed</h1>
                    <p>Error: {error}</p>
                    <p>You can close this window and return to the terminal.</p>
                </body>
            </html>
            """
            self.wfile.write(error_html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_callback_server(callback_storage, port=8080):
    def handler(*args, **kwargs):
        return CallbackHandler(callback_storage, *args, **kwargs)

    server = HTTPServer(("localhost", port), handler)
    server.handle_request()
    server.server_close()


async def get_oauth_token():
    print("Gmail OAuth Refresh Token Storage Script")
    print("=" * 50)

    port = 8080
    redirect_uri = f"http://localhost:{port}"

    callback_storage: dict[str, Any] = {}

    server_thread = threading.Thread(target=start_callback_server, args=(callback_storage, port), daemon=True)
    server_thread.start()

    authenticator = GoogleAuthenticatorWithOfflineAccess(redirect_uri)
    # Pass None to use the default scopes which include openid, email, profile + Gmail scopes
    auth_url = authenticator.get_authorization_url()

    print(green_text("\nOpening browser for OAuth authorization..."))
    print(f"If the browser doesn't open, visit: {auth_url}")
    print(f"Local server started on port {port} waiting for OAuth callback...")

    webbrowser.open(auth_url)

    print("\n⏳ Waiting for OAuth callback...")

    timeout = 120
    for _ in range(timeout):
        if "auth_code" in callback_storage or "error" in callback_storage:
            break
        await asyncio.sleep(1)
    else:
        print(red_text(f"\nTimeout after {timeout} seconds. Please try again."))
        return

    if "error" in callback_storage:
        print(red_text(f"\nOAuth error: {callback_storage['error']}"))
        return

    auth_code = callback_storage.get("auth_code")
    if not auth_code:
        print(red_text("\nNo authorization code received."))
        return

    print(green_text("\nAuthorization code received..."))

    print("\nExchanging authorization code for tokens...")
    print(f"Using client ID: {authenticator.client_id}")
    print(f"Using redirect URI: {authenticator.redirect_uri}")
    token = await authenticator.get_token(auth_code)

    print(green_text("\nSuccessfully obtained tokens!"))

    if not token.refresh_token:
        print(red_text("\n No refresh token received. This might happen if:"))
        print("- You've already authorized this app (try revoking and re-authorizing)")
        print("- The OAuth client isn't configured for offline access")
        return

    id_token_data = token.id_token_model
    email = None

    email = id_token_data.email

    if not email or "@" not in email:
        print("Invalid email address from google account")
        return

    return token, email


if __name__ == "__main__":
    asyncio.run(get_oauth_token())
