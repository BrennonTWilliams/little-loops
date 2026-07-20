"""Tests for little_loops.init.introspect — manifest-declared detection (FEAT-2703)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.init.detect import detect_project_type
from little_loops.init.introspect import IntrospectResult, introspect
from little_loops.issue_template import get_bundled_templates_dir


@pytest.fixture
def templates_dir() -> Path:
    return get_bundled_templates_dir()


@pytest.fixture
def python_template(templates_dir: Path, tmp_path: Path) -> object:
    (tmp_path / "pyproject.toml").touch()
    match = detect_project_type(tmp_path, templates_dir)
    (tmp_path / "pyproject.toml").unlink()
    return match


class TestPythonCommandDetection:
    def test_test_cmd_declared_via_pytest_ini_options(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
        )
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_cmd"]
        assert iv.provenance == "declared"
        assert "pytest" in iv.value
        assert "pytest.ini_options" in iv.evidence

    def test_lint_cmd_declared_via_ruff_table(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.lint_cmd"]
        assert iv.provenance == "declared"
        assert iv.value == "ruff check ."

    def test_format_cmd_declared_via_black_table_picks_black(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.black]\nline-length = 88\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.format_cmd"]
        assert iv.provenance == "declared"
        assert "black" in iv.value

    def test_format_cmd_prefers_ruff_over_black_when_both_present(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n\n[tool.black]\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.format_cmd"]
        assert "ruff" in iv.value

    def test_type_cmd_declared_via_mypy_table(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.mypy]\nstrict = true\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.type_cmd"]
        assert iv.provenance == "declared"
        assert iv.value == "mypy"

    def test_type_cmd_defaults_when_no_mypy_table(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.type_cmd"]
        assert iv.provenance == "default"
        assert iv.value == "mypy"  # still the template default value

    def test_no_pyproject_all_commands_default(
        self, tmp_path: Path, python_template: object
    ) -> None:
        result = introspect(tmp_path, python_template)
        assert isinstance(result, IntrospectResult)
        for field in ("test_cmd", "lint_cmd", "format_cmd", "type_cmd"):
            assert result.values[f"project.{field}"].provenance == "default"

    def test_declared_commands_are_full_shell_commands_without_command_options_pool(
        self, tmp_path: Path, templates_dir: Path
    ) -> None:
        """Regression: templates with no _meta.command_options (e.g. `generic`)
        must not fall back to a bare tool-name substring like "ruff"."""
        (tmp_path / "generic-marker.txt").touch()
        generic = detect_project_type(tmp_path, templates_dir)
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n\n[tool.mypy]\n")
        result = introspect(tmp_path, generic)
        assert result.values["project.lint_cmd"].value == "ruff check ."
        assert result.values["project.format_cmd"].value == "ruff format ."
        assert result.values["project.type_cmd"].value == "mypy"


class TestManifestDiscoveryNesting:
    def test_finds_pyproject_nested_one_level(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "pyproject.toml").write_text("[tool.ruff]\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.lint_cmd"]
        assert iv.provenance == "declared"
        assert iv.value == "ruff check ."

    def test_ambiguous_nested_pyproject_stays_default(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "a" / "pyproject.toml").write_text("[tool.ruff]\n")
        (tmp_path / "b" / "pyproject.toml").write_text("[tool.ruff]\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.lint_cmd"]
        assert iv.provenance == "default"


class TestNodeCommandDetection:
    def test_test_cmd_from_package_json_scripts_defaults_to_npm(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_cmd"]
        assert iv.provenance == "declared"
        assert iv.value == "npm run test"

    def test_test_cmd_uses_pnpm_when_lockfile_present(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))
        (tmp_path / "pnpm-lock.yaml").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_cmd"]
        assert iv.value == "pnpm run test"

    def test_type_cmd_matches_typecheck_script_alias(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"typecheck": "tsc --noEmit"}})
        )
        result = introspect(tmp_path, python_template)
        iv = result.values["project.type_cmd"]
        assert iv.provenance == "declared"
        assert iv.value == "npm run typecheck"

    def test_no_package_json_no_pyproject_all_default(
        self, tmp_path: Path, python_template: object
    ) -> None:
        result = introspect(tmp_path, python_template)
        for field in ("test_cmd", "lint_cmd", "format_cmd", "type_cmd"):
            assert result.values[f"project.{field}"].provenance == "default"


class TestSrcDirDetection:
    def test_src_star_init_marker_adopts_src(self, tmp_path: Path, python_template: object) -> None:
        pkg = tmp_path / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.provenance == "inferred"
        assert iv.value == "src/"

    def test_sole_top_level_package_dir_adopted(
        self, tmp_path: Path, python_template: object
    ) -> None:
        pkg = tmp_path / "scripts" / "little_loops"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.provenance == "inferred"
        assert iv.value == "scripts/"

    def test_top_level_dir_that_is_itself_the_package_adopted(
        self, tmp_path: Path, python_template: object
    ) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.provenance == "inferred"
        assert iv.value == "mypkg/"

    def test_tests_dir_with_init_py_not_treated_as_package_candidate(
        self, tmp_path: Path, python_template: object
    ) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.provenance == "inferred"
        assert iv.value == "mypkg/"

    def test_two_top_level_package_dirs_ambiguous_keeps_default(
        self, tmp_path: Path, python_template: object
    ) -> None:
        for name in ("scripts", "lib"):
            pkg = tmp_path / name / "pkg"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.provenance == "default"
        assert len(result.ambiguities) == 1
        ambiguity = result.ambiguities[0]
        assert ambiguity.field == "src_dir"
        assert set(ambiguity.candidates) == {"scripts/", "lib/"}

    def test_no_package_marker_keeps_default(self, tmp_path: Path, python_template: object) -> None:
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.provenance == "default"
        assert iv.value == python_template.data["project"]["src_dir"]


class TestFocusDirsDetection:
    def test_includes_adopted_src_dir_and_tests_dir(
        self, tmp_path: Path, python_template: object
    ) -> None:
        pkg = tmp_path / "scripts" / "little_loops"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        (tmp_path / "tests").mkdir()
        result = introspect(tmp_path, python_template)
        iv = result.values["scan.focus_dirs"]
        assert iv.provenance == "inferred"
        assert "scripts/" in iv.value
        assert "tests/" in iv.value

    def test_defaults_when_nothing_detected(self, tmp_path: Path, python_template: object) -> None:
        result = introspect(tmp_path, python_template)
        iv = result.values["scan.focus_dirs"]
        assert iv.provenance == "default"
        assert iv.value == python_template.data["scan"]["focus_dirs"]
