"""Synthetic-home builders for the ENH-3430 workspace-union spike.

Writes real, on-disk claude-code- and codex-shaped session files under a
fixture ``home`` directory so the spike drives the real
``list_workspaces``/``detect_sessions``/``iter_events`` seam end-to-end,
never a mock of it. The ll-activity signal used is the ``queue-operation``
record shape ``_is_ll_relevant`` checks first -- host-agnostic, so it works
identically whether the record is a whole claude-code JSONL line or nested
inside a codex rollout's ``payload``.
"""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.user_messages import encode_project_path

_LL_ACTIVITY_RECORD = {"type": "queue-operation", "operation": "enqueue", "content": "/ll:spike"}
_NON_LL_RECORD = {"type": "queue-operation", "operation": "enqueue", "content": "not-an-ll-command"}


def write_claude_project(
    home: Path,
    cwd: Path,
    session_id: str,
    *,
    encode_cwd: Path | None = None,
    ll_relevant: bool = True,
) -> None:
    """Write one real claude-code-shaped project + session under *home*.

    *encode_cwd* (defaults to *cwd*) is the path used to derive the on-disk
    project-directory encoding -- pass the resolved path to simulate a
    workspace recorded under an as-recorded spelling (e.g. a symlink) that
    differs from the directory's real encoding, exactly as
    ``_get_claude_project_folder`` expects the directory name to match one
    of ``_cwd_spellings(cwd)``.
    """
    encoded = encode_project_path(str(encode_cwd if encode_cwd is not None else cwd))
    project_dir = home / ".claude" / "projects" / encoded
    project_dir.mkdir(parents=True, exist_ok=True)
    records = [{"type": "session_meta", "cwd": str(cwd)}]
    records.append(_LL_ACTIVITY_RECORD if ll_relevant else _NON_LL_RECORD)
    path = project_dir / f"{session_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def write_codex_project(
    home: Path,
    cwd: Path,
    session_id: str,
    *,
    ll_relevant: bool = True,
) -> None:
    """Write one real codex-shaped rollout under *home*'s scan-fallback tree."""
    rollout = home / ".codex" / "sessions" / "2026" / "09" / "09" / f"{session_id}.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2026-09-09T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(cwd), "cli_version": "0.152.1"},
        },
        {
            "timestamp": "2026-09-09T00:00:01Z",
            "type": "response_item",
            "payload": _LL_ACTIVITY_RECORD if ll_relevant else _NON_LL_RECORD,
        },
    ]
    with rollout.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
