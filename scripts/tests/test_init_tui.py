"""Tests for little_loops.init.tui — interactive TUI frontend."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.init.tui import _build_final_config, run_tui
from little_loops.issue_template import get_bundled_templates_dir

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # little-loops root
_TEMPLATES_DIR = get_bundled_templates_dir()
_PLUGIN_ROOT = _PROJECT_ROOT


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_detect_installation() -> MagicMock:
    """Mock detect_installation to return (None, None, None) for all TUI tests.

    Ensures the Round 1 install-check confirm always fires (not-installed path)
    so confirm_returns lists in _wire_q() are always positionally consistent.
    """
    with patch(
        "little_loops.init.install_check.detect_installation",
        return_value=(None, None, None),
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def _default_plugin_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """FEAT-3372: stub the claude-code plugin-presence gate to True by default.

    `_apply_config()` calls `_dispatch_host_adapters()` with no `dry_run` kwarg
    (always real, unlike the headless `--dry-run`-aware paths), so any TUI
    test reaching it with claude-code selected would otherwise hit the real
    `claude` binary on PATH. Tests exercising the install branch itself
    override this via their own explicit `patch(...)`.
    """
    monkeypatch.setattr("little_loops.init.install_check.plugin_installed", lambda binary: True)


@pytest.fixture(autouse=True)
def _no_codegraph_on_this_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report "no codegraph, no npm" so init tests never shell out to codegraph/npm.

    The dev machine has codegraph on PATH; without this guard every --yes run
    would build a real index in the tmp project (slow, and not what these tests
    exercise). test_init_codegraph.py covers the real detection paths.
    """
    from little_loops.init.codegraph import CodegraphStatus

    def _none(project_root: Path, db_path: str | None = None) -> CodegraphStatus:
        return CodegraphStatus(
            binary=None,
            index_present=(Path(project_root) / ".codegraph" / "codegraph.db").is_file(),
            db_path=Path(project_root) / ".codegraph" / "codegraph.db",
            node=None,
            npm=None,
            npx=None,
        )

    monkeypatch.setattr("little_loops.init.codegraph.detect_codegraph", _none)


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
    path: str = "customize",
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
    use_epic_branches: bool = False,
    design_token_profile: str = "default",
    advanced: bool = True,
    session_digest: bool = True,
    prompt_optimization: bool = True,
    loop_clear_default: bool = True,
    diagram_mode: str = "clean",
    hosts: list[str] | None = None,
    settings: str = "local",
    claude_md: str = "yes",
    code_graph: str = "skip",
    install_confirmed: bool = True,
    confirmed: bool | None = True,
    kimi_confirm: bool = True,
    ctrl_c_at: str | None = None,
) -> None:
    """Wire a questionary mock for a complete wizard interaction.

    Prompts are answered by *message*, not by position, so the harness is
    independent of screen order. Express-first flow (2026-09 audit):

      env line + Detected setup panel → "How do you want to proceed?" (select:
      ``path`` = accept | customize | cancel)
      Customize: Project (text/select) → Scan (text, confirm) → Features
      (checkbox + parallel/design-token follow-ups) → Hosts (checkbox,
      kimi confirm) → Claude Code (settings select, CLAUDE.md select; only
      when claude-code selected) → Advanced (gate confirm, then 3 confirms +
      diagram select)
      Both: Code graph (select, only when codegraph/npm available) →
      summary → "Apply this configuration?" (confirm)

    ``ctrl_c_at`` returns ``None`` (Ctrl-C) for the first prompt whose
    message contains that substring.
    """
    if features is None:
        features = ["parallel", "product", "learning_tests", "analytics", "context_monitor"]
    if hosts is None:
        hosts = ["claude-code"]
    if worktree_files is None:
        worktree_files = []

    def _answer(message: str, value: object) -> MagicMock:
        if ctrl_c_at is not None and ctrl_c_at in message:
            return _mock_ask(None)
        return _mock_ask(value)

    def text(message: str = "", **kw: object) -> MagicMock:
        table: list[tuple[str, object]] = [
            ("Project name", name),
            ("Source directory", src_dir),
            ("Test command", test_cmd),
            ("Lint command", lint_cmd),
            ("Type-check", type_cmd),
            ("Format command", format_cmd),
            ("Focus directories", focus_dirs),
            ("Custom exclude", custom_excludes),
            ("Max parallel workers", workers),
            ("Custom profile path", design_token_profile),
        ]
        for key, value in table:
            if message.startswith(key):
                return _answer(message, value)
        return _answer(message, kw.get("default", ""))

    def confirm(message: str = "", **kw: object) -> MagicMock:
        table: list[tuple[str, object]] = [
            ("Proceed with wizard", install_confirmed),
            ("Add custom exclude", add_excludes),
            ("feature-branch", use_feature_branches),
            ("per-EPIC", use_epic_branches),
            ("Configure advanced", advanced),
            ("session digest", session_digest),
            ("prompt optimization", prompt_optimization),
            ("--clear", loop_clear_default),
            ("Kimi", kimi_confirm),
            ("Apply this configuration", confirmed),
        ]
        for key, value in table:
            if key in message:
                return _answer(message, value)
        return _answer(message, kw.get("default", True))

    def checkbox(message: str = "", **kw: object) -> MagicMock:
        if "Enable features" in message:
            return _answer(message, list(features))
        if "Copy these files" in message:
            return _answer(message, list(worktree_files))
        if "host harnesses" in message:
            return _answer(message, list(hosts))
        return _answer(message, [])

    def select(message: str = "", **kw: object) -> MagicMock:
        table: list[tuple[str, object]] = [
            ("How do you want to proceed", path),
            ("Test command", test_cmd),
            ("Lint command", lint_cmd),
            ("Format command", format_cmd),
            ("Design-token profile", design_token_profile),
            ("diagram mode", diagram_mode),
            ("permissions", settings),
            ("CLAUDE.md", claude_md),
            ("codegraph", code_graph),
        ]
        for key, value in table:
            if key in message:
                return _answer(message, value)
        return _answer(message, kw.get("default"))

    mock_q.text.side_effect = text
    mock_q.confirm.side_effect = confirm
    mock_q.checkbox.side_effect = checkbox
    mock_q.select.side_effect = select
    # Choice is used only to build checkbox/select lists; let it return a plain MagicMock
    mock_q.Choice.side_effect = lambda *a, **kw: MagicMock()


