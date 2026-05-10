"""Structural tests for the decide-issue skill (FEAT-1238).

Verifies that skills/decide-issue/SKILL.md documents all required structural
elements: flag parsing, option extraction patterns, codebase-pattern-finder
agent spawn, scoring criteria, selected-option annotation format, decision_needed
frontmatter update, and session log call.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "decide-issue" / "SKILL.md"


class TestDecideIssueSkillExists:
    """skills/decide-issue/SKILL.md must exist and be readable."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_FILE.exists(), "skills/decide-issue/SKILL.md not found"

    def test_skill_file_is_non_empty(self) -> None:
        content = SKILL_FILE.read_text()
        assert len(content) > 100, "SKILL.md is unexpectedly short"


class TestFlagParsing:
    """SKILL.md must document --auto and --dry-run flag parsing in Phase 1."""

    def test_phase_1_parse_arguments_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 1: Parse Arguments" in content, (
            "SKILL.md must contain a 'Phase 1: Parse Arguments' section"
        )

    def test_auto_flag_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase1_start = content.index("Phase 1: Parse Arguments")
        phase2_start = content.index("Phase 2: Locate Issue File")
        phase1_text = content[phase1_start:phase2_start]
        assert "--auto" in phase1_text, "Phase 1 must document the --auto flag"

    def test_dry_run_flag_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase1_start = content.index("Phase 1: Parse Arguments")
        phase2_start = content.index("Phase 2: Locate Issue File")
        phase1_text = content[phase1_start:phase2_start]
        assert "--dry-run" in phase1_text, "Phase 1 must document the --dry-run flag"


class TestOptionExtractionPatterns:
    """SKILL.md must document all three option extraction patterns in Phase 3."""

    def test_phase_3_extract_options_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 3: Extract Options" in content, (
            "SKILL.md must contain a 'Phase 3: Extract Options' section"
        )

    def test_pattern_1_section_headers_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("Phase 3: Extract Options")
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase3_text = content[phase3_start:phase4_start]
        assert "Pattern 1" in phase3_text, "Phase 3 must document Pattern 1 (section headers)"

    def test_pattern_2_bold_labels_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("Phase 3: Extract Options")
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase3_text = content[phase3_start:phase4_start]
        assert "Pattern 2" in phase3_text, "Phase 3 must document Pattern 2 (bold labels)"

    def test_pattern_3_numbered_items_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("Phase 3: Extract Options")
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase3_text = content[phase3_start:phase4_start]
        assert "Pattern 3" in phase3_text, "Phase 3 must document Pattern 3 (numbered items)"


class TestCodebasePatternFinderSpawn:
    """SKILL.md must document spawning codebase-pattern-finder agents in Phase 4."""

    def test_phase_4_gather_evidence_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 4: Gather Codebase Evidence" in content, (
            "SKILL.md must contain a 'Phase 4: Gather Codebase Evidence' section"
        )

    def test_codebase_pattern_finder_agent_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase5_start = content.index("Phase 5: Score Each Option")
        phase4_text = content[phase4_start:phase5_start]
        assert "codebase-pattern-finder" in phase4_text, (
            "Phase 4 must reference spawning codebase-pattern-finder agents per option"
        )

    def test_parallel_spawn_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase5_start = content.index("Phase 5: Score Each Option")
        phase4_text = content[phase4_start:phase5_start]
        assert "parallel" in phase4_text.lower() or "single message" in phase4_text, (
            "Phase 4 must document that agents are spawned in parallel (single message)"
        )


class TestScoringCriteria:
    """SKILL.md must document scoring dimensions in Phase 5."""

    def test_phase_5_score_options_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 5: Score Each Option" in content, (
            "SKILL.md must contain a 'Phase 5: Score Each Option' section"
        )

    def test_consistency_dimension_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase5_start = content.index("Phase 5: Score Each Option")
        phase6_start = content.index("Phase 6: Prepare Annotation")
        phase5_text = content[phase5_start:phase6_start]
        assert "Consistency" in phase5_text, (
            "Phase 5 must document the Consistency scoring dimension"
        )

    def test_simplicity_dimension_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase5_start = content.index("Phase 5: Score Each Option")
        phase6_start = content.index("Phase 6: Prepare Annotation")
        phase5_text = content[phase5_start:phase6_start]
        assert "Simplicity" in phase5_text, "Phase 5 must document the Simplicity scoring dimension"

    def test_testability_dimension_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase5_start = content.index("Phase 5: Score Each Option")
        phase6_start = content.index("Phase 6: Prepare Annotation")
        phase5_text = content[phase5_start:phase6_start]
        assert "Testability" in phase5_text, (
            "Phase 5 must document the Testability scoring dimension"
        )

    def test_risk_dimension_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase5_start = content.index("Phase 5: Score Each Option")
        phase6_start = content.index("Phase 6: Prepare Annotation")
        phase5_text = content[phase5_start:phase6_start]
        assert "Risk" in phase5_text, "Phase 5 must document the Risk scoring dimension"


