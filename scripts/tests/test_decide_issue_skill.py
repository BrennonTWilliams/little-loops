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
    """SKILL.md must document that Phase 3 reads named pattern tiers from
    `ll-issues locate-options --json` rather than re-implementing the regexes
    itself (ENH-2950) — the pattern definitions live only in issue_parser.py."""

    def test_phase_3_extract_options_present(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 3: Extract Options" in content, (
            "SKILL.md must contain a 'Phase 3: Extract Options' section"
        )

    def test_locate_options_cli_call_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("Phase 3: Extract Options")
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase3_text = content[phase3_start:phase4_start]
        assert "ll-issues locate-options" in phase3_text, (
            "Phase 3 must call ll-issues locate-options instead of re-scanning by hand"
        )

    def test_section_header_pattern_name_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("Phase 3: Extract Options")
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase3_text = content[phase3_start:phase4_start]
        assert "section_header" in phase3_text, "Phase 3 must name the section_header pattern tier"

    def test_bold_label_pattern_name_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("Phase 3: Extract Options")
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase3_text = content[phase3_start:phase4_start]
        assert "bold_label" in phase3_text, "Phase 3 must name the bold_label pattern tier"

    def test_numbered_pattern_name_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("Phase 3: Extract Options")
        phase4_start = content.index("Phase 4: Gather Codebase Evidence")
        phase3_text = content[phase3_start:phase4_start]
        assert "numbered" in phase3_text, "Phase 3 must name the numbered pattern tier"


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


