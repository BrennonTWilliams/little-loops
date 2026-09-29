"""Schedule current-session usage refresh after a supported Stop event.

This handler runs on the host's turn path. It only validates the event and
spawns a detached worker; all transcript and database I/O happens there.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from little_loops.config.core import resolve_config_path
from little_loops.hooks import resolve_hook_root
from little_loops.hooks.types import LLHookEvent, LLHookResult


def handle(event: LLHookEvent) -> LLHookResult:
    """Queue a detached usage refresh for a configured project."""
    if event.host not in {"claude-code", "codex"} or os.environ.get("LL_NON_INTERACTIVE"):
        return LLHookResult()

    transcript = event.payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript.strip().endswith(".jsonl"):
        return LLHookResult()

    try:
        root = resolve_hook_root(event)
        if resolve_config_path(root) is None:
            return LLHookResult()
        source = Path(transcript.strip()).expanduser()
        if not source.is_absolute():
            source = root / source
        db = Path(os.environ.get("LL_HISTORY_DB") or root / ".ll" / "history.db")
        argv = [
            sys.executable,
            "-m",
            "little_loops.cli.backfill_worker",
            str(db),
            str(source),
            "--host",
            event.host,
            "--usage-trigger",
            "--requested-at-ns",
            str(time.time_ns()),
        ]
        subprocess.Popen(
            argv,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(root),
        )
    except Exception:  # best-effort telemetry must never alter the Stop result
        pass
    return LLHookResult()
