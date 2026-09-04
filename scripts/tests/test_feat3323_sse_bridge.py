"""Tests for FEAT-3323: the out-of-process SSE bridge over UnixSocketTransport.

Drafted ahead of implementation (TDD, `tdd_mode: true`) per the issue's fully
enumerated `## Tests` section. `SseBridge` / `serve_sse_bridge` /
`BridgeEventsConfig` do not exist yet, so this module skips itself entirely
(rather than failing collection for the whole suite) until they land — remove
the `pytestmark` line once `little_loops.transport.SseBridge` is importable.

Two conventions borrowed from `tests.test_transport` (the `LocalBridgeTransport`
precedent this bridge mirrors, per the issue's Program Design):
  - `short_tmp_path` for any AF_UNIX-bound fixture (macOS tmp paths blow the
    104-char `sun_path` limit).
  - Raw-socket HTTP/SSE helpers (`_sse_connect`, `_read_sse_headers`,
    `_read_sse_frame`, `_lb_http_request`) since there is no SSE client lib in
    this codebase's dependency set.

Two producers in one test process necessarily share one real `os.getpid()`,
so "distinct producer_pid values" is exercised by patching
`little_loops.transport.os.getpid` around each producer's `send()` call
rather than by spawning real OS processes — the two producers are otherwise
completely real `UnixSocketTransport` instances bound in the same directory
(exercising the actual BUG-3324 probe-and-claim path).
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

import pytest

from little_loops.fsm.persistence import RUNNING_DIR
from little_loops.logger import Logger
from little_loops.transport import _CLIENT_QUEUE_MAXSIZE, UnixSocketTransport, _SocketClient
from tests.test_transport import (
    _client_count,
    _lb_http_request,
    _read_sse_frame,
    _read_sse_headers,
    _sse_connect,
    _wait_until,
)


@pytest.fixture
def short_tmp_path() -> Iterator[Path]:
    """Tmp dir with a short absolute path.

    Duplicated from tests.test_transport rather than imported: a pytest
    fixture imported into another test module and then used as a parameter
    name there trips ruff's F811 (looks like a redefinition), and this repo
    has no existing precedent for cross-module fixture re-export. See
    test_transport.py's copy for the AF_UNIX 104-char `sun_path` rationale.
    """
    d = Path(tempfile.mkdtemp(prefix="ll-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


try:
    from little_loops.config.features import EventsConfig
    from little_loops.transport import SseBridge, serve_sse_bridge  # noqa: F401

    _HAS_SSE_BRIDGE = True
except ImportError:
    _HAS_SSE_BRIDGE = False

try:
    from little_loops.cli.artifact.serve import cmd_serve  # noqa: F401

    _HAS_SERVE_CLI = True
except ImportError:
    _HAS_SERVE_CLI = False

pytestmark = pytest.mark.skipif(
    not _HAS_SSE_BRIDGE,
    reason="FEAT-3323: SseBridge/serve_sse_bridge/BridgeEventsConfig not implemented yet",
)

# NOTE: the producer_pid stamp itself (UnixSocketTransport.send()) needs no
# SseBridge and is tested in
# test_transport.py::TestUnixSocketTransport::test_send_stamps_producer_pid_on_a_copy_not_the_callers_dict
# instead of here, so it isn't caught by the module-wide skip above and
# genuinely runs red until that stamp lands.


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_config(**bridge_overrides: object) -> EventsConfig:
    """An EventsConfig with events.bridge overridden for a fast, isolated test."""
    config = EventsConfig()
    config.transports = ["socket"]
    for key, value in bridge_overrides.items():
        setattr(config.bridge, key, value)
    return config


def _bridge_port(bridge: SseBridge) -> int:
    """The real bound port, parsed from the public `.url` contract."""
    return int(urlparse(bridge.url).netloc.split(":")[1])


def _bridge_token(bridge: SseBridge) -> str:
    """The per-start token, parsed from the public `.url` contract."""
    return urlparse(bridge.url).path.strip("/").split("/")[0]


def _bridge_client_count(bridge: SseBridge) -> int:
    """SSE clients currently registered, mirroring `_lb_client_count` for LocalBridgeTransport.

    Assumes SseBridge mirrors LocalBridgeTransport's `_clients` / `_clients_lock`
    shape per the issue's Program Design ("mirroring LocalBridgeTransport's
    shape ... so tests get a handle"). Adjust the attribute names here if the
    real implementation names them differently.
    """
    with bridge._clients_lock:
        return len(bridge._clients)


def _write_loop_state_file(
    loops_dir: Path,
    name: str,
    *,
    pid: int | None = None,
    status: str = "completed",
    current_state: str = "done",
) -> Path:
    """A minimal `.state.json` fixture that list_running_loops() will pick up.

    `status="completed"` (never "running") so `_reconcile_stale_running` never
    touches the fixture — matching the issue's own "Seed fixtures must not
    trip reconciliation" note.
    """
    running_dir = loops_dir / RUNNING_DIR
    running_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    data: dict[str, object] = {
        "loop_name": name,
        "current_state": current_state,
        "iteration": 1,
        "captured": {},
        "prev_result": None,
        "last_result": None,
        "started_at": now,
        "updated_at": now,
        "status": status,
        "accumulated_ms": 0,
    }
    if pid is not None:
        data["pid"] = pid
    path = running_dir / f"{name}.state.json"
    path.write_text(json.dumps(data))
    return path


def _make_producer(
    base: Path,
    max_clients: int = 4,
    on_connect: Callable[[_SocketClient], None] | None = None,
) -> UnixSocketTransport:
    """A producer bound where SseBridge(base=...) will glob for it."""
    return UnixSocketTransport(base / "events.sock", max_clients=max_clients, on_connect=on_connect)


def _seed_state_change_on_connect(client: _SocketClient) -> None:
    """An `on_connect` that mimics `_make_seed_callback`'s `_seed` with one fixed frame.

    The real callback reads the CWD-relative `.loops/.running/`; this one
    enqueues a `state_change` line directly so the test controls the payload
    without touching the repo's own state dir.
    """
    event = {"event": "state_change", "loop_name": "seeded-loop", "status": "running", "pid": 99}
    client.queue.put_nowait((json.dumps(event) + "\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# Fan-in
# ---------------------------------------------------------------------------


class TestSseBridgeFanIn:
    def test_two_producers_reach_one_client_with_distinct_producer_pid(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """Events from two producer sockets both reach one SSE client, attributed correctly."""
        producer_a = _make_producer(short_tmp_path)
        producer_b = _make_producer(short_tmp_path)  # BUG-3324: lands on events-{pid}.sock
        assert producer_a._path != producer_b._path
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                leftover = _read_sse_headers(sock)
                # timeout=5.0 (default is 2.0): the fan-in thread must connect
                # to *two* producer sockets via real syscalls before this
                # condition holds; under heavy parallel-suite CPU contention
                # the default budget is occasionally too tight (matches the
                # timeout=3.0 headroom other fan-in tests in this file use).
                _wait_until(
                    lambda: _client_count(producer_a) == 1 and _client_count(producer_b) == 1,
                    timeout=5.0,
                )

                with mock.patch("little_loops.transport.os.getpid", return_value=1111):
                    producer_a.send({"event": "from-a"})
                with mock.patch("little_loops.transport.os.getpid", return_value=2222):
                    producer_b.send({"event": "from-b"})

                seen_pids = set()
                for _ in range(2):
                    # timeout=15.0 (default is 5.0): each event crosses five
                    # thread hops (producer client_loop -> bridge reader ->
                    # relay -> SSE write loop -> this socket) before this test
                    # ever sees a byte; under heavy parallel-suite CPU
                    # contention the default budget is occasionally too tight.
                    text, leftover = _read_sse_frame(sock, leftover, timeout=15.0)
                    seen_pids.add(json.loads(text)["producer_pid"])
                assert seen_pids == {1111, 2222}
            finally:
                sock.close()
        finally:
            bridge.close()
            producer_a.close()
            producer_b.close()

    def test_late_producer_is_picked_up_by_rescan(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """A producer socket created after the bridge is already serving still reaches a client."""
        bridge = SseBridge(
            _make_config(rescan_s=0.05), port=0, base=short_tmp_path, loops_dir=tmp_path
        )
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                leftover = _read_sse_headers(sock)

                producer = _make_producer(short_tmp_path)
                try:
                    _wait_until(lambda: _client_count(producer) == 1, timeout=3.0)
                    producer.send({"event": "late-producer"})
                    text, leftover = _read_sse_frame(sock, leftover)
                    assert json.loads(text)["event"] == "late-producer"
                finally:
                    producer.close()
            finally:
                sock.close()
        finally:
            bridge.close()

    def test_rescan_does_not_reconnect_an_already_connected_producer(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """A rescan opens no extra connection to a producer the bridge already holds."""
        producer = _make_producer(short_tmp_path)
        bridge = SseBridge(
            _make_config(rescan_s=0.05), port=0, base=short_tmp_path, loops_dir=tmp_path
        )
        try:
            _wait_until(lambda: _client_count(producer) == 1)
            time.sleep(0.3)  # several rescan_s intervals
            assert _client_count(producer) == 1
        finally:
            bridge.close()
            producer.close()

    def test_stale_socket_file_is_skipped_and_never_unlinked(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """A dead (bound-then-closed) socket file is skipped, not connected to or deleted."""
        stale = short_tmp_path / "events.sock"
        dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dead.bind(str(stale))
        dead.close()  # bound but never listen()ing: connect() on it fails ECONNREFUSED
        assert stale.exists()

        bridge = SseBridge(
            _make_config(rescan_s=0.05), port=0, base=short_tmp_path, loops_dir=tmp_path
        )
        try:
            time.sleep(0.3)
            assert stale.exists(), "the bridge must never unlink a stale producer socket file"
        finally:
            bridge.close()

    def test_producer_eof_then_reconnect_on_next_rescan(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """Producer EOF drops the reader; a fresh producer at the same path reconnects later."""
        producer = _make_producer(short_tmp_path)
        path = producer._path
        bridge = SseBridge(
            _make_config(rescan_s=0.05), port=0, base=short_tmp_path, loops_dir=tmp_path
        )
        try:
            _wait_until(lambda: _client_count(producer) == 1)
            producer.close()  # EOF from the bridge's perspective

            new_producer = UnixSocketTransport(path, max_clients=4)
            try:
                _wait_until(lambda: _client_count(new_producer) == 1, timeout=3.0)
            finally:
                new_producer.close()
        finally:
            bridge.close()

    def test_producer_at_max_clients_backs_off_sub_linearly(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """A producer at max_clients rejects the bridge's probe; rejections grow sub-linearly."""
        producer = UnixSocketTransport(short_tmp_path / "events.sock", max_clients=1)
        holder = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        holder.connect(str(producer._path))
        _wait_until(lambda: _client_count(producer) == 1)

        bridge = SseBridge(
            _make_config(rescan_s=0.05), port=0, base=short_tmp_path, loops_dir=tmp_path
        )
        try:
            time.sleep(0.5)
            first_window_rejections = producer.get_stats()["client_rejections"]
            time.sleep(1.0)
            second_window_rejections = (
                producer.get_stats()["client_rejections"] - first_window_rejections
            )
            # Sub-linear: without backoff a 0.05s rescan over ~1s would retry ~20x;
            # backoff should keep the second window well under that.
            assert second_window_rejections < 10
        finally:
            bridge.close()
            holder.close()
            producer.close()

    def test_socket_side_state_change_is_not_relayed(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """The producer's socket-connect seed (`state_change`) never reaches an SSE client.

        The producer is built with an `on_connect` seed (as `wire_transports`
        does via `_make_seed_callback`); without one this test is vacuous
        because no `state_change` line is ever sent for the bridge to filter.
        """
        producer = _make_producer(short_tmp_path, on_connect=_seed_state_change_on_connect)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                leftover = _read_sse_headers(sock)
                _wait_until(lambda: _client_count(producer) == 1)
                # The bridge's connect to `producer` just triggered its on_connect
                # seed -> a state_change line on that socket. It must be filtered,
                # so the first thing the SSE client sees is this live event (the
                # seed line was enqueued on the producer side before send() ran,
                # so ordering on the wire is seed-then-live).
                producer.send({"event": "not-a-seed"})
                text, leftover = _read_sse_frame(sock, leftover)
                assert json.loads(text)["event"] == "not-a-seed"
            finally:
                sock.close()
        finally:
            bridge.close()
            producer.close()


# ---------------------------------------------------------------------------
# Seeding (bridge-owned, on every SSE connect)
# ---------------------------------------------------------------------------


class TestSseBridgeSeeding:
    def test_sse_connect_receives_bridge_built_seed_before_live_traffic(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """A connect with a state file present gets a state_change seed frame first."""
        _write_loop_state_file(tmp_path, "my-loop", pid=4242)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                leftover = _read_sse_headers(sock)
                text, leftover = _read_sse_frame(sock, leftover)
                seed = json.loads(text)
                assert seed["event"] == "state_change"
                assert seed["producer_pid"] == 4242
                assert seed["pid"] == 4242
            finally:
                sock.close()
        finally:
            bridge.close()

    def test_seed_frame_omits_producer_pid_key_when_state_has_no_pid(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """A state file recording no pid yields a seed frame with no producer_pid key at all."""
        _write_loop_state_file(tmp_path, "no-pid-loop", pid=None)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                leftover = _read_sse_headers(sock)
                text, leftover = _read_sse_frame(sock, leftover)
                seed = json.loads(text)
                assert "producer_pid" not in seed
                assert "pid" not in seed
            finally:
                sock.close()
        finally:
            bridge.close()

    def test_reconnect_receives_the_seed_again(self, short_tmp_path: Path, tmp_path: Path) -> None:
        """Seeding is per-connect: a second connect (a reconnect) gets the same seed again."""
        _write_loop_state_file(tmp_path, "my-loop", pid=4242)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            for _ in range(2):
                sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
                try:
                    leftover = _read_sse_headers(sock)
                    text, _ = _read_sse_frame(sock, leftover)
                    assert json.loads(text)["event"] == "state_change"
                finally:
                    sock.close()
        finally:
            bridge.close()

    def test_event_emitted_during_seed_write_arrives_after_seed_not_lost(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """Register -> seed -> drain order: a live event during seeding is queued, not dropped.

        Drives the race by patching `list_running_loops` (as imported into
        `little_loops.transport`) to emit a producer event mid-call, proving the
        client's queue was registered before the seed snapshot was taken.

        Depends on `transport.py` importing `list_running_loops` at module
        level (the issue's § Seeding says so; a module-level import was probed
        against the package init, `fsm.persistence`, `cli.loop`, and
        `cli.artifact` with no cycle). `_make_seed_callback`'s lazy import is
        the pattern NOT to copy here, or this patch target silently misses.
        """
        _write_loop_state_file(tmp_path, "my-loop", pid=4242)
        producer = _make_producer(short_tmp_path)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            _wait_until(lambda: _client_count(producer) == 1)
            import little_loops.transport as transport_mod

            real_list_running_loops = transport_mod.list_running_loops

            def racy_list_running_loops(loops_dir: Path | None = None) -> object:
                result = real_list_running_loops(loops_dir)
                producer.send({"event": "mid-seed-race"})
                time.sleep(0.05)  # give the relay thread a chance to enqueue it
                return result

            with mock.patch.object(
                transport_mod, "list_running_loops", side_effect=racy_list_running_loops
            ):
                sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
                try:
                    leftover = _read_sse_headers(sock)
                    seed_text, leftover = _read_sse_frame(sock, leftover)
                    assert json.loads(seed_text)["event"] == "state_change"
                    live_text, leftover = _read_sse_frame(sock, leftover)
                    assert json.loads(live_text)["event"] == "mid-seed-race"
                finally:
                    sock.close()
        finally:
            bridge.close()
            producer.close()


# ---------------------------------------------------------------------------
# Server mechanics: page, routes, trailing slash
# ---------------------------------------------------------------------------


class TestSseBridgeServerMechanics:
    def test_no_trailing_slash_redirects_301(self, short_tmp_path: Path, tmp_path: Path) -> None:
        """GET /{token} (no slash) returns 301 to /{token}/."""
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            token = _bridge_token(bridge)
            status, _ = _lb_http_request(_bridge_port(bridge), "GET", f"/{token}")
            assert status == 301
        finally:
            bridge.close()

    def test_page_constant_uses_textcontent_only(self) -> None:
        """The page string never assigns innerHTML/outerHTML/insertAdjacentHTML.

        `_SSE_BRIDGE_PAGE_HTML` lives in `little_loops.transport` beside
        `_LOCAL_BRIDGE_DEFAULT_PAGE_HTML`, per the issue's § Page.
        """
        from little_loops.transport import _SSE_BRIDGE_PAGE_HTML  # type: ignore[attr-defined]

        assert "textContent" in _SSE_BRIDGE_PAGE_HTML
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML"):
            assert sink not in _SSE_BRIDGE_PAGE_HTML

    def test_script_payload_delivered_as_json_escaped_data(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """A <script> in a relayed event's payload survives the wire as plain JSON text.

        The browser-side XSS defense is the page rendering via textContent
        (covered by test_page_constant_uses_textcontent_only); this test only
        proves the wire format doesn't do something surprising to the payload
        (e.g. HTML-escaping or truncating it) on the way through the relay.
        """
        producer = _make_producer(short_tmp_path)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                leftover = _read_sse_headers(sock)
                _wait_until(lambda: _client_count(producer) == 1)
                producer.send({"event": "tool_output", "captured": "<script>alert(1)</script>"})
                text, leftover = _read_sse_frame(sock, leftover)
                payload = json.loads(text)
                assert payload["captured"] == "<script>alert(1)</script>"
            finally:
                sock.close()
        finally:
            bridge.close()
            producer.close()

    def test_routes_kwarg_mounts_extra_get_route(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """SseBridge(routes={...}) dispatches an extra GET route after Host/token checks."""

        def handler(req: object) -> None:  # Callable[[BaseHTTPRequestHandler], None]
            req.send_response(200)  # type: ignore[attr-defined]
            req.end_headers()  # type: ignore[attr-defined]
            req.wfile.write(b"extra-ok")  # type: ignore[attr-defined]

        bridge = SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path,
            routes={"extra": handler},
        )
        try:
            token = _bridge_token(bridge)
            status, body = _lb_http_request(_bridge_port(bridge), "GET", f"/{token}/extra")
            assert status == 200
            assert body == b"extra-ok"

            status, _ = _lb_http_request(_bridge_port(bridge), "GET", f"/{token}/other")
            assert status == 404
        finally:
            bridge.close()


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


class TestSseBridgeSecurity:
    def test_bad_host_header_returns_403(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            token = _bridge_token(bridge)
            status, _ = _lb_http_request(
                _bridge_port(bridge), "GET", f"/{token}/", host="evil.example.com"
            )
            assert status == 403
        finally:
            bridge.close()

    def test_wrong_or_missing_token_returns_404(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            status, _ = _lb_http_request(_bridge_port(bridge), "GET", "/not-the-real-token/")
            assert status == 404
        finally:
            bridge.close()

    def test_no_access_control_allow_origin_header(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                sock.settimeout(5.0)
                header_bytes = b""
                while b"\r\n\r\n" not in header_bytes:
                    header_bytes += sock.recv(4096)
                headers = header_bytes.decode("utf-8", errors="replace").lower()
                assert "access-control-allow-origin" not in headers
            finally:
                sock.close()
        finally:
            bridge.close()


# ---------------------------------------------------------------------------
# Lifecycle: cap, slow client, keepalive, retry, startup/shutdown
# ---------------------------------------------------------------------------


class TestSseBridgeLifecycle:
    def test_binds_loopback_only(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            assert urlparse(bridge.url).hostname == "127.0.0.1"
            sock = socket.create_connection(("127.0.0.1", _bridge_port(bridge)), timeout=5.0)
            sock.close()
        finally:
            bridge.close()

    def test_client_cap_returns_503_and_existing_clients_keep_receiving(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        producer = _make_producer(short_tmp_path)
        bridge = SseBridge(
            _make_config(max_clients=1), port=0, base=short_tmp_path, loops_dir=tmp_path
        )
        try:
            token = _bridge_token(bridge)
            port = _bridge_port(bridge)
            sock1 = _sse_connect(port, token)
            leftover1 = _read_sse_headers(sock1)
            _wait_until(lambda: _bridge_client_count(bridge) == 1)

            status, _ = _lb_http_request(port, "GET", f"/{token}/events")
            assert status == 503

            _wait_until(lambda: _client_count(producer) == 1)
            producer.send({"event": "still-here"})
            text, leftover1 = _read_sse_frame(sock1, leftover1)
            assert json.loads(text)["event"] == "still-here"
            sock1.close()
        finally:
            bridge.close()
            producer.close()

    def test_slow_client_is_dropped_without_disturbing_a_second_client(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        producer = _make_producer(short_tmp_path)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            token = _bridge_token(bridge)
            port = _bridge_port(bridge)
            slow = _sse_connect(port, token)
            _read_sse_headers(slow)
            healthy = _sse_connect(port, token)
            healthy_leftover = _read_sse_headers(healthy)
            _wait_until(lambda: _bridge_client_count(bridge) == 2)
            _wait_until(lambda: _client_count(producer) == 1)

            # Drain `healthy` continuously in the background so it stays healthy;
            # never drain `slow`. Payloads are padded so the total volume (~6MB)
            # exceeds the kernel socket buffer plus the 1024-slot queue — 2000
            # tiny events fit entirely in those buffers and never trip a drop.
            healthy_frames = 0
            stop_draining = threading.Event()

            def _drain() -> None:
                nonlocal healthy_frames, healthy_leftover
                while not stop_draining.is_set():
                    try:
                        _, healthy_leftover = _read_sse_frame(
                            healthy, healthy_leftover, timeout=0.5
                        )
                        healthy_frames += 1
                    except TimeoutError:
                        continue

            drainer = threading.Thread(target=_drain, daemon=True)
            drainer.start()
            padding = "x" * 1024
            # Paced in small batches rather than one tight 6000-iteration loop:
            # an unpaced burst is pure in-memory Queue.put_nowait() (tens of
            # microseconds each), which fills the *producer's own* per-client
            # queue (UnixSocketTransport._CLIENT_QUEUE_MAXSIZE, also 1024 —
            # the fan-in hop this issue's architecture adds ahead of the SSE
            # hop under test) faster than any real thread scheduling can drain
            # it, so most of the flood never reaches the bridge at all. A tiny
            # sleep between batches gives the reader/relay threads real
            # wall-clock time to keep the upstream hop draining, so the full
            # padded volume actually reaches the SSE clients and the *intended*
            # hop (the never-drained `slow` client's queue) is the one that
            # overflows.
            for batch_start in range(0, 6000, 200):
                for i in range(batch_start, batch_start + 200):
                    producer.send({"event": "spam", "i": i, "pad": padding})
                time.sleep(0.01)

            # Drop-newest on the slow client's bounded queue: the counter moves
            # and the queue never exceeds its bound.
            _wait_until(lambda: any(c.dropped_total > 0 for c in bridge._clients), timeout=10.0)
            assert all(c.queue.qsize() <= _CLIENT_QUEUE_MAXSIZE for c in bridge._clients)
            _wait_until(lambda: healthy_frames > 0, timeout=10.0)
            stop_draining.set()
            drainer.join(timeout=2.0)
            slow.close()
            healthy.close()
        finally:
            bridge.close()
            producer.close()

    def test_keepalive_and_retry_directive(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = SseBridge(
            _make_config(keepalive_s=0.2), port=0, base=short_tmp_path, loops_dir=tmp_path
        )
        try:
            sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
            try:
                buf = _read_sse_headers(sock)
                sock.settimeout(5.0)
                deadline = time.monotonic() + 3.0
                saw_retry = False
                saw_ping = False
                saw_id = False
                while time.monotonic() < deadline and not (saw_retry and saw_ping):
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    if b"retry: 2000" in buf:
                        saw_retry = True
                    if b": ping" in buf:
                        saw_ping = True
                    if b"\nid:" in buf or buf.startswith(b"id:"):
                        saw_id = True
                assert saw_retry, "expected `retry: 2000` once at stream open"
                assert saw_ping, "expected a keepalive comment frame within keepalive_s"
                assert not saw_id, "no `id:` line should ever be sent (no replay contract)"
            finally:
                sock.close()
        finally:
            bridge.close()

    def test_close_drains_producer_clients_ends_sse_stream_leaves_no_thread(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        producer = _make_producer(short_tmp_path)
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        sock = _sse_connect(_bridge_port(bridge), _bridge_token(bridge))
        _read_sse_headers(sock)
        _wait_until(lambda: _client_count(producer) == 1)
        _wait_until(lambda: _bridge_client_count(bridge) == 1)

        baseline_threads = threading.active_count()
        bridge.close()

        # The producer retires the slot on its next idle poll
        # (_CLIENT_QUEUE_POLL_TIMEOUT = 0.5s) via _peer_closed, not synchronously.
        _wait_until(lambda: _client_count(producer) == 0, timeout=3.0)
        sock.settimeout(2.0)
        assert sock.recv(4096) == b""  # stream ends
        _wait_until(lambda: threading.active_count() <= baseline_threads, timeout=15.0)
        sock.close()
        producer.close()

    def test_close_leaves_socket_dir_and_running_dir_untouched(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        _write_loop_state_file(tmp_path, "untouched-loop", pid=1)
        socket_dir_before = sorted(p.name for p in short_tmp_path.iterdir())
        running_dir_before = sorted(p.name for p in (tmp_path / RUNNING_DIR).iterdir())

        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        bridge.close()  # no SSE client ever connected, so no seed write should occur either

        socket_dir_after = sorted(p.name for p in short_tmp_path.iterdir())
        running_dir_after = sorted(p.name for p in (tmp_path / RUNNING_DIR).iterdir())
        assert socket_dir_before == socket_dir_after
        assert running_dir_before == running_dir_after


# ---------------------------------------------------------------------------
# CLI: serve_sse_bridge / cmd_serve
# ---------------------------------------------------------------------------


class TestServeSseBridgeCli:
    def test_serve_sse_bridge_binds_loopback_and_prints_url(
        self,
        short_tmp_path: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """serve_sse_bridge prints the printed URL and blocks until interrupted.

        TODO(FEAT-3323): once implemented, drive the real blocking call — e.g.
        run `serve_sse_bridge(config, port=0)` in a thread and stop it via
        whatever mechanism `SseBridge.close()`-on-KeyboardInterrupt actually
        uses internally (a private stop Event is the likely candidate, mirrored
        on `close()` per Program Design). This stub only pins the non-blocking
        half of the contract: `SseBridge` itself binds loopback and exposes the
        same URL shape `serve_sse_bridge` would print.
        """
        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            assert urlparse(bridge.url).hostname == "127.0.0.1"
        finally:
            bridge.close()


@pytest.mark.skipif(
    not _HAS_SERVE_CLI,
    reason="FEAT-3323: cli/artifact/serve.py (cmd_serve) not implemented yet",
)
class TestCmdServeCli:
    def test_port_in_use_prints_one_line_and_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """EADDRINUSE names the port and --port, with no traceback, exit code 1.

        `cmd_serve(args, logger)` follows the `cli/artifact` convention
        (`cmd_dashboard(args, logger)`, dispatched from `main_artifact()`).
        This stub assumes a `port: int | None` attribute on the Namespace,
        mirroring every other `cli/artifact/*` subcommand.
        """
        thrower = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        thrower.bind(("127.0.0.1", 0))
        thrower.listen(1)  # bound-but-not-listening is ambiguous under SO_REUSEADDR
        port = thrower.getsockname()[1]
        try:
            args = argparse.Namespace(port=port)
            exit_code = cmd_serve(args, Logger(use_color=False))  # type: ignore[name-defined]
            assert exit_code == 1
        finally:
            thrower.close()

        captured = capsys.readouterr()
        text = captured.out + captured.err
        assert str(port) in text, "message must name the port"
        assert "--port" in text, "message must name the --port override"
        assert "Traceback" not in text
        lines = [ln for ln in text.splitlines() if ln.strip()]
        assert len(lines) == 1, f"expected exactly one line, got {lines!r}"

    def test_no_producer_socket_prints_plain_message_and_keeps_serving(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With no producer socket present, the CLI says so rather than presenting success.

        TODO(FEAT-3323): needs cmd_serve's real signature plus a way to stop the
        blocking serve loop after one assertion pass (e.g. inject a pre-set stop
        Event, or run in a thread and call bridge.close()).
        """
        pytest.skip("drafted; needs cmd_serve's real call shape to drive non-interactively")
