"""End-to-end test: ``ll-init`` headless dry-run then apply (finding H2).

Drives the real ``main_init`` entry point against a temp directory with the
real bundled templates. The only mocked boundary is ``detect_installation``
(the pip/plugin probe), held to a clean no-install result so the run is
hermetic and does not branch into version-drift handling for the editable
dev install.

This is the first end-to-end coverage that runs init for real and asserts on
the *generated* config and filesystem — previously init was only exercised by
unit tests around individual writers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


# Patch target: detect_installation is imported function-locally inside
# _run_yes (init/cli.py), so patching it at its definition site takes effect.
_NO_INSTALL = ("little_loops.init.install_check.detect_installation",)


def _run_init(argv: list[str]) -> int:
    """Invoke main_init with a clean no-install probe."""
    from little_loops.init.cli import main_init

    with patch(_NO_INSTALL[0], return_value=(None, None, None)):
        return main_init(argv)


class TestInitHeadlessEndToEnd:
    def test_dry_run_writes_nothing_then_apply_generates_config(self, tmp_path: Path) -> None:
        """--dry-run previews without touching disk; a real apply then writes config + dirs."""
        project = tmp_path / "demo_project"
        project.mkdir()

        # --- Dry-run: must exit 0 and write NOTHING ---
        dry_code = _run_init(["--yes", "--dry-run", "--root", str(project)])
        assert dry_code == 0
        assert not (project / ".ll" / "ll-config.json").exists(), (
            "dry-run must not write the generated config"
        )
        assert not (project / ".issues").exists(), "dry-run must not create the issues tree"

        # --- Apply: must exit 0 and materialize the project ---
        apply_code = _run_init(["--yes", "--root", str(project)])
        assert apply_code == 0

        config_path = project / ".ll" / "ll-config.json"
        assert config_path.exists(), "apply must write .ll/ll-config.json"

        config = json.loads(config_path.read_text())
        # Schema pointer is always emitted.
        assert config["$schema"].endswith("config-schema.json")
        # Project name is derived from the target directory name.
        assert config["project"]["name"] == "demo_project"
        # CLAUDE.md guarantees init "always writes loops.run_defaults" — pin the
        # documented defaults exactly, not just existence (audit M1). Values are
        # schema-sourced (ENH-2434): config-schema.json declares clear=false,
        # show_diagrams=null (omitted after None-stripping) for a fresh install.
        assert config["loops"]["run_defaults"]["clear"] is False
        assert "show_diagrams" not in config["loops"]["run_defaults"]
        # Issues tree is scaffolded with the canonical category dirs.
        assert (project / ".issues" / "bugs").is_dir()
        assert (project / ".issues" / "features").is_dir()
        # Host permissions are merged into the Claude settings.
        assert (project / ".claude" / "settings.local.json").exists()

    def test_generated_config_round_trips_through_brconfig(self, tmp_path: Path) -> None:
        """The config init writes must load back through the real BRConfig parser.

        Guards against init emitting a config that the consumer (BRConfig) cannot
        parse — a class of divergence unit tests around individual writers miss.
        """
        from little_loops.config import BRConfig

        project = tmp_path / "round_trip"
        project.mkdir()

        assert _run_init(["--yes", "--root", str(project)]) == 0

        config = BRConfig(project)
        # Name falls through to the dir name when not overridden.
        assert config.project.name == "round_trip"
        # The issues base dir resolves to the scaffolded tree.
        assert (project / config.issues.base_dir / "bugs").is_dir()

    def test_plan_apply_produces_same_artifacts_as_yes(self, tmp_path: Path) -> None:
        """--plan→apply round-trip produces the same key artifacts as --yes."""
        import io
        from contextlib import redirect_stdout

        yes_root = tmp_path / "yes_project"
        yes_root.mkdir()
        apply_root = tmp_path / "apply_project"
        apply_root.mkdir()

        # Run --yes (no codex adapter; host adapter dispatch is a no-op for claude-code)
        yes_code = _run_init(["--yes", "--hosts", "claude-code", "--root", str(yes_root)])
        assert yes_code == 0

        # Generate plan from a scratch project
        plan_src = tmp_path / "plan_src"
        plan_src.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            plan_code = _run_init(["--plan", "--root", str(plan_src)])
        assert plan_code == 0
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(buf.getvalue())

        # Apply the plan — _run_apply now delegates host dispatch via --hosts
        apply_code = _run_init(
            [
                "--hosts",
                "claude-code",
                "--root",
                str(apply_root),
                "apply",
                "--config",
                str(plan_file),
            ]
        )
        assert apply_code == 0

        # Assert key artifacts exist in both destinations
        for root in (yes_root, apply_root):
            assert (root / ".ll" / "ll-config.json").exists(), f"config missing in {root}"
            assert (root / ".claude" / "CLAUDE.md").exists(), f"CLAUDE.md missing in {root}"
            assert (root / ".claude" / "settings.local.json").exists(), (
                f"settings missing in {root}"
            )
            assert (root / ".issues" / "bugs").is_dir(), f"bugs dir missing in {root}"


class TestInitLogoBanner:
    """The CLI logo banner prints on human-facing runs but never pollutes the
    machine-readable --plan JSON output."""

    def test_yes_run_prints_logo_banner_on_tty(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = tmp_path / "banner_yes"
        project.mkdir()

        # Force the interactive-terminal branch; capsys's capture reports
        # isatty() False by default.
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        out = capsys.readouterr().out
        assert "little loops" in out, "logo banner missing from --yes stdout on a TTY"

    def test_yes_run_omits_logo_when_not_tty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = tmp_path / "banner_yes_piped"
        project.mkdir()

        # capsys capture is not a TTY, so the guard suppresses the banner.
        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        out = capsys.readouterr().out
        assert "little loops" not in out, "logo banner leaked into non-TTY (piped) output"

    def test_plan_output_has_no_logo_and_stays_valid_json(
        self, tmp_path: Path
    ) -> None:
        import io
        from contextlib import redirect_stdout

        project = tmp_path / "banner_plan"
        project.mkdir()

        buf = io.StringIO()
        with redirect_stdout(buf):
            assert _run_init(["--plan", "--root", str(project)]) == 0

        stdout = buf.getvalue()
        assert "little loops" not in stdout, "logo leaked into --plan output"
        # stdout must remain parseable JSON (no banner prefix/suffix).
        json.loads(stdout)
