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
    features: list[str] | None = None,
    workers: str = "4",
    hosts: list[str] | None = None,
    settings: str = "local",
    confirmed: bool | None = True,
) -> None:
    """Wire a questionary mock for a complete TUI interaction.

    There are now two checkbox() calls: one for features (screen 2) and one for
    hosts (screen 3). Use side_effect to return the right value per call.
    """
    if features is None:
        features = ["parallel", "product", "learning_tests", "analytics", "context_monitor"]
    if hosts is None:
        hosts = ["claude-code"]

    text_returns = [name, src_dir, test_cmd, lint_cmd, type_cmd, format_cmd]
    if "parallel" in features:
        text_returns.append(workers)

    mock_q.text.side_effect = [_mock_ask(v) for v in text_returns]
    # Two checkbox calls: first is features, second is hosts
    mock_q.checkbox.side_effect = [_mock_ask(features), _mock_ask(hosts)]
    mock_q.select.return_value.ask.return_value = settings
    mock_q.confirm.return_value.ask.return_value = confirmed
    # Choice is used only to build the checkbox lists; let it return a plain MagicMock
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

        for subdir in ("bugs", "features", "enhancements", "completed", "deferred"):
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
    def test_shared_settings_writes_settings_json(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, settings="shared")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert (tmp_path / ".claude" / "settings.json").exists()
        assert not (tmp_path / ".claude" / "settings.local.json").exists()


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

        # 6 basics + 1 workers question = 7 text() calls (hosts is a checkbox, not text)
        assert mock_q.text.call_count == 7
        assert rc == 0

    @patch("little_loops.init.tui.questionary")
    def test_parallel_not_selected_skips_workers_question(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        # 6 basics only — no workers question
        assert mock_q.text.call_count == 6
        assert rc == 0

    @patch("little_loops.init.tui.questionary")
    def test_non_default_workers_written_to_config(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
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


# ---------------------------------------------------------------------------
# Ctrl-C / abort
# ---------------------------------------------------------------------------


class TestCtrlC:
    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_on_first_prompt_returns_130(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            mock_q.text.return_value.ask.return_value = None  # Ctrl-C on name
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 130

    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_on_features_returns_130(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            # Basics answer normally, features returns None (Ctrl-C on first checkbox)
            mock_q.text.side_effect = [
                _mock_ask("myapp"),
                _mock_ask("src/"),
                _mock_ask("pytest"),
                _mock_ask("ruff check ."),
                _mock_ask("mypy"),
                _mock_ask("ruff format ."),
            ]
            mock_q.checkbox.side_effect = [_mock_ask(None)]
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 130

    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_on_confirm_returns_130(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
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
    def test_existing_config_without_force_returns_1_no_prompts(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text("{}")

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, force=False)

        assert rc == 1
        mock_q.text.assert_not_called()

    @patch("little_loops.init.tui.questionary")
    def test_existing_config_with_force_overwrites(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
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

    def test_non_default_workers_writes_parallel_config(
        self, generic_template: object
    ) -> None:
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
            # Features returns normally, hosts returns None (Ctrl-C on second checkbox)
            mock_q.text.side_effect = [
                _mock_ask("myapp"),
                _mock_ask("src/"),
                _mock_ask("pytest"),
                _mock_ask("ruff check ."),
                _mock_ask("mypy"),
                _mock_ask("ruff format ."),
            ]
            mock_q.checkbox.side_effect = [
                _mock_ask(["analytics"]),  # features
                _mock_ask(None),           # hosts — Ctrl-C
            ]
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

        # Verify two checkbox() calls were made (features + hosts)
        assert mock_q.checkbox.call_count == 2
