"""Tests for little_loops.init.proposal — the shared detection + proposal model."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.init.proposal import Proposal, build_proposal
from little_loops.issue_template import get_bundled_templates_dir

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_TEMPLATES_DIR = get_bundled_templates_dir()

# The seven --plan keys skills/init/SKILL.md depends on.
_PLAN_KEYS = {
    "detected",
    "proposed_config",
    "requested_upgrade",
    "host_options",
    "warnings",
    "provenance",
    "ambiguities",
}


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text("[tool.pytest.ini_options]\n[tool.ruff]\n[tool.mypy]\n")
    pkg = project / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    return project


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


class TestBuildProposal:
    def test_introspection_seeds_choices_and_fields(self, python_project: Path) -> None:
        proposal = build_proposal(python_project, _TEMPLATES_DIR)
        assert isinstance(proposal, Proposal)
        assert proposal.choices["test_cmd"] == "pytest"
        assert proposal.choices["src_dir"] == "mypkg/"
        pf = proposal.field_for("project.lint_cmd")
        assert pf is not None and pf.provenance == "declared"
        assert "[tool.ruff]" in pf.evidence
        assert proposal.config["project"]["type_cmd"] == "mypy"

    def test_fresh_project_gets_recommended_features(self, python_project: Path) -> None:
        from little_loops.init.core import RECOMMENDED_FEATURES

        proposal = build_proposal(python_project, _TEMPLATES_DIR)
        for name in RECOMMENDED_FEATURES:
            pf = proposal.field_for(f"feature.{name}")
            assert pf is not None and pf.provenance == "recommended" and pf.value is True
        assert proposal.config.get("context_monitor", {}).get("enabled") is True

    def test_existing_config_wins_over_introspection(self, python_project: Path) -> None:
        (python_project / ".ll").mkdir()
        (python_project / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"test_cmd": "make test", "name": "kept"}})
        )
        proposal = build_proposal(python_project, _TEMPLATES_DIR)
        assert proposal.choices["test_cmd"] == "make test"
        assert proposal.choices["project_name"] == "kept"
        pf = proposal.field_for("project.test_cmd")
        assert pf is not None and pf.provenance == "existing"
        assert proposal.config["project"]["test_cmd"] == "make test"
        # untouched fields still come from introspection
        assert proposal.config["project"]["lint_cmd"] == "ruff check ."

    def test_flags_win_over_existing(self, python_project: Path) -> None:
        (python_project / ".ll").mkdir()
        (python_project / ".ll" / "ll-config.json").write_text(
            json.dumps({"product": {"enabled": True}})
        )
        proposal = build_proposal(
            python_project, _TEMPLATES_DIR, feature_choices={"product_enabled": False}
        )
        pf = proposal.field_for("feature.product")
        assert pf is not None and pf.provenance == "flag" and pf.value is False
        # the existing section survives the merge but is switched off
        assert proposal.config["product"]["enabled"] is False

    def test_force_skips_merge_but_keeps_prepopulation(self, python_project: Path) -> None:
        (python_project / ".ll").mkdir()
        (python_project / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"test_cmd": "make test"}, "custom": {"k": 1}})
        )
        proposal = build_proposal(python_project, _TEMPLATES_DIR, force=True)
        assert proposal.config["project"]["test_cmd"] == "make test"
        assert "custom" not in proposal.config

    def test_documents_detected_unless_existing_section(self, tmp_path: Path) -> None:
        project = tmp_path / "docs"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "architecture.md").write_text("# a\n")
        proposal = build_proposal(project, _TEMPLATES_DIR)
        assert "architecture" in proposal.config["documents"]["categories"]
        assert proposal.field_for("documents.categories") is not None
        (project / ".ll").mkdir()
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps({"documents": {"enabled": True, "categories": {"x": {"files": []}}}})
        )
        proposal = build_proposal(project, _TEMPLATES_DIR)
        assert proposal.config["documents"]["categories"] == {"x": {"files": []}}

    def test_validation_only_when_plugin_version_given(self, python_project: Path) -> None:
        assert build_proposal(python_project, _TEMPLATES_DIR).warnings == []
        with patch(
            "little_loops.init.validate.validate_deps",
            return_value=[
                __import__("little_loops.init.validate", fromlist=["DepWarning"]).DepWarning("x")
            ],
        ):
            proposal = build_proposal(python_project, _TEMPLATES_DIR, plugin_version="1.0")
        assert [w.message for w in proposal.warnings] == ["x"]

    def test_provenance_rows_hide_defaults_by_default(self, python_project: Path) -> None:
        proposal = build_proposal(python_project, _TEMPLATES_DIR)
        labels = {row[0] for row in proposal.provenance_rows()}
        assert {"Test", "Lint", "Type-check", "Source dir"} <= labels
        assert all("default" not in row[2] for row in proposal.provenance_rows())
        assert len(proposal.provenance_rows(include_default=True)) >= len(labels)

    def test_is_git_repo_flag(self, python_project: Path) -> None:
        assert build_proposal(python_project, _TEMPLATES_DIR).is_git_repo is False
        (python_project / ".git").mkdir()
        assert build_proposal(python_project, _TEMPLATES_DIR).is_git_repo is True


class TestPlanContract:
    def test_plan_keys_stable_and_fields_additive(self, python_project: Path) -> None:
        proposal = build_proposal(python_project, _TEMPLATES_DIR, plugin_version="1.0")
        plan = proposal.to_plan_dict(requested_upgrade=True, host_options={"has_claude_code": True})
        assert _PLAN_KEYS <= set(plan)
        assert plan["requested_upgrade"] is True
        assert plan["host_options"] == {"has_claude_code": True}
        assert plan["detected"]["project_type"] == "Python (Generic)"
        keys = {f["key"] for f in plan["fields"]}
        assert "project.test_cmd" in keys and "feature.context_monitor" in keys
        json.dumps(plan)  # serialisable

    def test_cli_plan_matches_yes_config(self, python_project: Path) -> None:
        """--plan's proposed_config is what --yes writes (same pipeline)."""
        from little_loops.init.cli import main_init

        patches = (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            patch(
                "little_loops.init.install_check.detect_installation",
                return_value=(None, None, None),
            ),
            patch("little_loops.init.install_check.plugin_installed", return_value=True),
        )
        buf = io.StringIO()
        with patches[0], patches[1], patches[2], redirect_stdout(buf):
            assert main_init(["--plan", "--root", str(python_project)]) == 0
        plan = json.loads(buf.getvalue())
        with patches[0], patches[1], patches[2]:
            assert (
                main_init(["--yes", "--hosts", "claude-code", "--root", str(python_project)]) == 0
            )
        written = json.loads((python_project / ".ll" / "ll-config.json").read_text())
        for key in ("project", "scan", "learning_tests", "context_monitor", "loops"):
            assert written[key] == plan["proposed_config"][key], key

    def test_plan_layers_existing_config_like_yes(self, python_project: Path) -> None:
        """A --plan over an existing config proposes the stored command, not the introspected one."""
        (python_project / ".ll").mkdir()
        (python_project / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"test_cmd": "make test"}})
        )
        from little_loops.init.cli import main_init

        buf = io.StringIO()
        with (
            patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT),
            redirect_stdout(buf),
        ):
            assert main_init(["--plan", "--root", str(python_project)]) == 0
        plan = json.loads(buf.getvalue())
        assert plan["proposed_config"]["project"]["test_cmd"] == "make test"
