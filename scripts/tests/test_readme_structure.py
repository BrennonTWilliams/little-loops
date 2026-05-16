"""Structural guard for README.md hero-page format.

README.md is a positioning document — pillar claims, quick demos, count summary.
CLI tool documentation (flags, subcommands, examples) lives in docs/reference/CLI.md.

These tests prevent the README from reverting to its old 600-line catalog format.
When adding a new CLI tool, add its section to docs/reference/CLI.md, not README.md.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
README = PROJECT_ROOT / "README.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"


class TestReadmeIsHeroPage:
    """README.md must remain a short positioning document, not a CLI catalog."""

    def test_readme_is_under_200_lines(self) -> None:
        lines = README.read_text().splitlines()
        assert len(lines) < 200, (
            f"README.md has {len(lines)} lines — it must stay under 200. "
            "CLI tool documentation belongs in docs/reference/CLI.md, not README.md."
        )

    def test_readme_has_no_ll_cli_sections(self) -> None:
        content = README.read_text()
        assert "### ll-" not in content, (
            "README.md must not contain '### ll-' CLI tool sections. "
            "Add new CLI tool documentation to docs/reference/CLI.md instead."
        )

    def test_readme_links_to_cli_reference(self) -> None:
        content = README.read_text()
        assert "CLI.md" in content or "CLI Reference" in content, (
            "README.md must link to docs/reference/CLI.md so readers can find the full CLI reference."
        )


class TestReadmePillarStructure:
    """README.md must preserve the three-pillar positioning structure."""

    def test_pillar_durability_present(self) -> None:
        content = README.read_text()
        assert "Run asynchronous agents until done" in content, (
            "README.md must contain the durability pillar heading "
            '("Run asynchronous agents until done").'
        )

    def test_pillar_consistency_present(self) -> None:
        content = README.read_text()
        assert "Smart tools create smart processes." in content, (
            "README.md must contain the consistency pillar heading "
            '("Smart tools create smart processes.").'
        )

    def test_pillar_verification_present(self) -> None:
        content = README.read_text()
        assert "Harness-driven development" in content, (
            'README.md must contain the verification pillar heading ("Harness-driven development").'
        )
