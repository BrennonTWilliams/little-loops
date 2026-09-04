"""Transport abstraction for the little-loops EventBus.

A `Transport` is an additive sink for events emitted by `EventBus`. The Protocol
is intentionally minimal — `send(event)` for delivery and `close()` for cleanup —
so that new sinks can be added without modifying `EventBus` itself.

Built-in implementations:
    JsonlTransport: appends each event as a JSON line to a file.
    UnixSocketTransport: streams newline-delimited JSON to AF_UNIX socket clients
        for sub-second-latency local consumers (TUIs, log tailers, dashboards).
    LocalBridgeTransport: binds a loopback-only stdlib HTTP server and streams
        events as Server-Sent Events to browser clients, while also accepting
        inbound `artifact_interaction` POSTs (ARTIFACT_CONTROL_LEVELS Level 3).
    OTelTransport: maps loop executions to OpenTelemetry traces/spans, exporting
        via OTLP to Grafana, Jaeger, Datadog, etc. Requires the optional
        ``opentelemetry-sdk`` and ``opentelemetry-exporter-otlp-grpc`` packages.
    WebhookTransport: POSTs batched events to an HTTP endpoint for remote
        dashboards, Slack bots, and CI systems. Requires the optional ``httpx``
        package (``pip install little-loops[webhooks]``).
    SQLiteTransport: records FSM loop events into the per-project session
        database (``.ll/history.db``) for indexed cross-cutting queries.

Public exports:
    Transport: runtime-checkable Protocol that any sink must satisfy
    JsonlTransport: writes events to a JSONL file
    UnixSocketTransport: streams events over an AF_UNIX socket
    LocalBridgeTransport: streams events over a loopback SSE bridge, bidirectionally
    OTelTransport: exports loop traces via OTLP
    WebhookTransport: POSTs batched events to an HTTP endpoint
    wire_transports: register transports listed in `EventsConfig` on an `EventBus`
"""

from __future__ import annotations

import enum
import errno
import http.server
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

# FEAT-3323: module-level (not lazy, unlike _make_seed_callback's own import of
# the same function) so the seed-to-live race test can
# mock.patch.object(little_loops.transport, "list_running_loops", ...) — a
# patch target that only exists as a module-level binding. Probed clean against
# the package init, fsm.persistence, cli.loop, and cli.artifact (no cycle).
from little_loops.fsm.persistence import list_running_loops

if TYPE_CHECKING:
    from little_loops.config.features import EventsConfig
    from little_loops.events import EventBus

logger = logging.getLogger(__name__)

_CLIENT_QUEUE_MAXSIZE = 1024
_DROP_LOG_INTERVAL_SEC = 5.0
_REJECT_LOG_INTERVAL_SEC = 5.0
_ACCEPT_THREAD_JOIN_TIMEOUT = 2.0
_CLIENT_THREAD_JOIN_TIMEOUT = 1.0
_CLOSE_TOTAL_TIMEOUT = 10.0
_ACCEPT_POLL_TIMEOUT = 1.0
_CLIENT_QUEUE_POLL_TIMEOUT = 0.5
_SOCKET_PROBE_TIMEOUT = 0.2

_WEBHOOK_BATCH_MS_DEFAULT = 1000
_WEBHOOK_CLOSE_TIMEOUT = 10.0
_WEBHOOK_RETRY_BASE_S = 0.5
_WEBHOOK_RETRY_MAX_S = 8.0

_LOCAL_BRIDGE_CLOSE_TIMEOUT = 10.0
_LOCAL_BRIDGE_THREAD_JOIN_TIMEOUT = 2.0
_LOCAL_BRIDGE_SERVE_THREAD_JOIN_TIMEOUT = 2.0
_LOCAL_BRIDGE_DEFAULT_PAGE_HTML = (
    '<!doctype html><html><head><meta charset="utf-8"></head>'
    "<body><p>LocalBridgeTransport: no page_html supplied.</p></body></html>"
)

# FEAT-3323: SseBridge (ll-artifact serve) constants.
_SSE_BRIDGE_CLOSE_TIMEOUT = 10.0
_SSE_BRIDGE_THREAD_JOIN_TIMEOUT = 2.0
_PRODUCER_READ_POLL_TIMEOUT = 0.5
_FANIN_CONNECT_TIMEOUT = 0.2
_FANIN_MAX_BACKOFF_S = 60.0


@runtime_checkable
class Transport(Protocol):
    """Protocol for an event sink registered on an `EventBus`.

    A transport receives every event emitted on the bus (no filtering at the
    transport layer; subscribe an observer with a filter for that). Implementations
    must tolerate being called with arbitrary `dict[str, Any]` shapes — the bus
    does not validate event contents.
    """

    def send(self, event: dict[str, Any]) -> None:
        """Deliver a single event."""
        ...

    def close(self) -> None:
        """Release any resources held by the transport. May be a no-op."""
        ...


