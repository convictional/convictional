from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient

from app.middleware.react_toggle import REACT_MODE_COOKIE, ReactToggleMiddleware
from app.middleware.sessions import LazySessionMiddleware
from config import settings


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/inbox")
    async def inbox():
        return {"page": "inbox"}

    @app.get("/api/mailbox_entries")
    async def api_route():
        return {"page": "api"}

    @app.post("/posts")
    async def post_route():
        return {"page": "post"}

    @app.get("/login")
    async def login(request: Request):
        request.session["user_id"] = "user-1"
        return {"ok": True}

    @app.get("/echo_cookie")
    async def echo_cookie(request: Request):
        return {"react_mode": request.cookies.get(REACT_MODE_COOKIE)}

    app.add_middleware(ReactToggleMiddleware)
    app.add_middleware(
        LazySessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie=settings.session_cookie_name,
    )
    return app


def test_logged_in_toggle_sets_clears_and_persists_cookie():
    client = TestClient(_build_app(), follow_redirects=False)
    client.get("/login")

    # Opt in: 302 to URL with `react` stripped but siblings preserved, cookie set.
    response = client.get("/inbox?sort=newest&react=on&cursor=abc")
    assert response.status_code == status.HTTP_302_FOUND
    location = response.headers["location"]
    assert "react=" not in location
    assert "sort=newest" in location
    assert "cursor=abc" in location
    assert client.cookies.get(REACT_MODE_COOKIE) == "on"

    # Cookie survives subsequent requests.
    assert client.get("/echo_cookie").json() == {"react_mode": "on"}

    # Opt out: cookie cleared, still a redirect.
    response = client.get("/inbox?react=off")
    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"].endswith("/inbox")
    assert client.cookies.get(REACT_MODE_COOKIE) is None


def test_toggle_skipped_for_unsupported_request_shapes():
    # Anonymous: still strip + redirect, but never set the cookie.
    anon = TestClient(_build_app(), follow_redirects=False)
    response = anon.get("/inbox?react=on")
    assert response.status_code == status.HTTP_302_FOUND
    assert anon.cookies.get(REACT_MODE_COOKIE) is None

    # HTMX, POST, /api/*, missing/invalid param: all pass through untouched.
    client = TestClient(_build_app(), follow_redirects=False)
    client.get("/login")

    pass_through_cases = [
        client.get("/inbox?react=on", headers={"HX-Request": "true"}),
        client.post("/posts?react=on"),
        client.get("/api/mailbox_entries?react=on"),
        client.get("/inbox?sort=newest"),
        client.get("/inbox?react=maybe"),
    ]
    for response in pass_through_cases:
        assert response.status_code == status.HTTP_200_OK

    assert client.cookies.get(REACT_MODE_COOKIE) is None
