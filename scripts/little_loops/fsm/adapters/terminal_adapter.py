"""Stdin/stdout ``CommunicationAdapter`` for interactive HITL approval (FEAT-1931).

The default, zero-config channel: the FSM prints a formatted prompt to the
terminal, blocks on one bounded ``selectors``-timed stdin read per
``await_response()`` call (the FEAT-1931 spike's proven
``await_line_single_read()`` shape), and parses the operator's verdict.
Shutdown responsiveness comes from the executor's re-entrant short-tick
calling pattern plus an uncaught ``KeyboardInterrupt`` — not from an internal
polling loop.
"""

from __future__ import annotations

import logging
import os
import selectors
import sys
import time
import uuid
from dataclasses import dataclass
from typing import IO

from little_loops.cli.output import colorize, status_block
from little_loops.fsm.communication_adapter import (
    AdapterResponse,
    CommunicationAdapter,
    TimeoutResponse,
    Verdict,
)

logger = logging.getLogger(__name__)

_UNRECOGNIZED_HINT = "Expected y/yes/approve, n/no/reject, e/edit"

# (word, verdict) pairs, checked in order. Case-insensitive unambiguous
# prefix matching: the three verdicts' word forms start with distinct
# letters (y/a, n/r, e), so a single-letter prefix never collides.
_VERDICT_WORDS: tuple[tuple[str, Verdict], ...] = (
    ("yes", "approve"),
    ("approve", "approve"),
    ("no", "reject"),
    ("reject", "reject"),
    ("edit", "edit"),
)


def _parse_verdict(line: str) -> AdapterResponse | None:
    """Parse one line of operator input into a verdict, or ``None`` if unrecognized."""
    stripped = line.strip()
    if not stripped:
        return None

    parts = stripped.split(None, 1)
    token = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    verdict: Verdict | None = None
    for word, mapped in _VERDICT_WORDS:
        if word.startswith(token):
            verdict = mapped
            break
    if verdict is None:
        return None

    if verdict == "reject":
        return AdapterResponse(verdict="reject", reason=rest or None)
    return AdapterResponse(verdict=verdict)


@dataclass
class _PendingAlert:
    """Per-alert adapter-side state, keyed by ``alert_id``."""

    state_name: str
    awaiting_edit_text: bool = False


