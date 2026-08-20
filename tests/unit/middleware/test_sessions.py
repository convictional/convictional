from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.sessions import LazySessionMiddleware, ModifiableSessionDict

# ModifiableSessionDict tests
session_app = FastAPI()
session_app.add_middleware(LazySessionMiddleware, secret_key="test-secret-key")


@session_app.get("/read")
async def read_session(request: Request):
    value = request.session.get("test_key", "not found")
    return JSONResponse({"value": value})


@session_app.post("/write")
async def write_session(request: Request):
    request.session["test_key"] = "test_value"
    return JSONResponse({"status": "written"})


@session_app.post("/modify")
async def modify_session(request: Request):
    request.session["existing_key"] = "modified_value"
    return JSONResponse({"status": "modified"})


@session_app.post("/delete")
async def delete_session(request: Request):
    if "test_key" in request.session:
        del request.session["test_key"]
    return JSONResponse({"status": "deleted"})


@session_app.post("/clear")
async def clear_session(request: Request):
    request.session.clear()
    return JSONResponse({"status": "cleared"})


@session_app.post("/login")
async def login_session(request: Request):
    request.session["user_id"] = "user-123"
    return JSONResponse({"status": "logged in"})


session_client = TestClient(session_app)


def _set_cookie_for(response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header
    return None


def test_modifiable_session_dict_initial_state():
    session = ModifiableSessionDict()
    assert not session.modified


def test_modifiable_session_dict_setitem():
    session = ModifiableSessionDict()
    session["key"] = "value"
    assert session.modified


def test_modifiable_session_dict_setitem_marks_modified():
    session = ModifiableSessionDict({"key": "value"})
    session._modified = False
    session["key"] = "new_value"
    assert session.modified


def test_modifiable_session_dict_delitem():
    session = ModifiableSessionDict({"key": "value"})
    session._modified = False
    del session["key"]
    assert session.modified


def test_modifiable_session_dict_clear():
    session = ModifiableSessionDict({"key": "value"})
    session._modified = False
    session.clear()
    assert session.modified


def test_modifiable_session_dict_clear_empty():
    session = ModifiableSessionDict()
    session.clear()
    assert not session.modified


def test_modifiable_session_dict_pop():
    session = ModifiableSessionDict({"key": "value"})
    session._modified = False
    session.pop("key")
    assert session.modified


def test_modifiable_session_dict_pop_nonexistent():
    session = ModifiableSessionDict()
    session.pop("key", None)
    assert not session.modified


def test_modifiable_session_dict_popitem():
    session = ModifiableSessionDict({"key": "value"})
    session._modified = False
    session.popitem()
    assert session.modified


def test_modifiable_session_dict_setdefault_existing():
    session = ModifiableSessionDict({"key": "value"})
    session._modified = False
    session.setdefault("key", "other")
    assert not session.modified


def test_modifiable_session_dict_setdefault_new():
    session = ModifiableSessionDict()
    session.setdefault("key", "value")
    assert session.modified


def test_modifiable_session_dict_update():
    session = ModifiableSessionDict()
    session.update({"key": "value"})
    assert session.modified


def test_modifiable_session_dict_mark_modified():
    session = ModifiableSessionDict()
    assert not session.modified
    session.mark_modified()
    assert session.modified


def test_no_set_cookie_on_read_without_session():
    """Reading session without existing session should not set cookie"""
    client = TestClient(session_app)
    response = client.get("/read")
    assert response.status_code == 200
    assert "set-cookie" not in response.headers


def test_set_cookie_on_write_new_session():
    """Writing to session should set cookie"""
    client = TestClient(session_app)
    response = client.post("/write")
    assert response.status_code == 200
    assert "set-cookie" in response.headers
    assert "session=" in response.headers["set-cookie"]


def test_no_set_cookie_on_read_with_existing_session():
    """Reading existing session without modification should not set cookie"""
    client = TestClient(session_app)
    client.post("/write")
    response = client.get("/read")
    assert response.status_code == 200
    assert response.json() == {"value": "test_value"}
    assert "set-cookie" not in response.headers


def test_set_cookie_on_modify_existing_session():
    """Modifying existing session should set cookie"""
    client = TestClient(session_app)
    client.post("/write")
    response = client.post("/modify")
    assert response.status_code == 200
    assert "set-cookie" in response.headers


def test_set_cookie_on_delete_from_session():
    """Deleting from session should set cookie"""
    client = TestClient(session_app)
    client.post("/write")
    response = client.post("/delete")
    assert response.status_code == 200
    assert "set-cookie" in response.headers


def test_set_cookie_on_clear_session():
    """Clearing session should set expiry cookie"""
    client = TestClient(session_app)
    client.post("/write")
    response = client.post("/clear")
    assert response.status_code == 200
    assert "set-cookie" in response.headers
    assert "expires=Thu, 01 Jan 1970" in response.headers["set-cookie"]


def test_session_data_persists_across_requests():
    """Session data should persist across requests"""
    client = TestClient(session_app)
    write_response = client.post("/write")
    assert write_response.status_code == 200

    read_response = client.get("/read")
    assert read_response.status_code == 200
    assert read_response.json() == {"value": "test_value"}


def test_cleared_session_removes_data():
    """Clearing session should remove all data"""
    client = TestClient(session_app)
    client.post("/write")
    client.post("/clear")
    response = client.get("/read")
    assert response.status_code == 200
    assert response.json() == {"value": "not found"}


def test_session_cookie_attributes():
    """Session cookie should have correct security attributes"""
    client = TestClient(session_app)
    response = client.post("/write")
    cookie_header = response.headers["set-cookie"]
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()
    assert "path=/" in cookie_header.lower()


def test_marker_cookie_set_on_authenticated_write():
    """Writing a session with user_id sets a JS-readable logged_in=1 marker mirroring session flags."""
    client = TestClient(session_app)
    response = client.post("/login")
    assert response.status_code == 200

    marker = _set_cookie_for(response, "logged_in")
    assert marker is not None
    assert "logged_in=1;" in marker

    # JS must be able to read it, so it is NOT HttpOnly, but mirrors the session
    # cookie's other security flags.
    assert "httponly" not in marker.lower()
    assert "samesite=lax" in marker.lower()
    assert "path=/" in marker.lower()


def test_marker_cookie_cleared_on_session_clear():
    """Clearing the session emits a logged_in expiry cookie alongside the session expiry."""
    client = TestClient(session_app)
    client.post("/login")
    response = client.post("/clear")
    assert response.status_code == 200

    marker = _set_cookie_for(response, "logged_in")
    assert marker is not None
    assert "expires=Thu, 01 Jan 1970" in marker
    assert "httponly" not in marker.lower()


def test_marker_cookie_expired_on_anonymous_session_write():
    """A session modified without a user_id expires the marker rather than leaving it set."""
    client = TestClient(session_app)
    response = client.post("/write")
    assert response.status_code == 200

    marker = _set_cookie_for(response, "logged_in")
    assert marker is not None
    assert "expires=Thu, 01 Jan 1970" in marker
    assert "logged_in=1;" not in marker
