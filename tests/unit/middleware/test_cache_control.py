from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.testclient import TestClient

from app.middleware.cache_control import CacheControlMiddleware
from app.middleware.sessions import LazySessionMiddleware

app = FastAPI()
# Order mirrors production (main.py): CacheControl is added first so it sits
# innermost on the response, with LazySession wrapping it. If you flip these,
# Set-Cookie sniffing appears to work but doesn't in production.
app.add_middleware(CacheControlMiddleware)
app.add_middleware(LazySessionMiddleware, secret_key="test-secret")

REVALIDATE = "private, no-cache"


@app.get("/page")
async def page_route():
    return HTMLResponse("<html><body>Page</body></html>")


@app.get("/static/asset.css")
async def static_route():
    return Response(content="body{}", media_type="text/css")


@app.post("/redirect")
async def redirect_route():
    return RedirectResponse("/page", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/session_write")
async def session_write_route(request: Request):
    request.session["key"] = "value"
    return HTMLResponse("<div>Written</div>")


@app.get("/handler_cache")
async def handler_cache_route():
    return Response(content="cached", headers={"Cache-Control": "public, max-age=3600"})


client = TestClient(app)


def test_dynamic_responses_get_revalidate_trio():
    response = client.get("/page")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == REVALIDATE
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


def test_redirects_get_revalidate_trio():
    response = client.post("/redirect", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["Cache-Control"] == REVALIDATE


def test_static_paths_are_left_alone():
    response = client.get("/static/asset.css")

    assert response.status_code == 200
    assert "Cache-Control" not in response.headers
    assert "Pragma" not in response.headers
    assert "Expires" not in response.headers


def test_handler_set_cache_control_is_preserved():
    response = client.get("/handler_cache")

    assert response.headers["Cache-Control"] == "public, max-age=3600"
    assert "Pragma" not in response.headers
    assert "Expires" not in response.headers


def test_handler_set_cache_control_is_preserved_for_preload():
    response = client.get("/handler_cache", headers={"hx-preloaded": "true"})

    assert response.headers["Cache-Control"] == "public, max-age=3600"


def test_htmx_preload_gets_short_private_cache():
    response = client.get("/page", headers={"hx-preloaded": "true"})

    assert response.headers["Cache-Control"] == "private, max-age=1"
    assert "Pragma" not in response.headers


def test_htmx_preload_falls_back_to_revalidate_when_session_is_written():
    response = client.get("/session_write", headers={"hx-preloaded": "true"})

    assert "set-cookie" in response.headers
    assert response.headers["Cache-Control"] == REVALIDATE
