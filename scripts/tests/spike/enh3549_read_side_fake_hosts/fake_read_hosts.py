"""Divergent fake read-side hosts injected into the real session seam (ENH-3549 spike).

Two fake hosts whose on-disk transcript shapes deliberately disagree, plus
``install_fake_read_hosts`` -- the minimal set of ``monkeypatch`` calls that
makes the *unmodified* ``detect_sessions`` / ``iter_events`` /
``explain_no_sessions`` treat them as registered layout hosts. No precedent
patches these session-side registries (fake hosts today are runner-side only),
which is the mechanism this spike proves.

Shapes:
- ``fake``:         ``{"kind": "prompt"|"reply", "at": ISO8601, "text": str, "tokens": {...}}``
- ``fake-minimal``: ``{"role": "user"|"assistant", "time": epoch-seconds, "content": [{"t": str}]}``
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from little_loops.session_store import sessions, writers
from little_loops.session_store.sessions import SessionEvent, SessionHandle
from little_loops.user_messages import encode_project_path

FAKE_HOSTS = ("fake", "fake-minimal")


def project_dir(host: str, cwd: Path, home: Path) -> Path:
    return home / f".{host}" / "projects" / encode_project_path(str(cwd))


def write_fake_session(home: Path, cwd: Path, session_id: str, prompts: list[str]) -> Path:
    """Write a ``fake``-shaped session: each prompt followed by a reply."""
    folder = project_dir("fake", cwd, home)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session_id}.jsonl"
    lines = []
    for i, text in enumerate(prompts):
        lines.append({"kind": "prompt", "at": f"2026-09-24T10:0{i}:00Z", "text": text})
        lines.append({"kind": "reply", "at": f"2026-09-24T10:0{i}:05Z", "tokens": {"in": 4}})
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")
    return path


def write_fake_minimal_session(home: Path, cwd: Path, session_id: str, prompts: list[str]) -> Path:
    """Write a ``fake-minimal``-shaped session: each prompt followed by a reply."""
    folder = project_dir("fake-minimal", cwd, home)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session_id}.jsonl"
    lines = []
    for i, text in enumerate(prompts):
        lines.append({"role": "user", "time": 1758708000 + i * 60, "content": [{"t": text}]})
        lines.append({"role": "assistant", "time": 1758708005 + i * 60, "content": []})
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")
    return path


def _records(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if raw:
                yield line_no, json.loads(raw)


def parse_fake(path: Path) -> Iterator[SessionEvent]:
    for line_no, rec in _records(path):
        yield SessionEvent(
            type="user" if rec["kind"] == "prompt" else "assistant",
            timestamp=rec["at"],
            host="fake",
            payload=rec,
            line_no=line_no,
        )


def parse_fake_minimal(path: Path) -> Iterator[SessionEvent]:
    for line_no, rec in _records(path):
        yield SessionEvent(
            type=rec["role"],
            timestamp=str(rec["time"]),
            host="fake-minimal",
            payload=rec,
            line_no=line_no,
        )


def prompt_text(event: SessionEvent) -> str | None:
    """Per-host prompt-text extraction -- the honest divergence, kept out of the seam."""
    if event.type != "user":
        return None
    if event.host == "fake":
        return str(event.payload["text"])
    return "".join(b["t"] for b in event.payload["content"])


def install_fake_read_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register both fakes on the real session seam (test-scoped, auto-undone)."""
    monkeypatch.setitem(sessions._PARSERS, "fake", parse_fake)
    monkeypatch.setitem(sessions._PARSERS, "fake-minimal", parse_fake_minimal)
    monkeypatch.setattr(sessions, "_REGISTERED_HOSTS", (*sessions._REGISTERED_HOSTS, *FAKE_HOSTS))
    monkeypatch.setattr(sessions, "_LAYOUT_HOSTS", (*sessions._LAYOUT_HOSTS, *FAKE_HOSTS))

    real_folder = sessions._project_folder_for_layout_host

    def folder(host: str, cwd: Path, home: Path) -> Path | None:
        if host in FAKE_HOSTS:
            found = project_dir(host, cwd, home)
            return found if found.is_dir() else None
        return real_folder(host, cwd, home)

    monkeypatch.setattr(sessions, "_project_folder_for_layout_host", folder)

    real_layout = writers.host_layout_for

    def layout(host: str) -> Any:
        if host in FAKE_HOSTS:
            return SimpleNamespace(session_glob="*.jsonl")
        return real_layout(host)

    monkeypatch.setattr(writers, "host_layout_for", layout)


def read_prompts(handles: list[SessionHandle]) -> list[str]:
    """A host-agnostic reader: only ``detect_sessions`` handles + ``iter_events``."""
    out: list[str] = []
    for handle in handles:
        for event in sessions.iter_events(handle):
            text = prompt_text(event)
            if text is not None:
                out.append(text)
    return out
