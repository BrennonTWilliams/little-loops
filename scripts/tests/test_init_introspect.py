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


class TestBaseToolToken:
    @pytest.mark.parametrize(
        ("cmd", "expected"),
        [
            ("pytest", "pytest"),
            ("python -m pytest -q", "pytest"),
            ("python3 -m pytest scripts/tests/", "pytest"),
            ("uv run pytest", "pytest"),
            ("poetry run ruff check .", "ruff"),
            ("npx tsc --noEmit", "tsc"),
            ("npm run lint", "lint"),
            ("pnpm run test", "test"),
            ("npm test", "test"),
            ("./gradlew test", "gradlew"),
            ("CI=1 pytest", "pytest"),
            ("cargo test", "cargo"),
            ("", ""),
        ],
    )
    def test_strips_launchers(self, cmd: str, expected: str) -> None:
        from little_loops.init.introspect import base_tool_token

        assert base_tool_token(cmd) == expected

    def test_unbalanced_quotes_fall_back_to_split(self) -> None:
        from little_loops.init.introspect import base_tool_token

        assert base_tool_token("pytest -k 'unterminated") == "pytest"


def _template_for(tmp_path: Path, marker: str, templates_dir: Path) -> object:
    """Detect the project-type template a *marker* file selects, then remove it."""
    path = tmp_path / marker
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    path.touch()
    match = detect_project_type(tmp_path, templates_dir)
    if created:
        path.unlink()
    return match


class TestNodeConfigFileDetection:
    def _node_template(self, tmp_path: Path, templates_dir: Path) -> object:
        return _template_for(tmp_path, "tsconfig.json", templates_dir)

    def test_tsconfig_without_typecheck_script_infers_tsc(
        self, tmp_path: Path, templates_dir: Path
    ) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        (tmp_path / "tsconfig.json").write_text("{}")
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        iv = result.values["project.type_cmd"]
        assert iv.provenance == "inferred"
        assert "tsc" in iv.value
        assert "tsconfig.json" in iv.evidence

    def test_declared_typecheck_script_beats_tsconfig(
        self, tmp_path: Path, templates_dir: Path
    ) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"typecheck": "tsc -p ."}}))
        (tmp_path / "tsconfig.json").write_text("{}")
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        iv = result.values["project.type_cmd"]
        assert iv.provenance == "declared"
        assert iv.value == "npm run typecheck"

    def test_eslint_and_prettier_config_files(self, tmp_path: Path, templates_dir: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        (tmp_path / "eslint.config.js").touch()
        (tmp_path / ".prettierrc").touch()
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert "eslint" in result.values["project.lint_cmd"].value
        assert result.values["project.lint_cmd"].provenance == "inferred"
        assert "prettier" in result.values["project.format_cmd"].value

    def test_biome_config_covers_lint_and_format(self, tmp_path: Path, templates_dir: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        (tmp_path / "biome.json").write_text("{}")
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert "biome" in result.values["project.lint_cmd"].value
        assert "biome" in result.values["project.format_cmd"].value

    def test_vitest_and_jest_configs(self, tmp_path: Path, templates_dir: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        (tmp_path / "vitest.config.ts").touch()
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert "vitest" in result.values["project.test_cmd"].value
        (tmp_path / "vitest.config.ts").unlink()
        (tmp_path / "jest.config.js").touch()
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert "jest" in result.values["project.test_cmd"].value

    def test_vite_config_only_implies_vitest_with_dependency(
        self, tmp_path: Path, templates_dir: Path
    ) -> None:
        (tmp_path / "vite.config.ts").touch()
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert result.values["project.test_cmd"].provenance == "default"
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {}, "devDependencies": {"vitest": "^1"}})
        )
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert "vitest" in result.values["project.test_cmd"].value

    def test_package_manager_field_beats_lockfile(
        self, tmp_path: Path, templates_dir: Path
    ) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "x"}, "packageManager": "pnpm@9.0.0"})
        )
        (tmp_path / "yarn.lock").touch()
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert result.values["project.test_cmd"].value == "pnpm run test"

    def test_bun_lock_text_variant(self, tmp_path: Path, templates_dir: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "x"}}))
        (tmp_path / "bun.lock").touch()
        result = introspect(tmp_path, self._node_template(tmp_path, templates_dir))
        assert result.values["project.test_cmd"].value == "bun run test"


