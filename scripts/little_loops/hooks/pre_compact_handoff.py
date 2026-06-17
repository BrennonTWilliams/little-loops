"""PreCompact handoff hook handler: write a session continuation prompt before context compaction.

``handle`` fires on every PreCompact event and writes ``.ll/ll-continue-prompt.md``
(≤2KB, priority-tiered) so ``/ll:resume`` can restore session state after compaction.

An idempotency guard skips the write when the prompt is already fresher than the
``compacted_at`` timestamp written by the preceding ``pre_compact`` handler.

The wire-visible output is ``.ll/ll-continue-prompt.md``; its schema (``## Intent`` +
``## Next Steps`` headings) is detected by ``commands/resume.md:56–68``.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

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

        # --- Gather state from external sources (all degrade gracefully) ---

        # Tier 1a: Active in-progress issues
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

        # Tier 1b: Files edited this session
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

        # Tier 1c: Current branch name
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

        # Tier 1d: Loop state (best-effort; .jsonl files are the norm, .json rare)
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

        # --- Build tiered sections (highest priority = lowest index = kept last) ---

        session_date = datetime.now(UTC).strftime("%Y-%m-%d")
        issues_summary = active_issues_text[:200] if active_issues_text else "none"
        intent_body = active_issues_text if active_issues_text else "No in-progress issues."

        # Section 0 is always-kept: frontmatter + ## Intent + ## Next Steps
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

        # Section 1: File modifications (always kept → placed early, dropped after header)
        files_body = files_text if files_text else "No uncommitted file changes."
        sections.append(f"## File Modifications\n{files_body}")

        # Section 2: Decisions/blockers + loop state (kept if space)
        decisions_parts: list[str] = []
        if loop_state_text:
            decisions_parts.append(f"Loop state:\n{loop_state_text}")
        decisions_body = (
            "\n".join(decisions_parts) if decisions_parts else "No open decisions recorded."
        )
        sections.append(f"## Decisions Made\n{decisions_body}")

        # Section 3: Recent tool-event summary from session events log (dropped first)
        session_events_file = state_dir / "ll-session-events.jsonl"
        if session_events_file.is_file():
            try:
                lines = session_events_file.read_text(encoding="utf-8").splitlines()
                recent = lines[-10:] if len(lines) > 10 else lines
                if recent:
                    sections.append("## Recent Activity\n" + "\n".join(recent))
            except OSError:
                pass

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
