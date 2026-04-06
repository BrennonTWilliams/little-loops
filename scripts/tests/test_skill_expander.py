"""Tests for little_loops.skill_expander module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.skill_expander import (
    _find_plugin_root,
    _resolve_content_path,
    _substitute_arguments,
    _substitute_config,
    _substitute_relative_refs,
    expand_skill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(values: dict[str, str | None] | None = None) -> MagicMock:
    """Return a MagicMock BRConfig that resolves variables from *values*."""
    config = MagicMock()
    values = values or {}
    config.resolve_variable.side_effect = lambda path: values.get(path)
    return config


# ---------------------------------------------------------------------------
# _find_plugin_root
# ---------------------------------------------------------------------------


class TestFindPluginRoot:
    def test_uses_env_var_when_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        assert _find_plugin_root() == tmp_path

    def test_falls_back_to_package_parent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        root = _find_plugin_root()
        # skill_expander.py is at scripts/little_loops/skill_expander.py
        # three parents up → project root
        import little_loops.skill_expander as mod

        expected = Path(mod.__file__).resolve().parent.parent.parent
        assert root == expected


# ---------------------------------------------------------------------------
# _resolve_content_path
# ---------------------------------------------------------------------------


class TestResolveContentPath:
    def test_finds_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# skill")
        assert _resolve_content_path(tmp_path, "my-skill") == skill_file

    def test_falls_back_to_commands(self, tmp_path: Path) -> None:
        cmd_dir = tmp_path / "commands"
        cmd_dir.mkdir(parents=True)
        cmd_file = cmd_dir / "my-cmd.md"
        cmd_file.write_text("# cmd")
        assert _resolve_content_path(tmp_path, "my-cmd") == cmd_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        assert _resolve_content_path(tmp_path, "nonexistent") is None

    def test_prefers_skill_over_command(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "dual"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# skill")

        cmd_dir = tmp_path / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "dual.md").write_text("# cmd")

        assert _resolve_content_path(tmp_path, "dual") == skill_file


# ---------------------------------------------------------------------------
# _substitute_config
# ---------------------------------------------------------------------------


class TestSubstituteConfig:
    def test_replaces_known_variable(self) -> None:
        config = _make_config({"project.src_dir": "src/"})
        result = _substitute_config("Source: {{config.project.src_dir}}", config)
        assert result == "Source: src/"

    def test_blanks_unknown_variable(self) -> None:
        config = _make_config()
        result = _substitute_config("Val: {{config.missing.key}}", config)
        assert result == "Val: "

    def test_replaces_multiple_variables(self) -> None:
        config = _make_config({"a.b": "X", "c.d": "Y"})
        result = _substitute_config("{{config.a.b}} and {{config.c.d}}", config)
        assert result == "X and Y"

    def test_no_placeholders_returns_unchanged(self) -> None:
        config = _make_config()
        result = _substitute_config("plain text", config)
        assert result == "plain text"


# ---------------------------------------------------------------------------
# _substitute_relative_refs
# ---------------------------------------------------------------------------


class TestSubstituteRelativeRefs:
    def test_converts_existing_file(self, tmp_path: Path) -> None:
        ref = tmp_path / "templates.md"
        ref.write_text("# tmpl")
        content = "See [templates](templates.md) here"
        result = _substitute_relative_refs(content, tmp_path)
        assert f"({ref.resolve()})" in result

    def test_leaves_nonexistent_file_unchanged(self, tmp_path: Path) -> None:
        content = "See (missing.md)"
        result = _substitute_relative_refs(content, tmp_path)
        assert result == content

    def test_leaves_absolute_path_unchanged(self, tmp_path: Path) -> None:
        content = "See (/abs/path/file.md)"
        result = _substitute_relative_refs(content, tmp_path)
        assert result == content

    def test_leaves_urls_unchanged(self, tmp_path: Path) -> None:
        content = "See (https://example.com/file.md)"
        result = _substitute_relative_refs(content, tmp_path)
        assert result == content


# ---------------------------------------------------------------------------
# _substitute_arguments
# ---------------------------------------------------------------------------


class TestSubstituteArguments:
    def test_replaces_arguments_token(self) -> None:
        result = _substitute_arguments("Args: $ARGUMENTS", ["bug", "fix", "BUG-001"])
        assert result == "Args: bug fix BUG-001"

    def test_no_token_returns_unchanged(self) -> None:
        result = _substitute_arguments("no token here", ["x"])
        assert result == "no token here"

    def test_empty_args(self) -> None:
        result = _substitute_arguments("Args: $ARGUMENTS", [])
        assert result == "Args: "


# ---------------------------------------------------------------------------
# expand_skill (integration)
# ---------------------------------------------------------------------------


class TestExpandSkill:
    def _make_plugin_root(self, tmp_path: Path, content: str, *, as_skill: bool = True) -> Path:
        """Write a SKILL.md or command file and return the plugin root."""
        if as_skill:
            skill_dir = tmp_path / "skills" / "test-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(content)
        else:
            cmd_dir = tmp_path / "commands"
            cmd_dir.mkdir(parents=True)
            (cmd_dir / "test-skill.md").write_text(content)
        return tmp_path

    def test_basic_expansion(self, tmp_path: Path) -> None:
        content = "# Skill\nDir: {{config.issues.base_dir}}\n$ARGUMENTS\n"
        plugin_root = self._make_plugin_root(tmp_path, content)
        config = _make_config({"issues.base_dir": ".issues"})

        with patch("little_loops.skill_expander._find_plugin_root", return_value=plugin_root):
            result = expand_skill("test-skill", ["bug", "fix"], config)

        assert result is not None
        assert "{{config." not in result
        assert "$ARGUMENTS" not in result
        assert ".issues" in result
        assert "bug fix" in result

    def test_strips_frontmatter(self, tmp_path: Path) -> None:
        content = "---\nname: test\n---\n# Body\n$ARGUMENTS\n"
        plugin_root = self._make_plugin_root(tmp_path, content)
        config = _make_config()

        with patch("little_loops.skill_expander._find_plugin_root", return_value=plugin_root):
            result = expand_skill("test-skill", ["arg"], config)

        assert result is not None
        assert "name: test" not in result
        assert "# Body" in result

    def test_returns_none_when_skill_not_found(self, tmp_path: Path) -> None:
        config = _make_config()
        with patch("little_loops.skill_expander._find_plugin_root", return_value=tmp_path):
            result = expand_skill("nonexistent", [], config)
        assert result is None

    def test_returns_none_on_exception(self, tmp_path: Path) -> None:
        config = _make_config()
        with patch(
            "little_loops.skill_expander._find_plugin_root",
            side_effect=RuntimeError("boom"),
        ):
            result = expand_skill("any", [], config)
        assert result is None

    def test_converts_relative_refs(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "templates.md").write_text("# templates")
        (skill_dir / "SKILL.md").write_text("See [tmpl](templates.md)\n$ARGUMENTS\n")
        config = _make_config()

        with patch("little_loops.skill_expander._find_plugin_root", return_value=tmp_path):
            result = expand_skill("test-skill", [], config)

        assert result is not None
        assert "(templates.md)" not in result
        assert str(skill_dir / "templates.md") in result


class TestExpandSkillAgainstRealManageIssue:
    """Integration test against the real manage-issue skill file."""

    def test_manage_issue_expansion_has_no_raw_tokens(self) -> None:
        """Expanded manage-issue content must contain no {{config. or $ARGUMENTS tokens."""
        from little_loops.config import BRConfig

        try:
            # Load real project config from the project root
            project_root = Path(__file__).resolve().parent.parent.parent
            config = BRConfig(project_root)
        except Exception:
            pytest.skip("Could not load BRConfig from project root")

        result = expand_skill("manage-issue", ["bug", "implement", "BUG-001"], config)

        if result is None:
            pytest.skip("manage-issue skill file not found (expected in skills/manage-issue/SKILL.md)")

        assert "{{config." not in result, "Unresolved {{config.xxx}} placeholders remain"
        assert "$ARGUMENTS" not in result, "$ARGUMENTS token was not substituted"
        assert "(templates.md)" not in result, "Relative (templates.md) reference was not resolved"
