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
