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


# ---------------------------------------------------------------------------
# TestLabelsNotRequired — BUG-2395
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent.parent / "little_loops" / "templates"


class TestLabelsNotRequired:
    """Template guard: Labels must not be a required body section (BUG-2395).

    ENH-1392 moved labels to frontmatter. The *-sections.json templates must
    reflect this so every consumer (is_formatted(), ensure_formatted gate,
    format-issue --check) stops chasing a phantom body section.
    """

    ISSUE_TYPES = ["feat", "bug", "enh", "epic"]

    def test_labels_required_false_in_all_templates(self) -> None:
        """Labels.required must be false in all four issue-type templates (BUG-2395)."""
        for issue_type in self.ISSUE_TYPES:
            data = json.loads((TEMPLATES_DIR / f"{issue_type}-sections.json").read_text())
            labels_def = data.get("common_sections", {}).get("Labels", {})
            assert labels_def.get("required") is not True, (
                f"{issue_type}-sections.json: Labels.required must be false "
                f"(ENH-1392 moved labels to frontmatter) — got {labels_def.get('required')!r}"
            )

    def test_user_story_not_required_in_feat(self) -> None:
        """User Story must not have level='required' in feat-sections.json (BUG-2395).

        'User Story' was renamed to 'Use Case'; the deprecated entry must not block
        issues that use the canonical ## Use Case heading.
        """
        data = json.loads((TEMPLATES_DIR / "feat-sections.json").read_text())
        user_story = data.get("type_sections", {}).get("User Story", {})
        assert user_story.get("level") != "required", (
            "feat-sections.json: User Story.level must not be 'required' — "
            "issues use the canonical ## Use Case heading (BUG-2395)"
        )

    def test_required_set_non_empty_for_all_types(self) -> None:
        """Demoting Labels must not empty the required set (vacuous-True regression guard).

        is_formatted() returns True unconditionally when required is empty.
        Each type must retain at least one required section after demotion.
        """
        for issue_type in self.ISSUE_TYPES:
            data = json.loads((TEMPLATES_DIR / f"{issue_type}-sections.json").read_text())
            required: set[str] = set()
            for name, defn in data.get("common_sections", {}).items():
                if (
                    isinstance(defn, dict)
                    and defn.get("required") is True
                    and not defn.get("deprecated", False)
                ):
                    required.add(name)
            for name, defn in data.get("type_sections", {}).items():
                if (
                    isinstance(defn, dict)
                    and defn.get("level") == "required"
                    and not defn.get("deprecated", False)
                ):
                    required.add(name)
            assert len(required) >= 1, (
                f"{issue_type}-sections.json: required set is empty after demotion — "
                "is_formatted() would return vacuous True for all issues"
            )
