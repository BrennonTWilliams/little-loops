"""Structural tests for the confidence-check skill (ENH-1087)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "confidence-check" / "SKILL.md"
RUBRIC_FILE = PROJECT_ROOT / "skills" / "confidence-check" / "rubric.md"


class TestConfidenceCheckPhase4CLI:
    """Phase 4 must use ll-issues set-scores (CLI), not a free-form Edit call (BUG-1307)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4: Update Frontmatter")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_uses_set_scores_cli(self) -> None:
        """Phase 4 must instruct the LLM to call ll-issues set-scores via Bash."""
        assert "ll-issues set-scores" in self._phase_text(), (
            "Phase 4 must use the ll-issues set-scores CLI, not a free-form Edit call (BUG-1307)"
        )

    def test_phase_4_does_not_use_edit_for_frontmatter(self) -> None:
        """Phase 4 must not instruct the LLM to use the Edit tool for frontmatter fields."""
        text = self._phase_text()
        assert "Use the Edit tool" not in text, (
            "Phase 4 must not use the Edit tool for frontmatter — CLI is the single source of truth (BUG-1307)"
        )

    def test_phase_4_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "### Phase 4: Update Frontmatter" in content, (
            "SKILL.md must contain a '### Phase 4: Update Frontmatter' section"
        )


class TestConfidenceCheckSkillWriteBack:
    """Verify Phase 4.5 write-back behavior is unconditional (ENH-1087)."""

    def test_skill_file_exists(self) -> None:
        """Skill file must be present."""
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_no_ask_user_question_in_phase_4_5(self) -> None:
        """AskUserQuestion must not appear in Phase 4.5 write-back path."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        # Find the next ### heading after Phase 4.5 to bound the section
        next_heading_idx = content.find("\n###", phase_4_5_start + 1)
        phase_4_5_end = next_heading_idx if next_heading_idx != -1 else len(content)
        phase_4_5_text = content[phase_4_5_start:phase_4_5_end]
        assert "AskUserQuestion" not in phase_4_5_text, (
            "Phase 4.5 must not use AskUserQuestion — write-back should be unconditional"
        )

    def test_check_mode_skip_guard_preserved(self) -> None:
        """CHECK_MODE skip guard must remain in Phase 4.5."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        phase_4_5_text = content[phase_4_5_start : phase_4_5_start + 2000]
        assert "CHECK_MODE" in phase_4_5_text, (
            "Phase 4.5 must preserve the CHECK_MODE skip guard (no writes in check mode)"
        )

    def test_has_findings_gate_preserved(self) -> None:
        """HAS_FINDINGS gate must remain in Phase 4.5."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        phase_4_5_text = content[phase_4_5_start : phase_4_5_start + 2000]
        assert "HAS_FINDINGS" in phase_4_5_text, "Phase 4.5 must preserve the HAS_FINDINGS gate"

    def test_confidence_check_notes_section_name_preserved(self) -> None:
        """The '## Confidence Check Notes' section name must remain in Phase 4.5."""
        content = SKILL_FILE.read_text()
        phase_4_5_start = content.index("### Phase 4.5: Findings Write-Back")
        phase_4_5_text = content[phase_4_5_start : phase_4_5_start + 2000]
        assert "## Confidence Check Notes" in phase_4_5_text, (
            "Phase 4.5 must preserve the '## Confidence Check Notes' section name"
        )


class TestFlagDelegationWriteBack:
    """Phase 4.6 must delegate all four flags to `ll-issues set-flags` (ENH-2946).

    Supersedes the old per-flag TestDecisionNeededFlagWriteBack /
    TestMissingArtifactsFlagWriteBack / TestImplementationOrderRiskFlagWriteBack
    classes — the phrase lists those tests asserted on now live solely in
    `scripts/little_loops/cli/issues/set_flags.py` (and are unit-tested there
    via `test_ll_issues_set_flags.py`), not duplicated in skill prose.
    """

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.6: Delegate Flag Setting")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_4_6_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Phase 4.6: Delegate Flag Setting" in content, (
            "SKILL.md must contain a 'Phase 4.6: Delegate Flag Setting' section"
        )

    def test_delegates_to_set_flags_cli(self) -> None:
        text = self._phase_text()
        assert "ll-issues set-flags" in text, (
            "Phase 4.6 must delegate flag setting to the ll-issues set-flags CLI"
        )
        assert "--from-notes" in text

    def test_no_phrase_list_duplicated(self) -> None:
        """The literal decision_needed phrase list must not be re-duplicated in prose."""
        text = self._phase_text()
        assert "unresolved decision" not in text, (
            "Phase 4.6 must not re-duplicate set_flags.py's phrase list — "
            "the CLI is the single source of truth"
        )

    def test_check_mode_guard_in_phase_4_6(self) -> None:
        assert "CHECK_MODE" in self._phase_text(), (
            "Phase 4.6 must include the CHECK_MODE skip guard (no writes in check mode)"
        )

    def test_no_ask_user_question_in_phase_4_6(self) -> None:
        assert "AskUserQuestion" not in self._phase_text(), (
            "Phase 4.6 must not use AskUserQuestion — flag write-back is unconditional"
        )

    def test_depth_moderate_or_deep_flag_documented(self) -> None:
        text = self._phase_text()
        assert "--depth-moderate-or-deep" in text, (
            "Phase 4.6 must document passing --depth-moderate-or-deep when Criterion A "
            "Depth was judged Moderate/Deep"
        )

    def test_external_api_suppression_documented(self) -> None:
        text = self._phase_text()
        assert "explore-api" in text and (
            "third-party" in text.lower() or "external" in text.lower()
        ), "Phase 4.6 must document the external-API suppression rule (advise /ll:explore-api)"


class TestPhase45OutcomeThreshold:
    """Phase 4.5 must use configurable outcome_threshold, not hardcoded 60 (BUG-1289)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.5: Findings Write-Back")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_outcome_threshold_referenced_in_phase_4_5(self) -> None:
        """Phase 4.5 must reference outcome_threshold, not hardcoded 60."""
        assert "outcome_threshold" in self._phase_text(), (
            "Phase 4.5 must reference outcome_threshold (not hardcoded 60) so the "
            "Outcome Risk Factors trigger respects the project-configurable threshold"
        )

    def test_hardcoded_60_absent_from_outcome_risk_condition(self) -> None:
        """The hardcoded '< 60' threshold must not appear in the Outcome Risk Factors condition."""
        text = self._phase_text()
        assert "outcome confidence < 60" not in text, (
            "Phase 4.5 must not use hardcoded '< 60'; use outcome_threshold instead (BUG-1289)"
        )

    def test_phase_4_6_guard_uses_outcome_threshold(self) -> None:
        """Phase 4.6 guard must reference outcome_threshold, not hardcoded 60."""
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 4.6: Delegate Flag Setting")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        phase_4_6_text = content[start:end]
        assert "outcome_confidence < 60" not in phase_4_6_text, (
            "Phase 4.6 guard must not use hardcoded '< 60'; use outcome_threshold instead (BUG-1289)"
        )


