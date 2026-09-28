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
        assert iv.value == "mypy ."  # no src/ dir exists in tmp_path -> src_dir is "."

    def test_type_cmd_bare_when_mypy_files_set(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text('[tool.mypy]\nfiles = ["src"]\n')
        result = introspect(tmp_path, python_template)
        assert result.values["project.type_cmd"].value == "mypy"

    def test_type_cmd_follows_detected_src_dir(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.mypy]\nstrict = true\n")
        (tmp_path / "mypkg").mkdir()
        (tmp_path / "mypkg" / "__init__.py").write_text("")
        result = introspect(tmp_path, python_template)
        assert result.values["project.src_dir"].value == "mypkg/"
        assert result.values["project.type_cmd"].value == "mypy mypkg/"

    def test_type_cmd_defaults_when_no_mypy_table(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        result = introspect(tmp_path, python_template)
        iv = result.values["project.type_cmd"]
        assert iv.provenance == "default"
        assert iv.value == "mypy src/"  # still the template default value

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
        assert result.values["project.type_cmd"].value == "mypy ."  # no src/ dir exists


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
        assert iv.value == "."  # template default "src/" does not exist in tmp_path
        assert len(result.ambiguities) == 1
        ambiguity = result.ambiguities[0]
        assert ambiguity.field == "src_dir"
        assert set(ambiguity.candidates) == {"scripts/", "lib/"}

    def test_no_package_marker_keeps_default(self, tmp_path: Path, python_template: object) -> None:
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.provenance == "default"
        assert iv.value == "."  # template default "src/" does not exist; no root-level sources


class TestPyprojectSrcCandidateRootSpellings:
    """BUG-3631: setuptools 'where' and tsconfig rootDir/include root spellings."""

    def test_setuptools_where_dot_returns_root(self) -> None:
        from little_loops.init.introspect import _pyproject_src_candidate

        py_data = {"tool": {"setuptools": {"packages": {"find": {"where": ["."]}}}}}
        assert _pyproject_src_candidate(py_data) == "."

    def test_setuptools_where_nested_unchanged(self) -> None:
        from little_loops.init.introspect import _pyproject_src_candidate

        py_data = {"tool": {"setuptools": {"packages": {"find": {"where": ["src"]}}}}}
        assert _pyproject_src_candidate(py_data) == "src/"

    def test_tsconfig_root_dir_dot_returns_root(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _tsconfig_src_candidate

        (tmp_path / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"rootDir": "."}}))
        assert _tsconfig_src_candidate(tmp_path) == "."

    def test_tsconfig_root_dir_dot_slash_returns_root(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _tsconfig_src_candidate

        (tmp_path / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"rootDir": "./"}}))
        assert _tsconfig_src_candidate(tmp_path) == "."

    def test_tsconfig_root_dir_src_unchanged(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _tsconfig_src_candidate

        (tmp_path / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"rootDir": "src"}}))
        assert _tsconfig_src_candidate(tmp_path) == "src/"

    def test_tsconfig_include_glob_returns_root(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _tsconfig_src_candidate

        (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["**/*.ts"]}))
        assert _tsconfig_src_candidate(tmp_path) == "."

    def test_tsconfig_include_src_dir_unchanged(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _tsconfig_src_candidate

        (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["src/**/*"]}))
        assert _tsconfig_src_candidate(tmp_path) == "src/"


class TestTestDirDetection:
    """ENH-3495: project.test_dir must be introspected next to src_dir."""

    def test_detects_tests_dir(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "tests").mkdir()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_dir"]
        assert iv.provenance == "inferred"
        assert iv.value == "tests/"

    def test_detects_test_dir_singular(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "test").mkdir()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_dir"]
        assert iv.provenance == "inferred"
        assert iv.value == "test/"

    def test_prefers_tests_over_test_when_both_present(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "test").mkdir()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_dir"]
        assert iv.value == "tests/"

    def test_no_test_dir_keeps_default(self, tmp_path: Path, python_template: object) -> None:
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_dir"]
        assert iv.provenance == "default"
        assert iv.value == "tests/"
        assert iv.evidence == "no test files found; conventional location for new tests"


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
        assert iv.value == ["."]  # template default ["src/", "tests/"] does not exist


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