class JsonlTransport:
    """Append events to a JSONL file, one JSON object per line.

    The parent directory is created at construction time so per-event writes do
    not have to check it. `close()` is a no-op since each `send()` opens and
    closes the file (matching the existing JSONL write pattern in this codebase).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, event: dict[str, Any]) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def close(self) -> None:
        return None


class _SocketClient:
    """Per-client state: connection, outbound queue, write thread, drop counters."""

    def __init__(self, conn: socket.socket, addr: str) -> None:
        self.conn = conn
        self.addr = addr
        self.queue: Queue[bytes] = Queue(maxsize=_CLIENT_QUEUE_MAXSIZE)
        self.thread: threading.Thread | None = None
        self.dropped_total = 0
        self.dropped_since_log = 0
        self.last_drop_log_ts = 0.0
        self.first_drop_logged = False


class UnixSocketTransport:
    """Stream events as newline-delimited JSON over an `AF_UNIX` socket.

    On construction, claims a bind path: `path` if it is absent or occupied by
    a stale file/dead socket (which is unlinked), or a `{stem}-{pid}{suffix}`
    sibling of `path` if a live listener already owns it (BUG-3324 — a second
    concurrent producer must never evict a first). It then starts an accept
    thread and accepts up to ``max_clients`` concurrent consumers. Each
    accepted client gets its own daemon thread and bounded outbound queue;
    ``send()`` enqueues the serialized event into every client queue without
    blocking. A full queue causes the newest event to be dropped (preserving
    causal order) and a rate-limited warning is logged.

    A misbehaving / disconnected client is removed from the pool without
    affecting other clients or the FSM thread.

    Not available on platforms without ``AF_UNIX`` (e.g. Windows). The platform
    check lives in :func:`wire_transports` so the user-facing error has clearer
    placement; constructing this class on a platform without ``AF_UNIX`` will
    raise an `OSError` from `socket.socket` directly.
    """

    def __init__(
        self,
        path: Path,
        max_clients: int = 32,
        on_connect: Callable[[_SocketClient], None] | None = None,
    ) -> None:
        if not hasattr(socket, "AF_UNIX"):
            raise RuntimeError(
                "UnixSocketTransport requires AF_UNIX, which is not available on this platform"
            )

        self._max_clients = max_clients
        self._on_connect = on_connect
        self._shutdown = threading.Event()
        self._clients: list[_SocketClient] = []
        self._clients_lock = threading.Lock()
        self._rejections_total: int = 0
        self._rejections_since_log: int = 0
        self._last_reject_log_ts: float = 0.0
        self._first_reject_logged: bool = False
        self._bound_id: tuple[int, int] | None = None

        path.parent.mkdir(parents=True, exist_ok=True)

        # BUG-3324: a second concurrent producer must not steal `path` out from
        # under a live listener. Claim it (probing for a live/stale/absent
        # owner) rather than unlinking blind; a live owner pushes us onto a
        # pid-suffixed sibling path instead.
        claimed = _claim_socket_path(path)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._server.bind(str(claimed))
        except OSError as exc:
            self._server.close()
            if exc.errno != errno.EADDRINUSE:
                raise
            # TOCTOU (BUG-3324): another producer won the race and bound
            # `claimed` between our probe and our bind(). Re-enter the claim
            # forcing the pid-suffixed fallback and retry once with a fresh
            # socket object (rebinding a socket whose bind() already failed is
            # platform-dependent).
            claimed = _claim_socket_path(path, force_suffix=True)
            self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                self._server.bind(str(claimed))
            except Exception:
                self._server.close()
                raise

        self._path = claimed
        if claimed != path:
            logger.info(
                "UnixSocketTransport: %s is in use by a live producer; bound %s instead",
                path,
                claimed,
            )
        try:
            self._bound_id = _stat_id(self._path)
            self._path.chmod(0o600)
            self._server.listen(max_clients)
            self._server.settimeout(_ACCEPT_POLL_TIMEOUT)
        except Exception:
            self._server.close()
            # Only unlink here if bind() actually succeeded above — a failure
            # in bind() itself never reaches this handler.
            self._path.unlink(missing_ok=True)
            raise

        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="unix-socket-transport-accept",
            daemon=True,
        )
        self._accept_thread.start()

    def _accept_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                conn, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                # Server socket closed during shutdown — exit cleanly
                return

            with self._clients_lock:
                if len(self._clients) >= self._max_clients:
                    self._record_rejection()
                    try:
                        conn.close()
                    except OSError:
                        pass
                    continue
                client = _SocketClient(conn, addr=str(self._path))
                client.thread = threading.Thread(
                    target=self._client_loop,
                    args=(client,),
                    name="unix-socket-transport-client",
                    daemon=True,
                )
                self._clients.append(client)
                if self._on_connect is not None:
                    self._on_connect(client)
                client.thread.start()

    def _client_loop(self, client: _SocketClient) -> None:
        try:
            while not self._shutdown.is_set():
                try:
                    payload = client.queue.get(timeout=_CLIENT_QUEUE_POLL_TIMEOUT)
                except Empty:
                    # BUG-3324: a client that never receives an event — most
                    # notably a liveness probe from `_probe_socket_path`,
                    # which connects and closes immediately — is otherwise
                    # only noticed on the next actual send()'s failed
                    # sendall(), leaving it occupying a slot indefinitely.
                    # A non-destructive peek on each idle poll detects a
                    # peer that already closed and retires the client
                    # promptly instead of waiting on the next event.
                    if self._peer_closed(client.conn):
                        return
                    continue
                try:
                    client.conn.sendall(payload)
                except OSError:
                    return
        finally:
            try:
                client.conn.close()
            except OSError:
                pass
            with self._clients_lock:
                if client in self._clients:
                    self._clients.remove(client)

    @staticmethod
    def _peer_closed(conn: socket.socket) -> bool:
        """Non-destructively check whether `conn`'s peer has closed its end."""
        try:
            conn.setblocking(False)
            try:
                return conn.recv(1, socket.MSG_PEEK) == b""
            except BlockingIOError:
                return False
            except OSError:
                return True
        finally:
            conn.setblocking(True)

    def send(self, event: dict[str, Any]) -> None:
        # FEAT-3323: stamp producer_pid onto a *copy* of event, never the
        # caller's own dict — EventBus.emit() passes the same mutable dict to
        # every registered transport, and a mutating stamp here would leak
        # producer_pid into JsonlTransport/SQLiteTransport/OTelTransport/
        # WebhookTransport whenever "socket" is listed alongside them.
        stamped = {**event, "producer_pid": os.getpid()}
        payload = (json.dumps(stamped) + "\n").encode("utf-8")
        with self._clients_lock:
            snapshot = list(self._clients)
        for client in snapshot:
            try:
                client.queue.put_nowait(payload)
            except Full:
                self._record_drop(client)

    def _record_drop(self, client: _SocketClient) -> None:
        client.dropped_total += 1
        client.dropped_since_log += 1
        now = time.monotonic()
        if not client.first_drop_logged:
            logger.warning(
                "UnixSocketTransport: dropping events for slow client (queue full at %d)",
                _CLIENT_QUEUE_MAXSIZE,
            )
            client.first_drop_logged = True
            client.last_drop_log_ts = now
            client.dropped_since_log = 0
            return
        if now - client.last_drop_log_ts >= _DROP_LOG_INTERVAL_SEC:
            logger.warning(
                "UnixSocketTransport: dropped %d events for slow client",
                client.dropped_since_log,
            )
            client.last_drop_log_ts = now
            client.dropped_since_log = 0

    def _record_rejection(self) -> None:
        """Rate-limited log for client rejections. Must be called under _clients_lock."""
        self._rejections_total += 1
        self._rejections_since_log += 1
        now = time.monotonic()
        if not self._first_reject_logged:
            logger.warning(
                "UnixSocketTransport: rejecting client; max_clients=%d reached",
                self._max_clients,
            )
            self._first_reject_logged = True
            self._last_reject_log_ts = now
            self._rejections_since_log = 0
            return
        if now - self._last_reject_log_ts >= _REJECT_LOG_INTERVAL_SEC:
            logger.warning(
                "UnixSocketTransport: rejected %d clients (max_clients=%d reached)",
                self._rejections_since_log,
                self._max_clients,
            )
            self._last_reject_log_ts = now
            self._rejections_since_log = 0

    def get_stats(self) -> dict[str, int]:
        """Return transport-level statistics."""
        return {"client_rejections": self._rejections_total}

    def close(self) -> None:
        deadline = time.monotonic() + _CLOSE_TOTAL_TIMEOUT
        self._shutdown.set()

        accept_budget = min(_ACCEPT_THREAD_JOIN_TIMEOUT, max(0.0, deadline - time.monotonic()))
        if self._accept_thread.is_alive():
            self._accept_thread.join(timeout=accept_budget)
            if self._accept_thread.is_alive():
                logger.warning(
                    "UnixSocketTransport: accept thread did not exit within %.1fs",
                    accept_budget,
                )

        try:
            self._server.close()
        except OSError:
            pass

        with self._clients_lock:
            snapshot = list(self._clients)
        for client in snapshot:
            try:
                client.conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            t = client.thread
            if t is not None and t.is_alive():
                budget = min(_CLIENT_THREAD_JOIN_TIMEOUT, max(0.0, deadline - time.monotonic()))
                t.join(timeout=budget)
                if t.is_alive():
                    logger.warning(
                        "UnixSocketTransport: client thread did not exit within %.1fs",
                        budget,
                    )

        # TOCTOU (BUG-3324): the drain above can take up to _CLOSE_TOTAL_TIMEOUT
        # seconds, during which another producer can probe this path, classify
        # it RECLAIMABLE (nothing is listening once the accept thread exits),
        # and bind it as its own. Unlinking by path alone would then delete
        # that producer's socket instead of ours, so re-stat and compare the
        # inode identity captured at bind() time before unlinking.
        if self._bound_id is not None:
            try:
                if _stat_id(self._path) == self._bound_id:
                    self._path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass


_SHUTDOWN = object()
"""Sentinel enqueued after the final rendered frame in `LocalBridgeTransport.close()`;
an SSE handler thread that dequeues this object (identity, not equality) exits its
write loop and returns, regardless of what `render_fragment` returned for the
`run_complete` event (including `None`)."""


class _SSEClient:
    """Per-SSE-client state: outbound queue, handler thread, drop counters."""

    def __init__(self) -> None:
        self.queue: Queue[Any] = Queue(maxsize=_CLIENT_QUEUE_MAXSIZE)
        self.thread: threading.Thread | None = None
        self.dropped_total = 0
        self.dropped_since_log = 0
        self.last_drop_log_ts = 0.0
        self.first_drop_logged = False


def _sse_encode(text: str) -> bytes:
    """Wrap `text` as an SSE `data:` frame, preserving embedded newlines per spec.

    Each line of `text` becomes its own ``data: <line>`` field; the frame ends with
    the blank line that terminates an SSE event.
    """
    lines = text.split("\n")
    frame = "".join(f"data: {line}\n" for line in lines) + "\n"
    return frame.encode("utf-8")


# ---------------------------------------------------------------------------
# Shared HTTP/SSE handler helpers (FEAT-3323)
#
# Extracted from `_make_local_bridge_handler`'s closure so `SseBridge`
# (`_make_sse_bridge_handler`, below) can reuse the Host check, the SSE write
# loop, and per-client drop accounting without depending on a
# `LocalBridgeTransport` instance — that would make the bridge an `EventBus`
# transport, contradicting § Proposed Solution (FEAT-3323 is an out-of-process
# consumer, not a sixth transport). `TestLocalBridgeTransport` pins this
# refactor: it must stay green unmodified.
# ---------------------------------------------------------------------------


