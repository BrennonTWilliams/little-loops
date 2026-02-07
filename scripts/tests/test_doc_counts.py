"""Tests for documentation count verification."""

from pathlib import Path

import pytest

from little_loops.doc_counts import (
    CountResult,
    FixResult,
    VerificationResult,
    count_files,
    extract_count_from_line,
    fix_counts,
    format_result_json,
    format_result_markdown,
    format_result_text,
    verify_documentation,
)


class TestCountFiles:
    """Tests for count_files function."""

    def test_count_commands(self, tmp_path: Path) -> None:
        """Count command markdown files."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("# Command 1")
        (commands_dir / "cmd2.md").write_text("# Command 2")

        count = count_files("commands", "*.md", tmp_path)
        assert count == 2

    def test_count_skills_with_subdirs(self, tmp_path: Path) -> None:
        """Count skill files in subdirectories."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill1_dir = skills_dir / "skill1"
        skill1_dir.mkdir()
        (skill1_dir / "SKILL.md").write_text("# Skill 1")

        count = count_files("skills", "SKILL.md", tmp_path)
        assert count == 1

    def test_count_nonexistent_directory(self, tmp_path: Path) -> None:
        """Return 0 for nonexistent directory."""
        count = count_files("nonexistent", "*.md", tmp_path)
        assert count == 0

    def test_count_empty_directory(self, tmp_path: Path) -> None:
        """Return 0 for empty directory."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()

        count = count_files("commands", "*.md", tmp_path)
        assert count == 0


class TestExtractCountFromLine:
    """Tests for extract_count_from_line function."""

    def test_extract_simple_count(self) -> None:
        """Extract simple '34 commands' pattern."""
        count = extract_count_from_line("34 commands", "commands")
        assert count == 34

    def test_extract_with_adjective(self) -> None:
        """Extract '34 slash commands' pattern."""
        count = extract_count_from_line("34 slash commands", "commands")
        assert count == 34

    def test_extract_agents(self) -> None:
        """Extract '8 specialized agents' pattern."""
        count = extract_count_from_line("8 specialized agents", "agents")
        assert count == 8

    def test_extract_skills(self) -> None:
        """Extract '6 skill definitions' pattern."""
        count = extract_count_from_line("6 skill definitions", "skills")
        assert count == 6

    def test_no_match_returns_none(self) -> None:
        """Return None when pattern doesn't match."""
        count = extract_count_from_line("no numbers here", "commands")
        assert count is None

    def test_case_insensitive(self) -> None:
        """Match regardless of case."""
        count = extract_count_from_line("34 Commands", "commands")
        assert count == 34

    def test_extract_with_markdown_bold(self) -> None:
        """Extract count from markdown bold text."""
        count = extract_count_from_line("**34 slash commands** for workflows", "commands")
        assert count == 34


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_add_result_tracks_mismatches(self) -> None:
        """Adding mismatched result updates state."""
        result = VerificationResult(total_checked=0)
        mismatch = CountResult(
            category="commands",
            actual=35,
            documented=34,
            file="README.md",
            line=10,
            matches=False,
        )

        result.add_result(mismatch)

        assert not result.all_match
        assert len(result.mismatches) == 1
        assert result.mismatches[0].category == "commands"

    def test_add_result_matching(self) -> None:
        """Adding matched result doesn't change all_match."""
        result = VerificationResult(total_checked=0)
        match = CountResult(
            category="commands",
            actual=34,
            documented=34,
            file="README.md",
            line=10,
            matches=True,
        )

        result.add_result(match)

        assert result.all_match
        assert len(result.mismatches) == 0