class TestExistingDirHelper:
    def test_dot_always_accepted(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _existing_dir

        assert _existing_dir(tmp_path, ".") == "."
        assert _existing_dir(tmp_path, "./") == "."

    def test_existing_relative_dir_accepted(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _existing_dir

        (tmp_path / "src").mkdir()
        assert _existing_dir(tmp_path, "src/") == "src/"

    def test_nonexistent_dir_rejected(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _existing_dir

        assert _existing_dir(tmp_path, "src/") is None

    def test_absolute_value_rejected(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _existing_dir

        assert _existing_dir(tmp_path, "/etc") is None

    def test_dotdot_value_rejected(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _existing_dir

        (tmp_path.parent / "sibling-does-not-matter").exists()
        assert _existing_dir(tmp_path, "../x") is None


class TestRootLayoutDetection:
    def test_top_level_python_module_is_root_layout(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _detect_root_layout

        (tmp_path / "main.py").touch()
        assert _detect_root_layout(tmp_path) is True

    def test_empty_dir_not_root_layout(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _detect_root_layout

        assert _detect_root_layout(tmp_path) is False

    def test_tooling_only_files_not_root_layout(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _detect_root_layout

        (tmp_path / "setup.py").touch()
        (tmp_path / "conftest.py").touch()
        (tmp_path / "vite.config.ts").touch()
        (tmp_path / ".eslintrc.js").touch()
        assert _detect_root_layout(tmp_path) is False

    def test_test_files_alone_not_root_layout(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _detect_root_layout

        (tmp_path / "test_foo.py").touch()
        assert _detect_root_layout(tmp_path) is False

    def test_top_level_go_file_is_root_layout(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _detect_root_layout

        (tmp_path / "main.go").touch()
        assert _detect_root_layout(tmp_path) is True


class TestNestedTestDirDetection:
    def test_finds_nested_scripts_tests(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _find_nested_test_dir

        (tmp_path / "scripts" / "tests").mkdir(parents=True)
        (tmp_path / "scripts" / "tests" / "test_foo.py").touch()
        assert _find_nested_test_dir(tmp_path, ".") == "scripts/tests/"

    def test_two_unrelated_nested_test_dirs_not_adopted(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _find_nested_test_dir

        (tmp_path / "frontend" / "test").mkdir(parents=True)
        (tmp_path / "frontend" / "test" / "foo.test.ts").touch()
        (tmp_path / "backend" / "tests").mkdir(parents=True)
        (tmp_path / "backend" / "tests" / "test_foo.py").touch()
        assert _find_nested_test_dir(tmp_path, ".") is None

    def test_dot_prefixed_dir_ignored(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _find_nested_test_dir

        (tmp_path / ".claude" / "tests").mkdir(parents=True)
        (tmp_path / ".claude" / "tests" / "test_foo.py").touch()
        assert _find_nested_test_dir(tmp_path, ".") is None

    def test_maven_layout_detected(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _find_nested_test_dir

        (tmp_path / "src" / "test" / "java").mkdir(parents=True)
        assert _find_nested_test_dir(tmp_path, "src/main/java/") == "src/test/java/"

    def test_src_dir_nested_tests_wins_over_one_level_probe(self, tmp_path: Path) -> None:
        from little_loops.init.introspect import _find_nested_test_dir

        (tmp_path / "scripts" / "tests").mkdir(parents=True)
        assert _find_nested_test_dir(tmp_path, "scripts/") == "scripts/tests/"


class TestSrcDirRootLayout:
    def test_flat_layout_yields_dot_inferred(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "app.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.value == "."
        assert iv.provenance == "inferred"

    def test_tooling_only_root_yields_dot_default(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "setup.py").touch()
        (tmp_path / "conftest.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.value == "."
        assert iv.provenance == "default"

    def test_flat_go_repo_yields_dot_inferred(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "go.mod", templates_dir)
        (tmp_path / "go.mod").write_text("module example.com/x\n")
        (tmp_path / "main.go").touch()
        result = introspect(tmp_path, template)
        iv = result.values["project.src_dir"]
        assert iv.value == "."
        assert iv.provenance == "inferred"
        assert iv.evidence == "root-level source files"

    def test_hatch_packages_naming_missing_dir_filtered_out(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "pyproject.toml").write_text('[tool.hatch.build]\npackages = ["ghost_pkg"]\n')
        result = introspect(tmp_path, python_template)
        iv = result.values["project.src_dir"]
        assert iv.value == "."

    def test_tsconfig_root_dir_naming_missing_dir_filtered_out(
        self, tmp_path: Path, templates_dir: Path
    ) -> None:
        template = _template_for(tmp_path, "tsconfig.json", templates_dir)
        (tmp_path / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"rootDir": "app"}}))
        result = introspect(tmp_path, template)
        iv = result.values["project.src_dir"]
        assert iv.value == "."


class TestTestDirNewBehavior:
    def test_nested_scripts_tests_detected(self, tmp_path: Path, python_template: object) -> None:
        (tmp_path / "scripts" / "little_loops").mkdir(parents=True)
        (tmp_path / "scripts" / "little_loops" / "__init__.py").touch()
        (tmp_path / "scripts" / "tests").mkdir()
        (tmp_path / "scripts" / "tests" / "test_foo.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_dir"]
        assert iv.value == "scripts/tests/"
        assert iv.provenance == "inferred"

    def test_go_colocated_tests_not_tests_fallback(
        self, tmp_path: Path, templates_dir: Path
    ) -> None:
        template = _template_for(tmp_path, "go.mod", templates_dir)
        (tmp_path / "go.mod").write_text("module example.com/x\n")
        (tmp_path / "main.go").touch()
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "foo_test.go").touch()
        result = introspect(tmp_path, template)
        iv = result.values["project.test_dir"]
        assert iv.value == "."
        assert iv.provenance == "inferred"

    def test_js_colocated_tests_under_src(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "tsconfig.json", templates_dir)
        (tmp_path / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"rootDir": "src"}}))
        src = tmp_path / "src"
        src.mkdir()
        (src / "index.ts").touch()
        (src / "index.test.ts").touch()
        result = introspect(tmp_path, template)
        assert result.values["project.src_dir"].value == "src/"
        iv = result.values["project.test_dir"]
        assert iv.value == "src/"
        assert iv.provenance == "inferred"

    def test_root_level_test_file_yields_dot(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "tsconfig.json", templates_dir)
        (tmp_path / "tsconfig.json").write_text("{}")
        (tmp_path / "foo.spec.ts").touch()
        result = introspect(tmp_path, template)
        iv = result.values["project.test_dir"]
        assert iv.value == "."
        assert iv.provenance == "inferred"

    def test_root_conftest_alone_falls_back_to_tests(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "conftest.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_dir"]
        assert iv.value == "tests/"
        assert iv.provenance == "default"

    def test_two_unrelated_nested_test_dirs_falls_back_to_colocated_search(
        self, tmp_path: Path, python_template: object
    ) -> None:
        """Neither ``frontend/test/`` nor ``backend/tests/`` is adopted as *the*
        nested test dir (ambiguous), but the broader bounded co-located search
        still finds a test file and proposes ``.`` rather than the phantom
        ``tests/`` — only an *empty* search falls all the way back to that."""
        (tmp_path / "frontend" / "test").mkdir(parents=True)
        (tmp_path / "frontend" / "test" / "foo.test.ts").touch()
        (tmp_path / "backend" / "tests").mkdir(parents=True)
        (tmp_path / "backend" / "tests" / "test_foo.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["project.test_dir"]
        assert iv.value == "."
        assert iv.provenance == "inferred"
        assert iv.evidence == "co-located test files"


class TestFocusDirsGuard:
    def test_ambiguous_src_plus_nested_tests_never_alone(
        self, tmp_path: Path, python_template: object
    ) -> None:
        for name in ("scripts", "lib"):
            pkg = tmp_path / name / "pkg"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").touch()
        (tmp_path / "scripts" / "tests").mkdir()
        (tmp_path / "scripts" / "tests" / "test_foo.py").touch()
        result = introspect(tmp_path, python_template)
        iv = result.values["scan.focus_dirs"]
        assert iv.value == ["."]

    def test_src_default_plus_top_level_tests_only_yields_dot(
        self, tmp_path: Path, python_template: object
    ) -> None:
        (tmp_path / "tests").mkdir()
        result = introspect(tmp_path, python_template)
        iv = result.values["scan.focus_dirs"]
        assert iv.value == ["."]

    def test_java_layout_focus_dirs(self, tmp_path: Path, templates_dir: Path) -> None:
        template = _template_for(tmp_path, "pom.xml", templates_dir)
        (tmp_path / "pom.xml").touch()
        (tmp_path / "src" / "main" / "java").mkdir(parents=True)
        (tmp_path / "src" / "test" / "java").mkdir(parents=True)
        result = introspect(tmp_path, template)
        iv = result.values["scan.focus_dirs"]
        assert iv.value == ["src/main/java/", "src/test/java/"]


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