def _expected_hosts(port: int) -> set[str]:
    """The two `Host` header values a loopback-bound server at `port` accepts.

    `::1` is deliberately absent: both bridges bind IPv4 loopback only, so a
    `Host: [::1]:<port>` request cannot legitimately arrive.
    """
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


def _record_sse_client_drop(client: _SSEClient, log_prefix: str) -> None:
    """Rate-limited drop-count bookkeeping for a per-SSE-client bounded queue.

    Shared by `LocalBridgeTransport` (ENH-3351) and `SseBridge` (FEAT-3323);
    `log_prefix` names the calling class so log lines stay attributable —
    text is otherwise identical to the pre-extraction per-class methods.
    """
    client.dropped_total += 1
    client.dropped_since_log += 1
    now = time.monotonic()
    if not client.first_drop_logged:
        logger.warning(
            "%s: dropping events for slow SSE client (queue full at %d)",
            log_prefix,
            _CLIENT_QUEUE_MAXSIZE,
        )
        client.first_drop_logged = True
        client.last_drop_log_ts = now
        client.dropped_since_log = 0
        return
    if now - client.last_drop_log_ts >= _DROP_LOG_INTERVAL_SEC:
        logger.warning(
            "%s: dropped %d events for slow SSE client",
            log_prefix,
            client.dropped_since_log,
        )
        client.last_drop_log_ts = now
        client.dropped_since_log = 0


def _serve_sse_stream(
    handler: http.server.BaseHTTPRequestHandler,
    clients: list[_SSEClient],
    clients_lock: threading.Lock,
    *,
    closed: Callable[[], bool],
    max_clients: int | None = None,
    keepalive_s: float | None = None,
    send_retry: bool = False,
    seed: Callable[[], list[bytes]] | None = None,
) -> None:
    """Register `handler` as an SSE client, stream frames, then deregister.

    Generalizes `_make_local_bridge_handler`'s original `_serve_events`
    (ENH-3351) with optional client cap / keepalive / `retry:` / seed
    parameters, all defaulting to off so `LocalBridgeTransport`'s existing
    behavior (no cap, no keepalive, no retry line, no seed) is unchanged.

    - `max_clients`: when given and already reached, responds `503` and
      returns *without* registering a client or writing stream headers.
    - `keepalive_s`: when given, writes an SSE comment frame (`: ping\\n\\n`)
      whenever the queue has been idle for this long.
    - `send_retry`: when True, a `retry: 2000` line (2s; no `id:` line is ever
      sent — there is no durable buffer to replay) is merged onto the first
      block actually written to the wire — a seed frame, a live frame, or a
      keepalive ping, whichever comes first — as an extra line inside that
      same blank-line-terminated SSE block, rather than sent as its own
      field-less block. This keeps a client that reads "one blank-line-
      terminated block = one frame" correct even when the very next real
      content is unknown at stream-open time (an empty seed, then a wait for
      the first live event).
    - `seed`: when given, called once — after the client is registered in
      `clients` (so a concurrently-relayed live event is already queued
      rather than lost) but before the queue is drained — and its returned
      frames are written directly to the wire.
    """
    if max_clients is not None:
        with clients_lock:
            if len(clients) >= max_clients:
                handler.send_error(503, "Too many SSE clients")
                return

    client = _SSEClient()
    client.thread = threading.current_thread()
    with clients_lock:
        clients.append(client)
    pending_prefix = b"retry: 2000\n" if send_retry else b""
    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.end_headers()
        if seed is not None:
            frames = seed()
            if frames:
                try:
                    handler.wfile.write(pending_prefix + frames[0])
                    for frame in frames[1:]:
                        handler.wfile.write(frame)
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
                pending_prefix = b""

        next_keepalive = time.monotonic() + keepalive_s if keepalive_s else None
        while True:
            timeout = _CLIENT_QUEUE_POLL_TIMEOUT
            if next_keepalive is not None:
                timeout = min(timeout, max(0.0, next_keepalive - time.monotonic()))
            try:
                frame = client.queue.get(timeout=timeout)
            except Empty:
                if closed():
                    return
                if next_keepalive is not None and time.monotonic() >= next_keepalive:
                    try:
                        handler.wfile.write(pending_prefix + b": ping\n\n")
                        handler.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    pending_prefix = b""
                    assert keepalive_s is not None  # narrowed by next_keepalive is not None above
                    next_keepalive = time.monotonic() + keepalive_s
                continue
            if frame is _SHUTDOWN:
                # A never-consumed pending_prefix (retry: 2000, merged onto
                # whatever real content arrives first) is simply dropped here
                # rather than written alone: a bare "retry: 2000\n" with no
                # blank-line terminator is neither a complete SSE frame nor
                # nothing, and a client tearing down expects the stream to
                # just end.
                return
            try:
                handler.wfile.write(pending_prefix + frame)
                handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
            pending_prefix = b""
    finally:
        # This connection is a one-shot indefinite stream, never reused for a
        # subsequent request — see the original comment this replaces at
        # `_make_local_bridge_handler._serve_events` for why `close_connection`
        # must be forced True here.
        handler.close_connection = True
        with clients_lock:
            if client in clients:
                clients.remove(client)


def _make_local_bridge_handler(
    transport: LocalBridgeTransport,
) -> type[http.server.BaseHTTPRequestHandler]:
    """Build a `BaseHTTPRequestHandler` subclass bound to `transport` via closure."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        server_version = "ll-local-bridge/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug("LocalBridgeTransport: " + format, *args)

        def _expected_hosts(self) -> set[str]:
            return _expected_hosts(transport._server.server_address[1])

        def _route(self) -> str | None:
            """Return the path suffix after `/{token}/`, or None if the prefix doesn't match."""
            path = self.path.split("?", 1)[0]
            prefix = f"/{transport._token}"
            if path in (prefix, prefix + "/"):
                return ""
            if path.startswith(prefix + "/"):
                return path[len(prefix) + 1 :]
            return None

        def do_GET(self) -> None:  # noqa: N802
            if self.headers.get("Host") not in self._expected_hosts():
                self.send_error(403, "Forbidden host")
                return
            route = self._route()
            if route is None:
                self.send_error(404, "Not found")
                return
            if route == "":
                self._serve_page()
            elif route == "events":
                self._serve_events()
            else:
                self.send_error(404, "Not found")

        def do_POST(self) -> None:  # noqa: N802
            if self.headers.get("Host") not in self._expected_hosts():
                self.send_error(403, "Forbidden host")
                return
            route = self._route()
            if route is None:
                self.send_error(404, "Not found")
                return
            if route == "interaction":
                self._handle_interaction()
            else:
                self.send_error(404, "Not found")

        def _serve_page(self) -> None:
            body = transport._page_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_events(self) -> None:
            _serve_sse_stream(
                self,
                transport._clients,
                transport._clients_lock,
                closed=lambda: transport._closed,
            )

        def _handle_interaction(self) -> None:
            length_header = self.headers.get("Content-Length")
            try:
                length = int(length_header) if length_header is not None else 0
            except ValueError:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            # Respond before touching `inbound` — a full/misbehaving inbound queue
            # must never surface as an HTTP-layer failure to the caller.
            self.send_response(204)
            self.end_headers()
            if transport._inbound is None:
                return
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                transport._record_inbound_drop("invalid JSON body")
                return
            if not isinstance(parsed, dict):
                transport._record_inbound_drop("non-dict JSON body")
                return
            try:
                transport._inbound.put_nowait(parsed)
            except Full:
                transport._record_inbound_drop("inbound queue full")

    return _Handler


