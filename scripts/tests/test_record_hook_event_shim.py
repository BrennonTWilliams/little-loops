"""Tests for the ``record-hook-event.sh`` bash shim (ENH-2506).

The shim is the telemetry path for hosts events that never route through the
Python dispatcher — today only ``Stop``/``SessionEnd``, which
``hooks/hooks.json`` binds directly to raw bash scripts. It must:

1. Exit 0 unconditionally (telemetry can never fail the paired hook).
2. Write a ``hook_events`` row via ``ll-session record-hook-event`` when
   ``analytics.enabled`` is true and ``analytics.capture.hooks`` is not
   explicitly ``false``.
3. Skip the write (but still exit 0) when no config is present, or when
   ``analytics.enabled`` is false, or ``analytics.capture.hooks`` is false.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM = REPO_ROOT / "hooks/scripts/record-hook-event.sh"
INVOKE_TIMEOUT = 10


def _run_shim(
    cwd: Path, event_name: str = "Stop", stdin: str = "{}"
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SHIM), event_name, "hooks/scripts/session-cleanup.sh"],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=INVOKE_TIMEOUT,
    )


def _write_config(project_dir: Path, *, analytics_enabled: bool, hooks: bool | None = None) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    analytics: dict = {"enabled": analytics_enabled}
    if hooks is not None:
        analytics["capture"] = {"hooks": hooks}
    (ll_dir / "ll-config.json").write_text(json.dumps({"analytics": analytics}), encoding="utf-8")


class TestRecordHookEventShim:
    def test_exits_zero_on_success(self, tmp_path: Path) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        result = _run_shim(tmp_path)
        assert result.returncode == 0

    def test_writes_row_when_enabled(self, tmp_path: Path) -> None:
        if shutil.which("ll-session") is None:
            pytest.skip("ll-session not installed on PATH")
        _write_config(tmp_path, analytics_enabled=True)
        result = _run_shim(tmp_path, stdin=json.dumps({"session_id": "sess-9"}))
        assert result.returncode == 0
        db = tmp_path / ".ll" / "history.db"
        assert db.exists()

        from little_loops.history_reader import recent_hook_events

        rows = recent_hook_events(db=db)
        assert len(rows) == 1
        assert rows[0].event_name == "Stop"
        assert rows[0].session_id == "sess-9"

    def test_skipped_when_analytics_disabled(self, tmp_path: Path) -> None:
        _write_config(tmp_path, analytics_enabled=False)
        result = _run_shim(tmp_path)
        assert result.returncode == 0
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_skipped_when_capture_hooks_false(self, tmp_path: Path) -> None:
        _write_config(tmp_path, analytics_enabled=True, hooks=False)
        result = _run_shim(tmp_path)
        assert result.returncode == 0
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_graceful_when_config_absent(self, tmp_path: Path) -> None:
        result = _run_shim(tmp_path)
        assert result.returncode == 0
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_graceful_when_ll_session_not_on_path(self, tmp_path: Path) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"
        result = subprocess.run(
            ["bash", str(SHIM), "Stop", "hooks/scripts/session-cleanup.sh"],
            input="{}",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
            timeout=INVOKE_TIMEOUT,
        )
        assert result.returncode == 0
