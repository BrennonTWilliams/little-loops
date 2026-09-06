"""Tests for little_loops._openai_compat_client — the OpenAIGenericRunner transport."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from little_loops._openai_compat_client import _extract_verdict, _strip_fences, main


def test_strip_fences_plain() -> None:
    assert _strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fences_fenced() -> None:
    assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_extract_verdict_dict() -> None:
    assert _extract_verdict('{"recommendation": "x"}') == {"recommendation": "x"}


def test_extract_verdict_fenced_dict() -> None:
    assert _extract_verdict('```json\n{"recommendation": "x"}\n```') == {"recommendation": "x"}


def test_extract_verdict_non_json_returns_raw() -> None:
    assert _extract_verdict("just some text") == "just some text"


def test_main_against_mock_server(monkeypatch, capsys) -> None:
    """End-to-end: POSTs to a mock /chat/completions and prints the envelope."""
    received: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received["path"] = self.path
            received["payload"] = json.loads(body)
            content = '{"recommendation": "go", "risks": [], "confidence": 0.9, "dissent": ""}'
            data = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert main(["client", base_url, "deepseek-v4-pro", "hello"]) == 0

        envelope = json.loads(capsys.readouterr().out)
        assert envelope["result"]["recommendation"] == "go"
        assert received["path"] == "/v1/chat/completions"
        assert received["payload"]["model"] == "deepseek-v4-pro"
        assert received["payload"]["messages"][0]["content"] == "hello"
    finally:
        server.shutdown()


def test_main_http_error_exits_nonzero(monkeypatch, capsys) -> None:
    """An upstream 4xx surfaces as a non-zero exit + stderr, not a traceback."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            data = b'{"error": "bad key"}'
            self.send_response(401)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:  # noqa: D102
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        assert main(["client", base_url, "m", "hello"]) == 2
        assert "401" in capsys.readouterr().err
    finally:
        server.shutdown()
