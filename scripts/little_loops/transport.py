"""Transport abstraction for the little-loops EventBus.

A `Transport` is an additive sink for events emitted by `EventBus`. The Protocol
is intentionally minimal — `send(event)` for delivery and `close()` for cleanup —
so that new sinks can be added without modifying `EventBus` itself.

Built-in implementations:
    JsonlTransport: appends each event as a JSON line to a file.
    UnixSocketTransport: streams newline-delimited JSON to AF_UNIX socket clients
        for sub-second-latency local consumers (TUIs, log tailers, dashboards).
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
    OTelTransport: exports loop traces via OTLP
    WebhookTransport: POSTs batched events to an HTTP endpoint
    wire_transports: register transports listed in `EventsConfig` on an `EventBus`
"""

from __future__ import annotations

import enum
import errno
import json
import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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
        payload = (json.dumps(event) + "\n").encode("utf-8")
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
