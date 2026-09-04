"""Two candidate await-with-timeout shapes for a terminal HITL adapter.

Proves the risky core FEAT-1931's Proposed Solution assumes but has no
codebase precedent for: a selectors-bounded blocking read on a text stream,
combined with (or substituted for) shutdown-flag polling.
"""

from __future__ import annotations

import selectors
import threading
import time
from typing import IO


class TerminalAwaiter:
    """Reads one line from ``stream`` with a bounded timeout.

    Not the real ``TerminalAdapter`` — proves the I/O core in isolation.
    """

    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream

    def await_line_polling(
        self,
        timeout: float,
        shutdown_event: threading.Event,
        tick: float = 0.1,
    ) -> str | None:
        """Combined mechanism: selectors-bounded read + shutdown-flag polling
        in one call. Mirrors mcp_call.py's deadline loop, adding the
        _interruptible_sleep()-style flag check each tick.

        Returns the line (newline stripped), or ``None`` on timeout or
        shutdown.
        """
        deadline = time.monotonic() + timeout
        sel = selectors.DefaultSelector()
        sel.register(self._stream, selectors.EVENT_READ)
        try:
            while True:
                if shutdown_event.is_set():
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                ready = sel.select(timeout=min(tick, remaining))
                if not ready:
                    continue
                line = self._stream.readline()
                if not line:
                    return None
                return line.rstrip("\n")
        finally:
            sel.close()

    def await_line_single_read(self, timeout: float) -> str | None:
        """Simpler mechanism: one bounded selectors read, no internal
        shutdown check. Relies on a caller satisfying the re-entrant
        ``await_response()`` contract by invoking this repeatedly with short
        timeouts and checking shutdown between calls itself.

        Returns the line (newline stripped), or ``None`` on timeout.
        """
        sel = selectors.DefaultSelector()
        sel.register(self._stream, selectors.EVENT_READ)
        try:
            ready = sel.select(timeout=timeout)
            if not ready:
                return None
            line = self._stream.readline()
            if not line:
                return None
            return line.rstrip("\n")
        finally:
            sel.close()
