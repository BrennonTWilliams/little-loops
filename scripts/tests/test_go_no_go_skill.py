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


class TestGoNoGoWaiverStampRegardlessOfFindings:
    """Step 3f must stamp outcome_gate_waived on GO regardless of HAS_FINDINGS
    (BUG-3390): a GO verdict with no novel findings previously skipped Step 3f
    entirely and never stamped the waiver, silently blocking autodev's
    check_go_no_go_waiver escalation valve."""

    def _phase_text(self) -> str:
        # Note: the fenced findings-section template inside Step 3f contains its
        # own literal "### Key Arguments For"/"### Rationale" headings, so a
        # bare "\n###" search would stop there instead of at the next real
        # step boundary — anchor on "\n### Step" specifically.
        content = SKILL_FILE.read_text()
        start = content.index("### Step 3f: Go/No-Go Findings Write-Back")
        next_heading = content.find("\n### Step", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_waiver_paragraph_present(self) -> None:
        assert "outcome_gate_waived" in self._phase_text(), (
            "Step 3f must document the outcome_gate_waived escalation"
        )

    def test_waiver_stamped_regardless_of_has_findings(self) -> None:
        text = self._phase_text()
        assert "regardless of `HAS_FINDINGS`" in text, (
            "Step 3f must direct stamping the waiver regardless of HAS_FINDINGS, "
            "not skip it alongside the findings write-back"
        )

    def test_no_go_never_stamps(self) -> None:
        assert "NO-GO" in self._phase_text() and "must never stamp" in self._phase_text(), (
            "Step 3f must explicitly forbid stamping the waiver on a NO-GO verdict"
        )