# ---------------------------------------------------------------------------
# Non-TTY detection
# ---------------------------------------------------------------------------


class TestNonTTY:
    def test_non_tty_falls_back_to_headless(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """No TTY → the headless --yes flow runs with the same defaults (2026-09 audit)."""
        with (
            patch("sys.stdin") as mock_stdin,
            patch("little_loops.init.cli._run_yes", return_value=0) as run_yes,
        ):
            mock_stdin.isatty.return_value = False
            rc = run_tui(
                tmp_path,
                _TEMPLATES_DIR,
                _PLUGIN_ROOT,
                hosts=["codex"],
                code_graph="skip",
                settings_target="shared",
                claude_md=False,
            )

        assert rc == 0
        run_yes.assert_called_once()
        kwargs = run_yes.call_args.kwargs
        assert kwargs["project_root"] == tmp_path
        assert kwargs["hosts"] == ["codex"]
        assert kwargs["settings_target"] == "shared"
        assert kwargs["claude_md"] is False
        assert kwargs["code_graph"] == "skip"
        assert "not a TTY" in capsys.readouterr().out

    def test_non_tty_writes_config_end_to_end(self, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, hosts=["claude-code"])
        assert rc == 0
        assert (tmp_path / ".ll" / "ll-config.json").exists()


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
    def test_deploy_issue_templates_via_tui(self, mock_q: MagicMock, tmp_path: Path) -> None:
        from little_loops.init import tui as tui_mod

        real_build = tui_mod._build_final_config

        def patched_build(**kwargs):
            cfg = real_build(**kwargs)
            cfg.setdefault("issues", {})["deploy_templates"] = True
            return cfg

        with (
            patch("sys.stdin") as mock_stdin,
            patch("little_loops.init.tui._build_final_config", side_effect=patched_build),
        ):
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert (tmp_path / ".ll" / "templates").is_dir()
        assert len(list((tmp_path / ".ll" / "templates").glob("*-sections.json"))) >= 4

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
        # The omit-on-default sentinel is schema-derived (parallel.max_workers
        # default is 2 — audit H-4), so accepting the prompt default must NOT
        # silently drop the section's only key.
        from little_loops.init.core import schema_default

        default_workers = str(schema_default("parallel.max_workers"))
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers=default_workers)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "parallel" not in config

    @patch("little_loops.init.tui.questionary")
    def test_old_sentinel_workers_now_written(self, mock_q: MagicMock, tmp_path: Path) -> None:
        """Audit H-4 regression: 4 was the old hard-coded sentinel and was
        silently dropped; it is a non-default value and must be written."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="4")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["parallel"]["max_workers"] == 4

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

    @patch("little_loops.init.tui.questionary")
    def test_epic_branches_enabled_written_to_config(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="4", use_epic_branches=True)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config.get("parallel", {}).get("epic_branches", {}).get("enabled") is True

    @patch("little_loops.init.tui.questionary")
    def test_epic_branches_disabled_not_written_to_config(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["parallel"], workers="4", use_epic_branches=False)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert "epic_branches" not in config.get("parallel", {})


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
            _wire_q(mock_q, ctrl_c_at="Enable features")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 130
        assert not (tmp_path / ".ll").exists()

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

    @patch("little_loops.init.tui.questionary")
    def test_tui_reinit_preserves_unmodeled_keys(self, mock_q: MagicMock, tmp_path: Path) -> None:
        """A full TUI re-init round-trip preserves keys the wizard does not model (BUG-2310)."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        existing = {
            "project": {"name": "oldproject"},
            "sprints": {"default_max_workers": 7},
            "my_custom_section": {"key": "value"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(existing))

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, name="oldproject")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, force=False)

        assert rc == 0
        config = json.loads((ll_dir / "ll-config.json").read_text())
        assert config["sprints"] == {"default_max_workers": 7}
        assert config["my_custom_section"] == {"key": "value"}

    @patch("little_loops.init.tui.questionary")
    def test_tui_reinit_force_drops_unmodeled_keys(self, mock_q: MagicMock, tmp_path: Path) -> None:
        """A forced TUI re-init resets to template defaults, dropping unmodeled keys (BUG-2310)."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        existing = {
            "project": {"name": "oldproject"},
            "my_custom_section": {"key": "value"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(existing))

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, name="oldproject")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, force=True)

        assert rc == 0
        config = json.loads((ll_dir / "ll-config.json").read_text())
        assert "my_custom_section" not in config


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
        from little_loops.init.core import schema_default

        config = _build_final_config(
            template=generic_template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="ruff",
            type_cmd="",
            format_cmd="",
            selected_set={"parallel"},
            parallel_workers=int(schema_default("parallel.max_workers")),
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
            _wire_q(mock_q, features=["analytics"], ctrl_c_at="host harnesses")
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
    def test_codex_adapter_staleness_row_shown(
        self, mock_q: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """FEAT-2387: Screen-1 surfaces a staleness row when the codex adapter's
        gen-version stamp diverges from the installed package version."""
        codex = tmp_path / ".codex"
        codex.mkdir()
        (codex / "hooks.json").write_text('{"_ll_gen_version": "0.0.1", "hooks": {}}')
        with (
            patch("sys.stdin") as mock_stdin,
            # Override the autouse (None,None,None) fixture: a known install +
            # version so the staleness comparison path is exercised.
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=("pypi", "9.9.9", None),
            ),
            patch(
                "little_loops.init.install_check.fetch_latest_pypi",
                return_value="9.9.9",
            ),
        ):
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], hosts=["codex"])
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, hosts=["codex"])

        assert rc == 0
        out = capsys.readouterr().out
        assert "Codex adapter outdated" in out
        assert "0.0.1" in out

    @patch("little_loops.init.tui.questionary")
    def test_kimi_selection_requires_confirm(self, mock_q: MagicMock, tmp_path: Path) -> None:
        """Declining the user-global write drops kimi-code from the selection."""
        with (
            patch("sys.stdin") as mock_stdin,
            patch("little_loops.init.writers.install_kimi_adapter") as install_kimi,
        ):
            mock_stdin.isatty.return_value = True
            _wire_q(
                mock_q,
                features=["analytics"],
                hosts=["claude-code", "kimi-code"],
                kimi_confirm=False,
            )
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 0
        install_kimi.assert_not_called()
        confirm_messages = [c.args[0] for c in mock_q.confirm.call_args_list if c.args]
        assert any("user-global" in m for m in confirm_messages)

    @patch("little_loops.init.tui.questionary")
    def test_settings_screen_skipped_without_claude_code(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], hosts=["codex"])
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert rc == 0
        select_messages = [c.args[0] for c in mock_q.select.call_args_list if c.args]
        assert not any("permissions" in m for m in select_messages)
        assert not any("CLAUDE.md" in m for m in select_messages)
        assert not (tmp_path / ".claude").exists()
        assert (tmp_path / "AGENTS.md").exists()

    @patch("little_loops.init.tui.questionary")
    def test_host_choices_show_availability(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with (
            patch("sys.stdin") as mock_stdin,
            patch(
                "little_loops.init.cli.shutil.which",
                side_effect=lambda b: b if b == "claude" else None,
            ),
        ):
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        labels = [c.args[0] for c in mock_q.Choice.call_args_list if c.args]
        assert any(label.startswith("Claude Code") and "[detected]" in label for label in labels)
        assert any(label.startswith("Codex") and "[not on PATH]" in label for label in labels)
        assert any(label.startswith("Gemini") for label in labels)
        pi = next(c for c in mock_q.Choice.call_args_list if c.args and c.args[0].startswith("Pi"))
        assert pi.kwargs.get("disabled")

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
        assert config["commands"]["confidence_gate"]["outcome_threshold"] == 65

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
    def test_prompt_optimization_opt_in_writes_enabled(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], prompt_optimization=True)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["prompt_optimization"] == {"enabled": True}

    @patch("little_loops.init.tui.questionary")
    def test_prompt_optimization_default_off_omits_key(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], prompt_optimization=False)
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
            _wire_q(
                mock_q,
                features=["design_tokens", "analytics"],
                design_token_profile="warm-paper",
                claude_md="skip",
            )
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
        from little_loops.init.core import schema_default

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(
                mock_q,
                features=["parallel", "analytics"],
                workers=str(schema_default("parallel.max_workers")),
                worktree_files=[],
            )
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


class TestNoGitRepoNotice:
    """ENH-3011: TUI warning panel surfaces the same no-git-repo notice."""

    @patch("little_loops.init.tui.questionary")
    def test_no_git_repo_prints_notice(
        self, mock_q: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert "isn't a git repository" in capsys.readouterr().out

    @patch("little_loops.init.tui.questionary")
    def test_git_repo_prints_no_notice(
        self, mock_q: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        (tmp_path / ".git").mkdir()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"])
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        assert "isn't a git repository" not in capsys.readouterr().out


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
        assert config["commands"]["confidence_gate"]["outcome_threshold"] == 65

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


# ---------------------------------------------------------------------------
# _apply_config — install_source propagation (BUG-3380)
# ---------------------------------------------------------------------------


class TestApplyConfigInstallSource:
    """BUG-3380: _apply_config() must thread install_source/install_path into
    the generated CLAUDE.md Install: line — no existing test called
    _apply_config() directly before this."""

    @pytest.fixture
    def generic_template(self, tmp_path: Path) -> object:
        from little_loops.init.detect import detect_project_type

        return detect_project_type(tmp_path, _TEMPLATES_DIR)

    def _apply(
        self,
        tmp_path: Path,
        generic_template: object,
        install_source: str | None,
        install_path: str | None,
    ) -> Path:
        from rich.console import Console

        from little_loops.init.tui import _apply_config

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
        project_root = tmp_path
        ll_dir = project_root / ".ll"
        _apply_config(
            config=config,
            project_root=project_root,
            ll_dir=ll_dir,
            config_path=ll_dir / "ll-config.json",
            templates_dir=_TEMPLATES_DIR,
            plugin_root=_PLUGIN_ROOT,
            hosts=[],
            settings_target="skip",
            force=False,
            console=Console(),
            claude_md_opt_in=True,
            install_source=install_source,
            install_path=install_path,
        )
        return project_root / ".claude" / "CLAUDE.md"

    def test_pypi_install_source_reaches_claude_md(
        self, tmp_path: Path, generic_template: object
    ) -> None:
        claude_md = self._apply(tmp_path, generic_template, "pypi", None)
        content = claude_md.read_text(encoding="utf-8")
        assert "Install: `pip install little-loops`" in content
        assert "./scripts[dev]" not in content

    def test_local_editable_install_path_reaches_claude_md(
        self, tmp_path: Path, generic_template: object
    ) -> None:
        editable_path = tmp_path / "scripts"
        claude_md = self._apply(tmp_path, generic_template, "local-editable", str(editable_path))
        content = claude_md.read_text(encoding="utf-8")
        assert 'Install: `pip install -e "./scripts[dev]"`' in content

    def test_stale_commands_block_survives_unchanged(
        self, tmp_path: Path, generic_template: object
    ) -> None:
        """ENH-3382: the TUI path never passes refresh=True — _apply_config()
        redirects users to `ll-init --upgrade` for refreshes (see the Screen-1
        hint), so an existing block (with a stale Install: line) must be left
        byte-identical."""
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"
        claude_md_path.parent.mkdir(parents=True)
        stale = (
            "# Config\n"
            "\n"
            "## little-loops CLI Commands\n"
            "\n"
            'Install: `pip install -e "./scripts[dev]"`\n'
        )
        claude_md_path.write_text(stale, encoding="utf-8")

        claude_md = self._apply(tmp_path, generic_template, "pypi", None)
        assert claude_md == claude_md_path
        assert claude_md.read_text(encoding="utf-8") == stale


# ---------------------------------------------------------------------------
# Wizard seeds its defaults from manifest introspection (audit finding A)
# ---------------------------------------------------------------------------


class TestWizardSeedsFromIntrospection:
    @patch("little_loops.init.tui.questionary")
    def test_prompts_default_to_introspected_values_with_evidence(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n[tool.ruff]\n[tool.mypy]\n"
        )
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        (tmp_path / "tests").mkdir()

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        text_calls = mock_q.text.call_args_list
        # "Source directory:" is the second text prompt
        assert text_calls[1].kwargs["default"] == "mypkg/"
        assert "inferred" in (text_calls[1].kwargs.get("instruction") or "")
        # "Type-check command (optional):" carries the [tool.mypy] evidence
        type_call = next(c for c in text_calls if c.args and c.args[0].startswith("Type-check"))
        assert type_call.kwargs["default"] == "mypy"
        assert "[tool.mypy]" in (type_call.kwargs.get("instruction") or "")
        # Test/Lint commands go through select with the declared value pre-selected
        select_calls = mock_q.select.call_args_list
        test_call = next(c for c in select_calls if c.args and c.args[0] == "Test command:")
        assert test_call.kwargs["default"] == "pytest"
        assert "[tool.pytest.ini_options]" in (test_call.kwargs.get("instruction") or "")
        # Focus dirs seeded from the adopted src_dir + tests/
        focus_call = next(c for c in text_calls if c.args and c.args[0].startswith("Focus"))
        assert focus_call.kwargs["default"] == "mypkg/, tests/"

    @patch("little_loops.init.tui.questionary")
    def test_detected_command_outside_curated_menu_is_inserted(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "Makefile").write_text("test:\n\tpytest\n")

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q)
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)

        test_call = next(
            c for c in mock_q.select.call_args_list if c.args and c.args[0] == "Test command:"
        )
        assert test_call.kwargs["default"] == "make test"
        choice_labels = [c.args[0] for c in mock_q.Choice.call_args_list if c.args]
        assert "make test" in choice_labels


# ---------------------------------------------------------------------------
# Express-first flow: accept path + advanced gate (2026-09 audit, finding E)
# ---------------------------------------------------------------------------


class TestAcceptPath:
    @patch("little_loops.init.tui.questionary")
    def test_accept_writes_proposal_unchanged(self, mock_q: MagicMock, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n[tool.ruff]\n")
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, path="accept")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, hosts=["claude-code"])

        assert rc == 0
        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["project"]["test_cmd"] == "pytest"
        assert config["project"]["lint_cmd"] == "ruff check ."
        assert config["project"]["src_dir"] == "mypkg/"
        assert config["context_monitor"]["enabled"] is True  # recommended feature
        # No customization prompts fired: just the fork select and the final confirm.
        assert mock_q.text.call_count == 0
        assert mock_q.checkbox.call_count == 0
        confirm_messages = [c.args[0] for c in mock_q.confirm.call_args_list if c.args]
        assert confirm_messages[-1] == "Apply this configuration?"
        # Only the (patched-as-missing) install notice precedes it — no customization prompts.
        assert all(
            m.startswith(("Proceed with wizard", "Apply this configuration"))
            for m in confirm_messages
        )
        # Claude surfaces written with the CLI defaults (settings local, CLAUDE.md on).
        assert (tmp_path / ".claude" / "settings.local.json").exists()
        assert (tmp_path / ".claude" / "CLAUDE.md").exists()

    @patch("little_loops.init.tui.questionary")
    def test_accept_matches_headless_yes(self, mock_q: MagicMock, tmp_path: Path) -> None:
        """Accept path and `ll-init --yes` write the same config."""
        from little_loops.init.cli import main_init

        wizard = tmp_path / "wizard"
        headless = tmp_path / "headless"
        for project in (wizard, headless):
            project.mkdir()
            (project / "pyproject.toml").write_text("[tool.ruff]\n[tool.mypy]\n")

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, path="accept")
            assert run_tui(wizard, _TEMPLATES_DIR, _PLUGIN_ROOT, hosts=["claude-code"]) == 0
        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PLUGIN_ROOT),
            patch("little_loops.init.install_check.plugin_installed", return_value=True),
        ):
            assert (
                main_init(
                    [
                        "--yes",
                        "--hosts",
                        "claude-code",
                        "--code-graph",
                        "skip",
                        "--root",
                        str(headless),
                    ]
                )
                == 0
            )
        w = json.loads((wizard / ".ll" / "ll-config.json").read_text())
        h = json.loads((headless / ".ll" / "ll-config.json").read_text())
        for key in ("project", "scan", "learning_tests", "context_monitor", "history", "loops"):
            w_section = {k: v for k, v in w[key].items() if k != "name"}
            h_section = {k: v for k, v in h[key].items() if k != "name"}
            assert w_section == h_section, key

    @patch("little_loops.init.tui.questionary")
    def test_accept_respects_no_claude_md_and_settings_flags(
        self, mock_q: MagicMock, tmp_path: Path
    ) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, path="accept")
            rc = run_tui(
                tmp_path,
                _TEMPLATES_DIR,
                _PLUGIN_ROOT,
                hosts=["claude-code"],
                settings_target="skip",
                claude_md=False,
            )
        assert rc == 0
        assert not (tmp_path / ".claude").exists()

    @patch("little_loops.init.tui.questionary")
    def test_cancel_at_fork_writes_nothing(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, path="cancel")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)
        assert rc == 1
        assert not (tmp_path / ".ll").exists()

    @patch("little_loops.init.tui.questionary")
    def test_ctrl_c_at_fork_returns_130(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, ctrl_c_at="How do you want to proceed")
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)
        assert rc == 130

    @patch("little_loops.init.tui.questionary")
    def test_detection_panel_shows_evidence(
        self, mock_q: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, path="accept")
            run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT, hosts=["claude-code"])
        out = capsys.readouterr().out
        assert "Detected setup" in out
        assert "[tool.ruff]" in out
        assert "How do you want to proceed" not in out  # the prompt is questionary's, not ours


class TestAdvancedGate:
    @patch("little_loops.init.tui.questionary")
    def test_advanced_skipped_by_default(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(mock_q, features=["analytics"], advanced=False)
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)
        assert rc == 0
        confirm_messages = [c.args[0] for c in mock_q.confirm.call_args_list if c.args]
        assert any("Configure advanced" in m for m in confirm_messages)
        assert not any(m.startswith("Enable ambient session digest") for m in confirm_messages)
        select_messages = [c.args[0] for c in mock_q.select.call_args_list if c.args]
        assert not any("diagram mode" in m for m in select_messages)
        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        # defaults still written
        assert config["history"]["session_digest"]["enabled"] is True
        assert config["loops"]["run_defaults"] == {"clear": True, "show_diagrams": "clean"}

    @patch("little_loops.init.tui.questionary")
    def test_advanced_answers_are_applied(self, mock_q: MagicMock, tmp_path: Path) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            _wire_q(
                mock_q,
                features=["analytics"],
                advanced=True,
                session_digest=False,
                prompt_optimization=True,
                loop_clear_default=False,
                diagram_mode="__disabled__",
            )
            rc = run_tui(tmp_path, _TEMPLATES_DIR, _PLUGIN_ROOT)
        assert rc == 0
        config = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        assert config["history"]["session_digest"]["enabled"] is False
        assert config["prompt_optimization"]["enabled"] is True
        assert config["loops"]["run_defaults"] == {"clear": False}
