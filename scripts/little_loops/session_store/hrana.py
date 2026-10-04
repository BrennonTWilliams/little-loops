"""Stdlib Hrana-over-HTTP client for a remote libSQL history store (FEAT-3535).

Talks to ``POST /v3/pipeline`` on sqld or Turso Cloud with :mod:`http.client`: real
socket timeouts, no GIL held across the network call, and structured error codes. This is
deliberately not the ``libsql`` Python binding, whose connect/statement calls cannot be
time-limited and freeze every thread (FEAT-3524's F1/F2/F5). Wire facts and the error-code
table are the ones proven in ``.ll/learning-tests/hrana-http.md``.

Each :meth:`HranaClient.execute` is one HTTP round trip (an ``execute`` request plus a
``close``), so the client holds no server-side stream between calls. Atomic multi-statement
work uses :meth:`HranaClient.batch`, whose step conditions give ``begin`` / conditional
``commit`` / ``not ok`` conditional ``rollback`` without an interactive transaction.

Errors are classified by structured ``code``, never by message, with one documented
exception: Turso reports an expired idle transaction as ``SQLITE_BUSY`` with the reason only
in the message, so that one pair is recognised by the ``"stream was idle"`` phrase.

The auth token is held only by the client instance and is never part of an exception
message or ``repr``.
"""

from __future__ import annotations

import base64
import http.client
import io
import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from little_loops.session_store import deadline as _deadline
from little_loops.session_store.backend import (
    HistoryError,
    HistoryIntegrityError,
    HistoryOperationError,
    HistoryUnavailable,
)
from little_loops.session_store.deadline import Deadline

_PIPELINE_PATH = "/v3/pipeline"
_READ_CHUNK = 65536
_SCHEME_MAP = {
    "libsql": "https",
    "https": "https",
    "wss": "https",
    "http": "http",
    "ws": "http",
}


# -- errors ---------------------------------------------------------------


class HranaError(HistoryError):
    """A classified Hrana failure. ``code`` is the server's structured error code."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class HranaIntegrityError(HranaError, HistoryIntegrityError):
    """``SQLITE_CONSTRAINT`` (primary-key, unique or NOT NULL violation)."""


class HranaOperationError(HranaError, HistoryOperationError):
    """``SQL_PARSE_ERROR``, ``SQLITE_UNKNOWN`` or any code not otherwise mapped."""


class HranaUnavailable(HranaError, HistoryUnavailable):
    """Unreachable, timed out, rejected (HTTP 400/401/403/5xx) or ``BLOCKED``."""


class HranaStreamLost(HranaUnavailable):
    """The server dropped the stream: sqld ``STREAM_EXPIRED`` or Turso's idle-transaction
    rollback (``SQLITE_BUSY``). One retryable class, because Turso cannot be told apart by
    code. Safe to retry once for an idempotent read; never inside a write transaction."""


def classify_error(code: str | None, message: str, http_status: int | None = None) -> HranaError:
    """Map a Hrana error to a :class:`HistoryError` subclass by ``code``."""
    if code == "SQLITE_CONSTRAINT":
        return HranaIntegrityError(message, code)
    if code == "STREAM_EXPIRED" or (code == "SQLITE_BUSY" and "stream was idle" in message.lower()):
        return HranaStreamLost(message, code)
    if code == "BLOCKED" or (
        http_status is not None and (http_status in (400, 401, 403) or http_status >= 500)
    ):
        return HranaUnavailable(message, code)
    return HranaOperationError(message, code)


# -- values ---------------------------------------------------------------


def encode_value(v: Any) -> dict[str, Any]:
    """Encode a Python value as a Hrana value (integers travel as strings)."""
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"type": "blob", "base64": base64.b64encode(bytes(v)).decode("ascii")}
    return {"type": "text", "value": str(v)}


def decode_value(v: dict[str, Any]) -> Any:
    """Decode a Hrana value to a Python value."""
    kind = v.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(v["value"])
    if kind == "float":
        return float(v["value"])
    if kind == "blob":
        return base64.b64decode(v.get("base64") or "")
    return v.get("value")


# -- results --------------------------------------------------------------


@dataclass
class HranaResult:
    """One statement's result."""

    cols: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    affected_row_count: int = 0
    last_insert_rowid: int | None = None


