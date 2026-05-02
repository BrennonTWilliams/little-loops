"""Tests for the Transport Protocol, JsonlTransport, and wire_transports()."""

from __future__ import annotations

import json
import logging
import shutil
import socket
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from little_loops.config.features import EventsConfig, SocketEventsConfig
from little_loops.events import EventBus
from little_loops.transport import (
    JsonlTransport,
    Transport,
    UnixSocketTransport,
    wire_transports,
)


@pytest.fixture
def short_tmp_path() -> Iterator[Path]:
    """Tmp dir with a short absolute path.

    The default ``tmp_path`` fixture lives under ``/private/var/folders/...`` on
    macOS, blowing past the AF_UNIX 104-char `sun_path` limit when we append a
    socket name. Use this fixture for any test that binds an AF_UNIX socket.
    """
    d = Path(tempfile.mkdtemp(prefix="ll-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _read_lines(conn: socket.socket, expected: int, timeout: float = 5.0) -> list[str]:
    """Read until ``expected`` newline-delimited messages have arrived or timeout."""
    conn.settimeout(timeout)
    deadline = time.monotonic() + timeout
    buf = b""
    lines: list[str] = []
    while len(lines) < expected and time.monotonic() < deadline:
        try:
            chunk = conn.recv(4096)
        except TimeoutError:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            lines.append(line.decode("utf-8"))
            if len(lines) >= expected:
                break
    return lines


class TestTransportProtocol:
    """Tests for the Transport Protocol."""

    def test_protocol_satisfied_by_class_with_send_and_close(self) -> None:
        """A class with send and close satisfies the Protocol via runtime_checkable."""

        class MyTransport:
            def send(self, event: dict[str, Any]) -> None:
                pass

            def close(self) -> None:
                pass

        t = MyTransport()
        assert isinstance(t, Transport)

    def test_jsonl_transport_satisfies_protocol(self, tmp_path: Path) -> None:
        """JsonlTransport instances satisfy the Transport Protocol."""
        t = JsonlTransport(tmp_path / "out.jsonl")
        assert isinstance(t, Transport)

    def test_protocol_rejects_class_without_send(self) -> None:
        """A class missing send is not a Transport."""

        class NotTransport:
            def close(self) -> None:
                pass

        assert not isinstance(NotTransport(), Transport)


class TestJsonlTransport:
    """Tests for JsonlTransport implementation."""

    def test_send_appends_jsonl(self, tmp_path: Path) -> None:
        """send() appends each event as a JSON line."""
        path = tmp_path / "events.jsonl"
        t = JsonlTransport(path)
        t.send({"event": "first", "ts": "t1", "x": 1})
        t.send({"event": "second", "ts": "t2", "x": 2})

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"

    def test_init_creates_parent_directory(self, tmp_path: Path) -> None:
        """JsonlTransport.__init__ creates parent directories if missing."""
        path = tmp_path / "nested" / "deep" / "events.jsonl"
        JsonlTransport(path)
        assert path.parent.exists()

    def test_close_is_noop(self, tmp_path: Path) -> None:
        """close() is a no-op and may be called repeatedly."""
        t = JsonlTransport(tmp_path / "events.jsonl")
        t.close()
        t.close()  # Idempotent


class TestEventBusTransports:
    """Tests for EventBus transport fan-out."""

    def test_add_transport_and_emit(self, tmp_path: Path) -> None:
        """Events emitted on the bus are dispatched to registered transports."""
        path = tmp_path / "events.jsonl"
        bus = EventBus()
        bus.add_transport(JsonlTransport(path))

        bus.emit({"event": "first", "ts": "t1"})
        bus.emit({"event": "second", "ts": "t2"})

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_multiple_transports_each_receive_event(self, tmp_path: Path) -> None:
        """All registered transports receive each emitted event."""
        path_a = tmp_path / "a.jsonl"
        path_b = tmp_path / "b.jsonl"
        bus = EventBus()
        bus.add_transport(JsonlTransport(path_a))
        bus.add_transport(JsonlTransport(path_b))

        bus.emit({"event": "x", "ts": "t"})

        assert path_a.read_text().strip()
        assert path_b.read_text().strip()

    def test_transport_exception_isolated(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """One transport's exception does not stop others or propagate."""
        captured: list[dict[str, Any]] = []

        class BadTransport:
            def send(self, event: dict[str, Any]) -> None:
                raise RuntimeError("boom")

            def close(self) -> None:
                pass

        class RecordingTransport:
            def send(self, event: dict[str, Any]) -> None:
                captured.append(event)

            def close(self) -> None:
                pass

        bus = EventBus()
        bus.add_transport(BadTransport())
        bus.add_transport(RecordingTransport())

        with caplog.at_level(logging.WARNING):
            bus.emit({"event": "test", "ts": "now"})

        # Second transport still received the event
        assert len(captured) == 1
        # And the exception was logged, not propagated
        assert any("transport" in record.message.lower() for record in caplog.records)

    def test_close_transports_calls_close_on_each(self) -> None:
        """close_transports() invokes close() on every registered transport."""
        closed: list[str] = []

        class CountingTransport:
            def __init__(self, name: str) -> None:
                self.name = name

            def send(self, event: dict[str, Any]) -> None:
                pass

            def close(self) -> None:
                closed.append(self.name)

        bus = EventBus()
        bus.add_transport(CountingTransport("a"))
        bus.add_transport(CountingTransport("b"))

        bus.close_transports()
        assert closed == ["a", "b"]


class TestWireTransports:
    """Tests for the wire_transports() registry helper."""

    def test_jsonl_registered_by_name(self, tmp_path: Path) -> None:
        """The jsonl transport is registered and wires up successfully."""
        bus = EventBus()
        config = EventsConfig(transports=["jsonl"])
        wire_transports(bus, config, log_dir=tmp_path)

        # After wiring, emitting should produce a file
        bus.emit({"event": "first", "ts": "t"})
        bus.close_transports()

        # JsonlTransport writes somewhere under tmp_path
        files = list(tmp_path.rglob("*.jsonl"))
        assert files, "expected JsonlTransport to write at least one file"

    def test_unknown_transport_warns_and_skips(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unknown transport names log a warning and are skipped."""
        bus = EventBus()
        config = EventsConfig(transports=["mystery"])

        with caplog.at_level(logging.WARNING):
            wire_transports(bus, config, log_dir=tmp_path)

        assert any("mystery" in record.message for record in caplog.records)

    def test_empty_transports_is_noop(self, tmp_path: Path) -> None:
        """Empty transports list does not register anything."""
        bus = EventBus()
        config = EventsConfig(transports=[])
        wire_transports(bus, config, log_dir=tmp_path)
        # No files produced
        bus.emit({"event": "x", "ts": "t"})
        assert not list(tmp_path.rglob("*.jsonl"))

    @pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX not available")
    def test_socket_registered_by_name(self, short_tmp_path: Path) -> None:
        """The socket transport is registered and wires up successfully."""
        bus = EventBus()
        config = EventsConfig(
            transports=["socket"],
            socket=SocketEventsConfig(path=str(short_tmp_path / "events.sock"), max_clients=4),
        )
        try:
            wire_transports(bus, config, log_dir=short_tmp_path)
            assert (short_tmp_path / "events.sock").exists()
        finally:
            bus.close_transports()

    @pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX not available")
    def test_socket_uses_socket_path_from_config(self, short_tmp_path: Path) -> None:
        """The socket transport binds at the configured path."""
        bus = EventBus()
        custom = short_tmp_path / "custom.sock"
        config = EventsConfig(
            transports=["socket"],
            socket=SocketEventsConfig(path=str(custom), max_clients=2),
        )
        try:
            wire_transports(bus, config, log_dir=short_tmp_path)
            assert custom.exists()
        finally:
            bus.close_transports()

    @pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX not available")
    def test_socket_and_jsonl_both_registered(self, short_tmp_path: Path) -> None:
        """jsonl and socket transports can be wired together on one bus."""
        bus = EventBus()
        config = EventsConfig(
            transports=["jsonl", "socket"],
            socket=SocketEventsConfig(path=str(short_tmp_path / "events.sock"), max_clients=2),
        )
        try:
            wire_transports(bus, config, log_dir=short_tmp_path)
            bus.emit({"event": "x", "ts": "t"})
            assert (short_tmp_path / "events.jsonl").exists()
            assert (short_tmp_path / "events.sock").exists()
        finally:
            bus.close_transports()

    def test_socket_raises_on_non_af_unix_platform(self, tmp_path: Path) -> None:
        """Without AF_UNIX, wire_transports raises a clear RuntimeError."""
        bus = EventBus()
        config = EventsConfig(
            transports=["socket"],
            socket=SocketEventsConfig(path=str(tmp_path / "x.sock"), max_clients=2),
        )

        with mock.patch("little_loops.transport.hasattr") as fake_hasattr:

            def stub(obj: Any, name: str) -> bool:
                if name == "AF_UNIX":
                    return False
                return hasattr(obj, name)

            fake_hasattr.side_effect = stub
            with pytest.raises(RuntimeError, match="AF_UNIX"):
                wire_transports(bus, config, log_dir=tmp_path)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX not available")
class TestUnixSocketTransport:
    """Tests for UnixSocketTransport."""

    def test_satisfies_protocol(self, short_tmp_path: Path) -> None:
        """UnixSocketTransport instances satisfy the Transport Protocol."""
        t = UnixSocketTransport(short_tmp_path / "events.sock", max_clients=2)
        try:
            assert isinstance(t, Transport)
        finally:
            t.close()

    def test_init_binds_and_creates_socket_file(self, short_tmp_path: Path) -> None:
        """__init__ creates the socket file at the configured path."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=2)
        try:
            assert path.exists()
        finally:
            t.close()

    def test_init_unlinks_stale_socket_file(self, short_tmp_path: Path) -> None:
        """A stale socket file at the path is unlinked before bind()."""
        path = short_tmp_path / "events.sock"
        path.write_text("stale")
        t = UnixSocketTransport(path, max_clients=2)
        try:
            assert path.exists()
        finally:
            t.close()

    def test_close_unlinks_socket_file(self, short_tmp_path: Path) -> None:
        """close() unlinks the socket file."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=2)
        t.close()
        assert not path.exists()

    def test_socket_file_permissions_owner_only(self, short_tmp_path: Path) -> None:
        """The socket file is chmod 0600 immediately after bind()."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=2)
        try:
            mode = path.stat().st_mode & 0o777
            assert mode == 0o600
        finally:
            t.close()

    def test_end_to_end_send_and_receive(self, short_tmp_path: Path) -> None:
        """A connected client receives newline-delimited JSON for each event."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=2)
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(str(path))
            time.sleep(0.2)

            t.send({"event": "first", "ts": "t1"})
            t.send({"event": "second", "ts": "t2"})

            lines = _read_lines(client, expected=2)
            assert len(lines) == 2
            assert json.loads(lines[0])["event"] == "first"
            assert json.loads(lines[1])["event"] == "second"
            client.close()
        finally:
            t.close()

    def test_multi_client_each_receives_every_event(self, short_tmp_path: Path) -> None:
        """Two simultaneous clients each receive every event."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=4)
        try:
            c1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c1.connect(str(path))
            c2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c2.connect(str(path))
            time.sleep(0.3)

            t.send({"event": "x"})
            t.send({"event": "y"})

            for c in (c1, c2):
                lines = _read_lines(c, expected=2)
                assert len(lines) == 2
                assert json.loads(lines[0])["event"] == "x"
                assert json.loads(lines[1])["event"] == "y"
                c.close()
        finally:
            t.close()

    def test_client_disconnect_does_not_affect_other_clients(self, short_tmp_path: Path) -> None:
        """Disconnecting one client leaves other clients healthy."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=4)
        try:
            c1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c1.connect(str(path))
            c2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c2.connect(str(path))
            time.sleep(0.3)

            c1.close()
            time.sleep(0.2)

            t.send({"event": "after-disconnect"})

            lines = _read_lines(c2, expected=1)
            assert len(lines) == 1
            assert json.loads(lines[0])["event"] == "after-disconnect"
            c2.close()
        finally:
            t.close()

    def test_max_clients_cap_rejects_extra_connection(self, short_tmp_path: Path) -> None:
        """Connections beyond max_clients are accepted-and-closed."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=1)
        try:
            c1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c1.connect(str(path))
            time.sleep(0.2)

            c2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c2.connect(str(path))
            time.sleep(0.3)

            t.send({"event": "only-c1"})
            lines = _read_lines(c1, expected=1)
            assert len(lines) == 1

            c2.settimeout(1.5)
            try:
                rejected = c2.recv(4096)
            except TimeoutError:
                rejected = b""
            assert rejected in (b"",), "extra client should be closed by transport"
            c1.close()
            c2.close()
        finally:
            t.close()

    def test_send_drops_when_queue_full_logs_warning(
        self, short_tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """send() drops events for a slow client and logs a warning, never blocking."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=2)
        try:
            c1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c1.connect(str(path))
            # Wait until the accept loop has registered the client
            for _ in range(50):
                with t._clients_lock:
                    if t._clients:
                        break
                time.sleep(0.05)

            with t._clients_lock:
                snapshot = list(t._clients)
            assert snapshot, "expected one connected client"
            client = snapshot[0]

            # Block the client thread by stealing the queue: replace it with a
            # full Queue so that put_nowait() inside send() always raises Full.
            from queue import Queue

            full_q: Queue[bytes] = Queue(maxsize=1)
            full_q.put_nowait(b"placeholder\n")
            client.queue = full_q

            with caplog.at_level(logging.WARNING):
                t.send({"event": "spam", "i": 0})
                # Push more so the rate-limit-summary path is also exercised.
                for i in range(1, 20):
                    t.send({"event": "spam", "i": i})

            assert client.dropped_total >= 20
            assert any("slow client" in record.message.lower() for record in caplog.records)
            c1.close()
        finally:
            t.close()

    def test_close_joins_threads_and_unlinks_within_budget(self, short_tmp_path: Path) -> None:
        """close() returns within the 10s ceiling and removes the socket file."""
        path = short_tmp_path / "events.sock"
        t = UnixSocketTransport(path, max_clients=4)
        c1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c1.connect(str(path))
        c2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c2.connect(str(path))
        time.sleep(0.3)

        start = time.monotonic()
        t.close()
        elapsed = time.monotonic() - start

        assert elapsed < 10.0, f"close() exceeded 10s budget: {elapsed:.2f}s"
        assert not path.exists()
        assert not t._accept_thread.is_alive()
        for client in t._clients:
            assert client.thread is None or not client.thread.is_alive()
        c1.close()
        c2.close()
