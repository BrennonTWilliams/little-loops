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
