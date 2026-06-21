"""Tests for little_loops.init.tui — interactive TUI frontend."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.init.tui import _build_final_config, run_tui

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # little-loops root
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"
_PLUGIN_ROOT = _PROJECT_ROOT


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_detect_installation() -> MagicMock:
    """Mock detect_installation to return (None, None) for all TUI tests.

    Ensures the Round 1 install-check confirm always fires (not-installed path)
    so confirm_returns lists in _wire_q() are always positionally consistent.
    """
    with patch(
        "little_loops.init.install_check.detect_installation",
        return_value=(None, None),
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ask(value: object) -> MagicMock:
    """Return a mock whose .ask() returns value."""
    m = MagicMock()
    m.ask.return_value = value
    return m


def _wire_q(
    mock_q: MagicMock,
    *,
    name: str = "myproject",
    src_dir: str = "src/",
    test_cmd: str = "pytest",
    lint_cmd: str = "ruff check .",
    type_cmd: str = "mypy",
    format_cmd: str = "ruff format .",
    focus_dirs: str = "src/",
    add_excludes: bool = False,
    custom_excludes: str = "",
    features: list[str] | None = None,
    workers: str = "4",
    worktree_files: list[str] | None = None,
    use_feature_branches: bool = False,
    session_digest: bool = True,
    prompt_optimization: bool = True,
    loop_clear_default: bool = True,
    hosts: list[str] | None = None,
    settings: str = "local",
    install_confirmed: bool = True,
    confirmed: bool | None = True,
) -> None:
    """Wire a questionary mock for a complete TUI interaction.

    Screen flow (7 screens):
      1. Plugin Install: install_confirmed (confirm) — fires when detect_installation returns (None,None)
      2. Project Basics: name, src_dir, test_cmd, lint_cmd, type_cmd, format_cmd (text)
      3. Scan: focus_dirs (text), add_excludes (confirm), [custom_excludes (text) if add_excludes]
      4. Features: features (checkbox), [workers (text) + worktree_files (checkbox) if parallel],
                   [use_feature_branches (confirm) if parallel], session_digest (confirm),
                   prompt_optimization (confirm), loop_clear_default (confirm)
      4b. Loop run defaults: loop_show_diagrams_default (select, via shared return_value)
      5. Hosts: hosts (checkbox)
      6. Settings: settings (select, via shared return_value)
      7. CLAUDE.md: (select, via shared return_value)
    """
    if features is None:
        features = ["parallel", "product", "learning_tests", "analytics", "context_monitor"]
    if hosts is None:
        hosts = ["claude-code"]
    if worktree_files is None:
        worktree_files = []

    # Text calls: Screen 2 (6 fields) + Screen 3 focus_dirs
    text_returns = [name, src_dir, test_cmd, lint_cmd, type_cmd, format_cmd, focus_dirs]
    if add_excludes:
        text_returns.append(custom_excludes)
    if "parallel" in features:
        text_returns.append(workers)

    mock_q.text.side_effect = [_mock_ask(v) for v in text_returns]

    # Checkbox calls: features, [worktree_files if parallel], hosts
    checkbox_returns: list[list[str]] = [features]
    if "parallel" in features:
        checkbox_returns.append(worktree_files)
    checkbox_returns.append(hosts)
    mock_q.checkbox.side_effect = [_mock_ask(v) for v in checkbox_returns]

    # Select: loop_show_diagrams_default (screen 4b) + settings (screen 6) + CLAUDE.md (screen 7)
    # — shared return_value means all three get the same value; "local" is a valid diagram preset
    # so this works for both the new loop_show_diagrams question and the settings/CLAUDE.md selects.
    # (no curated menus since tests use generic.json which has no command_options;
    #  and design_tokens not in default features so no profile select)
    mock_q.select.return_value.ask.return_value = settings

    # Confirm: install_confirmed (screen 1, ENH-2253), add_excludes (screen 3),
    # [use_feature_branches if parallel] (screen 4), session_digest (screen 4),
    # prompt_optimization (screen 4), loop_clear_default (screen 4, ENH-2243), apply (final)
    confirm_returns = [install_confirmed, add_excludes]
    if "parallel" in features:
        confirm_returns.append(use_feature_branches)
    confirm_returns.extend([session_digest, prompt_optimization, loop_clear_default, confirmed])
    mock_q.confirm.side_effect = [_mock_ask(v) for v in confirm_returns]

    # Choice is used only to build checkbox/select lists; let it return a plain MagicMock
    mock_q.Choice.side_effect = lambda *a, **kw: MagicMock()


# ---------------------------------------------------------------------------
# Non-TTY detection
# ---------------------------------------------------------------------------


class TestNonTTY:
    def test_non_tty_returns_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 1
        assert "--yes" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @patch("little_loops.init.tui.questionary")
    def test_full_run_writes_config(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, name="myapp", test_cmd="pytest --tb=short")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 0
        config_path = tmp_path / ".ll" / "ll-config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["project"]["name"] == "myapp"
        assert config["project"]["test_cmd"] == "pytest --tb=short"

    @patch("little_loops.init.tui.questionary")
    def test_issue_dirs_created(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        for subdir in ("bugs", "features", "enhancements", "epics"):
            assert (tmp_path / ".issues" / subdir).is_dir()

    @patch("little_loops.init.tui.questionary")
    def test_product_enabled_deploys_goals(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["product", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert (tmp_path / ".ll" / "ll-goals.md").exists()

    @patch("little_loops.init.tui.questionary")
    def test_no_product_no_goals_file(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert not (tmp_path / ".ll" / "ll-goals.md").exists()

    @patch("little_loops.init.tui.questionary")
    def test_local_settings_writes_settings_local_json(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, settings="local")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert (tmp_path / ".claude" / "settings.local.json").exists()

    @patch("little_loops.init.tui.questionary")
    def test_shared_settings_writes_settings_json(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, settings="shared")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert (tmp_path / ".claude" / "settings.json").exists()
        assert not (tmp_path / ".claude" / "settings.local.json").exists()

    @patch("little_loops.init.tui.questionary")
    def test_design_tokens_selected_deploys_profiles(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["design_tokens", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert (tmp_path / ".ll" / "design-tokens" / "profiles").is_dir()

    @patch("little_loops.init.tui.questionary")
    def test_learning_tests_adds_explore_api_permission(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        import json

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["learning_tests", "analytics"], settings="local")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
        assert "Skill(ll:explore-api)" in settings["permissions"]["allow"]


# ---------------------------------------------------------------------------
# Conditional parallel workers question
# ---------------------------------------------------------------------------


class TestConditionalParallel:
    @patch("little_loops.init.tui.questionary")
    def test_parallel_selected_asks_workers(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="6")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        # 6 basics + 1 focus_dirs (scan) + 1 workers = 8 text() calls
        assert mock_q.text.call_count == 8
        assert rc == 0

    @patch("little_loops.init.tui.questionary")
    def test_parallel_not_selected_skips_workers_question(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        # 6 basics + 1 focus_dirs (scan) = 7 text() calls — no workers question
        assert mock_q.text.call_count == 7
        assert rc == 0

    @patch("little_loops.init.tui.questionary")
    def test_non_default_workers_written_to_config(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="6")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["parallel"]["max_workers"] == 6

    @patch("little_loops.init.tui.questionary")
    def test_default_workers_omits_parallel_section(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="4")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "parallel" not in config

    @patch("little_loops.init.tui.questionary")
    def test_feature_branches_enabled_written_to_config(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="4", use_feature_branches=True)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config.get("parallel", {}).get("use_feature_branches") is True

    @patch("little_loops.init.tui.questionary")
    def test_feature_branches_disabled_not_written_to_config(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="4", use_feature_branches=False)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config.get("parallel", {}).get("use_feature_branches") is None


# ---------------------------------------------------------------------------
# Ctrl-C / abort
# ---------------------------------------------------------------------------


class TestCtrlC:
    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_on_first_prompt_returns_130(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            mock_q.text.return_value.ask.return_value = None  # Ctrl-C on name
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 130

    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_on_features_returns_130(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            # Screen 1: 6 basics, Screen 2: focus_dirs, Screen 2 confirm: add_excludes=False
            # Then features checkbox Ctrl-C
            mock_q.text.side_effect = [
                _mock_ask("myapp"),
                _mock_ask("src/"),
                _mock_ask("pytest"),
                _mock_ask("ruff check ."),
                _mock_ask("mypy"),
                _mock_ask("ruff format ."),
                _mock_ask("src/"),  # focus_dirs
            ]
            mock_q.confirm.side_effect = [
                _mock_ask(True),  # install_confirmed (screen 1, ENH-2253)
                _mock_ask(False),  # add_excludes
            ]
            mock_q.checkbox.side_effect = [_mock_ask(None)]  # features Ctrl-C
            mock_q.Choice.side_effect = lambda *a, **kw: MagicMock()
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 130

    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_on_confirm_returns_130(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            # confirmed=None triggers Ctrl-C on the final "Apply?" confirm
            _wire_q(mock_q, confirmed=None)
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 130

    @patch("little_loops.init.tui.questionary")
    def test_user_declines_confirm_returns_1_no_config(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, confirmed=False)
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 1
        assert not (tmp_path / ".ll" / "ll-config.json").exists()


# ---------------------------------------------------------------------------
# Existing config / force flag
# ---------------------------------------------------------------------------


class TestExistingConfig:
    @patch("little_loops.init.tui.questionary")
    def test_existing_config_without_force_pre_populates(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        """Without --force, wizard should still run and pre-fill from existing config."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        existing = {
            "project": {"name": "oldproject", "src_dir": "oldsrc/", "test_cmd": "old-pytest"},
            "analytics": {"enabled": True},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(existing))

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, name="oldproject", src_dir="oldsrc/", test_cmd="old-pytest")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, force=False)

        assert rc == 0
        assert mock_q.text.called  # wizard ran

    @patch("little_loops.init.tui.questionary")
    def test_existing_config_pre_populates_defaults(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        """Verify questionary prompts receive existing config values as the default= kwarg."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        existing = {
            "project": {
                "name": "myoldproject",
                "src_dir": "oldsrc/",
                "test_cmd": "old-pytest",
            },
            "analytics": {"enabled": True},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(existing))

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, name="myoldproject", src_dir="oldsrc/", test_cmd="old-pytest")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, force=False)

        calls = mock_q.text.call_args_list
        # Index 0: "Project name:" — should default to existing project name
        assert calls[0].kwargs.get("default") == "myoldproject"
        # Index 1: "Source directory:" — should default to existing src_dir
        assert calls[1].kwargs.get("default") == "oldsrc/"

    @patch("little_loops.init.tui.questionary")
    def test_existing_config_with_force_pre_populates(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        """--force still pre-fills from existing config and runs to completion."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text("{}")

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q)
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, force=True)

        assert rc == 0
        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "$schema" in config  # real config, not the empty placeholder


