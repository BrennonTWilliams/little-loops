"""In-process Hrana-over-HTTP test double (FEAT-3535).

A stdlib ``ThreadingHTTPServer`` on ``127.0.0.1`` port 0 that speaks the subset of
``POST /v3/pipeline`` the little-loops client uses (``execute``, ``batch`` with step
conditions, ``close``), backed by one in-memory ``sqlite3`` database. It reproduces the
wire shapes and error codes observed against sqld and Turso Cloud in
``.ll/learning-tests/hrana-http.md``:

- integers travel as strings, blobs as base64; results carry ``cols``/``rows``/
  ``affected_row_count``/``last_insert_rowid``;
- database errors arrive as ``results[i] = {"type": "error", "error": {message, code}}`` with
  HTTP 200 (``SQLITE_CONSTRAINT``, ``SQL_PARSE_ERROR``, ``SQLITE_UNKNOWN``);
- a bad or missing bearer token is HTTP 401.

One lock spans a whole request, so concurrent batches serialize the way ``begin immediate``
does on the real servers. Fault knobs: ``delay`` (sleep before answering), ``fail_next``
(queue of one-shot ``(status, body)`` overrides) and ``requests`` (every request received,
for asserting on what crossed the wire).
"""

from __future__ import annotations

import base64
import http.server
import json
import sqlite3
import threading
import time
from typing import Any


def _decode_value(v: dict[str, Any]) -> Any:
    kind = v.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(v["value"])
    if kind == "float":
        return float(v["value"])
    if kind == "blob":
        return base64.b64decode(v["base64"])
    return v["value"]


def _encode_value(v: Any) -> dict[str, Any]:
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"type": "blob", "base64": base64.b64encode(bytes(v)).decode()}
    return {"type": "text", "value": str(v)}


def _classify(exc: sqlite3.Error) -> dict[str, str]:
    msg = str(exc)
    if isinstance(exc, sqlite3.IntegrityError):
        code = "SQLITE_CONSTRAINT"
    elif "syntax error" in msg or "incomplete input" in msg:
        code = "SQL_PARSE_ERROR"
        msg = f"SQL string could not be parsed: {msg}"
    else:
        code = "SQLITE_UNKNOWN"
    return {"message": f"SQLite error: {msg}" if code != "SQL_PARSE_ERROR" else msg, "code": code}


class _Handler(http.server.BaseHTTPRequestHandler):
    server: HranaStub  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - quiet
        return

    def _reply(self, status: int, body: Any) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        stub = self.server
        stub.requests.append(
            {"path": self.path, "auth": self.headers.get("Authorization"), "body": raw.decode()}
        )
        if stub.delay:
            time.sleep(stub.delay)
        if stub.fail_next:
            status, body = stub.fail_next.pop(0)
            self._reply(status, body)
            return
        if self.path != "/v3/pipeline":
            self._reply(404, {"message": "not found"})
            return
        if stub.token is not None and self.headers.get("Authorization") != f"Bearer {stub.token}":
            self._reply(401, {"message": "Unauthorized: `The JWT is invalid`"})
            return
        try:
            req = json.loads(raw)
        except ValueError:
            self._reply(400, {"message": "malformed JSON", "code": "BAD_REQUEST"})
            return
        results: list[dict[str, Any]] = []
        with stub.lock:
            for item in req.get("requests", []):
                results.append(stub.run_request(item))
        self._reply(200, {"baton": None, "base_url": None, "results": results})


class HranaStub(http.server.ThreadingHTTPServer):
    """Start with :meth:`start`; stop with :meth:`stop`. ``url`` is the base URL."""

    daemon_threads = True

    def __init__(self, token: str | None = "test-token") -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.token = token
        self.lock = threading.Lock()
        self.db = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        self.delay = 0.0
        self.fail_next: list[tuple[int, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def start(self) -> HranaStub:
        self._thread = threading.Thread(
            target=lambda: self.serve_forever(poll_interval=0.01), daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        self.db.close()

    # -- request execution ------------------------------------------------

    def run_request(self, item: dict[str, Any]) -> dict[str, Any]:
        kind = item.get("type")
        if kind == "close":
            return {"type": "ok", "response": {"type": "close"}}
        if kind == "execute":
            try:
                result = self._exec(item["stmt"])
            except sqlite3.Error as exc:
                return {"type": "error", "error": _classify(exc)}
            return {"type": "ok", "response": {"type": "execute", "result": result}}
        if kind == "batch":
            return {
                "type": "ok",
                "response": {"type": "batch", "result": self._batch(item["batch"]["steps"])},
            }
        return {"type": "error", "error": {"message": f"unsupported {kind}", "code": "BAD_REQUEST"}}

    def _exec(self, stmt: dict[str, Any]) -> dict[str, Any]:
        args = [_decode_value(a) for a in stmt.get("args", [])]
        cur = self.db.execute(stmt["sql"], args)
        cols = [{"name": d[0], "decltype": None} for d in (cur.description or [])]
        rows = [[_encode_value(c) for c in row] for row in cur.fetchall()] if cols else []
        return {
            "cols": cols,
            "rows": rows,
            "affected_row_count": max(cur.rowcount, 0),
            "last_insert_rowid": str(cur.lastrowid) if cur.lastrowid else None,
        }

    def _cond(self, cond: dict[str, Any] | None, ok: list[bool], err: list[bool]) -> bool:
        if cond is None:
            return True
        kind = cond["type"]
        if kind == "ok":
            return ok[cond["step"]]
        if kind == "error":
            return err[cond["step"]]
        if kind == "not":
            return not self._cond(cond["cond"], ok, err)
        if kind == "and":
            return all(self._cond(c, ok, err) for c in cond["conds"])
        if kind == "or":
            return any(self._cond(c, ok, err) for c in cond["conds"])
        if kind == "is_autocommit":
            return self.db.in_transaction is False
        return False

    def _batch(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(steps)
        ok, err = [False] * n, [False] * n
        step_results: list[Any] = [None] * n
        step_errors: list[Any] = [None] * n
        for i, step in enumerate(steps):
            if not self._cond(step.get("condition"), ok, err):
                continue
            try:
                step_results[i] = self._exec(step["stmt"])
                ok[i] = True
            except sqlite3.Error as exc:
                step_errors[i] = _classify(exc)
                err[i] = True
        return {"step_results": step_results, "step_errors": step_errors}
