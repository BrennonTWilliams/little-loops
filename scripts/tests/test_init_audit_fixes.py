"""Tests for the 2026-08-05 ll-init audit fixes (thoughts/ll-init-audit-2026-08-05.md).

Covers the High defects (H-1..H-4), the wiring gaps (M-1..M-8), the widened
--force semantics (M-4), the shared output layer (U-1/U-3/U-4), and the
schema-coverage guard (recommendation 17).
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.init.install_check import InstallStatus, check_version
from little_loops.issue_template import get_bundled_templates_dir

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # little-loops root
_TEMPLATES_DIR = get_bundled_templates_dir()

_NO_INSTALL = ("little_loops.init.install_check.detect_installation", (None, None, None))

if sys.platform == "win32":
    pytest.skip("little-loops requires macOS/Linux", allow_module_level=True)


def _run(argv: list[str]) -> int:
    from little_loops.init.cli import main_init

    with (
        patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
        patch(_NO_INSTALL[0], return_value=_NO_INSTALL[1]),
        # FEAT-3372: `claude` is on PATH in dev environments — stub plugin
        # presence so claude-code-hosted runs through this helper don't hit
        # the real marketplace-add/install subprocess calls.
        patch("little_loops.init.install_check.plugin_installed", return_value=True),
    ):
        return main_init(argv)


def _plan_for(project: Path) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert _run(["--plan", "--root", str(project)]) == 0
    return json.loads(buf.getvalue())


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


# ===========================================================================
# H-1: --force must survive the apply subparser (both flag positions)
# ===========================================================================


class TestForceFlagPositions:
    def _seed(self, tmp_path: Path) -> tuple[Path, Path]:
        """Plan source + apply destination carrying an unmodeled section."""
        src = tmp_path / "src"
        src.mkdir()
        plan = _plan_for(src)
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        dest = tmp_path / "dest"
        (dest / ".ll").mkdir(parents=True)
        (dest / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"name": "dest"}, "my_custom_section": {"k": 1}})
        )
        return dest, plan_file

    def test_force_before_apply_subcommand(self, tmp_path: Path) -> None:
        """`ll-init --force apply` previously downgraded to a merge: the apply
        subparser's own --force default shadowed the parent's parsed True."""
        dest, plan_file = self._seed(tmp_path)
        code = _run(
            [
                "--force",
                "--hosts",
                "claude-code",
                "--root",
                str(dest),
                "apply",
                "--config",
                str(plan_file),
            ]
        )
        assert code == 0
        result = json.loads((dest / ".ll" / "ll-config.json").read_text())
        assert "my_custom_section" not in result

    def test_force_after_apply_subcommand(self, tmp_path: Path) -> None:
        """The subparser position must keep working (pre-existing contract)."""
        dest, plan_file = self._seed(tmp_path)
        code = _run(
            [
                "--hosts",
                "claude-code",
                "--root",
                str(dest),
                "apply",
                "--config",
                str(plan_file),
                "--force",
            ]
        )
        assert code == 0
        result = json.loads((dest / ".ll" / "ll-config.json").read_text())
        assert "my_custom_section" not in result

    def test_apply_without_force_merges(self, tmp_path: Path) -> None:
        dest, plan_file = self._seed(tmp_path)
        code = _run(
            ["--hosts", "claude-code", "--root", str(dest), "apply", "--config", str(plan_file)]
        )
        assert code == 0
        result = json.loads((dest / ".ll" / "ll-config.json").read_text())
        assert result["my_custom_section"] == {"k": 1}


# ===========================================================================
# H-2: --hosts must not swallow the apply subcommand
# ===========================================================================


class TestHostsDoNotSwallowApply:
    def test_hosts_then_apply_parses(self, tmp_path: Path) -> None:
        """With nargs='+', `apply` was absorbed as a host name and argparse
        died on "too few arguments"; action='append' leaves it a subcommand."""
        src = tmp_path / "src"
        src.mkdir()
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(_plan_for(src)))
        dest = tmp_path / "dest"
        dest.mkdir()

        code = _run(
            ["--hosts", "claude-code", "--root", str(dest), "apply", "--config", str(plan_file)]
        )
        assert code == 0
        assert (dest / ".ll" / "ll-config.json").exists()

    def test_hosts_repeatable_and_comma_split(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(_plan_for(src)))
        dest = tmp_path / "dest"
        dest.mkdir()

        # claude-code,codex → comma split; pi → second --hosts occurrence.
        code = _run(
            [
                "--hosts",
                "claude-code,codex",
                "--hosts",
                "pi",
                "--root",
                str(dest),
                "apply",
                "--config",
                str(plan_file),
            ]
        )
        assert code == 0
        # codex selection produced its adapter; pi degrades gracefully.
        assert (dest / ".codex" / "hooks.json").exists()


# ===========================================================================
# H-3: check_version must tolerate real-world version strings
# ===========================================================================


class TestCheckVersionHardened:
    def test_prerelease_suffix_no_crash(self) -> None:
        # Previously raised ValueError on int("0rc1").
        assert check_version("1.2.0rc1", "1.2.0") == InstallStatus.OutOfDate

    def test_dev_suffix_no_crash(self) -> None:
        assert check_version("1.2.0.dev0", "1.2.0") == InstallStatus.OutOfDate

    def test_uneven_lengths_equal(self) -> None:
        # Previously reported OutOfDate because (1,2) < (1,2,0).
        assert check_version("1.2", "1.2.0") == InstallStatus.UpToDate
        assert check_version("1.2.0", "1.2") == InstallStatus.UpToDate

    def test_numeric_ordering_still_correct(self) -> None:
        assert check_version("1.10.0", "1.9.0") == InstallStatus.UpToDate
        assert check_version("1.1.9", "1.2.0") == InstallStatus.OutOfDate

    def test_build_metadata_ignored(self) -> None:
        assert check_version("1.2.0+local", "1.2.0") == InstallStatus.UpToDate

    def test_calendar_versions(self) -> None:
        assert check_version("2024.10", "2024.9") == InstallStatus.UpToDate

    def test_main_init_returns_1_not_traceback_on_value_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Defense in depth: even if a comparison raises ValueError, the CLI
        exits 1 instead of dumping a stack trace (widened except clause)."""
        project = tmp_path / "proj"
        project.mkdir()
        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=("pypi", "1.2.0rc1", None),
            ),
            patch("little_loops.init.install_check.fetch_latest_pypi", return_value="1.2.0"),
            patch(
                "little_loops.init.install_check.check_version",
                side_effect=ValueError("boom"),
            ),
        ):
            from little_loops.init.cli import main_init

            code = main_init(["--yes", "--hosts", "claude-code", "--root", str(project)])
        assert code == 1
        assert "Error" in capsys.readouterr().err


