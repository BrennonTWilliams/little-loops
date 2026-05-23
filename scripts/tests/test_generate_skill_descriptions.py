"""Smoke tests for ll-generate-skill-descriptions CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.generate_skill_descriptions import (
    _build_prompt,
    _extract_trigger_keywords,
    _parse_frontmatter,
    _process_skills,
    _write_description_to_frontmatter,
    main_generate_skill_descriptions,
)


def _make_completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def _make_skill(
    tmp_path: Path,
    name: str,
    disable_model_invocation: bool = False,
    description: str = 'Use when user asks for stuff.\n\nTrigger keywords: "foo", "bar"',
    body: str = "# My Skill\n\nDoes stuff.",
) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    dm_line = "disable-model-invocation: true\n" if disable_model_invocation else ""
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(f"---\n{dm_line}description: |\n  {description}\n---\n\n{body}")
    return skill_md


# =============================================================================
# _parse_frontmatter
# =============================================================================


class TestParseFrontmatter:
    def test_parses_key_value_pairs(self) -> None:
        text = "---\nfoo: bar\nbaz: qux\n---\n# Body"
        fm, body = _parse_frontmatter(text)
        assert fm["foo"] == "bar"
        assert fm["baz"] == "qux"
        assert "# Body" in body

    def test_no_frontmatter_returns_empty_dict(self) -> None:
        text = "# No frontmatter"
        fm, body = _parse_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_parses_disable_model_invocation(self) -> None:
        text = "---\ndisable-model-invocation: true\ndescription: foo\n---\n# Body"
        fm, _ = _parse_frontmatter(text)
        assert fm["disable-model-invocation"] == "true"

    def test_resolves_block_scalar_description(self) -> None:
        """``description: |`` is resolved to its body so trigger keywords are preserved (BUG-1627)."""
        text = (
            "---\n"
            "description: |\n"
            "  Use when user does X.\n"
            '  Trigger keywords: "foo", "bar"\n'
            "---\n"
            "# Body\n"
        )
        fm, _ = _parse_frontmatter(text)
        assert fm["description"] != "|"  # regression guard
        assert "Trigger keywords" in fm["description"]
        # And downstream _extract_trigger_keywords must now find the line.
        assert "foo" in _extract_trigger_keywords(fm["description"])


# =============================================================================
# _extract_trigger_keywords
# =============================================================================


class TestExtractTriggerKeywords:
    def test_extracts_trigger_line(self) -> None:
        desc = 'Use when user does X.\n\nTrigger keywords: "foo", "bar"'
        result = _extract_trigger_keywords(desc)
        assert "Trigger keywords" in result
        assert "foo" in result

    def test_returns_empty_when_no_keywords_line(self) -> None:
        desc = "Use when user does X."
        assert _extract_trigger_keywords(desc) == ""


# =============================================================================
# _build_prompt
# =============================================================================


class TestBuildPrompt:
    def test_includes_skill_name(self) -> None:
        prompt = _build_prompt("my-skill", "kw1, kw2", "body text")
        assert "my-skill" in prompt

    def test_includes_trigger_keywords(self) -> None:
        prompt = _build_prompt("x", "kw1, kw2", "body")
        assert "kw1, kw2" in prompt

    def test_includes_body_excerpt(self) -> None:
        prompt = _build_prompt("x", "", "some body content here")
        assert "some body content here" in prompt

    def test_truncates_long_body(self) -> None:
        long_body = "x" * 1000
        prompt = _build_prompt("x", "", long_body)
        assert "x" * 500 in prompt
        assert "x" * 501 not in prompt


# =============================================================================
# _write_description_to_frontmatter
# =============================================================================


class TestWriteDescriptionToFrontmatter:
    def test_replaces_existing_description_line(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\ndescription: old description\nmodel: haiku\n---\n# Body")
        _write_description_to_frontmatter(skill_md, "new description")
        content = skill_md.read_text()
        assert "new description" in content
        assert "old description" not in content

    def test_noop_when_no_frontmatter(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        original = "# No frontmatter\nsome content"
        skill_md.write_text(original)
        _write_description_to_frontmatter(skill_md, "new description")
        assert skill_md.read_text() == original


# =============================================================================
# _process_skills — core skip and call-count logic
# =============================================================================


class TestProcessSkills:
    def test_skips_disable_model_invocation_skills(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "disabled-skill", disable_model_invocation=True)
        _make_skill(tmp_path, "enabled-skill", disable_model_invocation=False)

        with patch(
            "little_loops.subprocess_utils.run_claude_command",
            return_value=_make_completed(0, "Short description here"),
        ) as mock_run:
            processed, skipped, errors = _process_skills(
                tmp_path / "skills", apply=False, quiet=True
            )

        assert skipped == 1
        assert processed == 1
        assert errors == 0
        assert mock_run.call_count == 1

    def test_calls_run_claude_command_once_per_eligible_skill(self, tmp_path: Path) -> None:
        for name in ["skill-a", "skill-b", "skill-c"]:
            _make_skill(tmp_path, name)

        with patch(
            "little_loops.subprocess_utils.run_claude_command",
            return_value=_make_completed(0, "Generated desc"),
        ) as mock_run:
            processed, skipped, errors = _process_skills(
                tmp_path / "skills", apply=False, quiet=True
            )

        assert mock_run.call_count == 3
        assert processed == 3
        assert skipped == 0
        assert errors == 0

    def test_apply_writes_description_to_skill_md(self, tmp_path: Path) -> None:
        skill_md = _make_skill(tmp_path, "writable-skill")

        generated = "Use when user asks for writable stuff"
        with patch(
            "little_loops.subprocess_utils.run_claude_command",
            return_value=_make_completed(0, generated),
        ):
            _process_skills(tmp_path / "skills", apply=True, quiet=True)

        content = skill_md.read_text()
        assert generated in content

    def test_generated_description_truncated_to_max_100_chars(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "long-desc-skill")

        long_output = "A" * 200
        with patch(
            "little_loops.subprocess_utils.run_claude_command",
            return_value=_make_completed(0, long_output),
        ):
            _process_skills(tmp_path / "skills", apply=True, quiet=True)

        skill_md = tmp_path / "skills" / "long-desc-skill" / "SKILL.md"
        content = skill_md.read_text()
        for line in content.splitlines():
            if line.startswith("description:"):
                desc_val = line[len("description:") :].strip()
                assert len(desc_val) <= 100, f"Description too long: {desc_val!r}"
                break

    def test_nonzero_exit_counts_as_error(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "error-skill")

        with patch(
            "little_loops.subprocess_utils.run_claude_command",
            return_value=_make_completed(1, ""),
        ):
            processed, skipped, errors = _process_skills(
                tmp_path / "skills", apply=False, quiet=True
            )

        assert errors == 1
        assert processed == 0
        assert skipped == 0


# =============================================================================
# main_generate_skill_descriptions — entry-point
# =============================================================================


class TestMainGenerateSkillDescriptions:
    def test_dry_run_returns_zero_on_success(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill")

        with (
            patch.object(sys, "argv", ["ll-generate-skill-descriptions", "--quiet"]),
            patch(
                "little_loops.cli.generate_skill_descriptions._find_plugin_root",
                return_value=tmp_path,
            ),
            patch(
                "little_loops.subprocess_utils.run_claude_command",
                return_value=_make_completed(0, "Brief description"),
            ),
        ):
            result = main_generate_skill_descriptions()

        assert result == 0

    def test_returns_one_on_errors(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "bad-skill")

        with (
            patch.object(sys, "argv", ["ll-generate-skill-descriptions", "--quiet"]),
            patch(
                "little_loops.cli.generate_skill_descriptions._find_plugin_root",
                return_value=tmp_path,
            ),
            patch(
                "little_loops.subprocess_utils.run_claude_command",
                return_value=_make_completed(1, ""),
            ),
        ):
            result = main_generate_skill_descriptions()

        assert result == 1

    def test_missing_skills_dir_returns_one(self, tmp_path: Path) -> None:
        with (
            patch.object(sys, "argv", ["ll-generate-skill-descriptions"]),
            patch(
                "little_loops.cli.generate_skill_descriptions._find_plugin_root",
                return_value=tmp_path,
            ),
        ):
            result = main_generate_skill_descriptions()

        assert result == 1
