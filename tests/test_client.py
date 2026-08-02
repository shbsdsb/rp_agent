import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rp_agent.api.client import ApiError, chat, test_connection as api_test_connection
from rp_agent.api.models import ApiConnection


class _FakeHandler(BaseHTTPRequestHandler):
    status = 200
    body: dict = {}
    captured: dict = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        self.__class__.captured = json.loads(raw)
        self.send_response(self.__class__.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.__class__.body).encode("utf-8"))

    def log_message(self, *args):
        pass


@pytest.fixture()
def fake_server():
    server = HTTPServer(("127.0.0.1", 0), _FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _conn(server):
    return ApiConnection(
        name="test",
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        api_key="sk-test",
        model="test-model",
    )


def test_chat_success(fake_server):
    _FakeHandler.status = 200
    _FakeHandler.body = {"choices": [{"message": {"content": "你好"}}]}
    reply = chat(_conn(fake_server), [{"role": "user", "content": "hi"}])
    assert reply == "你好"
    assert _FakeHandler.captured["model"] == "test-model"
    assert _FakeHandler.captured["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_unauthorized(fake_server):
    _FakeHandler.status = 401
    _FakeHandler.body = {"error": "unauthorized"}
    with pytest.raises(ApiError, match="认证失败"):
        chat(_conn(fake_server), [{"role": "user", "content": "hi"}])


def test_chat_connection_failed():
    conn = ApiConnection(
        name="t",
        base_url="http://127.0.0.1:1/v1",  # 不可达端口
        api_key="k",
        model="m",
        timeout=0.5,
    )
    with pytest.raises(ApiError, match="连接失败"):
        chat(conn, [{"role": "user", "content": "hi"}])


def test_test_connection(fake_server):
    _FakeHandler.status = 200
    _FakeHandler.body = {"choices": [{"message": {"content": "pong"}}]}
    assert api_test_connection(_conn(fake_server)) == "pong"
