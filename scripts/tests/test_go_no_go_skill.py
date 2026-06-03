"""Structural tests for the go-no-go skill (ENH-1888)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "go-no-go" / "SKILL.md"


class TestGoNoGoHistoryContextInjection:
    """Step 3a must document historical context query with correction signal (ENH-1888)."""

    def _phase_text(self) -> str:
        content = SKILL_FILE.read_text()
        start = content.index("### Step 3a: Read the Issue File")
        next_heading = content.find("\n###", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_ll_history_context_command_present(self) -> None:
        assert "ll-history-context" in self._phase_text(), (
            "Step 3a must include the ll-history-context command invocation"
        )

    def test_correction_signal_documented(self) -> None:
        text = self._phase_text()
        assert "-0.2" in text, (
            "Step 3a must document the -0.2 correction signal on GO/NO-GO verdict confidence"
        )

    def test_hist_variable_present(self) -> None:
        assert "HIST" in self._phase_text(), (
            "Step 3a must assign ll-history-context output to HIST variable"
        )
