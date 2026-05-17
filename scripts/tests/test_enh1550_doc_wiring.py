"""Doc-wiring regression tests for ENH-1550: status canonical enum documentation.

Asserts that:
1. .claude/CLAUDE.md names all 6 canonical status values and lists forbidden synonyms
2. Five issue-touching skill/command files each contain the Status enum reference line
3. docs/guides/ISSUE_MANAGEMENT_GUIDE.md mentions synonym coercion in the status table section
4. docs/reference/CLI.md clarifies that --status input must be canonical
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
CAPTURE_SKILL = PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md"
FORMAT_SKILL = PROJECT_ROOT / "skills" / "format-issue" / "SKILL.md"
MANAGE_SKILL = PROJECT_ROOT / "skills" / "manage-issue" / "SKILL.md"
READY_CMD = PROJECT_ROOT / "commands" / "ready-issue.md"
REFINE_CMD = PROJECT_ROOT / "commands" / "refine-issue.md"
ISSUE_GUIDE = PROJECT_ROOT / "docs" / "guides" / "ISSUE_MANAGEMENT_GUIDE.md"
CLI_REF = PROJECT_ROOT / "docs" / "reference" / "CLI.md"


class TestClaudeMdStatusEnum:
    """.claude/CLAUDE.md must document the canonical status enum."""

    def test_status_values_subsection_present(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "**Status values**:" in content, (
            ".claude/CLAUDE.md must contain a '**Status values**:' subsection under "
            "Issue File Format naming all canonical status values"
        )

    def test_all_six_canonical_values_present(self) -> None:
        content = CLAUDE_MD.read_text()
        for value in ("open", "in_progress", "blocked", "deferred", "done", "cancelled"):
            assert value in content, (
                f".claude/CLAUDE.md must list canonical status value '{value}' "
                "in the Status values subsection"
            )

    def test_forbidden_synonyms_listed(self) -> None:
        content = CLAUDE_MD.read_text()
        for synonym in ("complete", "completed", "finished", "wip"):
            assert synonym in content, (
                f".claude/CLAUDE.md must explicitly name forbidden synonym '{synonym}' "
                "so coding agents know not to use it"
            )


class TestSkillStatusEnumReferences:
    """Each issue-touching skill/command file must contain a Status enum reference line."""

    def _assert_has_status_enum(self, path: Path) -> None:
        content = path.read_text()
        assert "**Status enum**:" in content, (
            f"{path.relative_to(PROJECT_ROOT)} must contain '**Status enum**:' "
            "pointing to .claude/CLAUDE.md § Issue File Format"
        )

    def test_capture_issue_skill(self) -> None:
        self._assert_has_status_enum(CAPTURE_SKILL)

    def test_format_issue_skill(self) -> None:
        self._assert_has_status_enum(FORMAT_SKILL)

    def test_manage_issue_skill(self) -> None:
        self._assert_has_status_enum(MANAGE_SKILL)

    def test_ready_issue_command(self) -> None:
        self._assert_has_status_enum(READY_CMD)

    def test_refine_issue_command(self) -> None:
        self._assert_has_status_enum(REFINE_CMD)


class TestIssueGuideCoercionNote:
    """ISSUE_MANAGEMENT_GUIDE.md must mention synonym coercion in the status section."""

    def test_synonym_coercion_note_present(self) -> None:
        content = ISSUE_GUIDE.read_text()
        assert "silently coerced to canonical values" in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must state that synonyms are "
            "'silently coerced to canonical values' on read, near the status table"
        )


class TestCliRefCanonicalNote:
    """docs/reference/CLI.md must clarify that --status arguments must be canonical."""

    def test_argparse_normalization_note_present(self) -> None:
        content = CLI_REF.read_text()
        assert "argparse validates choices before normalization runs" in content, (
            "docs/reference/CLI.md must note that 'argparse validates choices before "
            "normalization runs' so users know --status requires canonical values"
        )