class LocalBridgeTransport:
    """Loopback-only SSE bridge (ARTIFACT_CONTROL_LEVELS Level 3).

    Binds a stdlib `http.server.ThreadingHTTPServer` to `127.0.0.1` only (never
    `0.0.0.0` — there is no host-override parameter, deliberately stricter than
    `mcp_server/server.py`'s optional host override). All endpoints sit under a
    per-run token prefix (`secrets.token_urlsafe(16)`, generated at construction
    time): a request whose path doesn't start with `/{token}/` gets `404`. A
    request whose `Host` header isn't exactly `127.0.0.1:<port>` or
    `localhost:<port>` gets `403` (DNS-rebinding guard) — loopback binding alone
    does not stop a malicious page in the user's own browser from firing
    drive-by requests.

    Bidirectional, unlike the other built-in transports:

    - `GET /{token}/` serves `page_html` verbatim (or a minimal placeholder if
      `page_html` is None — the real dashboard page is built by CLI wiring, not
      by this class).
    - `GET /{token}/events` is `text/event-stream`. Each connecting client gets
      its own bounded outbound `Queue`, decoupled from `send()`'s bookkeeping
      the same way `UnixSocketTransport._SocketClient` decouples its clients. A
      full per-client queue drops the newest event and logs a rate-limited
      warning, mirroring `UnixSocketTransport.send()`.
    - `POST /{token}/interaction` reads the JSON request body and, if `inbound`
      was supplied, `inbound.put_nowait()`s the parsed dict unchanged. A full
      queue or invalid body is dropped silently (rate-limited warning); this
      handler never raises back to the HTTP layer.

    `send(event)` (the `Transport.send` outbound direction) renders `event` via
    the constructor-injected `render_fragment` callable if supplied — returning
    `str | None`, where `None` means "skip this event", and any embedded
    newlines become multiple `data:` lines per the SSE spec — or, when
    `render_fragment` is None (the default), forwards raw JSON
    (`data: {json.dumps(event)}\\n\\n`). The rendered frame fans out to every
    currently-connected SSE client's queue.

    Shutdown mechanics: `ThreadingHTTPServer` is constructed with
    `daemon_threads = True` so teardown never hangs on stdlib's
    `server_close()` (which does not join daemon threads). `close()` renders a
    final `{"event": "run_complete"}` frame the same way `send()` renders any
    other event, pushes it (followed by a private `_SHUTDOWN` sentinel object)
    into every currently-connected client's queue, then shuts the HTTP server
    down. Each SSE handler's write loop recognizes the `_SHUTDOWN` sentinel,
    writes the final frame, and returns — exiting its thread — regardless of
    what `render_fragment` returned for the sentinel event. Handlers catch
    `BrokenPipeError`/`ConnectionResetError` on write and deregister that
    client's queue from the fan-out list on any write failure (dead-client
    pruning) rather than crashing the handler thread. `close()` joins each
    handler thread within a bounded budget before returning.
    """

    def __init__(
        self,
        port: int = 0,
        inbound: Queue[dict[str, Any]] | None = None,
        render_fragment: Callable[[dict[str, Any]], str | None] | None = None,
        page_html: str | None = None,
    ) -> None:
        self._token = secrets.token_urlsafe(16)
        self._inbound = inbound
        self._render_fragment = render_fragment
        self._page_html = page_html if page_html is not None else _LOCAL_BRIDGE_DEFAULT_PAGE_HTML

        self._clients: list[_SSEClient] = []
        self._clients_lock = threading.Lock()
        self._closed = False

        self._inbound_drops_total = 0
        self._inbound_drops_since_log = 0
        self._last_inbound_drop_log_ts = 0.0
        self._inbound_drop_logged = False

        handler_cls = _make_local_bridge_handler(self)
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
        self._server.daemon_threads = True

        self._serve_thread = threading.Thread(
            target=self._server.serve_forever,
            name="local-bridge-transport-serve",
            daemon=True,
        )
        self._serve_thread.start()

    @property
    def url(self) -> str:
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/{self._token}/"

    def set_page_html(self, page_html: str) -> None:
        """Replace the HTML served at ``GET /{token}/`` after construction.

        The served page typically needs to embed this transport's own `url`
        (for its SSE/interaction endpoints), which is only known once the
        server is bound — so callers construct the transport first, build the
        page from `url`, then call this instead of passing `page_html` to
        `__init__`.
        """
        self._page_html = page_html

    def send(self, event: dict[str, Any]) -> None:
        frame = self._render_event(event)
        if frame is None:
            return
        with self._clients_lock:
            snapshot = list(self._clients)
        for client in snapshot:
            try:
                client.queue.put_nowait(frame)
            except Full:
                self._record_drop(client)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        final_frame = self._render_event({"event": "run_complete"})
        with self._clients_lock:
            snapshot = list(self._clients)
        for client in snapshot:
            if final_frame is not None:
                try:
                    client.queue.put_nowait(final_frame)
                except Full:
                    self._record_drop(client)
            try:
                client.queue.put_nowait(_SHUTDOWN)
            except Full:
                # Queue saturated even for the sentinel: the handler's idle-poll
                # timeout still notices `self._closed` and exits on its own.
                pass

        try:
            self._server.shutdown()
        except Exception:
            pass
        try:
            self._server.server_close()
        except Exception:
            pass

        deadline = time.monotonic() + _LOCAL_BRIDGE_CLOSE_TIMEOUT
        for client in snapshot:
            t = client.thread
            if t is not None and t.is_alive():
                budget = min(
                    _LOCAL_BRIDGE_THREAD_JOIN_TIMEOUT, max(0.0, deadline - time.monotonic())
                )
                t.join(timeout=budget)
                if t.is_alive():
                    logger.warning(
                        "LocalBridgeTransport: SSE handler thread did not exit within %.1fs",
                        budget,
                    )

        if self._serve_thread.is_alive():
            self._serve_thread.join(timeout=_LOCAL_BRIDGE_SERVE_THREAD_JOIN_TIMEOUT)

    def _render_event(self, event: dict[str, Any]) -> bytes | None:
        if self._render_fragment is not None:
            text = self._render_fragment(event)
            if text is None:
                return None
        else:
            text = json.dumps(event)
        return _sse_encode(text)

    def _record_drop(self, client: _SSEClient) -> None:
        _record_sse_client_drop(client, "LocalBridgeTransport")

    def _record_inbound_drop(self, reason: str) -> None:
        self._inbound_drops_total += 1
        self._inbound_drops_since_log += 1
        now = time.monotonic()
        if not self._inbound_drop_logged:
            logger.warning("LocalBridgeTransport: dropping interaction POST (%s)", reason)
            self._inbound_drop_logged = True
            self._last_inbound_drop_log_ts = now
            self._inbound_drops_since_log = 0
            return
        if now - self._last_inbound_drop_log_ts >= _DROP_LOG_INTERVAL_SEC:
            logger.warning(
                "LocalBridgeTransport: dropped %d interaction POSTs",
                self._inbound_drops_since_log,
            )
            self._last_inbound_drop_log_ts = now
            self._inbound_drops_since_log = 0


# ---------------------------------------------------------------------------
# SseBridge (FEAT-3323): out-of-process localhost SSE consumer of
# UnixSocketTransport. Not a Transport, never held by an EventBus — it
# fans in every live producer socket in the project and relays the merged
# stream to browser SSE clients. See the issue's § Program Design / § Server
# mechanics / § Fan-in / § Seeding for the authoritative design.
# ---------------------------------------------------------------------------