class TestSelectedAnnotationFormat:
    """SKILL.md must document the '> **Selected:**' annotation format in Phase 6."""

    def test_phase_6_prepare_annotation_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 6: Prepare Annotation" in content, (
            "SKILL.md must contain a 'Phase 6: Prepare Annotation' section"
        )

    def test_selected_callout_format_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase6_start = content.index("Phase 6: Prepare Annotation")
        phase7_start = content.index("Phase 7: Apply Changes")
        phase6_text = content[phase6_start:phase7_start]
        assert "> **Selected:**" in phase6_text, (
            "Phase 6 must document the '> **Selected:**' callout annotation format"
        )


class TestDecisionNeededFrontmatterUpdate:
    """SKILL.md must document setting decision_needed: false in Phase 7."""

    def test_phase_7_apply_changes_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 7: Apply Changes" in content, (
            "SKILL.md must contain a 'Phase 7: Apply Changes' section"
        )

    def test_decision_needed_false_update_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase7_start = content.index("Phase 7: Apply Changes")
        phase8_start = content.index("Phase 8: Append Session Log")
        phase7_text = content[phase7_start:phase8_start]
        assert "decision_needed: false" in phase7_text, (
            "Phase 7b must document setting decision_needed: false in issue frontmatter"
        )

    def test_idempotency_rule_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase7_start = content.index("Phase 7: Apply Changes")
        phase8_start = content.index("Phase 8: Append Session Log")
        phase7_text = content[phase7_start:phase8_start]
        assert "Idempotency" in phase7_text or "idempotent" in phase7_text.lower(), (
            "Phase 7 must document the idempotency rule for annotation and frontmatter writes"
        )


class TestSessionLogCall:
    """SKILL.md must document the ll-issues append-log call in Phase 8."""

    def test_phase_8_append_session_log_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 8: Append Session Log" in content, (
            "SKILL.md must contain a 'Phase 8: Append Session Log' section"
        )

    def test_ll_issues_append_log_call_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase8_start = content.index("Phase 8: Append Session Log")
        phase9_start = content.index("Phase 9: Output Report")
        phase8_text = content[phase8_start:phase9_start]
        assert "ll-issues append-log" in phase8_text, (
            "Phase 8 must document the 'll-issues append-log' command call"
        )


class TestPhase3bInlineProvisionalScan:
    """Phase 3b must be documented in SKILL.md for AUTO_MODE + OPTIONS=0 path (BUG-1416)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3b: Inline Decision Scan")
        next_heading = content.find("\n## Phase 4:", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_3b_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 3b: Inline Decision Scan" in content, (
            "SKILL.md must contain a 'Phase 3b: Inline Decision Scan' section"
        )

    def test_auto_mode_options_zero_guard_documented(self) -> None:
        text = self._phase_text()
        assert "AUTO_MODE" in text and "OPTIONS" in text, (
            "Phase 3b must document the AUTO_MODE=true and OPTIONS=0 precondition"
        )

    def test_provisional_pattern_eg_documented(self) -> None:
        text = self._phase_text()
        assert "e.g." in text or "(e.g.," in text, (
            "Phase 3b must document the '(e.g., ...)' provisional pattern"
        )

    def test_provisional_pattern_tbd_documented(self) -> None:
        text = self._phase_text()
        assert "TBD" in text, (
            "Phase 3b must document the TBD inline design marker pattern"
        )

    def test_provisional_pattern_replacement_language_documented(self) -> None:
        text = self._phase_text()
        assert "fundamental rethink" in text or "must be replaced with" in text, (
            "Phase 3b must document the definitive replacement language pattern"
        )

    def test_single_winner_writeback_documented(self) -> None:
        text = self._phase_text()
        assert "decision_needed: false" in text, (
            "Phase 3b must document setting decision_needed: false for the single-winner path"
        )

    def test_ambiguous_exit_documented(self) -> None:
        text = self._phase_text()
        assert "no resolvable" in text or "ambiguous" in text.lower() or "unresolvable" in text, (
            "Phase 3b must document the clean exit for ambiguous/no-winner cases"
        )

    def test_no_ask_user_question_in_phase_3b(self) -> None:
        text = self._phase_text()
        assert "AskUserQuestion" not in text, (
            "Phase 3b must not use AskUserQuestion — --auto mode is non-interactive"
        )
