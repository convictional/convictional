from starlette.requests import Request

# Mirrors REACT_MODE_COOKIE in app/middleware/react_toggle.py — the architecture
# linter forbids importing across the helpers/middleware boundary, so the name
# is duplicated. Keep both in sync.
_REACT_MODE_COOKIE = "react_mode"


def react_mode_enabled(request: Request) -> bool:
    return request.cookies.get(_REACT_MODE_COOKIE) == "on"