_SSE_BRIDGE_PAGE_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>little-loops: live event stream</title>
<style>
  body { font-family: ui-monospace, Menlo, Consolas, monospace; margin: 1rem; }
  .line { border-bottom: 1px solid #eee; padding: 2px 0; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>little-loops: live event stream</h1>
<p id="status">connecting...</p>
<div id="log"></div>
<script>
(function () {
  var statusEl = document.getElementById("status");
  var logEl = document.getElementById("log");
  var sseUrl = location.pathname.replace(/\\/?$/, "/") + "events";
  var source = new EventSource(sseUrl);
  source.addEventListener("open", function () {
    statusEl.textContent = "connected";
  });
  source.addEventListener("error", function () {
    statusEl.textContent = "reconnecting...";
  });
  source.addEventListener("message", function (event) {
    var line = document.createElement("div");
    line.className = "line";
    line.textContent = event.data;
    logEl.appendChild(line);
  });
})();
</script>
</body>
</html>"""


class _ProducerReader:
    """One per connected producer socket: the socket, its reader thread, and
    the bookkeeping `_fan_in_producer_sockets` needs to detect death and the
    connect-then-immediate-EOF backoff case (§ Fan-in → Backoff)."""

    def __init__(self, path: Path, sock: socket.socket) -> None:
        self.path = path
        self.sock = sock
        self.thread: threading.Thread | None = None
        self.connected_at = time.monotonic()
        self.forwarded_any = False


class _FanInPathState:
    """Per-path backoff bookkeeping for `_fan_in_producer_sockets` (§ Fan-in → Backoff)."""

    __slots__ = ("interval", "next_attempt", "warned")

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.next_attempt = 0.0
        self.warned = False


def _read_producer_socket(
    sock: socket.socket,
    out: Queue[bytes],
    stop: threading.Event,
    *,
    on_forward: Callable[[], None] | None = None,
    on_drop: Callable[[], None] | None = None,
) -> None:
    """Reader thread body for one connected producer socket (§ Fan-in).

    Reads newline-delimited JSON lines, splits on ``\\n``, forwards each
    complete line unchanged to the shared bounded queue `out` (drop-newest
    when full, via `on_drop`) and keeps the trailing partial line for the
    next `recv()`. `state_change` lines are filtered: that event exists only
    as a producer's socket-connect seed (`_make_seed_callback`) — with N
    producers the bridge would otherwise receive N unstamped copies of the
    same seed set — and the bridge rebuilds its own seed per SSE client
    instead (`_sse_bridge_seed_frames`). A line that fails to parse as JSON
    is skipped with a warning. Returns (thread exit) on EOF or any socket
    error; the caller detects this via `reader.thread.is_alive()` on its next
    rescan.
    """
    sock.settimeout(_PRODUCER_READ_POLL_TIMEOUT)
    buffer = b""
    while not stop.is_set():
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            continue
        except OSError:
            return
        if not chunk:
            return
        buffer += chunk
        while b"\n" in buffer:
            line, _, buffer = buffer.partition(b"\n")
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("SseBridge: skipping non-JSON line from a producer socket")
                continue
            if isinstance(parsed, dict) and parsed.get("event") == "state_change":
                continue
            try:
                out.put_nowait(line + b"\n")
            except Full:
                if on_drop is not None:
                    on_drop()
                continue
            if on_forward is not None:
                on_forward()


def _candidate_producer_paths(socket_path: Path) -> list[Path]:
    """Every path the bridge should fan in from: `socket_path` and its BUG-3324 siblings.

    ``{stem}{suffix}`` (the configured, un-suffixed path) union
    ``{stem}-*{suffix}`` (pid-suffixed concurrent-producer siblings,
    `_claim_socket_path`). Matched by exact filename comparison rather than
    `Path.glob()` so a `stem` containing a glob-special character can't turn
    this into an unintended wildcard.
    """
    directory = socket_path.parent
    stem = socket_path.stem
    suffix = socket_path.suffix
    sibling_prefix = f"{stem}-"
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    candidates = [
        p
        for p in entries
        if p.name == socket_path.name
        or (p.name.startswith(sibling_prefix) and p.name.endswith(suffix))
    ]
    return sorted(candidates)


def _fan_in_producer_sockets(
    socket_path: Path,
    out: Queue[bytes],
    stop: threading.Event,
    rescan_s: float = 2.0,
    *,
    readers: dict[Path, _ProducerReader] | None = None,
    on_drop: Callable[[], None] | None = None,
) -> None:
    """Rescan loop: discover producer sockets, connect, and merge their events into `out`.

    Runs until `stop` is set. Owns the `_ProducerReader` set (`readers`, keyed
    by bound path — bridge-owned, so `SseBridge.close()` can reach every
    producer client socket directly) and detects reader death via
    `reader.thread.is_alive()` on each rescan.

    Connect is the probe: a path already in `readers` is never re-probed
    (that would consume one of the producer's `max_clients` slots and
    re-trigger its `on_connect` seed). A stale file (`ECONNREFUSED` /
    `ENOTSOCK`) is skipped and never unlinked — reclaiming a dead socket file
    is the producer's job. A reader that dies within one `rescan_s` of
    connecting without forwarding a single line marks its path "flapping"
    (§ Fan-in → Backoff): the retry interval doubles each consecutive flap,
    capped at 60s, logs once per path, and resets on the first forwarded
    line.
    """
    readers = readers if readers is not None else {}
    path_state: dict[Path, _FanInPathState] = {}
    stale_logged: set[Path] = set()

    while not stop.is_set():
        now = time.monotonic()

        # Reap dead readers and update backoff state.
        for path in list(readers):
            reader = readers[path]
            if reader.thread is not None and reader.thread.is_alive():
                continue
            del readers[path]
            try:
                reader.sock.close()
            except OSError:
                pass
            state = path_state.setdefault(path, _FanInPathState(rescan_s))
            elapsed = now - reader.connected_at
            if not reader.forwarded_any and elapsed < rescan_s:
                state.interval = min(state.interval * 2, _FANIN_MAX_BACKOFF_S)
                if not state.warned:
                    logger.warning(
                        "SseBridge: producer at %s closed the connection immediately; "
                        "at max_clients?",
                        path,
                    )
                    state.warned = True
            else:
                state.interval = rescan_s
                state.warned = False
            state.next_attempt = now + state.interval

        # Discover and connect to new candidates.
        for path in _candidate_producer_paths(socket_path):
            if path in readers:
                continue
            existing_state = path_state.get(path)
            if existing_state is not None and now < existing_state.next_attempt:
                continue

            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(_FANIN_CONNECT_TIMEOUT)
                probe.connect(str(path))
            except OSError as exc:
                probe.close()
                if exc.errno in (errno.ECONNREFUSED, errno.ENOTSOCK):
                    if path not in stale_logged:
                        logger.debug("SseBridge: stale socket file %s, skipping", path)
                        stale_logged.add(path)
                continue
            stale_logged.discard(path)
            probe.settimeout(None)

            reader = _ProducerReader(path, probe)
            reader.connected_at = now
            readers[path] = reader

            def _on_forward(reader: _ProducerReader = reader, path: Path = path) -> None:
                if not reader.forwarded_any:
                    reader.forwarded_any = True
                    fwd_state = path_state.get(path)
                    if fwd_state is not None:
                        fwd_state.interval = rescan_s
                        fwd_state.warned = False

            reader.thread = threading.Thread(
                target=_read_producer_socket,
                args=(probe, out, stop),
                kwargs={"on_forward": _on_forward, "on_drop": on_drop},
                name="sse-bridge-producer-reader",
                daemon=True,
            )
            reader.thread.start()

        stop.wait(timeout=rescan_s)


def _sse_bridge_seed_frames(loops_dir: Path) -> list[bytes]:
    """One encoded `state_change` SSE frame per running-loop state file (§ Seeding).

    Bridge-owned seeding: producers seed a client only once, at socket-connect
    time, and the bridge is a long-lived socket client, so an SSE tab that
    (re)connects would get nothing unless the bridge rebuilds the seed itself
    from `list_running_loops` on every connect. `producer_pid` is set to
    `state.pid` (the loop's owning process — the honest attribution, since the
    bridge and not a producer emitted this frame) when that is not `None`,
    and omitted — never `null` — otherwise, matching `LoopState.to_dict()`'s
    own omission of an unset `pid`. `to_dict()` already emits `pid` when set,
    so a seed frame carries both `pid` and `producer_pid` with the same value
    — the redundancy is deliberate (one demux key on every frame).
    """
    frames: list[bytes] = []
    for state in list_running_loops(loops_dir):
        event: dict[str, Any] = {"event": "state_change", **state.to_dict()}
        if state.pid is not None:
            event["producer_pid"] = state.pid
        frames.append(_sse_encode(json.dumps(event)))
    return frames


def _make_sse_bridge_handler(bridge: SseBridge) -> type[http.server.BaseHTTPRequestHandler]:
    """Build a `BaseHTTPRequestHandler` subclass bound to `bridge` via closure.

    Dispatches through `bridge._routes` (page `""`, SSE `"events"`, plus any
    caller-supplied routes — the FEAT-3321 mount point) after the Host and
    token checks, rather than hardcoding the two routes the way
    `_make_local_bridge_handler` does.
    """

    class _Handler(http.server.BaseHTTPRequestHandler):
        server_version = "ll-sse-bridge/1.0"
        # § Server mechanics → Write timeout: bounds how long a peer that is
        # alive but not reading can pin this handler thread on a blocked
        # wfile.write() — StreamRequestHandler.setup() applies this as
        # settimeout() on the connection, so a wedged write raises
        # TimeoutError (an OSError, already caught by the SSE write loop).
        timeout = 2 * bridge._config.keepalive_s

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug("SseBridge: " + format, *args)

        def do_GET(self) -> None:  # noqa: N802
            port = bridge._server.server_address[1]
            if self.headers.get("Host") not in _expected_hosts(port):
                self.send_error(403, "Forbidden host")
                return
            path = self.path.split("?", 1)[0]
            prefix = f"/{bridge._token}"
            if path == prefix:
                # § Page → Trailing slash: a relative `./events` resolves to
                # `/events` from the slash-less form and 404s.
                self.send_response(301)
                self.send_header("Location", prefix + "/")
                self.end_headers()
                return
            if not path.startswith(prefix + "/"):
                self.send_error(404, "Not found")
                return
            route = path[len(prefix) + 1 :]
            handler_fn = bridge._routes.get(route)
            if handler_fn is None:
                self.send_error(404, "Not found")
                return
            handler_fn(self)

    return _Handler


class SseBridge:
    """Out-of-process localhost SSE bridge over `UnixSocketTransport` (FEAT-3323).

    Mirrors `LocalBridgeTransport`'s shape (constructor binds, `.url`,
    `.close()`) so tests get a handle, but is **not** a `Transport` and is
    never added to an `EventBus` — it is a client of every live producer
    socket in the project, not a sixth transport. See the issue's
    § Program Design for the full design; § Server mechanics / § Fan-in /
    § Seeding for the mechanics this class composes.
    """

    def __init__(
        self,
        config: EventsConfig,
        port: int | None = None,
        *,
        base: Path | None = None,
        loops_dir: Path | None = None,
        routes: dict[str, Callable[[http.server.BaseHTTPRequestHandler], None]] | None = None,
    ) -> None:
        self._config = config.bridge
        self._loops_dir = loops_dir if loops_dir is not None else Path(".loops")
        self._token = secrets.token_urlsafe(16)
        self._closed = False
        self._stop = threading.Event()

        self._clients: list[_SSEClient] = []
        self._clients_lock = threading.Lock()

        self._fanin_queue: Queue[bytes] = Queue(maxsize=_CLIENT_QUEUE_MAXSIZE)
        self._producer_readers: dict[Path, _ProducerReader] = {}
        self._fanin_dropped_total = 0
        self._fanin_dropped_since_log = 0
        self._fanin_last_drop_log_ts = 0.0
        self._fanin_first_drop_logged = False

        self._page_html = _SSE_BRIDGE_PAGE_HTML
        self._routes: dict[str, Callable[[http.server.BaseHTTPRequestHandler], None]] = {
            "": self._serve_page,
            "events": self._serve_events,
        }
        if routes:
            self._routes.update(routes)

        bind_port = port if port is not None else self._config.port

        # § Startup and shutdown → Bind before starting threads: construct the
        # ThreadingHTTPServer (the bind) first. A bind failure (e.g. EADDRINUSE)
        # then leaves nothing to clean up; starting the fan-in/relay threads
        # first would leak a fan-in thread scanning the socket directory on
        # every port-in-use failure.
        handler_cls = _make_sse_bridge_handler(self)
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", bind_port), handler_cls)
        self._server.daemon_threads = True

        base_dir = base if base is not None else Path(".ll")
        socket_path = _resolve_socket_path(config.socket.path, base_dir)

        self._serve_thread = threading.Thread(
            target=self._server.serve_forever,
            name="sse-bridge-serve",
            daemon=True,
        )
        self._fanin_thread = threading.Thread(
            target=_fan_in_producer_sockets,
            args=(socket_path, self._fanin_queue, self._stop, self._config.rescan_s),
            kwargs={"readers": self._producer_readers, "on_drop": self._record_fanin_drop},
            name="sse-bridge-fanin",
            daemon=True,
        )
        self._relay_thread = threading.Thread(
            target=self._relay_loop,
            name="sse-bridge-relay",
            daemon=True,
        )
        self._serve_thread.start()
        self._fanin_thread.start()
        self._relay_thread.start()

    @property
    def url(self) -> str:
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/{self._token}/"

    def set_page_html(self, page_html: str) -> None:
        """Replace the HTML served at ``GET /{token}/`` after construction (FEAT-3321).

        Mirrors `LocalBridgeTransport.set_page_html`; needed because the
        FEAT-3321 dashboard page embeds `self.url` (token), known only once
        the server is bound. Initialized to `_SSE_BRIDGE_PAGE_HTML` in
        `__init__` and never called at all when `events.bridge.history` is
        off, so the default path stays byte-for-byte FEAT-3323 behavior.
        """
        self._page_html = page_html

    def _serve_page(self, handler: http.server.BaseHTTPRequestHandler) -> None:
        body = self._page_html.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _serve_events(self, handler: http.server.BaseHTTPRequestHandler) -> None:
        _serve_sse_stream(
            handler,
            self._clients,
            self._clients_lock,
            closed=lambda: self._closed,
            max_clients=self._config.max_clients,
            keepalive_s=self._config.keepalive_s,
            send_retry=True,
            seed=lambda: _sse_bridge_seed_frames(self._loops_dir),
        )

    def _relay_loop(self) -> None:
        """Pop raw producer lines off the merged queue, SSE-encode, and fan out.

        `_fan_in_producer_sockets`/`_read_producer_socket` forward each
        producer line *unchanged* into `self._fanin_queue` (it is already the
        serialized envelope, per § Fan-in → Reader loop); this is the one
        place that wraps it as an SSE `data:` frame before it reaches any
        per-client queue.
        """
        while not self._stop.is_set():
            try:
                payload = self._fanin_queue.get(timeout=_CLIENT_QUEUE_POLL_TIMEOUT)
            except Empty:
                continue
            frame = _sse_encode(payload.decode("utf-8").rstrip("\n"))
            with self._clients_lock:
                snapshot = list(self._clients)
            for client in snapshot:
                try:
                    client.queue.put_nowait(frame)
                except Full:
                    _record_sse_client_drop(client, "SseBridge")

    def _record_fanin_drop(self) -> None:
        """Rate-limited drop accounting for the merged fan-in queue (§ Fan-in → Shared queue)."""
        self._fanin_dropped_total += 1
        self._fanin_dropped_since_log += 1
        now = time.monotonic()
        if not self._fanin_first_drop_logged:
            logger.warning(
                "SseBridge: dropping fan-in events (merged queue full at %d)",
                _CLIENT_QUEUE_MAXSIZE,
            )
            self._fanin_first_drop_logged = True
            self._fanin_last_drop_log_ts = now
            self._fanin_dropped_since_log = 0
            return
        if now - self._fanin_last_drop_log_ts >= _DROP_LOG_INTERVAL_SEC:
            logger.warning(
                "SseBridge: dropped %d fan-in events (merged queue full)",
                self._fanin_dropped_since_log,
            )
            self._fanin_last_drop_log_ts = now
            self._fanin_dropped_since_log = 0

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()

        # Close every producer client socket: each producer's _client_loop
        # then retires the slot via _peer_closed (transport.py:274), and any
        # reader thread blocked in recv() wakes immediately.
        for reader in list(self._producer_readers.values()):
            try:
                reader.sock.close()
            except OSError:
                pass

        with self._clients_lock:
            snapshot = list(self._clients)
        for client in snapshot:
            try:
                client.queue.put_nowait(_SHUTDOWN)
            except Full:
                pass

        try:
            self._server.shutdown()
        except Exception:
            pass
        try:
            self._server.server_close()
        except Exception:
            pass

        deadline = time.monotonic() + _SSE_BRIDGE_CLOSE_TIMEOUT
        for reader in list(self._producer_readers.values()):
            t = reader.thread
            if t is not None and t.is_alive():
                budget = min(_SSE_BRIDGE_THREAD_JOIN_TIMEOUT, max(0.0, deadline - time.monotonic()))
                t.join(timeout=budget)
        for client in snapshot:
            t = client.thread
            if t is not None and t.is_alive():
                budget = min(_SSE_BRIDGE_THREAD_JOIN_TIMEOUT, max(0.0, deadline - time.monotonic()))
                t.join(timeout=budget)
                if t.is_alive():
                    logger.warning(
                        "SseBridge: SSE handler thread did not exit within %.1fs", budget
                    )
        if self._fanin_thread.is_alive():
            self._fanin_thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if self._relay_thread.is_alive():
            self._relay_thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if self._serve_thread.is_alive():
            self._serve_thread.join(timeout=max(0.0, deadline - time.monotonic()))


def serve_sse_bridge(
    config: EventsConfig,
    port: int | None = None,
    *,
    routes: dict[str, Callable[[http.server.BaseHTTPRequestHandler], None]] | None = None,
    page_html_factory: Callable[[SseBridge], str] | None = None,
) -> int:
    """Blocking CLI wrapper: construct `SseBridge`, print its URL, block until Ctrl-C.

    `ll-artifact serve`'s `cmd_serve` calls this after resolving `--port` and
    checking for an existing `events.transports`/producer-socket setup.
    Binds `127.0.0.1` only (the `SseBridge` constructor's own default).
    Returns `0` on a clean `KeyboardInterrupt` shutdown. A bind failure
    (`OSError`, e.g. `EADDRINUSE`) or `AF_UNIX` unavailability propagates to
    the caller, which translates it into the documented exit codes (§ Startup
    and shutdown).

    If `"socket"` is absent from `config.transports`, or no producer socket
    is present yet, prints a plain one-line notice to stderr rather than
    silently serving an empty stream as success — but keeps serving, since a
    producer may start later (§ Considerations).

    `routes`/`page_html_factory` are FEAT-3321's optional history-route hook:
    `routes` is passed through to `SseBridge(...)`, and once bound,
    `page_html_factory(bridge)` (which needs `bridge.url` for the token) is
    called and its result installed via `bridge.set_page_html`. Any exception
    `page_html_factory` raises is caught, logged as a warning, and swallowed —
    the placeholder page stays and the bridge keeps serving; a page-render
    failure must never prevent the bridge from starting.
    """
    bridge = SseBridge(config, port=port, routes=routes)
    if page_html_factory is not None:
        try:
            bridge.set_page_html(page_html_factory(bridge))
        except Exception:
            logger.warning(
                "SseBridge: page_html_factory failed; serving the placeholder page instead",
                exc_info=True,
            )
    print(bridge.url)
    if "socket" not in config.transports:
        print(
            '"socket" is not in events.transports; no producer is reachable until a '
            "run adds it. Serving anyway — a producer may start later.",
            file=sys.stderr,
        )
    else:
        resolved = _resolve_socket_path(config.socket.path, Path(".ll"))
        if not _candidate_producer_paths(resolved):
            print(
                f"no producer socket found at {resolved} (or its BUG-3324 pid-suffixed "
                "siblings); serving anyway — a producer may start later.",
                file=sys.stderr,
            )
    try:
        while bridge._serve_thread.is_alive():
            bridge._serve_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
    return 0


def _stat_id(path: Path) -> tuple[int, int]:
    """Return the `(st_dev, st_ino)` identity of `path`."""
    st = os.stat(path)
    return (st.st_dev, st.st_ino)


class _PathState(enum.Enum):
    """Classification of a socket path's occupant, per BUG-3324."""

    LIVE = "live"
    ABSENT = "absent"
    RECLAIMABLE = "reclaimable"


def _probe_socket_path(path: Path, timeout: float = _SOCKET_PROBE_TIMEOUT) -> _PathState:
    """Classify what currently occupies `path` without mutating anything.

    Connects to `path` as a client would and inspects the outcome:

    - Connects successfully -> a live listener owns it (`LIVE`).
    - `FileNotFoundError` (`ENOENT`) -> nothing is there (`ABSENT`).
    - `ENOTSOCK` (a regular file) or `ECONNREFUSED` (a bound-but-dead socket)
      -> safe to reclaim (`RECLAIMABLE`).
    - Anything else (`EACCES`/`EPERM` from a different uid's `chmod 0600`
      socket, a probe timeout, `EAGAIN`, ...) -> assume `LIVE`. Erring toward
      "occupied" means a second producer takes a suffixed path rather than
      ever evicting one it can't positively rule out.
    """
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(timeout)
        try:
            probe.connect(str(path))
            return _PathState.LIVE
        except FileNotFoundError:
            return _PathState.ABSENT
        except OSError as exc:
            if exc.errno in (errno.ENOTSOCK, errno.ECONNREFUSED):
                return _PathState.RECLAIMABLE
            return _PathState.LIVE
    finally:
        probe.close()


def _claim_socket_path(configured: Path, *, force_suffix: bool = False) -> Path:
    """Return the path a new `UnixSocketTransport` should `bind()` to.

    Never binds. Probes `configured` (unless `force_suffix`) and unlinks it
    only when `RECLAIMABLE`. If `configured` is occupied by a live listener,
    claims a pid-suffixed sibling (`{stem}-{pid}{suffix}`) through the same
    probe/unlink logic rather than binding it blind — a prior producer under a
    recycled pid may have left an orphan there too.
    """
    if not force_suffix:
        state = _probe_socket_path(configured)
        if state is _PathState.RECLAIMABLE:
            configured.unlink(missing_ok=True)
        if state is not _PathState.LIVE:
            return configured

    suffixed = configured.with_name(f"{configured.stem}-{os.getpid()}{configured.suffix}")
    state = _probe_socket_path(suffixed)
    if state is _PathState.RECLAIMABLE:
        suffixed.unlink(missing_ok=True)
    elif state is _PathState.LIVE:
        # A distinct live process cannot be listening under our own pid.
        raise RuntimeError(
            f"UnixSocketTransport: pid-suffixed path {suffixed} is claimed by a live "
            "listener, which cannot happen for a distinct live process"
        )
    return suffixed


_OTEL_EVENT_TYPES = frozenset(
    {
        "evaluate",
        "route",
        "retry_exhausted",
        "cycle_detected",
        "stall_detected",
        "handoff_detected",
        "handoff_spawned",
        "action_output",
    }
)


class OTelTransport:
    """Map ll loop executions to OpenTelemetry traces and spans, exporting via OTLP.

    Span hierarchy: loop = trace root, state = child span, action = grandchild.
    Span events are added for evaluate, route, retry_exhausted, handoff_detected,
    handoff_spawned, and action_output on the innermost open span.

    Requires ``opentelemetry-sdk`` and ``opentelemetry-exporter-otlp-grpc``.
    Install with: ``pip install 'little-loops[otel]'``

    Sub-loop events (``depth > 0``) are no-ops with a single warning per session.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4317",
        service_name: str = "little-loops",
        *,
        _tracer_provider: Any | None = None,
    ) -> None:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            raise RuntimeError(
                "OTelTransport requires the 'opentelemetry-sdk' and "
                "'opentelemetry-exporter-otlp-grpc' packages. "
                "Install with: pip install 'little-loops[otel]'"
            ) from exc

        if _tracer_provider is not None:
            self._provider = _tracer_provider
        else:
            resource = Resource.create({"service.name": service_name})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            self._provider = provider

        self._tracer = self._provider.get_tracer("little-loops")
        self._loop_span: Any | None = None
        self._state_span: Any | None = None
        self._action_span: Any | None = None
        self._subloop_warned = False

    def send(self, event: dict[str, Any]) -> None:
        depth = event.get("depth", 0)
        if isinstance(depth, int) and depth > 0:
            if not self._subloop_warned:
                logger.warning(
                    "OTelTransport: sub-loop events (depth > 0) are not supported; "
                    "nested-trace support is deferred. Event type: %r",
                    event.get("event"),
                )
                self._subloop_warned = True
            return

        event_type = event.get("event", "")
        if event_type == "loop_start":
            self._handle_loop_start(event)
        elif event_type == "loop_resume":
            self._handle_loop_resume(event)
        elif event_type == "state_enter":
            self._handle_state_enter(event)
        elif event_type == "action_start":
            self._handle_action_start(event)
        elif event_type == "action_complete":
            self._handle_action_complete()
        elif event_type == "loop_complete":
            self._handle_loop_complete(event)
        elif event_type in _OTEL_EVENT_TYPES:
            self._add_span_event(event_type, event)

    def close(self) -> None:
        self._provider.force_flush()
        self._provider.shutdown()

    # ------------------------------------------------------------------
    # Internal span machine
    # ------------------------------------------------------------------

    def _handle_loop_start(self, event: dict[str, Any]) -> None:
        loop_name = str(event.get("loop_name", "ll-loop"))
        self._loop_span = self._tracer.start_span(loop_name)

    def _handle_loop_resume(self, event: dict[str, Any]) -> None:
        self._close_state_and_action()
        if self._loop_span is not None:
            self._loop_span.end()
        loop_name = str(event.get("loop_name", "ll-loop"))
        self._loop_span = self._tracer.start_span(loop_name)

    def _handle_state_enter(self, event: dict[str, Any]) -> None:
        self._close_state_and_action()
        if self._loop_span is None:
            logger.warning(
                "OTelTransport: state_enter received without a prior loop_start; skipping span"
            )
            return
        from opentelemetry import trace

        state_name = str(event.get("state", "unknown-state"))
        ctx = trace.set_span_in_context(self._loop_span)
        self._state_span = self._tracer.start_span(state_name, context=ctx)

    def _handle_action_start(self, event: dict[str, Any]) -> None:
        if self._state_span is None:
            logger.warning(
                "OTelTransport: action_start received without a prior state_enter; skipping span"
            )
            return
        from opentelemetry import trace

        action_name = str(event.get("action", "unknown-action"))
        ctx = trace.set_span_in_context(self._state_span)
        self._action_span = self._tracer.start_span(action_name, context=ctx)

    def _handle_action_complete(self) -> None:
        if self._action_span is not None:
            self._action_span.end()
            self._action_span = None

    def _handle_loop_complete(self, event: dict[str, Any]) -> None:
        from opentelemetry.trace import StatusCode

        from little_loops.fsm.persistence import map_final_status

        self._close_state_and_action()
        if self._loop_span is None:
            logger.warning(
                "OTelTransport: loop_complete received without a prior loop_start; skipping"
            )
            return
        terminated_by = str(event.get("terminated_by", ""))
        final_status = map_final_status(
            terminated_by, failure_terminal=bool(event.get("failure_terminal", False))
        )
        self._loop_span.set_attribute("ll.terminated_by", terminated_by)
        self._loop_span.set_attribute("ll.final_status", final_status)
        if final_status in ("failed", "timed_out"):
            self._loop_span.set_status(StatusCode.ERROR, final_status)
        elif final_status == "completed":
            self._loop_span.set_status(StatusCode.OK)
        else:
            self._loop_span.set_status(StatusCode.UNSET)
        self._loop_span.end()
        self._loop_span = None

    def _add_span_event(self, event_type: str, event: dict[str, Any]) -> None:
        span = self._action_span or self._state_span or self._loop_span
        if span is None:
            return
        attrs = {k: str(v) for k, v in event.items() if k != "event"}
        span.add_event(event_type, attributes=attrs)

    def _close_state_and_action(self) -> None:
        if self._action_span is not None:
            self._action_span.end()
            self._action_span = None
        if self._state_span is not None:
            self._state_span.end()
            self._state_span = None


class WebhookTransport:
    """POSTs batched FSM events to an HTTP endpoint.

    Events are enqueued non-blocking in ``send()`` and flushed by a daemon
    thread on a configurable interval.  Failed POSTs are retried with
    exponential backoff; after ``max_retries`` the batch is dropped with a
    warning rather than raising to the caller.

    Requires ``httpx``: ``pip install little-loops[webhooks]``.
    """

    def __init__(
        self,
        url: str,
        batch_ms: int = _WEBHOOK_BATCH_MS_DEFAULT,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> None:
        try:
            import httpx as _httpx
        except ImportError as exc:
            raise RuntimeError(
                "WebhookTransport requires httpx: pip install little-loops[webhooks]"
            ) from exc
        self._httpx = _httpx
        self._url = url
        self._batch_ms = batch_ms
        self._headers = dict(headers) if headers else {}
        self._max_retries = max_retries
        self._queue: Queue[dict[str, Any]] = Queue()
        self._shutdown = threading.Event()
        self._thread = threading.Thread(target=self._batch_loop, daemon=True, name="webhook-batch")
        self._thread.start()

    def send(self, event: dict[str, Any]) -> None:
        """Enqueue an event for the next batch flush (non-blocking)."""
        if not self._shutdown.is_set():
            self._queue.put(event)

    def close(self) -> None:
        """Signal shutdown, drain the queue with one final flush, and join the thread."""
        self._shutdown.set()
        self._thread.join(timeout=_WEBHOOK_CLOSE_TIMEOUT)

    def _batch_loop(self) -> None:
        while not self._shutdown.is_set():
            self._shutdown.wait(timeout=self._batch_ms / 1000.0)
            self._flush()
        # One final drain after shutdown signal
        self._flush()

    def _flush(self) -> None:
        events: list[dict[str, Any]] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                break
        if not events:
            return
        self._post_with_retry(events)

    def _post_with_retry(self, events: list[dict[str, Any]]) -> None:
        payload = json.dumps(events).encode()
        headers = {"Content-Type": "application/json", **self._headers}
        backoff = _WEBHOOK_RETRY_BASE_S
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._httpx.post(self._url, content=payload, headers=headers, timeout=10.0)
                if resp.status_code < 500:
                    return
            except Exception:
                pass
            if attempt < self._max_retries:
                time.sleep(backoff)
                backoff = min(backoff * 2, _WEBHOOK_RETRY_MAX_S)
        logger.warning(
            "WebhookTransport: giving up after %d retries posting to %r",
            self._max_retries,
            self._url,
        )


def _make_seed_callback() -> Callable[[_SocketClient], None]:
    """Return an on_connect callback that seeds a new client with current running loop state."""
    from little_loops.fsm.persistence import list_running_loops

    def _seed(client: _SocketClient) -> None:
        for state in list_running_loops(Path(".loops")):
            event = {"event": "state_change", **state.to_dict()}
            payload = (json.dumps(event) + "\n").encode("utf-8")
            try:
                client.queue.put_nowait(payload)
            except Full:
                pass

    return _seed


_TRANSPORT_REGISTRY: dict[str, str] = {
    "jsonl": "jsonl",
    "otel": "otel",
    "socket": "socket",
    "sqlite": "sqlite",
    "webhook": "webhook",
}


def wire_transports(
    bus: EventBus,
    config: EventsConfig,
    log_dir: Path | None = None,
) -> None:
    """Register transports named in `config.transports` on `bus`.

    Unknown transport names log a warning and are skipped (rather than raising)
    so that a typo in user config does not prevent the loop from starting. The
    one exception is the ``socket`` transport on platforms without ``AF_UNIX``,
    which raises a `RuntimeError` so the user is told why their config does
    not work — silently dropping the requested transport on Windows would be a
    more confusing failure mode.

    Args:
        bus: EventBus to register transports on
        config: EventsConfig holding the list of transport names to wire up
        log_dir: Directory under which built-in transports place their log files.
            Defaults to ``.ll`` under the current working directory.
    """
    base = log_dir if log_dir is not None else Path(".ll")
    for name in config.transports:
        if name not in _TRANSPORT_REGISTRY:
            logger.warning("Unknown transport %r; skipping", name)
            continue
        if name == "jsonl":
            bus.add_transport(JsonlTransport(base / "events.jsonl"))
        elif name == "otel":
            bus.add_transport(
                OTelTransport(
                    endpoint=config.otel.endpoint,
                    service_name=config.otel.service_name,
                )
            )
        elif name == "socket":
            if not hasattr(socket, "AF_UNIX"):
                raise RuntimeError(
                    "UnixSocketTransport requires AF_UNIX, which is not available on this "
                    'platform (e.g. Windows). Remove "socket" from events.transports or '
                    'use a different transport such as "jsonl".'
                )
            resolved = _resolve_socket_path(config.socket.path, base)
            bus.add_transport(
                UnixSocketTransport(
                    resolved,
                    config.socket.max_clients,
                    on_connect=_make_seed_callback(),
                )
            )
        elif name == "sqlite":
            from little_loops.session_store import SQLiteTransport

            bus.add_transport(SQLiteTransport(base / "history.db"))
        elif name == "webhook":
            if config.webhook.url is None:
                logger.warning("WebhookTransport: events.webhook.url is None; skipping")
                continue
            bus.add_transport(
                WebhookTransport(
                    url=config.webhook.url,
                    batch_ms=config.webhook.batch_ms,
                    headers=config.webhook.headers,
                    max_retries=3,
                )
            )


def _resolve_socket_path(configured: str, base: Path) -> Path:
    """Resolve a configured socket path against the per-call log_dir.

    The default config value is ``.ll/events.sock``. When `wire_transports` is
    given a custom ``log_dir`` (e.g. a tmp dir in tests), the socket should land
    inside that directory rather than literally at ``.ll/events.sock`` on disk.
    Mirroring the JsonlTransport behaviour: strip the ``.ll/`` prefix and treat
    the remainder as relative to ``base``. Absolute paths are honored as-is.
    """
    p = Path(configured)
    if p.is_absolute():
        return p
    if p.parts and p.parts[0] == ".ll":
        return base.joinpath(*p.parts[1:])
    return base / p
