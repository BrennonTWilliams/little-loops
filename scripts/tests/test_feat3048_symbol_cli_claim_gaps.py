"""check_format_gaps() integration tests for stale_symbol_ref/stale_cli_flag (FEAT-3048)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from little_loops.issue_parser import check_format_gaps
from little_loops.issues.cli_surface import CliSurfaceIndex
from little_loops.issues.symbol_claims import build_symbol_index
from little_loops.text_utils import RefIndex

_TEMPLATE = """---
id: FEAT-9001
title: Sample
type: FEAT
priority: P2
status: open
testable: true
---

# FEAT-9001: Sample

## Summary

{body}

## Current Behavior

n/a

## Expected Behavior

n/a

## Proposed Solution

n/a

## Acceptance Criteria

- [ ] n/a

## Impact

n/a
"""


def _write_issue(tmp_path: Path, body: str) -> Path:
    issues_dir = tmp_path / ".issues" / "features"
    issues_dir.mkdir(parents=True)
    path = issues_dir / "P2-FEAT-9001-sample.md"
    path.write_text(_TEMPLATE.format(body=body))
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    src = tmp_path / "scripts" / "little_loops" / "issues"
    src.mkdir(parents=True)
    (src / "prose_deps.py").write_text("def extract_prose_deps(body):\n    pass\n")
    return tmp_path


@pytest.fixture
def ref_index() -> RefIndex:
    return RefIndex(by_basename={"prose_deps.py": ["scripts/little_loops/issues/prose_deps.py"]})


@pytest.fixture
def cli_index() -> CliSurfaceIndex:
    return CliSurfaceIndex(
        surface={"ll-issues": {"link": {"--blocked-by", "--depends-on", "--relates-to"}}}
    )


def test_stale_symbol_ref_gap_populated(tmp_path: Path, repo: Path, ref_index: RefIndex) -> None:
    path = _write_issue(
        tmp_path,
        "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`.",
    )
    symbol_index = build_symbol_index(repo)
    gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
    assert any("does_not_exist_symbol" in entry for entry in gaps.stale_symbol_ref)
    assert gaps.has_gaps


def test_valid_symbol_ref_no_gap(tmp_path: Path, repo: Path, ref_index: RefIndex) -> None:
    path = _write_issue(
        tmp_path,
        "Reuse `extract_prose_deps` in `scripts/little_loops/issues/prose_deps.py`.",
    )
    symbol_index = build_symbol_index(repo)
    gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
    assert gaps.stale_symbol_ref == []


def test_symbol_ref_fails_open_without_indexes(tmp_path: Path) -> None:
    path = _write_issue(
        tmp_path,
        "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`.",
    )
    gaps = check_format_gaps(path)
    assert gaps.stale_symbol_ref == []


def test_stale_cli_flag_gap_populated_feat_2942_regression(
    tmp_path: Path, cli_index: CliSurfaceIndex
) -> None:
    """Reproduces FEAT-2942's original claim text (commit 2225b414): `ll-issues
    link --parent` is exactly the flag `cli/issues/link.py` never defined.
    """
    path = _write_issue(
        tmp_path, "Reuse `ll-issues link --parent` / `frontmatter.update_frontmatter` for writes"
    )
    gaps = check_format_gaps(path, cli_index=cli_index)
    assert any("--parent" in entry for entry in gaps.stale_cli_flag)
    assert gaps.has_gaps


def test_valid_cli_flag_no_gap(tmp_path: Path, cli_index: CliSurfaceIndex) -> None:
    path = _write_issue(tmp_path, "Use `ll-issues link --blocked-by` to write the edge.")
    gaps = check_format_gaps(path, cli_index=cli_index)
    assert gaps.stale_cli_flag == []


def test_stale_cli_flag_fails_open_without_index(tmp_path: Path) -> None:
    path = _write_issue(tmp_path, "Reuse `ll-issues link --parent` for writes")
    gaps = check_format_gaps(path)
    assert gaps.stale_cli_flag == []


def test_check_format_gaps_spawns_no_subprocess(
    tmp_path: Path,
    repo: Path,
    ref_index: RefIndex,
    cli_index: CliSurfaceIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: both indexes are built by the caller and merely looked up here —
    check_format_gaps() itself must not shell out, even when both new
    kwargs are populated with real-shaped indexes.
    """
    path = _write_issue(
        tmp_path,
        "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`. "
        "Also see `ll-issues link --parent`.",
    )
    symbol_index = build_symbol_index(repo)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("check_format_gaps must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    gaps = check_format_gaps(
        path, ref_index=ref_index, symbol_index=symbol_index, cli_index=cli_index
    )
    assert gaps.stale_symbol_ref
    assert gaps.stale_cli_flag
