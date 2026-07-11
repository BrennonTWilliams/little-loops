"""Tests for little_loops.decisions module."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest
import yaml

from little_loops.decisions import (
    CouplingEntry,
    DecisionEntry,
    ExceptionEntry,
    RuleEntry,
    add_entry,
    list_entries,
    load_coupling_entries,
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

    def test_loads_decision_entry(
        self, decisions_path: Path, sample_decision: DecisionEntry
    ) -> None:
        save_decisions([sample_decision], decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 1
        assert isinstance(loaded[0], DecisionEntry)

    def test_loads_exception_entry(
        self, decisions_path: Path, sample_exception: ExceptionEntry
    ) -> None:
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

    def test_raises_yaml_error_on_othe_203_corruption(
        self, decisions_path: Path
    ) -> None:
        """OTHE-203: ``rationale: \"abc \"\" def\"`` is invalid YAML (unterminated quote).

        Verifies that the malformed-input surface that ENH-2589's validator gates
        raises ``yaml.YAMLError`` (specifically a parser error).
        """
        decisions_path.write_text(
            "entries:\n"
            "  - id: OTHE-203\n"
            "    type: decision\n"
            '    rationale: "abc "" def"\n',
            encoding="utf-8",
        )
        with pytest.raises(yaml.YAMLError, match="parsing"):
            load_decisions(decisions_path)

    def test_raises_key_error_for_missing_required_field(
        self, decisions_path: Path
    ) -> None:
        """Entry missing the ``id`` field raises ``KeyError`` at from_dict()."""
        decisions_path.write_text(
            "entries:\n"
            "  - type: rule\n"
            "    rationale: no id here\n",
            encoding="utf-8",
        )
        with pytest.raises(KeyError):
            load_decisions(decisions_path)

    def test_raises_value_error_for_unknown_entry_type(
        self, decisions_path: Path
    ) -> None:
        """Entry with an unregistered ``type`` raises ``ValueError`` from _entry_from_dict()."""
        decisions_path.write_text(
            "entries:\n"
            "  - id: BAD-001\n"
            "    type: foo\n"
            "    rationale: bad discriminator\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Unknown entry type"):
            load_decisions(decisions_path)


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

    def test_round_trip_preserves_fields(
        self, decisions_path: Path, sample_rule: RuleEntry
    ) -> None:
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

    def test_returns_empty_for_no_matches(
        self, decisions_path: Path, sample_rule: RuleEntry
    ) -> None:
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

    def test_sets_outcome_on_decision(
        self, decisions_path: Path, sample_decision: DecisionEntry
    ) -> None:
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
        set_outcome(
            "WORKFLOW-001", "adopted", "2026-07-01", notes="Worked well", path=decisions_path
        )
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
        ll_local.write_text(
            "---\nkey: value\n---\n\n## Active Rules\n\n- Old rule\n", encoding="utf-8"
        )

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
        new_rule = RuleEntry(
            id="R-002", rule="New rule", enforcement="required", supersedes="R-001"
        )
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

    def test_resolve_path_none_uses_cwd_default(self, tmp_path: Path) -> None:
        """_resolve_path(None) uses Path.cwd() / '.ll/decisions.yaml'."""
        from little_loops.decisions_sync import _resolve_path

        resolved = _resolve_path(None)
        import pathlib

        expected = pathlib.Path.cwd() / ".ll" / "decisions.yaml"
        assert resolved == expected

    def test_replaces_last_active_rules_section_when_multiple_present(
        self, decisions_path: Path
    ) -> None:
        """When ll.local.md has multiple '## Active Rules', rfind replaces only the last one."""
        from little_loops.decisions import save_decisions
        from little_loops.decisions_sync import sync_to_local_md

        ll_local = decisions_path.parent / "ll.local.md"
        # Two sections: an earlier one in frontmatter notes, a later one that is the real active block
        ll_local.write_text(
            "## Active Rules\n\n- First occurrence (should stay)\n\n"
            "# Notes\n\nSome text.\n\n"
            "## Active Rules\n\n- Old last rule\n",
            encoding="utf-8",
        )

        rule = RuleEntry(id="R-001", rule="New required rule", enforcement="required")
        save_decisions([rule], decisions_path)

        sync_to_local_md(path=decisions_path)

        content = ll_local.read_text(encoding="utf-8")
        # The NEW rule should be present
        assert "New required rule" in content
        # Old last rule should be replaced
        assert "Old last rule" not in content
        # First occurrence of the heading should still be in the file
        assert "First occurrence" in content


# =============================================================================
# TestDecisionsGracefulDegradation
# =============================================================================


class TestDecisionsGracefulDegradation:
    """Graceful degradation when .ll/decisions.yaml is absent."""

    def test_load_absent_path_returns_empty(self, tmp_path: Path) -> None:
        absent = tmp_path / "nonexistent.yaml"
        assert load_decisions(absent) == []

    def test_list_entries_absent_path_returns_empty(self, tmp_path: Path) -> None:
        absent = tmp_path / "nonexistent.yaml"
        assert list_entries(absent) == []

    def test_resolve_active_empty_list_returns_empty(self) -> None:
        assert resolve_active([]) == []


# =============================================================================
# TestDecisionsExceptionSuppression
# =============================================================================


class TestDecisionsExceptionSuppression:
    """Exception entries suppress corresponding rule violations."""

    def test_exception_found_by_rule_ref(
        self,
        decisions_path: Path,
        sample_rule: RuleEntry,
        sample_exception: ExceptionEntry,
    ) -> None:
        save_decisions([sample_rule, sample_exception], decisions_path)
        exceptions = list_entries(decisions_path, type="exception")
        suppressors = [
            e for e in exceptions if isinstance(e, ExceptionEntry) and e.rule_ref == sample_rule.id
        ]
        assert len(suppressors) == 1
        assert suppressors[0].id == sample_exception.id

    def test_rule_suppressed_when_exception_matches(
        self,
        decisions_path: Path,
        sample_rule: RuleEntry,
        sample_exception: ExceptionEntry,
    ) -> None:
        save_decisions([sample_rule, sample_exception], decisions_path)
        rules = list_entries(decisions_path, type="rule")
        exceptions = list_entries(decisions_path, type="exception")
        exception_rule_refs = {e.rule_ref for e in exceptions if isinstance(e, ExceptionEntry)}
        unviolated = [r for r in rules if r.id not in exception_rule_refs]
        assert sample_rule.id in exception_rule_refs
        assert len(unviolated) == 0


# =============================================================================
# TestGenerateFromCompleted
# =============================================================================


class TestGenerateFromCompleted:
    """generate_from_completed() auto-generates DecisionEntry records."""

    def test_generates_entries_from_completed_issues(
        self,
        decisions_path: Path,
        temp_project_dir: Path,
    ) -> None:
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        from little_loops.decisions import generate_from_completed
        from little_loops.issue_history.models import CompletedIssue

        completed = [
            CompletedIssue(
                path=temp_project_dir / ".issues/features/P3-FEAT-001-test.md",
                issue_type="FEAT",
                priority="P3",
                issue_id="FEAT-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
            CompletedIssue(
                path=temp_project_dir / ".issues/bugs/P2-BUG-001-test.md",
                issue_type="BUG",
                priority="P2",
                issue_id="BUG-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
        ]
        config = MagicMock()
        config.project_root = temp_project_dir
        config.decisions.log_path = ".ll/decisions.yaml"
        config.issues.base_dir = ".issues"

        with patch(
            "little_loops.issue_history.parsing.scan_completed_issues", return_value=completed
        ):
            count = generate_from_completed(config)

        assert count == 2
        entries = load_decisions(decisions_path)
        assert len(entries) == 2
        issue_ids = {e.issue for e in entries if isinstance(e, DecisionEntry) and e.issue}
        assert "FEAT-001" in issue_ids
        assert "BUG-001" in issue_ids

    def test_skips_already_logged_issues(
        self,
        decisions_path: Path,
        temp_project_dir: Path,
    ) -> None:
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        from little_loops.decisions import generate_from_completed
        from little_loops.issue_history.models import CompletedIssue

        existing = DecisionEntry(id="DEC-FEAT-001", issue="FEAT-001")
        save_decisions([existing], decisions_path)

        completed = [
            CompletedIssue(
                path=temp_project_dir / ".issues/features/P3-FEAT-001-test.md",
                issue_type="FEAT",
                priority="P3",
                issue_id="FEAT-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
        ]
        config = MagicMock()
        config.project_root = temp_project_dir
        config.decisions.log_path = ".ll/decisions.yaml"
        config.issues.base_dir = ".issues"

        with patch(
            "little_loops.issue_history.parsing.scan_completed_issues", return_value=completed
        ):
            count = generate_from_completed(config)

        assert count == 0
        entries = load_decisions(decisions_path)
        assert len(entries) == 1

    def test_auto_generate_prefix_filter_skips_excluded_types(
        self,
        decisions_path: Path,
        temp_project_dir: Path,
    ) -> None:
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        from little_loops.decisions import generate_from_completed
        from little_loops.issue_history.models import CompletedIssue

        completed = [
            CompletedIssue(
                path=temp_project_dir / ".issues/features/P3-FEAT-001-test.md",
                issue_type="FEAT",
                priority="P3",
                issue_id="FEAT-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
            CompletedIssue(
                path=temp_project_dir / ".issues/bugs/P2-BUG-001-test.md",
                issue_type="BUG",
                priority="P2",
                issue_id="BUG-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
        ]
        config = MagicMock()
        config.project_root = temp_project_dir
        config.decisions.log_path = ".ll/decisions.yaml"
        config.decisions.auto_generate = ["FEAT"]
        config.issues.base_dir = ".issues"

        with patch(
            "little_loops.issue_history.parsing.scan_completed_issues", return_value=completed
        ):
            count = generate_from_completed(config)

        assert count == 1
        entries = load_decisions(decisions_path)
        assert len(entries) == 1
        assert entries[0].issue == "FEAT-001"  # type: ignore[union-attr]

    def test_auto_generate_empty_list_processes_all_types(
        self,
        decisions_path: Path,
        temp_project_dir: Path,
    ) -> None:
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        from little_loops.decisions import generate_from_completed
        from little_loops.issue_history.models import CompletedIssue

        completed = [
            CompletedIssue(
                path=temp_project_dir / ".issues/features/P3-FEAT-001-test.md",
                issue_type="FEAT",
                priority="P3",
                issue_id="FEAT-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
            CompletedIssue(
                path=temp_project_dir / ".issues/bugs/P2-BUG-001-test.md",
                issue_type="BUG",
                priority="P2",
                issue_id="BUG-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
        ]
        config = MagicMock()
        config.project_root = temp_project_dir
        config.decisions.log_path = ".ll/decisions.yaml"
        config.decisions.auto_generate = []
        config.issues.base_dir = ".issues"

        with patch(
            "little_loops.issue_history.parsing.scan_completed_issues", return_value=completed
        ):
            count = generate_from_completed(config)

        assert count == 2


# =============================================================================
# TestIsNearDuplicate
# =============================================================================


class TestIsNearDuplicate:
    """Unit tests for _is_near_duplicate() token-overlap dedup helper."""

    def _fn(self, rule: str, existing: list[str]) -> bool:
        from little_loops.cli.issues.decisions import _is_near_duplicate

        return _is_near_duplicate(rule, existing)

    def test_empty_existing_returns_false(self) -> None:
        assert self._fn("Always use atomic_write for file writes", []) is False

    def test_no_overlap_returns_false(self) -> None:
        assert self._fn("Never skip linting", ["Always write unit tests first"]) is False

    def test_high_overlap_returns_true(self) -> None:
        existing = ["always use atomic write for file writes"]
        assert self._fn("Always use atomic_write for file writes", existing) is True

    def test_below_threshold_returns_false(self) -> None:
        # 1/4 tokens overlap — below 60%
        existing = ["dogs bark loudly outside"]
        assert self._fn("cats always bark quietly", existing) is False

    def test_exact_duplicate_returns_true(self) -> None:
        rule = "Never mock the database in integration tests"
        assert self._fn(rule, [rule.lower()]) is True

    def test_short_tokens_ignored(self) -> None:
        # Words < 4 chars are excluded from significant tokens
        assert self._fn("Do it now", ["Do it now"]) is False


# =============================================================================
# TestCouplingEntry
# =============================================================================


@pytest.fixture
def sample_coupling() -> CouplingEntry:
    return CouplingEntry(
        id="COUPLING-001",
        type="coupling",
        timestamp="2026-06-06T00:00:00Z",
        category="wiring",
        labels=["wire-issue", "archetype:add-cli-command"],
        rationale="New CLI commands must be registered in plugin.json",
        if_changed="commands/*.md",
        then_check=[".claude-plugin/plugin.json", ".claude/CLAUDE.md"],
        tier="hard",
        archetype="add-cli-command",
    )


class TestCouplingEntry:
    """Tests for CouplingEntry dataclass and load_coupling_entries()."""

    def test_round_trip(self, decisions_path: Path, sample_coupling: CouplingEntry) -> None:
        save_decisions([sample_coupling], decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 1
        entry = loaded[0]
        assert isinstance(entry, CouplingEntry)
        assert entry.id == "COUPLING-001"
        assert entry.if_changed == "commands/*.md"
        assert entry.then_check == [".claude-plugin/plugin.json", ".claude/CLAUDE.md"]
        assert entry.tier == "hard"
        assert entry.archetype == "add-cli-command"

    def test_to_dict_omits_none_fields(self, sample_coupling: CouplingEntry) -> None:
        d = sample_coupling.to_dict()
        assert "if_changed" in d
        assert "then_check" in d
        assert "tier" in d
        assert "archetype" in d

    def test_to_dict_omits_none_optional_fields(self) -> None:
        entry = CouplingEntry(
            id="COUPLING-002",
            if_changed="scripts/**",
            then_check=["docs/reference/API.md"],
        )
        d = entry.to_dict()
        assert "archetype" not in d
        assert "supersedes" not in d
        assert "issue" not in d

    def test_load_coupling_entries_returns_only_coupling(
        self, decisions_path: Path, sample_coupling: CouplingEntry, sample_rule: RuleEntry
    ) -> None:
        save_decisions([sample_coupling, sample_rule], decisions_path)
        entries = load_coupling_entries(decisions_path)
        assert len(entries) == 1
        assert entries[0].id == "COUPLING-001"

    def test_load_coupling_entries_glob_match(
        self, decisions_path: Path, sample_coupling: CouplingEntry
    ) -> None:
        save_decisions([sample_coupling], decisions_path)
        # Matches commands/*.md pattern
        matched = load_coupling_entries(decisions_path, changed_globs=["commands/help.md"])
        assert len(matched) == 1
        # Does not match
        unmatched = load_coupling_entries(decisions_path, changed_globs=["scripts/foo.py"])
        assert len(unmatched) == 0

    def test_load_coupling_entries_archetype_filter(
        self, decisions_path: Path, sample_coupling: CouplingEntry
    ) -> None:
        other = CouplingEntry(
            id="COUPLING-002",
            if_changed="config-schema.json",
            then_check=["docs/reference/API.md"],
            tier="hard",
            archetype="add-config-key",
        )
        save_decisions([sample_coupling, other], decisions_path)
        entries = load_coupling_entries(decisions_path, archetype="add-cli-command")
        assert len(entries) == 1
        assert entries[0].id == "COUPLING-001"

    def test_load_coupling_entries_archetype_and_glob_combined(
        self, decisions_path: Path, sample_coupling: CouplingEntry
    ) -> None:
        save_decisions([sample_coupling], decisions_path)
        # archetype matches, glob also matches
        matched = load_coupling_entries(
            decisions_path,
            changed_globs=["commands/new-cmd.md"],
            archetype="add-cli-command",
        )
        assert len(matched) == 1
        # archetype matches, glob does not match
        no_match = load_coupling_entries(
            decisions_path,
            changed_globs=["scripts/foo.py"],
            archetype="add-cli-command",
        )
        assert len(no_match) == 0

    def test_load_coupling_entries_absent_file(self, tmp_path: Path) -> None:
        absent = tmp_path / "nonexistent.yaml"
        assert load_coupling_entries(absent) == []

    def test_tier_classification(self) -> None:
        hard = CouplingEntry(id="C-001", if_changed="*.md", then_check=["a.md"], tier="hard")
        soft = CouplingEntry(id="C-002", if_changed="*.md", then_check=["b.md"], tier="soft")
        fyi = CouplingEntry(id="C-003", if_changed="*.md", then_check=["c.md"], tier="fyi")
        assert hard.tier == "hard"
        assert soft.tier == "soft"
        assert fyi.tier == "fyi"

    def test_mixed_entries_list_filter(
        self, decisions_path: Path, sample_coupling: CouplingEntry, sample_rule: RuleEntry
    ) -> None:
        save_decisions([sample_coupling, sample_rule], decisions_path)
        coupling_entries = list_entries(decisions_path, type="coupling")
        assert len(coupling_entries) == 1
        assert coupling_entries[0].id == "COUPLING-001"

    def test_add_coupling_entry(self, decisions_path: Path, sample_coupling: CouplingEntry) -> None:
        add_entry(sample_coupling, decisions_path)
        loaded = load_decisions(decisions_path)
        assert len(loaded) == 1
        assert isinstance(loaded[0], CouplingEntry)
