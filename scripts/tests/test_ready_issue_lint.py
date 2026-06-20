"""Tests for ready-issue lint: file:line contamination detection — ENH-1300."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "ready-issue.md"

CLEAN_ISSUE = """\
---
title: Clean issue
---

# ENH-001: Clean Issue

## Summary

This issue uses only anchor-style references.

## Proposed Solution

See `scripts/foo.py` (near function `process`) for the existing implementation.

```python
# file.py:42 — this is inside a code fence and should be ignored
x = 1
```
"""

CONTAMINATED_ISSUE = """\
---
title: Contaminated issue
---

# ENH-002: Contaminated Issue

## Summary

This issue has a file:line reference.

## Proposed Solution

See scripts/foo.py:42 for the existing implementation.
Also check bar.ts:100 for the interface.
"""


class TestReadyIssueLintRule:
    """Validate that the file:line lint rule detects contamination correctly."""

    def test_clean_issue_passes(self) -> None:
        """An issue with no bare file:line refs (only anchors) reports no matches."""
        from little_loops.issues.anchor_sweep import _CODE_FENCE, _FILE_LINE

        content = CLEAN_ISSUE
        fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

        def _in_fence(start: int, end: int) -> bool:
            return any(fs <= start and end <= fe for fs, fe in fence_spans)

        matches = [m for m in _FILE_LINE.finditer(content) if not _in_fence(m.start(), m.end())]
        assert matches == [], f"Expected no file:line matches, got: {matches}"

    def test_contaminated_issue_flagged(self) -> None:
        """An issue with bare file:line refs outside fences is correctly flagged."""
        from little_loops.issues.anchor_sweep import _CODE_FENCE, _FILE_LINE

        content = CONTAMINATED_ISSUE
        fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

        def _in_fence(start: int, end: int) -> bool:
            return any(fs <= start and end <= fe for fs, fe in fence_spans)

        matches = [m for m in _FILE_LINE.finditer(content) if not _in_fence(m.start(), m.end())]
        paths = [m.group(1) for m in matches]
        assert "scripts/foo.py" in paths
        assert "bar.ts" in paths

    def test_ref_inside_fence_not_flagged(self) -> None:
        """file:line references inside code fences are not flagged."""
        from little_loops.issues.anchor_sweep import _CODE_FENCE, _FILE_LINE

        content = "```\nfoo.py:99\n```\n"
        fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

        def _in_fence(start: int, end: int) -> bool:
            return any(fs <= start and end <= fe for fs, fe in fence_spans)

        matches = [m for m in _FILE_LINE.finditer(content) if not _in_fence(m.start(), m.end())]
        assert matches == []


class TestReadyIssueHistoryContextInjection:
    """commands/ready-issue.md must document historical context query in Step 2 (ENH-1847)."""

    def _phase_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 2. Validate Issue Content")
        next_heading = content.find("\n### 3.", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_ll_history_context_command_present(self) -> None:
        assert "ll-history-context" in self._phase_text(), (
            "Step 2 must include the ll-history-context command invocation"
        )

    def test_historical_concerns_mentioned(self) -> None:
        text = self._phase_text()
        assert "Historical Concerns" in text or "historical" in text.lower(), (
            "Step 2 must mention Historical Concerns sub-bullet for matched corrections"
        )

    def test_graceful_degradation_mentioned(self) -> None:
        text = self._phase_text()
        assert "missing" in text.lower() or "absent" in text.lower() or "DB" in text, (
            "Step 2 must mention graceful degradation when DB is missing or no matches"
        )


class TestReadyIssueLearningTestGate:
    """commands/ready-issue.md must document Learning Test Gate in Step 2 (ENH-1284)."""

    def _phase_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 2. Validate Issue Content")
        next_heading = content.find("\n### 3.", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_learning_test_gate_section_present(self) -> None:
        assert "Learning Test Gate" in self._phase_text(), (
            "Step 2 must include a Learning Test Gate subsection"
        )

    def test_ll_learning_tests_command_present(self) -> None:
        assert "ll-learning-tests" in self._phase_text(), (
            "Step 2 must include the ll-learning-tests check command invocation"
        )

    def test_opt_in_behavior_mentioned(self) -> None:
        text = self._phase_text()
        assert "opt-in" in text.lower() or "absent" in text.lower() or "empty" in text.lower(), (
            "Step 2 must mention that the gate is opt-in (absent/empty field is PASS)"
        )


class TestReadyIssueLearningTestAutoProvision:
    """commands/ready-issue.md must auto-invoke explore-api for missing/refuted targets (ENH-2242)."""

    RUBRIC_FILE = PROJECT_ROOT / "skills" / "confidence-check" / "rubric.md"

    def _gate_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("#### Learning Test Gate")
        next_heading = content.find("\n####", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def _rubric_lt_text(self) -> str:
        content = self.RUBRIC_FILE.read_text()
        start = content.index("ll-learning-tests check")
        next_heading = content.find("\nWhen `LT_ROWS`", start)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_ready_issue_refuted_auto_invokes_explore_api(self) -> None:
        text = self._gate_text()
        assert "explore-api" in text, (
            "Learning Test Gate must reference explore-api for refuted targets (ENH-2242)"
        )
        assert (
            "Auto-invoke" in text
            or "auto-invoke" in text
            or "Auto-provision" in text
            or "auto-provision" in text
        ), "Learning Test Gate must describe auto-invocation for refuted targets (ENH-2242)"

    def test_ready_issue_missing_auto_invokes_explore_api(self) -> None:
        text = self._gate_text()
        # Must not only block — must also describe the auto-invoke path for missing targets
        assert "explore-api" in text, (
            "Learning Test Gate must reference explore-api for missing targets (ENH-2242)"
        )

    def test_ready_issue_stale_does_not_trigger_auto_invoke(self) -> None:
        text = self._gate_text()
        # stale line must remain a WARN, not an auto-invoke
        stale_line = next(
            (line for line in text.splitlines() if "stale" in line and "WARN" in line), None
        )
        assert stale_line is not None, (
            "stale targets must still produce a WARN row (not trigger auto-invoke) (ENH-2242)"
        )

    def test_confidence_check_rubric_has_auto_provision_step(self) -> None:
        content = self.RUBRIC_FILE.read_text()
        assert "Auto-provision" in content, (
            "confidence-check rubric.md must include an Auto-provision step for missing/refuted targets (ENH-2242)"
        )

    def test_confidence_check_rubric_auto_provision_before_lt_rows(self) -> None:
        content = self.RUBRIC_FILE.read_text()
        auto_pos = content.find("Auto-provision")
        lt_rows_pos = content.find("When `LT_ROWS`")
        assert auto_pos != -1, "Auto-provision step must exist in rubric.md (ENH-2242)"
        assert lt_rows_pos != -1, "When `LT_ROWS` paragraph must exist in rubric.md"
        assert auto_pos < lt_rows_pos, (
            "Auto-provision step must appear before the 'When LT_ROWS is non-empty' paragraph (ENH-2242)"
        )
