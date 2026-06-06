"""Tests for wire-issue static coupling layer (FEAT-1736).

Covers: load_coupling_entries() behavior as consumed by wire-issue Phase 3.5:
- Glob matching changed files against coupling if_changed patterns
- Archetype filtering for bundle pre-load
- Tier classification for hard/soft/fyi partitioning
- Graceful skip when decisions.yaml is absent
- Graceful skip when no entries match
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.decisions import (
    CouplingEntry,
    RuleEntry,
    load_coupling_entries,
    save_decisions,
)


@pytest.fixture
def decisions_path(tmp_path: Path) -> Path:
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    return ll_dir / "decisions.yaml"


@pytest.fixture
def cli_command_coupling() -> CouplingEntry:
    return CouplingEntry(
        id="COUPLING-001",
        category="wiring",
        rationale="New CLI commands must be registered in plugin.json",
        if_changed="commands/*.md",
        then_check=[".claude-plugin/plugin.json", ".claude/CLAUDE.md", "skills/*/SKILL.md"],
        tier="hard",
        archetype="add-cli-command",
    )


@pytest.fixture
def config_key_coupling() -> CouplingEntry:
    return CouplingEntry(
        id="COUPLING-002",
        category="wiring",
        rationale="Config schema changes must be reflected in API reference",
        if_changed="config-schema.json",
        then_check=["docs/reference/API.md", ".claude/CLAUDE.md"],
        tier="hard",
        archetype="add-config-key",
    )


@pytest.fixture
def event_coupling() -> CouplingEntry:
    return CouplingEntry(
        id="COUPLING-003",
        category="wiring",
        rationale="New LLEvent subtypes require schema regeneration",
        if_changed="scripts/little_loops/events/**",
        then_check=["docs/reference/schemas/", "scripts/little_loops/cli/ll_generate_schemas.py"],
        tier="hard",
    )


@pytest.fixture
def soft_coupling() -> CouplingEntry:
    return CouplingEntry(
        id="COUPLING-004",
        category="wiring",
        rationale="Script changes should update API docs",
        if_changed="scripts/**",
        then_check=["docs/reference/API.md"],
        tier="soft",
    )


@pytest.fixture
def fyi_coupling() -> CouplingEntry:
    return CouplingEntry(
        id="COUPLING-005",
        category="wiring",
        rationale="All changes should consider CHANGELOG",
        if_changed="**",
        then_check=["CHANGELOG.md"],
        tier="fyi",
    )


# =============================================================================
# No-file fallback
# =============================================================================


class TestStaticLayerFallback:
    """Graceful degradation when decisions.yaml is absent."""

    def test_absent_file_returns_empty(self, tmp_path: Path) -> None:
        absent = tmp_path / "nonexistent.yaml"
        result = load_coupling_entries(absent, changed_globs=["commands/help.md"])
        assert result == []

    def test_absent_file_no_globs_returns_empty(self, tmp_path: Path) -> None:
        absent = tmp_path / "nonexistent.yaml"
        assert load_coupling_entries(absent) == []

    def test_no_coupling_entries_returns_empty(self, decisions_path: Path, tmp_path: Path) -> None:
        rule = RuleEntry(id="RULE-001", rule="Some rule", enforcement="required")
        save_decisions([rule], decisions_path)
        result = load_coupling_entries(decisions_path, changed_globs=["commands/help.md"])
        assert result == []


# =============================================================================
# Glob matching
# =============================================================================


class TestStaticLayerGlobMatching:
    """load_coupling_entries() filters by if_changed glob against changed files."""

    def test_matches_wildcard_pattern(
        self, decisions_path: Path, cli_command_coupling: CouplingEntry
    ) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        matched = load_coupling_entries(decisions_path, changed_globs=["commands/help.md"])
        assert len(matched) == 1
        assert matched[0].id == "COUPLING-001"

    def test_no_match_different_path(
        self, decisions_path: Path, cli_command_coupling: CouplingEntry
    ) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        matched = load_coupling_entries(decisions_path, changed_globs=["scripts/foo.py"])
        assert len(matched) == 0

    def test_any_changed_file_triggers_match(
        self, decisions_path: Path, cli_command_coupling: CouplingEntry
    ) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        # Multiple changed files — one matches
        matched = load_coupling_entries(
            decisions_path,
            changed_globs=["scripts/foo.py", "commands/new-cmd.md"],
        )
        assert len(matched) == 1

    def test_multiple_matching_entries(
        self,
        decisions_path: Path,
        cli_command_coupling: CouplingEntry,
        soft_coupling: CouplingEntry,
    ) -> None:
        save_decisions([cli_command_coupling, soft_coupling], decisions_path)
        # commands/help.md matches both "commands/*.md" and "scripts/**"? No — only commands/*.md
        # scripts/foo.py matches "scripts/**" only
        matched = load_coupling_entries(
            decisions_path,
            changed_globs=["commands/help.md", "scripts/foo.py"],
        )
        assert len(matched) == 2

    def test_no_changed_globs_returns_all_coupling(
        self,
        decisions_path: Path,
        cli_command_coupling: CouplingEntry,
        soft_coupling: CouplingEntry,
    ) -> None:
        save_decisions([cli_command_coupling, soft_coupling], decisions_path)
        # No glob filter — returns all coupling entries
        all_entries = load_coupling_entries(decisions_path)
        assert len(all_entries) == 2


# =============================================================================
# Archetype filtering
# =============================================================================


class TestStaticLayerArchetypeFilter:
    """load_coupling_entries() --archetype filter selects bundle."""

    def test_archetype_filter_exact_match(
        self,
        decisions_path: Path,
        cli_command_coupling: CouplingEntry,
        config_key_coupling: CouplingEntry,
    ) -> None:
        save_decisions([cli_command_coupling, config_key_coupling], decisions_path)
        entries = load_coupling_entries(decisions_path, archetype="add-cli-command")
        assert len(entries) == 1
        assert entries[0].id == "COUPLING-001"

    def test_archetype_filter_no_match(
        self, decisions_path: Path, cli_command_coupling: CouplingEntry
    ) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        entries = load_coupling_entries(decisions_path, archetype="add-event-type")
        assert len(entries) == 0

    def test_archetype_and_glob_combined(
        self,
        decisions_path: Path,
        cli_command_coupling: CouplingEntry,
    ) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        # archetype matches, glob also matches
        matched = load_coupling_entries(
            decisions_path,
            changed_globs=["commands/new-cmd.md"],
            archetype="add-cli-command",
        )
        assert len(matched) == 1

    def test_archetype_matches_but_glob_does_not(
        self,
        decisions_path: Path,
        cli_command_coupling: CouplingEntry,
    ) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        # archetype matches, but no changed file matches if_changed
        no_match = load_coupling_entries(
            decisions_path,
            changed_globs=["scripts/foo.py"],
            archetype="add-cli-command",
        )
        assert len(no_match) == 0

    def test_no_archetype_on_entry_excluded(
        self,
        decisions_path: Path,
        event_coupling: CouplingEntry,  # no archetype set
    ) -> None:
        save_decisions([event_coupling], decisions_path)
        entries = load_coupling_entries(decisions_path, archetype="add-cli-command")
        assert len(entries) == 0


# =============================================================================
# Tier classification
# =============================================================================


class TestStaticLayerTierClassification:
    """Tier values are preserved for hard/soft/fyi partitioning in wire-issue."""

    def test_hard_tier(self, decisions_path: Path, cli_command_coupling: CouplingEntry) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        entries = load_coupling_entries(decisions_path, changed_globs=["commands/help.md"])
        assert entries[0].tier == "hard"

    def test_soft_tier(self, decisions_path: Path, soft_coupling: CouplingEntry) -> None:
        save_decisions([soft_coupling], decisions_path)
        entries = load_coupling_entries(decisions_path, changed_globs=["scripts/foo.py"])
        assert entries[0].tier == "soft"

    def test_fyi_tier(self, decisions_path: Path, fyi_coupling: CouplingEntry) -> None:
        save_decisions([fyi_coupling], decisions_path)
        entries = load_coupling_entries(decisions_path, changed_globs=["anything.md"])
        assert entries[0].tier == "fyi"

    def test_partition_by_tier(
        self,
        decisions_path: Path,
        cli_command_coupling: CouplingEntry,
        soft_coupling: CouplingEntry,
        fyi_coupling: CouplingEntry,
    ) -> None:
        save_decisions([cli_command_coupling, soft_coupling, fyi_coupling], decisions_path)
        entries = load_coupling_entries(
            decisions_path,
            changed_globs=["commands/help.md", "scripts/foo.py", "README.md"],
        )
        hard = [e for e in entries if e.tier == "hard"]
        soft = [e for e in entries if e.tier == "soft"]
        fyi = [e for e in entries if e.tier == "fyi"]
        assert len(hard) >= 1
        assert len(soft) >= 1
        assert len(fyi) >= 1

    def test_then_check_targets_preserved(
        self, decisions_path: Path, cli_command_coupling: CouplingEntry
    ) -> None:
        save_decisions([cli_command_coupling], decisions_path)
        entries = load_coupling_entries(decisions_path, changed_globs=["commands/new-cmd.md"])
        assert ".claude-plugin/plugin.json" in entries[0].then_check
        assert ".claude/CLAUDE.md" in entries[0].then_check
