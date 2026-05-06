"""Wiring tests for ENH-1268: Execution Summary documented in COMMANDS.md.

Asserts that the /ll:analyze-loop section of docs/reference/COMMANDS.md
contains the Execution Summary output format description introduced by ENH-1266.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMANDS_REF = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestAnalyzeLoopCommandsWiring:
    """docs/reference/COMMANDS.md must document the Execution Summary output block."""

    def _analyze_loop_section(self) -> str:
        content = COMMANDS_REF.read_text()
        start = content.index("### `/ll:analyze-loop`")
        # Use backtick pattern to skip ### headings inside fenced code blocks
        next_heading = content.find("\n### `", start + 1)
        return content[start:next_heading]

    def test_execution_summary_present(self) -> None:
        section = self._analyze_loop_section()
        assert "Execution Summary" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must document "
            "the Execution Summary output block"
        )

    def test_loop_goal_field_present(self) -> None:
        section = self._analyze_loop_section()
        assert "**Loop goal**" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must include "
            "the '**Loop goal**' field in the Execution Summary"
        )

    def test_observed_path_field_present(self) -> None:
        section = self._analyze_loop_section()
        assert "**Observed path**" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must include "
            "the '**Observed path**' field in the Execution Summary"
        )

    def test_goal_alignment_field_present(self) -> None:
        section = self._analyze_loop_section()
        assert "**Goal alignment**" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must include "
            "the '**Goal alignment**' field in the Execution Summary"
        )

    def test_resolved_flag_present(self) -> None:
        section = self._analyze_loop_section()
        assert "--resolved" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must document "
            "that Step 2 uses --resolved --json for sub-loop visibility"
        )

    def test_subloop_verdict_discarded_signal_present(self) -> None:
        section = self._analyze_loop_section()
        assert "Sub-loop verdict discarded" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must document "
            "the 'BUG — Sub-loop verdict discarded' signal"
        )

    def test_fault_signals_grouping_present(self) -> None:
        section = self._analyze_loop_section()
        assert "Fault Signals" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must document "
            "the 'Fault Signals' output grouping introduced by ENH-1335"
        )

    def test_effectiveness_signals_grouping_present(self) -> None:
        section = self._analyze_loop_section()
        assert "Effectiveness Signals" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must document "
            "the 'Effectiveness Signals' output grouping introduced by ENH-1335"
        )


class TestAssessLoopCommandsWiring:
    """docs/reference/COMMANDS.md must document the Goal-vs-Outcome Scorecard output block."""

    def _assess_loop_section(self) -> str:
        content = COMMANDS_REF.read_text()
        start = content.index("### `/ll:assess-loop`")
        # Use backtick pattern to skip ### headings inside fenced code blocks
        next_heading = content.find("\n### `", start + 1)
        return content[start:next_heading]

    def test_scorecard_present(self) -> None:
        section = self._assess_loop_section()
        assert "Goal-vs-Outcome Scorecard" in section, (
            "docs/reference/COMMANDS.md /ll:assess-loop entry must document "
            "the Goal-vs-Outcome Scorecard output block"
        )

    def test_verdict_field_present(self) -> None:
        section = self._assess_loop_section()
        assert "**Verdict**" in section, (
            "docs/reference/COMMANDS.md /ll:assess-loop entry must include "
            "the '**Verdict**' field in the Scorecard"
        )

    def test_phantom_verdict_present(self) -> None:
        section = self._assess_loop_section()
        assert "phantom" in section, (
            "docs/reference/COMMANDS.md /ll:assess-loop entry must document "
            "the 'phantom' verdict value"
        )

    def test_no_rubric_audit_flag_present(self) -> None:
        section = self._assess_loop_section()
        assert "--no-rubric-audit" in section, (
            "docs/reference/COMMANDS.md /ll:assess-loop entry must document "
            "the '--no-rubric-audit' flag"
        )

    def test_resolved_flag_present(self) -> None:
        section = self._assess_loop_section()
        assert "--resolved" in section, (
            "docs/reference/COMMANDS.md /ll:assess-loop entry must document "
            "that Step 2 uses --resolved --json for sub-loop visibility"
        )

    def test_skip_issue_creation_flag_present(self) -> None:
        section = self._assess_loop_section()
        assert "--skip-issue-creation" in section, (
            "docs/reference/COMMANDS.md /ll:assess-loop entry must document "
            "the '--skip-issue-creation' flag (ENH-1373)"
        )

    def test_auto_flag_present(self) -> None:
        section = self._assess_loop_section()
        assert "--auto" in section, (
            "docs/reference/COMMANDS.md /ll:assess-loop entry must document "
            "the '--auto' flag (ENH-1373)"
        )


class TestAnalyzeLoopHeadlessFlagsWiring:
    """docs/reference/COMMANDS.md must document --skip-issue-creation and --auto for /ll:analyze-loop."""

    def _analyze_loop_section(self) -> str:
        content = COMMANDS_REF.read_text()
        start = content.index("### `/ll:analyze-loop`")
        next_heading = content.find("\n### `", start + 1)
        return content[start:next_heading]

    def test_skip_issue_creation_flag_present(self) -> None:
        section = self._analyze_loop_section()
        assert "--skip-issue-creation" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must document "
            "the '--skip-issue-creation' flag (ENH-1373)"
        )

    def test_auto_flag_present(self) -> None:
        section = self._analyze_loop_section()
        assert "--auto" in section, (
            "docs/reference/COMMANDS.md /ll:analyze-loop entry must document "
            "the '--auto' flag (ENH-1373)"
        )
