"""Behavioral fixtures for the `/ll:init` skill's plan -> inspect -> apply flow (FEAT-2705).

`/ll:init`'s Inspect step is Claude reading repo files to settle ambiguous or
unverified `ll-init --plan` values — there is no automated check of Claude's
own reasoning here (a markdown skill, not a Python module). What *is*
deterministic and pytest-checkable is the CLI seam the skill drives:

- the unambiguous-plan fixture below proves a fully-declared repo needs no
  settlement at all (Inspect is a no-op; `apply` on the unedited plan matches
  `--yes`) — this is the fast path the skill's Process step 3 short-circuits.
- the ambiguous fixture proves `--plan` actually surfaces the ambiguity/gap
  (`src_dir` candidates, `test_cmd` staying at `default` despite a Makefile
  test target) that the skill's Inspect step is responsible for resolving.

To exercise the live agentic Inspect step itself, run the skill against
either fixture directory via `ll-harness skill init` (see docs/reference/CLI.md
for the invocation shape), pointed at a project root built the same way these
fixtures are built here.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration

_NO_INSTALL = "little_loops.init.install_check.detect_installation"


def _run_init(argv: list[str]) -> int:
    from little_loops.init.cli import main_init

    with patch(_NO_INSTALL, return_value=(None, None, None)):
        return main_init(argv)


def _plan_for(project: Path) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert _run_init(["--plan", "--root", str(project)]) == 0
    return json.loads(buf.getvalue())


class TestUnambiguousPlanFixture:
    """All keys `declared`/unambiguous: Inspect is a no-op, apply matches --yes."""

    def _build(self, tmp_path: Path) -> Path:
        project = tmp_path / "unambiguous_project"
        project.mkdir()
        (project / "pyproject.toml").write_text(
            "[tool.ruff]\n\n[tool.mypy]\n\n[tool.pytest.ini_options]\n"
        )
        pkg = project / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        return project

    def test_plan_has_no_ambiguities(self, tmp_path: Path) -> None:
        project = self._build(tmp_path)
        plan = _plan_for(project)
        assert plan["ambiguities"] == []

    def test_apply_of_unedited_plan_matches_yes_output(self, tmp_path: Path) -> None:
        plan_project = self._build(tmp_path)
        plan = _plan_for(plan_project)

        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))
        applied_project = tmp_path / "applied_via_plan"
        applied_project.mkdir()
        assert (
            _run_init(
                [
                    "--hosts",
                    "claude-code",
                    "--root",
                    str(applied_project),
                    "apply",
                    "--config",
                    str(plan_file),
                ]
            )
            == 0
        )

        yes_project = tmp_path / "applied_via_yes"
        yes_project.mkdir()
        (yes_project / "pyproject.toml").write_text((plan_project / "pyproject.toml").read_text())
        pkg = yes_project / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        assert _run_init(["--yes", "--hosts", "claude-code", "--root", str(yes_project)]) == 0

        applied_config = json.loads((applied_project / ".ll" / "ll-config.json").read_text())
        yes_config = json.loads((yes_project / ".ll" / "ll-config.json").read_text())
        # "name" legitimately differs (each fixture is built in its own tmp dir);
        # every other project.* key must match exactly.
        assert {k: v for k, v in applied_config["project"].items() if k != "name"} == {
            k: v for k, v in yes_config["project"].items() if k != "name"
        }


class TestAmbiguousSrcDirMakefileFixture:
    """Two top-level packages (ambiguous src_dir) + a Makefile-driven test target.

    `introspect()` has no Makefile support, so `test_cmd` stays `default` here
    even though a human (or the skill's Inspect step) reading the Makefile
    would settle it to `make test`. This is exactly the long-tail case
    FEAT-2705's Summary calls out.
    """

    def _build(self, tmp_path: Path) -> Path:
        project = tmp_path / "ambiguous_makefile_project"
        project.mkdir()
        for name in ("service_a", "service_b"):
            pkg = project / name
            pkg.mkdir()
            (pkg / "__init__.py").touch()
        (project / "Makefile").write_text("test:\n\tpytest service_a service_b\n")
        return project

    def test_plan_surfaces_src_dir_ambiguity(self, tmp_path: Path) -> None:
        project = self._build(tmp_path)
        plan = _plan_for(project)
        ambiguous_fields = {a["field"]: a for a in plan["ambiguities"]}
        assert "src_dir" in ambiguous_fields
        assert set(ambiguous_fields["src_dir"]["candidates"]) == {"service_a/", "service_b/"}

    def test_plan_leaves_test_cmd_at_default_despite_makefile(self, tmp_path: Path) -> None:
        project = self._build(tmp_path)
        plan = _plan_for(project)
        provenance = {p["field"]: p for p in plan["provenance"]}
        assert provenance["project.test_cmd"].get("provenance") == "default"
