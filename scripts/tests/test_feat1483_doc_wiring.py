"""Tests for FEAT-1483: Codex slash-command and skill discovery research.

Verifies that the documentation artifacts produced by the research spike
exist and reference the correct API surfaces:
  (a) HOST_COMPATIBILITY.md references ~/.codex/skills/ (not .codex/prompts/)
  (b) thoughts/research/codex-command-discovery.md exists
  (c) hooks/adapters/codex/README.md "Out of scope" note is updated to
      reference the confirmed Codex Skills API
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HOST_COMPAT = PROJECT_ROOT / "docs" / "reference" / "HOST_COMPATIBILITY.md"
RESEARCH_DOC = PROJECT_ROOT / "thoughts" / "research" / "codex-command-discovery.md"
CODEX_README = PROJECT_ROOT / "hooks" / "adapters" / "codex" / "README.md"


class TestHostCompatibilityCodexSkills:
    """HOST_COMPATIBILITY.md must reference the Codex Skills API path."""

    def test_codex_skills_path_present(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "~/.codex/skills" in content or "codex/skills" in content, (
            "HOST_COMPATIBILITY.md must reference ~/.codex/skills/ after FEAT-1483 research"
        )

    def test_feat1483_tracking_reference(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "FEAT-1483" in content, (
            "HOST_COMPATIBILITY.md must reference FEAT-1483 in the tracking issues section"
        )

    def test_slash_command_row_marked_supported(self) -> None:
        """After FEAT-1493 lands, the Slash-command discovery row for Codex
        must show ✓ (commands bridged via `ll-adapt-skills-for-codex`).
        """
        content = HOST_COMPAT.read_text()
        slash_rows = [
            line for line in content.splitlines() if line.startswith("| Slash-command discovery")
        ]
        assert slash_rows, (
            "HOST_COMPATIBILITY.md is missing the 'Slash-command discovery' row"
        )
        row = slash_rows[0]
        # The Codex (last) cell must contain ✓, not ✗
        codex_cell = row.rsplit("|", 2)[1] if row.count("|") >= 4 else row
        assert "✓" in codex_cell, (
            "Slash-command discovery row's Codex column must be ✓ after FEAT-1493 "
            f"(commands bridged). Got: {row!r}"
        )
        assert "✗" not in codex_cell, (
            "Slash-command discovery row's Codex column still contains ✗; "
            "FEAT-1493 should have flipped it to ✓"
        )

    def test_feat1493_tracking_reference(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "FEAT-1493" in content, (
            "HOST_COMPATIBILITY.md must reference FEAT-1493 once the commands bridge ships"
        )


class TestCodexCommandDiscoveryDoc:
    """thoughts/research/codex-command-discovery.md must exist with key content."""

    def test_research_doc_exists(self) -> None:
        assert RESEARCH_DOC.exists(), (
            "thoughts/research/codex-command-discovery.md must exist after FEAT-1483 research spike"
        )

    def test_research_doc_skills_api(self) -> None:
        content = RESEARCH_DOC.read_text()
        assert "~/.codex/skills" in content, (
            "codex-command-discovery.md must document the ~/.codex/skills/ Skills API"
        )

    def test_research_doc_confirmed_stable(self) -> None:
        content = RESEARCH_DOC.read_text()
        assert "stable" in content.lower(), (
            "codex-command-discovery.md must note that the Codex Skills API is confirmed stable"
        )

    def test_research_doc_no_prompts_path(self) -> None:
        content = RESEARCH_DOC.read_text()
        # The doc should mention .codex/prompts/ only to note it doesn't exist
        if ".codex/prompts" in content:
            assert (
                "no" in content.lower() or "not" in content.lower() or "does not" in content.lower()
            ), "codex-command-discovery.md must clarify that .codex/prompts/ does not exist"


class TestCodexReadmeOutOfScopeUpdated:
    """hooks/adapters/codex/README.md must reference confirmed Codex Skills API."""

    def test_codex_readme_skills_api_mentioned(self) -> None:
        content = CODEX_README.read_text()
        assert "codex/skills" in content or "Skills API" in content or "SKILL.md" in content, (
            "hooks/adapters/codex/README.md must reference the Codex Skills API after FEAT-1483"
        )

    def test_codex_readme_feat1483_or_research_link(self) -> None:
        content = CODEX_README.read_text()
        assert "FEAT-1483" in content or "codex-command-discovery" in content, (
            "hooks/adapters/codex/README.md must reference FEAT-1483 or the research doc"
        )
