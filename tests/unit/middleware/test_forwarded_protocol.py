from fastapi import FastAPI, Request, WebSocket
from fastapi.testclient import TestClient

from app.middleware.forwarded_protocol import ForwardedProtocolMiddleware
from tests.helpers.vcr import mark_as_vcr, vcr_config  # noqa

app = FastAPI()
app.add_middleware(ForwardedProtocolMiddleware)


@app.get("/test")
async def scheme_route(request: Request):
    return {"scheme": request.url.scheme}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"scheme": websocket.scope["scheme"]})
    await websocket.close()


client = TestClient(app)


def test_forwarded_protocol_middleware_with_header():
    response = client.get("/test", headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 200
    assert response.json() == {"scheme": "https"}


def test_forwarded_protocol_middleware_without_header():
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"scheme": "http"}


def test_forwarded_protocol_middleware_websocket_with_header():
    with client.websocket_connect("/ws", headers={"X-Forwarded-Proto": "wss"}) as websocket:
        data = websocket.receive_json()
        assert data == {"scheme": "wss"}


def test_forwarded_protocol_middleware_websocket_without_header():
    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data == {"scheme": "ws"}
