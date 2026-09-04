"""AC tests for the FEAT-1931 terminal-HITL-await spike.

Uses a real ``os.pipe()`` (not ``StringIO``) because ``selectors`` requires a
real file-descriptor-backed object to prove readiness semantics.
"""

from __future__ import annotations

import ast
import os
import threading
import time
from pathlib import Path

import pytest

from scripts.tests.spike.terminal_hitl_await.awaiter import TerminalAwaiter


@pytest.fixture
def pipe():
    r_fd, w_fd = os.pipe()
    reader = os.fdopen(r_fd, "r")
    writer = os.fdopen(w_fd, "w")
    yield reader, writer
    for f in (reader, writer):
        if not f.closed:
            f.close()


class TestPollingMechanism:
    """Combined mechanism: selectors-bounded read + shutdown-flag polling."""

    def test_polling_returns_line_when_available_before_timeout(self, pipe) -> None:
        reader, writer = pipe
        writer.write("approve\n")
        writer.flush()
        awaiter = TerminalAwaiter(reader)
        result = awaiter.await_line_polling(timeout=2.0, shutdown_event=threading.Event())
        assert result == "approve"

    def test_polling_returns_none_on_pure_timeout_no_shutdown(self, pipe) -> None:
        reader, _writer = pipe
        awaiter = TerminalAwaiter(reader)
        start = time.monotonic()
        result = awaiter.await_line_polling(timeout=0.3, shutdown_event=threading.Event())
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed < 1.0

    def test_polling_exits_promptly_on_shutdown_signal_mid_block(self, pipe) -> None:
        reader, _writer = pipe
        shutdown_event = threading.Event()

        def flip_after_delay() -> None:
            time.sleep(0.2)
            shutdown_event.set()

        threading.Thread(target=flip_after_delay, daemon=True).start()
        awaiter = TerminalAwaiter(reader)
        start = time.monotonic()
        result = awaiter.await_line_polling(
            timeout=5.0, shutdown_event=shutdown_event, tick=0.1
        )
        elapsed = time.monotonic() - start
        assert result is None
        # Proves the shutdown flag interrupts the block within ~one tick,
        # not only at the next long-timeout await_response() call.
        assert elapsed < 1.0


class TestSingleReadMechanism:
    """Simpler mechanism: one bounded read, no internal shutdown polling."""

    def test_single_read_returns_line_when_available_before_timeout(self, pipe) -> None:
        reader, writer = pipe
        writer.write("reject\n")
        writer.flush()
        awaiter = TerminalAwaiter(reader)
        result = awaiter.await_line_single_read(timeout=2.0)
        assert result == "reject"

    def test_single_read_returns_none_on_timeout(self, pipe) -> None:
        reader, _writer = pipe
        awaiter = TerminalAwaiter(reader)
        start = time.monotonic()
        result = awaiter.await_line_single_read(timeout=0.3)
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed < 1.0

    def test_repeated_short_timeout_calls_satisfy_reentrant_contract(self, pipe) -> None:
        """Simulates the executor's documented re-entrant calling pattern:
        short-timeout calls in a loop, with shutdown checked by the caller
        between calls — proving await_line_single_read() alone (no internal
        polling) achieves the same responsiveness as the combined mechanism.
        """
        reader, writer = pipe
        shutdown_event = threading.Event()

        def flip_after_delay() -> None:
            time.sleep(0.25)
            shutdown_event.set()

        threading.Thread(target=flip_after_delay, daemon=True).start()
        awaiter = TerminalAwaiter(reader)
        start = time.monotonic()
        result = None
        while not shutdown_event.is_set():
            result = awaiter.await_line_single_read(timeout=0.1)
            if result is not None:
                break
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed < 1.0

        # Verdict still arrives correctly when written before the caller's
        # next poll — proving no verdict is lost by the re-entrant pattern.
        writer.write("edit\n")
        writer.flush()
        result = awaiter.await_line_single_read(timeout=0.5)
        assert result == "edit"


class TestSpikeIsolation:
    def test_spike_does_not_import_production_adapter_modules(self) -> None:
        forbidden = {"little_loops.fsm.adapters.terminal_adapter", "little_loops.fsm.executor"}
        spike_dir = Path(__file__).parent
        for py_file in spike_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module} if node.module else set()
                else:
                    continue
                hit = names & forbidden
                assert not hit, f"{py_file.name} imports forbidden production module(s): {hit}"