class TestFormatResultText:
    """Tests for format_result_text function."""

    def test_format_all_match(self) -> None:
        """Format when all counts match."""
        result = VerificationResult(total_checked=3, all_match=True)

        output = format_result_text(result)

        assert "All 3 count(s) match" in output
        assert "✓" in output

    def test_format_with_mismatches(self) -> None:
        """Format with mismatched counts."""
        result = VerificationResult(total_checked=3, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_text(result)

        assert "1 mismatch" in output
        assert "commands:" in output
        assert "documented=34, actual=35" in output
        assert "README.md:10" in output


class TestFormatResultJson:
    """Tests for format_result_json function."""

    def test_format_valid_json(self) -> None:
        """Output is valid JSON."""
        import json

        result = VerificationResult(total_checked=2, all_match=True)

        output = format_result_json(result)

        data = json.loads(output)
        assert data["all_match"] is True
        assert data["total_checked"] == 2

    def test_format_includes_mismatches(self) -> None:
        """JSON includes mismatch details."""
        import json

        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_json(result)
        data = json.loads(output)

        assert len(data["mismatches"]) == 1
        assert data["mismatches"][0]["category"] == "commands"
        assert data["mismatches"][0]["actual"] == 35


class TestFormatResultMarkdown:
    """Tests for format_result_markdown function."""

    def test_format_all_match_markdown(self) -> None:
        """Format markdown when all counts match."""
        result = VerificationResult(total_checked=3, all_match=True)

        output = format_result_markdown(result)

        assert "# Documentation Count Verification" in output
        assert "All Counts Match" in output
        assert "✅" in output

    def test_format_with_mismatches_table(self) -> None:
        """Format markdown with mismatches table."""
        result = VerificationResult(total_checked=3, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_markdown(result)

        assert "| Category | Documented | Actual |" in output
        assert "| commands | 34 | 35 |" in output
        assert "`README.md:10`" in output


class TestFixCounts:
    """Tests for fix_counts function."""

    def test_fix_replaces_count(self, tmp_path: Path) -> None:
        """Fix replaces incorrect count with actual."""
        # Create test file with wrong count
        test_file = tmp_path / "README.md"
        test_file.write_text("## 34 commands\n")

        # Create result with mismatch
        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,  # Actual count
                documented=34,  # Documented (wrong)
                file="README.md",
                line=1,
                matches=False,
            )
        )

        # Fix
        fix_result = fix_counts(tmp_path, result)

        # Verify
        assert fix_result.fixed_count == 1
        assert len(fix_result.files_modified) == 1

        updated = test_file.read_text()
        assert "35 commands" in updated
        assert "34 commands" not in updated

    def test_fix_preserves_line_format(self, tmp_path: Path) -> None:
        """Fix preserves surrounding text and format."""
        test_file = tmp_path / "README.md"
        test_file.write_text("- **34 slash commands** for workflows\n")

        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=1,
                matches=False,
            )
        )

        fix_counts(tmp_path, result)

        updated = test_file.read_text()
        assert "- **35 slash commands** for workflows" in updated

    def test_fix_multiple_mismatches_same_file(self, tmp_path: Path) -> None:
        """Fix multiple mismatches in the same file."""
        test_file = tmp_path / "README.md"
        test_file.write_text("## 34 commands\n## 8 agents\n")

        result = VerificationResult(total_checked=2, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=1,
                matches=False,
            )
        )
        result.mismatches.append(
            CountResult(
                category="agents",
                actual=9,
                documented=8,
                file="README.md",
                line=2,
                matches=False,
            )
        )

        fix_result = fix_counts(tmp_path, result)

        assert fix_result.fixed_count == 2
        updated = test_file.read_text()
        assert "35 commands" in updated
        assert "9 agents" in updated

    def test_fix_multiple_files(self, tmp_path: Path) -> None:
        """Fix mismatches across multiple files."""
        readme = tmp_path / "README.md"
        readme.write_text("## 34 commands\n")

        contributing = tmp_path / "CONTRIBUTING.md"
        contributing.write_text("## 8 agents\n")

        result = VerificationResult(total_checked=2, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=1,
                matches=False,
            )
        )
        result.mismatches.append(
            CountResult(
                category="agents",
                actual=9,
                documented=8,
                file="CONTRIBUTING.md",
                line=1,
                matches=False,
            )
        )

        fix_result = fix_counts(tmp_path, result)

        assert fix_result.fixed_count == 2
        assert len(fix_result.files_modified) == 2
        assert "README.md" in fix_result.files_modified
        assert "CONTRIBUTING.md" in fix_result.files_modified

    def test_fix_no_changes_when_all_match(self, tmp_path: Path) -> None:
        """No changes made when all counts match."""
        test_file = tmp_path / "README.md"
        original_content = "## 34 commands\n"
        test_file.write_text(original_content)

        result = VerificationResult(total_checked=1, all_match=True)

        fix_result = fix_counts(tmp_path, result)

        assert fix_result.fixed_count == 0
        assert len(fix_result.files_modified) == 0
        assert test_file.read_text() == original_content


class TestVerifyDocumentation:
    """Integration tests for verify_documentation function."""

    def test_verify_with_all_counts_matching(self, tmp_path: Path) -> None:
        """Verify returns all_match when counts are correct."""
        # Create directories with files
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        for i in range(3):
            (commands_dir / f"cmd{i}.md").write_text(f"# Command {i}")

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        for i in range(2):
            (agents_dir / f"agent{i}.md").write_text(f"# Agent {i}")

        # Create documentation with correct counts
        readme = tmp_path / "README.md"
        readme.write_text("## 3 commands\n## 2 agents\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is True
        assert result.total_checked == 2
        assert len(result.mismatches) == 0

    def test_verify_detects_mismatches(self, tmp_path: Path) -> None:
        """Verify detects when documented counts don't match."""
        # Create directories with files
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        for i in range(5):
            (commands_dir / f"cmd{i}.md").write_text(f"# Command {i}")

        # Create documentation with wrong count
        readme = tmp_path / "README.md"
        readme.write_text("## 3 commands\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is False
        assert result.total_checked == 1
        assert len(result.mismatches) == 1
        assert result.mismatches[0].category == "commands"
        assert result.mismatches[0].documented == 3
        assert result.mismatches[0].actual == 5

    def test_verify_skips_nonexistent_doc_files(self, tmp_path: Path) -> None:
        """Verify gracefully handles missing documentation files."""
        # Create directories but no documentation files
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("# Command 1")

        result = verify_documentation(tmp_path)

        # Should not crash, just return empty result
        assert result.total_checked == 0
        assert result.all_match is True

    def test_verify_with_skills_subdirectories(self, tmp_path: Path) -> None:
        """Verify correctly counts skills in subdirectories."""
        # Create skills with subdirectories
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for i in range(3):
            skill_dir = skills_dir / f"skill{i}"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(f"# Skill {i}")

        # Create documentation with correct count
        readme = tmp_path / "README.md"
        readme.write_text("## 3 skills\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is True
        assert result.total_checked == 1