# ---------------------------------------------------------------------------
# _build_final_config unit tests
# ---------------------------------------------------------------------------


class TestBuildFinalConfig:
    @pytest.fixture
    def generic_template(self, tmp_path: Path) -> object:
        from little_loops.init.detect import detect_project_type

        return detect_project_type(tmp_path, _TEMPLATES_DIR)

    def test_command_overrides_applied(self, generic_template: object) -> None:
        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="lib/",
            test_cmd="cargo test",
            lint_cmd="clippy",
            type_cmd="",
            format_cmd="",
            selected_set={"analytics"},
            parallel_workers=4,
        )
        assert config["project"]["src_dir"] == "lib/"
        assert config["project"]["test_cmd"] == "cargo test"
        assert config["project"]["type_cmd"] is None
        assert config["project"]["format_cmd"] is None

    def test_documents_section_added_when_selected(self, generic_template: object) -> None:
        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="ruff",
            type_cmd="",
            format_cmd="",
            selected_set={"documents"},
            parallel_workers=4,
        )
        assert config["documents"]["enabled"] is True

    def test_design_tokens_section_added_when_selected(self, generic_template: object) -> None:
        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="ruff",
            type_cmd="",
            format_cmd="",
            selected_set={"design_tokens"},
            parallel_workers=4,
        )
        assert config["design_tokens"]["enabled"] is True

    def test_non_default_workers_writes_parallel_config(self, generic_template: object) -> None:
        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="ruff",
            type_cmd="",
            format_cmd="",
            selected_set={"parallel"},
            parallel_workers=8,
        )
        assert config["parallel"]["max_workers"] == 8

    def test_default_workers_omits_parallel_section(self, generic_template: object) -> None:
        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="ruff",
            type_cmd="",
            format_cmd="",
            selected_set={"parallel"},
            parallel_workers=4,
        )
        assert "parallel" not in config

    def test_analytics_disabled_when_not_selected(self, generic_template: object) -> None:
        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="ruff",
            type_cmd="",
            format_cmd="",
            selected_set=set(),
            parallel_workers=4,
        )
        assert config["analytics"]["enabled"] is False

    def test_product_disabled_omits_product_section(self, generic_template: object) -> None:
        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="ruff",
            type_cmd="",
            format_cmd="",
            selected_set=set(),
            parallel_workers=4,
        )
        assert "product" not in config