class TestCriterionDDualPattern:
    """Criterion D must distinguish Pattern A (code blast radius) from Pattern B (enumerated mechanical fanout)."""

    def _criterion_d_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("#### Criterion D:")
        next_heading = content.find("\n####", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_pattern_a_heading_present(self) -> None:
        assert "Pattern A" in self._criterion_d_text()

    def test_pattern_b_heading_present(self) -> None:
        assert "Pattern B" in self._criterion_d_text()

    def test_verifiability_table_row_present(self) -> None:
        assert "verification grep" in self._criterion_d_text()

    def test_original_count_table_retained_for_pattern_a(self) -> None:
        assert "0-2 callers" in self._criterion_d_text()

    def test_pattern_b_covers_code_call_site_sweeps(self) -> None:
        """BUG-2734: Pattern B detection must not be restricted to markdown/config/template files."""
        text = self._criterion_d_text()
        assert "source-code call sites" in text or "source code" in text, (
            "Criterion D must document that Pattern B can apply to uniform code call-site sweeps"
        )


class TestCriterionABreadthDepthSplit:
    """Criterion A must be split into Breadth (0-12) and Depth (0-13) sub-scores summing to 25."""

    def _criterion_a_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("#### Criterion A:")
        next_heading = content.find("\n####", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_breadth_sub_table_present(self) -> None:
        assert "Breadth" in self._criterion_a_text(), "Criterion A must contain a Breadth sub-table"

    def test_depth_sub_table_present(self) -> None:
        assert "Depth" in self._criterion_a_text(), "Criterion A must contain a Depth sub-table"

    def test_breadth_max_is_12(self) -> None:
        assert "0-12" in self._criterion_a_text(), (
            "Criterion A Breadth sub-score must be 0-12 points"
        )

    def test_depth_max_is_13(self) -> None:
        assert "0-13" in self._criterion_a_text(), "Criterion A Depth sub-score must be 0-13 points"

    def test_breadth_detection_method_present(self) -> None:
        text = self._criterion_a_text()
        assert "Integration Map" in text or "Files to Modify" in text, (
            "Criterion A must document Breadth detection method (file enumeration)"
        )

    def test_depth_detection_method_present(self) -> None:
        text = self._criterion_a_text()
        assert "substitute" in text or "rewiring" in text, (
            "Criterion A must document Depth detection method (change-description language)"
        )

    def test_criterion_a_heading_preserved(self) -> None:
        content = SKILL_FILE.read_text()
        assert "#### Criterion A:" in content, (
            "The '#### Criterion A:' heading must be preserved exactly (used as section anchor)"
        )


class TestPhase48Retired:
    """BUG-2734: Phase 4.8 (mechanical_fanout_suppressed) is retired — its
    detection folded into Criterion D's Pattern B classification instead of a
    post-hoc, write-only frontmatter flag."""

    def test_phase_4_8_heading_absent(self) -> None:
        assert "Phase 4.8:" not in SKILL_FILE.read_text()

    def test_mechanical_fanout_suppressed_absent(self) -> None:
        assert "mechanical_fanout_suppressed" not in SKILL_FILE.read_text()


class TestConfidenceCheckHistoryContextInjection:
    """Phase 1 must document historical context query with correction signal (ENH-1847)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 1: Gather Context")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_ll_history_context_command_present(self) -> None:
        assert "ll-history-context" in self._phase_text(), (
            "Phase 1 must include the ll-history-context command invocation"
        )

    def test_correction_signal_documented(self) -> None:
        text = self._phase_text()
        assert "−0.1" in text or "-0.1" in text, (
            "Phase 1 must document the -0.1 correction signal on Outcome Confidence Score"
        )

    def test_hist_variable_present(self) -> None:
        assert "HIST" in self._phase_text(), (
            "Phase 1 must assign ll-history-context output to HIST variable"
        )


class TestConfidenceCheckLearningTestPrefetch:
    """Phase 1.5 must pre-fetch learning test context (ENH-2232)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 1.5:")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_phase_1_5_heading_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "### Phase 1.5:" in content, (
            "SKILL.md must contain a '### Phase 1.5:' section for learning test pre-fetch (ENH-2232)"
        )

    def test_learning_tests_required_in_rubric(self) -> None:
        assert "learning_tests_required" in RUBRIC_FILE.read_text(), (
            "rubric.md must document the learning_tests_required read pattern (ENH-2232)"
        )

    def test_ll_learning_tests_check_in_rubric(self) -> None:
        assert "ll-learning-tests check" in RUBRIC_FILE.read_text(), (
            "rubric.md must include the ll-learning-tests check invocation (ENH-2232)"
        )

    def test_learning_test_context_block_in_rubric(self) -> None:
        assert "## Learning Test Context" in RUBRIC_FILE.read_text(), (
            "rubric.md must define the ## Learning Test Context block format (ENH-2232)"
        )

    def test_stop_override_in_phase_3(self) -> None:
        content = SKILL_FILE.read_text()
        start = content.index("### Phase 3:")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        phase_3_text = content[start:end]
        assert "missing" in phase_3_text or "refuted" in phase_3_text, (
            "Phase 3 must document the hard STOP override for missing/refuted targets (ENH-2232)"
        )

    def test_ll_learning_tests_in_allowed_tools(self) -> None:
        content = SKILL_FILE.read_text()
        frontmatter_end = content.index("\n---", 3)
        frontmatter = content[:frontmatter_end]
        assert "ll-learning-tests" in frontmatter, (
            "SKILL.md allowed-tools frontmatter must include Bash(ll-learning-tests:*) (ENH-2232)"
        )


class TestConfidenceCheckRubricLearningTestStatus:
    """rubric.md must include Learning Test Status scoring rows (ENH-2232)."""

    def test_minus_10_penalty_present(self) -> None:
        assert "−10" in RUBRIC_FILE.read_text(), (
            "rubric.md must include the −10 penalty row for missing/refuted learning test targets (ENH-2232)"
        )

    def test_minus_5_penalty_present(self) -> None:
        assert "−5" in RUBRIC_FILE.read_text(), (
            "rubric.md must include the −5 penalty row for stale learning test targets (ENH-2232)"
        )


class TestVerdictJsonTrailer:
    """rubric.md's single-issue output format must emit VERDICT_JSON (ENH-2949)."""

    def test_verdict_json_tag_present(self) -> None:
        assert "VERDICT_JSON:" in RUBRIC_FILE.read_text(), (
            "rubric.md must document a VERDICT_JSON: trailer after the single-issue output "
            "format so _record_verdict() captures structured fields (ENH-2949)"
        )

    def test_verdict_json_follows_single_issue_format(self) -> None:
        content = RUBRIC_FILE.read_text()
        single_start = content.index("## Output Format (single issue)")
        batch_start = content.index("## Batch Output Format")
        section = content[single_start:batch_start]
        assert "VERDICT_JSON:" in section, (
            "VERDICT_JSON trailer must be documented within the single-issue output section"
        )

    def test_verdict_json_has_required_fields(self) -> None:
        content = RUBRIC_FILE.read_text()
        idx = content.index('VERDICT_JSON: {"verdict"')
        line = content[idx : idx + 400]
        for field in ("verdict", "confidence", "target_id", "target_kind", "severity_counts", "findings_count"):
            assert f'"{field}"' in line, f"VERDICT_JSON example must include the {field} field"
