"""PreCompact handoff hook handler: write a session continuation prompt before context compaction.

``handle`` fires on every PreCompact event and writes ``.ll/ll-continue-prompt.md``
(≤2KB, priority-tiered) so ``/ll:resume`` can restore session state after compaction.

An idempotency guard skips the write when the prompt is already fresher than the
``compacted_at`` timestamp written by the preceding ``pre_compact`` handler.

When ``.ll/ll-session-events.jsonl`` is present (written by FEAT-1262's session-capture.sh),
``_build_from_event_log()`` is used: file edits are deduplicated by subject, only unresolved
errors are included, and task state reflects the last event per subject. Otherwise
``_build_fallback()`` reconstructs state from git diff and loop run snapshots.

The wire-visible output is ``.ll/ll-continue-prompt.md``; its schema (``## Intent`` +
``## Next Steps`` headings) is detected by ``commands/resume.md:56–68``.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.file_utils import acquire_lock, atomic_write
from little_loops.hooks.types import LLHookEvent, LLHookResult

_FEEDBACK = "[ll] Session handoff snapshot written."


def _build_content(sections: list[str], max_bytes: int = 2048) -> str:
    """Join *sections* with double newlines, dropping trailing entries LIFO until ≤ *max_bytes*.

    Mutates *sections* in place (callers pass a freshly-built list each time).
    Returns the joined string; returns empty string when *sections* is empty.
    """
    while len("\n\n".join(sections).encode()) > max_bytes:
        if len(sections) <= 1:
            break
        sections.pop()
    return "\n\n".join(sections)


def _build_from_event_log(log_path: Path) -> list[str]:
    """Build priority-tiered markdown sections from structured JSONL session events.

    Returns sections in the same format as ``_build_fallback()`` so the existing
    ``_build_content()`` size-capping logic applies unchanged.

    Event schema (written by session-capture.sh, FEAT-1262):
        {"ts": "ISO8601", "type": "file|task|git|error", "op": "...", "subject": "...", "status": ""}
    """
    from little_loops.events import EventBus

    events = EventBus.read_events(log_path)

    # File edits: last event per subject wins (deduplication; reverts naturally excluded)
    file_edits: dict[str, str] = {}
    for ev in events:
        if ev.type == "file":
            subject = ev.payload.get("subject", "")
            if subject:
                file_edits[subject] = subject

    # Error resolution heuristic (canonical definition in FEAT-1262 § Event Semantics):
    # track the last event for each subject across ALL event types. If the last event
    # for a given subject still has type=error, the error is unresolved.
    last_by_subject: dict[str, Any] = {}
    for ev in events:
        subject = ev.payload.get("subject", "")
        if subject:
            last_by_subject[subject] = ev
    unresolved_errors = [ev for ev in last_by_subject.values() if ev.type == "error"]

    # Tasks: net state — last event per subject wins
    task_state: dict[str, Any] = {}
    for ev in events:
        if ev.type == "task":
            subject = ev.payload.get("subject", "")
            if subject:
                task_state[subject] = ev

    files_md = "\n".join(f"- {s}" for s in file_edits) or "(none)"
    errors_md = (
        "\n".join(f"- {ev.payload.get('subject', '?')}" for ev in unresolved_errors)
        or "(none)"
    )
    tasks_md = (
        "\n".join(
            f"- {ev.payload.get('subject', '?')} [{ev.payload.get('status', '')}]"
            for ev in task_state.values()
        )
        or "(none)"
    )

    return [
        f"## File Modifications\n{files_md}",
        f"## Unresolved Errors\n{errors_md}",
        f"## Task State\n{tasks_md}",
    ]


def _build_fallback() -> list[str]:
    """Build sections from git diff and loop state when no event log is available (FEAT-1156 path)."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        files_text = r.stdout.strip() if r.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        files_text = ""

    loop_state_lines: list[str] = []
    try:
        runs_dir = Path(".loops/runs")
        if runs_dir.is_dir():
            run_dirs = sorted(
                (d for d in runs_dir.glob("*/") if d.is_dir()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for rd in run_dirs[:3]:
                for jf in list(rd.glob("*.json"))[:1]:
                    try:
                        data = json.loads(jf.read_text(encoding="utf-8"))
                        keys = list(data.keys())[:3]
                        loop_state_lines.append(f"- {rd.name}: {keys}")
                    except (OSError, json.JSONDecodeError):
                        continue
    except OSError:
        pass
    loop_state_text = "\n".join(loop_state_lines)

    sections = []
    files_body = files_text if files_text else "No uncommitted file changes."
    sections.append(f"## File Modifications\n{files_body}")

    decisions_parts: list[str] = []
    if loop_state_text:
        decisions_parts.append(f"Loop state:\n{loop_state_text}")
    decisions_body = (
        "\n".join(decisions_parts) if decisions_parts else "No open decisions recorded."
    )
    sections.append(f"## Decisions Made\n{decisions_body}")

    return sections


def handle(event: LLHookEvent) -> LLHookResult:
    """Write .ll/ll-continue-prompt.md before context compaction.

    Returns ``LLHookResult(exit_code=2, feedback=...)`` on successful write,
    ``LLHookResult(exit_code=0)`` on idempotency skip or any error.
    """
    try:
        state_dir = Path(".ll")
        prompt_path = state_dir / "ll-continue-prompt.md"
        lock_path = prompt_path.with_suffix(".md.lock")
        state_file = state_dir / "ll-precompact-state.json"
        event_log = state_dir / "ll-session-events.jsonl"

        # Idempotency guard: skip write if prompt is already fresher than compacted_at.
        # Any parse error means we cannot verify freshness → proceed with write.
        try:
            compacted_at_str = json.loads(
                state_file.read_text(encoding="utf-8")
            )["compacted_at"]
            compacted_epoch = datetime.fromisoformat(
                compacted_at_str.replace("Z", "+00:00")
            ).timestamp()
            if prompt_path.stat().st_mtime > compacted_epoch:
                return LLHookResult(exit_code=0)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass

        # --- Header data (common to both paths) ---

        # Active in-progress issues
        try:
            r = subprocess.run(
                ["ll-issues", "list", "--status", "in_progress"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            active_issues_text = r.stdout.strip() if r.returncode == 0 else ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            active_issues_text = ""

        # Current branch name
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            session_branch = r.stdout.strip() if r.returncode == 0 else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            session_branch = "unknown"

        # --- Build header (Section 0: always kept) ---

        session_date = datetime.now(UTC).strftime("%Y-%m-%d")
        issues_summary = active_issues_text[:200] if active_issues_text else "none"
        intent_body = active_issues_text if active_issues_text else "No in-progress issues."

        header = (
            f"---\n"
            f"session_date: {session_date}\n"
            f"session_branch: {session_branch}\n"
            f"issues_in_progress: {issues_summary}\n"
            f"---\n\n"
            f"## Intent\n{intent_body}\n\n"
            f"## Next Steps\nResume active work on the issues above."
        )

        sections = [header]

        # --- Primary path: structured event log (FEAT-1262) ---
        # Fallback path: git diff + loop state (FEAT-1156)
        if event_log.is_file():
            sections.extend(_build_from_event_log(event_log))
        else:
            sections.extend(_build_fallback())

        # Apply LIFO 2KB cap and write
        state_dir.mkdir(parents=True, exist_ok=True)
        content = _build_content(sections, max_bytes=2048)

        try:
            with acquire_lock(lock_path, timeout=3.0):
                atomic_write(prompt_path, content)
        except TimeoutError:
            atomic_write(prompt_path, content)

    except Exception:
        return LLHookResult(exit_code=0)

    return LLHookResult(exit_code=2, feedback=_FEEDBACK)
