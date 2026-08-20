import json
import re
from base64 import b64decode, b64encode

from itsdangerous.exc import BadSignature
from starlette.datastructures import MutableHeaders
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import HTTPConnection
from starlette.types import Message, Receive, Scope, Send


class ModifiableSessionDict(dict):
    """
    A dict subclass that tracks whether it has been modified.
    Only sends Set-Cookie header when the session has been modified.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._modified = False

    @property
    def modified(self) -> bool:
        return self._modified

    def mark_modified(self):
        self._modified = True

    def __setitem__(self, key, value):
        self._modified = True
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self._modified = True
        super().__delitem__(key)

    def clear(self):
        if len(self) > 0:
            self._modified = True
        super().clear()

    def pop(self, *args, **kwargs):
        if args[0] in self:
            self._modified = True
        return super().pop(*args, **kwargs)

    def popitem(self):
        self._modified = True
        return super().popitem()

    def setdefault(self, key, default=None):
        if key not in self:
            self._modified = True
        return super().setdefault(key, default)

    def update(self, *args, **kwargs):
        self._modified = True
        super().update(*args, **kwargs)


class LazySessionMiddleware(SessionMiddleware):
    """
    Session middleware that only sends Set-Cookie headers when the session is modified.
    This allows GET requests with unmodified sessions to be cached by browsers and CDNs.
    """

    # JS-readable marker cookie that mirrors whether an authenticated session exists.
    # A client-side `pageshow` guard reads this to detect a back-button restore of an
    # authenticated page after logout (replacing the old Clear-Site-Data eviction).
    marker_cookie = "logged_in"

    @property
    def marker_security_flags(self) -> str:
        # Mirror the session cookie's flags but drop HttpOnly so document.cookie can read it.
        return re.sub(r"httponly;?\s*", "", self.security_flags, flags=re.IGNORECASE).strip()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        if self.session_cookie in connection.cookies:
            data = connection.cookies[self.session_cookie].encode("utf-8")
            try:
                data = self.signer.unsign(data, max_age=self.max_age)
                scope["session"] = ModifiableSessionDict(json.loads(b64decode(data)))
                initial_session_was_empty = False
            except BadSignature:
                scope["session"] = ModifiableSessionDict()
        else:
            scope["session"] = ModifiableSessionDict()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                session = scope["session"]

                if session and session.modified:
                    # Session was modified, send Set-Cookie to persist it
                    data = self._encode_session(dict(session))
                    headers = MutableHeaders(scope=message)
                    headers.append("Set-Cookie", self._format_cookie(self.session_cookie, data, self.security_flags))
                    if session.get("user_id"):
                        headers.append(
                            "Set-Cookie", self._format_cookie(self.marker_cookie, "1", self.marker_security_flags)
                        )
                    else:
                        # Anonymous session write: never let the marker linger without an authenticated session.
                        headers.append(
                            "Set-Cookie", self._format_expiry_cookie(self.marker_cookie, self.marker_security_flags)
                        )
                elif not session and not initial_session_was_empty:
                    # Session was cleared, send expiry cookies
                    headers = MutableHeaders(scope=message)
                    headers.append("Set-Cookie", self._format_expiry_cookie(self.session_cookie, self.security_flags))
                    headers.append(
                        "Set-Cookie", self._format_expiry_cookie(self.marker_cookie, self.marker_security_flags)
                    )

            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _encode_session(self, session_dict: dict) -> str:
        """Encode session data into a signed cookie value."""
        data = b64encode(json.dumps(session_dict).encode("utf-8"))
        return self.signer.sign(data).decode("utf-8")

    def _format_cookie(self, name: str, value: str, security_flags: str) -> str:
        """Format a Set-Cookie value that persists for the session's max age."""
        max_age = f"Max-Age={self.max_age}; " if self.max_age else ""
        return f"{name}={value}; path={self.path}; {max_age}{security_flags}"

    def _format_expiry_cookie(self, name: str, security_flags: str) -> str:
        """Format a Set-Cookie value that expires the cookie immediately."""
        expires = "expires=Thu, 01 Jan 1970 00:00:00 GMT; "
        return f"{name}=null; path={self.path}; {expires}{security_flags}"
