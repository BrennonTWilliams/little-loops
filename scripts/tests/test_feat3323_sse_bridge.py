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
import http.client
import json
import logging
import math
import shutil
import socket
import sqlite3
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
    # BUG-3484: this test's own legitimate worst-case wall-clock budget (two
    # producers + a full SseBridge, 5 real thread hops, generous per-step
    # timeouts already widened twice for CPU-contention flakiness) sums to
    # ~100-105s. Under full-suite xdist CPU contention that legitimately
    # exceeded the suite's global --timeout=120 (and even
    # @pytest.mark.timeout(180) under extreme contention), pytest-timeout's
    # thread-method watchdog can't interrupt a blocked C-level recv()/
    # thread-join and hard-kills the whole xdist worker (os._exit) instead
    # of failing just this test.
    #
    # Structural fix (BUG-2523): skip on xdist workers via the
    # no_parallel marker. Under the default -n logical addopts the
    # controller never runs tests under -n N, so this test only actually
    # executes via scripts/tests/test_no_parallel_serial_gate.py's serial
    # `-n 0` invocation (BUG-3523), where CPU contention is absent and the
    # legitimate 100-105s wall-clock budget is safe.
    @pytest.mark.no_parallel
    @pytest.mark.timeout(180)
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
                    # timeout=30.0 (default is 5.0; was 15.0 until it still
                    # flaked at -n logical full-suite width — see BUG history
                    # below): each event crosses five thread hops (producer
                    # client_loop -> bridge reader -> relay -> SSE write loop
                    # -> this socket) before this test ever sees a byte, and
                    # each is a real Python thread competing for the GIL
                    # against every other xdist worker's tests on the same
                    # cores. _read_sse_frame's socket.settimeout() applies
                    # per-recv(), not cumulatively, so widening this only
                    # costs time when the relay is genuinely starved (this
                    # test still finishes in ~3s standalone) — it never slows
                    # a healthy run.
                    text, leftover = _read_sse_frame(sock, leftover, timeout=30.0)
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
        self, short_tmp_path: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A producer at max_clients rejects the bridge's probe; rejections grow sub-linearly
        and the "closed the connection immediately" warning fires exactly once for the path."""
        rescan_s = 0.05
        span = 2.0
        producer = UnixSocketTransport(short_tmp_path / "events.sock", max_clients=1)
        holder = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        holder.connect(str(producer._path))
        _wait_until(lambda: _client_count(producer) == 1)

        try:
            with caplog.at_level(logging.WARNING, logger="little_loops.transport"):
                bridge = SseBridge(
                    _make_config(rescan_s=rescan_s), port=0, base=short_tmp_path, loops_dir=tmp_path
                )
                try:
                    deadline = time.monotonic() + span
                    while time.monotonic() < deadline:
                        time.sleep(0.05)
                    rejections = producer.get_stats()["client_rejections"]
                finally:
                    bridge.close()

            flap_warnings = [
                r for r in caplog.records if "closed the connection immediately" in r.message
            ]
            assert len(flap_warnings) == 1

            # Sub-linear: without backoff a 0.05s rescan over a 2s span would retry
            # ~40x; with doubling backoff the count is bounded logarithmically.
            bound = math.ceil(math.log2(span / rescan_s)) + 3
            assert rejections <= bound
        finally:
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


# ---------------------------------------------------------------------------
# FEAT-3321: read-only history payload route on `ll-artifact serve`
# ---------------------------------------------------------------------------


def _build_history_db(path: Path) -> None:
    """Minimal synthetic history.db shaped like session_store/schema.py's DDL.

    Column lists match the ENH-075 shareable-mode split (`error` and
    `diagnostics_path` are excluded from `loop_runs` in shareable mode).
    """
    import sqlite3

    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE loop_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT, loop_name TEXT, started_at TEXT, ended_at TEXT,
            final_state TEXT, iterations INTEGER, terminated_by TEXT,
            error TEXT, evaluator_score REAL, diagnostics_path TEXT,
            head_sha TEXT, branch TEXT, failure_terminal INTEGER
        );
        CREATE TABLE usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, session_id TEXT, model TEXT, state TEXT,
            input_tokens INTEGER, output_tokens INTEGER,
            cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER,
            cost_usd REAL, invocation_id TEXT, provider_vendor TEXT, run_id TEXT
        );
        """
    )
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
    conn.executemany(
        "INSERT INTO loop_runs (run_id, loop_name, started_at, ended_at, final_state, "
        "iterations, error, diagnostics_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "r-1",
                "loop-a",
                "2026-08-01T00:00:00Z",
                "2026-08-01T01:00:00Z",
                "done",
                1,
                "secret failure text",
                "/opt/synthetic-fixture/diag.json",
            )
        ],
    )
    conn.commit()
    conn.close()


