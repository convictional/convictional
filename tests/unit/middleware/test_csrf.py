from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient

from app.middleware.csrf import CSRFMiddleware
from app.middleware.sessions import LazySessionMiddleware
from config import settings

app = FastAPI()
app.add_middleware(CSRFMiddleware)
app.add_middleware(LazySessionMiddleware, secret_key=settings.secret_key.get_secret_value())

route_aware_app = FastAPI()


@route_aware_app.get("/token")
async def route_aware_token_route(request: Request):
    return {"csrf_token": request.state.csrf_token}


@route_aware_app.post("/test")
async def route_aware_csrf_route(request: Request):
    data = await request.form()
    return {"foo": data.get("foo")}


route_aware_app.add_middleware(CSRFMiddleware, routes=route_aware_app.router.routes)
route_aware_app.add_middleware(LazySessionMiddleware, secret_key=settings.secret_key.get_secret_value())
route_aware_client = TestClient(route_aware_app)


@app.get("/token")
async def token_route(request: Request):
    return {"csrf_token": request.state.csrf_token}


@app.post("/test")
async def csrf_route(request: Request):
    data = await request.form()
    return {"foo": data.get("foo")}


client = TestClient(app)


def test_csrf_token_stored_in_session():
    response = client.get("/token")
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["csrf_token"]
    assert token
    assert "csrf_token" not in response.cookies


def test_csrf_token_persists_across_requests():
    fresh_client = TestClient(app)
    response1 = fresh_client.get("/token")
    token1 = response1.json()["csrf_token"]

    response2 = fresh_client.get("/token")
    token2 = response2.json()["csrf_token"]

    assert token1 == token2


def test_post_without_csrf_token_returns_403():
    response = client.get("/token")
    response = client.post("/test", data={"foo": "bar"})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.headers["X-CSRF-Failure"] == "true"


def test_post_with_invalid_csrf_token_returns_403():
    client.get("/token")
    response = client.post(
        "/test",
        data={"foo": "bar"},
        headers={"x-csrftoken": "invalid"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.headers["X-CSRF-Failure"] == "true"


def test_post_with_valid_csrf_header():
    response = client.get("/token")
    csrf_token = response.json()["csrf_token"]

    response = client.post(
        "/test",
        data={"foo": "bar"},
        headers={"x-csrftoken": csrf_token},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"foo": "bar"}


def test_post_with_valid_csrf_form_body():
    response = client.get("/token")
    csrf_token = response.json()["csrf_token"]

    response = client.post(
        "/test",
        data={"foo": "bar", "csrf_token": csrf_token},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"foo": "bar"}


def test_csrf_token_not_accepted_from_query_params():
    response = client.get("/token")
    csrf_token = response.json()["csrf_token"]

    response = client.post(f"/test?csrf_token={csrf_token}", data={"foo": "bar"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_post_to_nonexistent_route_skips_csrf_when_routes_configured():
    response = route_aware_client.post("/does-not-exist", data={"foo": "bar"})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "X-CSRF-Failure" not in response.headers


def test_post_to_existing_route_still_validates_csrf_when_routes_configured():
    route_aware_client.get("/token")
    response = route_aware_client.post("/test", data={"foo": "bar"})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.headers["X-CSRF-Failure"] == "true"