# ===========================================================================
# H-4: TUI workers sentinel is schema-derived (covered in test_init_tui.py)
# M-1: headless can now express every section the TUI writes
# ===========================================================================


class TestHeadlessTuiConfigEquivalence:
    """--enable parity: build_config covers the five sections that only the
    TUI used to write, so headless and wizard configs are equivalent."""

    def _template(self, tmp_path: Path):
        from little_loops.init.detect import detect_project_type_all

        project = tmp_path / "proj"
        project.mkdir()
        return detect_project_type_all(project, _TEMPLATES_DIR)[0]

    def test_build_config_models_tui_only_sections(self, tmp_path: Path) -> None:
        from little_loops.init.core import build_config, schema_default

        template = self._template(tmp_path)
        config = build_config(
            template,
            {
                "parallel_enabled": True,
                "documents_enabled": True,
                "design_tokens_enabled": True,
                "sync_enabled": True,
                "confidence_gate_enabled": True,
                "tdd_enabled": True,
            },
        )

        # parallel carries the template stamp (ARCHITECTURE-096)
        assert config["parallel"]["use_feature_branches"] is False
        assert config["parallel"]["epic_branches"] == {"enabled": False}
        assert config["documents"] == {"enabled": True}
        assert config["design_tokens"] == {
            "enabled": True,
            "active": schema_default("design_tokens.active"),
        }
        assert config["sync"] == {"enabled": True}
        gate = config["commands"]["confidence_gate"]
        assert gate["enabled"] is True
        assert gate["readiness_threshold"] == schema_default(
            "commands.confidence_gate.readiness_threshold"
        )
        assert gate["outcome_threshold"] == schema_default(
            "commands.confidence_gate.outcome_threshold"
        )
        assert config["commands"]["tdd_mode"] is True

    def test_tui_and_headless_produce_equivalent_sections(self, tmp_path: Path) -> None:
        from little_loops.init.core import build_config
        from little_loops.init.tui import _build_final_config

        template = self._template(tmp_path)
        headless = build_config(
            template,
            {
                "project_name": "proj",
                "parallel_enabled": True,
                "documents_enabled": True,
                "design_tokens_enabled": True,
                "sync_enabled": True,
                "confidence_gate_enabled": True,
                "tdd_enabled": True,
            },
        )
        tui = _build_final_config(
            template=template,
            name="proj",
            src_dir="src/",
            test_cmd="pytest",
            lint_cmd="",
            type_cmd="",
            format_cmd="",
            selected_set={
                "parallel",
                "documents",
                "design_tokens",
                "github_sync",
                "confidence_gate",
                "tdd",
            },
            parallel_workers=2,  # schema default → omitted, like headless
            documents_categories=None,
        )

        # parallel: headless carries the template stamp (ARCHITECTURE-096);
        # the TUI omits sub-keys sitting at schema default, so with
        # all-default answers it omits the section entirely. Both shapes are
        # runtime-equivalent — every effective value is a schema default.
        assert headless["parallel"] == {
            "use_feature_branches": False,
            "epic_branches": {"enabled": False},
        }
        if "parallel" in tui:
            assert tui["parallel"].get("use_feature_branches", False) is False
            assert tui["parallel"].get("epic_branches", {"enabled": False}) == {"enabled": False}
        assert headless["sync"] == tui["sync"] == {"enabled": True}
        assert headless["design_tokens"]["enabled"] == tui["design_tokens"]["enabled"] is True
        assert headless["documents"]["enabled"] == tui["documents"]["enabled"] is True
        assert headless["commands"]["confidence_gate"] == tui["commands"]["confidence_gate"]
        assert headless["commands"]["tdd_mode"] == tui["commands"]["tdd_mode"] is True

    def test_documents_toggle_suppresses_detection(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "architecture.md").write_text("# Arch\n")

        assert (
            _run(
                [
                    "--yes",
                    "--disable",
                    "documents",
                    "--hosts",
                    "claude-code",
                    "--root",
                    str(project),
                ]
            )
            == 0
        )
        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert "documents" not in config

    def test_enable_writes_schema_default_shapes(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert (
            _run(
                [
                    "--yes",
                    "--enable",
                    "parallel",
                    "--enable",
                    "sync",
                    "--enable",
                    "design_tokens",
                    "--hosts",
                    "claude-code",
                    "--root",
                    str(project),
                ]
            )
            == 0
        )
        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["sync"] == {"enabled": True}
        assert config["design_tokens"]["enabled"] is True
        assert "parallel" in config


# ===========================================================================
# M-5: --enable X --disable X is a usage error
# ===========================================================================


class TestEnableDisableConflict:
    def test_conflict_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        code = _run(["--yes", "--enable", "tdd", "--disable", "tdd", "--root", str(project)])
        assert code == 2
        err = capsys.readouterr().err
        assert "Conflicting" in err and "tdd" in err
        assert not (project / ".ll" / "ll-config.json").exists()


# ===========================================================================
# M-6: --plan runs the same merge preview apply performs
# ===========================================================================


class TestPlanMergeParity:
    def test_plan_reflects_merge_with_existing_config(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        (project / ".ll").mkdir(parents=True)
        (project / ".ll" / "ll-config.json").write_text(json.dumps({"my_custom_section": {"k": 1}}))
        plan = _plan_for(project)
        assert plan["proposed_config"]["my_custom_section"] == {"k": 1}

    def test_plan_force_skips_merge_preview(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        (project / ".ll").mkdir(parents=True)
        (project / ".ll" / "ll-config.json").write_text(json.dumps({"my_custom_section": {"k": 1}}))
        buf = io.StringIO()
        with redirect_stdout(buf):
            assert _run(["--force", "--plan", "--root", str(project)]) == 0
        plan = json.loads(buf.getvalue())
        assert "my_custom_section" not in plan["proposed_config"]

    def test_plan_does_not_clobber_existing_documents(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "architecture.md").write_text("# Arch\n")
        (project / ".ll").mkdir()
        existing_docs = {"enabled": True, "categories": {"product": {"files": ["p.md"]}}}
        (project / ".ll" / "ll-config.json").write_text(json.dumps({"documents": existing_docs}))
        plan = _plan_for(project)
        # Detected architecture docs must NOT replace the existing section.
        assert plan["proposed_config"]["documents"] == existing_docs

    def test_plan_url_a_overrides_url_b_in_existing_config(self, tmp_path: Path) -> None:
        """URL A (SCHEMA_URL) wins on merge when the existing config has URL B.

        Regression guard for ENH-206 Gap 4: if `build_config` (init/core.py:158,161)
        ever drops the $schema key, this assertion fails; if `deep_merge` ever
        changes string-replacement semantics, this also fails. Behavior is
        already correct today — see ENH-206 ## Codebase Research Findings.
        """
        from little_loops.init.core import SCHEMA_URL

        URL_B = "https://example.invalid/old-config-schema.json"
        project = tmp_path / "proj"
        (project / ".ll").mkdir(parents=True)
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps({"$schema": URL_B, "my_custom_section": {"k": 1}})
        )
        plan = _plan_for(project)
        assert plan["proposed_config"]["$schema"] == SCHEMA_URL
        # Hand-edited unmodeled section must still survive the merge.
        assert plan["proposed_config"]["my_custom_section"] == {"k": 1}


# ===========================================================================
# M-7: apply --dry-run + requested_upgrade honored
# ===========================================================================


class TestApplyDryRunAndUpgrade:
    def test_apply_dry_run_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(_plan_for(src)))
        dest = tmp_path / "dest"
        dest.mkdir()

        code = _run(
            [
                "--hosts",
                "claude-code",
                "--root",
                str(dest),
                "apply",
                "--config",
                str(plan_file),
                "--dry-run",
            ]
        )
        assert code == 0
        assert not (dest / ".ll" / "ll-config.json").exists()
        assert not (dest / ".gitignore").exists()
        out = capsys.readouterr().out
        assert "Dry run complete" in out

    def test_apply_honors_requested_upgrade(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan = _plan_for(src)
        plan["requested_upgrade"] = True
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))
        dest = tmp_path / "dest"
        dest.mkdir()

        with patch("little_loops.init.cli._dispatch_host_upgrade") as upgrade_mock:
            code = _run(
                ["--hosts", "claude-code", "--root", str(dest), "apply", "--config", str(plan_file)]
            )
        assert code == 0
        upgrade_mock.assert_called_once()

    def test_apply_ignores_requested_upgrade_in_dry_run(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan = _plan_for(src)
        plan["requested_upgrade"] = True
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))
        dest = tmp_path / "dest"
        dest.mkdir()

        with patch("little_loops.init.cli._dispatch_host_upgrade") as upgrade_mock:
            code = _run(
                [
                    "--hosts",
                    "claude-code",
                    "--root",
                    str(dest),
                    "apply",
                    "--config",
                    str(plan_file),
                    "--dry-run",
                ]
            )
        assert code == 0
        upgrade_mock.assert_not_called()

    def test_apply_requested_upgrade_refreshes_stale_commands_block(self, tmp_path: Path) -> None:
        """ENH-3382: requested_upgrade splices a stale block, mirroring --yes --upgrade."""
        src = tmp_path / "src"
        src.mkdir()
        plan = _plan_for(src)
        plan["requested_upgrade"] = True
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))
        dest = tmp_path / "dest"
        dest.mkdir()
        claude_md = dest / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text(
            "# Config\n"
            "\n"
            "## little-loops CLI Commands\n"
            "\n"
            'Install: `pip install -e "./scripts[dev]"`\n',
            encoding="utf-8",
        )

        with patch("little_loops.init.cli._dispatch_host_upgrade"):
            code = _run(
                ["--hosts", "claude-code", "--root", str(dest), "apply", "--config", str(plan_file)]
            )
        assert code == 0
        content = claude_md.read_text(encoding="utf-8")
        assert 'Install: `pip install -e "./scripts[dev]"`' not in content

    def test_apply_without_requested_upgrade_leaves_stale_commands_block(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(_plan_for(src)))
        dest = tmp_path / "dest"
        dest.mkdir()
        claude_md = dest / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        stale = (
            "# Config\n"
            "\n"
            "## little-loops CLI Commands\n"
            "\n"
            'Install: `pip install -e "./scripts[dev]"`\n'
        )
        claude_md.write_text(stale, encoding="utf-8")

        code = _run(
            ["--hosts", "claude-code", "--root", str(dest), "apply", "--config", str(plan_file)]
        )
        assert code == 0
        assert claude_md.read_text(encoding="utf-8") == stale


