"""Tests for little_loops.init — detection, config building, validation, writers."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.init.cli import _plugin_root
from little_loops.init.core import SCHEMA_URL, build_config, schema_default
from little_loops.init.detect import (
    TemplateMatch,
    _find_templates_dir,
    _load_templates,
    detect_project_type,
)
from little_loops.init.validate import (
    _check_jq,
    _check_little_loops_version,
    _check_python3,
    _check_pyyaml,
    _check_tool_commands,
    validate_deps,
)
from little_loops.init.writers import (
    _GITIGNORE_ENTRIES,
    _LL_PERMISSIONS,
    deploy_design_tokens,
    deploy_goals,
    install_codex_adapter,
    load_existing_config,
    make_issue_dirs,
    make_learning_tests_dir,
    merge_settings,
    merge_with_existing,
    read_adapter_gen_version,
    strip_none_leaves,
    update_gitignore,
    write_claude_md,
    write_config,
)
from little_loops.issue_template import get_bundled_templates_dir

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_PROJECT_ROOT = Path(__file__).parent.parent.parent  # scripts/tests/.. → project root


@pytest.fixture
def templates_dir() -> Path:
    """Return the in-package templates/ directory."""
    return get_bundled_templates_dir()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Return a scratch project root directory."""
    return tmp_path


@pytest.fixture
def fake_templates(tmp_path: Path) -> Path:
    """Minimal in-memory templates/ directory with two templates + generic fallback."""
    tdir = tmp_path / "templates"
    tdir.mkdir()

    # python-like template
    (tdir / "python-generic.json").write_text(
        json.dumps(
            {
                "_meta": {
                    "name": "Python (Generic)",
                    "description": "Python project",
                    "detect": ["pyproject.toml", "setup.py", "requirements.txt"],
                    "tags": ["python"],
                },
                "project": {
                    "src_dir": "src/",
                    "test_cmd": "pytest",
                    "lint_cmd": "ruff check .",
                    "type_cmd": "mypy",
                    "format_cmd": "ruff format .",
                    "build_cmd": None,
                    "run_cmd": None,
                },
                "scan": {
                    "focus_dirs": ["src/", "tests/"],
                    "exclude_patterns": ["**/__pycache__/**"],
                },
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                        "enhancements": {
                            "prefix": "ENH",
                            "dir": "enhancements",
                            "action": "improve",
                        },
                        "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
                    },
                },
                "product": {"enabled": False},
                "analytics": {"enabled": False},
                "context_monitor": {"enabled": True},
            }
        )
    )

    # JS/TS template with detect_exclude
    (tdir / "typescript.json").write_text(
        json.dumps(
            {
                "_meta": {
                    "name": "TypeScript",
                    "description": "TypeScript project",
                    "detect": ["tsconfig.json"],
                    "tags": ["typescript"],
                },
                "project": {
                    "src_dir": "src/",
                    "test_cmd": "npm test",
                    "lint_cmd": "npm run lint",
                    "type_cmd": "tsc --noEmit",
                    "format_cmd": None,
                    "build_cmd": "npm run build",
                    "run_cmd": None,
                },
                "scan": {"focus_dirs": ["src/"], "exclude_patterns": ["**/node_modules/**"]},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                        "enhancements": {
                            "prefix": "ENH",
                            "dir": "enhancements",
                            "action": "improve",
                        },
                        "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
                    },
                },
                "product": {"enabled": False},
                "analytics": {"enabled": False},
                "context_monitor": {"enabled": True},
            }
        )
    )

    # JS template with detect_exclude (tsconfig.json excludes it)
    (tdir / "javascript.json").write_text(
        json.dumps(
            {
                "_meta": {
                    "name": "JavaScript (Node.js)",
                    "description": "JavaScript project",
                    "detect": ["package.json"],
                    "detect_exclude": ["tsconfig.json"],
                    "tags": ["javascript"],
                },
                "project": {
                    "src_dir": "src/",
                    "test_cmd": "npm test",
                    "lint_cmd": "npm run lint",
                    "type_cmd": None,
                    "format_cmd": None,
                    "build_cmd": None,
                    "run_cmd": "npm start",
                },
                "scan": {"focus_dirs": ["src/"], "exclude_patterns": ["**/node_modules/**"]},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                        "enhancements": {
                            "prefix": "ENH",
                            "dir": "enhancements",
                            "action": "improve",
                        },
                        "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
                    },
                },
                "product": {"enabled": False},
                "analytics": {"enabled": False},
                "context_monitor": {"enabled": True},
            }
        )
    )

    # Generic fallback
    (tdir / "generic.json").write_text(
        json.dumps(
            {
                "_meta": {
                    "name": "Generic",
                    "description": "Fallback",
                    "detect": [],
                    "priority": -1,
                    "tags": ["generic"],
                },
                "project": {
                    "src_dir": "src/",
                    "test_cmd": None,
                    "lint_cmd": None,
                    "type_cmd": None,
                    "format_cmd": None,
                    "build_cmd": None,
                    "run_cmd": None,
                },
                "scan": {"focus_dirs": ["src/", "lib/"], "exclude_patterns": []},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                        "enhancements": {
                            "prefix": "ENH",
                            "dir": "enhancements",
                            "action": "improve",
                        },
                        "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
                    },
                },
                "product": {"enabled": False},
                "analytics": {"enabled": False},
                "context_monitor": {"enabled": True},
            }
        )
    )

    return tdir


def _make_match(tdir: Path, filename: str) -> TemplateMatch:
    """Load a TemplateMatch from *tdir/filename*."""
    path = tdir / filename
    data = json.loads(path.read_text())
    meta = data["_meta"]
    return TemplateMatch(
        name=meta["name"],
        filename=filename,
        template_path=path,
        meta=meta,
        data=data,
    )


# ===========================================================================
# TestPluginRoot
# ===========================================================================


class TestPluginRoot:
    def test_uses_env_var_when_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        assert _plugin_root() == tmp_path

    def test_falls_back_to_file_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        root = _plugin_root()
        import little_loops.init.cli as mod

        expected = Path(mod.__file__).resolve().parent.parent.parent.parent
        assert root == expected


# ===========================================================================
# TestFindTemplatesDir
# ===========================================================================


class TestFindTemplatesDir:
    def test_uses_env_var_when_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "templates").mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        assert _find_templates_dir() == tmp_path / "templates"

    def test_falls_back_to_bundled_when_env_var_has_no_templates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        tdir = _find_templates_dir()
        import little_loops.init.detect as mod

        expected = Path(mod.__file__).resolve().parent.parent / "templates"
        assert tdir == expected

    def test_falls_back_to_file_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        tdir = _find_templates_dir()
        import little_loops.init.detect as mod

        expected = Path(mod.__file__).resolve().parent.parent / "templates"
        assert tdir == expected


# ===========================================================================
# TestDetectProjectType
# ===========================================================================


