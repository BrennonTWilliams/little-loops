"""Contract tests for BUG-3753: historical Verification Notes vs the blocking stale-file scan."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.issue_parser import _mask_historical_notes, check_format_gaps
from little_loops.text_utils import build_ref_index, classify_issue_refs, extract_file_paths

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURE = (
    Path(__file__).parent / "fixtures" / "issues" / "BUG-3753-stale-quote-in-verification-notes.md"
)
VERIFY_CMD = PROJECT_ROOT / "commands" / "verify-issues.md"
LOOP = PROJECT_ROOT / "scripts" / "little_loops" / "loops" / "refine-to-ready-issue.yaml"

STALE = "skills/gone/skill-rubric-reference.md"
_EMPTY_LS = subprocess.CompletedProcess(args=["git"], returncode=0, stdout=b"", stderr=b"")


def _gaps(tmp_path: Path, body: str):  # type: ignore[no-untyped-def]
    path = tmp_path / "P3-ENH-9753-x.md"
    path.write_text(
        "---\nid: ENH-9753\ntype: ENH\ntitle: x\npriority: P3\nstatus: open\n---\n\n" + body,
        encoding="utf-8",
    )
    with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_LS):
        return check_format_gaps(path, ref_index=build_ref_index(tmp_path))


def _stale(tmp_path: Path, body: str) -> list[str]:
    return list(_gaps(tmp_path, body).stale_file_ref)  # type: ignore[attr-defined]


class TestHistoricalOnlyExemption:
    def test_frozen_reproduction_has_no_stale_blocker(self, tmp_path: Path) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        assert STALE in text
        path = tmp_path / "P3-ENH-9753-frozen.md"
        path.write_text(text, encoding="utf-8")
        with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_LS):
            gaps = check_format_gaps(path, ref_index=build_ref_index(tmp_path))
        assert gaps.stale_file_ref == []  # type: ignore[attr-defined]
        # Guard against a vacuous pass: the same file must still block unmasked.
        with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_LS):
            idx = build_ref_index(tmp_path)
        assert classify_issue_refs(text, idx)[STALE] == "stale"

    def test_unmasked_frozen_reproduction_still_extracts_path(self) -> None:
        # Shared extraction keeps whole-file behavior.
        assert STALE in extract_file_paths(FIXTURE.read_text(encoding="utf-8"))

    def test_same_path_outside_notes_still_blocks(self, tmp_path: Path) -> None:
        body = f"## Current Behavior\n\nSee `{STALE}`.\n\n## Verification Notes\n\nWas `{STALE}`.\n"
        assert _stale(tmp_path, body) == [STALE]

    def test_active_mention_after_notes_blocks(self, tmp_path: Path) -> None:
        body = f"## Verification Notes\n\nWas `{STALE}`.\n\n## Impact\n\nSee `{STALE}`.\n"
        assert _stale(tmp_path, body) == [STALE]

    def test_historical_planned_new_does_not_exempt_active_mention(self, tmp_path: Path) -> None:
        body = (
            f"## Current Behavior\n\nSee `{STALE}`.\n\n"
            f"## Verification Notes\n\n- `{STALE}` (new file)\n"
        )
        assert _stale(tmp_path, body) == [STALE]


class TestSpanBoundaries:
    def test_every_occurrence_is_masked(self, tmp_path: Path) -> None:
        body = (
            f"## Verification Notes\n\nA `{STALE}`.\n\n## Impact\n\nfine\n\n"
            f"## Verification Notes\n\nB `{STALE}`.\n"
        )
        assert _stale(tmp_path, body) == []

    def test_h3_content_stays_inside_section(self, tmp_path: Path) -> None:
        body = f"## Verification Notes\n\n### Pass 2\n\n`{STALE}`\n\n#### Detail\n\n`{STALE}`\n"
        assert _stale(tmp_path, body) == []

    def test_h1_terminates_section(self, tmp_path: Path) -> None:
        body = f"## Verification Notes\n\nx\n\n# Appendix\n\n`{STALE}`\n"
        assert _stale(tmp_path, body) == [STALE]

    def test_h2_terminates_section(self, tmp_path: Path) -> None:
        body = f"## Verification Notes\n\nx\n\n## Other\n\n`{STALE}`\n"
        assert _stale(tmp_path, body) == [STALE]

    @pytest.mark.parametrize(
        "heading", ["### Verification Notes", "## Verification Notes (old)", "## Verification Note"]
    )
    def test_variant_headings_do_not_exempt(self, tmp_path: Path, heading: str) -> None:
        assert _stale(tmp_path, f"{heading}\n\n`{STALE}`\n") == [STALE]

    def test_trailing_whitespace_heading_exempts(self, tmp_path: Path) -> None:
        assert _stale(tmp_path, f"## Verification Notes  \n\n`{STALE}`\n") == []

    def test_fenced_heading_does_not_start_span(self, tmp_path: Path) -> None:
        body = f"```markdown\n## Verification Notes\n```\n\n`{STALE}`\n"
        assert _stale(tmp_path, body) == [STALE]

    def test_fenced_heading_does_not_end_span(self, tmp_path: Path) -> None:
        body = f"## Verification Notes\n\n```markdown\n## Other\n```\n\n`{STALE}`\n"
        assert _stale(tmp_path, body) == []

    def test_unterminated_fence_retains_original_text(self, tmp_path: Path) -> None:
        body = f"## Verification Notes\n\n```\nunterminated\n\n`{STALE}`\n"
        assert _stale(tmp_path, body) == [STALE]

    def test_mask_preserves_length_and_line_breaks(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        masked = _mask_historical_notes(text)
        assert len(masked) == len(text)
        assert masked.count("\n") == text.count("\n")
        assert STALE not in masked

    def test_no_section_returns_content_unchanged(self) -> None:
        text = "## Summary\n\nnothing\n"
        assert _mask_historical_notes(text) is text


class TestSharedAndAmbiguityContracts:
    def test_classify_issue_refs_remains_whole_file(self, tmp_path: Path) -> None:
        with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_LS):
            index = build_ref_index(tmp_path)
        assert classify_issue_refs(FIXTURE.read_text(encoding="utf-8"), index)[STALE] == "stale"


class TestCommandAndLoopPins:
    def test_command_keeps_paraphrase_and_post_write_rule(self) -> None:
        text = VERIFY_CMD.read_text(encoding="utf-8")
        assert "Verification Notes must not re-introduce the finding" in text
        assert "**paraphrase**" in text
        assert "ll-issues format-check <ID>" in text

    def test_loop_reentry_topology_and_single_attempt_budget(self) -> None:
        states = yaml.safe_load(LOOP.read_text(encoding="utf-8"))["states"]
        assert states["check_claim_correction_budget"]["on_yes"] == "correct_claims"
        assert states["check_claim_correction_budget"]["on_no"] == "record_gate_unmet"
        assert states["check_claim_correction_budget"]["evaluate"]["target"] == 2
        assert states["correct_claims"]["next"] == "normalize_structure"
        assert states["normalize_structure"]["on_yes"] == "clear_verify_verdict"
        assert states["clear_verify_verdict"]["next"] == "verify_issue"