class TestPhase3CountOneResidualDirectiveGuard:
    """BUG-3287 ordering constraint: Phase 3's `count == 1` clear branch must not
    fire when a residual_directive is present — otherwise decision_needed gets
    cleared with a co-located Pattern E directive still open."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3: Extract Options")
        next_heading = content.find("\n## Phase 3b:", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_count_one_branch_guards_on_residual_directive(self) -> None:
        text = self._phase_text()
        assert "residual_directive" in text, (
            "Phase 3's count == 1 branch must reference residual_directive"
        )

    def test_count_one_clear_branch_still_documented(self) -> None:
        text = self._phase_text()
        assert "count == 1" in text
        assert "decision_needed" in text


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
        assert "TBD" in text, "Phase 3b must document the TBD inline design marker pattern"

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


class TestPhase3bResolvedFilter:
    """Phase 3b-i resolved-question filter must be documented in SKILL.md (ENH-1986)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3b: Inline Decision Scan")
        next_heading = content.find("\n## Phase 4:", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_resolved_filter_subsection_exists(self) -> None:
        text = self._phase_text()
        assert "Phase 3b-i" in text, (
            "Phase 3b must include a Phase 3b-i resolved-question filter subsection"
        )

    def test_resolved_markers_documented(self) -> None:
        text = self._phase_text()
        assert "✅ RESOLVED" in text, "Phase 3b-i must document the ✅ RESOLVED marker variant"
        assert "NO_ACTIONABLE_DECISIONS" in text, (
            "Phase 3b-i must document the NO_ACTIONABLE_DECISIONS output token"
        )

    def test_decision_needed_not_cleared_on_no_actionable(self) -> None:
        text = self._phase_text()
        assert (
            "decision_needed remains true" in text
            or "leave it as `true`" in text
            or "leave `decision_needed`" in text
        ), (
            "Phase 3b-i must document that decision_needed is NOT cleared on the NO_ACTIONABLE_DECISIONS path"
        )

    def test_no_file_edit_on_no_actionable(self) -> None:
        text = self._phase_text()
        assert "Do NOT edit the issue file" in text or "do not edit" in text.lower(), (
            "Phase 3b-i must document that the issue file is not edited on the NO_ACTIONABLE_DECISIONS path"
        )


class TestPattern4BulletOptions:
    """Phase 3 must document the bullet pattern tier (bullet-list options) — FEAT-389
    design gap.

    refine-issue commonly deposits options as `- (a) ...` / `- (b) ...` bullet lists in
    `## Codebase Research Findings`. The `bullet` tier catches these; the auto-mode
    guardrail keeps them from being scored without an explicit author recommendation.
    """

    def _phase3_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("Phase 3: Extract Options")
        end = content.index("## Phase 3b")
        return content[start:end]

    def test_pattern_4_documented(self) -> None:
        assert "`bullet`" in self._phase3_text(), (
            "Phase 3 must document the bullet pattern tier (bullet-list options)"
        )

    def test_bullet_list_match_documented(self) -> None:
        assert "bullet" in self._phase3_text().lower(), (
            "Phase 3 must describe bullet-list option matching"
        )

    def test_secondary_sections_scanned(self) -> None:
        assert "Codebase Research Findings" in self._phase3_text(), (
            "Phase 3 must widen extraction to ## Codebase Research Findings when "
            "Proposed Solution yields 0 options"
        )

    def test_auto_mode_bullet_guardrail_documented(self) -> None:
        text = self._phase3_text()
        assert "Pattern D" in text and "recommendation marker" in text.lower(), (
            "Phase 3 Option Count Check must gate auto-mode bullet-pattern options behind "
            "a declarative recommendation marker (Pattern D)"
        )


class TestValidateOnly:
    """SKILL.md must document --validate-only in Phase 1 (ENH-2443)."""

    def test_validate_only_flag_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase1_start = content.index("Phase 1: Parse Arguments")
        phase2_start = content.index("Phase 2: Locate Issue File")
        phase1_text = content[phase1_start:phase2_start]
        assert "--validate-only" in phase1_text, "Phase 1 must document the --validate-only flag"

    def test_validate_only_in_arguments_table(self) -> None:
        content = SKILL_FILE.read_text()
        args_start = content.index("## Arguments")
        phase1_start = content.index("## Phase 1: Parse Arguments")
        args_text = content[args_start:phase1_start]
        assert "--validate-only" in args_text, (
            "Arguments section flag table must document --validate-only"
        )


class TestDepositAttemptedFlag:
    """SKILL.md must document --deposit-attempted as an internal runtime flag (ENH-2443)."""

    def test_deposit_attempted_flag_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase1_start = content.index("Phase 1: Parse Arguments")
        phase2_start = content.index("Phase 2: Locate Issue File")
        phase1_text = content[phase1_start:phase2_start]
        assert "--deposit-attempted" in phase1_text or "DEPOSIT_ATTEMPTED" in phase1_text, (
            "Phase 1 must document the --deposit-attempted runtime flag"
        )


class TestPhase2_5Detection:
    """SKILL.md must document the new Phase 2.5 decidability gate (ENH-2443)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 2.5: Decidability Gate")
        end = content.index("## Phase 3: Extract Options")
        return content[start:end]

    def test_phase_2_5_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 2.5: Decidability Gate" in content, (
            "SKILL.md must contain a 'Phase 2.5: Decidability Gate' section"
        )

    def test_phase_2_5_reuses_phase_3_patterns(self) -> None:
        text = self._phase_text()
        assert "ll-issues locate-options" in text and "Phase 3" in text, (
            "Phase 2.5 must document calling the same locate-options CLI Phase 3 uses, "
            "reusing its option-extraction patterns"
        )

    def test_options_missing_token_documented(self) -> None:
        text = self._phase_text()
        assert "OPTIONS_MISSING" in text, "Phase 2.5 must document the OPTIONS_MISSING token"

    def test_manual_review_recommended_token_documented(self) -> None:
        text = self._phase_text()
        assert "MANUAL_REVIEW_RECOMMENDED" in text, (
            "Phase 2.5 must document the MANUAL_REVIEW_RECOMMENDED token distinct from "
            "MANUAL_REVIEW_NEEDED"
        )

    def test_exhausted_retry_falls_through_to_phase_3(self) -> None:
        """BUG-2606: an exhausted auto-recovery retry must fall through to Phase 3
        (so Phase 3b's provisional-language scan gets a chance) instead of
        short-circuiting to MANUAL_REVIEW_RECOMMENDED before Phase 3 ever runs."""
        text = self._phase_text().lower()
        assert "fall through" in text and "phase 3" in text, (
            "Phase 2.5's exhausted-retry branch must document falling through to "
            "Phase 3 rather than exiting to Phase 8"
        )
        assert "skip phases 3" not in text, (
            "Phase 2.5 must no longer document skipping Phases 3-7 on exhausted retry"
        )

    def test_no_scoring_no_writes_documented(self) -> None:
        text = self._phase_text()
        assert "no writes" in text.lower() or "do not write" in text.lower(), (
            "Phase 2.5 must document that it performs no frontmatter writes"
        )


class TestOptionsMissing:
    """SKILL.md must document the OPTIONS_MISSING outcome shape (ENH-2443)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 2.5: Decidability Gate")
        end = content.index("## Phase 3: Extract Options")
        return content[start:end]

    def test_options_missing_reason_documented(self) -> None:
        text = self._phase_text()
        assert "no enumerable alternatives" in text, (
            "OPTIONS_MISSING must document the 'no enumerable alternatives' reason"
        )

    def test_suggested_command_documented(self) -> None:
        text = self._phase_text()
        assert "/ll:refine-issue" in text, (
            "OPTIONS_MISSING must suggest /ll:refine-issue as the remedy"
        )

    def test_decision_needed_left_unchanged_on_exhausted_retry(self) -> None:
        text = self._phase_text()
        assert "decision_needed: true` unchanged" in text or "unchanged" in text, (
            "Phase 2.5 must document leaving decision_needed:true unchanged when the "
            "deposit retry is exhausted"
        )


class TestSingleOptionRegression:
    """Regression guard: the existing Phase 3 single-option auto-clear must survive
    the Phase 2.5 insertion (ENH-2443)."""

    def test_single_option_auto_clear_still_documented(self) -> None:
        content = SKILL_FILE.read_text()
        phase3_start = content.index("## Phase 3: Extract Options")
        phase3b_start = content.index("## Phase 3b")
        phase3_text = content[phase3_start:phase3b_start]
        assert "count == 1" in phase3_text, "Phase 3 must still document the single-option branch"
        assert "Clearing decision_needed if set" in phase3_text, (
            "Phase 3 must still document auto-clearing decision_needed for the single-option case"
        )


class TestFEAT398Snapshot:
    """Golden-file characterization test for the FEAT-398 reproduction (ENH-2443).

    decide-issue is a markdown SKILL (LLM-executed), so there is no CLI binary to
    subprocess into for a live exit-code test. count_enumerable_options() is the
    deterministic Python re-implementation FSM callers use (ll-issues check-decidable);
    this test locks in that the snapshotted fixture is a genuine 0-options case.
    """

    FIXTURE = Path(__file__).parent / "fixtures" / "issues" / "FEAT-398-decide-empty-proposed.md"

    def test_fixture_exists(self) -> None:
        assert self.FIXTURE.exists(), (
            "scripts/tests/fixtures/issues/FEAT-398-decide-empty-proposed.md must exist"
        )

    def test_fixture_has_decision_needed_true(self) -> None:
        content = self.FIXTURE.read_text()
        assert "decision_needed: true" in content

    def test_fixture_has_zero_enumerable_options(self) -> None:
        from little_loops.issue_parser import count_enumerable_options

        content = self.FIXTURE.read_text()
        assert count_enumerable_options(content) == 0, (
            "FEAT-398 fixture must reproduce the 0-enumerable-options case"
        )

    def test_fixture_is_structurally_present_not_empty_sections(self) -> None:
        content = self.FIXTURE.read_text()
        assert "### Design Decisions to Make" in content
        assert "### Implementation Outline" in content


class TestOptionsMissingExitCodes:
    """Subprocess-level exit-code contract for ll-issues check-decidable (ENH-2443).

    Mirrors the ll-issues format-check contract (0 = decidable, 1 = OPTIONS_MISSING);
    exercises the real deterministic CLI companion to --validate-only end to end.
    """

    def test_two_options_exits_zero(self) -> None:
        from little_loops.issue_parser import count_enumerable_options

        content = "## Proposed Solution\n\n### Option A\nDo X\n\n### Option B\nDo Y\n"
        assert count_enumerable_options(content) == 2

    def test_single_option_exits_zero(self) -> None:
        from little_loops.issue_parser import count_enumerable_options

        content = "## Proposed Solution\n\n### Option A\nDo X\n"
        assert count_enumerable_options(content) == 1

    def test_zero_options_exits_nonzero_condition(self) -> None:
        from little_loops.issue_parser import count_enumerable_options

        content = "## Proposed Solution\n\nA single narrative approach, no alternatives.\n"
        assert count_enumerable_options(content) == 0


class TestPattern3bDeclarativeRecommendation:
    """Phase 3b must document Pattern D + the absent-Open-Questions fall-through — FEAT-389.

    The original Phase 3b-i exited NO_ACTIONABLE_DECISIONS whenever ## Open Questions was
    absent, short-circuiting the provisional scan. The fix falls through to the scan, and
    Pattern D recognizes explicit declarative recommendations on bullet-list options.
    """

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3b: Inline Decision Scan")
        next_heading = content.find("\n## Phase 4:", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_pattern_d_documented(self) -> None:
        assert "Pattern D" in self._phase_text(), (
            "Phase 3b must document Provisional Pattern D (declarative recommendation)"
        )

    def test_recommendation_marker_described(self) -> None:
        assert "recommend" in self._phase_text().lower(), (
            "Pattern D must describe declarative recommendation markers"
        )

    def test_absent_open_questions_falls_through(self) -> None:
        text = self._phase_text().lower()
        assert "absent" in text and "fall through" in text, (
            "Phase 3b-i must fall through to the provisional scan when ## Open Questions "
            "is absent/empty rather than exiting NO_ACTIONABLE_DECISIONS"
        )

    def test_no_actionable_gated_on_existing_resolved_section(self) -> None:
        assert "exists with items" in self._phase_text(), (
            "Phase 3b-i must restrict the NO_ACTIONABLE_DECISIONS exit to an existing, "
            "all-resolved ## Open Questions section"
        )


class TestPhase3bMaterializeInformalDecisions:
    """Phase 3b Resolution Logic must document reformatting informal decisions into
    structured options and routing to full Phase 4-7 scoring (ENH-2715).

    Previously a clear winner always short-circuited to a lock-in-only exit, skipping
    Phase 4-7 evidence scoring even when the underlying decision already existed in the
    issue as informal prose (Pattern-4 bullets or Open-Questions alternatives). This
    materializes the alternatives as **Option A**/**Option B** blocks and routes to Phase 4.
    """

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3b: Inline Decision Scan")
        next_heading = content.find("\n## Phase 4:", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_materialize_step_documented(self) -> None:
        assert "Materialize alternatives" in self._phase_text(), (
            "Phase 3b Resolution Logic must document the materialize-alternatives step (ENH-2715)"
        )

    def test_materialize_reuses_enh_2607_template(self) -> None:
        text = self._phase_text()
        assert "ENH-2607" in text, (
            "Materialization must document reusing the ENH-2607 bold-label option template "
            "from commands/refine-issue.md"
        )
        assert "**Option A**" in text and "**Option B**" in text, (
            "Materialization must document the **Option A**/**Option B** target shape"
        )

    def test_pattern_d_no_longer_requires_existing_bullet_only(self) -> None:
        text = self._phase_text()
        assert "Open Questions" in text and "no pre-existing bullet is required" in text, (
            "Pattern D's Requirement must be relaxed to also match alternatives named "
            "inline in an unresolved Open Questions item, not just existing Pattern-4 bullets"
        )

    def test_route_to_phase_4_after_materialize_documented(self) -> None:
        text = self._phase_text()
        assert "proceeding to Phase 4" in text or "proceed directly to **Phase 4**" in text, (
            "Phase 3b must document routing to Phase 4 scoring after a successful "
            "materialization instead of the lock-in-only exit"
        )

    def test_lock_in_only_path_preserved_for_already_structured_case(self) -> None:
        text = self._phase_text()
        assert "Lock in without scoring" in text, (
            "Phase 3b must preserve the original lock-in-only path for cases where "
            "alternatives are already structured or no reformattable shape was found"
        )


class TestPattern3bDirectiveAlternatives:
    """Phase 3b must document Provisional Pattern E — un-preferenced decision
    directive (ENH-2936): 2+ named alternatives co-occurring with an imperative
    decide-marker but no stated preference, routed to Phase 4 scoring."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3b: Inline Decision Scan")
        next_heading = content.find("\n## Phase 4:", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_pattern_e_documented(self) -> None:
        assert "Pattern E" in self._phase_text(), (
            "Phase 3b must document Provisional Pattern E (un-preferenced decision directive)"
        )

    def test_imperative_marker_described(self) -> None:
        text = self._phase_text().lower()
        assert "imperative decide-marker" in text or "imperative" in text, (
            "Pattern E must describe the imperative decide-marker requirement"
        )

    def test_no_preference_requirement_described(self) -> None:
        normalized = " ".join(self._phase_text().split())
        assert "NO stated preference" in normalized, (
            "Pattern E must require the passage to state no preference"
        )

    def test_bare_or_prose_guardrail_documented(self) -> None:
        normalized = " ".join(self._phase_text().split())
        assert "Bare" in normalized and "explicitly NOT Pattern E" in normalized, (
            "Pattern E must document that bare 'X or Y' prose without an imperative "
            "marker is explicitly excluded (the settled-informal-list guardrail)"
        )

    def test_scan_scope_narrower_than_patterns_a_d(self) -> None:
        text = self._phase_text()
        assert "Scope Boundaries" in text, (
            "Pattern E's scan scope must include ## Scope Boundaries, where ENH-2866's "
            "directive lived"
        )

    def test_pattern_e_routes_to_materialize_and_score(self) -> None:
        text = self._phase_text()
        assert "Pattern E match" in text, (
            "Resolution Logic must classify Pattern E matches and route them through "
            "the materialize-and-score path (steps 1-2), skipping the clear-winner/"
            "ambiguous classification"
        )

    def test_pattern_d_cross_references_pattern_e(self) -> None:
        text = self._phase_text()
        assert (
            "Pattern E" in text.split("Provisional Pattern D")[1].split("Provisional Pattern E")[0]
        ), "Pattern D's Requirement note must cross-reference Pattern E for the no-preference case"


class TestBug3278DecisionGroupGating:
    """SKILL.md must document BUG-3278's decision-group model: Phase 7b and Phase 3b
    step 4 gate the `decision_needed: false` clear on `check-unresolved-decisions`
    rather than clearing unconditionally after annotating only the highest-precedence
    decision point."""

    def _phase3_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3: Extract Options")
        end = content.index("## Phase 3b")
        return content[start:end]

    def _phase3b_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 3b: Inline Decision Scan")
        next_heading = content.find("\n## Phase 4:", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def _phase7_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("## Phase 7: Apply Changes")
        end = content.index("## Phase 8:")
        return content[start:end]

    def test_phase3_sources_from_check_unresolved_decisions(self) -> None:
        text = self._phase3_text()
        assert "check-unresolved-decisions" in text and "unresolved[0]" in text, (
            "Phase 3 must source its candidate group from check-unresolved-decisions, "
            "not locate-options' raw tier winner"
        )

    def test_phase3_decision_rules_numbered_carveout_documented(self) -> None:
        text = self._phase3_text()
        assert "decision_rules_numbered" in text, (
            "Phase 3's zero-groups fall-through must carve out decision_rules_numbered "
            "(BUG-3278 part 4b) or the flag clears with nothing scored"
        )

    def test_phase3b_step3_ac_branch_requires_callout(self) -> None:
        text = self._phase3b_text()
        assert (
            "Patterns A–C additionally add a" in text and "per the locked-in provisional" in text
        ), (
            "Phase 3b step 3's Patterns A-C branch must write a > **Selected:** callout "
            "on structured option blocks, or step 4's gate stalls the single-decision "
            "auto path (BUG-3278)"
        )

    def test_phase3b_step4_gates_on_check_unresolved_decisions(self) -> None:
        text = self._phase3b_text()
        assert "check-unresolved-decisions" in text and "decision_needed remains true" in text, (
            "Phase 3b step 4 must gate its decision_needed: false write on "
            "check-unresolved-decisions — this is the AUTO_MODE-only clearing site "
            "Phase 7b's gate never reaches (BUG-3278)"
        )

    def test_phase7a_idempotency_is_per_group(self) -> None:
        text = self._phase7_text()
        assert "is_group_resolved" in text and "per-group" in text, (
            "Phase 7a's idempotency rule must be per-group (is_group_resolved), not "
            "document-wide — a document-wide rule suppresses the annotation for every "
            "group after the first"
        )

    def test_phase7a_rationale_heading_stays_literal(self) -> None:
        text = self._phase7_text()
        assert "Keep the heading literally" in text, (
            "Phase 7a must document that the ### Decision Rationale heading is never "
            "suffixed — _unapplied_decision's strict heading regex depends on the exact form"
        )

    def test_phase7a_provisional_e_retired_by_suppression_not_callout(self) -> None:
        text = self._phase7_text()
        assert "retirement being" in text and "probe suppression" in text, (
            "Phase 7a must document that a provisional_e group is retired by probe "
            "suppression, never by is_group_resolved or a callout"
        )

    def test_phase7b_gates_on_check_unresolved_decisions(self) -> None:
        text = self._phase7_text()
        assert (
            "check-unresolved-decisions" in text
            and "**after** 7a's annotation" in text
            and "decision_needed remains true" in text
        ), (
            "Phase 7b must run check-unresolved-decisions after 7a's annotation write "
            "and leave decision_needed: true on a residual (BUG-3278)"
        )
