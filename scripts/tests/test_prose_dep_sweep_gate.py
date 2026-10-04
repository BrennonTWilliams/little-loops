"""Repo-wide prose-dependency drift gate (FEAT-2850).

Sweeps every active issue in this repo's real ``.issues/`` directory via
``format-check --all`` and fails the suite if any issue's prose claims a
dependency missing from its ``blocked_by``/``depends_on`` frontmatter, or
still names a done/cancelled issue. This is the local-pytest-suite gate the
project's no-hosted-CI policy requires (.claude/CLAUDE.md § Testing & CI
Policy) — no GitHub Actions workflow is added.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.config.core import BRConfig
from little_loops.issue_parser import check_format_gaps, find_issues
from little_loops.issue_progress import _ALL_STATUSES
from little_loops.issue_template import resolve_templates_dir
from tests.head_corpus import corpus_gate_at_head, head_issue_blobs, head_issue_infos

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _sweep_inputs(config: BRConfig) -> tuple[dict[str, str], list[tuple[str, Path]]]:
    """Return ``(issue_statuses, [(issue_id, path)] of active issues)``.

    Under ``LL_CORPUS_GATE_AT_HEAD`` (set by ``code-run-gate``, ENH-3697) the corpus is
    read from committed ``HEAD`` blobs so another session's uncommitted ``.issues/``
    edits cannot fail the gate. Falls back to the working tree when there is no HEAD.
    """
    blobs = head_issue_blobs(config) if corpus_gate_at_head() else None
    if blobs is not None:
        pairs = head_issue_infos(config, blobs)
        statuses = {info.issue_id: info.status for info, _ in pairs}
        closed = ("done", "cancelled", "deferred")
        return statuses, [
            (info.issue_id, path)  # type: ignore[misc]
            for info, path in pairs
            if info.status not in closed
        ]

    all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))
    # Only sweep active issues; a closed issue's stale prose isn't gated.
    return (
        {info.issue_id: info.status for info in all_issues},
        [(info.issue_id, info.path) for info in find_issues(config)],
    )


def test_no_prose_dependency_drift_in_repo() -> None:
    config = BRConfig(_REPO_ROOT)
    issue_statuses, active = _sweep_inputs(config)
    templates_dir = resolve_templates_dir(config)

    drifted: dict[str, list[str]] = {}
    for issue_id, path in active:
        gaps = check_format_gaps(
            path,
            templates_dir=templates_dir,
            issue_statuses=issue_statuses,
        )
        entries = gaps.prose_dep_drift + gaps.stale_prose_dep
        if entries:
            drifted[issue_id] = entries

    assert not drifted, f"prose-dependency drift found: {drifted}"