@dataclass
class BatchStep:
    """One step of an atomic batch. ``condition`` is built with the ``cond_*`` helpers."""

    sql: str
    params: Sequence[Any] = ()
    condition: dict[str, Any] | None = None


@dataclass
class BatchResult:
    """Per-step outcome: a skipped step has both entries ``None``."""

    step_results: list[HranaResult | None]
    step_errors: list[dict[str, Any] | None]

    def first_error(self) -> dict[str, Any] | None:
        return next((e for e in self.step_errors if e), None)


def cond_ok(step: int) -> dict[str, Any]:
    return {"type": "ok", "step": step}


def cond_not(cond: dict[str, Any]) -> dict[str, Any]:
    return {"type": "not", "cond": cond}


def _parse_result(raw: dict[str, Any]) -> HranaResult:
    rid = raw.get("last_insert_rowid")
    return HranaResult(
        cols=[c.get("name") or "" for c in raw.get("cols", [])],
        rows=[tuple(decode_value(c) for c in row) for row in raw.get("rows", [])],
        affected_row_count=int(raw.get("affected_row_count") or 0),
        last_insert_rowid=int(rid) if rid is not None else None,
    )


def normalize_url(url: str) -> str:
    """Reduce an endpoint URL to ``scheme://host[:port]`` for ``http.client``.

    ``libsql://`` and ``wss://`` are the endpoint spellings Turso hands out; both speak
    HTTPS on the same host.
    """
    parts = urlsplit(url.strip())
    scheme = _SCHEME_MAP.get(parts.scheme.lower())
    if scheme is None or not parts.netloc:
        raise ValueError(f"unsupported libSQL endpoint URL scheme in {parts.scheme!r}")
    host = parts.netloc.rsplit("@", 1)[-1]  # never keep userinfo
    return f"{scheme}://{host}"


# -- deadline-bound transport ----------------------------------------------


class _DeadlineReader(io.RawIOBase):
    """Raw reader that arms the socket timeout from the remaining budget before every receive.

    ``BufferedReader`` over this loops on ``readinto``, so a trickle of one byte per receive
    (inside one header parse or one buffered body read) still hits the expiry check each time.
    """

    def __init__(self, owner: _DeadlineSocket) -> None:
        super().__init__()
        self._owner = owner

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        return self._owner.recv_into(buffer)

    def close(self) -> None:
        if not self.closed:
            super().close()
            self._owner._reader_closed()


class _DeadlineSocket:
    """Proxy for the connected (optionally TLS-wrapped) socket of a deadline-bound request.

    Owns the live socket independently of ``HTTPConnection.sock``: ``getresponse()`` detaches
    that attribute for connection-closing responses while the response still reads, so the
    expiry must be enforced here. The real socket closes once the connection has closed *and*
    every reader made by :meth:`makefile` has closed.
    """

    def __init__(self, sock: Any, expiry: float) -> None:
        self._sock = sock
        self._expiry = expiry
        self._readers = 0
        self._closing = False
        self._closed = False

    def _arm(self) -> None:
        remaining = self._expiry - _deadline.now()
        if remaining <= 0:
            raise TimeoutError("request deadline exceeded")
        self._sock.settimeout(remaining)

    def sendall(self, data: Any) -> None:
        self._arm()
        self._sock.sendall(data)

    def recv_into(self, buffer: Any) -> int:
        self._arm()
        return int(self._sock.recv_into(buffer))

    def makefile(self, mode: str = "rb", buffering: int | None = None) -> io.BufferedReader:
        if "r" not in mode or "w" in mode:
            raise ValueError(f"unsupported mode {mode!r}")
        self._readers += 1
        return io.BufferedReader(_DeadlineReader(self))

    def _reader_closed(self) -> None:
        self._readers -= 1
        self._maybe_close()

    def close(self) -> None:
        self._closing = True
        self._maybe_close()

    def _maybe_close(self) -> None:
        if self._closing and self._readers <= 0 and not self._closed:
            self._closed = True
            self._sock.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sock, name)


