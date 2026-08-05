"""Repo-wide stale_symbol_ref/stale_cli_flag sweep (FEAT-3048/BUG-3063).

Mirrors the FEAT-2850 sweep shape (test_prose_dep_sweep_gate.py): walks every
active issue in this repo's real ``.issues/`` directory and runs
``check_format_gaps()`` with real ``ref_index``/``symbol_index``/``cli_index``.

Was report-only under FEAT-3048 (measured baseline: 32/72 issues, 94 hits,
dominated by forward-looking-section and mis-attribution false positives).
BUG-3063's A1 (current-state section allowlist) + C (resolves-elsewhere
downgrade) fix cut that to a measured 2 stale_symbol_ref hits (2 issues) and
5 mislocated_symbol_ref hits (4 issues) on this repo's corpus as of
2026-08-05 (well under the § Acceptance Criteria 1 ceiling of 18) — this test
now pins a real ceiling instead of only asserting the sweep completes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.config.core import BRConfig
from little_loops.issue_parser import check_format_gaps, find_issues
from little_loops.issues.cli_surface import build_cli_surface_index
from little_loops.issues.symbol_claims import build_symbol_index
from little_loops.text_utils import build_ref_index

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.timeout(180)
def test_symbol_and_cli_flag_claim_sweep_report_only() -> None:
    config = BRConfig(_REPO_ROOT)
    ref_index = build_ref_index(config.project_root)
    symbol_index = build_symbol_index(config.project_root)
    cli_index = build_cli_surface_index()

    active_issues = find_issues(config)

    symbol_hits: dict[str, list[str]] = {}
    mislocated_hits: dict[str, list[str]] = {}
    cli_hits: dict[str, list[str]] = {}
    for info in active_issues:
        gaps = check_format_gaps(
            info.path,
            ref_index=ref_index,
            symbol_index=symbol_index,
            cli_index=cli_index,
        )
        if gaps.stale_symbol_ref:
            symbol_hits[info.issue_id] = gaps.stale_symbol_ref
        if gaps.mislocated_symbol_ref:
            mislocated_hits[info.issue_id] = gaps.mislocated_symbol_ref
        if gaps.stale_cli_flag:
            cli_hits[info.issue_id] = gaps.stale_cli_flag

    total_symbol_hits = sum(len(v) for v in symbol_hits.values()) + sum(
        len(v) for v in mislocated_hits.values()
    )
    print(
        f"\n[BUG-3063] stale_symbol_ref: {len(symbol_hits)}/{len(active_issues)} issue(s); "
        f"mislocated_symbol_ref: {len(mislocated_hits)}/{len(active_issues)} issue(s); "
        f"stale_cli_flag: {len(cli_hits)}/{len(active_issues)} issue(s)"
    )

    # BUG-3063 § Acceptance Criteria 1: combined stale_symbol_ref +
    # mislocated_symbol_ref hits must stay at or below the measured A1+C
    # ceiling (18) — the sweep no longer just asserts it completes without
    # raising, it pins a real regression ceiling. stale_cli_flag is a
    # separate gap class (FEAT-3048) not touched by this fix and stays
    # unasserted here.
    assert total_symbol_hits <= 18, (
        f"stale_symbol_ref + mislocated_symbol_ref hit count regressed past the "
        f"BUG-3063 A1+C ceiling: {total_symbol_hits} > 18 "
        f"(stale={symbol_hits}, mislocated={mislocated_hits})"
    )
