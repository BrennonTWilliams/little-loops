"""PreDone hook handler: gate the advisor consult onto the ``Stop`` event (FEAT-3118).

Invoked by the dispatcher in ``little_loops.hooks.__init__::main_hooks`` after
the Claude Code adapter (``hooks/adapters/claude-code/stop.sh``) parses the
host's stdin payload into an :class:`LLHookEvent`. Claude Code's ``Stop``
fires after *every* assistant turn, not at task completion, so this handler
dedups on a SHA-256 of the capped working diff — it consults once per
distinct diff state rather than once per turn (see FEAT-3118's "Expected
Behavior" -> "``Stop`` fires per turn" for the full rationale).

Decision order (first match short-circuits to a no-op ``LLHookResult(exit_code=0)``):

1. ``find_project_root`` fails, or the root isn't a git work tree, or
   ``git`` is unavailable.
2. ``git diff HEAD`` is empty and there are no untracked files.
3. The capped diff's SHA-256 matches the last recorded hash for this task.
4. ``advisor.timeout_seconds > 190`` (the ``Stop`` hook's own timeout margin).
5. Otherwise: consult, and on a real verdict record the new diff hash.

v1 is advisory only — ``exit_code`` is always 0; a successful verdict is
surfaced via ``feedback`` (stderr), never via blocking (``exit_code=2``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from little_loops.file_utils import acquire_lock, atomic_write_json
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.paths import find_project_root

logger = logging.getLogger(__name__)

_DIFF_MAX_LINES = 400
_DIFF_MAX_BYTES = 96_000
_QUESTION = (
    "Review the current working diff for correctness, risk, and completeness "
    "before this task is considered done."
)


def _run_git(root: Path, *args: str) -> str | None:
    """Run a git command in *root*; return stdout, or None on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _capture_diff(root: Path) -> str | None:
    """Return the capped working diff, or None if there is nothing to consult on."""
    diff = _run_git(root, "diff", "HEAD")
    status = _run_git(root, "status", "--porcelain")
    if diff is None or status is None:
        return None
    if not diff.strip() and not status.strip():
        return None

    combined = diff
    if status.strip():
        combined = f"{diff}\n--- untracked/status ---\n{status}" if diff else status

    lines = combined.splitlines()
    truncated_lines = len(lines) > _DIFF_MAX_LINES
    capped_lines = lines[:_DIFF_MAX_LINES]
    capped = "\n".join(capped_lines)

    encoded = capped.encode("utf-8")
    truncated_bytes = len(encoded) > _DIFF_MAX_BYTES
    if truncated_bytes:
        capped = encoded[:_DIFF_MAX_BYTES].decode("utf-8", errors="ignore")

    if truncated_lines or truncated_bytes:
        capped += (
            f"\n... [truncated: {min(len(lines), _DIFF_MAX_LINES)} of {len(lines)} lines, "
            f"{min(len(encoded), _DIFF_MAX_BYTES)} of {len(encoded)} bytes]"
        )

    return capped


def _dedup_path(root: Path, task_key: Any) -> Path:
    """Sibling of ``advisor._budget_path`` for this task's diff-hash dedup state."""
    return root / ".ll" / "advisor-budget" / f"{task_key.kind}-{task_key.value}.pre_done.json"


def _last_diff_sha(root: Path, task_key: Any) -> str | None:
    path = _dedup_path(root, task_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sha = data.get("last_diff_sha")
    return sha if isinstance(sha, str) else None


def _record_diff_sha(root: Path, task_key: Any, sha: str) -> None:
    path = _dedup_path(root, task_key)
    with acquire_lock(path.with_suffix(".lock")):
        atomic_write_json(path, {"last_diff_sha": sha})


def _format_feedback(verdict: Any) -> str:
    lines = [
        "[ll] pre_done advisor consult:",
        f"Recommendation: {verdict.recommendation}",
        f"Confidence: {verdict.confidence}",
    ]
    if verdict.risks:
        lines.append("Risks: " + "; ".join(verdict.risks))
    if verdict.dissent:
        lines.append(f"Dissent: {verdict.dissent}")
    return "\n".join(lines)


def handle(event: LLHookEvent) -> LLHookResult:
    """Auto-consult the advisor on the working diff, deduped per distinct diff state.

    Fail-soft throughout — any exception returns ``LLHookResult(exit_code=0)``
    so a broken consult never blocks the turn (FEAT-3118 AC #5).
    """
    try:
        if shutil.which("git") is None:
            return LLHookResult(exit_code=0)

        root = find_project_root(Path(event.cwd or os.getcwd()))
        if root is None or not (root / ".git").exists():
            return LLHookResult(exit_code=0)

        capped_diff = _capture_diff(root)
        if capped_diff is None:
            return LLHookResult(exit_code=0)

        from little_loops.advisor import consult_for_trigger, resolve_task_key
        from little_loops.config import BRConfig

        config = BRConfig(root)

        if event.session_id and not os.environ.get("CLAUDE_SESSION_ID"):
            os.environ["CLAUDE_SESSION_ID"] = event.session_id

        task_key = resolve_task_key()

        diff_sha = hashlib.sha256(capped_diff.encode("utf-8")).hexdigest()
        if diff_sha == _last_diff_sha(root, task_key):
            return LLHookResult(exit_code=0)

        if config.advisor.timeout_seconds > 190:
            logger.warning(
                "pre_done: advisor.timeout_seconds (%d) exceeds the Stop hook's 190s "
                "margin — skipping consult to avoid a host-killed hook that has "
                "already spent budget",
                config.advisor.timeout_seconds,
            )
            return LLHookResult(exit_code=0)

        outcome = consult_for_trigger(
            "pre_done",
            question=_QUESTION,
            context=capped_diff,
            config=config,
        )

        if outcome.verdict is not None:
            _record_diff_sha(root, task_key, diff_sha)
            return LLHookResult(exit_code=0, feedback=_format_feedback(outcome.verdict))

        if outcome.skipped_reason not in ("disabled", "trigger_not_allowed"):
            logger.warning(
                "pre_done: consult skipped: %s%s",
                outcome.skipped_reason,
                f" ({outcome.error})" if outcome.error else "",
            )
    except Exception:
        return LLHookResult(exit_code=0)

    return LLHookResult(exit_code=0)