class TestDetectProjectType:
    def test_detects_python_via_pyproject_toml(
        self, tmp_project: Path, fake_templates: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        assert match.filename == "python-generic.json"
        assert match.name == "Python (Generic)"

    def test_detects_typescript_via_tsconfig(self, tmp_project: Path, fake_templates: Path) -> None:
        (tmp_project / "tsconfig.json").touch()
        match = detect_project_type(tmp_project, fake_templates)
        assert match.filename == "typescript.json"

    def test_js_excluded_by_tsconfig(self, tmp_project: Path, fake_templates: Path) -> None:
        """package.json + tsconfig.json → TypeScript wins; JavaScript excluded."""
        (tmp_project / "package.json").touch()
        (tmp_project / "tsconfig.json").touch()
        match = detect_project_type(tmp_project, fake_templates)
        assert match.filename == "typescript.json"

    def test_js_matched_without_tsconfig(self, tmp_project: Path, fake_templates: Path) -> None:
        (tmp_project / "package.json").touch()
        match = detect_project_type(tmp_project, fake_templates)
        assert match.filename == "javascript.json"

    def test_fallback_to_generic_on_no_match(self, tmp_project: Path, fake_templates: Path) -> None:
        match = detect_project_type(tmp_project, fake_templates)
        assert match.filename == "generic.json"
        assert match.name == "Generic"

    def test_section_templates_excluded(self, fake_templates: Path) -> None:
        """bug-sections.json etc. must not appear as project-type candidates."""
        (fake_templates / "bug-sections.json").write_text(
            json.dumps({"title": "Bug", "sections": []})
        )
        templates = _load_templates(fake_templates)
        filenames = {tmpl_path.name for _, tmpl_path in templates}
        assert "bug-sections.json" not in filenames

    def test_raises_when_no_templates_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty_templates"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            detect_project_type(tmp_path, empty)

    def test_warns_and_returns_generic_when_templates_dir_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        missing_dir = tmp_path / "nonexistent_templates"
        # Do NOT mkdir — we want a non-existent dir, not an empty dir.
        match = detect_project_type(tmp_path, missing_dir)
        assert match.filename == "generic.json"
        assert match.name == "Generic"
        err = capsys.readouterr().err
        assert "Warning" in err
        assert "templates/" in err

    def test_real_templates_dir_loads(self, templates_dir: Path, tmp_project: Path) -> None:
        """Smoke test: the real templates/ directory is readable and returns a match."""
        match = detect_project_type(tmp_project, templates_dir)
        assert match.filename  # non-empty filename
        assert match.name  # non-empty human name


# ===========================================================================
# TestDetectAllRealTemplates — parity coverage for all 9 project types
# ===========================================================================


@pytest.mark.parametrize(
    "indicator_files,expected_filename",
    [
        (["pyproject.toml"], "python-generic.json"),
        (["setup.py"], "python-generic.json"),
        (["requirements.txt"], "python-generic.json"),
        (["tsconfig.json"], "typescript.json"),
        (["package.json"], "javascript.json"),  # no tsconfig.json
        (["go.mod"], "go.json"),
        (["Cargo.toml"], "rust.json"),
        (["pom.xml"], "java-maven.json"),
        (["build.gradle"], "java-gradle.json"),
        ([], "generic.json"),  # fallback
    ],
)
def test_real_template_detection(
    indicator_files: list[str],
    expected_filename: str,
    tmp_project: Path,
    templates_dir: Path,
) -> None:
    for fname in indicator_files:
        (tmp_project / fname).touch()
    match = detect_project_type(tmp_project, templates_dir)
    assert match.filename == expected_filename, (
        f"Expected {expected_filename!r}, got {match.filename!r} (indicators: {indicator_files})"
    )


# ===========================================================================
# TestBuildConfig
# ===========================================================================


class TestBuildConfig:
    def test_schema_url_present(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert config["$schema"] == SCHEMA_URL

    def test_core_sections_present(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "project" in config
        assert "issues" in config
        assert "scan" in config

    def test_project_name_injected(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"project_name": "my-app"})
        assert config["project"]["name"] == "my-app"

    def test_learning_tests_disabled_by_default(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "learning_tests" in config
        assert config["learning_tests"]["enabled"] is False

    def test_learning_tests_enabled_via_choice(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"learning_tests_enabled": True})
        assert config["learning_tests"]["enabled"] is True

    def test_analytics_disabled_by_default(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert config["analytics"] == {"enabled": False}
        assert "capture" not in config["analytics"]

    def test_analytics_enabled_via_choice(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"analytics_enabled": True})
        assert config["analytics"]["enabled"] is True
        assert "capture" in config["analytics"]

    def test_product_disabled_by_default(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "product" not in config

    def test_product_omitted_when_disabled(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"product_enabled": False})
        assert "product" not in config

    def test_product_enabled_via_choice(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"product_enabled": True})
        assert config.get("product", {}).get("enabled") is True

    def test_context_monitor_enabled_by_default(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert config.get("context_monitor", {}).get("enabled") is True

    def test_context_monitor_omitted_when_disabled(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"context_monitor_enabled": False})
        assert "context_monitor" not in config

    def test_analytics_disabled(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"analytics_enabled": False})
        assert config["analytics"] == {"enabled": False}
        assert "capture" not in config["analytics"]

    def test_issues_section_from_template(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert config["issues"]["base_dir"] == ".issues"
        assert "bugs" in config["issues"]["categories"]

    def test_history_session_digest_written(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "history" in config
        assert config["history"]["session_digest"]["enabled"] is True

    def test_history_session_digest_defaults(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        sd = config["history"]["session_digest"]
        assert sd["days"] == 7
        assert "char_cap" not in sd

    def test_history_session_digest_disabled_via_choice(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"session_digest_enabled": False})
        assert config["history"]["session_digest"]["enabled"] is False

    def test_loops_run_defaults_present(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "loops" in config
        assert "run_defaults" in config["loops"]

    def test_loops_run_defaults_keys(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        rd = config["loops"]["run_defaults"]
        assert rd["clear"] is False
        assert "show_diagrams" not in rd
        assert "mode" not in rd

    def test_loops_run_defaults_override_via_choices(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(
            match, {"loop_clear_default": True, "loop_show_diagrams_default": "clean"}
        )
        rd = config["loops"]["run_defaults"]
        assert rd["clear"] is True
        assert rd["show_diagrams"] == "clean"
        assert "mode" not in rd

    # --- opt-in toggles (decisions / scratch_pad / session_capture) ---

    def test_decisions_omitted_by_default(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "decisions" not in config

    def test_decisions_written_when_enabled(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"decisions_enabled": True})
        assert config["decisions"] == {"enabled": True}

    def test_scratch_pad_omitted_by_default(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "scratch_pad" not in config

    def test_scratch_pad_written_when_enabled(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"scratch_pad_enabled": True})
        assert config["scratch_pad"] == {"enabled": True}

    def test_session_capture_omitted_by_default(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "session_capture" not in config

    def test_session_capture_written_when_enabled(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"session_capture_enabled": True})
        assert config["session_capture"] == {"enabled": True}

    # --- prompt_optimization opt-out (default-on feature) ---

    def test_prompt_optimization_omitted_by_default(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "prompt_optimization" not in config

    def test_prompt_optimization_omitted_when_explicitly_enabled(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"prompt_optimization_enabled": True})
        assert "prompt_optimization" not in config

    def test_prompt_optimization_disabled_writes_enabled_false(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"prompt_optimization_enabled": False})
        assert config["prompt_optimization"] == {"enabled": False}

    def test_build_config_emits_no_null_leaves(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        """The config generated by build_config must contain zero None values after stripping."""
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)

        choices = {"loop_show_diagrams_default": None}
        config = build_config(match, choices)

        # Recursive leaf scan — no value at any depth may be None.
        def _scanner(obj: object, path: str = "$") -> list[str]:
            found: list[str] = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    probe = f"{path}.{k}"
                    if v is None:
                        found.append(probe)
                    elif isinstance(v, dict):
                        found += _scanner(v, probe)
                    elif isinstance(v, list):
                        # list elements pass through — None inside lists is not stripped
                        pass
            return found

        null_paths = _scanner(config)
        assert null_paths == [], f"Expected zero null leaves, found: {null_paths}"


# ===========================================================================
# TestBuildConfigSchemaParity
# ===========================================================================


class TestBuildConfigSchemaParity:
    """Regression guard for ENH-2434.

    Every value build_config() emits without a choices override must equal
    config-schema.json's declared default at the matching dotted path — the
    drift class behind ENH-2298 and BUG-2321. Sections build_config() derives
    from the project template (project/issues/scan), not the schema, are out
    of scope for this comparison.
    """

    _TEMPLATE_DERIVED = {"$schema", "project", "issues", "scan"}

    def test_emitted_defaults_match_schema(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)  # no choices — pure schema-sourced baseline

        mismatches: list[str] = []

        def _walk(obj: object, path: str) -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    _walk(value, f"{path}.{key}")
                return
            try:
                expected = schema_default(path)
            except KeyError:
                return  # no schema default declared at this path — nothing to compare
            if obj != expected:
                mismatches.append(f"{path}: build_config()={obj!r} schema default={expected!r}")

        for key, value in config.items():
            if key in self._TEMPLATE_DERIVED:
                continue
            _walk(value, key)

        assert mismatches == [], (
            "core.py literal(s) drifted from config-schema.json:\n" + "\n".join(mismatches)
        )

    def test_analytics_capture_defaults_match_schema_when_enabled(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        # The no-choices baseline above leaves analytics disabled (schema default),
        # so "capture" is never emitted there — exercise the enabled branch directly.
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"analytics_enabled": True})
        capture = config["analytics"]["capture"]
        for key, value in capture.items():
            assert value == schema_default(f"analytics.capture.{key}")


# ===========================================================================
# TestWriteConfig
# ===========================================================================


class TestWriteConfig:
    def test_writes_json_file(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        config = {"$schema": SCHEMA_URL, "project": {"name": "test"}}
        write_config(config, ll_dir)
        assert (ll_dir / "ll-config.json").exists()
        data = json.loads((ll_dir / "ll-config.json").read_text())
        assert data["project"]["name"] == "test"

    def test_creates_ll_dir(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        assert not ll_dir.exists()
        write_config({"$schema": SCHEMA_URL}, ll_dir)
        assert ll_dir.exists()

    def test_dry_run_no_write(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        ll_dir = tmp_path / ".ll"
        write_config({"$schema": SCHEMA_URL}, ll_dir, dry_run=True)
        assert not (ll_dir / "ll-config.json").exists()
        out = capsys.readouterr().out
        assert "$schema" in out


# ===========================================================================
# TestUpdateGitignore
# ===========================================================================


class TestUpdateGitignore:
    def test_creates_gitignore_with_entries(self, tmp_project: Path) -> None:
        changed = update_gitignore(tmp_project)
        assert changed is True
        content = (tmp_project / ".gitignore").read_text()
        for entry in _GITIGNORE_ENTRIES:
            assert entry in content

    def test_idempotent_when_entries_present(self, tmp_project: Path) -> None:
        update_gitignore(tmp_project)
        changed = update_gitignore(tmp_project)
        assert changed is False

    def test_appends_to_existing_gitignore(self, tmp_project: Path) -> None:
        (tmp_project / ".gitignore").write_text("*.pyc\n__pycache__/\n")
        update_gitignore(tmp_project)
        content = (tmp_project / ".gitignore").read_text()
        assert "*.pyc" in content
        assert _GITIGNORE_ENTRIES[0] in content

    def test_dry_run_no_write(self, tmp_project: Path, capsys: pytest.CaptureFixture) -> None:
        changed = update_gitignore(tmp_project, dry_run=True)
        assert changed is True
        assert not (tmp_project / ".gitignore").exists()
        assert "[update]" in capsys.readouterr().out

    def test_partial_entries_only_appends_missing(self, tmp_project: Path) -> None:
        existing = _GITIGNORE_ENTRIES[0] + "\n"
        (tmp_project / ".gitignore").write_text(existing)
        update_gitignore(tmp_project)
        content = (tmp_project / ".gitignore").read_text()
        # Should appear exactly once
        for entry in _GITIGNORE_ENTRIES:
            assert content.count(entry) == 1


# ===========================================================================
# TestMergeSettings
# ===========================================================================


class TestMergeSettings:
    def test_creates_settings_file(self, tmp_project: Path) -> None:
        merge_settings(tmp_project)
        target = tmp_project / ".claude" / "settings.local.json"
        assert target.exists()
        data = json.loads(target.read_text())
        allow = data["permissions"]["allow"]
        assert "Bash(ll-auto:*)" in allow

    def test_all_canonical_permissions_present(self, tmp_project: Path) -> None:
        merge_settings(tmp_project)
        target = tmp_project / ".claude" / "settings.local.json"
        data = json.loads(target.read_text())
        allow = data["permissions"]["allow"]
        for perm in _LL_PERMISSIONS:
            assert perm in allow, f"Missing permission: {perm}"

    def test_idempotent_on_re_run(self, tmp_project: Path) -> None:
        merge_settings(tmp_project)
        merge_settings(tmp_project)
        target = tmp_project / ".claude" / "settings.local.json"
        data = json.loads(target.read_text())
        allow = data["permissions"]["allow"]
        # No duplicates
        assert len(allow) == len(set(allow))

    def test_preserves_unrelated_existing_entries(self, tmp_project: Path) -> None:
        target = tmp_project / ".claude" / "settings.local.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"permissions": {"allow": ["Bash(git:*)", "Read(*)"]}}))
        merge_settings(tmp_project)
        data = json.loads(target.read_text())
        allow = data["permissions"]["allow"]
        assert "Bash(git:*)" in allow
        assert "Read(*)" in allow

    def test_removes_stale_canonical_ll_entries(self, tmp_project: Path) -> None:
        target = tmp_project / ".claude" / "settings.local.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        # Seed a canonical entry that should be de-duped (not doubled) on re-init.
        target.write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": ["Bash(ll-action:*)", "Write(.ll/ll-continue-prompt.md)"]
                    }
                }
            )
        )
        merge_settings(tmp_project)
        data = json.loads(target.read_text())
        allow = data["permissions"]["allow"]
        # Canonical entries must appear exactly once after merge (idempotent).
        assert sum(1 for e in allow if e == "Bash(ll-action:*)") == 1
        assert sum(1 for e in allow if e == "Write(.ll/ll-continue-prompt.md)") == 1

    def test_preserves_custom_ll_prefix_permissions(self, tmp_project: Path) -> None:
        target = tmp_project / ".claude" / "settings.local.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        # User-added Bash(ll-mytool:*) is NOT in _LL_PERMISSIONS and must survive re-init.
        target.write_text(json.dumps({"permissions": {"allow": ["Bash(ll-mytool:*)"]}}))
        merge_settings(tmp_project)
        data = json.loads(target.read_text())
        allow = data["permissions"]["allow"]
        assert "Bash(ll-mytool:*)" in allow

    def test_extra_permissions_inserted(self, tmp_project: Path) -> None:
        merge_settings(tmp_project, extra_permissions=["Skill(ll:explore-api)"])
        data = json.loads((tmp_project / ".claude" / "settings.local.json").read_text())
        allow = data["permissions"]["allow"]
        assert "Skill(ll:explore-api)" in allow
        # Must appear before the trailing Write entry
        write_idx = allow.index("Write(.ll/ll-continue-prompt.md)")
        skill_idx = allow.index("Skill(ll:explore-api)")
        assert skill_idx < write_idx

    def test_dry_run_no_write(self, tmp_project: Path, capsys: pytest.CaptureFixture) -> None:
        merge_settings(tmp_project, dry_run=True)
        assert not (tmp_project / ".claude" / "settings.local.json").exists()
        assert "[update]" in capsys.readouterr().out


# ===========================================================================
# TestMakeIssueDirs
# ===========================================================================


class TestMakeIssueDirs:
    def test_creates_all_subdirs(self, tmp_project: Path) -> None:
        base = tmp_project / ".issues"
        make_issue_dirs(base)
        for sd in ("bugs", "features", "enhancements", "epics"):
            assert (base / sd).is_dir()

    def test_idempotent(self, tmp_project: Path) -> None:
        base = tmp_project / ".issues"
        make_issue_dirs(base)
        make_issue_dirs(base)  # should not raise

    def test_dry_run_no_create(self, tmp_project: Path, capsys: pytest.CaptureFixture) -> None:
        base = tmp_project / ".issues"
        make_issue_dirs(base, dry_run=True)
        assert not base.exists()
        assert "[mkdir]" in capsys.readouterr().out


# ===========================================================================
# TestMakeLearningTestsDir
# ===========================================================================


class TestMakeLearningTestsDir:
    def test_creates_dir_and_gitkeep(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = make_learning_tests_dir(ll_dir)
        assert created is True
        assert (ll_dir / "learning-tests").is_dir()
        assert (ll_dir / "learning-tests" / ".gitkeep").exists()

    def test_skips_if_already_exists(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        (ll_dir / "learning-tests").mkdir(parents=True)
        created = make_learning_tests_dir(ll_dir)
        assert created is False

    def test_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = make_learning_tests_dir(ll_dir, dry_run=True)
        assert created is True
        assert not (ll_dir / "learning-tests").exists()
        assert "[mkdir]" in capsys.readouterr().out


# ===========================================================================
# TestDeployGoals
# ===========================================================================


class TestDeployGoals:
    def test_deploys_goals_template(self, tmp_path: Path, templates_dir: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_goals(ll_dir, templates_dir)
        assert created is True
        assert (ll_dir / "ll-goals.md").exists()

    def test_skips_if_already_exists(self, tmp_path: Path, templates_dir: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-goals.md").write_text("existing")
        created = deploy_goals(ll_dir, templates_dir)
        assert created is False
        assert (ll_dir / "ll-goals.md").read_text() == "existing"

    def test_skips_if_template_missing(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        fake_tdir = tmp_path / "templates"
        fake_tdir.mkdir()
        created = deploy_goals(ll_dir, fake_tdir)
        assert created is False
        assert "Warning" in capsys.readouterr().err

    def test_dry_run(
        self, tmp_path: Path, templates_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_goals(ll_dir, templates_dir, dry_run=True)
        assert created is True
        assert not (ll_dir / "ll-goals.md").exists()
        assert "[write]" in capsys.readouterr().out


# ===========================================================================
# TestDeployDesignTokens
# ===========================================================================


class TestDeployDesignTokens:
    def test_deploys_profiles(self, tmp_path: Path, templates_dir: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_design_tokens(ll_dir, templates_dir)
        assert created is True
        assert (ll_dir / "design-tokens" / "profiles").is_dir()

    def test_skips_if_already_exists(self, tmp_path: Path, templates_dir: Path) -> None:
        ll_dir = tmp_path / ".ll"
        dest = ll_dir / "design-tokens" / "profiles"
        dest.mkdir(parents=True)
        created = deploy_design_tokens(ll_dir, templates_dir)
        assert created is False

    def test_dry_run(
        self, tmp_path: Path, templates_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_design_tokens(ll_dir, templates_dir, dry_run=True)
        assert created is True
        assert not (ll_dir / "design-tokens").exists()
        assert "[write]" in capsys.readouterr().out

    def test_skips_if_source_missing(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        fake_tdir = tmp_path / "templates"
        fake_tdir.mkdir()
        created = deploy_design_tokens(ll_dir, fake_tdir)
        assert created is False
        assert "Warning" in capsys.readouterr().err


# ===========================================================================
# TestInstallCodexAdapter
# ===========================================================================


class TestInstallCodexAdapter:
    def _make_plugin_root(self, tmp_path: Path) -> Path:
        plugin_root = tmp_path / "plugin"
        adapter_dir = plugin_root / "hooks" / "adapters" / "codex"
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "hooks.json").write_text('{"root": "{{LL_PLUGIN_ROOT}}", "hooks": []}')
        return plugin_root

    def test_installs_adapter(self, tmp_path: Path) -> None:
        import little_loops.init.writers as writers_mod

        project_root = tmp_path / "project"
        project_root.mkdir()
        plugin_root = self._make_plugin_root(tmp_path)
        installed = install_codex_adapter(project_root, plugin_root)
        assert installed is True
        dest = project_root / ".codex" / "hooks.json"
        assert dest.exists()
        content = dest.read_text()
        # Substitution value is the in-package little_loops root (not plugin_root)
        assert str(Path(writers_mod.__file__).parent.parent) in content
        assert "{{LL_PLUGIN_ROOT}}" not in content

    def test_skips_existing_without_force(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        plugin_root = self._make_plugin_root(tmp_path)
        (project_root / ".codex").mkdir()
        (project_root / ".codex" / "hooks.json").write_text("{}")
        installed = install_codex_adapter(project_root, plugin_root)
        assert installed is False

    def test_overwrites_with_force(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        plugin_root = self._make_plugin_root(tmp_path)
        (project_root / ".codex").mkdir()
        (project_root / ".codex" / "hooks.json").write_text("{}")
        installed = install_codex_adapter(project_root, plugin_root, force=True)
        assert installed is True

    def test_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        plugin_root = self._make_plugin_root(tmp_path)
        installed = install_codex_adapter(project_root, plugin_root, dry_run=True)
        assert installed is True
        assert not (project_root / ".codex" / "hooks.json").exists()
        assert "[write]" in capsys.readouterr().out

    def test_skips_when_template_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.init import writers as writers_mod

        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.setattr(
            writers_mod, "_codex_template_path", lambda: tmp_path / "nonexistent" / "hooks.json"
        )
        installed = install_codex_adapter(project_root, tmp_path)
        assert installed is None

    def test_writes_gen_version_stamp(self, tmp_path: Path) -> None:
        """The rendered adapter embeds the installed package version, not a placeholder."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        plugin_root = self._make_plugin_root(tmp_path)
        with patch(
            "little_loops.init.install_check.installed_package_version",
            return_value="9.9.9",
        ):
            install_codex_adapter(project_root, plugin_root)
        dest = project_root / ".codex" / "hooks.json"
        data = json.loads(dest.read_text())
        assert data["_ll_gen_version"] == "9.9.9"
        assert "{{LL_GEN_VERSION}}" not in dest.read_text()

    def test_read_adapter_gen_version_round_trip(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        plugin_root = self._make_plugin_root(tmp_path)
        with patch(
            "little_loops.init.install_check.installed_package_version",
            return_value="9.9.9",
        ):
            install_codex_adapter(project_root, plugin_root)
        assert read_adapter_gen_version(project_root) == "9.9.9"

    def test_read_adapter_gen_version_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert read_adapter_gen_version(tmp_path) is None

    def test_read_adapter_gen_version_malformed_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / ".codex").mkdir()
        (tmp_path / ".codex" / "hooks.json").write_text("{not valid json")
        assert read_adapter_gen_version(tmp_path) is None

    def test_read_adapter_gen_version_absent_field_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / ".codex").mkdir()
        (tmp_path / ".codex" / "hooks.json").write_text('{"hooks": {}}')
        assert read_adapter_gen_version(tmp_path) is None


# ===========================================================================
# TestWriteClaudeMd
# ===========================================================================


class TestWriteClaudeMd:
    def test_creates_dot_claude_md_when_absent(self, tmp_path: Path) -> None:
        result = write_claude_md(tmp_path)
        dest = tmp_path / ".claude" / "CLAUDE.md"
        assert result is True
        assert dest.exists()
        content = dest.read_text(encoding="utf-8")
        assert "## little-loops CLI Commands" in content
        assert "# Project Configuration" in content

    def test_appends_to_existing_dot_claude_md(self, tmp_path: Path) -> None:
        dest = tmp_path / ".claude" / "CLAUDE.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("# My Project\n\nSome existing content.\n", encoding="utf-8")
        result = write_claude_md(tmp_path)
        assert result is True
        content = dest.read_text(encoding="utf-8")
        assert "# My Project" in content
        assert "## little-loops CLI Commands" in content
        # Original content preserved
        assert "Some existing content." in content

    def test_appends_to_root_claude_md_when_no_dot_claude(self, tmp_path: Path) -> None:
        root_md = tmp_path / "CLAUDE.md"
        root_md.write_text("# Root Config\n", encoding="utf-8")
        result = write_claude_md(tmp_path)
        assert result is True
        content = root_md.read_text(encoding="utf-8")
        assert "# Root Config" in content
        assert "## little-loops CLI Commands" in content

    def test_prefers_dot_claude_md_over_root_claude_md(self, tmp_path: Path) -> None:
        dot_claude = tmp_path / ".claude" / "CLAUDE.md"
        dot_claude.parent.mkdir(parents=True)
        dot_claude.write_text("# Dot Claude\n", encoding="utf-8")
        root_md = tmp_path / "CLAUDE.md"
        root_md.write_text("# Root\n", encoding="utf-8")
        write_claude_md(tmp_path)
        assert "## little-loops CLI Commands" in dot_claude.read_text(encoding="utf-8")
        assert "## little-loops CLI Commands" not in root_md.read_text(encoding="utf-8")

    def test_noop_when_section_present_in_dot_claude_md(self, tmp_path: Path) -> None:
        dest = tmp_path / ".claude" / "CLAUDE.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("# Config\n\n## little-loops CLI Commands\n\nAlready here.\n")
        original_mtime = dest.stat().st_mtime
        result = write_claude_md(tmp_path)
        assert result is False
        assert dest.stat().st_mtime == original_mtime

    def test_noop_when_section_present_in_root_claude_md(self, tmp_path: Path) -> None:
        root_md = tmp_path / "CLAUDE.md"
        root_md.write_text("# Config\n\n## little-loops section here.\n", encoding="utf-8")
        result = write_claude_md(tmp_path)
        assert result is False

    def test_dry_run_create(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        result = write_claude_md(tmp_path, dry_run=True)
        assert result is True
        assert not (tmp_path / ".claude" / "CLAUDE.md").exists()
        out = capsys.readouterr().out
        assert "[write]" in out
        assert "CLAUDE.md" in out

    def test_dry_run_append(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        dest = tmp_path / ".claude" / "CLAUDE.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("# Existing\n", encoding="utf-8")
        original = dest.read_text(encoding="utf-8")
        result = write_claude_md(tmp_path, dry_run=True)
        assert result is True
        assert dest.read_text(encoding="utf-8") == original  # unchanged
        out = capsys.readouterr().out
        assert "[update]" in out
        assert "CLAUDE.md" in out

    def test_dry_run_noop_when_section_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        dest = tmp_path / ".claude" / "CLAUDE.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("# Config\n\n## little-loops CLI Commands\n")
        result = write_claude_md(tmp_path, dry_run=True)
        assert result is False
        assert capsys.readouterr().out == ""

    def test_canonical_block_contains_key_tools(self, tmp_path: Path) -> None:
        write_claude_md(tmp_path)
        content = (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        for tool in ("ll-auto", "ll-loop", "ll-issues", "ll-logs"):
            assert f"`{tool}`" in content


# ===========================================================================
# TestValidateDeps
# ===========================================================================


class TestValidateDeps:
    def test_no_warnings_when_all_present(self) -> None:
        with (
            patch("little_loops.init.validate.shutil.which", return_value="/usr/bin/jq"),
            patch(
                "little_loops.init.validate.subprocess.run",
                return_value=MagicMock(returncode=0),
            ),
            patch(
                "little_loops.init.validate.importlib.metadata.version",
                return_value="1.118.0",
            ),
        ):
            warnings = validate_deps(
                config=None,
                plugin_version="1.118.0",
                project_root=Path("/tmp"),
            )
        assert warnings == []

    def test_warns_when_jq_missing(self) -> None:
        with patch("little_loops.init.validate.shutil.which", return_value=None):
            w = _check_jq()
        assert w is not None
        assert "jq" in w.message

    def test_warns_when_python3_missing(self) -> None:
        with patch("little_loops.init.validate.shutil.which", return_value=None):
            w = _check_python3()
        assert w is not None
        assert "python3" in w.message

    def test_warns_when_pyyaml_missing(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("little_loops.init.validate.subprocess.run", return_value=mock_result):
            w = _check_pyyaml()
        assert w is not None
        assert "pyyaml" in w.message
        assert w.install_hint == "pip install pyyaml"

    def test_warns_when_package_not_installed(self, tmp_path: Path) -> None:
        exc = importlib.metadata.PackageNotFoundError("little-loops")
        with patch(
            "little_loops.init.validate.importlib.metadata.version",
            side_effect=exc,
        ):
            w = _check_little_loops_version("1.118.0", tmp_path)
        assert w is not None
        assert "not installed" in w.message

    def test_warns_on_version_mismatch(self, tmp_path: Path) -> None:
        with patch(
            "little_loops.init.validate.importlib.metadata.version",
            return_value="1.0.0",
        ):
            w = _check_little_loops_version("1.118.0", tmp_path)
        assert w is not None
        assert "mismatch" in w.message
        assert "1.0.0" in w.message

    def test_silent_on_version_match(self, tmp_path: Path) -> None:
        with patch(
            "little_loops.init.validate.importlib.metadata.version",
            return_value="1.118.0",
        ):
            w = _check_little_loops_version("1.118.0", tmp_path)
        assert w is None

    def test_tool_command_check_warns_missing_base(self) -> None:
        config = {"project": {"test_cmd": "nonexistent_tool_xyz --flag", "lint_cmd": None}}
        with patch("little_loops.init.validate.shutil.which", return_value=None):
            warnings = _check_tool_commands(config)
        assert any("nonexistent_tool_xyz" in w.message for w in warnings)

    def test_tool_command_check_deduplicates_base(self) -> None:
        config = {
            "project": {
                "test_cmd": "pytest",
                "lint_cmd": "pytest --lint",  # same base
            }
        }
        with patch("little_loops.init.validate.shutil.which", return_value=None):
            warnings = _check_tool_commands(config)
        # Only one warning for 'pytest', not two
        pytest_warnings = [w for w in warnings if "pytest" in w.message]
        assert len(pytest_warnings) == 1

    def test_validate_deps_collects_all_warnings(self, tmp_path: Path) -> None:
        """validate_deps returns warnings from all checks in one call."""
        exc = importlib.metadata.PackageNotFoundError("little-loops")
        with (
            patch("little_loops.init.validate.shutil.which", return_value=None),
            patch(
                "little_loops.init.validate.subprocess.run",
                return_value=MagicMock(returncode=1),
            ),
            patch(
                "little_loops.init.validate.importlib.metadata.version",
                side_effect=exc,
            ),
        ):
            config = {"project": {"test_cmd": "pytest"}}
            warnings = validate_deps(config, "1.118.0", tmp_path)
        # Should have: tool cmd + jq + python3 + pyyaml + package
        assert len(warnings) >= 4


# ===========================================================================
# TestMainInit (CLI smoke tests)
# ===========================================================================


class TestMainInit:
    def test_no_args_launches_tui_non_tty(self, capsys: pytest.CaptureFixture) -> None:
        # No flags → TUI path. In a non-TTY test runner stdin.isatty() returns False,
        # so run_tui exits with 1 and emits a --yes hint to stderr.
        from little_loops.init.cli import main_init

        with patch.object(sys, "argv", ["ll-init"]):
            code = main_init([])
        assert code == 1
        assert "--yes" in capsys.readouterr().err

    def test_dry_run_yes_exits_zero(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--dry-run", "--root", str(tmp_project)])
        assert code == 0
        assert not (tmp_project / ".ll" / "ll-config.json").exists()

    def test_yes_creates_config(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        config_path = tmp_project / ".ll" / "ll-config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert "$schema" in data

    def test_yes_merges_existing_config(self, tmp_project: Path) -> None:
        """--yes on a project with existing config merges rather than failing."""
        import json

        from little_loops.init.cli import main_init

        (tmp_project / ".ll").mkdir()
        existing = {
            "project": {"name": "preserved", "src_dir": "kept/"},
            "analytics": {"enabled": False},
        }
        (tmp_project / ".ll" / "ll-config.json").write_text(json.dumps(existing))

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        result = json.loads((tmp_project / ".ll" / "ll-config.json").read_text())
        # Existing project name and src_dir should be preserved
        assert result["project"]["name"] == "preserved"
        assert result["project"]["src_dir"] == "kept/"
        # Existing analytics=disabled should be preserved
        assert result["analytics"]["enabled"] is False

    def test_yes_preserves_unmodeled_keys(self, tmp_project: Path) -> None:
        """--yes on an existing config preserves keys build_config does not model (BUG-2310)."""
        import json

        from little_loops.init.cli import main_init

        (tmp_project / ".ll").mkdir()
        existing = {
            "project": {"name": "preserved"},
            # Sections build_config never emits — must survive re-init.
            "sprints": {"default_max_workers": 7},
            "documents": {"enabled": True, "categories": {"arch": {"files": ["x.md"]}}},
            "commands": {"confidence_gate": {"enabled": True, "readiness_threshold": 91}},
            "context_monitor": {"enabled": True, "auto_handoff_threshold": 42},
            "history": {
                "compaction": {"enabled": True, "budget_tokens": 4096},
                "session_digest": {"enabled": True, "char_cap": 1200},
            },
            "my_custom_section": {"key": "value"},
        }
        (tmp_project / ".ll" / "ll-config.json").write_text(json.dumps(existing))

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        result = json.loads((tmp_project / ".ll" / "ll-config.json").read_text())
        # Wholly unmodeled sections survive verbatim.
        assert result["sprints"] == {"default_max_workers": 7}
        assert result["documents"]["categories"] == {"arch": {"files": ["x.md"]}}
        assert result["commands"]["confidence_gate"]["readiness_threshold"] == 91
        assert result["my_custom_section"] == {"key": "value"}
        # Unmodeled leaves inside a section build_config *does* touch survive too.
        assert result["context_monitor"]["auto_handoff_threshold"] == 42
        assert result["history"]["compaction"] == {"enabled": True, "budget_tokens": 4096}
        assert result["history"]["session_digest"]["char_cap"] == 1200

    def test_yes_force_drops_unmodeled_keys(self, tmp_project: Path) -> None:
        """--yes --force resets to template defaults, dropping unmodeled keys (BUG-2310)."""
        import json

        from little_loops.init.cli import main_init

        (tmp_project / ".ll").mkdir()
        existing = {
            "project": {"name": "preserved"},
            "my_custom_section": {"key": "value"},
        }
        (tmp_project / ".ll" / "ll-config.json").write_text(json.dumps(existing))

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--force", "--root", str(tmp_project)])
        assert code == 0
        result = json.loads((tmp_project / ".ll" / "ll-config.json").read_text())
        assert "my_custom_section" not in result

    def test_apply_preserves_unmodeled_keys(self, tmp_project: Path, tmp_path: Path) -> None:
        """`apply` on an existing config preserves unmodeled keys (BUG-2310 third write path)."""
        import io
        import json
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        # Generate a plan JSON from a clean source.
        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(buf.getvalue())

        # Apply destination already has a config with an unmodeled key.
        apply_dest = tmp_path / "apply_dest"
        (apply_dest / ".ll").mkdir(parents=True)
        (apply_dest / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"name": "dest"}, "my_custom_section": {"key": "value"}})
        )

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--root", str(apply_dest), "apply", "--config", str(plan_file)])
        assert code == 0
        result = json.loads((apply_dest / ".ll" / "ll-config.json").read_text())
        assert result["my_custom_section"] == {"key": "value"}

    def test_apply_force_drops_unmodeled_keys(self, tmp_project: Path, tmp_path: Path) -> None:
        """`apply --force` resets to the plan config, dropping unmodeled keys (BUG-2310)."""
        import io
        import json
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(buf.getvalue())

        apply_dest = tmp_path / "apply_dest"
        (apply_dest / ".ll").mkdir(parents=True)
        (apply_dest / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"name": "dest"}, "my_custom_section": {"key": "value"}})
        )

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(
                ["--root", str(apply_dest), "apply", "--config", str(plan_file), "--force"]
            )
        assert code == 0
        result = json.loads((apply_dest / ".ll" / "ll-config.json").read_text())
        assert "my_custom_section" not in result

    def test_plan_emits_json(self, tmp_project: Path, capsys: pytest.CaptureFixture) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--plan", "--root", str(tmp_project)])
        assert code == 0
        out = capsys.readouterr().out
        plan = json.loads(out)
        assert "detected" in plan
        assert "proposed_config" in plan
        assert "host_options" in plan
        assert "warnings" in plan

    def test_yes_enable_feature_flags_write_sections(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(
                [
                    "--yes",
                    "--enable",
                    "decisions",
                    "--enable",
                    "session_capture",
                    "--root",
                    str(tmp_project),
                ]
            )
        assert code == 0
        data = json.loads((tmp_project / ".ll" / "ll-config.json").read_text())
        assert data["decisions"] == {"enabled": True}
        assert data["session_capture"] == {"enabled": True}
        assert "prompt_optimization" not in data

    def test_yes_disable_prompt_optimization_writes_disabled(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(
                ["--yes", "--disable", "prompt_optimization", "--root", str(tmp_project)]
            )
        assert code == 0
        data = json.loads((tmp_project / ".ll" / "ll-config.json").read_text())
        assert data["prompt_optimization"] == {"enabled": False}

    def test_unknown_feature_flag_exits_2(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--enable", "bogus", "--root", str(tmp_project)])
        assert code == 2
        assert "Unknown feature" in capsys.readouterr().err
        assert not (tmp_project / ".ll" / "ll-config.json").exists()

    def test_feature_flags_require_headless_mode(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--enable", "decisions", "--root", str(tmp_project)])
        assert code == 2
        assert "--yes" in capsys.readouterr().err

    def test_plan_reflects_feature_flags(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--plan", "--enable", "scratch_pad", "--root", str(tmp_project)])
        assert code == 0
        plan = json.loads(capsys.readouterr().out)
        assert plan["proposed_config"]["scratch_pad"] == {"enabled": True}

    def test_apply_from_plan(self, tmp_project: Path, tmp_path: Path) -> None:
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        # Generate plan JSON into a buffer
        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan_json = buf.getvalue()

        plan_file = tmp_path / "plan.json"
        plan_file.write_text(plan_json)

        # Apply to a separate destination
        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--root", str(apply_dest), "apply", "--config", str(plan_file)])
        assert code == 0
        assert (apply_dest / ".ll" / "ll-config.json").exists()
        assert (apply_dest / ".claude" / "CLAUDE.md").exists()

    def test_apply_writes_claude_md(self, tmp_project: Path, tmp_path: Path) -> None:
        """_run_apply must write .claude/CLAUDE.md (was missing before BUG-2313 fix)."""
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(buf.getvalue())

        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--root", str(apply_dest), "apply", "--config", str(plan_file)])
        assert code == 0
        assert (apply_dest / ".claude" / "CLAUDE.md").exists()

    def test_apply_deploys_design_tokens_when_enabled(
        self, tmp_project: Path, tmp_path: Path
    ) -> None:
        """_run_apply copies design-token profiles when plan config has design_tokens.enabled."""
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan = json.loads(buf.getvalue())
        plan["proposed_config"]["design_tokens"] = {"enabled": True, "active": "warm-paper"}
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--root", str(apply_dest), "apply", "--config", str(plan_file)])
        assert code == 0
        assert (apply_dest / ".ll" / "design-tokens" / "profiles").is_dir()

    def test_apply_deploys_issue_templates_when_enabled(
        self, tmp_project: Path, tmp_path: Path
    ) -> None:
        """_run_apply copies *-sections.json files when plan config has issues.deploy_templates."""
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan = json.loads(buf.getvalue())
        plan["proposed_config"].setdefault("issues", {})["deploy_templates"] = True
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--root", str(apply_dest), "apply", "--config", str(plan_file)])
        assert code == 0
        assert (apply_dest / ".ll" / "templates").is_dir()
        assert len(list((apply_dest / ".ll" / "templates").glob("*-sections.json"))) >= 4

    def test_apply_creates_learning_tests_dir_when_enabled(
        self, tmp_project: Path, tmp_path: Path
    ) -> None:
        """_run_apply creates .ll/learning-tests/ when plan config has learning_tests.enabled."""
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan = json.loads(buf.getvalue())
        plan["proposed_config"]["learning_tests"] = {"enabled": True}
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--root", str(apply_dest), "apply", "--config", str(plan_file)])
        assert code == 0
        assert (apply_dest / ".ll" / "learning-tests" / ".gitkeep").exists()

    def test_apply_adds_explore_api_permission_when_learning_tests(
        self, tmp_project: Path, tmp_path: Path
    ) -> None:
        """_run_apply injects Skill(ll:explore-api) into settings when learning_tests.enabled."""
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan = json.loads(buf.getvalue())
        plan["proposed_config"]["learning_tests"] = {"enabled": True}
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--root", str(apply_dest), "apply", "--config", str(plan_file)])
        assert code == 0
        settings = json.loads((apply_dest / ".claude" / "settings.local.json").read_text())
        assert "Skill(ll:explore-api)" in settings["permissions"]["allow"]

    def test_apply_installs_codex_adapter_when_host_detected(
        self, tmp_project: Path, tmp_path: Path
    ) -> None:
        """_run_apply installs .codex/hooks.json when --hosts codex is specified."""
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(buf.getvalue())

        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(
                ["--hosts", "codex", "--root", str(apply_dest), "apply", "--config", str(plan_file)]
            )
        assert code == 0
        assert (apply_dest / ".codex" / "hooks.json").exists()

    def test_apply_force_overwrites_codex_adapter(self, tmp_project: Path, tmp_path: Path) -> None:
        """_run_apply with --force overwrites an existing .codex/hooks.json."""
        import io
        from contextlib import redirect_stdout

        from little_loops.init.cli import main_init

        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
                main_init(["--plan", "--root", str(plan_src)])
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(buf.getvalue())

        apply_dest = tmp_path / "apply_dest"
        apply_dest.mkdir()
        codex_dir = apply_dest / ".codex"
        codex_dir.mkdir()
        stub = codex_dir / "hooks.json"
        stub.write_text('{"stub": true}')

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(
                [
                    "--hosts",
                    "codex",
                    "--root",
                    str(apply_dest),
                    "apply",
                    "--config",
                    str(plan_file),
                    "--force",
                ]
            )
        assert code == 0
        content = json.loads(stub.read_text())
        assert "stub" not in content

    def test_yes_deploys_design_tokens_when_enabled(self, tmp_project: Path) -> None:
        """_run_yes copies design-token profiles when config has design_tokens.enabled."""
        from little_loops.init import core as init_core
        from little_loops.init.cli import main_init

        real_build = init_core.build_config

        def patched_build(template, choices=None):
            cfg = real_build(template, choices)
            cfg["design_tokens"] = {"enabled": True, "active": "warm-paper"}
            return cfg

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch("little_loops.init.core.build_config", side_effect=patched_build),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        assert (tmp_project / ".ll" / "design-tokens" / "profiles").is_dir()

    def test_yes_deploys_issue_templates_when_enabled(self, tmp_project: Path) -> None:
        """_run_yes copies *-sections.json files when config has issues.deploy_templates."""
        from little_loops.init import core as init_core
        from little_loops.init.cli import main_init

        real_build = init_core.build_config

        def patched_build(template, choices=None):
            cfg = real_build(template, choices)
            cfg.setdefault("issues", {})["deploy_templates"] = True
            return cfg

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch("little_loops.init.core.build_config", side_effect=patched_build),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        assert (tmp_project / ".ll" / "templates").is_dir()
        assert len(list((tmp_project / ".ll" / "templates").glob("*-sections.json"))) >= 4

    def test_yes_adds_explore_api_permission_when_learning_tests(self, tmp_project: Path) -> None:
        """_run_yes injects Skill(ll:explore-api) into settings when learning_tests enabled."""
        from little_loops.init import core as init_core
        from little_loops.init.cli import main_init

        real_build = init_core.build_config

        def patched_build(template, choices=None):
            cfg = real_build(template, choices)
            cfg["learning_tests"] = {"enabled": True}
            return cfg

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch("little_loops.init.core.build_config", side_effect=patched_build),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        settings = json.loads((tmp_project / ".claude" / "settings.local.json").read_text())
        assert "Skill(ll:explore-api)" in settings["permissions"]["allow"]

    def test_yes_warns_when_pypi_stale_without_upgrade_flag(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Without --upgrade, headless mode warns but never runs pip install/upgrade."""
        from unittest.mock import patch

        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=("pypi", "1.0.0", None),
            ),
            patch(
                "little_loops.init.install_check.fetch_latest_pypi",
                return_value="1.1.0",
            ),
            patch("little_loops.init.cli._subprocess") as mock_sp,
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        # No pip subprocess should have been called during the install check
        mock_sp.run.assert_not_called()
        err = capsys.readouterr().err
        assert "mismatch" in err or "Hint" in err

    def test_yes_upgrades_when_pypi_stale_with_upgrade_flag(self, tmp_project: Path) -> None:
        """With --upgrade, headless mode runs pip install --upgrade for PyPI installs."""
        from unittest.mock import MagicMock, patch

        from little_loops.init.cli import main_init

        captured_runs: list = []

        def record_run(cmd, **kwargs):
            captured_runs.append(cmd)
            return MagicMock(returncode=0, stdout="")

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=("pypi", "1.0.0", None),
            ),
            patch(
                "little_loops.init.install_check.fetch_latest_pypi",
                return_value="1.1.0",
            ),
            patch("little_loops.init.cli._subprocess.run", side_effect=record_run),
        ):
            code = main_init(["--yes", "--upgrade", "--root", str(tmp_project)])
        assert code == 0
        # At least one call should be the pip upgrade
        upgrade_calls = [c for c in captured_runs if "--upgrade" in c and "little-loops" in c]
        assert upgrade_calls, f"Expected pip --upgrade little-loops call; got: {captured_runs}"

    def test_yes_consumer_path_never_uses_editable_bare_name(self, tmp_project: Path) -> None:
        """pip install -e <bare-package-name> must never be constructed for PyPI installs."""
        from unittest.mock import MagicMock, patch

        from little_loops.init.cli import main_init

        captured_runs: list = []

        def record_run(cmd, **kwargs):
            captured_runs.append(list(cmd))
            return MagicMock(returncode=0, stdout="")

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=("pypi", "1.0.0", None),
            ),
            patch(
                "little_loops.init.install_check.fetch_latest_pypi",
                return_value="1.1.0",
            ),
            patch("little_loops.init.cli._subprocess.run", side_effect=record_run),
        ):
            main_init(["--yes", "--upgrade", "--root", str(tmp_project)])

        # Assert that no call uses `pip install -e little-loops` (bare name)
        for cmd in captured_runs:
            if "-e" in cmd:
                idx = cmd.index("-e")
                editable_target = cmd[idx + 1] if idx + 1 < len(cmd) else ""
                assert editable_target != "little-loops", (
                    f"pip install -e <bare-name> must not be constructed; got: {cmd}"
                )

    def test_project_scoped_plugin_install_source_written_to_config(
        self, tmp_project: Path
    ) -> None:
        """detect_installation returning project-claude-code scope writes it to config (BUG-2266)."""
        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=("project-claude-code", "1.0.0", "/proj/.claude/plugins/ll"),
            ),
        ):
            code = main_init(["--yes", "--root", str(tmp_project)])
        assert code == 0
        config = json.loads((tmp_project / ".ll" / "ll-config.json").read_text())
        assert config.get("install_source") == "project-claude-code"

    def test_dry_run_shows_epics_not_completed_deferred(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """--dry-run [mkdir] lines list 'epics' (not stale 'completed'/'deferred')."""
        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--dry-run", "--root", str(tmp_project)])
        assert code == 0
        out = capsys.readouterr().out
        mkdir_lines = [line for line in out.splitlines() if "[mkdir]" in line]
        assert any("epics" in line for line in mkdir_lines)
        assert not any("completed" in line for line in mkdir_lines)
        assert not any("deferred" in line for line in mkdir_lines)

    def test_dry_run_shows_design_tokens_when_enabled(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """--dry-run output includes design-token write when design_tokens.enabled."""
        from little_loops.init import core as init_core
        from little_loops.init.cli import main_init

        real_build = init_core.build_config

        def patched_build(template, choices=None):
            cfg = real_build(template, choices)
            cfg["design_tokens"] = {"enabled": True, "active": "warm-paper"}
            return cfg

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch("little_loops.init.core.build_config", side_effect=patched_build),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--dry-run", "--root", str(tmp_project)])
        assert code == 0
        assert "design-token" in capsys.readouterr().out

    def test_dry_run_shows_issue_templates_when_enabled(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """--dry-run output includes issue templates write when issues.deploy_templates."""
        from little_loops.init import core as init_core
        from little_loops.init.cli import main_init

        real_build = init_core.build_config

        def patched_build(template, choices=None):
            cfg = real_build(template, choices)
            cfg.setdefault("issues", {})["deploy_templates"] = True
            return cfg

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch("little_loops.init.core.build_config", side_effect=patched_build),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--dry-run", "--root", str(tmp_project)])
        assert code == 0
        assert "section templates" in capsys.readouterr().out

    def test_dry_run_shows_learning_tests_when_enabled(
        self, tmp_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """--dry-run output includes learning-tests mkdir and explore-api permission."""
        from little_loops.init import core as init_core
        from little_loops.init.cli import main_init

        real_build = init_core.build_config

        def patched_build(template, choices=None):
            cfg = real_build(template, choices)
            cfg["learning_tests"] = {"enabled": True}
            return cfg

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch("little_loops.init.core.build_config", side_effect=patched_build),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--dry-run", "--root", str(tmp_project)])
        assert code == 0
        out = capsys.readouterr().out
        assert "learning-tests" in out
        assert "Skill(ll:explore-api)" in out

    def test_dry_run_output_matches_yes_writes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Issue-subdir [mkdir] names in --dry-run match the directories --yes creates."""
        from little_loops.init.cli import main_init

        dry_root = tmp_path / "dry"
        live_root = tmp_path / "live"
        dry_root.mkdir()
        live_root.mkdir()

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code = main_init(["--yes", "--dry-run", "--root", str(dry_root)])
        assert code == 0
        out = capsys.readouterr().out
        dry_mkdir_names = {
            Path(line.strip().split(None, 1)[1].strip()).name
            for line in out.splitlines()
            if "[mkdir]" in line and ".issues" in line
        }

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
        ):
            code2 = main_init(["--yes", "--root", str(live_root)])
        assert code2 == 0
        live_issue_dir = live_root / ".issues"
        live_mkdir_names = {p.name for p in live_issue_dir.iterdir() if p.is_dir()}

        assert dry_mkdir_names == live_mkdir_names


# ===========================================================================
# TestDetectHosts
# ===========================================================================


class TestDetectHosts:
    def test_codex_binary_detected(self, tmp_path: Path) -> None:
        from little_loops.init.cli import _detect_hosts

        with patch(
            "little_loops.init.cli.shutil.which", side_effect=lambda b: b if b == "codex" else None
        ):
            hosts = _detect_hosts(tmp_path)
        assert "codex" in hosts

    def test_codex_dir_detected(self, tmp_path: Path) -> None:
        from little_loops.init.cli import _detect_hosts

        (tmp_path / ".codex").mkdir()
        with patch("little_loops.init.cli.shutil.which", return_value=None):
            hosts = _detect_hosts(tmp_path)
        assert "codex" in hosts

    def test_claude_binary_detected(self, tmp_path: Path) -> None:
        from little_loops.init.cli import _detect_hosts

        with patch(
            "little_loops.init.cli.shutil.which", side_effect=lambda b: b if b == "claude" else None
        ):
            hosts = _detect_hosts(tmp_path)
        assert "claude-code" in hosts

    def test_pi_binary_detected(self, tmp_path: Path) -> None:
        from little_loops.init.cli import _detect_hosts

        with patch(
            "little_loops.init.cli.shutil.which", side_effect=lambda b: b if b == "pi" else None
        ):
            hosts = _detect_hosts(tmp_path)
        assert "pi" in hosts

    def test_opencode_binary_detected(self, tmp_path: Path) -> None:
        from little_loops.init.cli import _detect_hosts

        with patch(
            "little_loops.init.cli.shutil.which",
            side_effect=lambda b: b if b == "opencode" else None,
        ):
            hosts = _detect_hosts(tmp_path)
        assert "opencode" in hosts

    def test_nothing_detected_defaults_to_claude_code(self, tmp_path: Path) -> None:
        from little_loops.init.cli import _detect_hosts

        with patch("little_loops.init.cli.shutil.which", return_value=None):
            hosts = _detect_hosts(tmp_path)
        assert hosts == ["claude-code"]

    def test_multiple_hosts_detected(self, tmp_path: Path) -> None:
        from little_loops.init.cli import _detect_hosts

        with patch(
            "little_loops.init.cli.shutil.which",
            side_effect=lambda b: b if b in ("claude", "codex") else None,
        ):
            hosts = _detect_hosts(tmp_path)
        assert "claude-code" in hosts
        assert "codex" in hosts


# ===========================================================================
# TestHostDispatch
# ===========================================================================


class TestHostDispatch:
    def test_hosts_codex_installs_adapter(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        # Use the real plugin root so templates and adapter template both exist
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--hosts", "codex", "--root", str(tmp_project)])
        assert code == 0
        assert (tmp_project / ".codex" / "hooks.json").exists()

    def test_hosts_claude_code_no_adapter_file(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--hosts", "claude-code", "--root", str(tmp_project)])
        assert code == 0
        assert not (tmp_project / ".codex" / "hooks.json").exists()

    def test_hosts_pi_graceful_unavailable(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--hosts", "pi", "--root", str(tmp_project)])
        assert code == 0
        assert "not yet available" in capsys.readouterr().out

    def test_hosts_comma_separated(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--hosts", "claude-code,codex", "--root", str(tmp_project)])
        assert code == 0
        assert (tmp_project / ".codex" / "hooks.json").exists()

    def test_unknown_host_warns_and_skips(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import _dispatch_host_adapters

        _dispatch_host_adapters(
            ["codx"],  # typo
            project_root=tmp_project,
            plugin_root=tmp_project,
        )
        captured = capsys.readouterr()
        assert "Unknown host" in captured.err
        assert "codx" in captured.err

    def test_codex_deprecated_alias_still_works(self, tmp_project: Path) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--codex", "--root", str(tmp_project)])
        assert code == 0
        assert (tmp_project / ".codex" / "hooks.json").exists()

    def test_dry_run_codex_shows_write_line(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--dry-run", "--hosts", "codex", "--root", str(tmp_project)])
        assert code == 0
        assert ".codex/hooks.json" in capsys.readouterr().out

    def test_dry_run_pi_shows_unavailable(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--yes", "--dry-run", "--hosts", "pi", "--root", str(tmp_project)])
        assert code == 0
        assert "not yet available" in capsys.readouterr().out

    def test_plan_includes_has_pi(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import main_init

        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            code = main_init(["--plan", "--root", str(tmp_project)])
        assert code == 0
        plan = json.loads(capsys.readouterr().out)
        assert "has_pi" in plan["host_options"]


# ===========================================================================
# TestDispatchHostUpgrade
# ===========================================================================


class TestDispatchHostUpgrade:
    """FEAT-2387: host-parameterized surface refresh on --upgrade."""

    @staticmethod
    def _runner_mock(binary: str = "claude") -> MagicMock:
        invocation = MagicMock()
        invocation.binary = binary
        runner = MagicMock()
        runner.build_version_check.return_value = invocation
        return runner

    def test_project_scoped_runs_plugin_update(self, tmp_project: Path) -> None:
        from little_loops.init.cli import _dispatch_host_upgrade

        captured: list[list[str]] = []

        def record(cmd, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(list(cmd))
            return MagicMock(returncode=0, stdout="")

        with (
            patch("little_loops.init.cli._subprocess.run", side_effect=record),
            patch(
                "little_loops.host_runner.resolve_host",
                return_value=self._runner_mock("claude"),
            ),
        ):
            _dispatch_host_upgrade(
                ["claude-code"], tmp_project, _PROJECT_ROOT, "project-claude-code"
            )
        assert any("plugin" in c and "update" in c and "ll@little-loops" in c for c in captured), (
            f"expected plugin update call; got {captured}"
        )

    def test_user_scoped_advise_only(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import _dispatch_host_upgrade

        captured: list[list[str]] = []

        def record(cmd, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(list(cmd))
            return MagicMock(returncode=0, stdout="")

        with patch("little_loops.init.cli._subprocess.run", side_effect=record):
            _dispatch_host_upgrade(
                ["claude-code"], tmp_project, _PROJECT_ROOT, "global-claude-code"
            )
        # No plugin-update subprocess for user-scoped installs.
        assert not any("plugin" in c for c in captured), f"unexpected plugin call: {captured}"
        assert "claude plugin update ll@little-loops" in capsys.readouterr().err

    def test_codex_force_regenerates_stale_adapter(self, tmp_project: Path) -> None:
        from little_loops.init.cli import _dispatch_host_upgrade

        codex = tmp_project / ".codex"
        codex.mkdir()
        (codex / "hooks.json").write_text('{"_ll_gen_version": "0.0.1", "stale": true}')
        with patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT):
            _dispatch_host_upgrade(["codex"], tmp_project, _PROJECT_ROOT, "pypi")
        data = json.loads((codex / "hooks.json").read_text())
        # Regenerated from the in-package template (force=True), not the stale stub.
        assert "hooks" in data
        assert "stale" not in data

    def test_warn_adapter_staleness_prints_hint(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import _warn_adapter_staleness

        codex = tmp_project / ".codex"
        codex.mkdir()
        (codex / "hooks.json").write_text('{"_ll_gen_version": "0.0.1"}')
        with patch(
            "little_loops.init.install_check.installed_package_version",
            return_value="9.9.9",
        ):
            _warn_adapter_staleness(["codex"], tmp_project)
        err = capsys.readouterr().err
        assert "0.0.1" in err and "9.9.9" in err
        assert "--upgrade" in err

    def test_warn_adapter_staleness_silent_when_current(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import _warn_adapter_staleness

        codex = tmp_project / ".codex"
        codex.mkdir()
        (codex / "hooks.json").write_text('{"_ll_gen_version": "9.9.9"}')
        with patch(
            "little_loops.init.install_check.installed_package_version",
            return_value="9.9.9",
        ):
            _warn_adapter_staleness(["codex"], tmp_project)
        assert "generated against" not in capsys.readouterr().err

    def test_warn_adapter_staleness_noop_without_codex(
        self, tmp_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.cli import _warn_adapter_staleness

        _warn_adapter_staleness(["claude-code"], tmp_project)
        assert capsys.readouterr().err == ""


# ===========================================================================
# TestDetectDocuments
# ===========================================================================


class TestDetectDocuments:
    def test_returns_empty_when_no_docs(self, tmp_project: Path) -> None:
        from little_loops.init.detect import detect_documents

        result = detect_documents(tmp_project)
        assert result == {}

    def test_finds_architecture_doc(self, tmp_project: Path) -> None:
        from little_loops.init.detect import detect_documents

        docs_dir = tmp_project / "docs"
        docs_dir.mkdir()
        (docs_dir / "architecture.md").write_text("# Architecture")
        result = detect_documents(tmp_project)
        assert "architecture" in result
        assert "docs/architecture.md" in result["architecture"]["files"]

    def test_finds_product_doc(self, tmp_project: Path) -> None:
        from little_loops.init.detect import detect_documents

        (tmp_project / "roadmap.md").write_text("# Roadmap")
        result = detect_documents(tmp_project)
        assert "product" in result
        assert "roadmap.md" in result["product"]["files"]

    def test_excludes_node_modules(self, tmp_project: Path) -> None:
        from little_loops.init.detect import detect_documents

        nm = tmp_project / "node_modules" / "some-pkg"
        nm.mkdir(parents=True)
        (nm / "architecture.md").write_text("noise")
        result = detect_documents(tmp_project)
        assert result == {}

    def test_excludes_dot_git(self, tmp_project: Path) -> None:
        from little_loops.init.detect import detect_documents

        git_dir = tmp_project / ".git" / "info"
        git_dir.mkdir(parents=True)
        (git_dir / "goals.md").write_text("noise")
        result = detect_documents(tmp_project)
        assert result == {}

    def test_architecture_and_product_both_detected(self, tmp_project: Path) -> None:
        from little_loops.init.detect import detect_documents

        docs = tmp_project / "docs"
        docs.mkdir()
        (docs / "api.md").write_text("# API")
        (docs / "vision.md").write_text("# Vision")
        result = detect_documents(tmp_project)
        assert "architecture" in result
        assert "product" in result


# ===========================================================================
# TestTemplateCommandOptions — integrity check for all typed templates
# ===========================================================================


class TestTemplateCommandOptions:
    """All 8 non-generic project-type templates must have _meta.command_options."""

    TYPED_TEMPLATES = [
        "python-generic.json",
        "typescript.json",
        "javascript.json",
        "go.json",
        "rust.json",
        "java-maven.json",
        "java-gradle.json",
        "dotnet.json",
    ]

    @pytest.mark.parametrize("filename", TYPED_TEMPLATES)
    def test_has_command_options(self, filename: str, templates_dir: Path) -> None:
        data = json.loads((templates_dir / filename).read_text())
        assert "command_options" in data["_meta"], f"{filename} is missing _meta.command_options"

    @pytest.mark.parametrize("filename", TYPED_TEMPLATES)
    def test_command_options_has_test_cmd(self, filename: str, templates_dir: Path) -> None:
        data = json.loads((templates_dir / filename).read_text())
        opts = data["_meta"]["command_options"]
        assert "test_cmd" in opts and len(opts["test_cmd"]) >= 2, (
            f"{filename} command_options.test_cmd is missing or has fewer than 2 choices"
        )

    def test_generic_has_no_command_options(self, templates_dir: Path) -> None:
        data = json.loads((templates_dir / "generic.json").read_text())
        assert "command_options" not in data["_meta"]


# ---------------------------------------------------------------------------
# Merge helpers (BUG-2310)
# ---------------------------------------------------------------------------


class TestMergeHelpers:
    def test_strip_none_leaves_removes_nested_nulls(self) -> None:
        src = {
            "a": 1,
            "b": None,
            "c": {"d": None, "e": 2, "f": {"g": None}},
            "h": [None, 1],  # lists pass through untouched
        }
        assert strip_none_leaves(src) == {"a": 1, "c": {"e": 2, "f": {}}, "h": [None, 1]}
        # Input is not mutated.
        assert src["b"] is None

    def test_strip_none_leaves_preserves_falsy_values(self) -> None:
        """False, 0, and empty string are not None and must survive stripping."""
        src = {
            "a": False,
            "b": 0,
            "c": "",
            "d": None,
        }
        assert strip_none_leaves(src) == {"a": False, "b": 0, "c": ""}
        assert strip_none_leaves({}) == {}

    def test_merge_with_existing_force_returns_new_unchanged(self) -> None:
        existing = {"keep": 1, "project": {"name": "old"}}
        new = {"project": {"name": "new"}}
        assert merge_with_existing(new, existing, force=True) is new

    def test_merge_with_existing_no_existing_returns_new(self) -> None:
        new = {"project": {"name": "new"}}
        assert merge_with_existing(new, {}, force=False) is new

    def test_merge_with_existing_preserves_unmodeled_and_overrides_modeled(self) -> None:
        existing = {
            "project": {"name": "old", "src_dir": "kept/"},
            "sprints": {"default_max_workers": 7},
        }
        new = {"project": {"name": "new"}}
        merged = merge_with_existing(new, existing, force=False)
        assert merged["project"]["name"] == "new"  # modeled key overridden
        assert merged["project"]["src_dir"] == "kept/"  # unmodeled leaf preserved
        assert merged["sprints"] == {"default_max_workers": 7}  # unmodeled section preserved

    def test_merge_with_existing_null_leaf_does_not_delete_user_key(self) -> None:
        existing = {"loops": {"run_defaults": {"mode": "auto", "clear": False}}}
        new = {"loops": {"run_defaults": {"mode": None, "clear": True}}}
        merged = merge_with_existing(new, existing, force=False)
        # The None leaf is stripped, so the user's mode survives; clear is overridden.
        assert merged["loops"]["run_defaults"]["mode"] == "auto"
        assert merged["loops"]["run_defaults"]["clear"] is True

    def test_load_existing_config_absent_returns_empty(self, tmp_path: Path) -> None:
        assert load_existing_config(tmp_path) == {}

    def test_load_existing_config_reads_ll_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps({"project": {"name": "x"}}))
        assert load_existing_config(tmp_path) == {"project": {"name": "x"}}

    def test_load_existing_config_malformed_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{ not json")
        assert load_existing_config(tmp_path) == {}


# ===========================================================================
# TestProjectTypeTemplatesEpicBranchesStamp (FEAT-2447)
# ===========================================================================


class TestProjectTypeTemplatesEpicBranchesStamp:
    """All 9 project-type templates must stamp `parallel.epic_branches: {enabled: false}`.

    Decision ARCHITECTURE-096 mandates the stamp so that init-using projects
    see the same defaults as config-file users. Mirrors the existing
    `use_feature_branches: false` precedent.
    """

    def test_all_project_type_templates_have_epic_branches_stamp(self) -> None:
        bundled = get_bundled_templates_dir()
        project_templates = [
            "typescript.json",
            "python-generic.json",
            "javascript.json",
            "java-maven.json",
            "java-gradle.json",
            "rust.json",
            "go.json",
            "dotnet.json",
            "generic.json",
        ]
        for name in project_templates:
            path = bundled / name
            assert path.exists(), f"Missing template: {path}"
            data = json.loads(path.read_text())
            assert "parallel" in data, f"{name}: missing parallel block"
            assert "epic_branches" in data["parallel"], (
                f"{name}: missing epic_branches stamp (FEAT-2447 / ARCHITECTURE-096)"
            )
            assert data["parallel"]["epic_branches"].get("enabled") is False, (
                f"{name}: epic_branches.enabled should default to False"
            )


# ===========================================================================
# TestSchemaLoaderInWheelInstall — regression guard for the ll-init --yes
# wheel-install crash. The previous Path(__file__).resolve().parents[3]
# traversal in init/core.py:_load_schema only worked in editable installs.
# ===========================================================================


class TestSchemaLoaderInWheelInstall:
    """config-schema.json must load in both editable AND wheel installs."""

    def test_load_schema_succeeds_in_current_install(self) -> None:
        """_load_schema() must return a dict with 'properties' from the bundled file.

        Regression: the old loader walked Path(__file__).parents[3] to the repo
        root, which exists in editable installs and not in wheel installs.
        The new loader uses importlib.resources.files('little_loops'), which
        resolves in both layouts.
        """
        from little_loops.init import core as core_mod

        # Clear the lru_cache so we exercise the loader path, not the cache.
        core_mod._load_schema.cache_clear()
        try:
            data = core_mod._load_schema()
        finally:
            core_mod._load_schema.cache_clear()
        assert isinstance(data, dict), f"_load_schema returned {type(data).__name__}, expected dict"
        assert "properties" in data, "bundled schema missing top-level 'properties'"
        # Spot-check a few keys to confirm we got the real schema, not a stub.
        assert "learning_tests" in data["properties"]
        assert "analytics" in data["properties"]

    def test_schema_default_returns_real_default(self) -> None:
        """schema_default() — the function ll-init --yes actually calls — works."""
        from little_loops.init import core as core_mod

        core_mod._load_schema.cache_clear()
        try:
            # Exact dotted path exercised by _run_yes (init/cli.py:395 → core.py:125).
            value = core_mod.schema_default("learning_tests.enabled")
        finally:
            core_mod._load_schema.cache_clear()
        assert value is False, (
            f"schema_default('learning_tests.enabled') returned {value!r}; "
            f"bundled schema default is False"
        )
