"""Tests for ll-issues sections sub-command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _write_config(temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))


def _invoke(argv: list[str]) -> tuple[int, str, str]:
    """Invoke main_issues() with given argv; returns (exit_code, stdout, stderr)."""
    with patch.object(sys, "argv", argv):
        from little_loops.cli import main_issues

        result = main_issues()
    return result


class TestSectionsJsonOutput:
    """Tests that valid types print JSON content to stdout."""

    @pytest.mark.parametrize("issue_type", ["bug", "feat", "enh", "epic"])
    def test_valid_type_prints_json(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
        issue_type: str,
    ) -> None:
        """Each valid type prints valid JSON to stdout, exit 0."""
        _write_config(temp_project_dir, sample_config)

        result = _invoke(["ll-issues", "sections", issue_type, "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        data = json.loads(out)
        assert isinstance(data, (dict, list))

    @pytest.mark.parametrize("issue_type", ["bug", "feat", "enh", "epic"])
    def test_uppercase_type_is_normalized(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
        issue_type: str,
    ) -> None:
        """Uppercase type input is normalized to lowercase for lookup."""
        _write_config(temp_project_dir, sample_config)

        result = _invoke(
            ["ll-issues", "sections", issue_type.upper(), "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert json.loads(out)  # non-empty JSON

    def test_alias_sec_works(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Alias 'll-issues sec' produces the same output as 'll-issues sections'."""
        _write_config(temp_project_dir, sample_config)

        result = _invoke(["ll-issues", "sec", "bug", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        json.loads(out)  # must be valid JSON


class TestSectionsPathFlag:
    """Tests for --path flag printing the absolute path instead of content."""

    @pytest.mark.parametrize("issue_type", ["bug", "feat", "enh", "epic"])
    def test_path_flag_prints_absolute_path(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
        issue_type: str,
    ) -> None:
        """--path prints absolute path to the JSON file, exit 0."""
        _write_config(temp_project_dir, sample_config)

        result = _invoke(
            ["ll-issues", "sections", issue_type, "--path", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        path = Path(out.strip())
        assert path.is_absolute()
        assert path.name == f"{issue_type}-sections.json"
        assert path.exists()


class TestSectionsInvalidType:
    """Tests for invalid or missing type arguments."""

    def test_invalid_type_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Invalid type exits 1 with error message to stderr."""
        _write_config(temp_project_dir, sample_config)

        result = _invoke(["ll-issues", "sections", "invalid", "--config", str(temp_project_dir)])
        _, err = capsys.readouterr()

        assert result == 1
        assert "invalid" in err.lower() or "invalid" in err

    def test_invalid_type_message_contains_type(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Error message mentions the bad type value."""
        _write_config(temp_project_dir, sample_config)

        result = _invoke(["ll-issues", "sections", "badtype", "--config", str(temp_project_dir)])
        _, err = capsys.readouterr()

        assert result == 1
        assert "badtype" in err


class TestSectionsTemplateMissing:
    """Tests for missing template file scenario."""

    def test_missing_template_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """When templates_dir has no matching file, exits 1 with error to stderr."""
        # Point templates_dir to an empty directory
        empty_templates = tmp_path / "empty-templates"
        empty_templates.mkdir()

        config_with_override = {**sample_config}
        config_with_override.setdefault("issues", {})
        config_with_override["issues"] = {
            **sample_config.get("issues", {}),
            "templates_dir": str(empty_templates),
        }
        _write_config(temp_project_dir, config_with_override)

        result = _invoke(["ll-issues", "sections", "bug", "--config", str(temp_project_dir)])
        _, err = capsys.readouterr()

        assert result == 1
        assert "not found" in err or "template" in err.lower()


class TestSectionsResolverTiers:
    """Tests that the 4-tier resolver precedence is respected."""

    def test_project_local_templates_override_bundled(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Per-project .ll/templates/ takes precedence over bundled templates."""
        _write_config(temp_project_dir, sample_config)

        # Write a custom template to <project>/.ll/templates/
        ll_templates = temp_project_dir / ".ll" / "templates"
        ll_templates.mkdir(parents=True, exist_ok=True)
        custom_content = '{"custom": true}'
        (ll_templates / "bug-sections.json").write_text(custom_content)

        result = _invoke(["ll-issues", "sections", "bug", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        data = json.loads(out)
        assert data.get("custom") is True

    def test_explicit_config_override_takes_highest_precedence(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Explicit issues.templates_dir in config overrides all other tiers."""
        explicit_templates = tmp_path / "explicit-templates"
        explicit_templates.mkdir()
        custom_content = '{"explicit": true}'
        (explicit_templates / "feat-sections.json").write_text(custom_content)

        config_override = {**sample_config}
        config_override["issues"] = {
            **sample_config.get("issues", {}),
            "templates_dir": str(explicit_templates),
        }
        _write_config(temp_project_dir, config_override)

        # Also write a project-local template to verify it's NOT used
        ll_templates = temp_project_dir / ".ll" / "templates"
        ll_templates.mkdir(parents=True, exist_ok=True)
        (ll_templates / "feat-sections.json").write_text('{"project_local": true}')

        result = _invoke(["ll-issues", "sections", "feat", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        data = json.loads(out)
        assert data.get("explicit") is True
