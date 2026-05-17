"""Tests for ll-adapt-skills-for-codex CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.adapt_skills_for_codex import (
    _extract_short_desc,
    _insert_fields,
    _make_openai_yaml,
    _process_commands,
    _process_skills,
    _synthesized_skill_md,
    _title_case,
    main_adapt_skills_for_codex,
)


def _make_skill(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    extra_frontmatter: str = "",
    body: str = "# My Skill\n\nDoes stuff.",
) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(f"---\ndescription: {description}\n{extra_frontmatter}---\n\n{body}")
    return skill_md


def _make_command(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    extra_frontmatter: str = "",
    body: str = "# My Command\n\nDoes stuff.",
) -> Path:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    cmd_md = commands_dir / f"{name}.md"
    cmd_md.write_text(f"---\ndescription: {description}\n{extra_frontmatter}---\n\n{body}")
    return cmd_md


def _make_skill_block_scalar(tmp_path: Path, name: str) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\ndescription: |\n  Use when asked to do something.\n  More context here.\n\n"
        '  Trigger keywords: "foo", "bar"\n---\n\n# My Skill\n'
    )
    return skill_md


# =============================================================================
# _extract_short_desc
# =============================================================================


class TestExtractShortDesc:
    def test_single_line_description(self) -> None:
        text = "---\ndescription: Use when user asks for stuff.\n---\n# Body"
        assert _extract_short_desc(text) == "Use when user asks for stuff."

    def test_block_scalar_returns_first_line(self) -> None:
        text = (
            "---\ndescription: |\n  Use when asked to do something.\n  More context.\n---\n# Body"
        )
        result = _extract_short_desc(text)
        assert result == "Use when asked to do something."

    def test_truncates_to_80_chars(self) -> None:
        long_desc = "A" * 100
        text = f"---\ndescription: {long_desc}\n---\n# Body"
        result = _extract_short_desc(text)
        assert len(result) == 80

    def test_no_frontmatter_returns_empty(self) -> None:
        assert _extract_short_desc("# No frontmatter") == ""

    def test_no_description_field_returns_empty(self) -> None:
        text = "---\nname: my-skill\n---\n# Body"
        assert _extract_short_desc(text) == ""


# =============================================================================
# _insert_fields
# =============================================================================


class TestInsertFields:
    def test_inserts_name_when_absent(self) -> None:
        content = "---\ndescription: Use when stuff.\n---\n# Body\n"
        new_content, changed = _insert_fields(content, "my-skill", "Use when stuff.")
        assert changed is True
        assert "name: my-skill\n" in new_content

    def test_no_op_when_name_already_present(self) -> None:
        content = "---\nname: my-skill\ndescription: Use when stuff.\n---\n# Body\n"
        new_content, _ = _insert_fields(content, "my-skill", "Use when stuff.")
        assert new_content.count("name:") == 1

    def test_inserts_metadata_short_description(self) -> None:
        content = "---\ndescription: Use when stuff.\n---\n# Body\n"
        new_content, changed = _insert_fields(content, "my-skill", "Use when stuff.")
        assert changed is True
        assert "metadata:\n  short-description: Use when stuff." in new_content

    def test_no_op_when_short_description_already_present(self) -> None:
        content = (
            "---\nname: my-skill\ndescription: Use when stuff.\n"
            "metadata:\n  short-description: Use when stuff.\n---\n# Body\n"
        )
        new_content, changed = _insert_fields(content, "my-skill", "Use when stuff.")
        assert changed is False
        assert new_content == content

    def test_preserves_existing_frontmatter_fields(self) -> None:
        content = (
            '---\ndescription: Use when stuff.\nargument-hint: "[arg]"\n'
            "allowed-tools:\n  - Read\n---\n# Body\n"
        )
        new_content, _ = _insert_fields(content, "my-skill", "Use when stuff.")
        assert 'argument-hint: "[arg]"' in new_content
        assert "allowed-tools:" in new_content
        assert "- Read" in new_content

    def test_body_content_preserved_unchanged(self) -> None:
        body = "# My Skill\n\nDoes important things.\n\n---\n\nHorizontal rule in body.\n"
        content = f"---\ndescription: Use when stuff.\n---\n{body}"
        new_content, _ = _insert_fields(content, "my-skill", "Use when stuff.")
        assert body in new_content

    def test_no_frontmatter_returns_unchanged(self) -> None:
        content = "# No frontmatter\n"
        new_content, changed = _insert_fields(content, "my-skill", "desc")
        assert changed is False
        assert new_content == content


# =============================================================================
# _make_openai_yaml
# =============================================================================


class TestMakeOpenaiYaml:
    def test_contains_interface_block(self) -> None:
        result = _make_openai_yaml("Capture Issue", "Capture an issue from conversation.")
        assert result.startswith("interface:")

    def test_contains_display_name(self) -> None:
        result = _make_openai_yaml("Capture Issue", "Capture an issue from conversation.")
        assert 'display_name: "Capture Issue"' in result

    def test_contains_short_description(self) -> None:
        desc = "Capture an issue from conversation."
        result = _make_openai_yaml("Capture Issue", desc)
        assert f'short_description: "{desc}"' in result


# =============================================================================
# _title_case
# =============================================================================


class TestTitleCase:
    def test_single_word(self) -> None:
        assert _title_case("configure") == "Configure"

    def test_hyphenated_slug(self) -> None:
        assert _title_case("capture-issue") == "Capture Issue"

    def test_multi_word_slug(self) -> None:
        assert _title_case("ready-issue") == "Ready Issue"


# =============================================================================
# _process_skills
# =============================================================================


class TestProcessSkills:
    def test_dry_run_does_not_write_files(self, tmp_path: Path) -> None:
        skill_md = _make_skill(tmp_path, "my-skill")
        original = skill_md.read_text()

        adapted, skipped, errors = _process_skills(tmp_path / "skills", apply=False, quiet=True)

        assert adapted == 1
        assert skipped == 0
        assert errors == 0
        assert skill_md.read_text() == original
        assert not (skill_md.parent / "agents" / "openai.yaml").exists()

    def test_apply_writes_name_to_skill_md(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill")
        _process_skills(tmp_path / "skills", apply=True, quiet=True)
        content = (tmp_path / "skills" / "my-skill" / "SKILL.md").read_text()
        assert "name: my-skill\n" in content

    def test_apply_writes_metadata_short_description(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill", description="Use when stuff.")
        _process_skills(tmp_path / "skills", apply=True, quiet=True)
        content = (tmp_path / "skills" / "my-skill" / "SKILL.md").read_text()
        assert "metadata:\n  short-description: Use when stuff." in content

    def test_apply_creates_agents_openai_yaml(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill", description="Use when stuff.")
        _process_skills(tmp_path / "skills", apply=True, quiet=True)
        openai_yaml = tmp_path / "skills" / "my-skill" / "agents" / "openai.yaml"
        assert openai_yaml.exists()
        content = openai_yaml.read_text()
        assert "interface:" in content
        assert "display_name:" in content
        assert "short_description:" in content

    def test_skips_already_adapted_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "adapted-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: adapted-skill\ndescription: Use when stuff.\n"
            "metadata:\n  short-description: Use when stuff.\n---\n# Body\n"
        )
        (skill_dir / "agents").mkdir()
        (skill_dir / "agents" / "openai.yaml").write_text("interface:\n  display_name: x\n")

        adapted, skipped, errors = _process_skills(tmp_path / "skills", apply=True, quiet=True)
        assert adapted == 0
        assert skipped == 1
        assert errors == 0

    def test_skips_skill_without_description(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "no-desc-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: no-desc-skill\n---\n# Body\n")

        adapted, skipped, errors = _process_skills(tmp_path / "skills", apply=False, quiet=True)
        assert adapted == 0
        assert skipped == 1
        assert errors == 0

    def test_handles_block_scalar_description(self, tmp_path: Path) -> None:
        _make_skill_block_scalar(tmp_path, "block-skill")
        adapted, _, errors = _process_skills(tmp_path / "skills", apply=True, quiet=True)
        assert adapted == 1
        assert errors == 0
        content = (tmp_path / "skills" / "block-skill" / "SKILL.md").read_text()
        assert "short-description: Use when asked to do something." in content

    def test_multiple_skills_all_adapted(self, tmp_path: Path) -> None:
        for name in ["skill-a", "skill-b", "skill-c"]:
            _make_skill(tmp_path, name, description=f"Use when {name}.")
        adapted, skipped, errors = _process_skills(tmp_path / "skills", apply=True, quiet=True)
        assert adapted == 3
        assert skipped == 0
        assert errors == 0

    def test_errors_count_incremented_on_unreadable_file(self, tmp_path: Path) -> None:
        # Simulate missing file by creating directory without SKILL.md then patching glob
        skill_dir = tmp_path / "skills" / "ghost-skill"
        skill_dir.mkdir(parents=True)
        ghost_md = skill_dir / "SKILL.md"
        ghost_md.write_text("placeholder")

        import unittest.mock as mock
        from typing import Any

        original_read = Path.read_text

        def raise_on_ghost(self: Path, **kwargs: Any) -> str:
            if self == ghost_md:
                raise OSError("permission denied")
            return original_read(self, **kwargs)

        with mock.patch.object(Path, "read_text", raise_on_ghost):
            _, _, errors = _process_skills(tmp_path / "skills", apply=False, quiet=True)

        assert errors == 1


# =============================================================================
# main_adapt_skills_for_codex — entry-point
# =============================================================================


class TestMainAdaptSkillsForCodex:
    def test_dry_run_returns_zero_on_success(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill")

        with (
            patch.object(sys, "argv", ["ll-adapt-skills-for-codex", "--quiet"]),
            patch(
                "little_loops.cli.adapt_skills_for_codex._find_plugin_root",
                return_value=tmp_path,
            ),
        ):
            result = main_adapt_skills_for_codex()

        assert result == 0

    def test_missing_skills_dir_returns_one(self, tmp_path: Path) -> None:
        with (
            patch.object(sys, "argv", ["ll-adapt-skills-for-codex"]),
            patch(
                "little_loops.cli.adapt_skills_for_codex._find_plugin_root",
                return_value=tmp_path,
            ),
        ):
            result = main_adapt_skills_for_codex()

        assert result == 1

    def test_apply_flag_writes_files(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill")

        with (
            patch.object(sys, "argv", ["ll-adapt-skills-for-codex", "--apply", "--quiet"]),
            patch(
                "little_loops.cli.adapt_skills_for_codex._find_plugin_root",
                return_value=tmp_path,
            ),
        ):
            result = main_adapt_skills_for_codex()

        assert result == 0
        content = (tmp_path / "skills" / "my-skill" / "SKILL.md").read_text()
        assert "name: my-skill" in content


# =============================================================================
# Integration guard: real skills/*/SKILL.md (post-apply validation)
# =============================================================================


class TestRealSkillsIntegrationGuard:
    """After ll-adapt-skills-for-codex --apply, all real skills must be adapted."""

    def test_all_real_skills_have_name_field(self) -> None:
        skills_dir = Path(__file__).parent.parent.parent / "skills"
        if not skills_dir.exists():
            return
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            skill_name = skill_md.parent.name
            text = skill_md.read_text()
            import re

            fm_end = re.search(r"\n---\s*\n", text[3:])
            if not fm_end:
                continue
            fm_raw = text[3 : 3 + fm_end.start()]
            try:
                import yaml

                fm = yaml.safe_load(fm_raw) or {}
            except Exception:
                continue
            assert "name" in fm, (
                f"skills/{skill_name}/SKILL.md missing 'name:' frontmatter field. "
                "Run: ll-adapt-skills-for-codex --apply"
            )
            assert fm["name"] == skill_name, (
                f"skills/{skill_name}/SKILL.md has name: {fm['name']!r}, expected {skill_name!r}"
            )

    def test_all_real_skills_have_metadata_short_description(self) -> None:
        skills_dir = Path(__file__).parent.parent.parent / "skills"
        if not skills_dir.exists():
            return
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            skill_name = skill_md.parent.name
            text = skill_md.read_text()
            import re

            fm_end = re.search(r"\n---\s*\n", text[3:])
            if not fm_end:
                continue
            fm_raw = text[3 : 3 + fm_end.start()]
            try:
                import yaml

                fm = yaml.safe_load(fm_raw) or {}
            except Exception:
                continue
            metadata = fm.get("metadata") or {}
            assert isinstance(metadata, dict), (
                f"skills/{skill_name}/SKILL.md: metadata field is not a dict"
            )
            short_desc = metadata.get("short-description", "")
            assert short_desc, (
                f"skills/{skill_name}/SKILL.md missing metadata.short-description. "
                "Run: ll-adapt-skills-for-codex --apply"
            )
            assert len(short_desc) <= 80, (
                f"skills/{skill_name}/SKILL.md: metadata.short-description is "
                f"{len(short_desc)} chars (max 80): {short_desc!r}"
            )

    def test_all_real_skills_have_openai_yaml(self) -> None:
        skills_dir = Path(__file__).parent.parent.parent / "skills"
        if not skills_dir.exists():
            return
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            skill_name = skill_md.parent.name
            text = skill_md.read_text()
            import re

            fm_end = re.search(r"\n---\s*\n", text[3:])
            if not fm_end:
                continue
            fm_raw = text[3 : 3 + fm_end.start()]
            try:
                import yaml

                fm = yaml.safe_load(fm_raw) or {}
            except Exception:
                continue
            if fm.get("disable-model-invocation"):
                continue
            openai_yaml = skill_md.parent / "agents" / "openai.yaml"
            assert openai_yaml.exists(), (
                f"skills/{skill_name}/agents/openai.yaml missing. "
                "Run: ll-adapt-skills-for-codex --apply"
            )


# =============================================================================
# _synthesized_skill_md
# =============================================================================


class TestSynthesizedSkillMd:
    def test_contains_namespaced_name(self) -> None:
        result = _synthesized_skill_md("check-code", "Run code quality checks.")
        assert "name: ll-check-code\n" in result

    def test_contains_description_verbatim(self) -> None:
        desc = "Run code quality checks (lint, format, types, build)"
        result = _synthesized_skill_md("check-code", desc)
        assert f"description: {desc}\n" in result

    def test_contains_metadata_short_description(self) -> None:
        result = _synthesized_skill_md("check-code", "Run code quality checks.")
        assert "metadata:\n  short-description: Run code quality checks.\n" in result

    def test_short_description_truncated_to_80(self) -> None:
        long_desc = "A" * 200
        result = _synthesized_skill_md("foo", long_desc)
        # extract the short-description line
        for line in result.splitlines():
            if line.strip().startswith("short-description:"):
                short = line.split("short-description:", 1)[1].strip()
                assert len(short) == 80
                break
        else:
            raise AssertionError("short-description line missing")

    def test_body_references_source_command(self) -> None:
        result = _synthesized_skill_md("check-code", "Run code quality checks.")
        assert "commands/check-code.md" in result


# =============================================================================
# _process_commands
# =============================================================================


class TestProcessCommands:
    def test_dry_run_does_not_write_files(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "check-code")
        (tmp_path / "skills").mkdir()

        adapted, skipped, errors = _process_commands(
            tmp_path / "commands", tmp_path / "skills", apply=False, quiet=True
        )

        assert adapted == 1
        assert skipped == 0
        assert errors == 0
        assert not (tmp_path / "skills" / "ll-check-code").exists()

    def test_apply_writes_namespaced_skill_md(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "check-code", description="Run quality checks.")
        (tmp_path / "skills").mkdir()

        _process_commands(tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True)

        out_md = tmp_path / "skills" / "ll-check-code" / "SKILL.md"
        assert out_md.exists()
        content = out_md.read_text()
        assert "name: ll-check-code" in content
        assert "description: Run quality checks." in content
        assert "short-description: Run quality checks." in content

    def test_apply_writes_namespaced_openai_yaml(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "check-code", description="Run quality checks.")
        (tmp_path / "skills").mkdir()

        _process_commands(tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True)

        openai_yaml = tmp_path / "skills" / "ll-check-code" / "agents" / "openai.yaml"
        assert openai_yaml.exists()
        content = openai_yaml.read_text()
        assert 'display_name: "Check Code"' in content
        assert 'short_description: "Run quality checks."' in content

    def test_namespace_prefix_avoids_collision(self, tmp_path: Path) -> None:
        # A skill and a command share a base name "commit"; the command must
        # be installed under ll-commit to avoid colliding with skills/commit/.
        _make_command(tmp_path, "commit", description="Create git commit.")
        skill_dir = tmp_path / "skills" / "commit"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: commit\ndescription: Existing skill.\n---\n# Skill\n"
        )

        _process_commands(tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True)

        # Original skill untouched
        assert (
            (tmp_path / "skills" / "commit" / "SKILL.md")
            .read_text()
            .startswith("---\nname: commit\n")
        )
        # Command installed at ll-commit
        assert (tmp_path / "skills" / "ll-commit" / "SKILL.md").exists()

    def test_name_derived_from_stem_not_dir(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "scan-codebase", description="Scan it.")
        (tmp_path / "skills").mkdir()

        _process_commands(tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True)

        content = (tmp_path / "skills" / "ll-scan-codebase" / "SKILL.md").read_text()
        assert "name: ll-scan-codebase" in content

    def test_skips_already_adapted_command(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "check-code", description="Run quality checks.")
        out_dir = tmp_path / "skills" / "ll-check-code"
        out_dir.mkdir(parents=True)
        (out_dir / "SKILL.md").write_text(
            "---\nname: ll-check-code\ndescription: existing\n---\n# Body\n"
        )
        (out_dir / "agents").mkdir()
        (out_dir / "agents" / "openai.yaml").write_text("interface:\n  display_name: x\n")

        adapted, skipped, errors = _process_commands(
            tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True
        )

        assert adapted == 0
        assert skipped == 1
        assert errors == 0

    def test_skips_disable_model_invocation_command(self, tmp_path: Path) -> None:
        _make_command(
            tmp_path,
            "internal-cmd",
            description="Internal only.",
            extra_frontmatter="disable-model-invocation: true\n",
        )
        (tmp_path / "skills").mkdir()

        adapted, skipped, errors = _process_commands(
            tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True
        )

        assert adapted == 0
        assert skipped == 1
        assert errors == 0
        assert not (tmp_path / "skills" / "ll-internal-cmd").exists()

    def test_skips_command_without_description(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "no-desc.md").write_text("---\nargument-hint: '[x]'\n---\n# Body\n")
        (tmp_path / "skills").mkdir()

        adapted, skipped, errors = _process_commands(
            tmp_path / "commands", tmp_path / "skills", apply=False, quiet=True
        )
        assert adapted == 0
        assert skipped == 1
        assert errors == 0

    def test_missing_commands_dir_is_noop(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()
        adapted, skipped, errors = _process_commands(
            tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True
        )
        assert (adapted, skipped, errors) == (0, 0, 0)

    def test_multiple_commands_all_bridged(self, tmp_path: Path) -> None:
        for n in ["check-code", "scan-codebase", "commit"]:
            _make_command(tmp_path, n, description=f"Do {n}.")
        (tmp_path / "skills").mkdir()

        adapted, _, errors = _process_commands(
            tmp_path / "commands", tmp_path / "skills", apply=True, quiet=True
        )
        assert adapted == 3
        assert errors == 0
        for n in ["check-code", "scan-codebase", "commit"]:
            assert (tmp_path / "skills" / f"ll-{n}" / "SKILL.md").exists()


# =============================================================================
# Integration guard: real commands/*.md (post-apply validation)
# =============================================================================


class TestRealCommandsIntegrationGuard:
    """After ll-adapt-skills-for-codex --apply, every commands/*.md must be bridged
    to a skills/ll-<stem>/ entry with valid Codex frontmatter (unless the command
    carries disable-model-invocation: true).
    """

    def _repo_root(self) -> Path:
        return Path(__file__).parent.parent.parent

    def _read_frontmatter(self, md_path: Path) -> dict | None:
        import re

        import yaml

        text = md_path.read_text()
        if not text.startswith("---"):
            return None
        m = re.search(r"\n---\s*\n", text[3:])
        if not m:
            return None
        try:
            fm = yaml.safe_load(text[3 : 3 + m.start()]) or {}
        except Exception:
            return None
        return fm if isinstance(fm, dict) else None

    def test_every_command_has_bridged_skill(self) -> None:
        repo = self._repo_root()
        commands_dir = repo / "commands"
        skills_dir = repo / "skills"
        if not commands_dir.exists() or not skills_dir.exists():
            return

        for cmd_md in sorted(commands_dir.glob("*.md")):
            stem = cmd_md.stem
            fm = self._read_frontmatter(cmd_md)
            if fm is None:
                continue
            if fm.get("disable-model-invocation"):
                continue
            description = fm.get("description") or ""
            if not isinstance(description, str) or not description.strip():
                continue

            bridged = skills_dir / f"ll-{stem}" / "SKILL.md"
            assert bridged.exists(), (
                f"skills/ll-{stem}/SKILL.md missing for commands/{stem}.md. "
                "Run: ll-adapt-skills-for-codex --apply"
            )

    def test_every_bridged_skill_has_required_frontmatter(self) -> None:
        repo = self._repo_root()
        skills_dir = repo / "skills"
        if not skills_dir.exists():
            return

        for skill_md in sorted(skills_dir.glob("ll-*/SKILL.md")):
            stem = skill_md.parent.name.removeprefix("ll-")
            fm = self._read_frontmatter(skill_md)
            assert fm is not None, f"skills/ll-{stem}/SKILL.md frontmatter unparseable"
            assert fm.get("name") == f"ll-{stem}", (
                f"skills/ll-{stem}/SKILL.md name field is {fm.get('name')!r}, expected 'll-{stem}'"
            )
            metadata = fm.get("metadata") or {}
            assert isinstance(metadata, dict)
            short_desc = metadata.get("short-description", "")
            assert short_desc, (
                f"skills/ll-{stem}/SKILL.md missing metadata.short-description. "
                "Run: ll-adapt-skills-for-codex --apply"
            )
            assert len(short_desc) <= 80

    def test_every_bridged_skill_has_openai_yaml(self) -> None:
        repo = self._repo_root()
        skills_dir = repo / "skills"
        if not skills_dir.exists():
            return

        for skill_md in sorted(skills_dir.glob("ll-*/SKILL.md")):
            openai_yaml = skill_md.parent / "agents" / "openai.yaml"
            assert openai_yaml.exists(), (
                f"{skill_md.parent.name}/agents/openai.yaml missing. "
                "Run: ll-adapt-skills-for-codex --apply"
            )
