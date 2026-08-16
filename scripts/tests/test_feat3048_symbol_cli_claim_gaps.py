"""check_format_gaps() integration tests for stale_symbol_ref/stale_cli_flag (FEAT-3048)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from little_loops.issue_parser import check_format_gaps
from little_loops.issues.cli_surface import CliSurfaceIndex
from little_loops.issues.symbol_claims import build_symbol_index
from little_loops.text_utils import RefIndex

_SCOPE_TEMPLATE = """---
id: FEAT-9010
title: Sample
type: FEAT
priority: P2
status: open
testable: true
---

# FEAT-9010: Sample

## Summary

{summary}

## Current Behavior

{current_behavior}

## Program Design

{program_design}

### Files to Modify

{files_to_modify}

## Implementation Steps

{implementation_steps}

## Rollout Notes

{rollout_notes}

## Acceptance Criteria

- [ ] n/a

## Impact

n/a
"""

_CLAIM = "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`."


def _write_scoped_issue(tmp_path: Path, **sections: str) -> Path:
    values = {
        "summary": "n/a",
        "current_behavior": "n/a",
        "program_design": "n/a",
        "files_to_modify": "n/a",
        "implementation_steps": "n/a",
        "rollout_notes": "n/a",
    }
    values.update(sections)
    issues_dir = tmp_path / ".issues" / "features"
    issues_dir.mkdir(parents=True, exist_ok=True)
    path = issues_dir / "P2-FEAT-9010-scoped.md"
    path.write_text(_SCOPE_TEMPLATE.format(**values))
    return path


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


class TestStaleSymbolRefScoping:
    """A1 — current-state allowlist scoping (BUG-3063). Positive control: the
    claim still fires inside Summary/Current Behavior. Negative control: the
    same claim inside a forward-looking section, including an arbitrary
    unlisted heading, must not fire -- that last case is what proves the
    scoping is an allowlist, not a denylist."""

    def test_fires_in_summary(self, tmp_path: Path, repo: Path, ref_index: RefIndex) -> None:
        path = _write_scoped_issue(tmp_path, summary=_CLAIM)
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert any("does_not_exist_symbol" in entry for entry in gaps.stale_symbol_ref)

    def test_fires_in_current_behavior(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_scoped_issue(tmp_path, current_behavior=_CLAIM)
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert any("does_not_exist_symbol" in entry for entry in gaps.stale_symbol_ref)

    def test_no_gap_in_program_design(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_scoped_issue(tmp_path, program_design=_CLAIM)
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []
        assert gaps.mislocated_symbol_ref == []

    def test_no_gap_in_files_to_modify(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_scoped_issue(tmp_path, files_to_modify=_CLAIM)
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []

    def test_no_gap_in_implementation_steps(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_scoped_issue(tmp_path, implementation_steps=_CLAIM)
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []

    def test_no_gap_in_arbitrary_unlisted_heading(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        """Proves allowlist-not-denylist: `## Rollout Notes` names no forward-
        looking keyword and is still out of scope because it's simply absent
        from the allowlist."""
        path = _write_scoped_issue(tmp_path, rollout_notes=_CLAIM)
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []


class TestMislocatedSymbolRef:
    """C — resolves-elsewhere downgrade (BUG-3063)."""

    def test_mislocated_when_symbol_resolves_in_another_tracked_file(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_issue(
            tmp_path,
            "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`.",
        )
        symbol_index = build_symbol_index(repo)
        symbol_index._reverse = {
            "does_not_exist_symbol": frozenset({"scripts/little_loops/issues/other.py"})
        }
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []
        assert any("does_not_exist_symbol" in entry for entry in gaps.mislocated_symbol_ref)

    def test_stale_when_symbol_resolves_nowhere(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_issue(
            tmp_path,
            "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`.",
        )
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert any("does_not_exist_symbol" in entry for entry in gaps.stale_symbol_ref)
        assert gaps.mislocated_symbol_ref == []


class TestBug3194SuppressionNoReroute:
    """BUG-3194 Finding 1: suppressed claims must disappear entirely, not
    reroute from mislocated_symbol_ref into stale_symbol_ref."""

    def test_bare_form_floor_suppression_hits_neither_gap_key(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_issue(
            tmp_path,
            "Reuse `enabled` in `scripts/little_loops/issues/prose_deps.py`.",
        )
        symbol_index = build_symbol_index(repo)
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []
        assert gaps.mislocated_symbol_ref == []

    def test_breadth_cap_suppression_hits_neither_gap_key(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        path = _write_issue(
            tmp_path,
            "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`.",
        )
        symbol_index = build_symbol_index(repo)
        symbol_index._reverse = {
            "does_not_exist_symbol": frozenset(f"file_{n}.py" for n in range(9))
        }
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []
        assert gaps.mislocated_symbol_ref == []

    def test_true_positive_still_fires_after_breadth_cap(
        self, tmp_path: Path, repo: Path, ref_index: RefIndex
    ) -> None:
        """A genuine mis-attribution resolving in a handful of files (below the
        N=8 cap) must still fire -- the cap must not blanket-suppress."""
        path = _write_issue(
            tmp_path,
            "Reuse `does_not_exist_symbol` in `scripts/little_loops/issues/prose_deps.py`.",
        )
        symbol_index = build_symbol_index(repo)
        symbol_index._reverse = {
            "does_not_exist_symbol": frozenset({"scripts/little_loops/issues/other.py"})
        }
        gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []
        assert any("does_not_exist_symbol" in entry for entry in gaps.mislocated_symbol_ref)


class TestBug3201IndexedClaimClasses:
    """BUG-3201 — the two claim classes `_extract_symbols` could not see, driven
    end-to-end through check_format_gaps rather than the resolver alone."""

    @pytest.fixture
    def bug3201_repo(self, tmp_path: Path) -> Path:
        store = tmp_path / "scripts" / "little_loops" / "session_store"
        store.mkdir(parents=True)
        (store / "schema.py").write_text(
            '_MIGRATIONS = """\n'
            "    CREATE TABLE IF NOT EXISTS tool_events (id INTEGER PRIMARY KEY);\n"
            '"""\n'
        )
        cli = tmp_path / "scripts" / "little_loops" / "cli"
        cli.mkdir(parents=True)
        (cli / "adapt.py").write_text(
            "def cmd_adapt():\n"
            "    from little_loops.skill_expander import _find_plugin_root as _fpr\n"
            "    return _fpr()\n"
        )
        (cli / "logs.py").write_text("from datetime import time as dt_time\n")
        return tmp_path

    @pytest.fixture
    def bug3201_ref_index(self) -> RefIndex:
        return RefIndex(
            by_basename={
                "schema.py": ["scripts/little_loops/session_store/schema.py"],
                "adapt.py": ["scripts/little_loops/cli/adapt.py"],
                "logs.py": ["scripts/little_loops/cli/logs.py"],
            }
        )

    def test_sql_table_claim_in_schema_file_is_not_a_gap(
        self, tmp_path: Path, bug3201_repo: Path, bug3201_ref_index: RefIndex
    ) -> None:
        path = _write_issue(
            tmp_path,
            "The `tool_events` table in "
            "`scripts/little_loops/session_store/schema.py` needs a new column.",
        )
        gaps = check_format_gaps(
            path,
            ref_index=bug3201_ref_index,
            symbol_index=build_symbol_index(bug3201_repo),
        )
        assert gaps.stale_symbol_ref == []
        assert gaps.mislocated_symbol_ref == []

    def test_sql_table_claimed_against_wrong_file_is_mislocated(
        self, tmp_path: Path, bug3201_repo: Path, bug3201_ref_index: RefIndex
    ) -> None:
        """SQL names are repo-unique and DO enter the reverse index, so a
        wrong-file claim is a mis-attribution, not a stale claim."""
        path = _write_issue(
            tmp_path,
            "The `tool_events` table in `scripts/little_loops/cli/logs.py` needs a new column.",
        )
        symbol_index = build_symbol_index(bug3201_repo)
        symbol_index._reverse = {
            "tool_events": frozenset({"scripts/little_loops/session_store/schema.py"})
        }
        gaps = check_format_gaps(path, ref_index=bug3201_ref_index, symbol_index=symbol_index)
        assert gaps.stale_symbol_ref == []
        assert any("tool_events" in entry for entry in gaps.mislocated_symbol_ref)

    def test_aliased_import_claim_is_not_a_gap(
        self, tmp_path: Path, bug3201_repo: Path, bug3201_ref_index: RefIndex
    ) -> None:
        path = _write_issue(
            tmp_path,
            "The `_fpr` helper in `scripts/little_loops/cli/adapt.py` resolves the plugin root.",
        )
        gaps = check_format_gaps(
            path,
            ref_index=bug3201_ref_index,
            symbol_index=build_symbol_index(bug3201_repo),
        )
        assert gaps.stale_symbol_ref == []
        assert gaps.mislocated_symbol_ref == []

    def test_explicit_form_aliased_import_claim_is_not_a_gap(
        self, tmp_path: Path, bug3201_repo: Path, bug3201_ref_index: RefIndex
    ) -> None:
        path = _write_issue(
            tmp_path, "See `scripts/little_loops/cli/logs.py:dt_time` for the parsing entry point."
        )
        gaps = check_format_gaps(
            path,
            ref_index=bug3201_ref_index,
            symbol_index=build_symbol_index(bug3201_repo),
        )
        assert gaps.stale_symbol_ref == []
        assert gaps.mislocated_symbol_ref == []
