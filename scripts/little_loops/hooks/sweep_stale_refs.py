"""SessionEnd hook handler: sweep stale cross-issue status references — FEAT-1680.

Fires at the end of every Claude Code session. Collects all issue IDs with
``status: done``, then scans open issue files for prose that still asserts
those IDs are ``open``, ``in_progress``, or active blockers.  Findings are
reported via ``LLHookResult.feedback`` (stderr).  When ``hooks.stale_ref_fix``
is ``"auto"`` in ``ll-config.json``, stale phrases are rewritten in-place.

The handler exits 0 in all cases — it is advisory only and must never block
session end.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from little_loops.config.core import BRConfig, resolve_config_path
from little_loops.file_utils import atomic_write
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.issue_parser import find_issues
from little_loops.text_utils import _CODE_FENCE

# Matches any issue ID token (e.g. FEAT-1112, ENH-42, BUG-007, EPIC-3)
_ISSUE_ID_RE = re.compile(r"\b(ENH|BUG|FEAT|EPIC)-(\d+)\b")

# Stale-status phrase patterns — matched *after* the issue ID on the same line
_STALE_STATUS_RE = re.compile(
    r"\bis\s+(?:still\s+)?(open|in_progress|active)\b",
    re.IGNORECASE,
)

# Blocked-by phrase — the issue ID appears after "blocked by"
_BLOCKED_BY_RE = re.compile(r"\bblocked\s+by\b", re.IGNORECASE)


def _in_fence(pos_start: int, pos_end: int, fence_spans: list[tuple[int, int]]) -> bool:
    """Return True if the span [pos_start, pos_end) falls inside a code fence."""
    return any(fs <= pos_start and pos_end <= fe for fs, fe in fence_spans)


def _scan_file(
    path: Path,
    done_ids: set[str],
) -> list[tuple[int, str, str]]:
    """Scan *path* for stale references to any ID in *done_ids*.

    Returns a list of ``(lineno, issue_id, snippet)`` tuples (1-based lineno).
    Lines inside code fences are skipped.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

    findings: list[tuple[int, str, str]] = []
    offset = 0
    for lineno, line in enumerate(content.splitlines(), start=1):
        line_start = offset
        line_end = offset + len(line)
        offset = line_end + 1  # +1 for the newline

        if _in_fence(line_start, line_end, fence_spans):
            continue

        for m in _ISSUE_ID_RE.finditer(line):
            issue_id = m.group(0)
            if issue_id not in done_ids:
                continue

            # Check for stale-status phrase anywhere on the line
            if _STALE_STATUS_RE.search(line):
                snippet = line.strip()
                findings.append((lineno, issue_id, snippet))
                break  # one finding per line is enough

            # Check for "blocked by <ID>" where this ID is done
            # Pattern: "blocked by" appears before the ID on the line
            pre_id = line[: m.start()]
            if _BLOCKED_BY_RE.search(pre_id):
                snippet = line.strip()
                findings.append((lineno, issue_id, snippet))
                break

    return findings


def _auto_fix_file(path: Path, done_ids: set[str]) -> bool:
    """Rewrite stale status phrases in *path* for any done ID mentioned.

    Uses :func:`atomic_write` for safe in-place replacement.  Returns True if
    the file was modified.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

    new_lines: list[str] = []
    modified = False
    offset = 0
    for line in content.splitlines(keepends=True):
        line_start = offset
        line_end = offset + len(line)
        offset = line_end

        if _in_fence(line_start, line_end, fence_spans):
            new_lines.append(line)
            continue

        # Only rewrite lines that mention a done ID
        has_done_ref = any(m.group(0) in done_ids for m in _ISSUE_ID_RE.finditer(line))
        if has_done_ref and _STALE_STATUS_RE.search(line):
            new_line = _STALE_STATUS_RE.sub("is done", line)
            new_lines.append(new_line)
            modified = True
        else:
            new_lines.append(line)

    if modified:
        atomic_write(path, "".join(new_lines))
    return modified


def handle(event: LLHookEvent) -> LLHookResult:
    """Sweep open issue files for stale references to done issue IDs.

    Reads ``hooks.stale_ref_fix`` from ``ll-config.json`` (default
    ``"report"``).  When ``"auto"``, stale phrases are rewritten in-place.
    Always returns ``LLHookResult(exit_code=0)`` — findings are advisory and
    must never block session end.
    """
    try:
        payload = event.payload or {}
        raw_cwd = payload.get("cwd") or (event.cwd or "")
        cwd = Path(raw_cwd) if raw_cwd else Path.cwd()

        # Load raw hooks config to read stale_ref_fix mode
        config_path = resolve_config_path(cwd)
        fix_mode = "report"
        if config_path is not None:
            try:
                raw_config = json.loads(config_path.read_text(encoding="utf-8"))
                raw_hooks = raw_config.get("hooks", {})
                if isinstance(raw_hooks, dict):
                    fix_mode = raw_hooks.get("stale_ref_fix", "report")
            except (OSError, json.JSONDecodeError):
                pass

        # Build BRConfig for find_issues()
        config = BRConfig(project_root=cwd)

        # Collect done IDs
        done_issues = find_issues(config, status_filter={"done"})
        done_ids: set[str] = {i.issue_id for i in done_issues}

        if not done_ids:
            return LLHookResult(exit_code=0)

        # Collect open issues (default call skips done/cancelled/deferred)
        open_issues = find_issues(config)

        all_findings: list[tuple[Path, int, str, str]] = []

        for issue in open_issues:
            path: Path = issue.path
            if not path.is_file():
                continue

            if fix_mode == "auto":
                _auto_fix_file(path, done_ids)

            findings = _scan_file(path, done_ids)
            for lineno, issue_id, snippet in findings:
                all_findings.append((path, lineno, issue_id, snippet))

        if not all_findings:
            return LLHookResult(exit_code=0)

        lines = [f"[ll] {len(all_findings)} stale cross-issue reference(s) found:"]
        for path, lineno, issue_id, snippet in all_findings:
            lines.append(f"  {path}:{lineno}: [{issue_id}] {snippet}")
        feedback = "\n".join(lines)

        return LLHookResult(exit_code=0, feedback=feedback)

    except Exception:
        return LLHookResult(exit_code=0)