# ---------------------------------------------------------------------------
# Host multi-select screen
# ---------------------------------------------------------------------------


class TestHostSelection:
    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_on_hosts_returns_130(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            # Screen 1: 6 basics, Screen 2: focus_dirs + add_excludes=False confirm,
            # Screen 3: features=["analytics"] (no parallel/design_tokens) + session_digest confirm,
            # then hosts checkbox Ctrl-C
            mock_q.text.side_effect = [
                _mock_ask("myapp"),
                _mock_ask("src/"),
                _mock_ask("pytest"),
                _mock_ask("ruff check ."),
                _mock_ask("mypy"),
                _mock_ask("ruff format ."),
                _mock_ask("src/"),  # focus_dirs
            ]
            mock_q.confirm.side_effect = [
                _mock_ask(True),  # install_confirmed (screen 1, ENH-2253)
                _mock_ask(False),  # add_excludes
                _mock_ask(True),  # session_digest
                _mock_ask(True),  # prompt_optimization
                _mock_ask(True),  # loop_clear_default (ENH-2243)
            ]
            mock_q.checkbox.side_effect = [
                _mock_ask(["analytics"]),  # features
                _mock_ask(None),  # hosts — Ctrl-C
            ]
            mock_q.Choice.side_effect = lambda *a, **kw: MagicMock()
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 130

    @patch("little_loops.init.tui.questionary")
    def test_codex_host_installs_adapter(self, mock_q: MagicMock, tmp_path: Path) -> None:
        plugin_root = _PLUGIN_ROOT  # real plugin root has the adapter template
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], hosts=["codex"])
            rc = run_tui(tmp_path, _TEMPLATES_DIR, plugin_root)

        assert rc == 0
        assert (tmp_path / ".codex" / "hooks.json").exists()

    @patch("little_loops.init.tui.questionary")
    def test_claude_code_host_no_adapter_file(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], hosts=["claude-code"])
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 0
        # No .codex/hooks.json for claude-code (plugin hooks fire via global plugin)
        assert not (tmp_path / ".codex" / "hooks.json").exists()

    @patch("little_loops.init.tui.questionary")
    def test_pi_host_graceful_unavailable(
        self, mock_q: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], hosts=["pi"])
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 0
        assert "not yet available" in capsys.readouterr().out

    @patch("little_loops.init.tui.questionary")
    def test_detection_seeded_defaults_shown(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, hosts=["codex"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, hosts=["codex"])

        # features checkbox + parallel worktree_files checkbox + hosts checkbox = 3
        assert mock_q.checkbox.call_count == 3


# ---------------------------------------------------------------------------
# New parity features: github_sync / confidence_gate / tdd
# ---------------------------------------------------------------------------


class TestNewFeatureToggles:
    @patch("little_loops.init.tui.questionary")
    def test_github_sync_produces_sync_key(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["github_sync", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["sync"] == {"enabled": True}

    @patch("little_loops.init.tui.questionary")
    def test_confidence_gate_produces_commands_key(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["confidence_gate", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["commands"]["confidence_gate"]["enabled"] is True
        assert config["commands"]["confidence_gate"]["readiness_threshold"] == 85

    @patch("little_loops.init.tui.questionary")
    def test_tdd_mode_produces_commands_tdd_key(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["tdd", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["commands"]["tdd_mode"] is True

    @patch("little_loops.init.tui.questionary")
    def test_confidence_gate_and_tdd_merged_into_one_commands_block(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["confidence_gate", "tdd", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["commands"]["confidence_gate"]["enabled"] is True
        assert config["commands"]["tdd_mode"] is True

    @patch("little_loops.init.tui.questionary")
    def test_decisions_toggle_produces_decisions_key(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["decisions", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["decisions"] == {"enabled": True}

    @patch("little_loops.init.tui.questionary")
    def test_scratch_pad_toggle_produces_scratch_pad_key(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["scratch_pad", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["scratch_pad"] == {"enabled": True}

    @patch("little_loops.init.tui.questionary")
    def test_session_capture_toggle_produces_session_capture_key(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["session_capture", "analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["session_capture"] == {"enabled": True}

    @patch("little_loops.init.tui.questionary")
    def test_new_toggles_omitted_when_not_selected(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "decisions" not in config
        assert "scratch_pad" not in config
        assert "session_capture" not in config

    @patch("little_loops.init.tui.questionary")
    def test_prompt_optimization_opt_out_writes_disabled(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], prompt_optimization=False)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["prompt_optimization"] == {"enabled": False}

    @patch("little_loops.init.tui.questionary")
    def test_prompt_optimization_default_on_omits_key(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], prompt_optimization=True)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "prompt_optimization" not in config


# ---------------------------------------------------------------------------
# Design-token profile picker
# ---------------------------------------------------------------------------


class TestDesignTokenProfilePicker:
    @patch("little_loops.init.tui.questionary")
    def test_profile_warm_paper_written_to_config(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True

            # Wire basics (no parallel → 7 text calls), then design_tokens feature selected
            # Profile select must fire before session_digest confirm and settings select
            text_returns = [
                "proj",
                "src/",
                "pytest",
                "ruff check .",
                "mypy",
                "ruff format .",
                "src/",
            ]
            mock_q.text.side_effect = [_mock_ask(v) for v in text_returns]
            mock_q.checkbox.side_effect = [
                _mock_ask(["design_tokens", "analytics"]),  # features
                _mock_ask(["claude-code"]),  # hosts
            ]
            mock_q.select.side_effect = [
                _mock_ask("warm-paper"),  # profile picker (screen 3)
                _mock_ask("clean"),  # loop_show_diagrams_default (ENH-2243)
                _mock_ask("local"),  # settings (screen 5)
                _mock_ask("skip"),  # CLAUDE.md (screen 6)
            ]
            mock_q.confirm.side_effect = [
                _mock_ask(True),  # install_confirmed (screen 1, ENH-2253)
                _mock_ask(False),  # add_excludes
                _mock_ask(True),  # session_digest
                _mock_ask(True),  # prompt_optimization
                _mock_ask(True),  # loop_clear_default (ENH-2243)
                _mock_ask(True),  # apply
            ]
            mock_q.Choice.side_effect = lambda *a, **kw: MagicMock()
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 0
        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["design_tokens"]["active"] == "warm-paper"

    @patch("little_loops.init.tui.questionary")
    def test_design_tokens_no_profile_prompt_when_not_selected(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "design_tokens" not in config


# ---------------------------------------------------------------------------
# Scan screen
# ---------------------------------------------------------------------------


class TestScanScreen:
    @patch("little_loops.init.tui.questionary")
    def test_custom_focus_dirs_written_to_config(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], focus_dirs="app/, lib/")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["scan"]["focus_dirs"] == ["app/", "lib/"]

    @patch("little_loops.init.tui.questionary")
    def test_custom_excludes_appended_to_template_defaults(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(
                mock_q,
                features=["analytics"],
                add_excludes=True,
                custom_excludes="**/scratch/**",
            )
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "**/scratch/**" in config["scan"]["exclude_patterns"]

    @patch("little_loops.init.tui.questionary")
    def test_no_custom_excludes_by_default(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], add_excludes=False)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        # Confirm: add_excludes was called, custom_excludes text was NOT called
        # (7 text calls: 6 basics + focus_dirs)
        assert mock_q.text.call_count == 7


# ---------------------------------------------------------------------------
# Worktree copy files
# ---------------------------------------------------------------------------


class TestWorktreeCopyFiles:
    @patch("little_loops.init.tui.questionary")
    def test_worktree_files_written_to_config(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel", "analytics"], worktree_files=[".env", ".secrets"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["parallel"]["worktree_copy_files"] == [".env", ".secrets"]

    @patch("little_loops.init.tui.questionary")
    def test_empty_worktree_files_no_key(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel", "analytics"], workers="4", worktree_files=[])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        # Neither max_workers nor worktree_copy_files → parallel section omitted
        assert "parallel" not in config


# ---------------------------------------------------------------------------
# Session digest
# ---------------------------------------------------------------------------


class TestSessionDigest:
    @patch("little_loops.init.tui.questionary")
    def test_session_digest_off_written_to_config(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], session_digest=False)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["history"]["session_digest"]["enabled"] is False

    @patch("little_loops.init.tui.questionary")
    def test_session_digest_on_by_default(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["history"]["session_digest"]["enabled"] is True


# ---------------------------------------------------------------------------
# Settings "Skip" option
# ---------------------------------------------------------------------------


class TestSettingsSkip:
    @patch("little_loops.init.tui.questionary")
    def test_settings_skip_writes_no_settings_file(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], settings="skip")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert not (tmp_path / ".claude" / "settings.local.json").exists()
        assert not (tmp_path / ".claude" / "settings.json").exists()

    @patch("little_loops.init.tui.questionary")
    def test_settings_skip_still_writes_config(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], settings="skip")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert (tmp_path / ".ll" / "ll-config.json").exists()


# ---------------------------------------------------------------------------
# _build_final_config unit tests — new parity params
# ---------------------------------------------------------------------------


class TestBuildFinalConfigParity:
    @pytest.fixture
    def generic_template(self, tmp_path: Path) -> object:
        from little_loops.init.detect import detect_project_type

        return detect_project_type(tmp_path, _TEMPLATES_DIR)

    def _base_kwargs(self, template: object) -> dict:
        return {
            "template": template,
            "name": "proj",
            "src_dir": "src/",
            "test_cmd": "pytest",
            "lint_cmd": "ruff",
            "type_cmd": "",
            "format_cmd": "",
            "parallel_workers": 4,
        }

    def test_github_sync_key(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set={"github_sync"},
        )
        assert config["sync"] == {"enabled": True}

    def test_confidence_gate_key(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set={"confidence_gate"},
        )
        assert config["commands"]["confidence_gate"]["enabled"] is True
        assert config["commands"]["confidence_gate"]["readiness_threshold"] == 85

    def test_tdd_key(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set={"tdd"},
        )
        assert config["commands"]["tdd_mode"] is True

    def test_session_digest_disabled(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set=set(),
            session_digest_enabled=False,
        )
        assert config["history"]["session_digest"]["enabled"] is False

    def test_design_token_profile_in_config(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set={"design_tokens"},
            design_token_profile="warm-paper",
        )
        assert config["design_tokens"]["active"] == "warm-paper"

    def test_documents_categories_written(self, generic_template: object) -> None:
        cats = {"architecture": {"description": "Arch docs", "files": ["docs/ARCH.md"]}}
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set={"documents"},
            documents_categories=cats,
        )
        assert config["documents"]["categories"] == cats

    def test_custom_focus_dirs_in_scan(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set=set(),
            scan_focus_dirs=["app/", "lib/"],
        )
        assert config["scan"]["focus_dirs"] == ["app/", "lib/"]

    def test_custom_excludes_appended(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set=set(),
            scan_custom_excludes=["**/scratch/**"],
        )
        assert "**/scratch/**" in config["scan"]["exclude_patterns"]

    def test_worktree_copy_files_in_parallel(self, generic_template: object) -> None:
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set={"parallel"},
            worktree_copy_files=[".env", ".secrets"],
        )
        assert config["parallel"]["worktree_copy_files"] == [".env", ".secrets"]

    def test_yes_path_unaffected_by_new_defaults(self, generic_template: object) -> None:
        """--yes path: calling _build_final_config with all defaults is unchanged."""
        config = _build_final_config(
            **self._base_kwargs(generic_template),
            selected_set={"parallel", "product", "learning_tests", "analytics", "context_monitor"},
        )
        # No new top-level keys added by default
        assert "sync" not in config
        assert "commands" not in config
