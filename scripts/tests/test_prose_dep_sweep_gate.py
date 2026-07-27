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

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_prose_dependency_drift_in_repo() -> None:
    config = BRConfig(_REPO_ROOT)
    all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))
    issue_statuses = {info.issue_id: info.status for info in all_issues}
    templates_dir = resolve_templates_dir(config)

    # Only sweep active issues; a closed issue's stale prose isn't gated.
    active_issues = find_issues(config)

    drifted: dict[str, list[str]] = {}
    for info in active_issues:
        gaps = check_format_gaps(
            info.path,
            templates_dir=templates_dir,
            issue_statuses=issue_statuses,
        )
        entries = gaps.prose_dep_drift + gaps.stale_prose_dep
        if entries:
            drifted[info.issue_id] = entries

    assert not drifted, f"prose-dependency drift found: {drifted}"
