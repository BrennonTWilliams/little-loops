"""ENH-3430 spike: per-host ``list_workspaces`` union + cwd-dedupe.

Proves the algorithm ENH-3430's Proposed Solution step 2 describes. The
issue's own Codebase Research Findings flag it as unprecedented: "No shared
'dedupe a list of Path's across hosts' utility exists in the codebase ...
this step's mechanism is genuinely new code with no confirming precedent
anywhere." This module drives the real ``list_workspaces``/``detect_sessions``/
``iter_events`` seam (``session_store/sessions.py``) and the real
``_is_ll_relevant`` filter (``cli/logs.py``) against synthetic fixture homes
to retire that risk. Nothing here is faked or reimplemented from the
production seam; only the on-disk fixture data is synthetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from little_loops.cli.logs import _is_ll_relevant
from little_loops.session_store.sessions import (
    SessionHandle,
    detect_sessions,
    iter_events,
    list_workspaces,
)


def _workspace_has_ll_activity(handles: list[SessionHandle]) -> bool:
    """Early-exit walk over parsed events, mirroring ``_has_ll_activity``'s intent."""
    for handle in handles:
        if handle.is_agent:
            continue
        for event in iter_events(handle):
            if _is_ll_relevant(event.payload):
                return True
    return False


def union_workspaces(
    hosts: Sequence[str],
    *,
    home: Path,
    detect_sessions_calls: list[tuple[Path, str]] | None = None,
) -> list[Path]:
    """Union of ll-active workspaces across *hosts*, deduped on resolved cwd.

    Iterates *hosts* one at a time and calls ``list_workspaces(host,
    home=home)`` per host -- never ``detect_sessions(ws, None)`` per
    workspace, which would probe every registered host for every candidate
    workspace and multiply the discovery cost (ENH-3430 Impact -> Risk).
    Dedupes on ``str(Path.resolve())`` so a workspace recorded under two
    hosts with different spellings (a resolved vs. as-recorded path)
    collapses to one entry, keeping the first-seen host's recorded spelling.
    The ll-activity filter is re-applied per surviving workspace so the
    union does not widen beyond ``_has_ll_activity``'s existing scope.

    *detect_sessions_calls*, when given, records every ``(workspace, host)``
    pair this function passes to ``detect_sessions`` -- the regression-guard
    test's spy.
    """
    seen: dict[str, Path] = {}
    for host in hosts:
        for workspace in list_workspaces(host, home=home):
            key = str(workspace.resolve())
            if key in seen:
                continue
            handles = detect_sessions(workspace, host, home=home)
            if detect_sessions_calls is not None:
                detect_sessions_calls.append((workspace, host))
            if not _workspace_has_ll_activity(handles):
                continue
            seen[key] = workspace
    return list(seen.values())
