"""Tests for little_loops.init — detection, config building, validation, writers."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.init.cli import _plugin_root
from little_loops.init.core import SCHEMA_URL, build_config
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
    make_issue_dirs,
    make_learning_tests_dir,
    merge_settings,
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

    def test_learning_tests_always_written(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "learning_tests" in config
        assert config["learning_tests"]["enabled"] is True

    def test_analytics_always_written(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert "analytics" in config
        assert config["analytics"]["enabled"] is True
        assert "capture" in config["analytics"]

    def test_product_enabled_by_default(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match)
        assert config.get("product", {}).get("enabled") is True

    def test_product_omitted_when_disabled(self, fake_templates: Path, tmp_project: Path) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(match, {"product_enabled": False})
        assert "product" not in config

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
        assert rd["clear"] is True
        assert rd["show_diagrams"] == "clean"
        assert rd["mode"] is None

    def test_loops_run_defaults_override_via_choices(
        self, fake_templates: Path, tmp_project: Path
    ) -> None:
        (tmp_project / "pyproject.toml").touch()
        match = detect_project_type(tmp_project, fake_templates)
        config = build_config(
            match, {"loop_clear_default": False, "loop_show_diagrams_default": None}
        )
        rd = config["loops"]["run_defaults"]
        assert rd["clear"] is False
        assert rd["show_diagrams"] is None
        assert rd["mode"] is None

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

    def test_removes_stale_ll_entries(self, tmp_project: Path) -> None:
        target = tmp_project / ".claude" / "settings.local.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": ["Bash(ll-old-tool:*)", "Write(.ll/ll-continue-prompt.md)"]
                    }
                }
            )
        )
        merge_settings(tmp_project)
        data = json.loads(target.read_text())
        allow = data["permissions"]["allow"]
        # Old entry replaced by canonical set; should not be double-entered
        count = sum(1 for e in allow if e == "Bash(ll-old-tool:*)")
        assert count == 0

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