class TerminalAdapter(CommunicationAdapter):
    """Stdin/stdout implementation of the HITL communication protocol.

    Synchronous adapter: one bounded stdin read per ``await_response()`` call.
    Always available with zero configuration.
    """

    def __init__(self, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> None:
        """Streams default to ``sys.stdin``/``sys.stdout`` resolved at call time.

        Tests inject ``os.pipe()``-backed streams; ``selectors`` needs a real fd.
        """
        self._stdin = stdin
        self._stdout = stdout
        self._pending: dict[str, _PendingAlert] = {}
        self._stdin_closed = False
        # Raw bytes read from the fd but not yet consumed as a full line.
        # readline() on the stream itself is never used: TextIOWrapper's
        # internal chunk read-ahead can pull a later line's bytes off the fd
        # during one readline() call, leaving nothing for `selectors` to see
        # on the next call's select() even though a line is already buffered
        # — so line splitting is done manually on raw fd reads instead.
        self._read_buffer = b""

    def _resolve_stdin(self) -> IO[str]:
        return self._stdin if self._stdin is not None else sys.stdin

    def _resolve_stdout(self) -> IO[str]:
        return self._stdout if self._stdout is not None else sys.stdout

    def send_alert(
        self,
        loop_name: str,
        state_name: str,
        prompt: str,
        captured_context: dict,
    ) -> str:
        """Render formatted prompt + context to stdout."""
        alert_id = uuid.uuid4().hex
        self._pending[alert_id] = _PendingAlert(state_name=state_name)

        items: dict[str, str] = {
            "Loop": loop_name,
            "State": state_name,
            "Prompt": prompt,
        }
        deadline = captured_context.get("deadline")
        if isinstance(deadline, int | float):
            items["Time remaining"] = f"{int(deadline - time.monotonic())}s"
        context_items = {k: str(v) for k, v in captured_context.items() if k != "deadline"}
        if context_items:
            items["Context"] = ", ".join(f"{k}={v}" for k, v in context_items.items())
        items["Valid responses"] = "y/yes/approve, n/no/reject, e/edit"

        stdout = self._resolve_stdout()
        print(colorize("Human approval requested", "36"), file=stdout)
        print(status_block(items), file=stdout)
        return alert_id

    def _read_line(self, timeout: float) -> str | None:
        """One bounded ``selectors`` read; ``None`` on timeout or EOF.

        Reads raw bytes off the fd (never ``stream.readline()``) into
        ``_read_buffer`` and splits off complete lines manually, so a line
        already sitting in the buffer from a prior read satisfies this call
        with no further ``select()`` needed. Sets ``_stdin_closed`` the first
        time a raw read returns empty (EOF), logging a single warning.
        """
        stream = self._resolve_stdin()
        encoding = getattr(stream, "encoding", None) or "utf-8"
        fd = stream.fileno()
        deadline = time.monotonic() + timeout
        sel = selectors.DefaultSelector()
        sel.register(fd, selectors.EVENT_READ)
        try:
            while True:
                newline_at = self._read_buffer.find(b"\n")
                if newline_at != -1:
                    line, self._read_buffer = (
                        self._read_buffer[:newline_at],
                        self._read_buffer[newline_at + 1 :],
                    )
                    return line.decode(encoding, errors="replace")

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                if not sel.select(timeout=remaining):
                    continue

                chunk = os.read(fd, 4096)
                if not chunk:
                    if not self._stdin_closed:
                        logger.warning(
                            "TerminalAdapter: stdin closed (EOF); HITL prompts will time out"
                        )
                    self._stdin_closed = True
                    return None
                self._read_buffer += chunk
        finally:
            sel.close()

    def await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse:
        """Block on stdin with shutdown-signal awareness, parse verdict."""
        pending = self._pending[alert_id]
        start = time.monotonic()

        if self._stdin_closed:
            time.sleep(timeout)
            return TimeoutResponse(elapsed_seconds=time.monotonic() - start)

        if pending.awaiting_edit_text:
            line = self._read_line(timeout)
            if line is None:
                return TimeoutResponse(elapsed_seconds=time.monotonic() - start)
            del self._pending[alert_id]
            return AdapterResponse(verdict="edit", edited_text=line)

        line = self._read_line(timeout)
        if line is None:
            return TimeoutResponse(elapsed_seconds=time.monotonic() - start)

        parsed = _parse_verdict(line)
        if parsed is None:
            print(_UNRECOGNIZED_HINT, file=self._resolve_stdout())
            return TimeoutResponse(elapsed_seconds=time.monotonic() - start)

        if parsed.verdict == "edit":
            print("Enter replacement text (one line):", file=self._resolve_stdout())
            pending.awaiting_edit_text = True
            remaining = max(0.0, timeout - (time.monotonic() - start))
            edit_line = self._read_line(remaining)
            if edit_line is None:
                return TimeoutResponse(elapsed_seconds=time.monotonic() - start)
            del self._pending[alert_id]
            return AdapterResponse(verdict="edit", edited_text=edit_line)

        del self._pending[alert_id]
        return parsed

    def supports_async(self) -> bool:
        """Terminal adapter is synchronous — operator must be present."""
        return False

    def cancel_alert(self, alert_id: str) -> None:
        """Print a withdrawn notice and drop the alert's pending state."""
        if self._pending.pop(alert_id, None) is None:
            return
        print(colorize(f"Alert withdrawn: {alert_id}", "33"), file=self._resolve_stdout())