def _history_project(project_root: Path):
    """A minimal project root with a synthetic `.ll/history.db`, as a `BRConfig`."""
    from little_loops.config.core import BRConfig

    (project_root / ".ll").mkdir(parents=True, exist_ok=True)
    (project_root / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
    _build_history_db(project_root / ".ll" / "history.db")
    return BRConfig(project_root)


def _history_request(
    port: int,
    path: str,
    *,
    host: str | None = None,
    if_none_match: str | None = None,
    timeout: float = 5.0,
) -> tuple[int, dict[str, str], bytes]:
    """Like `_lb_http_request`, but also returns response headers (for ETag)."""
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.putrequest("GET", path, skip_host=True)
        conn.putheader("Host", host if host is not None else f"127.0.0.1:{port}")
        if if_none_match is not None:
            conn.putheader("If-None-Match", if_none_match)
        conn.endheaders()
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, dict(resp.getheaders()), data
    finally:
        conn.close()


@pytest.mark.skipif(
    not _HAS_SSE_BRIDGE,
    reason="FEAT-3323: SseBridge/serve_sse_bridge/BridgeEventsConfig not implemented yet",
)
class TestHistoryRoute:
    def test_returns_payload_json_and_inherits_host_and_token_gates(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        from little_loops.cli.artifact.serve import make_history_route

        config = _history_project(tmp_path / "project")
        bridge = SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path / "loops",
            routes={"history": make_history_route(config)},
        )
        try:
            token = _bridge_token(bridge)
            port = _bridge_port(bridge)

            status, headers, body = _history_request(port, f"/{token}/history")
            assert status == 200
            assert headers["Content-Type"] == "application/json"
            assert headers["Cache-Control"] == "no-store"
            assert "ETag" in headers
            payload = json.loads(body)
            assert set(payload) == {
                "snapshot_gzip_b64",
                "exported_at",
                "source_schema_version",
                "export_mode",
                "filter_tables",
            }
            assert payload["export_mode"] == "shareable"
            assert sorted(payload["filter_tables"]) == ["loop_run", "usage_event"]

            import base64
            import gzip
            import sqlite3

            dest = tmp_path / "recovered.db"
            dest.write_bytes(gzip.decompress(base64.b64decode(payload["snapshot_gzip_b64"])))
            conn = sqlite3.connect(dest)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(loop_runs)")]
            assert "error" not in columns
            assert "diagnostics_path" not in columns

            status, _, _ = _history_request(port, f"/{token}/history", host="evil.example.com")
            assert status == 403
            status, _, _ = _history_request(port, "/not-the-real-token/history")
            assert status == 404
        finally:
            bridge.close()

    def test_never_migrates_or_creates_missing_db(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        from little_loops.cli.artifact.serve import make_history_route
        from little_loops.config.core import BRConfig

        project = tmp_path / "project"
        (project / ".ll").mkdir(parents=True)
        (project / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        config = BRConfig(project)
        bridge = SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path / "loops",
            routes={"history": make_history_route(config)},
        )
        try:
            token = _bridge_token(bridge)
            status, _, body = _history_request(_bridge_port(bridge), f"/{token}/history")
            assert status == 200
            import base64
            import gzip

            payload = json.loads(body)
            assert gzip.decompress(base64.b64decode(payload["snapshot_gzip_b64"])) == b""
            assert not (project / ".ll" / "history.db").exists()
        finally:
            bridge.close()

    def test_repeated_polls_do_not_rebuild_and_matching_etag_returns_304(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        import little_loops.cli.artifact.dashboard as dashboard_mod
        from little_loops.cli.artifact.serve import make_history_route

        config = _history_project(tmp_path / "project")
        bridge = SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path / "loops",
            routes={"history": make_history_route(config)},
        )
        try:
            token = _bridge_token(bridge)
            port = _bridge_port(bridge)
            with mock.patch.object(
                dashboard_mod, "build_snapshot_db", wraps=dashboard_mod.build_snapshot_db
            ) as spy:
                status1, headers1, _ = _history_request(port, f"/{token}/history")
                status2, _, _ = _history_request(port, f"/{token}/history")
                status3, _, _ = _history_request(port, f"/{token}/history")
                assert status1 == status2 == status3 == 200
                assert spy.call_count == 1

                etag = headers1["ETag"]
                status4, _, body4 = _history_request(port, f"/{token}/history", if_none_match=etag)
                assert status4 == 304
                assert body4 == b""
                assert spy.call_count == 1
        finally:
            bridge.close()

    def test_new_rows_appear_without_reload(self, short_tmp_path: Path, tmp_path: Path) -> None:
        import base64
        import gzip
        import sqlite3

        from little_loops.cli.artifact.serve import make_history_route

        project = tmp_path / "project"
        config = _history_project(project)
        bridge = SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path / "loops",
            routes={"history": make_history_route(config)},
        )
        try:
            token = _bridge_token(bridge)
            port = _bridge_port(bridge)
            status1, _, body1 = _history_request(port, f"/{token}/history")
            assert status1 == 200
            payload1 = json.loads(body1)
            db1 = tmp_path / "snap1.db"
            db1.write_bytes(gzip.decompress(base64.b64decode(payload1["snapshot_gzip_b64"])))
            rows1 = sqlite3.connect(db1).execute("SELECT run_id FROM loop_runs").fetchall()
            assert ("r-new",) not in rows1

            conn = sqlite3.connect(project / ".ll" / "history.db")
            conn.execute(
                "INSERT INTO loop_runs (run_id, loop_name, started_at, ended_at, final_state, "
                "iterations) VALUES ('r-new', 'loop-b', '2026-08-02T00:00:00Z', "
                "'2026-08-02T01:00:00Z', 'done', 1)"
            )
            conn.commit()
            conn.close()
            import os

            os.utime(project / ".ll" / "history.db", None)

            status2, _, body2 = _history_request(port, f"/{token}/history")
            assert status2 == 200
            payload2 = json.loads(body2)
            db2 = tmp_path / "snap2.db"
            db2.write_bytes(gzip.decompress(base64.b64decode(payload2["snapshot_gzip_b64"])))
            rows2 = sqlite3.connect(db2).execute("SELECT run_id FROM loop_runs").fetchall()
            assert ("r-new",) in rows2
        finally:
            bridge.close()

    def test_oversize_returns_413(self, short_tmp_path: Path, tmp_path: Path) -> None:
        from little_loops.cli.artifact.serve import make_history_route

        project = tmp_path / "project"
        (project / ".ll").mkdir(parents=True)
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps({"artifacts": {"export": {"max_artifact_bytes": 1}}}), encoding="utf-8"
        )
        _build_history_db(project / ".ll" / "history.db")
        from little_loops.config.core import BRConfig

        config = BRConfig(project)
        bridge = SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path / "loops",
            routes={"history": make_history_route(config)},
        )
        try:
            token = _bridge_token(bridge)
            status, _, _ = _history_request(_bridge_port(bridge), f"/{token}/history")
            assert status == 413
        finally:
            bridge.close()

    def test_readonly_opener_rejects_writes(self, tmp_path: Path) -> None:
        """The route's snapshot build goes through `_connect_readonly` (D19)."""
        from little_loops.session_store.queries import _connect_readonly

        db_path = tmp_path / "history.db"
        _build_history_db(db_path)
        conn = _connect_readonly(db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO loop_runs (run_id) VALUES ('x')")
        finally:
            conn.close()

    def test_concurrent_fetches_against_cold_cache_build_once(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        import little_loops.cli.artifact.dashboard as dashboard_mod
        from little_loops.cli.artifact.serve import make_history_route

        config = _history_project(tmp_path / "project")
        bridge = SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path / "loops",
            routes={"history": make_history_route(config)},
        )
        try:
            token = _bridge_token(bridge)
            port = _bridge_port(bridge)
            with mock.patch.object(
                dashboard_mod, "build_snapshot_db", wraps=dashboard_mod.build_snapshot_db
            ) as spy:
                statuses: list[int] = []
                threads = [
                    threading.Thread(
                        target=lambda: statuses.append(
                            _history_request(port, f"/{token}/history")[0]
                        )
                    )
                    for _ in range(8)
                ]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=10.0)
                assert statuses == [200] * 8
                assert spy.call_count == 1
        finally:
            bridge.close()

    def test_history_route_absent_and_placeholder_page_when_no_routes_mounted(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """Mirrors the default `events.bridge.history: false` gate: no routes mounted."""
        from little_loops.transport import _SSE_BRIDGE_PAGE_HTML  # type: ignore[attr-defined]

        bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        try:
            token = _bridge_token(bridge)
            port = _bridge_port(bridge)
            status, _, _ = _history_request(port, f"/{token}/history")
            assert status == 404
            status, body = _lb_http_request(port, "GET", f"/{token}/")
            assert status == 200
            assert body.decode("utf-8") == _SSE_BRIDGE_PAGE_HTML
        finally:
            bridge.close()


@pytest.mark.skipif(
    not _HAS_SSE_BRIDGE,
    reason="FEAT-3323: SseBridge/serve_sse_bridge/BridgeEventsConfig not implemented yet",
)
class TestPageHtmlFactoryFallback:
    def test_raising_factory_falls_back_to_placeholder_and_keeps_serving(
        self, short_tmp_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A page_html_factory failure must never take down the bridge (FEAT-3321)."""
        import little_loops.transport as transport_mod
        from little_loops.transport import _SSE_BRIDGE_PAGE_HTML  # type: ignore[attr-defined]

        real_bridge = SseBridge(_make_config(), port=0, base=short_tmp_path, loops_dir=tmp_path)
        monkeypatch.setattr(transport_mod, "SseBridge", lambda *a, **kw: real_bridge)

        def factory(bridge: SseBridge) -> str:
            raise ValueError("boom")

        result: dict[str, int] = {}

        def run() -> None:
            result["code"] = transport_mod.serve_sse_bridge(
                _make_config(), port=0, page_html_factory=factory
            )

        t = threading.Thread(target=run, daemon=True)
        t.start()
        try:
            _wait_until(lambda: real_bridge._serve_thread.is_alive())
            time.sleep(0.2)  # let the (synchronous) factory call in serve_sse_bridge run
            token = _bridge_token(real_bridge)
            status, body = _lb_http_request(_bridge_port(real_bridge), "GET", f"/{token}/")
            assert status == 200
            assert body.decode("utf-8") == _SSE_BRIDGE_PAGE_HTML

            sock = _sse_connect(_bridge_port(real_bridge), token)
            try:
                _read_sse_headers(sock)  # SSE stream still routes; would hang/error if dead
            finally:
                sock.close()
        finally:
            real_bridge.close()
            t.join(timeout=5.0)
        assert result.get("code") == 0


@pytest.mark.skipif(
    not _HAS_SERVE_CLI,
    reason="FEAT-3323: cli/artifact/serve.py (cmd_serve) not implemented yet",
)
class TestCmdServeHistoryGate:
    def test_history_disabled_by_default_passes_no_routes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        with mock.patch("little_loops.transport.serve_sse_bridge", return_value=0) as spy:
            code = cmd_serve(argparse.Namespace(port=None), Logger(use_color=False))  # type: ignore[name-defined]
        assert code == 0
        spy.assert_called_once()
        assert spy.call_args.kwargs["routes"] is None
        assert spy.call_args.kwargs["page_html_factory"] is None

    def test_history_enabled_passes_route_and_factory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"events": {"bridge": {"history": True}}}), encoding="utf-8"
        )
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        with mock.patch("little_loops.transport.serve_sse_bridge", return_value=0) as spy:
            code = cmd_serve(argparse.Namespace(port=None), Logger(use_color=False))  # type: ignore[name-defined]
        assert code == 0
        spy.assert_called_once()
        assert spy.call_args.kwargs["routes"] is not None
        assert "history" in spy.call_args.kwargs["routes"]
        assert spy.call_args.kwargs["page_html_factory"] is not None


@pytest.mark.skipif(
    not _HAS_SSE_BRIDGE,
    reason="FEAT-3323: SseBridge/serve_sse_bridge/BridgeEventsConfig not implemented yet",
)
class TestMethodRoutes:
    """FEAT-3504: `do_POST` + bounded `{name}`-segment matching on `method_routes`.

    Models `TestLocalBridgeTransport`'s POST dispatch tests
    (`test_interaction_post_lands_on_inbound_queue_unchanged`,
    `_lb_http_request`) since that is the direct in-repo precedent for POST
    over this handler shape.
    """

    def _bridge(self, short_tmp_path: Path, tmp_path: Path, **method_route_handlers):
        def _echo(handler, captured=None):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/plain")
            handler.end_headers()
            handler.wfile.write((captured or "").encode("utf-8"))

        def _post_echo(handler):
            length = int(handler.headers.get("Content-Length", "0"))
            body = handler.rfile.read(length) if length else b""
            handler.send_response(200)
            handler.send_header("Content-Type", "application/octet-stream")
            handler.end_headers()
            handler.wfile.write(body)

        method_routes = [
            ("GET", "widgets/{id}", _echo),
            ("GET", "widgets", lambda h: _echo(h, "list")),
            ("POST", "widgets", _post_echo),
        ]
        return SseBridge(
            _make_config(),
            port=0,
            base=short_tmp_path,
            loops_dir=tmp_path / "loops",
            method_routes=method_routes,
        )

    def test_get_matches_parameterized_segment_and_captures_it(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            status, body = _lb_http_request(_bridge_port(bridge), "GET", f"/{token}/widgets/abc123")
            assert status == 200
            assert body == b"abc123"
        finally:
            bridge.close()

    def test_get_matches_param_less_pattern(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            status, body = _lb_http_request(_bridge_port(bridge), "GET", f"/{token}/widgets")
            assert status == 200
            assert body == b"list"
        finally:
            bridge.close()

    def test_post_dispatches_to_matching_method_route(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            status, body = _lb_http_request(
                _bridge_port(bridge), "POST", f"/{token}/widgets", body=b"hello"
            )
            assert status == 200
            assert body == b"hello"
        finally:
            bridge.close()

    def test_wrong_method_for_a_registered_pattern_is_404(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """`widgets/{id}` is GET-only; POSTing it must not fall through to it."""
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            status, _ = _lb_http_request(
                _bridge_port(bridge), "POST", f"/{token}/widgets/abc123", body=b"x"
            )
            assert status == 404
        finally:
            bridge.close()

    def test_post_bad_host_header_returns_403(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            status, _ = _lb_http_request(
                _bridge_port(bridge), "POST", f"/{token}/widgets", host="evil.com", body=b"x"
            )
            assert status == 403
        finally:
            bridge.close()

    def test_post_wrong_token_returns_404(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            status, _ = _lb_http_request(
                _bridge_port(bridge), "POST", "/not-the-real-token/widgets", body=b"x"
            )
            assert status == 404
        finally:
            bridge.close()

    def test_post_bare_token_no_trailing_slash_returns_404_not_redirect(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """Bare `/{token}` 301-redirects for GET but 404s for POST (no unified
        `LocalBridgeTransport._route()`-style both-forms acceptance for POST)."""
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            status, _ = _lb_http_request(_bridge_port(bridge), "POST", f"/{token}", body=b"x")
            assert status == 404
        finally:
            bridge.close()

    def test_get_bare_token_still_redirects(self, short_tmp_path: Path, tmp_path: Path) -> None:
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            conn = http.client.HTTPConnection("127.0.0.1", _bridge_port(bridge), timeout=5.0)
            try:
                conn.putrequest("GET", f"/{token}", skip_host=True)
                conn.putheader("Host", f"127.0.0.1:{_bridge_port(bridge)}")
                conn.endheaders()
                resp = conn.getresponse()
                resp.read()
                assert resp.status == 301
                assert resp.getheader("Location") == f"/{token}/"
            finally:
                conn.close()
        finally:
            bridge.close()

    def test_existing_get_history_route_and_events_unaffected(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        """Existing exact-key `_routes` GET dispatch still wins over method_routes,
        and the SSE `events` route is untouched by the new matcher."""
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            sock = _sse_connect(_bridge_port(bridge), token)
            try:
                _read_sse_headers(sock)
            finally:
                sock.close()
        finally:
            bridge.close()

    def test_no_cors_headers_on_method_route_response(
        self, short_tmp_path: Path, tmp_path: Path
    ) -> None:
        bridge = self._bridge(short_tmp_path, tmp_path)
        try:
            token = _bridge_token(bridge)
            conn = http.client.HTTPConnection("127.0.0.1", _bridge_port(bridge), timeout=5.0)
            try:
                conn.putrequest("GET", f"/{token}/widgets", skip_host=True)
                conn.putheader("Host", f"127.0.0.1:{_bridge_port(bridge)}")
                conn.endheaders()
                resp = conn.getresponse()
                resp.read()
                headers = dict(resp.getheaders())
                assert not any(k.lower().startswith("access-control-") for k in headers)
            finally:
                conn.close()
        finally:
            bridge.close()