# ===========================================================================
# M-8: host_options is complete
# ===========================================================================


class TestHostOptionsComplete:
    def test_all_hosts_and_settings_file_present(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        plan = _plan_for(project)
        opts = plan["host_options"]
        for key in ("has_claude_code", "has_codex", "has_opencode", "has_pi", "has_kimi_code"):
            assert key in opts, f"host_options missing {key}"
        assert opts["suggested_settings_file"] == ".claude/settings.local.json"
        # additive keys (2026-09 audit): full availability map + resolved default list
        from little_loops.init.cli import _KNOWN_HOSTS

        assert set(opts["available"]) == set(_KNOWN_HOSTS)
        assert opts["default"] and opts["primary"] == opts["default"][0]


class TestHeadlessSettingsFlags:
    def test_settings_skip_writes_no_claude_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert (
            _run(["--yes", "--settings", "skip", "--hosts", "claude-code", "--root", str(project)])
            == 0
        )
        assert not (project / ".claude" / "settings.local.json").exists()
        assert not (project / ".claude" / "settings.json").exists()
        assert (project / ".claude" / "CLAUDE.md").exists()  # CLAUDE.md is separate

    def test_no_settings_alias(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert (
            _run(["--yes", "--no-settings", "--hosts", "claude-code", "--root", str(project)]) == 0
        )
        assert not (project / ".claude" / "settings.local.json").exists()

    def test_settings_shared(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert (
            _run(
                ["--yes", "--settings", "shared", "--hosts", "claude-code", "--root", str(project)]
            )
            == 0
        )
        assert (project / ".claude" / "settings.json").exists()
        assert not (project / ".claude" / "settings.local.json").exists()

    def test_no_claude_md(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert (
            _run(["--yes", "--no-claude-md", "--hosts", "claude-code", "--root", str(project)]) == 0
        )
        assert not (project / ".claude" / "CLAUDE.md").exists()
        assert (project / ".claude" / "settings.local.json").exists()

    def test_codex_only_writes_no_claude_surfaces(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--hosts", "codex", "--root", str(project)]) == 0
        assert not (project / ".claude").exists()
        assert (project / "AGENTS.md").exists()
        assert (project / ".codex" / "hooks.json").exists()

    def test_apply_honors_settings_flags(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(_plan_for(src)))
        dest = tmp_path / "dest"
        dest.mkdir()
        assert (
            _run(
                [
                    "--hosts",
                    "claude-code",
                    "--no-settings",
                    "--no-claude-md",
                    "--root",
                    str(dest),
                    "apply",
                    "--config",
                    str(plan_file),
                ]
            )
            == 0
        )
        assert not (dest / ".claude").exists()


# ===========================================================================
# M-4: --force redeploys bundled artifacts
# ===========================================================================


class TestForceRedeploysArtifacts:
    def test_force_restores_corrupted_goals_file(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        # Goals deploy is gated on product.enabled (schema default false in
        # headless), so enable it explicitly.
        assert (
            _run(["--yes", "--enable", "product", "--hosts", "claude-code", "--root", str(project)])
            == 0
        )

        goals = project / ".ll" / "ll-goals.md"
        assert goals.exists()
        bundled = (_TEMPLATES_DIR / "ll-goals-template.md").read_text(encoding="utf-8")
        goals.write_text("corrupted by the user", encoding="utf-8")

        # Plain re-init merges and skips the existing file…
        assert (
            _run(["--yes", "--enable", "product", "--hosts", "claude-code", "--root", str(project)])
            == 0
        )
        assert goals.read_text(encoding="utf-8") == "corrupted by the user"

        # …--force restores it from the bundled template.
        assert (
            _run(
                [
                    "--yes",
                    "--force",
                    "--enable",
                    "product",
                    "--hosts",
                    "claude-code",
                    "--root",
                    str(project),
                ]
            )
            == 0
        )
        assert goals.read_text(encoding="utf-8") == bundled

    def test_force_overwrites_design_tokens(self, tmp_path: Path) -> None:
        from little_loops.init.writers import deploy_design_tokens

        ll_dir = tmp_path / ".ll"
        dest = ll_dir / "design-tokens" / "profiles"
        dest.mkdir(parents=True)
        (dest / "primitives.json").write_text("{}")
        assert deploy_design_tokens(ll_dir, _TEMPLATES_DIR, force=True) is True
        # Bundled profile files are present after the forced redeploy.
        assert any(dest.rglob("primitives.json"))


# ===========================================================================
# rec-13: explicit host selection persists into the config
# ===========================================================================


class TestHostSelectionPersisted:
    def test_explicit_hosts_persist(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--hosts", "codex", "--root", str(project)]) == 0
        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["orchestration"]["host_cli"] == "codex"
        # codex is inside hooks.host's enum.
        assert config["hooks"]["host"] == "codex"

    def test_auto_detected_hosts_persisted(self, tmp_path: Path) -> None:
        """Auto-detected hosts persist too, so resolve_host() later agrees with
        the adapters that were written (2026-09 audit, finding C)."""
        project = tmp_path / "proj"
        project.mkdir()
        with patch("little_loops.init.cli.default_hosts", return_value=["claude-code", "codex"]):
            assert _run(["--yes", "--root", str(project)]) == 0
        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["orchestration"]["host_cli"] == "claude-code"
        assert config["hooks"]["host"] == "claude-code"

    def test_existing_host_cli_stays_primary_on_reinit(self, tmp_path: Path) -> None:
        from little_loops.init.cli import default_hosts

        with patch(
            "little_loops.init.cli.shutil.which",
            side_effect=lambda b: b if b in ("claude", "codex") else None,
        ):
            hosts = default_hosts(tmp_path, {"orchestration": {"host_cli": "codex"}})
        assert hosts[0] == "codex"
        assert "claude-code" in hosts

    def test_host_outside_hooks_enum_skipped(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--hosts", "pi", "--root", str(project)]) == 0
        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["orchestration"]["host_cli"] == "pi"
        assert "hooks" not in config  # pi is not in hooks.host's enum


# ===========================================================================
# U-1/U-3/U-4: output layer, next steps, completion strings
# ===========================================================================


class TestOutputLayer:
    @pytest.fixture(autouse=True)
    def _reset_output_state(self):
        from little_loops.cli import output as output_mod

        yield
        output_mod.configure_output()

    def test_yes_completion_and_next_steps(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        assert "little-loops initialized" in out
        assert "Next steps:" in out
        assert "/ll:scan-codebase" in out
        assert "scan the codebase and file" in out  # no longer claims to "index"
        assert "ll-doctor" in out
        assert "/ll:capture-issue" in out
        assert "codegraph init" in out  # no index on this (patched) machine
        assert "git init" in out  # tmp project is not a repo

    def test_adapter_hosts_no_longer_get_manual_mirror_hint(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """ENH-3389: gemini/kimi-code/qwen mirror automatically; codex still needs
        the manual `ll-adapt --host codex --apply` next-steps hint."""
        project = tmp_path / "proj"
        project.mkdir()
        with patch.dict("os.environ", {"KIMI_CODE_HOME": str(tmp_path / "kimi-home")}):
            assert (
                _run(
                    [
                        "--yes",
                        "--hosts",
                        "codex,gemini,kimi-code,qwen",
                        "--root",
                        str(project),
                    ]
                )
                == 0
            )
        out = capsys.readouterr().out
        assert "mirror skills/commands for Codex CLI" in out
        assert "mirror skills/commands for Gemini CLI" not in out
        assert "mirror skills/commands for Kimi Code" not in out
        assert "mirror skills/commands for Qwen Code" not in out

    def test_dry_run_paths_are_relative(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--dry-run", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        write_lines = [
            ln for ln in out.splitlines() if ln.lstrip("ℹ ").startswith(("write ", "mkdir "))
        ]
        assert write_lines, out
        assert all(str(project) not in ln for ln in write_lines), write_lines
        assert any(".ll/ll-config.json" in ln for ln in write_lines)

    def test_dependency_block_reports_success(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        with patch("little_loops.init.validate.validate_deps", return_value=[]):
            assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        assert "Validating dependencies..." in out
        assert "All dependencies found" in out

    def test_apply_completion_string(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(_plan_for(src)))
        dest = tmp_path / "dest"
        dest.mkdir()
        assert (
            _run(
                ["--hosts", "claude-code", "--root", str(dest), "apply", "--config", str(plan_file)]
            )
            == 0
        )
        out = capsys.readouterr().out
        assert "Applied init plan" in out
        assert "Next steps:" in out

    def test_no_color_env_disables_glyphs_and_ansi(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.cli.output import configure_output

        monkeypatch.setenv("NO_COLOR", "1")
        configure_output()
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        assert "\x1b[" not in out
        assert "✓" not in out
        assert "little-loops initialized" in out  # the text survives the gate

    def test_color_flag_forces_ansi_in_pipes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--color", "--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        assert "\x1b[" in out

    def test_color_flags_mutually_exclusive(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        # Mutually exclusive group: argparse rejects both at once.
        from little_loops.init.cli import main_init

        with pytest.raises(SystemExit):
            main_init(["--color", "--no-color", "--yes", "--root", str(project)])

    def test_dry_run_validates_and_closes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--dry-run", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        assert "Validating dependencies..." in out  # validation runs in preview too
        assert "Dry run complete" in out
        assert "write" in out  # planned-write preview lines
        assert "$schema" not in out  # …but no raw config dump


# ===========================================================================
# Re-init idempotency (ll-init audit 2026-09-04, finding B)
# ===========================================================================


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


class TestHeadlessIdempotent:
    """`ll-init --yes` twice must produce byte-identical artifacts."""

    def _init(self, project: Path, *extra: str) -> None:
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project), *extra]) == 0

    def test_yes_twice_produces_identical_artifacts(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "pyproject.toml").write_text("[tool.ruff]\n")
        self._init(project)
        first = {
            name: (project / name).read_text()
            for name in (".ll/ll-config.json", ".claude/settings.local.json", ".gitignore")
        }
        first_goals = (project / ".ll" / "ll-goals.md").exists()
        self._init(project)
        for name, content in first.items():
            assert (project / name).read_text() == content, name
        assert (project / ".ll" / "ll-goals.md").exists() == first_goals

    def test_reinit_does_not_reenable_default_off_features(self, tmp_path: Path) -> None:
        from little_loops.init.core import schema_default

        project = tmp_path / "proj"
        project.mkdir()
        self._init(project)
        self._init(project)
        config = _read_json(project / ".ll" / "ll-config.json")
        assert config.get("product", {}).get("enabled", False) is bool(
            schema_default("product.enabled")
        )
        assert config["learning_tests"]["enabled"] is bool(schema_default("learning_tests.enabled"))

    def test_reinit_preserves_explicitly_enabled_features(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        self._init(project, "--enable", "product", "--enable", "learning_tests")
        self._init(project)
        config = _read_json(project / ".ll" / "ll-config.json")
        assert config["product"]["enabled"] is True
        assert config["learning_tests"]["enabled"] is True

    def test_reinit_preserves_subconfig_values(self, tmp_path: Path) -> None:
        """Enabled sub-config sections are not rebuilt from schema defaults."""
        project = tmp_path / "proj"
        project.mkdir()
        (project / ".ll").mkdir()
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps(
                {
                    "commands": {"confidence_gate": {"enabled": True, "readiness_threshold": 91}},
                    "design_tokens": {"enabled": True, "active": "warm-paper"},
                    "parallel": {"max_workers": 3, "use_feature_branches": True},
                }
            )
        )
        self._init(project)
        config = _read_json(project / ".ll" / "ll-config.json")
        assert config["commands"]["confidence_gate"]["readiness_threshold"] == 91
        assert config["design_tokens"]["active"] == "warm-paper"
        assert config["parallel"] == {"max_workers": 3, "use_feature_branches": True}


# ===========================================================================
# Robustness (audit finding F)
# ===========================================================================


class TestRobustness:
    def test_keyerror_from_schema_default_is_friendly(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        with patch(
            "little_loops.init.core.schema_default",
            side_effect=KeyError("config-schema.json has no property at 'x'"),
        ):
            rc = _run(["--yes", "--hosts", "claude-code", "--root", str(project)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "Error:" in err and "schema" in err
        assert "Traceback" not in err

    def test_apply_stamps_install_source(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(_plan_for(src)))
        dest = tmp_path / "dest"
        dest.mkdir()
        from little_loops.init.cli import main_init

        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=("pypi", "1.0.0", None),
            ),
            patch("little_loops.init.install_check.plugin_installed", return_value=True),
        ):
            rc = main_init(
                ["--hosts", "claude-code", "--root", str(dest), "apply", "--config", str(plan_file)]
            )
        assert rc == 0
        assert _read_json(dest / ".ll" / "ll-config.json")["install_source"] == "pypi"

    def test_ll_state_dir_redirects_writes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.setenv("LL_STATE_DIR", ".codex")
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        assert (project / ".codex" / "ll-config.json").exists()
        assert not (project / ".ll" / "ll-config.json").exists()

    def test_help_documents_exit_130(self, capsys: pytest.CaptureFixture) -> None:
        from little_loops.init.cli import main_init

        with pytest.raises(SystemExit):
            main_init(["--help"])
        assert "130" in capsys.readouterr().out


# ===========================================================================
# Code graph step (2026-09 audit, finding D)
# ===========================================================================


class TestCodeGraphHeadless:
    def _index(self, project: Path) -> None:
        (project / ".codegraph").mkdir()
        (project / ".codegraph" / "codegraph.db").write_bytes(b"")

    def test_skip_writes_no_section(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert (
            _run(
                ["--yes", "--code-graph", "skip", "--hosts", "claude-code", "--root", str(project)]
            )
            == 0
        )
        assert "code_query" not in _read_json(project / ".ll" / "ll-config.json")

    def test_commands_mode_prints_commands(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert (
            _run(
                [
                    "--yes",
                    "--code-graph",
                    "commands",
                    "--hosts",
                    "claude-code",
                    "--root",
                    str(project),
                ]
            )
            == 0
        )
        out = capsys.readouterr().out
        assert "npm install -g @colbymchenry/codegraph" in out
        assert "codegraph init ." in out
        assert "code_query" not in _read_json(project / ".ll" / "ll-config.json")

    def test_existing_index_writes_code_query(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        self._index(project)
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        config = _read_json(project / ".ll" / "ll-config.json")
        assert config["code_query"] == {"provider": "auto"}

    def test_existing_index_summary_and_next_steps(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        self._index(project)
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        assert "indexed (.codegraph/)" in out
        assert "ll-code status" in out
        assert "codegraph init" not in out

    def test_plan_includes_code_graph(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        plan = _plan_for(project)
        assert plan["code_graph"]["index_present"] is False
        assert plan["code_graph"]["recommended_action"] == "commands"
        assert "codegraph init ." in plan["code_graph"]["manual_commands"]
        self._index(project)
        plan = _plan_for(project)
        assert plan["code_graph"]["index_present"] is True
        assert plan["proposed_config"]["code_query"] == {"provider": "auto"}

    def test_gitignore_covers_codegraph(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        assert ".codegraph/" in (project / ".gitignore").read_text().splitlines()

    def test_claude_md_lists_ll_code(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        assert "`ll-code`" in (project / ".claude" / "CLAUDE.md").read_text()

    def test_index_mode_runs_and_writes_section(self, tmp_path: Path) -> None:
        """With the binary present, --code-graph index runs codegraph init and enables code_query."""
        from little_loops.init.codegraph import CodegraphActionResult, CodegraphStatus

        project = tmp_path / "proj"
        project.mkdir()
        db = project / ".codegraph" / "codegraph.db"

        def _detect(root: Path, db_path: str | None = None) -> CodegraphStatus:
            return CodegraphStatus("/usr/bin/codegraph", db.is_file(), db, None, None, None)

        def _index(root: Path, status: CodegraphStatus, *, dry_run: bool = False, timeout: int = 0):
            db.parent.mkdir(exist_ok=True)
            db.write_bytes(b"")
            return CodegraphActionResult(True, "index", "indexed", [["codegraph", "init", "."]])

        with (
            patch("little_loops.init.codegraph.detect_codegraph", _detect),
            patch("little_loops.init.codegraph.index_codegraph", _index),
        ):
            assert (
                _run(
                    [
                        "--yes",
                        "--code-graph",
                        "index",
                        "--hosts",
                        "claude-code",
                        "--root",
                        str(project),
                    ]
                )
                == 0
            )
        assert _read_json(project / ".ll" / "ll-config.json")["code_query"] == {"provider": "auto"}

    def test_index_failure_is_warning_not_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.init.codegraph import CodegraphActionResult, CodegraphStatus

        project = tmp_path / "proj"
        project.mkdir()
        db = project / ".codegraph" / "codegraph.db"
        with (
            patch(
                "little_loops.init.codegraph.detect_codegraph",
                lambda root, db_path=None: CodegraphStatus(
                    "/x/codegraph", False, db, None, None, None
                ),
            ),
            patch(
                "little_loops.init.codegraph.index_codegraph",
                lambda *a, **k: CodegraphActionResult(False, "index", "boom", [["codegraph"]]),
            ),
        ):
            assert _run(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0
        out = capsys.readouterr().out
        assert "indexing failed: boom" in out
        assert "codegraph init ." in out
        assert "code_query" not in _read_json(project / ".ll" / "ll-config.json")

    def test_dry_run_does_not_index(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        from little_loops.init.codegraph import CodegraphStatus

        project = tmp_path / "proj"
        project.mkdir()
        db = project / ".codegraph" / "codegraph.db"
        with (
            patch(
                "little_loops.init.codegraph.detect_codegraph",
                lambda root, db_path=None: CodegraphStatus(
                    "/x/codegraph", False, db, None, None, None
                ),
            ),
            patch("little_loops.init.codegraph._run") as run,
        ):
            assert (
                _run(["--yes", "--dry-run", "--hosts", "claude-code", "--root", str(project)]) == 0
            )
        run.assert_not_called()
        assert "would build the codegraph index: /x/codegraph init ." in capsys.readouterr().out


# ===========================================================================
# rec-17: schema coverage guard
# ===========================================================================


# Sections ll-init writes today: build_config + TUI-only sections +
# post-write keys (install_source) + explicit host persistence (rec-13).
_INIT_WRITTEN_SECTIONS = frozenset(
    {
        "project",
        "issues",
        "scan",
        "product",
        "analytics",
        "context_monitor",
        "learning_tests",
        "decisions",
        "scratch_pad",
        "session_capture",
        "prompt_optimization",
        "history",
        "loops",
        "parallel",
        "documents",
        "design_tokens",
        "sync",
        "commands",
        "install_source",
        "orchestration",
        "hooks",
        # 2026-09 audit: written (provider=auto) once a codegraph index exists
        # or ll-init built one via --code-graph.
        "code_query",
    }
)

# Runtime/tuning sections deliberately never written by init. Adding a new
# schema section must consciously land in one of these two sets (rec-17).
_ALLOWED_UNTOUCHED_SECTIONS = frozenset(
    {
        "advisor",
        "artifacts",
        "automation",
        "cache",
        "cli",
        "compression",
        "continuation",
        "deferred_tools",
        "dependency_mapping",
        "events",
        "extensions",
        # FEAT-1930: hitl.channel defaults to "terminal" — a project only needs
        # this section to opt into a non-default HITL communication adapter,
        # same posture as advisor/tamper_guard.
        "hitl",
        # FEAT-3149: the ll-mcp transport policy's defaults (HTTP denies mutations, stdio
        # allows them) are the correct posture for a fresh project, so init has nothing to
        # write — a project only needs this section to *loosen* the default.
        "mcp",
        "observability",
        "queue",
        # ENH-3142: off by default (enabled: bool = False); a project only needs this
        # section to opt in, same posture as tamper_guard below.
        "prepatch_check",
        "refine_status",
        "skill_budget",
        "sprints",
        "tamper_guard",
    }
)


class TestSchemaCoverageGuard:
    def test_every_schema_section_is_init_modeled_or_consciously_untouched(self) -> None:
        from little_loops.init.core import _load_schema

        _load_schema.cache_clear()
        try:
            sections = set(_load_schema()["properties"].keys())
        finally:
            _load_schema.cache_clear()
        sections.discard("$schema")

        unaccounted = sections - _INIT_WRITTEN_SECTIONS - _ALLOWED_UNTOUCHED_SECTIONS
        assert not unaccounted, (
            f"New schema section(s) {sorted(unaccounted)} have no init coverage: add "
            "them to _INIT_WRITTEN_SECTIONS (with build_config/TUI wiring) or to "
            "_ALLOWED_UNTOUCHED_SECTIONS (with a reason)."
        )
        stale = (_INIT_WRITTEN_SECTIONS | _ALLOWED_UNTOUCHED_SECTIONS) - sections
        assert not stale, f"Coverage sets reference removed schema sections: {sorted(stale)}"
