"""Structural tests for the refine-issue command (ENH-1237).

Verifies that /ll:refine-issue --auto sets `decision_needed: true` in issue
frontmatter when 2+ implementation options are deposited into Proposed Solution,
and that the flag is documented in the expected locations.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "refine-issue.md"
ISSUE_TEMPLATE = PROJECT_ROOT / "docs" / "reference" / "ISSUE_TEMPLATE.md"
COMMANDS_REF = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestOptionCountDetectionInCommand:
    """commands/refine-issue.md must document option-count detection in Step 5a."""

    def test_command_file_exists(self) -> None:
        assert COMMAND_FILE.exists(), "commands/refine-issue.md not found"

    def test_decision_needed_key_in_step_5a(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "decision_needed" in step_5a_text, (
            "Step 5a must reference `decision_needed` for the option-count detection logic"
        )

    def test_option_count_detection_block_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Option-Count Detection" in content, (
            "commands/refine-issue.md must contain an Option-Count Detection block in Step 5a"
        )

    def test_two_or_more_threshold_documented(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert ">= 2" in step_5a_text or "2+" in step_5a_text or "count >= 2" in step_5a_text, (
            "Step 5a must document the >= 2 threshold for setting decision_needed: true"
        )

    def test_idempotency_guard_mentioned(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "Idempotency" in step_5a_text or "idempotent" in step_5a_text.lower(), (
            "Step 5a must document idempotency: skip write if field already has same value"
        )

    def test_dry_run_guard_mentioned(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "--dry-run" in step_5a_text, (
            "Step 5a must document that the frontmatter write is skipped in --dry-run mode"
        )

    def test_placement_targets_proposed_solution(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "## Proposed Solution" in step_5a_text, (
            "Step 5a must document that the Option block is placed inside "
            "`## Proposed Solution`, not just 'near the original prose' (BUG-2820)"
        )

    def test_check_decidable_verification_documented(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "check-decidable" in step_5a_text, (
            "Step 5a must document verifying via `ll-issues check-decidable <ID>` "
            "before setting decision_needed: true (BUG-2820)"
        )

    def test_no_ask_user_question_in_step_5a(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "AskUserQuestion" not in step_5a_text, (
            "Step 5a must not use AskUserQuestion — option-count write-back is unconditional in auto mode"
        )

    def test_decision_needed_in_file_status_section(self) -> None:
        content = COMMAND_FILE.read_text()
        file_status_start = content.index("## FILE STATUS")
        next_heading = content.find("\n##", file_status_start + 1)
        file_status_text = content[file_status_start:next_heading]
        assert "decision_needed" in file_status_text, (
            "Step 8 FILE STATUS section must surface the decision_needed flag value"
        )

    def test_decision_point_formatting_rule_documented(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "Decision-Point Formatting" in step_5a_text, (
            "Step 5a must document the Decision-Point Formatting rule that converts "
            "prose recommendations into bold-label option blocks"
        )
        assert "**Option A**" in step_5a_text and "**Recommended**" in step_5a_text, (
            "Step 5a must show the **Option A**/**Recommended** bold-label template "
            "for formatting decision recommendations"
        )


class TestDecisionNeededDocWiring:
    """`decision_needed` must be documented in the issue template reference."""

    def test_decision_needed_in_issue_template(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        assert "`decision_needed`" in content, (
            "docs/reference/ISSUE_TEMPLATE.md Frontmatter Fields table must include "
            "a `decision_needed` row"
        )

    def test_decision_needed_row_mentions_refine_issue(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        lines = [line for line in content.splitlines() if "`decision_needed`" in line]
        assert lines, "Expected at least one line referencing `decision_needed`"
        row = next((line for line in lines if line.lstrip().startswith("|")), "")
        assert row, "Expected a table row for `decision_needed`"
        assert "refine-issue" in row or "refine" in row.lower(), (
            "`decision_needed` row must mention refine-issue as the source of this field"
        )

    def test_decision_needed_in_commands_ref(self) -> None:
        content = COMMANDS_REF.read_text()
        assert "decision_needed" in content, (
            "docs/reference/COMMANDS.md must document the `decision_needed` frontmatter "
            "write-back for /ll:refine-issue"
        )

    def test_frontmatter_write_back_note_in_commands_ref(self) -> None:
        content = COMMANDS_REF.read_text()
        refine_start = content.index("### `/ll:refine-issue`")
        next_heading = content.find("\n###", refine_start + 1)
        refine_text = content[refine_start:next_heading]
        assert "Frontmatter write-back" in refine_text, (
            "docs/reference/COMMANDS.md /ll:refine-issue entry must include a "
            "'Frontmatter write-back' note (follow issue-size-review pattern at line 249)"
        )


class TestGapAnalysisMode:
    """commands/refine-issue.md must document the --gap-analysis and --full-rewrite flags."""

    def _section_5c_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 5c. Gap-Analysis Mode")
        next_heading = content.find("\n### 6.", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_gap_analysis_flag_in_step_0(self) -> None:
        content = COMMAND_FILE.read_text()
        step_0_start = content.index("### 0. Parse Flags")
        step_1_start = content.index("### 1. Locate Issue File")
        step_0_text = content[step_0_start:step_1_start]
        assert "--gap-analysis" in step_0_text, (
            "Step 0 Parse Flags must detect the --gap-analysis flag"
        )

    def test_full_rewrite_flag_in_step_0(self) -> None:
        content = COMMAND_FILE.read_text()
        step_0_start = content.index("### 0. Parse Flags")
        step_1_start = content.index("### 1. Locate Issue File")
        step_0_text = content[step_0_start:step_1_start]
        assert "--full-rewrite" in step_0_text, (
            "Step 0 Parse Flags must detect the --full-rewrite flag"
        )

    def test_section_5c_exists_after_5b(self) -> None:
        content = COMMAND_FILE.read_text()
        pos_5b = content.index("### 5b. Interactive Refinement")
        pos_5c = content.index("### 5c. Gap-Analysis Mode")
        assert pos_5c > pos_5b, (
            "### 5c. Gap-Analysis Mode must appear after ### 5b. Interactive Refinement"
        )

    def test_additive_only_contract_documented(self) -> None:
        text = self._section_5c_text()
        assert "never removes" in text.lower() or "additive" in text.lower(), (
            "Section 5c must document the additive-only contract (never removes existing content)"
        )

    def test_max_refine_count_exemption_documented(self) -> None:
        text = self._section_5c_text()
        assert "max_refine_count" in text, (
            "Section 5c must document that gap-analysis runs are exempt from max_refine_count"
        )

    def test_gap_analysis_in_examples(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_text = content[examples_start:]
        assert "--gap-analysis" in examples_text, (
            "Examples section must include a --gap-analysis example"
        )

    def test_full_rewrite_in_examples(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_text = content[examples_start:]
        assert "--full-rewrite" in examples_text, (
            "Examples section must include a --full-rewrite example"
        )


class TestSupersededDirectiveMarker:
    """Preservation Rule must document the `> ⚠ Superseded — ...` annotation
    carve-out (ENH-2995): annotate-only, three directive sections, same-pass
    refutation, idempotent, and the bounded marker-removal right.
    """

    def _preservation_rule_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("#### Preservation Rule")
        end = content.index("### 5b. Interactive Refinement")
        return content[start:end]

    def test_superseded_marker_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "⚠ Superseded" in text, (
            "Preservation Rule must document the `> ⚠ Superseded — ...` marker text"
        )

    def test_scope_limited_to_three_directive_sections(self) -> None:
        text = self._preservation_rule_text()
        for section in ("Implementation Steps", "Files to Modify", "Acceptance Criteria"):
            assert section in text, (
                f"Preservation Rule must scope the carve-out to include `{section}`"
            )

    def test_annotate_only_never_edit_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "annotate" in text.lower(), (
            "Preservation Rule must state the carve-out is annotation-only, never "
            "editing the refuted line's own text"
        )

    def test_same_pass_only_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "same pass" in text.lower() or "this pass" in text.lower(), (
            "Preservation Rule must restrict the carve-out to findings from the "
            "current refine pass, not prior appended blocks"
        )

    def test_idempotency_via_substring_containment_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "idempotent" in text.lower(), (
            "Preservation Rule must document idempotency for the superseded marker"
        )

    def test_marker_removal_right_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "remove" in text.lower() or "delet" in text.lower(), (
            "Preservation Rule must document the bounded marker-removal right "
            "(a marker is the one deletable line when its refutation no longer holds)"
        )


class TestRefineIssueHistoryContextInjection:
    """commands/refine-issue.md must document Step 2.5 historical context query (ENH-1847)."""

    def _phase_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 2.5 — Query Historical Context")
        next_heading = content.find("\n### 3.", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_step_2_5_heading_exists(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "### 2.5 — Query Historical Context" in content, (
            "commands/refine-issue.md must contain a '### 2.5 — Query Historical Context' section"
        )

    def test_ll_history_context_command_present(self) -> None:
        assert "ll-history-context" in self._phase_text(), (
            "Step 2.5 must include the ll-history-context command invocation"
        )

    def test_hist_variable_in_step_2_5(self) -> None:
        assert "HIST" in self._phase_text(), (
            "Step 2.5 must assign ll-history-context output to HIST variable"
        )

    def test_graceful_degradation_mentioned(self) -> None:
        text = self._phase_text()
        assert "missing" in text.lower() or "absent" in text.lower() or "DB" in text, (
            "Step 2.5 must mention graceful degradation when DB is missing or no matches"
        )


class TestResearchTriageWiring:
    """Step 3 must condition its spawn set on `ll-issues research-triage` (ENH-2971)."""

    def _step_3_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 3. Research Codebase")
        end = content.index("### 4. Identify Knowledge Gaps")
        return content[start:end]

    def test_triage_cli_invoked(self) -> None:
        assert "ll-issues research-triage" in self._step_3_text(), (
            "Step 3 must call `ll-issues research-triage` before spawning research agents"
        )

    def test_spawn_set_is_conditioned_on_triage(self) -> None:
        text = self._step_3_text()
        assert "covered" in text, "Step 3 must branch on the triage output's `covered` field"
        assert "Spawn exactly one Task per axis whose `covered` is `false`" in text, (
            "Step 3 must instruct spawning one agent per uncovered axis, not all three"
        )
        assert "Spawn all 3 agents in a SINGLE message" not in text, (
            "the unconditional 3-agent spawn instruction must be gone from Step 3"
        )

    def test_full_rewrite_preserves_unconditional_spawn(self) -> None:
        text = self._step_3_text()
        assert "FULL_REWRITE" in text, (
            "Step 3 must exempt --full-rewrite from triage (a full rewrite does not "
            "trust existing content)"
        )

    def test_cli_failure_falls_back_to_all_three(self) -> None:
        text = self._step_3_text().lower()
        assert "fail open" in text or "fail-open" in text, (
            "Step 3 must fail open to all three agents when the triage CLI fails"
        )

    def test_zero_unmet_axes_branch_present(self) -> None:
        text = self._step_3_text()
        assert "#### 3.1" in text, "Step 3 must contain the zero-unmet-axes branch as 3.1"
        for step in ("4", "5a", "5b"):
            assert step in text, f"the 3.1 branch must name Step {step} as skipped"
        assert "Session Log" in text, (
            "a no-op refine must still append its Session Log entry, or callers cannot "
            "distinguish it from a silent failure"
        )

    def test_step_4_guards_against_absent_findings(self) -> None:
        content = COMMAND_FILE.read_text()
        start = content.index("### 4. Identify Knowledge Gaps")
        end = content.index("### 5a.")
        assert "3.1" in content[start:end], (
            "Step 4 must skip when Step 3.1 applied — with no research findings there is "
            "nothing to identify gaps against"
        )