def _connect_budget(expiry: float) -> float:
    remaining = expiry - _deadline.now()
    if remaining <= 0:
        raise TimeoutError("request deadline exceeded")
    return remaining


class _DeadlineHTTPConnection(http.client.HTTPConnection):
    """Bounds connect by the expiry, then wraps the socket for send/receive enforcement."""

    _expiry: float = 0.0

    def connect(self) -> None:
        self.timeout = _connect_budget(self._expiry)
        super().connect()
        self.sock = _DeadlineSocket(self.sock, self._expiry)  # type: ignore[assignment]


class _DeadlineHTTPSConnection(http.client.HTTPSConnection):
    """As :class:`_DeadlineHTTPConnection`; the TLS handshake is bounded by the same budget."""

    _expiry: float = 0.0

    def connect(self) -> None:
        self.timeout = _connect_budget(self._expiry)
        super().connect()
        self.sock = _DeadlineSocket(self.sock, self._expiry)  # type: ignore[assignment]


# -- client ---------------------------------------------------------------


class HranaClient:
    """Stateless, thread-safe Hrana pipeline client (one connection per request)."""

    def __init__(
        self,
        url: str,
        auth_token: str | None = None,
        *,
        timeout: float = 10.0,
        deadline: Deadline | None = None,
    ) -> None:
        self._base = normalize_url(url)
        self._token = auth_token
        self._timeout = timeout
        # ENH-3720: an optional caller expiry shared by every request this (dedicated,
        # never-mutated) client makes; each request is capped by the earlier of it and ``timeout``.
        self._deadline = deadline

    def __repr__(self) -> str:
        return f"HranaClient(url={self._base!r}, timeout={self._timeout})"

    __str__ = __repr__

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def deadline(self) -> Deadline | None:
        return self._deadline

    def check_deadline(self) -> None:
        """Raise :class:`HranaUnavailable` when this client's caller deadline has expired."""
        if self._deadline is not None and self._deadline.expired():
            raise HranaUnavailable("history read deadline expired; no request sent")

    def _scrub(self, text: str) -> str:
        if self._token and self._token in text:
            text = text.replace(self._token, "***")
        return text[:500]

    def _post(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        parts = urlsplit(self._base)
        host = parts.hostname or ""
        self.check_deadline()
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        body = json.dumps({"baton": None, "requests": requests})
        try:
            if self._deadline is None:
                status, raw = self._exchange(parts, body, headers)
            else:
                expiry = min(_deadline.now() + self._timeout, self._deadline.expires_at)
                status, raw = self._exchange_bound(parts, body, headers, expiry)
        except (OSError, http.client.HTTPException) as exc:
            raise HranaUnavailable(
                f"could not reach {host}: {type(exc).__name__}: {self._scrub(str(exc))}"
            ) from None
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        self.check_deadline()  # synchronous decoding is not preempted; never report late success
        if status != 200:
            message = code = None
            if isinstance(payload, dict):
                message, code = payload.get("message"), payload.get("code")
            raise classify_error(
                code, self._scrub(str(message or raw[:200].decode(errors="replace"))), status
            )
        if not isinstance(payload, dict):
            raise HranaOperationError(f"{host} returned a non-JSON pipeline response")
        return payload

    def _exchange(self, parts: Any, body: str, headers: dict[str, str]) -> tuple[int, bytes]:
        """One request/response with the client's per-request cap (no caller deadline)."""
        conn_cls = (
            http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        )
        deadline = time.monotonic() + self._timeout
        conn = conn_cls(parts.hostname or "", parts.port, timeout=self._timeout)
        try:
            conn.request("POST", _PIPELINE_PATH, body, headers)
            resp = conn.getresponse()
            raw = self._read(resp, conn, deadline)
        finally:
            conn.close()
        return resp.status, raw

    def _exchange_bound(
        self, parts: Any, body: str, headers: dict[str, str], expiry: float
    ) -> tuple[int, bytes]:
        """One request/response whose connect, send, header and body I/O all end by *expiry*."""
        conn_cls = _DeadlineHTTPSConnection if parts.scheme == "https" else _DeadlineHTTPConnection
        conn = conn_cls(parts.hostname or "", parts.port, timeout=self._timeout)
        conn._expiry = expiry
        try:
            conn.request("POST", _PIPELINE_PATH, body, headers)
            resp = conn.getresponse()
            try:
                return resp.status, resp.read()
            finally:
                resp.close()
        finally:
            conn.close()

    @staticmethod
    def _read(
        resp: http.client.HTTPResponse, conn: http.client.HTTPConnection, deadline: float
    ) -> bytes:
        """Read the body under a monotonic total deadline (socket timeouts alone reset per read)."""
        chunks: list[bytes] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("request deadline exceeded")
            if conn.sock is not None:
                conn.sock.settimeout(remaining)
            chunk = resp.read(_READ_CHUNK)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    def _results(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = self._post(requests).get("results", [])
        if len(results) < len(requests):
            raise HranaOperationError("Hrana pipeline returned fewer results than requests")
        return results

    @staticmethod
    def _stmt(sql: str, params: Sequence[Any]) -> dict[str, Any]:
        return {"sql": sql, "args": [encode_value(p) for p in params]}

    @staticmethod
    def _raise_for(item: dict[str, Any]) -> None:
        if item.get("type") == "error":
            err = item.get("error") or {}
            raise classify_error(err.get("code"), str(err.get("message", "")))

    # -- public API -------------------------------------------------------

    def execute(self, sql: str, params: Sequence[Any] = ()) -> HranaResult:
        """Run one statement (autocommit) in one round trip."""
        item = self._results(
            [{"type": "execute", "stmt": self._stmt(sql, params)}, {"type": "close"}]
        )[0]
        self._raise_for(item)
        return _parse_result(item["response"]["result"])

    def batch(self, steps: Sequence[BatchStep]) -> BatchResult:
        """Run an atomic batch; per-step failures are returned, not raised."""
        wire = []
        for step in steps:
            entry: dict[str, Any] = {"stmt": self._stmt(step.sql, step.params)}
            if step.condition is not None:
                entry["condition"] = step.condition
            wire.append(entry)
        item = self._results([{"type": "batch", "batch": {"steps": wire}}, {"type": "close"}])[0]
        self._raise_for(item)
        raw = item["response"]["result"]
        return BatchResult(
            step_results=[_parse_result(r) if r is not None else None for r in raw["step_results"]],
            step_errors=list(raw["step_errors"]),
        )

    def execute_many(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> int:
        """Run *sql* once per parameter set inside one atomic batch; return rows affected.

        All-or-nothing: the first failing statement rolls the whole set back and raises.
        """
        rows = list(seq_of_params)
        if not rows:
            return 0
        steps = [BatchStep("begin")]
        for i, params in enumerate(rows):
            steps.append(BatchStep(sql, params, cond_ok(i)))
        last = len(rows)
        steps.append(BatchStep("commit", condition=cond_ok(last)))
        steps.append(BatchStep("rollback", condition=cond_not(cond_ok(last + 1))))
        result = self.batch(steps)
        err = result.first_error()
        if err is not None:
            raise classify_error(err.get("code"), str(err.get("message", "")))
        return sum(r.affected_row_count for r in result.step_results[1 : last + 1] if r is not None)
