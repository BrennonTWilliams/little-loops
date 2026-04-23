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