class TestTaskRunnerDetection:
    def test_makefile_targets(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "Makefile").write_text(
            ".PHONY: test lint\ntest:\n\tpytest\nlint:\n\truff check .\nfmt:\n\truff format .\n"
        )
        result = introspect(tmp_path, python_template)
        assert result.values["project.test_cmd"].value == "make test"
        assert result.values["project.test_cmd"].provenance == "inferred"
        assert "Makefile target 'test'" in result.values["project.test_cmd"].evidence
        assert result.values["project.lint_cmd"].value == "make lint"
        assert result.values["project.format_cmd"].value == "make fmt"

    def test_makefile_ignores_variable_assignments(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "Makefile").write_text("test := 1\nbuild:\n\techo\n")
        result = introspect(tmp_path, python_template)
        assert result.values["project.test_cmd"].provenance == "default"
        assert result.values["project.build_cmd"].value == "make build"

    def test_justfile_recipes(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "justfile").write_text("test:\n    pytest\nlint flag='':\n    ruff\n")
        result = introspect(tmp_path, python_template)
        assert result.values["project.test_cmd"].value == "just test"
        assert result.values["project.lint_cmd"].value == "just lint"

    def test_tox_envs(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "tox.ini").write_text("[tox]\n[testenv]\ncommands = pytest\n[testenv:lint]\n")
        result = introspect(tmp_path, python_template)
        assert result.values["project.test_cmd"].value == "tox"
        assert result.values["project.lint_cmd"].value == "tox -e lint"

    def test_noxfile_sessions(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "noxfile.py").write_text(
            "import nox\n@nox.session\ndef tests(session):\n    pass\n"
            "@nox.session\ndef typecheck(session):\n    pass\n"
        )
        result = introspect(tmp_path, python_template)
        assert result.values["project.test_cmd"].value == "nox -s tests"
        assert result.values["project.type_cmd"].value == "nox -s typecheck"

    def test_declared_manifest_beats_task_runner(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
        result = introspect(tmp_path, python_template)
        assert result.values["project.test_cmd"].provenance == "declared"
        assert result.values["project.test_cmd"].value == "pytest"


class TestEcosystemDetection:
    def test_go_conventions(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "go.mod", templates_dir)
        (tmp_path / "go.mod").write_text("module example.com/x\n")
        result = introspect(tmp_path, template)
        assert result.values["project.test_cmd"].value == "go test ./..."
        assert result.values["project.test_cmd"].provenance == "inferred"
        assert result.values["project.lint_cmd"].value == "go vet ./..."
        assert result.values["project.build_cmd"].value == "go build ./..."
        (tmp_path / ".golangci.yml").touch()
        result = introspect(tmp_path, template)
        assert "golangci-lint" in result.values["project.lint_cmd"].value

    def test_rust_conventions(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "Cargo.toml", templates_dir)
        (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n")
        result = introspect(tmp_path, template)
        assert result.values["project.test_cmd"].value == "cargo test"
        assert "clippy" in result.values["project.lint_cmd"].value
        assert result.values["project.build_cmd"].value == "cargo build"
        assert result.values["project.build_cmd"].provenance == "inferred"

    def test_gradle_wrapper_preferred(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "build.gradle", templates_dir)
        (tmp_path / "build.gradle").touch()
        result = introspect(tmp_path, template)
        assert result.values["project.test_cmd"].value == "gradle test"
        (tmp_path / "gradlew").touch()
        result = introspect(tmp_path, template)
        assert result.values["project.test_cmd"].value == "./gradlew test"

    def test_dotnet_conventions(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "app.csproj", templates_dir)
        (tmp_path / "app.csproj").touch()
        result = introspect(tmp_path, template)
        assert result.values["project.test_cmd"].value == "dotnet test"
        assert result.values["project.build_cmd"].value == "dotnet build"


class TestBuildCmd:
    def test_node_build_script_declared(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "tsconfig.json", templates_dir)
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}))
        result = introspect(tmp_path, template)
        assert result.values["project.build_cmd"].value == "npm run build"
        assert result.values["project.build_cmd"].provenance == "declared"

    def test_build_cmd_reaches_config(self, tmp_path: Path, templates_dir: Path) -> None:
        from little_loops.init.core import build_config

        template = _template_for(tmp_path, "pyproject.toml", templates_dir)
        config = build_config(template, {"build_cmd": "make build"})
        assert config["project"]["build_cmd"] == "make build"


class TestFocusDirsEvidence:
    def test_evidence_names_only_detected_parts(
        self, tmp_path: Path, python_template: object
    ) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["scan.focus_dirs"]
        assert iv.evidence == "adopted src_dir"
        (tmp_path / "tests").mkdir()
        result = introspect(tmp_path, python_template)
        assert (
            result.values["scan.focus_dirs"].evidence
            == "adopted src_dir + detected tests/ directory"
        )
