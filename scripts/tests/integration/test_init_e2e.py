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
        # schema-sourced (ENH-2434): config-schema.json declares clear=true and
        # show_diagrams="clean" for a fresh install so ll-loop run defaults to
        # the pinned-diagram display in target projects.
        assert config["loops"]["run_defaults"]["clear"] is True
        assert config["loops"]["run_defaults"]["show_diagrams"] == "clean"
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


class TestInitHeadlessDocumentDetection:
    """detect_documents() wiring into the headless --yes/--plan paths (ENH-2701)."""

    def test_yes_populates_documents_categories_from_detected_docs(self, tmp_path: Path) -> None:
        project = tmp_path / "docs_project"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "architecture.md").write_text("# Architecture\n")
        (project / "roadmap.md").write_text("# Roadmap\n")

        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        categories = config["documents"]["categories"]
        assert "docs/architecture.md" in categories["architecture"]["files"]
        assert "roadmap.md" in categories["product"]["files"]

    def test_yes_leaves_existing_documents_section_untouched(self, tmp_path: Path) -> None:
        project = tmp_path / "docs_reinit"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "architecture.md").write_text("# Architecture\n")

        (project / ".ll").mkdir()
        existing = {
            "documents": {
                "enabled": True,
                "categories": {"custom": {"description": "hand-edited", "files": ["x.md"]}},
            }
        }
        (project / ".ll" / "ll-config.json").write_text(json.dumps(existing))

        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["documents"]["categories"] == {
            "custom": {"description": "hand-edited", "files": ["x.md"]}
        }

    def test_plan_includes_detected_documents_categories(self, tmp_path: Path) -> None:
        import io
        from contextlib import redirect_stdout

        project = tmp_path / "docs_plan"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "architecture.md").write_text("# Architecture\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            assert _run_init(["--plan", "--root", str(project)]) == 0
        plan = json.loads(buf.getvalue())
        categories = plan["proposed_config"]["documents"]["categories"]
        assert "docs/architecture.md" in categories["architecture"]["files"]


class TestInitHeadlessIntrospection:
    """introspect() wiring into the headless --yes/--plan paths (FEAT-2703)."""

    def test_yes_derives_src_dir_and_commands_from_declared_manifest(self, tmp_path: Path) -> None:
        project = tmp_path / "declared_project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[tool.ruff]\n\n[tool.mypy]\n")
        pkg = project / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()

        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["project"]["src_dir"] == "mypkg/"
        assert config["project"]["lint_cmd"] == "ruff check ."
        assert config["project"]["type_cmd"] == "mypy"

    def test_yes_prints_provenance_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = tmp_path / "printed_summary_project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[tool.ruff]\n\n[tool.mypy]\n")

        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        out = capsys.readouterr().out
        assert "lint_cmd: ruff check .  (declared: [tool.ruff] present)" in out
        assert "type_cmd: mypy  (declared: [tool.mypy] present)" in out

    def test_yes_derives_node_test_cmd_from_package_json(self, tmp_path: Path) -> None:
        project = tmp_path / "node_project"
        project.mkdir()
        (project / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))

        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["project"]["test_cmd"] == "npm run test"

    def test_yes_preserves_existing_config_commands_on_reinit(self, tmp_path: Path) -> None:
        """Existing-config values win over introspection, matching src_dir precedent."""
        project = tmp_path / "reinit_project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[tool.ruff]\n\n[tool.mypy]\n")

        (project / ".ll").mkdir()
        existing = {
            "project": {
                "src_dir": "custom_src/",
                "test_cmd": "custom test command",
                "lint_cmd": "custom lint command",
                "format_cmd": "custom format command",
                "type_cmd": "custom type command",
            },
            "scan": {"focus_dirs": ["custom_src/"]},
        }
        (project / ".ll" / "ll-config.json").write_text(json.dumps(existing))

        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(project)]) == 0

        config = json.loads((project / ".ll" / "ll-config.json").read_text())
        assert config["project"]["src_dir"] == "custom_src/"
        assert config["project"]["test_cmd"] == "custom test command"
        assert config["project"]["lint_cmd"] == "custom lint command"
        assert config["project"]["format_cmd"] == "custom format command"
        assert config["project"]["type_cmd"] == "custom type command"
        assert config["scan"]["focus_dirs"] == ["custom_src/"]

    def test_plan_includes_provenance_and_ambiguities(self, tmp_path: Path) -> None:
        import io
        from contextlib import redirect_stdout

        project = tmp_path / "provenance_plan"
        project.mkdir()
        (project / "pyproject.toml").write_text("[tool.ruff]\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            assert _run_init(["--plan", "--root", str(project)]) == 0
        plan = json.loads(buf.getvalue())
        assert "provenance" in plan
        assert "ambiguities" in plan
        fields = {p["field"] for p in plan["provenance"]}
        assert "project.lint_cmd" in fields


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

    def test_plan_output_has_no_logo_and_stays_valid_json(self, tmp_path: Path) -> None:
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
