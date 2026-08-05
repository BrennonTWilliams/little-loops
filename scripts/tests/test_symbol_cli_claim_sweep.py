"""Repo-wide stale_symbol_ref/stale_cli_flag sweep (FEAT-3048), report-only.

Mirrors the FEAT-2850 sweep shape (test_prose_dep_sweep_gate.py): walks every
active issue in this repo's real ``.issues/`` directory and runs
``check_format_gaps()`` with real ``ref_index``/``symbol_index``/``cli_index``.

Deliberately **report-only** per FEAT-3048's Acceptance Criteria — the
Claim Grammar's false-positive-control measures are new and unmeasured
against the live backlog. This test does not assert zero gaps; it prints a
summary so a human can sample and measure precision, and only exercises the
code path end-to-end (catching crashes, not drift) until the precision bar
is met and the assertion is added.
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
        if gaps.stale_cli_flag:
            cli_hits[info.issue_id] = gaps.stale_cli_flag

    print(
        f"\n[FEAT-3048 report-only] stale_symbol_ref: {len(symbol_hits)}/{len(active_issues)} "
        f"issue(s); stale_cli_flag: {len(cli_hits)}/{len(active_issues)} issue(s)"
    )

    # Report-only: no assertion on gap counts (see module docstring). The
    # sweep itself must complete without raising.
    assert isinstance(symbol_hits, dict)
    assert isinstance(cli_hits, dict)
