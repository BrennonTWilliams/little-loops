"""Transport abstraction for the little-loops EventBus.

A `Transport` is an additive sink for events emitted by `EventBus`. The Protocol
is intentionally minimal — `send(event)` for delivery and `close()` for cleanup —
so that new sinks can be added without modifying `EventBus` itself.

Built-in implementations:
    JsonlTransport: appends each event as a JSON line to a file.
    UnixSocketTransport: streams newline-delimited JSON to AF_UNIX socket clients
        for sub-second-latency local consumers (TUIs, log tailers, dashboards).

Public exports:
    Transport: runtime-checkable Protocol that any sink must satisfy
    JsonlTransport: writes events to a JSONL file
    UnixSocketTransport: streams events over an AF_UNIX socket
    wire_transports: register transports listed in `EventsConfig` on an `EventBus`
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from pathlib import Path
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from little_loops.config.features import EventsConfig
    from little_loops.events import EventBus

logger = logging.getLogger(__name__)

_CLIENT_QUEUE_MAXSIZE = 1024
_DROP_LOG_INTERVAL_SEC = 5.0
_ACCEPT_THREAD_JOIN_TIMEOUT = 2.0
_CLIENT_THREAD_JOIN_TIMEOUT = 1.0
_CLOSE_TOTAL_TIMEOUT = 10.0
_ACCEPT_POLL_TIMEOUT = 1.0
_CLIENT_QUEUE_POLL_TIMEOUT = 0.5


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

    On construction, binds the socket at ``path`` (after unlinking any stale
    file), starts an accept thread, and accepts up to ``max_clients`` concurrent
    consumers. Each accepted client gets its own daemon thread and bounded
    outbound queue; ``send()`` enqueues the serialized event into every client
    queue without blocking. A full queue causes the newest event to be dropped
    (preserving causal order) and a rate-limited warning is logged.

    A misbehaving / disconnected client is removed from the pool without
    affecting other clients or the FSM thread.

    Not available on platforms without ``AF_UNIX`` (e.g. Windows). The platform
    check lives in :func:`wire_transports` so the user-facing error has clearer
    placement; constructing this class on a platform without ``AF_UNIX`` will
    raise an `OSError` from `socket.socket` directly.
    """

    def __init__(self, path: Path, max_clients: int = 8) -> None:
        if not hasattr(socket, "AF_UNIX"):
            raise RuntimeError(
                "UnixSocketTransport requires AF_UNIX, which is not available on this platform"
            )

        self._path = path
        self._max_clients = max_clients
        self._shutdown = threading.Event()
        self._clients: list[_SocketClient] = []
        self._clients_lock = threading.Lock()

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.unlink(missing_ok=True)

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._server.bind(str(self._path))
            self._path.chmod(0o600)
            self._server.listen(max_clients)
            self._server.settimeout(_ACCEPT_POLL_TIMEOUT)
        except Exception:
            self._server.close()
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
                    logger.warning(
                        "UnixSocketTransport: rejecting client; max_clients=%d reached",
                        self._max_clients,
                    )
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
                client.thread.start()

    def _client_loop(self, client: _SocketClient) -> None:
        try:
            while not self._shutdown.is_set():
                try:
                    payload = client.queue.get(timeout=_CLIENT_QUEUE_POLL_TIMEOUT)
                except Empty:
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

        self._path.unlink(missing_ok=True)


_TRANSPORT_REGISTRY: dict[str, str] = {"jsonl": "jsonl", "socket": "socket"}


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
        elif name == "socket":
            if not hasattr(socket, "AF_UNIX"):
                raise RuntimeError(
                    "UnixSocketTransport requires AF_UNIX, which is not available on this "
                    'platform (e.g. Windows). Remove "socket" from events.transports or '
                    'use a different transport such as "jsonl".'
                )
            resolved = _resolve_socket_path(config.socket.path, base)
            bus.add_transport(UnixSocketTransport(resolved, config.socket.max_clients))


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
