"""Tests for little_loops.decisions module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.decisions import (
    DecisionEntry,
    ExceptionEntry,
    RuleEntry,
    add_entry,
    list_entries,
    load_decisions,
    resolve_active,
    save_decisions,
    set_outcome,
)


@pytest.fixture
def decisions_path(temp_project_dir: Path) -> Path:
    ll_dir = temp_project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    return ll_dir / "decisions.yaml"


@pytest.fixture
def sample_rule() -> RuleEntry:
    return RuleEntry(
        id="NAMING-001",
        type="rule",
        timestamp="2026-06-03T00:00:00Z",
        category="naming",
        labels=["style"],
        rationale="Consistent naming aids readability",
        rule="All PRs must link an issue ID",
        enforcement="required",
    )


@pytest.fixture
def sample_decision() -> DecisionEntry:
    return DecisionEntry(
        id="WORKFLOW-001",
        type="decision",
        timestamp="2026-06-03T00:00:00Z",
        category="workflow",
        labels=["storage"],
        rationale="Simpler than SQLite for this use case",
        rule="Use YAML over SQLite for decisions log",
        scope="project",
    )


@pytest.fixture
def sample_exception() -> ExceptionEntry:
    return ExceptionEntry(
        id="NAMING-EX-001",
        type="exception",
        timestamp="2026-06-03T00:00:00Z",
        category="naming",
        labels=["legacy"],
        rationale="Legacy issue predates the naming rule",
        rule_ref="NAMING-001",
        issue="BUG-042",
    )


class TestLoadDecisions:
    """Tests for load_decisions()."""

    def test_returns_empty_list_when_file_absent(self, decisions_path: Path) -> None:
        assert load_decisions(decisions_path) == []

    def test_returns_empty_list_for_empty_file(self, decisions_path: Path) -> None:
        decisions_path.write_text("")
        assert load_decisions(decisions_path) == []

    def test_loads_rule_entry(self, decisions_path: Path, sample_rule: RuleEntry) -> None:
        save_decisions([sample_rule], decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 1
        assert loaded[0].id == "NAMING-001"
        assert isinstance(loaded[0], RuleEntry)

    def test_loads_decision_entry(self, decisions_path: Path, sample_decision: DecisionEntry) -> None:
        save_decisions([sample_decision], decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 1
        assert isinstance(loaded[0], DecisionEntry)

    def test_loads_exception_entry(self, decisions_path: Path, sample_exception: ExceptionEntry) -> None:
        save_decisions([sample_exception], decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 1
        assert isinstance(loaded[0], ExceptionEntry)

    def test_loads_mixed_entries(
        self,
        decisions_path: Path,
        sample_rule: RuleEntry,
        sample_decision: DecisionEntry,
        sample_exception: ExceptionEntry,
    ) -> None:
        save_decisions([sample_rule, sample_decision, sample_exception], decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 3


class TestSaveDecisions:
    """Tests for save_decisions()."""

    def test_creates_parent_dir(self, temp_project_dir: Path) -> None:
        nested_path = temp_project_dir / ".ll" / "nested" / "decisions.yaml"
        rule = RuleEntry(id="TEST-001", rule="Test rule")
        save_decisions([rule], nested_path)
        assert nested_path.exists()

    def test_writes_valid_yaml(self, decisions_path: Path, sample_rule: RuleEntry) -> None:
        save_decisions([sample_rule], decisions_path)
        content = decisions_path.read_text()
        data = yaml.safe_load(content)
        assert isinstance(data, list)
        assert data[0]["id"] == "NAMING-001"

    def test_round_trip_preserves_fields(self, decisions_path: Path, sample_rule: RuleEntry) -> None:
        save_decisions([sample_rule], decisions_path)
        loaded = load_decisions(decisions_path)
        assert loaded[0].id == sample_rule.id
        assert loaded[0].enforcement == sample_rule.enforcement
        assert loaded[0].labels == sample_rule.labels


class TestAddEntry:
    """Tests for add_entry()."""

    def test_adds_to_empty_log(self, decisions_path: Path, sample_rule: RuleEntry) -> None:
        add_entry(sample_rule, decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 1
        assert loaded[0].id == "NAMING-001"

    def test_appends_to_existing(
        self, decisions_path: Path, sample_rule: RuleEntry, sample_decision: DecisionEntry
    ) -> None:
        add_entry(sample_rule, decisions_path)
        add_entry(sample_decision, decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 2


class TestListEntries:
    """Tests for list_entries()."""

    def test_returns_all_without_filters(
        self,
        decisions_path: Path,
        sample_rule: RuleEntry,
        sample_decision: DecisionEntry,
        sample_exception: ExceptionEntry,
    ) -> None:
        save_decisions([sample_rule, sample_decision, sample_exception], decisions_path)
        result = list_entries(decisions_path)
        assert len(result) == 3

    def test_filter_by_type(
        self, decisions_path: Path, sample_rule: RuleEntry, sample_decision: DecisionEntry
    ) -> None:
        save_decisions([sample_rule, sample_decision], decisions_path)
        result = list_entries(decisions_path, type="rule")
        assert len(result) == 1
        assert result[0].id == "NAMING-001"

    def test_filter_by_category(
        self, decisions_path: Path, sample_rule: RuleEntry, sample_decision: DecisionEntry
    ) -> None:
        save_decisions([sample_rule, sample_decision], decisions_path)
        result = list_entries(decisions_path, category="workflow")
        assert len(result) == 1
        assert result[0].id == "WORKFLOW-001"

    def test_filter_by_label(
        self, decisions_path: Path, sample_rule: RuleEntry, sample_decision: DecisionEntry
    ) -> None:
        save_decisions([sample_rule, sample_decision], decisions_path)
        result = list_entries(decisions_path, label="storage")
        assert len(result) == 1
        assert result[0].id == "WORKFLOW-001"

    def test_returns_empty_for_no_matches(self, decisions_path: Path, sample_rule: RuleEntry) -> None:
        save_decisions([sample_rule], decisions_path)
        result = list_entries(decisions_path, type="decision")
        assert result == []


class TestResolveActive:
    """Tests for resolve_active()."""

    def test_returns_all_when_no_supersedes(
        self, sample_rule: RuleEntry, sample_decision: DecisionEntry
    ) -> None:
        entries = [sample_rule, sample_decision]
        active = resolve_active(entries)
        assert len(active) == 2

    def test_excludes_superseded_entry(self) -> None:
        old_rule = RuleEntry(id="NAMING-001", rule="Old rule")
        new_rule = RuleEntry(id="NAMING-002", rule="New rule", supersedes="NAMING-001")
        active = resolve_active([old_rule, new_rule])
        assert len(active) == 1
        assert active[0].id == "NAMING-002"

    def test_keeps_superseding_entry(self) -> None:
        old_rule = RuleEntry(id="NAMING-001", rule="Old rule")
        new_rule = RuleEntry(id="NAMING-002", rule="New rule", supersedes="NAMING-001")
        active = resolve_active([old_rule, new_rule])
        assert active[0].id == "NAMING-002"

    def test_empty_list(self) -> None:
        assert resolve_active([]) == []


class TestSetOutcome:
    """Tests for set_outcome()."""

    def test_sets_outcome_on_decision(self, decisions_path: Path, sample_decision: DecisionEntry) -> None:
        save_decisions([sample_decision], decisions_path)
        set_outcome("WORKFLOW-001", "adopted", "2026-07-01", path=decisions_path)
        loaded = load_decisions(decisions_path)
        assert isinstance(loaded[0], DecisionEntry)
        assert loaded[0].outcome is not None
        assert loaded[0].outcome.result == "adopted"
        assert loaded[0].outcome.measured_at == "2026-07-01"

    def test_refuses_overwrite_without_force(
        self, decisions_path: Path, sample_decision: DecisionEntry
    ) -> None:
        save_decisions([sample_decision], decisions_path)
        set_outcome("WORKFLOW-001", "adopted", "2026-07-01", path=decisions_path)
        with pytest.raises(ValueError, match="already has an outcome"):
            set_outcome("WORKFLOW-001", "rejected", "2026-08-01", path=decisions_path)

    def test_allows_overwrite_with_force(
        self, decisions_path: Path, sample_decision: DecisionEntry
    ) -> None:
        save_decisions([sample_decision], decisions_path)
        set_outcome("WORKFLOW-001", "adopted", "2026-07-01", path=decisions_path)
        set_outcome("WORKFLOW-001", "rejected", "2026-08-01", path=decisions_path, force=True)
        loaded = load_decisions(decisions_path)
        assert isinstance(loaded[0], DecisionEntry)
        assert loaded[0].outcome is not None
        assert loaded[0].outcome.result == "rejected"

    def test_raises_key_error_for_unknown_id(self, decisions_path: Path) -> None:
        save_decisions([], decisions_path)
        with pytest.raises(KeyError):
            set_outcome("NONEXISTENT-001", "adopted", "2026-07-01", path=decisions_path)

    def test_raises_type_error_for_non_decision(
        self, decisions_path: Path, sample_rule: RuleEntry
    ) -> None:
        save_decisions([sample_rule], decisions_path)
        with pytest.raises(TypeError, match="not a DecisionEntry"):
            set_outcome("NAMING-001", "adopted", "2026-07-01", path=decisions_path)

    def test_outcome_with_notes(self, decisions_path: Path, sample_decision: DecisionEntry) -> None:
        save_decisions([sample_decision], decisions_path)
        set_outcome("WORKFLOW-001", "adopted", "2026-07-01", notes="Worked well", path=decisions_path)
        loaded = load_decisions(decisions_path)
        assert isinstance(loaded[0], DecisionEntry)
        assert loaded[0].outcome is not None
        assert loaded[0].outcome.notes == "Worked well"

    def test_scope_and_optional_fields_round_trip(self, decisions_path: Path) -> None:
        decision = DecisionEntry(
            id="SCOPE-001",
            rule="Use quarterly reviews",
            scope="quarter",
            issue=None,
        )
        save_decisions([decision], decisions_path)
        loaded = load_decisions(decisions_path)
        assert isinstance(loaded[0], DecisionEntry)
        assert loaded[0].scope == "quarter"
        assert loaded[0].issue is None


class TestSyncToLocalMd:
    """Tests for sync_to_local_md() in little_loops.decisions_sync."""

    @pytest.fixture
    def decisions_path(self, tmp_path: Path) -> Path:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        return ll_dir / "decisions.yaml"

    def _write_rules(self, decisions_path: Path, rules: list) -> None:
        import yaml
        decisions_path.write_text(yaml.dump(rules), encoding="utf-8")

    def test_creates_section(self, decisions_path: Path) -> None:
        from little_loops.decisions import save_decisions
        from little_loops.decisions_sync import sync_to_local_md

        rule = RuleEntry(id="R-001", rule="Use atomic writes", enforcement="required")
        save_decisions([rule], decisions_path)

        sync_to_local_md(path=decisions_path)

        ll_local = decisions_path.parent / "ll.local.md"
        content = ll_local.read_text(encoding="utf-8")
        assert "## Active Rules" in content
        assert "Use atomic writes" in content

    def test_replaces_existing_section(self, decisions_path: Path) -> None:
        from little_loops.decisions import save_decisions
        from little_loops.decisions_sync import sync_to_local_md

        ll_local = decisions_path.parent / "ll.local.md"
        ll_local.write_text("---\nkey: value\n---\n\n## Active Rules\n\n- Old rule\n", encoding="utf-8")

        rule = RuleEntry(id="R-001", rule="New required rule", enforcement="required")
        save_decisions([rule], decisions_path)

        sync_to_local_md(path=decisions_path)

        content = ll_local.read_text(encoding="utf-8")
        assert content.count("## Active Rules") == 1
        assert "New required rule" in content
        assert "Old rule" not in content

    def test_filters_advisory_rules(self, decisions_path: Path) -> None:
        from little_loops.decisions import save_decisions
        from little_loops.decisions_sync import sync_to_local_md

        required = RuleEntry(id="R-001", rule="Required rule", enforcement="required")
        advisory = RuleEntry(id="R-002", rule="Advisory rule", enforcement="advisory")
        save_decisions([required, advisory], decisions_path)

        sync_to_local_md(path=decisions_path)

        ll_local = decisions_path.parent / "ll.local.md"
        content = ll_local.read_text(encoding="utf-8")
        assert "Required rule" in content
        assert "Advisory rule" not in content

    def test_excludes_superseded_rules(self, decisions_path: Path) -> None:
        from little_loops.decisions import save_decisions
        from little_loops.decisions_sync import sync_to_local_md

        old_rule = RuleEntry(id="R-001", rule="Old rule", enforcement="required")
        new_rule = RuleEntry(id="R-002", rule="New rule", enforcement="required", supersedes="R-001")
        save_decisions([old_rule, new_rule], decisions_path)

        sync_to_local_md(path=decisions_path)

        ll_local = decisions_path.parent / "ll.local.md"
        content = ll_local.read_text(encoding="utf-8")
        assert "New rule" in content
        assert "Old rule" not in content

    def test_uses_atomic_write(self, decisions_path: Path) -> None:
        from unittest.mock import patch
        from little_loops.decisions import save_decisions
        from little_loops.decisions_sync import sync_to_local_md

        rule = RuleEntry(id="R-001", rule="Atomic rule", enforcement="required")
        save_decisions([rule], decisions_path)

        ll_local = decisions_path.parent / "ll.local.md"
        with patch("os.replace") as mock_replace:
            sync_to_local_md(path=decisions_path)
        assert mock_replace.called
        # The target of the replace should be ll.local.md
        final_target = mock_replace.call_args[0][1]
        assert str(ll_local) == str(final_target)
