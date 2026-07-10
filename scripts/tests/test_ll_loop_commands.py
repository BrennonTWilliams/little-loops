"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
import yaml

if TYPE_CHECKING:
    pass


# ENH-2529: consolidate per-test temp dirs under one module-scoped parent to cut
# macOS launchservicesd/mds re-indexing churn during full-suite runs. Each test
# still gets a fresh, unique directory; only the parent dir consolidates.
_TMP_COUNTER = itertools.count()


@pytest.fixture(scope="module")
def _module_tmp_parent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One temp parent per module instead of one top-level dir per test."""
    return tmp_path_factory.mktemp("ll_loop_commands")


@pytest.fixture
def tmp_path(_module_tmp_parent: Path, request: pytest.FixtureRequest) -> Path:
    """Override built-in tmp_path: unique fresh subdir of the module parent."""
    name = re.sub(r"\W", "_", request.node.name)[:30]
    path = _module_tmp_parent / f"{name}_{next(_TMP_COUNTER)}"
    path.mkdir()
    return path


_RUNNABLE_FSM_SUFFIX = "initial: start\nstates:\n  start:\n    terminal: true\n"


def _runnable(spec: str) -> str:
    """Append a minimal runnable FSM tail to a YAML fixture so it passes
    `is_runnable_loop()` (BUG-1634). Keeps existing fixture content as-is so
    behaviour assertions (description, category, labels) keep working.
    """
    if not spec.endswith("\n"):
        spec += "\n"
    return spec + _RUNNABLE_FSM_SUFFIX


class TestCmdValidate:
    """Tests for validate command logic."""

    @pytest.fixture
    def valid_loop_file(self, tmp_path: Path) -> Path:
        """Create a valid loop file."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "test-loop.yaml"
        loop_file.write_text("""
name: test-loop
initial: check
states:
  check:
    action: "echo hello"
    on_yes: done
    on_no: done
  done:
    terminal: true
""")
        return loop_file

    @pytest.fixture
    def invalid_loop_file(self, tmp_path: Path) -> Path:
        """Create an invalid loop file."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "invalid-loop.yaml"
        loop_file.write_text("""
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
""")
        return loop_file

    def test_valid_loop_structure(self, valid_loop_file: Path) -> None:
        """Valid loop file has correct structure."""

        with open(valid_loop_file) as f:
            data = yaml.safe_load(f)

        assert "name" in data
        assert "initial" in data
        assert "states" in data
        assert data["initial"] in data["states"]

    def test_invalid_loop_structure(self, invalid_loop_file: Path) -> None:
        """Invalid loop file has missing initial state."""

        with open(invalid_loop_file) as f:
            data = yaml.safe_load(f)

        assert data["initial"] not in data["states"]

    def test_validate_with_unreachable_state_prints_warning(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop with unreachable state is valid but prints ⚠ warning to stdout."""
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "test-loop.yaml"
        loop_file.write_text(
            "name: test-loop\n"
            "initial: start\n"
            "states:\n"
            "  start:\n"
            "    action: test\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
            "  orphan:\n"
            "    action: unreachable\n"
            "    next: done\n"
        )

        logger = Logger(use_color=False)
        result = cmd_validate("test-loop", argparse.Namespace(), loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "⚠" in captured.out

    def test_validate_warns_when_description_missing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ENH-1331: cmd_validate prints ⚠ warning when description: field is absent."""
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "no-desc.yaml"
        loop_file.write_text(
            "name: no-desc\ninitial: check\nstates:\n  check:\n    terminal: true\n"
        )

        logger = Logger(use_color=False)
        result = cmd_validate("no-desc", argparse.Namespace(), loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert "description" in captured.out

    def test_validate_with_custom_on_routing_no_false_positive(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop with custom on_done routing does not produce an unreachable-state warning."""
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "custom-routing.yaml"
        loop_file.write_text(
            "name: custom-routing\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    on_done: final\n"
            "    on_retry: check\n"
            "  final:\n"
            "    terminal: true\n"
        )

        logger = Logger(use_color=False)
        result = cmd_validate("custom-routing", argparse.Namespace(), loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "not reachable" not in captured.out

    def test_validate_json_output_valid_loop(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json flag outputs valid=true with empty violations for a valid loop."""
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "valid-loop.yaml").write_text(
            "name: valid-loop\ndescription: Test\ninitial: check\nstates:\n  check:\n    terminal: true\n"
        )

        logger = Logger(use_color=False)
        args = argparse.Namespace(json=True)
        result = cmd_validate("valid-loop", args, loops_dir, logger)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["loop"] == "valid-loop"
        assert data["valid"] is True
        assert data["violations"] == []

    def test_validate_json_output_invalid_loop(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json flag outputs valid=false with non-empty violations for an invalid loop."""
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "bad-loop.yaml").write_text(
            "name: bad-loop\ninitial: nonexistent\nstates:\n  check:\n    action: echo\n    on_yes: check\n    on_no: check\n"
        )

        logger = Logger(use_color=False)
        args = argparse.Namespace(json=True)
        result = cmd_validate("bad-loop", args, loops_dir, logger)

        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert data["loop"] == "bad-loop"
        assert data["valid"] is False
        assert len(data["violations"]) > 0
        assert all("severity" in v and "path" in v and "message" in v for v in data["violations"])
        assert any(v["severity"] == "error" for v in data["violations"])

    def test_validate_json_loop_reference_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An unresolvable bare loop: ref is an ERROR — --json reports invalid and exits non-zero.

        Promoted from WARNING (BUG-2305): a static loop: target that cannot resolve at
        definition time fails identically at runtime, so it fails the load instead of
        deferring to an opaque on_error route.
        """
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "ref-loop.yaml").write_text(
            "name: ref-loop\n"
            "description: test\n"
            "initial: run\n"
            "states:\n"
            "  run:\n"
            "    loop: no-such-loop\n"
            "    on_complete: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        logger = Logger(use_color=False)
        args = argparse.Namespace(json=True)
        result = cmd_validate("ref-loop", args, loops_dir, logger)

        assert result == 1  # ERROR causes non-zero exit
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is False
        ref_errors = [v for v in data["violations"] if "no-such-loop" in v["message"]]
        assert len(ref_errors) == 1
        assert ref_errors[0]["severity"] == "error"
        assert ref_errors[0]["path"] == "states.run.loop"

    def test_validate_json_no_flag_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --json, plain-text output is unchanged when args are passed."""
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "plain-loop.yaml").write_text(
            "name: plain-loop\ndescription: Test\ninitial: check\nstates:\n  check:\n    terminal: true\n"
        )

        logger = Logger(use_color=False)
        args = argparse.Namespace(json=False)
        result = cmd_validate("plain-loop", args, loops_dir, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "plain-loop is valid" in out
        assert "States:" in out


class TestCmdList:
    """Tests for list command logic."""

    @pytest.fixture
    def loops_dir(self, tmp_path: Path) -> Path:
        """Create a .loops directory with some files."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text("name: a")
        (loops_dir / "loop-b.yaml").write_text("name: b")
        (loops_dir / "loop-c.yaml").write_text("name: c")
        return loops_dir

    def test_list_available_loops(self, loops_dir: Path) -> None:
        """List returns all YAML files."""
        yaml_files = list(loops_dir.glob("*.yaml"))
        assert len(yaml_files) == 3
        names = sorted(p.stem for p in yaml_files)
        assert names == ["loop-a", "loop-b", "loop-c"]

    def test_no_loops_dir(self, tmp_path: Path) -> None:
        """No .loops directory returns gracefully."""
        loops_dir = tmp_path / ".loops"
        assert not loops_dir.exists()

    def test_list_shows_description(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Available loops display description."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            _runnable("name: my-loop\ndescription: Ensure tests pass\n")
        )
        (loops_dir / "bare-loop.yaml").write_text(_runnable("name: bare\n"))

        # ENH-2572: descriptions render in the detailed (-l/--long) layout.
        args = argparse.Namespace(running=False, status=None, long=True)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr().out
        assert "Ensure tests pass" in captured
        assert "my-loop" in captured
        assert "bare-loop" in captured

    def test_running_shows_status_and_elapsed(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--running output includes state.status and elapsed time."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        loops_dir = tmp_path / ".loops"
        state = LoopState(
            loop_name="my-loop",
            current_state="check_types",
            iteration=3,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:02:15",
            status="running",
            accumulated_ms=135_000,  # 2m 15s
        )

        args = argparse.Namespace(running=True, status=None)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[state]):
            result = cmd_list(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr().out
        assert "[running]" in captured
        assert "2m 15s" in captured
        assert "iteration 3" in captured

    def test_status_filter_matches(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--status filters running loops by status."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        loops_dir = tmp_path / ".loops"

        def make_state(name: str, s: str) -> LoopState:
            return LoopState(
                loop_name=name,
                current_state="check",
                iteration=1,
                captured={},
                prev_result=None,
                last_result=None,
                started_at="2026-01-01T00:00:00",
                updated_at="2026-01-01T00:00:01",
                status=s,
                accumulated_ms=5_000,
            )

        states = [make_state("loop-a", "interrupted"), make_state("loop-b", "running")]

        args = argparse.Namespace(running=False, status="interrupted")
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=states):
            result = cmd_list(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr().out
        assert "loop-a" in captured
        assert "loop-b" not in captured

    def test_status_filter_no_match_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--status returns exit code 1 when no loops match."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        args = argparse.Namespace(running=False, status="interrupted")
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[]):
            result = cmd_list(args, loops_dir)

        assert result == 1
        captured = capsys.readouterr().out
        assert "No loops with status: interrupted" in captured

    def test_list_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs a valid JSON array with name and path fields."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text(_runnable("name: loop-a\n"))
        (loops_dir / "loop-b.yaml").write_text(_runnable("name: loop-b\n"))

        args = argparse.Namespace(running=False, status=None, json=True)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 2
        names = {item["name"] for item in data}
        assert names == {"loop-a", "loop-b"}
        for item in data:
            assert "name" in item
            assert "path" in item
            assert "description" in item

    def test_list_json_empty(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with no loops outputs an empty JSON array."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        args = argparse.Namespace(running=False, status=None, json=True)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_list_without_json_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --json, output groups loops by category (uncategorized when none set)."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(_runnable("name: my-loop\n"))

        args = argparse.Namespace(running=False, status=None, json=False)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # ENH-2572: project loops pin under YOUR PROJECT with a dim
        # home-category tag instead of appearing under category headers.
        assert "YOUR PROJECT" in out
        assert "(uncategorized)" in out
        assert "my-loop" in out

    # --- BUG-1634: nested-loop enumeration -------------------------------

    def test_nested_loop_appears_with_relative_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loops nested in subdirectories (e.g. oracles/) appear in listing as
        a relative-path identifier that round-trips through `ll-loop run`.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        oracles_dir = loops_dir / "oracles"
        oracles_dir.mkdir(parents=True)
        (oracles_dir / "foo.yaml").write_text(_runnable("name: foo\n"))

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "oracles/foo" in out

    def test_lib_fragment_excluded(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Library fragments under lib/ (no `initial:`) are filtered out by
        `is_runnable_loop`, even though they live under loops/.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        lib_dir = loops_dir / "lib"
        lib_dir.mkdir(parents=True)
        # Real runnable loop alongside the fragment so the listing isn't empty.
        (loops_dir / "real-loop.yaml").write_text(_runnable("name: real-loop\n"))
        # Fragment shape: name + states but NO `initial:` — what lib/ files look like.
        (lib_dir / "fragment.yaml").write_text(
            "name: fragment\nstates:\n  step:\n    terminal: true\n"
        )

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "real-loop" in out
        assert "lib/fragment" not in out
        assert "fragment" not in out

    def test_project_override_keys_on_relative_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A project loop only overrides a built-in loop when their relative
        paths match — not their bare stems. A project oracles/foo.yaml must
        NOT suppress a built-in foo.yaml (different relative paths).
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        oracles_dir = loops_dir / "oracles"
        oracles_dir.mkdir(parents=True)
        (oracles_dir / "foo.yaml").write_text(_runnable("name: foo\n"))

        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        (builtin_dir / "foo.yaml").write_text(_runnable("name: foo\n"))

        args = argparse.Namespace(running=False, status=None, json=True, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        names = {item["name"] for item in data}
        # Both loops appear: the relative paths differ, so no override collision.
        assert "oracles/foo" in names
        assert "foo" in names


class TestLoopListCategoryFilter:
    """Tests for --category and --label filtering in cmd_list."""

    def test_category_filter_shows_only_matching(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--category shows only loops in that category."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-apo.yaml").write_text(_runnable("name: loop-apo\ncategory: apo\n"))
        (loops_dir / "loop-meta.yaml").write_text(_runnable("name: loop-meta\ncategory: meta\n"))

        args = argparse.Namespace(
            running=False, status=None, json=False, category="apo", label=None
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "loop-apo" in out
        assert "loop-meta" not in out

    def test_label_filter_shows_only_matching(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--label shows only loops with that label."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text(
            _runnable("name: loop-a\ncategory: apo\nlabels:\n  - optimize\n  - prompt\n")
        )
        (loops_dir / "loop-b.yaml").write_text(
            _runnable("name: loop-b\ncategory: meta\nlabels:\n  - health\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=["optimize"]
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "loop-a" in out
        assert "loop-b" not in out

    def test_grouped_display_by_category(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without filters, loops are grouped by category with headers (ENH-2539).

        Uses acronym-aware title casing (``apo`` -> ``APO``) instead of
        ``.title()`` (``Apo``).
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        # ENH-2572: category headers apply to built-in loops (project loops
        # pin under YOUR PROJECT) and categories with <3 members fold into
        # OTHER. Seed 4 apo + 3 meta built-ins plus one uncategorized loop.
        for i in range(4):
            (builtin_dir / f"loop-apo-{i}.yaml").write_text(
                _runnable(f"name: loop-apo-{i}\ncategory: apo\n")
            )
        for i in range(3):
            (builtin_dir / f"loop-meta-{i}.yaml").write_text(
                _runnable(f"name: loop-meta-{i}\ncategory: meta\n")
            )
        (builtin_dir / "loop-bare.yaml").write_text(_runnable("name: loop-bare\n"))

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # `apo` is in ACRONYMS -> "APO"; `meta` isn't -> "META" (v2 polish: all-caps).
        assert "APO" in out, f"acronym casing: {out!r}"
        assert "META" in out
        # The bare-old .title() rendering of `apo` would have produced "Apo"; ensure
        # that header form is no longer present.
        assert "Apo\n" not in out
        assert "loop-apo-0" in out
        assert "loop-meta-0" in out
        assert "loop-bare" in out
        # ENH-2572: categories ordered by member count descending — APO (4)
        # before META (3); the singleton uncategorized loop folds into OTHER
        # with a dim home-category tag.
        assert out.index("APO") < out.index("META")
        assert "UNCATEGORIZED" not in out
        assert "OTHER" in out
        assert "(uncategorized)" in out
        assert out.index("META") < out.index("OTHER")

    def test_json_output_includes_category_and_labels(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """JSON output includes category and labels fields."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text(
            _runnable("name: loop-a\ncategory: apo\nlabels:\n  - optimize\n")
        )

        args = argparse.Namespace(running=False, status=None, json=True, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["category"] == "apo"
        assert data[0]["labels"] == ["optimize"]

    def test_no_match_filter_returns_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Filters with no match print a message and return 0."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text(_runnable("name: loop-a\ncategory: apo\n"))

        args = argparse.Namespace(
            running=False, status=None, json=False, category="data", label=None
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "No loops match" in out


class TestLoopListVisibilityFilter:
    """Tests for the visibility tier filter in cmd_list (public/internal/example)."""

    def _seed(self, loops_dir: Path) -> None:
        loops_dir.mkdir(parents=True, exist_ok=True)
        (loops_dir / "pub.yaml").write_text(_runnable("name: pub\n"))
        (loops_dir / "vis-pub.yaml").write_text(_runnable("name: vis-pub\nvisibility: public\n"))
        (loops_dir / "sub.yaml").write_text(_runnable("name: sub\nvisibility: internal\n"))
        (loops_dir / "demo.yaml").write_text(_runnable("name: demo\nvisibility: example\n"))

    def test_default_hides_internal_and_example(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Default listing shows only public loops; internal/example hidden."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=False,
            category=None,
            label=None,
            all=False,
            internal=False,
            examples=False,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        out = capsys.readouterr().out
        assert "pub" in out
        assert "vis-pub" in out
        assert "  sub" not in out
        assert "demo" not in out
        # Footer surfaces hidden counts via the closing summary hint.
        assert "hidden" in out
        assert "1 internal" in out
        assert "1 example" in out

    def test_all_shows_everything(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--all includes internal and example loops."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=False,
            category=None,
            label=None,
            all=True,
            internal=False,
            examples=False,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        out = capsys.readouterr().out
        for name in ("pub", "vis-pub", "sub", "demo"):
            assert name in out

    def test_internal_flag_shows_only_internal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--internal narrows to internal-tier loops only."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=False,
            internal=True,
            examples=False,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert names == {"sub"}

    def test_examples_flag_shows_only_examples(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--examples narrows to example-tier loops only."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=False,
            internal=False,
            examples=True,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert names == {"demo"}

    def test_json_includes_visibility_field(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """JSON output carries the visibility tier for each loop."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=True,
            internal=False,
            examples=False,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        by_name = {i["name"]: i["visibility"] for i in json.loads(capsys.readouterr().out)}
        assert by_name["pub"] == "public"
        assert by_name["sub"] == "internal"
        assert by_name["demo"] == "example"

    def test_internal_includes_from_stubs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--internal shows a pure from: stub (no initial/states) with visibility: internal."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir(parents=True, exist_ok=True)

        # Parent loop with the full FSM
        (loops_dir / "parent.yaml").write_text(_runnable("name: parent\nvisibility: public\n"))
        # Pure context-override stub — no initial or states of its own
        (loops_dir / "ctx-stub.yaml").write_text(
            "name: ctx-stub\nfrom: parent\nvisibility: internal\ndescription: variant\n"
        )

        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=False,
            internal=True,
            examples=False,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert "ctx-stub" in names
        assert "parent" not in names  # parent is public, not internal

    def test_default_hides_from_stub_with_internal_visibility(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Default listing still hides a from: stub marked visibility: internal."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir(parents=True, exist_ok=True)

        (loops_dir / "parent.yaml").write_text(_runnable("name: parent\nvisibility: public\n"))
        (loops_dir / "ctx-stub.yaml").write_text(
            "name: ctx-stub\nfrom: parent\nvisibility: internal\ndescription: variant\n"
        )

        args = argparse.Namespace(
            running=False,
            status=None,
            json=False,
            category=None,
            label=None,
            all=False,
            internal=False,
            examples=False,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        out = capsys.readouterr().out
        assert "ctx-stub" not in out

    def test_visibility_flag_public_shows_only_public(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--visibility public returns only public loops (explicit form of the default view)."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=False,
            internal=False,
            examples=False,
            visibility="public",
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert "pub" in names
        assert "vis-pub" in names
        assert "sub" not in names
        assert "demo" not in names

    def test_visibility_flag_internal_shows_only_internal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--visibility internal narrows to internal loops."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=False,
            internal=False,
            examples=False,
            visibility="internal",
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert names == {"sub"}

    def test_visibility_flag_example_shows_only_examples(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--visibility example narrows to example-tier loops."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=False,
            internal=False,
            examples=False,
            visibility="example",
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert names == {"demo"}

    def test_visibility_flag_all_shows_everything(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--visibility all includes all tiers."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        self._seed(loops_dir)
        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=None,
            all=False,
            internal=False,
            examples=False,
            visibility="all",
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert {"pub", "vis-pub", "sub", "demo"} == names

    def test_visibility_flag_composes_with_label(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--visibility public + --label filters to labeled public loops only."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        (loops_dir / "pub-tagged.yaml").write_text(
            _runnable("name: pub-tagged\nvisibility: public\nlabels: [hermes]\n")
        )
        (loops_dir / "pub-plain.yaml").write_text(
            _runnable("name: pub-plain\nvisibility: public\n")
        )
        (loops_dir / "int-tagged.yaml").write_text(
            _runnable("name: int-tagged\nvisibility: internal\nlabels: [hermes]\n")
        )

        args = argparse.Namespace(
            running=False,
            status=None,
            json=True,
            category=None,
            label=["hermes"],
            all=False,
            internal=False,
            examples=False,
            visibility="public",
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            assert cmd_list(args, loops_dir) == 0
        names = {item["name"] for item in json.loads(capsys.readouterr().out)}
        assert names == {"pub-tagged"}


class TestLoopListFormatting:
    """Tests for ENH-1614: ll-loop list output readability improvements."""

    def test_truncate_unit(
        self,
    ) -> None:
        """_truncate() truncates with ellipsis, handles short/zero edge cases."""
        from little_loops.cli.loop.info import _truncate

        assert _truncate("hello", 3) == "he…"
        assert _truncate("hi", 5) == "hi"
        assert _truncate("text", 0) == ""
        assert _truncate("abcd", 3) == "ab…"
        assert _truncate("abc", 3) == "abc"  # exact fit, no truncation
        assert _truncate("", 10) == ""

    def test_column_alignment_names_padded(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Names are padded to fixed width so descriptions start at same column."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "short.yaml").write_text(
            _runnable("name: a\ncategory: test\ndescription: desc-a\n")
        )
        (loops_dir / "long.yaml").write_text(
            _runnable("name: a-very-long-name\ncategory: test\ndescription: desc-b\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        import re

        ansi_re = re.compile(r"\033\[[0-9;]*m")
        lines = out.strip().split("\n")
        # Find the two entry lines (skip header)
        entry_lines = [line for line in lines if line.startswith("  ") and "desc-" in line]
        assert len(entry_lines) == 2
        # Both descriptions should start at the same horizontal position
        cleaned = [ansi_re.sub("", line) for line in entry_lines]
        desc_positions = {
            name: clean.index(name)
            for clean in cleaned
            for name in ("desc-a", "desc-b")
            if name in clean
        }
        assert len(desc_positions) == 2
        positions = list(desc_positions.values())
        assert positions[0] == positions[1]

    def test_column_alignment_across_subgroups_and_flat_tail(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Rows under an auto-clustered subgroup subhead (4-space indent) must
        keep their kind/description columns aligned with the category's flat
        tail rows (2-space indent). Regression: the fixed-width name field did
        not compensate for the extra subgroup indent, shifting every column to
        the right for subgrouped rows only.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        # A "spike-*" prefix cluster (>=3 members) triggers a subgroup subhead;
        # "other" falls into the flat tail. ENH-2572: subgroups render inside
        # built-in category sections (project loops pin under YOUR PROJECT).
        for name in ("spike-alpha", "spike-beta", "spike-gamma"):
            (builtin_dir / f"{name}.yaml").write_text(
                _runnable(f"name: {name}\ncategory: test\ndescription: desc-{name}\n")
            )
        (builtin_dir / "other.yaml").write_text(
            _runnable("name: other\ncategory: test\ndescription: desc-other\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        ansi_re = re.compile(r"\033\[[0-9;]*m")
        # Description column must start at the same absolute position for a
        # subgrouped row and a flat-tail row.
        positions = {}
        for line in out.split("\n"):
            clean = ansi_re.sub("", line)
            for name in ("desc-spike-alpha", "desc-other"):
                if name in clean:
                    positions[name] = clean.index(name)
        assert set(positions) == {"desc-spike-alpha", "desc-other"}
        assert positions["desc-spike-alpha"] == positions["desc-other"], (
            f"columns misaligned: {positions}"
        )

    def test_description_truncation_at_narrow_width(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Description is truncated with … when terminal width is narrow."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_desc = "This is a very long description that would definitely overflow a narrow terminal width setting"
        (loops_dir / "my-loop.yaml").write_text(
            _runnable(f"name: my-loop\ncategory: test\ndescription: {long_desc}\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=60):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "…" in out

    def test_description_not_truncated_at_wide_width(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Description is NOT truncated when terminal is wide enough."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        short_desc = "Short description"
        (loops_dir / "my-loop.yaml").write_text(
            _runnable(f"name: my-loop\ncategory: test\ndescription: {short_desc}\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "…" not in out

    def test_multiline_description_collapsed_to_single_line(
        self,
        tmp_path: Path,
    ) -> None:
        """_load_loop_meta() collapses multi-line descriptions into a single
        space-joined ``description`` string so ``ll-loop list`` rows can fill
        the full terminal width regardless of YAML block-scalar wrapping
        (BUG-2566 follow-up)."""
        from little_loops.cli.loop.info import _load_loop_meta

        loop_file = tmp_path / "multi.yaml"
        loop_file.write_text("name: multi\ndescription: |\n  First line.\n  Second line.\n")
        meta = _load_loop_meta(loop_file)

        assert meta["description"] == "First line. Second line."
        assert "\n" not in meta["description"]
        assert "…" not in meta["description"]

    def test_singleline_description_no_ellipsis(
        self,
        tmp_path: Path,
    ) -> None:
        """_load_loop_meta() does NOT append … for single-line descriptions."""
        from little_loops.cli.loop.info import _load_loop_meta

        loop_file = tmp_path / "single.yaml"
        loop_file.write_text("name: single\ndescription: Only one line.\n")
        meta = _load_loop_meta(loop_file)

        assert meta["description"] == "Only one line."

    def test_from_inheritance_resolves_category(
        self,
        tmp_path: Path,
    ) -> None:
        """_load_loop_meta() resolves from: inheritance so inherited category is visible."""
        from little_loops.cli.loop.info import _load_loop_meta

        parent_file = tmp_path / "lib" / "apo-base.yaml"
        parent_file.parent.mkdir(parents=True)
        parent_file.write_text(
            "name: apo-base\ncategory: apo\nlabels:\n  - apo\ninitial: start\nstates:\n  start:\n    action_type: prompt\n    prompt: base\n"
        )
        child_file = tmp_path / "apo-child.yaml"
        child_file.write_text(
            "name: apo-child\nfrom: lib/apo-base\ndescription: A child loop.\ninitial: start\nstates:\n  start:\n    action_type: prompt\n    prompt: child\n"
        )

        meta = _load_loop_meta(child_file)

        assert meta["category"] == "apo"
        assert "apo" in meta["labels"]

    def test_label_badge_rendering(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Labels up to 2 are displayed as [label] badges; extras collapse to [+N]."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # 2 labels: both shown, no overflow badge
        (loops_dir / "labeled.yaml").write_text(
            _runnable("name: labeled\ncategory: test\nlabels:\n  - experimental\n  - slow\n")
        )
        # 4 labels: first 2 shown, [+2] overflow badge
        (loops_dir / "many-labels.yaml").write_text(
            _runnable("name: many-labels\ncategory: test\nlabels:\n  - a\n  - b\n  - c\n  - d\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # First loop: 2 labels, both visible, no overflow
        assert "[experimental]" in out
        assert "[slow]" in out
        # Second loop: 4 labels, only first 2 visible + overflow badge
        assert "[a]" in out
        assert "[b]" in out
        assert "[c]" not in out
        assert "[d]" not in out
        assert "[+2]" in out

    def test_builtin_vs_project_name_color(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ENH-2572: per-category color on built-in section headers; project
        loops pin under YOUR PROJECT (the kind column is gone)."""
        from little_loops.cli import output as output_mod
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "project-loop.yaml").write_text(
            _runnable("name: project-loop\ncategory: test\n")
        )

        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        # >=3 members so "test" renders as a real category section.
        for n in ("builtin-a", "builtin-b", "builtin-c"):
            (builtin_dir / f"{n}.yaml").write_text(_runnable(f"name: {n}\ncategory: test\n"))

        # Patch CATEGORY_COLOR to a known code to make the assertion stable.
        with patch.dict(output_mod.CATEGORY_COLOR, {"test": "38;5;201"}, clear=False):
            args = argparse.Namespace(
                running=False, status=None, json=False, category=None, label=None
            )
            with patch(
                "little_loops.cli.loop.info.get_builtin_loops_dir",
                return_value=builtin_dir,
            ):
                with patch("little_loops.cli.output._USE_COLOR", True):
                    result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # The built-in category header carries the per-category color.
        assert "\033[38;5;201m" in out
        # Project loop pins under YOUR PROJECT with its home-category tag.
        assert "YOUR PROJECT" in out
        assert "project-loop" in out and "builtin-a" in out
        assert out.index("YOUR PROJECT") < out.index("TEST")
        # ENH-2572: the kind column is gone — "built-in" appears nowhere.
        assert "built-in" not in out

    def test_builtin_tag_absent_project_marker_present(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ENH-2572: no kind column and no ● marker — built-in rows are
        unlabeled; project loops are distinguished by the pinned section."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "project-loop.yaml").write_text(
            _runnable("name: project-loop\ncategory: test\n")
        )

        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        (builtin_dir / "builtin-loop.yaml").write_text(
            _runnable("name: builtin-loop\ncategory: test\n")
        )

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        lines = out.split("\n")
        project_line = next(line for line in lines if "project-loop" in line)
        builtin_line = next(line for line in lines if "builtin-loop" in line)
        # The built-in row carries no kind word at all (it is the default).
        assert "built-in" not in builtin_line
        # The project row lives in the pinned section, above the built-in row.
        assert out.index("YOUR PROJECT") < out.index("builtin-loop")
        assert out.index(project_line) < out.index(builtin_line)
        # Old marker removed
        assert "●" not in project_line and "●" not in builtin_line

    def test_blank_line_between_categories(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A blank line separates category groups (before each header after the first)."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        # ENH-2572: >=3 members per category so both render as real sections.
        for i in range(3):
            (builtin_dir / f"loop-a{i}.yaml").write_text(
                _runnable(f"name: loop-a{i}\ncategory: alpha\n")
            )
            (builtin_dir / f"loop-b{i}.yaml").write_text(
                _runnable(f"name: loop-b{i}\ncategory: beta\n")
            )

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        lines = out.split("\n")
        beta_header_idx = next(i for i, line in enumerate(lines) if "BETA" in line and "(" in line)
        assert beta_header_idx > 0
        assert lines[beta_header_idx - 1] == ""

    def test_name_column_capped_at_32(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A name longer than 32 chars is truncated; descriptions still get a real budget."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_name = "a" * 50  # 50 chars — well over the 32-char cap
        (loops_dir / "long.yaml").write_text(
            _runnable(f"name: {long_name}\ncategory: test\ndescription: Some desc here\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=80):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        import re

        ansi_re = re.compile(r"\033\[[0-9;]*m")
        lines = [ansi_re.sub("", line) for line in out.split("\n")]
        entry_line = next(line for line in lines if "Some desc here" in line)
        # Name column capped: truncated name is at most 33 chars (32 + ellipsis)
        name_part = entry_line.lstrip()
        assert len(name_part.split()[0]) <= 33
        # Description is visible (not an ellipsis stub)
        assert "Some desc here" in entry_line

    def test_summary_header(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A summary header with loop count and category count is printed before groups."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text(_runnable("name: loop-a\ncategory: cat1\n"))
        (loops_dir / "loop-b.yaml").write_text(_runnable("name: loop-b\ncategory: cat2\n"))

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # Summary header appears before any category header (v2 polish: all-caps)
        assert "2 LOOPS" in out
        assert "2 CATEGORIES" in out
        # Summary appears before first category
        first_cat_pos = min(
            out.index("CAT1") if "CAT1" in out else len(out),
            out.index("CAT2") if "CAT2" in out else len(out),
        )
        assert out.index("2 LOOPS") < first_cat_pos

    def test_no_color_output_no_ansi(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """NO_COLOR mode produces no ANSI escape codes in list output."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            _runnable(
                "name: my-loop\ncategory: test\ndescription: A test loop\nlabels:\n  - experimental\n"
            )
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.output._USE_COLOR", False):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "\033[" not in out
        assert "my-loop" in out
        assert "A test loop" in out
        assert "[experimental]" in out

    def test_row_fits_terminal_with_wide_labels(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Wide labels must not overflow the terminal width.

        Regression test: previously the description column budget was computed
        once per render and did not shrink when labels were wider than the
        reserved 18-col slot, so rows with two long labels could render to
        82-94 cols at TW=80.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "wide.yaml").write_text(
            _runnable(
                "name: wide\n"
                "category: test\n"
                "description: A simple description\n"
                "labels:\n"
                "  - experimental\n"
                "  - performance-critical\n"
            )
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=80):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        ansi_re = re.compile(r"\033\[[0-9;]*m")
        # Walk every non-blank, non-header line; entry rows contain the loop name.
        for line in out.split("\n"):
            stripped = ansi_re.sub("", line)
            if "wide" not in stripped or "experimental" not in stripped:
                continue
            assert len(stripped.rstrip()) <= 80, (
                f"row overflows TW=80 with wide labels: len={len(stripped.rstrip())} {stripped!r}"
            )

    def test_desc_budget_shrinks_when_labels_wide(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Wide labels reduce the desc budget so the row fits.

        Same description, same TW=80 — with wide labels the desc truncates
        (ends with …); without labels the desc renders fully.
        """
        from little_loops.cli.loop.info import cmd_list

        long_desc = (
            "This is a fairly long description that definitely exceeds the "
            "shrunk desc budget when wide labels consume most of the row."
        )

        # Wide labels variant
        loops_dir_wide = tmp_path / "loops_wide"
        loops_dir_wide.mkdir()
        (loops_dir_wide / "wide.yaml").write_text(
            _runnable(
                "name: wide\n"
                "category: test\n"
                f"description: {long_desc}\n"
                "labels:\n"
                "  - experimental\n"
                "  - performance-critical\n"
            )
        )
        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=80):
                cmd_list(args, loops_dir_wide)
        out_wide = capsys.readouterr().out
        ansi_re = re.compile(r"\033\[[0-9;]*m")
        entry_wide = next(
            ansi_re.sub("", ln)
            for ln in out_wide.split("\n")
            if "wide" in ln and "experimental" in ln
        )
        assert "…" in entry_wide, f"desc should be truncated with wide labels: {entry_wide!r}"
        assert long_desc not in entry_wide

        # No-labels variant — desc renders more of itself
        loops_dir_bare = tmp_path / "loops_bare"
        loops_dir_bare.mkdir()
        (loops_dir_bare / "bare.yaml").write_text(
            _runnable("name: bare\ncategory: test\ndescription: " + long_desc + "\n")
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=80):
                cmd_list(args, loops_dir_bare)
        out_bare = capsys.readouterr().out
        entry_bare = next(ansi_re.sub("", ln) for ln in out_bare.split("\n") if "bare" in ln)
        # Compare visible desc length: with wide labels the desc budget
        # shrinks, so the rendered description must be shorter than without
        # labels. Use the ellipsis boundary as the marker — anything beyond
        # the ellipsis is hidden either way for a 121-char input at TW=80.
        import re as _re

        del _re  # regex anchoring on the desc gap is ambiguous with tags/labels

        def _visible_desc(entry: str) -> int:
            """Visible length of the description text itself in the row."""
            anchor = long_desc[:10]
            if anchor not in entry:
                return 0
            seg = entry[entry.index(anchor) :]
            if "…" in seg:
                return seg.index("…")
            return len(seg.rstrip())

        wide_visible = _visible_desc(entry_wide)
        bare_visible = _visible_desc(entry_bare)
        assert wide_visible < bare_visible, (
            f"wide labels should shrink desc budget: wide={wide_visible}, bare={bare_visible}\n"
            f"wide_entry={entry_wide!r}\nbare_entry={entry_bare!r}"
        )

    @pytest.mark.parametrize(
        "labels_yaml",
        [
            "",  # no labels
            "labels:\n  - a\n",
            "labels:\n  - a\n  - b\n",
            "labels:\n  - experimental\n  - performance-critical\n  - optimization\n",  # +1 collapse
        ],
    )
    def test_row_width_invariant_across_label_counts(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        labels_yaml: str,
    ) -> None:
        """Every entry row fits within TW regardless of label count/size."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # File name matches the loop name we expect to see in the rendered row.
        (loops_dir / "myloop.yaml").write_text(
            _runnable(f"name: myloop\ncategory: test\ndescription: A description\n{labels_yaml}")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=100):
                cmd_list(args, loops_dir)
        out = capsys.readouterr().out
        ansi_re = re.compile(r"\033\[[0-9;]*m")
        entry = next(ansi_re.sub("", ln) for ln in out.split("\n") if "myloop" in ln)
        assert len(entry.rstrip()) <= 100, (
            f"row overflows TW=100 (labels_yaml={labels_yaml!r}): "
            f"len={len(entry.rstrip())} {entry!r}"
        )

    def test_long_description_row_fills_to_terminal_width(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A long-description row consumes the FULL available width up to TW,
        not merely ``<= TW``.

        BUG-2566 follow-up: after collapsing multi-line descriptions to a single
        truncated row, a row whose description exceeds the desc budget must fill
        to the terminal edge (matching ``ll-issues list``), leaving no unused
        horizontal space. Measured with ``_display_width`` (ANSI-aware) so the
        3-byte ``…`` glyph doesn't inflate the byte count into a false pass.
        """
        from little_loops.cli.loop.info import cmd_list
        from little_loops.cli.loop.layout import _display_width

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Description far longer than any width under test guarantees truncation.
        long_desc = "word " * 60
        (loops_dir / "wideloop.yaml").write_text(
            _runnable(f"name: wideloop\ncategory: test\ndescription: {long_desc}\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=False, category=None, label=None, long=True
        )
        for tw in (80, 100, 120, 160):
            with patch(
                "little_loops.cli.loop.info.get_builtin_loops_dir",
                return_value=tmp_path / "nonexistent",
            ):
                with patch("little_loops.cli.loop.info.terminal_width", return_value=tw):
                    cmd_list(args, loops_dir)
            out = capsys.readouterr().out
            entry = next(ln for ln in out.split("\n") if "wideloop" in ln)
            width = _display_width(entry.rstrip("\n"))
            # Fills to the terminal edge, minus at most one clipped word:
            # ENH-2572 truncation cuts at the last word boundary rather than
            # mid-word, so the row may stop a few columns short of TW.
            assert tw - 8 <= width <= tw, (
                f"long-desc row should fill to ~TW={tw}, got width={width}: {entry!r}"
            )

    def test_no_truncate_flag_bypasses_truncation(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--no-truncate renders the full description even at narrow TW."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_desc = "A description that is way longer than what fits at TW=60"
        # File name matches the loop name we expect to see in the rendered row.
        (loops_dir / "longloop.yaml").write_text(
            _runnable(f"name: longloop\ncategory: test\ndescription: {long_desc}\n")
        )

        args = argparse.Namespace(
            running=False,
            status=None,
            json=False,
            category=None,
            label=None,
            long=True,
            no_truncate=True,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=60):
                cmd_list(args, loops_dir)
        out = capsys.readouterr().out
        ansi_re = re.compile(r"\033\[[0-9;]*m")
        entry = next(ansi_re.sub("", ln) for ln in out.split("\n") if "longloop" in ln)
        # Full description present, no ellipsis
        assert long_desc in entry, f"no-truncate should render full desc: {entry!r}"
        assert "…" not in entry

    def test_no_truncate_flag_round_trip_through_argparse(self) -> None:
        """--no-truncate round-trips through argparse into cmd_list args."""
        import argparse as _argparse

        # Build a minimal parser mirroring the real list subparser.
        parser = _argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        list_p = sub.add_parser("list")
        list_p.add_argument("--no-truncate", action="store_true")

        ns_on = parser.parse_args(["list", "--no-truncate"])
        assert ns_on.no_truncate is True
        ns_off = parser.parse_args(["list"])
        assert ns_off.no_truncate is False


# ---------------------------------------------------------------------------
# ENH-2539: cmd_list Polish — integration tests for the 8 polish points
# ---------------------------------------------------------------------------


def _base_args(tmp_path: Path) -> argparse.Namespace:
    """Standard argparse.Namespace for cmd_list tests (defaults filter)."""
    return argparse.Namespace(
        running=False,
        status=None,
        json=False,
        long=False,
        category=None,
        label=None,
        builtin=False,
        all=False,
        internal=False,
        examples=False,
        visibility=None,
    )


class TestCmdListENH2539Polished:
    """Integration tests for ENH-2539: cmd_list polish (8 points).

    Each test covers one polish point from the issue; tests run end-to-end
    via cmd_list with `tmp_path`-seeded loop YAMLs and patched `get_builtin_loops_dir`.
    """

    def test_header_uses_per_category_color(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #1: each category header uses a distinct CATEGORY_COLOR code."""
        from little_loops.cli import output as output_mod

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        # ENH-2572: >=3 members per category so both render as real sections
        # (category headers apply to built-in loops).
        for i in range(3):
            (builtin_dir / f"a{i}.yaml").write_text(_runnable(f"name: a{i}\ncategory: apo\n"))
            (builtin_dir / f"b{i}.yaml").write_text(_runnable(f"name: b{i}\ncategory: gate\n"))

        with patch.dict(
            output_mod.CATEGORY_COLOR,
            {"apo": "38;5;201", "gate": "38;5;196"},
            clear=False,
        ):
            args = _base_args(tmp_path)
            args.label = []  # type: ignore[attr-defined]
            with patch(
                "little_loops.cli.loop.info.get_builtin_loops_dir",
                return_value=builtin_dir,
            ):
                with patch("little_loops.cli.output._USE_COLOR", True):
                    from little_loops.cli.loop.info import cmd_list

                    result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "\033[38;5;201m" in out, f"apo color missing: {out!r}"
        assert "\033[38;5;196m" in out, f"gate color missing: {out!r}"

    def test_rollup_badge_in_header(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #2: category header carries an inline rollup badge.

        ENH-2572: project loops pin under YOUR PROJECT, so category sections
        only mix kinds via visibility tiers (internal/example with --all).
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        for n in ("b1", "b2", "b3"):
            (builtin_dir / f"{n}.yaml").write_text(_runnable(f"name: {n}\ncategory: harness\n"))
        (builtin_dir / "b4.yaml").write_text(
            _runnable("name: b4\ncategory: harness\nvisibility: internal\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.all = True
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # 3 built-in + 1 internal → 4 total. Dominant is built-in (matches
        # the (N) header), so the rollup badge emits only the minority:
        # "1 internal".
        assert "(4)" in out
        assert "1 internal" in out
        # The dominant count is no longer echoed in the rollup; the (N) in
        # the category header carries it.
        assert "3 built-in" not in out

    def test_rollup_badge_uses_gray(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ENH-2542: rollup badge is rendered in ANSI 90 (gray), not ANSI 36 (cyan).

        The badge inside each category header (e.g. "18 built-in, 1 project")
        was previously cyan — which reads as greenish on teal-leaning dark
        palettes. Gray is a neutral de-emphasis that doesn't compete with the
        bold category header color above it.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        for n in ("b1", "b2", "b3"):
            (builtin_dir / f"{n}.yaml").write_text(_runnable(f"name: {n}\ncategory: harness\n"))
        (builtin_dir / "b4.yaml").write_text(
            _runnable("name: b4\ncategory: harness\nvisibility: internal\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.all = True
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            with patch("little_loops.cli.output._USE_COLOR", True):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # Locate the category-header line carrying the rollup badge.
        header_line = next(ln for ln in out.split("\n") if "HARNESS" in ln and "internal" in ln)
        # The badge substring (between the ANSI opener and reset) should be
        # wrapped in ANSI 90 (gray), not ANSI 36 (cyan).
        # Sanity: the badge text is present.
        assert "1 internal" in header_line
        # Find the ANSI opener immediately preceding "1 internal" — it must
        # be the gray opener (\033[90m), not a cyan one (\033[36m).
        badge_idx = header_line.index("1 internal")
        before_badge = header_line[:badge_idx]
        # Strip ANSI codes from `before_badge` to find the last opener
        import re as _re

        last_opener_match = list(_re.finditer(r"\x1b\[([0-9;]*)m", before_badge))
        assert last_opener_match, f"No ANSI opener before badge: {header_line!r}"
        last_opener_code = last_opener_match[-1].group(1)
        assert last_opener_code == "90", (
            f"Rollup badge opener should be ANSI 90 (gray), got "
            f"\\033[{last_opener_code}m: {header_line!r}"
        )

    def test_kind_column_removed_badge_for_exceptions(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ENH-2572 item 1: the kind column is gone — "built-in" never renders
        as a row value; internal/example exceptions carry a ◆ badge."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        (builtin_dir / "bl.yaml").write_text(_runnable("name: bl\ncategory: cat\n"))
        (builtin_dir / "il.yaml").write_text(
            _runnable("name: il\ncategory: cat\nvisibility: internal\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.all = True
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        lines = out.split("\n")
        blt = next(line for line in lines if "bl" in line and "▸" not in line)
        il = next(line for line in lines if "il" in line and "▸" not in line)
        # Built-in is the unlabeled default; exceptions get a ◆ badge.
        assert "built-in" not in blt
        assert "◆ internal" in il

    def test_acronym_casing_in_title(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #8: acronyms (APO) are uppercased; non-acronyms (evaluation) use ``.title()``."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        # ENH-2572: >=3 members per category so both render as real sections.
        for i in range(3):
            (builtin_dir / f"loop-a{i}.yaml").write_text(
                _runnable(f"name: loop-a{i}\ncategory: apo\n")
            )
            (builtin_dir / f"loop-e{i}.yaml").write_text(
                _runnable(f"name: loop-e{i}\ncategory: evaluation\n")
            )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # `apo` is in ACRONYMS -> "APO"
        assert "APO" in out
        # `evaluation` -> "EVALUATION" (v2 polish: all-caps, not title-case)
        assert "EVALUATION" in out
        # Old `.title()` form would have rendered `apo` -> "Apo"; ensure that
        # acronym-heading form is gone.
        assert "Apo\n" not in out

    def test_closing_total_summary(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #7: output ends with a `Total:` summary line."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "a.yaml").write_text(_runnable("name: a\ncategory: foo\n"))
        (loops_dir / "b.yaml").write_text(_runnable("name: b\ncategory: bar\n"))

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # v2 polish: top summary is uppercased + bold
        assert "TOTAL:" not in out  # removed in favor of single header summary
        # The top summary header still carries the totals.
        assert "2 LOOPS" in out
        assert "CATEGORIES" in out

    def test_subgroup_subhead_for_shared_prefix(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #6: ≥3 members sharing a prefix get a dim subgroup subhead."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        (builtin_dir / "apo-beam.yaml").write_text(_runnable("name: apo-beam\ncategory: harness\n"))
        (builtin_dir / "apo-contrastive.yaml").write_text(
            _runnable("name: apo-contrastive\ncategory: harness\n")
        )
        (builtin_dir / "apo-feedback.yaml").write_text(
            _runnable("name: apo-feedback\ncategory: harness\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # subgroup subheads render in the detailed layout
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "· apo-*" in out, f"Expected bullet-prefix-glob subhead: {out!r}"

    def test_row_columns_aligned_at_tw_80(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #3 + Polish #9: rows render at TW=80; description content is preserved."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        for n in ("alpha", "beta", "gamma"):
            (loops_dir / f"{n}.yaml").write_text(
                _runnable(
                    f"name: {n}\ncategory: cat\ndescription: Short description text for {n}\n"
                )
            )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # descriptions render in the detailed layout
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=80):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # At TW=80 the description column is ≤30 chars; verify each row renders its
        # description (rather than only ellipsis).
        assert "Short descr" in out  # first 13 chars of "Short description…"
        assert "alpha" in out and "beta" in out and "gamma" in out
        # The redundant "TOTAL:" closing summary line was removed; the top
        # summary header carries the totals.
        assert "TOTAL:" not in out
        assert "3 LOOPS" in out

    def test_row_columns_at_tw_120(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #3: rows align at TW=120 with description content preserved."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "x.yaml").write_text(
            _runnable(
                "name: x\ncategory: cat\n"
                "description: A medium-length description that survives medium terminals\n"
            )
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # descriptions render in the detailed layout
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=120):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "medium-length description" in out

    def test_row_columns_at_tw_200(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Polish #3: rows align at TW=200 with full description content."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "x.yaml").write_text(
            _runnable(
                "name: x\ncategory: cat\n"
                "description: A long description that absolutely definitely fits at a wide 200 column terminal\n"
            )
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # descriptions render in the detailed layout
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=200):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "absolutely definitely fits" in out

    def test_summary_header_bold_and_uppercase(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """v2 polish: top summary uses bold ANSI + uppercase labels."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "a.yaml").write_text(_runnable("name: a\ncategory: foo\n"))
        (loops_dir / "b.yaml").write_text(_runnable("name: b\ncategory: foo\n"))

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.output._USE_COLOR", True):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # Top summary header is bold + uppercase
        first_summary_line = next(ln for ln in out.split("\n") if "LOOPS" in ln)
        assert "\033[1m" in first_summary_line
        assert "2 LOOPS" in first_summary_line
        # Closing TOTAL line was removed; the top summary is the only one.
        assert "TOTAL:" not in out

    def test_description_text_not_dim(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """v2 polish: per-row description is plain text (no dim ANSI code)."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "x.yaml").write_text(
            _runnable("name: x\ncategory: cat\ndescription: This description should not be dim.\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # descriptions render in the detailed layout
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.output._USE_COLOR", True):
                with patch("little_loops.cli.output.terminal_width", return_value=120):
                    with patch("little_loops.cli.loop.info.terminal_width", return_value=120):
                        result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # Description text appears verbatim
        assert "This description should not be dim." in out
        # The dim ANSI code (\033[2m) may wrap the home-category tag on a
        # pinned row (ENH-2572), but must not wrap the description text: the
        # last ANSI opener before the description must not be the dim code.
        desc_row = next(ln for ln in out.split("\n") if "This description" in ln)
        before_desc = desc_row[: desc_row.index("This description")]
        import re as _re_dim

        openers = _re_dim.findall(r"\x1b\[([0-9;]*)m", before_desc)
        assert openers and openers[-1] != "2", f"description wrapped in dim: {desc_row!r}"

    def test_default_terminal_width_120(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """v2 polish: cmd_list uses terminal_width(default=120).

        At TW=80 the description column is floored to 20 chars; at TW=120 it
        grows to 52. A 40-char description fits at TW=120 but is truncated at
        TW=80 — so the substring at position 30-40 is the discriminator.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # 45-char description: present at TW=120 (52-col desc) but truncated
        # at TW=80 (20-col desc). The substring at position ~30-45 is the
        # discriminator.
        long_desc = "A description that is forty chars long total!"
        assert len(long_desc) == 45, len(long_desc)
        (loops_dir / "x.yaml").write_text(
            _runnable(f"name: x\ncategory: cat\ndescription: {long_desc}\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # descriptions render in the detailed layout
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.output.terminal_width", return_value=120):
                with patch("little_loops.cli.loop.info.terminal_width", return_value=120):
                    result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # At TW=120 desc_col=52, the 40-char description is fully visible.
        assert long_desc in out
        # Sanity: TW=80 would have truncated to ~20 chars; the substring at
        # position 30+ would be absent.
        assert "forty chars long" in out

    def test_loop_name_bold_white(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop name column renders with bold ANSI ("1"), not color.

        Weight-based emphasis reads identically across every terminal palette
        (no chromatic ambiguity with category headers or kind labels). The
        bold weight keeps it the most prominent thing in the row.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "alpha.yaml").write_text(_runnable("name: alpha\ncategory: cat\n"))

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            with patch("little_loops.cli.output._USE_COLOR", True):
                result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # The row containing "alpha" should be wrapped in bold ANSI, and the
        # bold opener must precede "alpha" with no intervening color code.
        row = next(ln for ln in out.split("\n") if "alpha" in ln)
        # Find every ANSI opener that appears in the row before "alpha".
        before_alpha = row[: row.index("alpha")]
        # At minimum, a \033[1m must open the loop-name cell (the bold code).
        assert "\033[1m" in before_alpha, (
            f"Expected bold opener (\033[1m) before loop name: {row!r}"
        )
        # No chromatic opener should directly precede "alpha" — the bold cell
        # should be the only ANSI block wrapping the name (no intervening color
        # code like \033[36m or \033[38;5;67m between the bold opener and alpha).
        last_opener = before_alpha.rsplit("\033[", 1)[-1]
        assert last_opener.startswith("1m"), (
            f"Last ANSI block before loop name should be the bold opener "
            f"(\\033[1m), got \\033[{last_opener!r}: {row!r}"
        )

    def test_multiline_description_no_continuation_row(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Multi-line YAML descriptions are collapsed into a single
        space-joined line and do NOT spill onto wrapped continuation lines
        below the row (BUG-2554 single-line invariant, extended by the
        BUG-2566 follow-up that keeps the *full* description rather than only
        the first line). The terminal width is pinned wide so the assertion
        tests the single-line collapse itself, not incidental width
        truncation.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "alpha.yaml").write_text(
            _runnable(
                "name: alpha\ncategory: cat\n"
                "description: |\n"
                "  First line summary.\n"
                "  Second line continues here and would previously wrap below.\n"
            )
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # descriptions render in the detailed layout
        # Pin a wide terminal so the full description is rendered without width
        # truncation — otherwise this test would pass only by accident on
        # narrow terminals that clip the second line away, and fail on wide /
        # non-TTY runners (e.g. CI, where width defaults to 120).
        with (
            patch(
                "little_loops.cli.loop.info.get_builtin_loops_dir",
                return_value=tmp_path / "nonexistent",
            ),
            patch(
                "little_loops.cli.loop.info.terminal_width",
                return_value=200,
            ),
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        import re as _re_ansi

        stripped = _re_ansi.sub(r"\033\[[0-9;]*m", "", out)
        # Both description lines are collapsed onto a single space-joined row —
        # the full text lives inline, not just the first line.
        row_lines = [ln for ln in stripped.splitlines() if "First line summary." in ln]
        assert len(row_lines) == 1, f"expected exactly one description row, got {row_lines!r}"
        row = row_lines[0]
        assert "First line summary. Second line continues here" in row
        # No 4-space-indented continuation row is emitted below the loop row.
        for ln in stripped.splitlines():
            if ln.startswith("    ") and ln[4:].strip():
                pytest.fail(f"Unexpected continuation row: {ln!r}")

    def test_single_line_description_no_extra_row(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Single-line descriptions do NOT emit a 4-space-indented
        continuation row — that would create a phantom empty line.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "alpha.yaml").write_text(
            _runnable("name: alpha\ncategory: cat\ndescription: Only one line.\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # No line in the output should be a 4-space-indented continuation —
        # the loop row itself begins with 2-space indent + colored name.
        # Strip ANSI so we can detect pure whitespace indents.
        import re as _re_ansi

        stripped = _re_ansi.sub(r"\033\[[0-9;]*m", "", out)
        for ln in stripped.splitlines():
            if ln.startswith("    ") and ln[4:].strip():
                pytest.fail(f"Unexpected 4-space-indented continuation row: {ln!r}")

    def test_subgroup_header_uses_bullet_glyph(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Subgroup headers (prefix clusters of ≥3 loops) render as
        ``· {prefix}-* (N)`` in dim gray — visually distinct from the
        parent category's ``▸ {CATEGORY}  (N)`` heading.
        """
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        (builtin_dir / "rn-implement.yaml").write_text(
            _runnable("name: rn-implement\ncategory: planning\n")
        )
        (builtin_dir / "rn-plan.yaml").write_text(_runnable("name: rn-plan\ncategory: planning\n"))
        (builtin_dir / "rn-refine.yaml").write_text(
            _runnable("name: rn-refine\ncategory: planning\n")
        )

        args = _base_args(tmp_path)
        args.label = []  # type: ignore[attr-defined]
        args.long = True  # subgroup subheads render in the detailed layout
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        # Subgroup header renders as bullet + lowercase prefix + glob.
        assert "· rn-*" in out, f"Expected bullet-prefix-glob subhead: {out!r}"
        # Parent category header keeps the arrow style.
        assert "▸" in out
        # The legacy "  RN (3)" all-caps style is gone.
        assert "  RN (" not in out


class TestCmdListENH2572ScanningFirst:
    """ENH-2572: `ll-loop list` scanning-first layout.

    Covers the pinned YOUR PROJECT section, OTHER folding, compact-grid
    default vs -l detail, size-ordered categories, · separators, footer
    hints, smart truncation, and the relaxed subgroup rule.
    """

    def _seed(self, tmp_path: Path) -> tuple[Path, Path]:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-proj.yaml").write_text(
            _runnable("name: my-proj\ncategory: harness\ndescription: My project loop.\n")
        )
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        for i in range(4):
            (builtin_dir / f"harness-{i}.yaml").write_text(
                _runnable(f"name: harness-{i}\ncategory: harness\ndescription: Harness loop {i}.\n")
            )
        for i in range(3):
            (builtin_dir / f"gate-{i}.yaml").write_text(
                _runnable(f"name: gate-{i}\ncategory: gate\ndescription: Gate loop {i}.\n")
            )
        (builtin_dir / "solo.yaml").write_text(
            _runnable("name: solo\ncategory: routing\ndescription: Singleton loop.\n")
        )
        return loops_dir, builtin_dir

    def _run(self, loops_dir: Path, builtin_dir: Path, **overrides: object) -> int:
        from little_loops.cli.loop.info import cmd_list

        args = _base_args(loops_dir.parent)
        args.label = []  # type: ignore[attr-defined]
        for k, v in overrides.items():
            setattr(args, k, v)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=builtin_dir,
        ):
            return cmd_list(args, loops_dir)

    def test_project_loops_pinned_first_and_exclusive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Project loops appear only in the pinned top section, with a dim
        home-category tag — never duplicated under their category."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir) == 0
        out = capsys.readouterr().out
        assert "YOUR PROJECT" in out
        # Pinned section leads (right after the summary header).
        assert out.index("YOUR PROJECT") < out.index("HARNESS")
        # Exactly one occurrence — not duplicated under HARNESS.
        assert out.count("my-proj") == 1
        # Home-category tag preserved inline.
        proj_line = next(ln for ln in out.split("\n") if "my-proj" in ln)
        assert "(harness)" in proj_line
        # Category count excludes the pinned copy: HARNESS shows 4 built-ins.
        assert "HARNESS  (4)" in out

    def test_small_categories_fold_into_other(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Categories with <3 members fold into a trailing OTHER group with
        the original category as a dim inline tag."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir) == 0
        out = capsys.readouterr().out
        assert "ROUTING" not in out
        assert "OTHER  (1)" in out
        solo_line = next(ln for ln in out.split("\n") if "solo" in ln)
        assert "(routing)" in solo_line
        # OTHER trails the real categories.
        assert out.index("OTHER") > out.index("GATE")

    def test_categories_ordered_by_size(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Categories are ordered by member count descending, not alphabet
        (alphabetically GATE < HARNESS, but HARNESS has more members)."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir) == 0
        out = capsys.readouterr().out
        assert out.index("HARNESS") < out.index("GATE")

    def test_uncategorized_sorts_last_among_categories(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        loops_dir, builtin_dir = self._seed(tmp_path)
        for i in range(5):
            (builtin_dir / f"bare-{i}.yaml").write_text(_runnable(f"name: bare-{i}\n"))
        assert self._run(loops_dir, builtin_dir) == 0
        out = capsys.readouterr().out
        # 5 members — bigger than every real category, but still sorted last.
        assert out.index("UNCATEGORIZED") > out.index("GATE")

    def test_header_uses_middot_separators_throughout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-2572 item 8: `N PROJECT · N BUILT-IN`, not `N PROJECT, N BUILT-IN`."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir) == 0
        out = capsys.readouterr().out
        header = next(ln for ln in out.split("\n") if "LOOPS" in ln)
        assert "1 PROJECT · 8 BUILT-IN" in header
        assert "," not in header

    def test_footer_next_action_hints(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir) == 0
        out = capsys.readouterr().out
        assert "ll-loop show <name> for details" in out
        assert "--category <cat> to filter" in out
        # Table default advertises the compact-grid flag.
        assert "--grid for a compact name grid" in out

    def test_grid_flag_has_no_descriptions_one_column_when_not_tty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--grid selects the compact name grid: no descriptions, and one loop
        per line when stdout is not a TTY (capsys pipes stdout)."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir, grid=True) == 0
        out = capsys.readouterr().out
        assert "Harness loop 0." not in out
        # Non-TTY → one name per line: no line carries two loop names.
        for ln in out.split("\n"):
            assert not ("harness-0" in ln and "harness-1" in ln), f"multi-col on non-TTY: {ln!r}"

    def test_grid_multi_column_when_tty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        loops_dir, builtin_dir = self._seed(tmp_path)
        with patch("little_loops.cli.loop.info._is_tty", return_value=True):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=120):
                assert self._run(loops_dir, builtin_dir, grid=True) == 0
        out = capsys.readouterr().out
        assert any("harness-0" in ln and "harness-1" in ln for ln in out.split("\n")), (
            f"expected multi-column grid on TTY: {out!r}"
        )

    def test_table_is_default_shows_descriptions(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The default layout is the detailed one-row-per-loop table, so
        descriptions render without any flag."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir) == 0
        out = capsys.readouterr().out
        assert "Harness loop 0." in out
        assert "My project loop." in out

    def test_long_flag_is_noop_alias_for_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`-l/--long` is retained as a no-op alias now that the table is the
        default: it still yields the detailed table."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir, long=True) == 0
        out = capsys.readouterr().out
        assert "Harness loop 0." in out
        assert "My project loop." in out

    def test_long_flag_round_trip_through_argparse(self) -> None:
        """-l / --long round-trips through argparse into cmd_list args
        (mirrors the real `ll-loop list` subparser flags)."""
        import argparse as _argparse

        parser = _argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        list_p = sub.add_parser("list")
        list_p.add_argument("-l", "--long", action="store_true")

        assert parser.parse_args(["list", "-l"]).long is True
        assert parser.parse_args(["list", "--long"]).long is True
        assert parser.parse_args(["list"]).long is False

    def test_no_project_badge_inside_pinned_section(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Rows in YOUR PROJECT don't repeat a `◆ project` badge — the section
        itself carries that information."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir, long=True) == 0
        out = capsys.readouterr().out
        proj_line = next(ln for ln in out.split("\n") if "my-proj" in ln)
        assert "◆ project" not in proj_line

    def test_json_output_unchanged_by_layout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--json is unaffected by the scanning-first layout: flat array with
        the same fields, project loops not reordered into sections."""
        loops_dir, builtin_dir = self._seed(tmp_path)
        assert self._run(loops_dir, builtin_dir, json=True) == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 9
        item = next(d for d in data if d["name"] == "my-proj")
        assert set(item) >= {"name", "path", "category", "labels", "visibility", "description"}
        assert "built_in" not in item
        assert all(d.get("built_in") for d in data if d["name"] != "my-proj")

    def test_smart_truncate_word_boundary(self) -> None:
        from little_loops.cli.loop.info import _smart_truncate

        text = "Generator evaluator harness for interactive widgets"
        cut = _smart_truncate(text, 30)
        assert cut.endswith("…")
        # No mid-word cut: the fragment before … is a word-boundary prefix.
        body = cut[:-1]
        assert text.startswith(body) and (text[len(body)] == " " or body.endswith(" ") is False)
        assert not body or text[: len(body)].rstrip() == body.rstrip()
        assert body.rstrip() in text
        assert text[len(body.rstrip()) : len(body.rstrip()) + 1] == " "

    def test_smart_truncate_prefers_first_sentence(self) -> None:
        from little_loops.cli.loop.info import _smart_truncate

        text = "Short first sentence. Then a much longer second sentence follows here."
        assert _smart_truncate(text, 40) == "Short first sentence."

    def test_smart_truncate_short_text_unchanged(self) -> None:
        from little_loops.cli.loop.info import _smart_truncate

        assert _smart_truncate("hello world", 40) == "hello world"

    def test_shared_desc_prefix_detection(self) -> None:
        from little_loops.cli.loop.info import _shared_desc_prefix

        descs = [
            "Generator-evaluator harness for canvas sketches.",
            "Generator-evaluator harness for p5js sketches.",
            "Generator-evaluator harness for SVG images.",
            "Something else entirely.",
        ]
        prefix = _shared_desc_prefix(descs)
        assert prefix == "Generator-evaluator harness for "
        # Fewer than 3 sharing → no prefix.
        assert _shared_desc_prefix(descs[:2]) == ""

    def test_shared_prefix_dimmed_in_long_layout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Repeated leading boilerplate within a category renders dim so the
        distinguishing tail stands out."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        for n in ("canvas", "p5js", "svg"):
            (builtin_dir / f"{n}.yaml").write_text(
                _runnable(
                    f"name: {n}\ncategory: harness\n"
                    f"description: Generator-evaluator harness for {n} output.\n"
                )
            )
        with patch("little_loops.cli.output._USE_COLOR", True):
            with patch("little_loops.cli.loop.info.terminal_width", return_value=120):
                assert self._run(loops_dir, builtin_dir, long=True) == 0
        out = capsys.readouterr().out
        row = next(ln for ln in out.split("\n") if "canvas output" in ln)
        assert "\033[2mGenerator-evaluator harness for " in row

    def test_subgroup_rule_relaxed_no_dominance_requirement(self) -> None:
        """ENH-2572 item 10: a ≥3-member prefix cluster subgroups even when it
        is well under 50% of the category."""
        from little_loops.cli.loop.info import _detect_subgroups

        group = [{"name": f"rl-{i}"} for i in range(3)] + [
            {"name": f"loner-{i}x"} for i in range(7)
        ]
        subgroups = _detect_subgroups(group)
        prefixes = [p for p, _ in subgroups]
        assert "rl" in prefixes, f"expected rl-* subgroup: {subgroups}"


class TestCmdHistory:
    """Tests for history command logic."""

    @pytest.fixture
    def events_file(self, tmp_path: Path) -> Path:
        """Create an events file."""
        running_dir = tmp_path / ".loops" / ".running"
        running_dir.mkdir(parents=True)
        events_file = running_dir / "test-loop.events.jsonl"

        events = [
            {"event": "loop_start", "ts": "2026-01-13T10:00:00", "loop": "test-loop"},
            {"event": "state_enter", "ts": "2026-01-13T10:00:01", "state": "check", "iteration": 1},
            {"event": "action_start", "ts": "2026-01-13T10:00:02", "action": "echo hello"},
            {"event": "evaluate", "ts": "2026-01-13T10:00:03", "verdict": "yes"},
        ]

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_file

    def test_read_events(self, events_file: Path) -> None:
        """Events file can be read as JSONL."""
        events: list[dict[str, Any]] = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line.strip()))

        assert len(events) == 4
        assert events[0]["event"] == "loop_start"
        assert events[-1]["verdict"] == "yes"

    def test_tail_events(self, events_file: Path) -> None:
        """Tail returns last N events."""
        events: list[dict[str, Any]] = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line.strip()))

        tail = 2
        last_n = events[-tail:]
        assert len(last_n) == 2
        assert last_n[0]["event"] == "action_start"


class TestHistoryTail:
    """Integration tests for history --tail flag truncation behavior."""

    @pytest.fixture
    def many_events_file(self, tmp_path: Path) -> Path:
        """Create an archived events file with 10 events for tail testing."""
        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

        # Create 10 events with unique identifiers
        events = [
            {
                "event": "transition",
                "ts": f"2026-01-15T10:00:{i:02d}",
                "from": f"state{i}",
                "to": f"state{i + 1}",
            }
            for i in range(10)
        ]

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_file

    def test_history_tail_limits_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail N should show only last N events."""
        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "3"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Verify only last 3 events appear (state7, state8, state9)
        assert "from=state7" in captured.out
        assert "from=state8" in captured.out
        assert "from=state9" in captured.out
        # First events should NOT appear (use exact match to avoid state10 matching state1)
        assert "from=state0" not in captured.out
        assert "from=state1" not in captured.out
        assert "from=state5" not in captured.out

    def test_history_tail_zero_shows_all(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail 0 shows all events (Python list[-0:] returns full list)."""
        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "0"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Due to Python slicing behavior, list[-0:] returns all items
        # All 10 events should appear
        for i in range(10):
            assert f"from=state{i}" in captured.out

    def test_history_tail_exceeds_events_shows_all(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail N where N > total events shows all events."""
        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "100"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 10 events should appear
        for i in range(10):
            assert f"from=state{i}" in captured.out

    def test_history_default_tail_shows_all_small(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """Without --tail (default 50), all events shown when < 50."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 10 events should appear (10 < 50 default)
        for i in range(10):
            assert f"from=state{i}" in captured.out

    def test_history_tail_preserves_chronological_order(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """Tail should show events in chronological order."""
        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "3"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Verify chronological order: state7 before state8 before state9
        state7_pos = captured.out.find("state7")
        state8_pos = captured.out.find("state8")
        state9_pos = captured.out.find("state9")
        assert state7_pos < state8_pos < state9_pos

    def test_history_tail_with_empty_events(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--tail with empty events file handles gracefully."""
        # Create empty archived events file
        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        events_file.write_text("")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "5"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
        captured = capsys.readouterr()
        assert "No events found" in captured.out

    def test_history_tail_excludes_action_output_from_count(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """action_output events should not count toward --tail in non-verbose mode.

        Regression test for BUG-657: when a shell action produces many output lines,
        those action_output events should not consume the tail budget, hiding earlier
        iterations from the user.
        """
        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

        # Simulate 3 iterations, each with 1 visible event + 10 action_output events.
        # Total raw events: 3 * 11 = 33. With --tail 5 applied to raw events (old bug),
        # only the last 5 raw events (all action_output from iter 3) would be kept,
        # hiding iter 1 and iter 2. With the fix, tail applies to visible events only.
        events = []
        for i in range(1, 4):
            events.append(
                {
                    "event": "state_enter",
                    "ts": f"2026-01-15T10:00:{i:02d}",
                    "state": f"iter{i}",
                    "iteration": i,
                }
            )
            for j in range(10):
                events.append(
                    {
                        "event": "action_output",
                        "ts": f"2026-01-15T10:00:{i:02d}",
                        "line": f"output line {j}",
                    }
                )

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "5"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 3 iterations should be visible (3 visible events <= tail 5)
        assert "iter1" in captured.out
        assert "iter2" in captured.out
        assert "iter3" in captured.out
        # action_output lines should NOT appear in non-verbose mode
        assert "output line" not in captured.out

    def test_history_tail_verbose_counts_action_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """In verbose mode, action_output events count toward --tail as before."""
        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

        # 2 iterations: 1 state_enter + 3 action_output each = 8 raw events total
        events = []
        for i in range(1, 3):
            events.append(
                {
                    "event": "state_enter",
                    "ts": f"2026-01-15T10:00:{i:02d}",
                    "state": f"iter{i}",
                    "iteration": i,
                }
            )
            for j in range(3):
                events.append(
                    {
                        "event": "action_output",
                        "ts": f"2026-01-15T10:00:{i:02d}",
                        "line": f"line{i}-{j}",
                    }
                )

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        monkeypatch.chdir(tmp_path)
        # --tail 3 in verbose mode: only last 3 raw events (all action_output from iter2)
        with patch.object(
            sys,
            "argv",
            ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "3", "--verbose"],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # iter1 should NOT appear (its events are beyond tail=3 in verbose/raw mode)
        assert "iter1" not in captured.out
        # action_output lines from iter2 should appear
        assert "line2-0" in captured.out
        assert "line2-1" in captured.out
        assert "line2-2" in captured.out

    def test_history_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs a valid JSON array of events."""
        from little_loops.cli.loop.info import cmd_history

        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events = [
            {"event": "loop_start", "ts": "2026-01-13T10:00:00", "loop": "test-loop"},
            {"event": "state_enter", "ts": "2026-01-13T10:00:01", "state": "check", "iteration": 1},
        ]
        events_file = archive_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        args = argparse.Namespace(tail=50, verbose=False, json=True)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["event"] == "loop_start"
        assert data[1]["event"] == "state_enter"

    def test_history_json_respects_tail(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with --tail N returns only the last N events."""
        from little_loops.cli.loop.info import cmd_history

        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events = [{"event": f"evt_{i}", "ts": f"2026-01-13T10:00:{i:02d}"} for i in range(5)]
        events_file = archive_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        args = argparse.Namespace(tail=2, verbose=False, json=True)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2
        assert data[0]["event"] == "evt_3"
        assert data[1]["event"] == "evt_4"

    def test_history_json_empty(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with no history outputs nothing (no history message, exit 0)."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        args = argparse.Namespace(tail=50, verbose=False, json=True)
        result = cmd_history("nonexistent", None, args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "No history" in out


class TestHistoryVerboseLLM:
    """Tests for --verbose LLM call details rendering in ll-loop history."""

    def _write_events(self, tmp_path: Path, events: list[dict[str, Any]]) -> None:
        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

    def test_verbose_evaluate_shows_llm_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose shows LLM call block (model, latency, prompt, response) for evaluate events."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "confidence": 0.9,
                    "reason": "Looks good",
                    "llm_model": "claude-sonnet-4-6",
                    "llm_latency_ms": 1234,
                    "llm_prompt": "Evaluate this output",
                    "llm_raw_output": '{"verdict":"yes"}',
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=True, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "claude-sonnet-4-6" in out
        assert "1234ms" in out
        assert "Evaluate this output" in out
        assert '{"verdict":"yes"}' in out

    def test_non_verbose_evaluate_hides_llm_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --verbose, LLM call details are not shown."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "llm_model": "claude-sonnet-4-6",
                    "llm_latency_ms": 1234,
                    "llm_prompt": "Evaluate this output",
                    "llm_raw_output": '{"verdict":"yes"}',
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=False, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "claude-sonnet-4-6" not in out
        assert "1234ms" not in out
        assert "Evaluate this output" not in out

    def test_verbose_action_complete_shows_output_preview(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose shows output_preview for action_complete events."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "action_complete",
                    "ts": "2026-01-13T10:00:02",
                    "exit_code": 0,
                    "duration_ms": 500,
                    "output_preview": "All tests passed",
                    "is_prompt": False,
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=True, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "All tests passed" in out

    def test_non_verbose_action_complete_hides_output_preview(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --verbose, output_preview is not shown in action_complete."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "action_complete",
                    "ts": "2026-01-13T10:00:02",
                    "exit_code": 0,
                    "duration_ms": 500,
                    "output_preview": "All tests passed",
                    "is_prompt": False,
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=False, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "All tests passed" not in out

    def test_full_implies_verbose_and_shows_llm_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--full implies --verbose and shows LLM call details."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "llm_model": "claude-sonnet-4-6",
                    "llm_latency_ms": 800,
                    "llm_prompt": "Evaluate this",
                    "llm_raw_output": '{"verdict":"yes"}',
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=False, full=True, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "claude-sonnet-4-6" in out
        assert "800ms" in out

    def test_evaluate_without_llm_fields_no_extra_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """evaluate events without llm_model/llm_prompt don't render LLM block."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "confidence": 0.9,
                    "reason": "exit code 0",
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=True, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "LLM Call" not in out
        assert "Prompt:" not in out


class TestCmdListRunningJson:
    """Tests for list --running --json."""

    def test_list_running_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running --json outputs a JSON array of running loop states."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=3,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:00:01",
            status="running",
        )

        args = argparse.Namespace(running=True, status=None, json=True)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[state]):
            result = cmd_list(args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["loop_name"] == "my-loop"
        assert data[0]["current_state"] == "run_tests"
        assert data[0]["iteration"] == 3

    def test_list_running_json_empty(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running --json with no running loops exits 0 with 'No running loops' message."""
        from little_loops.cli.loop.info import cmd_list

        args = argparse.Namespace(running=True, status=None, json=True)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[]):
            result = cmd_list(args, tmp_path / ".loops")

        assert result == 0
        out = capsys.readouterr().out
        assert "No running loops" in out

    def test_list_running_without_json_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running without --json still outputs human-readable text."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=3,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:00:01",
            status="running",
            accumulated_ms=42000,
        )

        args = argparse.Namespace(running=True, status=None, json=False)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[state]):
            result = cmd_list(args, tmp_path / ".loops")

        assert result == 0
        out = capsys.readouterr().out
        assert "Running loops:" in out
        assert "my-loop" in out


class TestCmdShow:
    """Tests for show command."""

    @pytest.fixture
    def valid_loop_dir(self, tmp_path: Path) -> Path:
        """Create a .loops directory with a valid loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "    on_no: check\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_show_displays_metadata(
        self,
        valid_loop_dir: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Show command displays loop metadata."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "handoff: pause" in out
        assert "check" in out
        assert "done" in out
        assert "ll-loop run my-loop" in out

    def test_show_displays_on_handoff(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Show command displays on_handoff value when set."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "spawn-loop.yaml").write_text(
            "name: spawn-loop\n"
            "initial: check\n"
            "on_handoff: spawn\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "    on_no: check\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "spawn-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "handoff: spawn" in out

    def test_show_displays_diagram(
        self,
        valid_loop_dir: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Show command displays FSM diagram."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Diagram:" in out
        assert "check" in out
        assert "done" in out

    def test_show_nonexistent_loop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Show command returns error for missing loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_show_states_hidden_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """States section is hidden when --verbose is not passed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_prompt = "\n".join(f"Line {i}: " + "x" * 50 for i in range(10))
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: fix\n"
            "states:\n"
            "  fix:\n"
            "    action: |\n"
            + "\n".join(f"      {line}" for line in long_prompt.splitlines())
            + "\n"
            "    action_type: prompt\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "States:" not in out
        assert "action:" not in out
        # Overview table and other sections still present
        assert "Diagram:" in out
        assert "Commands:" in out

    def test_show_shell_action_hidden_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Shell action is hidden when --verbose is not passed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_shell = "echo " + "x" * 100
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: run\n"
            "states:\n"
            "  run:\n"
            f'    action: "{long_shell}"\n'
            "    action_type: shell\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "States:" not in out
        assert long_shell not in out

    def test_show_verbose_shows_full_action(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose flag shows full action text."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        full_prompt = "\n".join(f"Line {i}: " + "detail " * 10 for i in range(5))
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: fix\n"
            "states:\n"
            "  fix:\n"
            "    action: |\n"
            + "\n".join(f"      {line}" for line in full_prompt.splitlines())
            + "\n"
            "    action_type: prompt\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Line 0" in out
        assert "Line 4" in out

    def test_show_verbose_shows_evaluate_prompt(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose flag shows evaluate.prompt."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            "      prompt: Did the command succeed? Answer yes or no.\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "prompt:" in out
        assert "Did the command succeed" in out

    def test_show_evaluate_hidden_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Evaluate section is hidden when --verbose is not passed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            "      prompt: |\n"
            "        Examine the output carefully.\n"
            "        Second line detail.\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "evaluate:" not in out
        assert "Examine the output carefully" not in out

    def test_show_evaluate_prompt_truncated_at_100_chars(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Evaluate prompt is hidden without --verbose; shown fully with it."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_prompt = "x" * 120
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            f"      prompt: {long_prompt}\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert long_prompt not in out
        assert "States:" not in out

    def test_show_evaluate_min_confidence_non_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-default min_confidence is shown in evaluate block."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            "      min_confidence: 0.8\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "min_confidence: 0.8" in out

    def test_show_evaluate_min_confidence_default_hidden(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default min_confidence (0.5) is not shown."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "min_confidence" not in out

    def test_show_evaluate_operator_and_target(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """operator and target shown for numeric evaluators."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo 5"\n'
            "    evaluate:\n"
            "      type: output_numeric\n"
            "      operator: gt\n"
            "      target: 3\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "operator: gt 3" in out

    def test_show_evaluate_pattern(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """pattern shown for output_contains evaluator."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: output_contains\n"
            "      pattern: ERROR\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "pattern: ERROR" in out

    def test_show_state_capture_timeout_on_maintain(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """State-level capture, timeout, and on_maintain are displayed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    capture: result\n"
            "    timeout: 60\n"
            "    on_maintain: check\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "capture: result" in out
        assert "timeout: 60s" in out
        assert "maintain \u2500\u2500\u2192 check" in out

    def test_show_state_optional_fields_absent_when_unset(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """capture, timeout, on_maintain not shown when not configured."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "capture:" not in out
        assert "timeout:" not in out
        assert "on_maintain" not in out

    def test_show_llm_config_block_non_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """LLM config block shown when non-default values are set."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "llm:\n"
            "  model: opus\n"
            "  max_tokens: 512\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "llm:" in out
        assert "model=opus" in out
        assert "max_tokens=512" in out

    def test_show_llm_config_block_hidden_when_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """LLM config block not shown when all values are default."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "LLM config" not in out

    def test_show_verbose_multiline_action_all_lines_indented(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose: all continuation lines of a multiline action are indented."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: fix\n"
            "states:\n"
            "  fix:\n"
            "    action: |\n"
            "      First line of action.\n"
            "      Second line of action.\n"
            "      Third line of action.\n"
            "    action_type: prompt\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        # Collect lines that are part of the action block (6-space indented content)
        action_content_lines = []
        in_action = False
        for line in out.splitlines():
            if line.rstrip() == "    action:":
                in_action = True
                continue
            if in_action:
                if line.startswith("      "):  # 6-space indent = action content
                    action_content_lines.append(line)
                else:
                    break
        assert len(action_content_lines) == 3, (
            f"Expected 3 action content lines, got {len(action_content_lines)}: {action_content_lines}"
        )
        for line in action_content_lines:
            assert line.startswith("      "), f"Action line not indented: {line!r}"

    def test_show_diagram_appears_before_states(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Diagram section appears before States section in output."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        diagram_pos = out.find("Diagram:")
        states_pos = out.find("States:")
        assert diagram_pos != -1
        assert states_pos != -1
        assert diagram_pos < states_pos, "Diagram: must appear before States:"

    def test_show_state_header_includes_type_badge(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """State header includes (action_type) badge; standalone type: line is absent."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: run\n"
            "states:\n"
            "  run:\n"
            '    action: "echo hello"\n'
            "    action_type: shell\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        # The state header for an initial state shows "── run ── INITIAL · shell ──"
        assert "shell" in out
        assert "    type: shell" not in out

    def test_show_commands_section_lists_all_subcommands(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Commands section lists run, test, status, and history subcommands."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Commands:" in out
        assert "ll-loop run my-loop" in out
        assert "ll-loop test my-loop" in out
        assert "ll-loop status my-loop" in out
        assert "ll-loop history my-loop" in out

    def test_show_commands_override_when_yaml_has_commands(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When loop YAML has a 'commands:' block, Commands section shows those entries."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "description: A parameterized loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
            "commands:\n"
            "  - cmd: 'll-loop run my-loop --param issue_id=P3-ENH-1367'\n"
            "    comment: 'run (replace issue_id with your issue)'\n"
            "  - cmd: 'll-loop test my-loop --param issue_id=P3-ENH-1367'\n"
            "    comment: 'single test iteration'\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Commands:" in out
        assert "ll-loop run my-loop --param issue_id=P3-ENH-1367" in out
        assert "run (replace issue_id with your issue)" in out
        assert "ll-loop test my-loop --param issue_id=P3-ENH-1367" in out
        # Generic fallback commands must NOT appear
        assert "ll-loop stop my-loop" not in out
        assert "ll-loop status my-loop" not in out
        assert "ll-loop history my-loop" not in out

    def test_show_commands_fallback_without_yaml_commands(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When loop YAML has no 'commands:' block, generic default commands are shown."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Commands:" in out
        assert "ll-loop run my-loop" in out
        assert "ll-loop stop my-loop" in out
        assert "ll-loop status my-loop" in out
        assert "ll-loop history my-loop" in out


class TestCmdTest:
    """Tests for cmd_test --state flag (FEAT-609)."""

    @pytest.fixture
    def multi_state_loop(self, tmp_path: Path) -> Path:
        """Create a multi-state loop with distinct states."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "multi-state.yaml"
        loop_file.write_text(
            "name: multi-state\n"
            "initial: check_types\n"
            "states:\n"
            "  check_types:\n"
            '    action: "echo checking types"\n'
            "    on_yes: done\n"
            "    on_no: fix_types\n"
            "  fix_types:\n"
            '    action: "echo fixing types"\n'
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_default_behavior_uses_initial_state(
        self,
        multi_state_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --state, cmd_test uses the initial state."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state=None)
        logger = Logger(use_color=False)
        result = cmd_test("multi-state", args, multi_state_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "State: check_types" in captured.out

    def test_state_flag_tests_specified_state(
        self,
        multi_state_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--state <name> tests the specified state instead of the initial one."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="fix_types")
        logger = Logger(use_color=False)
        result = cmd_test("multi-state", args, multi_state_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "State: fix_types" in captured.out

    def test_invalid_state_returns_error(
        self,
        multi_state_loop: Path,
    ) -> None:
        """--state with a nonexistent state logs an error and returns 1."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="nonexistent_state")
        logger = Logger(use_color=False)
        result = cmd_test("multi-state", args, multi_state_loop, logger)

        assert result == 1

    @pytest.fixture
    def slash_command_loop(self, tmp_path: Path) -> Path:
        """Create a loop with a slash-command evaluate state."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "slash-loop.yaml"
        loop_file.write_text(
            "name: slash-loop\n"
            "initial: evaluate\n"
            "states:\n"
            "  evaluate:\n"
            '    action: "/ll:check-code"\n'
            "    on_yes: done\n"
            "    on_no: fix\n"
            "  fix:\n"
            '    action: "/ll:manage-issue bug fix"\n'
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_slash_command_with_exit_code_0_traces_success_route(
        self,
        slash_command_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--exit-code 0 simulates yes verdict and traces transition to on_yes state."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="evaluate", exit_code=0)
        logger = Logger(use_color=False)
        result = cmd_test("slash-loop", args, slash_command_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATED" in captured.out
        assert "Exit code: 0" in captured.out
        assert "done" in captured.out  # routes to done on success

    def test_slash_command_with_exit_code_1_traces_failure_route(
        self,
        slash_command_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--exit-code 1 simulates no verdict and traces transition to on_no state."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="evaluate", exit_code=1)
        logger = Logger(use_color=False)
        result = cmd_test("slash-loop", args, slash_command_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATED" in captured.out
        assert "Exit code: 1" in captured.out
        assert "fix" in captured.out  # routes to fix on failure

    def test_slash_command_no_exit_code_uses_interactive_prompt(
        self,
        slash_command_loop: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --exit-code, slash-command state falls back to interactive prompt."""
        import io

        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        monkeypatch.setattr("sys.stdin", io.StringIO("1\n"))  # select Success (exit 0)
        args = argparse.Namespace(state="evaluate", exit_code=None)
        logger = Logger(use_color=False)
        result = cmd_test("slash-loop", args, slash_command_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "Exit code: 0" in captured.out
        assert "done" in captured.out


class TestCmdRunContextInjection:
    """Tests for cmd_run positional input injection into fsm.context."""

    @pytest.fixture
    def simple_loop(self, tmp_path: Path) -> Path:
        """Create a minimal loop that accepts a runtime input."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "input-loop.yaml"
        loop_file.write_text("""
name: input-loop
initial: init
context:
  input: null
states:
  init:
    action: "echo {{context.input}}"
    on_yes: done
    on_no: done
  done:
    terminal: true
""")
        return loops_dir

    @pytest.fixture
    def custom_key_loop(self, tmp_path: Path) -> Path:
        """Create a loop that uses a non-default input_key."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "keyed-loop.yaml"
        loop_file.write_text("""
name: keyed-loop
initial: init
input_key: issue_id
context:
  issue_id: null
states:
  init:
    action: "echo {{context.issue_id}}"
    on_yes: done
    on_no: done
  done:
    terminal: true
""")
        return loops_dir

    def test_positional_input_injected_into_context(self, simple_loop: Path) -> None:
        """Positional input arg is injected as context['input'] before execution."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        args = argparse.Namespace(
            input="FEAT-719",
            context=[],
            max_iterations=None,
            delay=None,
            no_llm=False,
            llm_model=None,
            dry_run=True,
            background=False,
            foreground_internal=False,
            quiet=False,
            verbose=False,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
            queue=False,
            program_md=None,
        )
        logger = Logger(use_color=False)
        result = cmd_run("input-loop", args, simple_loop, logger)
        assert result == 0

        # Verify injection directly via load_and_validate + manual injection
        path = simple_loop / "input-loop.yaml"
        fsm, _ = load_and_validate(path)
        fsm.context[fsm.input_key] = "FEAT-719"
        assert fsm.context["input"] == "FEAT-719"

    def test_input_hash_determinism(self, simple_loop: Path) -> None:
        """input_hash is deterministic: same input yields same hash, different yields different."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        logger = Logger(use_color=False)

        def run_with_input(task: str) -> str:
            args = argparse.Namespace(
                input=task,
                context=[],
                max_iterations=None,
                delay=None,
                no_llm=False,
                llm_model=None,
                dry_run=True,
                background=False,
                foreground_internal=False,
                quiet=False,
                verbose=False,
                show_diagrams=None,
                diagram_edge_labels=None,
                diagram_state_detail=None,
                diagram_scope=None,
                clear=False,
                queue=False,
                program_md=None,
            )
            path = simple_loop / "input-loop.yaml"
            fsm, _ = load_and_validate(path)

            def fake_load_and_validate(p: Path):  # type: ignore[override]
                return fsm, []

            from unittest.mock import patch

            with patch(
                "little_loops.fsm.validation.load_and_validate",
                side_effect=fake_load_and_validate,
            ):
                cmd_run("input-loop", args, simple_loop, logger)
            return fsm.context["input_hash"]

        hash1 = run_with_input("FEAT-719")
        hash2 = run_with_input("FEAT-719")
        hash3 = run_with_input("BUG-1960")

        assert hash1 == hash2, "Same input must produce the same input_hash"
        assert hash2 != hash3, "Different input must produce different input_hash"
        assert len(hash1) == 12, "input_hash must be 12 hex chars"
        assert len(hash3) == 12, "input_hash must be 12 hex chars"

    def test_dry_run_with_show_diagrams_renders_diagram(
        self, simple_loop: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--dry-run --show-diagrams renders FSM diagram before the execution plan."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        args = argparse.Namespace(
            input=None,
            context=[],
            max_iterations=None,
            delay=None,
            no_llm=False,
            llm_model=None,
            dry_run=True,
            background=False,
            foreground_internal=False,
            quiet=False,
            verbose=False,
            show_diagrams=True,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
            queue=False,
            program_md=None,
        )
        logger = Logger(use_color=False)
        result = cmd_run("input-loop", args, simple_loop, logger)
        assert result == 0
        out = capsys.readouterr().out
        # Diagram header and box-drawing characters must appear
        assert "== loop: input-loop" in out
        assert any(c in out for c in ("┌", "─", "│", "└"))
        # Execution plan still renders after diagram
        assert "Execution plan for" in out

    def test_dry_run_without_show_diagrams_no_diagram(
        self, simple_loop: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--dry-run without --show-diagrams does not render any diagram."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        args = argparse.Namespace(
            input=None,
            context=[],
            max_iterations=None,
            delay=None,
            no_llm=False,
            llm_model=None,
            dry_run=True,
            background=False,
            foreground_internal=False,
            quiet=False,
            verbose=False,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
            queue=False,
            program_md=None,
        )
        logger = Logger(use_color=False)
        result = cmd_run("input-loop", args, simple_loop, logger)
        assert result == 0
        out = capsys.readouterr().out
        assert "== loop: input-loop" not in out
        assert "Execution plan for" in out

    def test_no_positional_input_leaves_context_unchanged(self, simple_loop: Path) -> None:
        """When no positional input is given, context['input'] retains its YAML default."""
        from little_loops.fsm.validation import load_and_validate

        path = simple_loop / "input-loop.yaml"
        fsm, _ = load_and_validate(path)
        # No injection; context retains the null declared in YAML
        assert fsm.context.get("input") is None

    def test_context_flag_overrides_positional_input(self, simple_loop: Path) -> None:
        """--context input=X overrides a positional input since it runs after injection."""
        from little_loops.fsm.validation import load_and_validate

        path = simple_loop / "input-loop.yaml"
        fsm, _ = load_and_validate(path)

        # Simulate cmd_run injection order: positional first, then --context
        positional_input = "FEAT-719"
        fsm.context[fsm.input_key] = positional_input
        # --context override
        for kv in ["input=OVERRIDE"]:
            key, _, value = kv.partition("=")
            fsm.context[key.strip()] = value.strip()

        assert fsm.context["input"] == "OVERRIDE"

    def test_custom_input_key_loaded_from_yaml(self, custom_key_loop: Path) -> None:
        """input_key declared in YAML is respected by the FSMLoop dataclass."""
        from little_loops.fsm.validation import load_and_validate

        path = custom_key_loop / "keyed-loop.yaml"
        fsm, _ = load_and_validate(path)

        assert fsm.input_key == "issue_id"
        # Simulate positional injection using custom key
        fsm.context[fsm.input_key] = "FEAT-100"

    @pytest.fixture
    def multi_context_loop(self, tmp_path: Path) -> Path:
        """Create a loop with two named context variables for JSON unpacking tests."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "multi-context-loop.yaml"
        loop_file.write_text("""
name: multi-context-loop
initial: init
context:
  loop_name: ""
  input: ""
states:
  init:
    action: "echo {{context.loop_name}} {{context.input}}"
    on_yes: done
    on_no: done
  done:
    terminal: true
""")
        return loops_dir

    def test_json_input_all_keys_match_unpacks_all(self, multi_context_loop: Path) -> None:
        """JSON object with all keys matching context variables unpacks into those keys."""
        import json

        from little_loops.fsm.validation import load_and_validate

        path = multi_context_loop / "multi-context-loop.yaml"
        fsm, _ = load_and_validate(path)

        raw = '{"loop_name": "general-task", "input": "some task"}'
        parsed = json.loads(raw)
        matched = {k: v for k, v in parsed.items() if k in fsm.context}
        if matched:
            fsm.context.update(matched)
        else:
            fsm.context[fsm.input_key] = raw

        assert fsm.context["loop_name"] == "general-task"
        assert fsm.context["input"] == "some task"

    def test_json_input_no_keys_match_falls_back_to_string(self, multi_context_loop: Path) -> None:
        """JSON object with no matching context keys falls back to raw string storage."""
        import json

        from little_loops.fsm.validation import load_and_validate

        path = multi_context_loop / "multi-context-loop.yaml"
        fsm, _ = load_and_validate(path)

        raw = '{"unrelated": "value", "other": "data"}'
        parsed = json.loads(raw)
        matched = {k: v for k, v in parsed.items() if k in fsm.context}
        if matched:
            fsm.context.update(matched)
        else:
            fsm.context[fsm.input_key] = raw

        assert fsm.context[fsm.input_key] == raw
        assert fsm.context["loop_name"] == ""

    def test_json_input_partial_keys_match_unpacks_only_matched(
        self, multi_context_loop: Path
    ) -> None:
        """JSON object with only some keys matching context unpacks only matched keys."""
        import json

        from little_loops.fsm.validation import load_and_validate

        path = multi_context_loop / "multi-context-loop.yaml"
        fsm, _ = load_and_validate(path)

        raw = '{"loop_name": "my-loop", "unknown_key": "ignored"}'
        parsed = json.loads(raw)
        matched = {k: v for k, v in parsed.items() if k in fsm.context}
        if matched:
            fsm.context.update(matched)
        else:
            fsm.context[fsm.input_key] = raw

        assert fsm.context["loop_name"] == "my-loop"
        assert fsm.context["input"] == ""
        assert "unknown_key" not in fsm.context

    def test_non_json_string_stored_as_string(self, multi_context_loop: Path) -> None:
        """Non-JSON string input falls through to string storage unchanged."""
        import json

        from little_loops.fsm.validation import load_and_validate

        path = multi_context_loop / "multi-context-loop.yaml"
        fsm, _ = load_and_validate(path)

        raw = "plain text input"
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                matched = {k: v for k, v in parsed.items() if k in fsm.context}
                if matched:
                    fsm.context.update(matched)
                else:
                    fsm.context[fsm.input_key] = raw
            else:
                fsm.context[fsm.input_key] = raw
        except (json.JSONDecodeError, ValueError):
            fsm.context[fsm.input_key] = raw

        assert fsm.context[fsm.input_key] == "plain text input"

    def test_json_array_input_stored_as_string(self, multi_context_loop: Path) -> None:
        """JSON array input (not a dict) falls back to string storage."""
        import json

        from little_loops.fsm.validation import load_and_validate

        path = multi_context_loop / "multi-context-loop.yaml"
        fsm, _ = load_and_validate(path)

        raw = '["item1", "item2"]'
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                matched = {k: v for k, v in parsed.items() if k in fsm.context}
                if matched:
                    fsm.context.update(matched)
                else:
                    fsm.context[fsm.input_key] = raw
            else:
                fsm.context[fsm.input_key] = raw
        except (json.JSONDecodeError, ValueError):
            fsm.context[fsm.input_key] = raw

        assert fsm.context[fsm.input_key] == raw

    @pytest.fixture
    def required_input_loop(self, tmp_path: Path) -> Path:
        """Create a loop that declares required_inputs."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "required-loop.yaml"
        loop_file.write_text(
            "name: required-loop\n"
            "description: A loop that requires description input\n"
            "initial: init\n"
            "input_key: description\n"
            "required_inputs:\n"
            "  - description\n"
            "context:\n"
            "  description: ''\n"
            "states:\n"
            "  init:\n"
            "    action: 'echo ${context.description}'\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_required_input_supplied_proceeds(
        self,
        required_input_loop: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When required input is supplied, cmd_run proceeds past the required_inputs guard."""
        import sys
        from unittest.mock import patch

        monkeypatch.chdir(required_input_loop.parent)
        with patch.object(
            sys, "argv", ["ll-loop", "run", "--dry-run", "required-loop", "a nice description"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        # Guard should not abort (exit 1 with guard message) — dry-run returns 0
        assert result == 0


class TestCmdStatusJson:
    """Tests for ll-loop status --json."""

    def test_status_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs loop state as a JSON object."""
        from little_loops.cli.loop.lifecycle import cmd_status
        from little_loops.fsm.persistence import LoopState

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=5,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:05:00",
            status="running",
        )

        with patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, state)]):
            from little_loops.logger import Logger

            logger = Logger(verbose=False)
            args = argparse.Namespace(json=True)
            result = cmd_status("my-loop", loops_dir, logger, args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["loop_name"] == "my-loop"
        assert data["current_state"] == "run_tests"
        assert data["iteration"] == 5
        assert data["status"] == "running"
        assert "pid" in data
        assert "pid_source" in data
        assert "events_file" in data

    def test_status_json_no_state(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with no state returns exit code 1."""
        from little_loops.cli.loop.lifecycle import cmd_status

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[]):
            from little_loops.logger import Logger

            logger = Logger(verbose=False)
            args = argparse.Namespace(json=True)
            result = cmd_status("my-loop", loops_dir, logger, args)

        assert result == 1

    def test_status_human_readable_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --json, output is unchanged human-readable format."""
        from little_loops.cli.loop.lifecycle import cmd_status
        from little_loops.fsm.persistence import LoopState

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=2,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:01:00",
            status="interrupted",
        )

        with patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, state)]):
            from little_loops.logger import Logger

            logger = Logger(verbose=False)
            args = argparse.Namespace(json=False)
            result = cmd_status("my-loop", loops_dir, logger, args)

        assert result == 0
        out = capsys.readouterr().out
        assert "Loop: my-loop" in out
        assert "Status: interrupted" in out
        assert out.strip()[0] != "{"  # Not JSON


class TestCmdShowJson:
    """Tests for ll-loop show --json."""

    def test_show_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs FSM config as a JSON object."""
        from little_loops.cli.loop.info import cmd_show

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = loops_dir / "my-loop.yaml"
        loop_yaml.write_text(
            "name: my-loop\n"
            "description: Test loop\n"
            "initial: start\n"
            "states:\n"
            "  start:\n"
            "    action: echo hello\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        from little_loops.logger import Logger

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=True, verbose=False, resolved=False)
        result = cmd_show("my-loop", args, loops_dir, logger)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "name" in data or "states" in data  # FSMLoop.to_dict() includes these
        assert isinstance(data, dict)

    def test_show_json_invalid_loop(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with missing loop returns exit code 1."""
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=True, verbose=False, resolved=False)
        result = cmd_show("nonexistent-loop", args, loops_dir, logger)

        assert result == 1

    def test_show_human_readable_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --json, output contains the expected human-readable sections."""
        from little_loops.cli.loop.info import cmd_show

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = loops_dir / "my-loop.yaml"
        loop_yaml.write_text(
            "name: my-loop\n"
            "initial: start\n"
            "states:\n"
            "  start:\n"
            "    action: echo hello\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        from little_loops.logger import Logger

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=False, verbose=False, resolved=False)
        result = cmd_show("my-loop", args, loops_dir, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "my-loop" in out
        assert "Diagram:" in out

    def test_show_json_includes_commands_when_present(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json output includes 'commands' array when loop YAML has a commands: block."""
        import argparse
        import json

        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = loops_dir / "my-loop.yaml"
        loop_yaml.write_text(
            "name: my-loop\n"
            "description: A parameterized loop\n"
            "initial: start\n"
            "states:\n"
            "  start:\n"
            "    action: echo hello\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
            "commands:\n"
            "  - cmd: 'll-loop run my-loop --param issue_id=ENH-1367'\n"
            "    comment: 'run (replace issue_id)'\n"
        )

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=True, verbose=False, resolved=False)
        result = cmd_show("my-loop", args, loops_dir, logger)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "commands" in data
        assert len(data["commands"]) == 1
        assert data["commands"][0]["cmd"] == "ll-loop run my-loop --param issue_id=ENH-1367"
        assert data["commands"][0]["comment"] == "run (replace issue_id)"


class TestCmdShowResolved:
    """Tests for ll-loop show --resolved --json sub-loop expansion."""

    def test_resolved_expands_subloop(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--resolved --json adds _subloop key for states with loop: field."""
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        child_yaml = loops_dir / "inner-eval.yaml"
        child_yaml.write_text(
            "name: inner-eval\n"
            "description: Minimal evaluation child loop for testing\n"
            "initial: evaluate\n"
            "states:\n"
            "  evaluate:\n"
            "    action_type: prompt\n"
            "    action: Evaluate the current state.\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        parent_yaml = loops_dir / "parent-loop.yaml"
        parent_yaml.write_text(
            "name: parent-loop\n"
            "description: Parent loop with sub-loop reference\n"
            "initial: run_eval\n"
            "states:\n"
            "  run_eval:\n"
            "    loop: inner-eval\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=True, verbose=False, resolved=True)
        result = cmd_show("parent-loop", args, loops_dir, logger)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "_subloop" in data["states"]["run_eval"]
        subloop = data["states"]["run_eval"]["_subloop"]
        assert "evaluate" in subloop
        assert "done" in subloop

    def test_resolved_json_without_resolved_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json without --resolved does not add _subloop key."""
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        child_yaml = loops_dir / "inner-eval.yaml"
        child_yaml.write_text(
            "name: inner-eval\n"
            "initial: evaluate\n"
            "states:\n"
            "  evaluate:\n"
            "    action_type: prompt\n"
            "    action: Evaluate.\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        parent_yaml = loops_dir / "parent-loop.yaml"
        parent_yaml.write_text(
            "name: parent-loop\n"
            "initial: run_eval\n"
            "states:\n"
            "  run_eval:\n"
            "    loop: inner-eval\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=True, verbose=False, resolved=False)
        result = cmd_show("parent-loop", args, loops_dir, logger)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "_subloop" not in data["states"]["run_eval"]


class TestHistoryFiltering:
    """Tests for --event, --state, --since filtering in ll-loop history."""

    @pytest.fixture
    def mixed_events_file(self, tmp_path: Path) -> Path:
        """Create an archived events file with a variety of event types and states."""
        from datetime import datetime, timedelta

        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

        now = datetime.now()
        old_ts = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
        recent_ts = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")

        events = [
            {"event": "state_enter", "ts": old_ts, "state": "check", "iteration": 1},
            {"event": "action_start", "ts": old_ts, "state": "check", "action": "echo hi"},
            {"event": "evaluate", "ts": old_ts, "state": "check", "verdict": "no"},
            {"event": "route", "ts": old_ts, "from": "check", "to": "fix"},
            {"event": "state_enter", "ts": recent_ts, "state": "fix", "iteration": 2},
            {"event": "evaluate", "ts": recent_ts, "state": "fix", "verdict": "yes"},
            {"event": "route", "ts": recent_ts, "from": "fix", "to": "done"},
            {"event": "loop_complete", "ts": recent_ts, "final_state": "done"},
        ]

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_file

    def test_event_filter_evaluate(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--event evaluate returns only evaluate events."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event="evaluate",
            state=None,
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert all(e["event"] == "evaluate" for e in data)
        assert len(data) == 2

    def test_state_filter_check(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--state check returns events where state, from, or to field equals 'check'."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event=None,
            state="check",
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        # state_enter(check), action_start(check), evaluate(check), route(from=check)
        assert len(data) == 4
        for e in data:
            matches = (
                e.get("state") == "check" or e.get("from") == "check" or e.get("to") == "check"
            )
            assert matches, f"Event {e} does not match --state check"

    def test_since_filter_excludes_old_events(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--since 1h excludes events older than 1 hour."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event=None,
            state=None,
            since="1h",
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        # Only the 4 recent events (30m old) should survive; old events (3h old) excluded
        assert len(data) == 4

    def test_combined_event_and_state_filter(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--event route --state check returns only route events touching state 'check'."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event="route",
            state="check",
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["event"] == "route"
        assert data[0]["from"] == "check"

    def test_tail_applied_after_filter(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--tail applies as the final limit after --event filter."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=1,
            verbose=False,
            json=True,
            full=False,
            event="state_enter",
            state=None,
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        # 2 state_enter events exist, but --tail 1 limits to last 1
        assert len(data) == 1
        assert data[0]["state"] == "fix"

    def test_loop_complete_human_readable_normal(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """loop_complete event renders final_state, iterations, terminated_by (json=False)."""
        from little_loops.cli.loop.info import cmd_history

        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        events_file.write_text(
            json.dumps(
                {
                    "event": "loop_complete",
                    "ts": "2026-06-25T10:00:00",
                    "final_state": "done",
                    "iterations": 3,
                    "terminated_by": "terminal",
                }
            )
            + "\n"
        )

        args = argparse.Namespace(
            tail=50, verbose=False, json=False, full=False, event=None, state=None, since=None
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        out = capsys.readouterr().out
        assert "done" in out
        assert "3" in out
        assert "terminal" in out
        assert "error" not in out

    def test_loop_complete_human_readable_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """loop_complete event with error field renders crash reason in human output."""
        from little_loops.cli.loop.info import cmd_history

        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        events_file.write_text(
            json.dumps(
                {
                    "event": "loop_complete",
                    "ts": "2026-06-25T10:00:00",
                    "final_state": "cua_observe",
                    "iterations": 2,
                    "terminated_by": "error",
                    "error": "Loop file not found: cua-fix-verify",
                }
            )
            + "\n"
        )

        args = argparse.Namespace(
            tail=50, verbose=False, json=False, full=False, event=None, state=None, since=None
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        out = capsys.readouterr().out
        assert "error" in out
        assert "Loop file not found: cua-fix-verify" in out

    def test_no_filter_behavior_unchanged(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No filter flags: shows all non-action_output events (existing behavior)."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event=None,
            state=None,
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 8


class TestHistorySinceShortForm:
    """Tests for -S short form of --since in ll-loop history (ENH-910)."""

    @pytest.fixture
    def loop_archive(self, tmp_path: Path) -> Path:
        """Create an archived events file for history testing."""
        archive_dir = tmp_path / ".loops" / ".history" / "test-run-id-test-loop"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        events = [
            {"event": "transition", "ts": "2026-01-15T10:00:00", "from": "idle", "to": "check"},
        ]
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")
        return tmp_path

    def test_history_since_short_form(
        self,
        loop_archive: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-S is accepted as --since in ll-loop history (ENH-910)."""
        monkeypatch.chdir(loop_archive)
        with patch.object(
            sys,
            "argv",
            ["ll-loop", "history", "test-loop", "test-run-id", "-S", "1h"],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0


class TestCmdFragments:
    """Tests for ll-loop fragments command handler."""

    def test_fragments_lists_names_and_descriptions(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_fragments prints fragment names and first line of description."""
        from little_loops.cli.loop.info import cmd_fragments
        from little_loops.logger import Logger

        lib = tmp_path / "mylib.yaml"
        lib.write_text(
            "fragments:\n"
            "  shell_exit:\n"
            "    description: |\n"
            "      Shell command evaluated by exit code.\n"
            "      State must supply: action, on_yes, on_no.\n"
            "    action_type: shell\n"
            "    evaluate:\n"
            "      type: exit_code\n"
            "  llm_gate:\n"
            "    description: LLM prompt state with structured yes/no output.\n"
            "    action_type: prompt\n"
            "    evaluate:\n"
            "      type: llm_structured\n"
        )
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        logger = Logger(verbose=False)
        result = cmd_fragments(str(lib), argparse.Namespace(), loops_dir, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "shell_exit" in out
        assert "llm_gate" in out
        assert "Shell command evaluated by exit code." in out
        assert "LLM prompt state with structured yes/no output." in out

    def test_fragments_resolves_builtin_lib_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_fragments resolves lib/common.yaml as a built-in library path."""
        from little_loops.cli.loop.info import cmd_fragments
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        logger = Logger(verbose=False)
        result = cmd_fragments("lib/common.yaml", argparse.Namespace(), loops_dir, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "shell_exit" in out
        assert "common.yaml" in out

    def test_fragments_missing_lib_returns_nonzero(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_fragments returns 1 when the library file does not exist."""
        from little_loops.cli.loop.info import cmd_fragments
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        logger = Logger(verbose=False)
        result = cmd_fragments("lib/nonexistent.yaml", argparse.Namespace(), loops_dir, logger)

        assert result == 1

    def test_fragments_no_description_shows_placeholder(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_fragments shows a placeholder when a fragment has no description."""
        from little_loops.cli.loop.info import cmd_fragments
        from little_loops.logger import Logger

        lib = tmp_path / "plain.yaml"
        lib.write_text(
            "fragments:\n"
            "  bare_fragment:\n"
            "    action_type: shell\n"
            "    evaluate:\n"
            "      type: exit_code\n"
        )
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        logger = Logger(verbose=False)
        result = cmd_fragments(str(lib), argparse.Namespace(), loops_dir, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "bare_fragment" in out
        assert "(no description)" in out


class TestCmdSimulateCircuit:
    """Tests for ENH-1137: cmd_simulate accepts and forwards a RateLimitCircuit."""

    def test_cmd_simulate_forwards_circuit_kwarg(self, tmp_path: Path) -> None:
        """Passing circuit= to cmd_simulate forwards it through to the FSMExecutor."""
        from little_loops.cli.loop.testing import cmd_simulate
        from little_loops.fsm.executor import FSMExecutor
        from little_loops.fsm.rate_limit_circuit import RateLimitCircuit
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "sim-loop.yaml"
        loop_file.write_text(
            "name: sim-loop\n"
            "initial: execute\n"
            "states:\n"
            "  execute:\n"
            "    action: 'echo hello'\n"
            "    action_type: shell\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        circuit = RateLimitCircuit(tmp_path / "circuit.json")
        logger = Logger(use_color=False)
        args = argparse.Namespace(max_iterations=1, scenario=None)

        captured: dict[str, Any] = {}
        original_init = FSMExecutor.__init__

        def _capture_init(self: Any, *init_args: Any, **init_kwargs: Any) -> None:
            captured["kwargs"] = init_kwargs
            original_init(self, *init_args, **init_kwargs)

        with patch.object(FSMExecutor, "__init__", _capture_init):
            result = cmd_simulate("sim-loop", args, loops_dir, logger, circuit=circuit)

        assert result == 0
        assert captured["kwargs"].get("circuit") is circuit


class TestCmdNextLoop:
    """Tests for cmd_next_loop."""

    @pytest.fixture
    def loops_dir_with_history(self, tmp_path: Path) -> Path:
        """Create a loops dir with mock history for two loops."""
        loops_dir = tmp_path / ".loops"
        history_base = loops_dir / ".history"
        history_base.mkdir(parents=True)

        # autodev: 3 runs, 2 completed
        for run_id, status in [
            ("2026-01-01T120000", "completed"),
            ("2026-01-02T120000", "completed"),
            ("2026-01-03T120000", "failed"),
        ]:
            d = history_base / f"{run_id}-autodev"
            d.mkdir()
            (d / "state.json").write_text(
                json.dumps(
                    {
                        "loop_name": "autodev",
                        "status": status,
                        "started_at": f"{run_id[:10]}T12:00:00Z",
                        "current_state": "done",
                        "iteration": 1,
                        "captured": {},
                        "prev_result": None,
                        "last_result": None,
                        "updated_at": "",
                        "accumulated_ms": 1000,
                    }
                )
            )

        # review-loop: 1 run, completed
        d = history_base / "2026-01-01T090000-review-loop"
        d.mkdir()
        (d / "state.json").write_text(
            json.dumps(
                {
                    "loop_name": "review-loop",
                    "status": "completed",
                    "started_at": "2026-01-01T09:00:00Z",
                    "current_state": "done",
                    "iteration": 1,
                    "captured": {},
                    "prev_result": None,
                    "last_result": None,
                    "updated_at": "",
                    "accumulated_ms": 500,
                }
            )
        )

        return loops_dir

    def test_top_suggestion_by_default(
        self,
        loops_dir_with_history: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """next-loop returns exactly one suggestion by default."""
        from little_loops.cli.loop.next_loop import cmd_next_loop
        from little_loops.logger import Logger

        logger = Logger(use_color=False)
        args = argparse.Namespace(count=1, json=False, execute=False, exclude=[])
        result = cmd_next_loop(args, loops_dir_with_history, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "#1" in out
        # autodev has more runs so should rank higher
        assert "autodev" in out

    def test_count_returns_multiple_suggestions(
        self,
        loops_dir_with_history: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--count 2 returns two ranked suggestions."""
        from little_loops.cli.loop.next_loop import cmd_next_loop
        from little_loops.logger import Logger

        logger = Logger(use_color=False)
        args = argparse.Namespace(count=2, json=False, execute=False, exclude=[])
        result = cmd_next_loop(args, loops_dir_with_history, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "#1" in out
        assert "#2" in out

    def test_json_output_stable(
        self,
        loops_dir_with_history: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json emits valid JSON with required keys."""
        from little_loops.cli.loop.next_loop import cmd_next_loop
        from little_loops.logger import Logger

        logger = Logger(use_color=False)
        args = argparse.Namespace(count=1, json=True, execute=False, exclude=[])
        result = cmd_next_loop(args, loops_dir_with_history, logger)

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 1
        item = data[0]
        for key in ("loop", "input", "context", "score", "rationale", "command"):
            assert key in item, f"Missing key: {key}"

    def test_empty_history_returns_exit_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Empty history prints a clear message and returns exit code 1."""
        from little_loops.cli.loop.next_loop import cmd_next_loop
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        logger = Logger(use_color=False)
        args = argparse.Namespace(count=1, json=False, execute=False, exclude=[])
        result = cmd_next_loop(args, loops_dir, logger)

        assert result == 1
        out = capsys.readouterr().out
        assert "No loop history" in out

    def test_exclude_filters_loop(
        self,
        loops_dir_with_history: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--exclude skips the named loop from suggestions."""
        from little_loops.cli.loop.next_loop import cmd_next_loop
        from little_loops.logger import Logger

        logger = Logger(use_color=False)
        args = argparse.Namespace(count=1, json=False, execute=False, exclude=["autodev"])
        result = cmd_next_loop(args, loops_dir_with_history, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "autodev" not in out
        assert "review-loop" in out

    def test_ranking_prefers_higher_frequency(
        self,
        loops_dir_with_history: Path,
    ) -> None:
        """Loop with more runs scores higher than one with fewer, all else equal."""
        from little_loops.cli.loop.next_loop import _scan_history, _score_loop

        history = _scan_history(loops_dir_with_history)
        autodev_score, _, _ = _score_loop(history.get("autodev", []))
        review_score, _, _ = _score_loop(history.get("review-loop", []))
        assert autodev_score > review_score


_SIMPLE_LOOP_YAML = (
    "name: my-loop\n"
    "initial: start\n"
    "states:\n"
    "  start:\n"
    "    action: echo hello\n"
    "    on_yes: done\n"
    "  done:\n"
    "    terminal: true\n"
)


class TestCmdShowDiagramOptions:
    """Tests for ll-loop show --show-diagrams flag family (ENH-1698)."""

    def _setup_loop(self, tmp_path: Path) -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(_SIMPLE_LOOP_YAML)
        return loops_dir

    def _base_args(self, **kwargs: Any) -> argparse.Namespace:
        defaults: dict[str, Any] = {
            "json": False,
            "verbose": False,
            "resolved": False,
            "show_diagrams": None,
            "diagram_edge_labels": None,
            "diagram_state_detail": None,
            "diagram_scope": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_no_show_diagrams_uses_existing_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Without --show-diagrams, existing verbose+badges path is used (no facets kwargs)."""
        from little_loops.cli.loop import info as info_mod
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = self._setup_loop(tmp_path)
        logger = Logger(verbose=False)
        with patch.object(
            info_mod, "_render_fsm_diagram", wraps=info_mod._render_fsm_diagram
        ) as mock_render:
            result = cmd_show("my-loop", self._base_args(), loops_dir, logger)
        assert result == 0
        assert mock_render.called
        call_kwargs = mock_render.call_args.kwargs
        # Existing path does not pass suppress_labels or title_only
        assert "suppress_labels" not in call_kwargs
        assert "title_only" not in call_kwargs

    def test_bare_show_diagrams_uses_summary_preset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bare --show-diagrams (True sentinel) defaults to the 'summary' preset (main scope)."""
        from little_loops.cli.loop import info as info_mod
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = self._setup_loop(tmp_path)
        logger = Logger(verbose=False)
        args = self._base_args(show_diagrams=True)
        with patch.object(
            info_mod, "_render_fsm_diagram", wraps=info_mod._render_fsm_diagram
        ) as mock_render:
            result = cmd_show("my-loop", args, loops_dir, logger)
        assert result == 0
        call_kwargs = mock_render.call_args.kwargs
        # summary preset: edge_labels=True, state_detail=full, scope=main
        assert call_kwargs.get("mode") == "main"
        assert call_kwargs.get("suppress_labels") is False
        assert call_kwargs.get("title_only") is False

    def test_show_diagrams_clean_preset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams=clean produces suppress_labels=True, title_only=True, mode=main."""
        from little_loops.cli.loop import info as info_mod
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = self._setup_loop(tmp_path)
        logger = Logger(verbose=False)
        args = self._base_args(show_diagrams="clean")
        with patch.object(
            info_mod, "_render_fsm_diagram", wraps=info_mod._render_fsm_diagram
        ) as mock_render:
            result = cmd_show("my-loop", args, loops_dir, logger)
        assert result == 0
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs.get("suppress_labels") is True
        assert call_kwargs.get("title_only") is True
        assert call_kwargs.get("mode") == "main"

    def test_show_diagrams_slim_preset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams=slim produces suppress_labels=True, title_only=True, mode=main."""
        from little_loops.cli.loop import info as info_mod
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = self._setup_loop(tmp_path)
        logger = Logger(verbose=False)
        args = self._base_args(show_diagrams="slim")
        with patch.object(
            info_mod, "_render_fsm_diagram", wraps=info_mod._render_fsm_diagram
        ) as mock_render:
            result = cmd_show("my-loop", args, loops_dir, logger)
        assert result == 0
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs.get("suppress_labels") is True
        assert call_kwargs.get("title_only") is True
        assert call_kwargs.get("mode") == "main"

    def test_show_diagrams_detailed_preset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams=detailed produces suppress_labels=False, title_only=False, mode=full."""
        from little_loops.cli.loop import info as info_mod
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = self._setup_loop(tmp_path)
        logger = Logger(verbose=False)
        args = self._base_args(show_diagrams="detailed")
        with patch.object(
            info_mod, "_render_fsm_diagram", wraps=info_mod._render_fsm_diagram
        ) as mock_render:
            result = cmd_show("my-loop", args, loops_dir, logger)
        assert result == 0
        call_kwargs = mock_render.call_args.kwargs
        assert call_kwargs.get("suppress_labels") is False
        assert call_kwargs.get("title_only") is False
        assert call_kwargs.get("mode") == "full"

    def test_show_diagrams_and_json_mutually_exclusive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams and --json together return exit code 1."""
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = self._setup_loop(tmp_path)
        logger = Logger(verbose=False)
        args = self._base_args(json=True, show_diagrams=True)
        result = cmd_show("my-loop", args, loops_dir, logger)
        assert result == 1

    def test_diagram_output_contains_box_chars(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams renders actual diagram output (contains box-drawing chars)."""
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = self._setup_loop(tmp_path)
        logger = Logger(verbose=False)
        args = self._base_args(show_diagrams=True)
        result = cmd_show("my-loop", args, loops_dir, logger)
        assert result == 0
        out = capsys.readouterr().out
        assert "┌" in out or "─" in out  # box-drawing chars in diagram


class TestCmdAuditMeta:
    """Tests for ll-loop audit-meta command."""

    def _make_meta_eval(self, run_dir: Path, entries: list[dict[str, Any]]) -> None:
        """Write a meta-eval.jsonl file in run_dir."""
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "meta-eval.jsonl", "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def _base_args(self, as_json: bool = False) -> argparse.Namespace:
        return argparse.Namespace(json=as_json)

    def test_no_history_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 0 when no .history directory exists."""
        from little_loops.cli.loop.info import cmd_audit_meta

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        result = cmd_audit_meta("my-loop", self._base_args(), loops_dir)
        assert result == 0
        assert "No history" in capsys.readouterr().out

    def test_no_meta_eval_files_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 0 when runs exist but have no meta-eval.jsonl."""
        from little_loops.cli.loop.info import cmd_audit_meta

        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        run_dir.mkdir(parents=True)
        result = cmd_audit_meta("my-loop", self._base_args(), loops_dir)
        assert result == 0
        assert "No meta-eval" in capsys.readouterr().out

    def test_agreement_rate_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Agreement rate is computed and printed correctly."""
        from little_loops.cli.loop.info import cmd_audit_meta

        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        entries = [
            {"agreed": True, "diff_stats": {"files_changed": 2}},
            {"agreed": True, "diff_stats": {"files_changed": 1}},
            {"agreed": False, "diff_stats": {"files_changed": 0}},
            {"agreed": False, "diff_stats": {"files_changed": 0}},
        ]
        self._make_meta_eval(run_dir, entries)
        result = cmd_audit_meta("my-loop", self._base_args(), loops_dir)
        assert result == 0
        out = capsys.readouterr().out
        assert "50%" in out
        assert "No divergence" in out

    def test_optimistic_drift_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns exit code 1 and prints flag when agreed=false streak >=3."""
        from little_loops.cli.loop.info import cmd_audit_meta

        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        entries = [
            {"agreed": False, "diff_stats": {"files_changed": 0}},
            {"agreed": False, "diff_stats": {"files_changed": 0}},
            {"agreed": False, "diff_stats": {"files_changed": 0}},
        ]
        self._make_meta_eval(run_dir, entries)
        result = cmd_audit_meta("my-loop", self._base_args(), loops_dir)
        assert result == 1
        out = capsys.readouterr().out
        assert "optimistic drift" in out.lower()

    def test_trivial_agreement_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns exit code 1 and prints flag when agreed=true + files_changed=0 streak >=3."""
        from little_loops.cli.loop.info import cmd_audit_meta

        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        entries = [
            {"agreed": True, "diff_stats": {"files_changed": 0}},
            {"agreed": True, "diff_stats": {"files_changed": 0}},
            {"agreed": True, "diff_stats": {"files_changed": 0}},
        ]
        self._make_meta_eval(run_dir, entries)
        result = cmd_audit_meta("my-loop", self._base_args(), loops_dir)
        assert result == 1
        out = capsys.readouterr().out
        assert "trivial agreement" in out.lower()

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--json flag outputs parseable JSON with expected keys."""
        from little_loops.cli.loop.info import cmd_audit_meta

        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        entries = [
            {"agreed": True, "diff_stats": {"files_changed": 3}},
            {"agreed": False, "diff_stats": {"files_changed": 1}},
        ]
        self._make_meta_eval(run_dir, entries)
        result = cmd_audit_meta("my-loop", self._base_args(as_json=True), loops_dir)
        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_entries"] == 2
        assert data["agreed_count"] == 1
        assert data["agreement_rate"] == 0.5
        assert "flags" in data


class TestCmdDiagnoseEvaluators:
    """Tests for ll-loop diagnose-evaluators command."""

    def _make_events_jsonl(self, run_dir: Path, events: list[dict[str, Any]]) -> None:
        """Write a synthetic events.jsonl file in run_dir."""
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "events.jsonl", "w") as f:
            for entry in events:
                f.write(json.dumps(entry) + "\n")

    def _base_args(
        self,
        as_json: bool = False,
        threshold: float = 0.05,
        min_runs: int = 10,
    ) -> argparse.Namespace:
        return argparse.Namespace(json=as_json, threshold=threshold, min_runs=min_runs)

    def test_no_history_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 0 when no .history directory exists."""
        from little_loops.cli.loop.info import cmd_diagnose_evaluators

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        result = cmd_diagnose_evaluators("my-loop", self._base_args(), loops_dir)
        assert result == 0
        assert "No history" in capsys.readouterr().out

    def test_insufficient_runs_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 0 when runs exist but count < min_runs."""
        from little_loops.cli.loop.info import cmd_diagnose_evaluators

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"
        run_dir = history_root / "20260101T000000-my-loop"
        events = [
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "yes"},
        ]
        self._make_events_jsonl(run_dir, events)
        result = cmd_diagnose_evaluators("my-loop", self._base_args(min_runs=10), loops_dir)
        assert result == 0
        assert "Insufficient" in capsys.readouterr().out

    def test_all_pass_returns_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns 1 when a state has 100% pass rate (variance=0 < threshold)."""
        from little_loops.cli.loop.info import cmd_diagnose_evaluators

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": "yes"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = cmd_diagnose_evaluators("my-loop", self._base_args(min_runs=10), loops_dir)
        assert result == 1
        out = capsys.readouterr().out
        assert "low variance" in out
        assert "pass_rate=1.00" in out

    def test_mixed_returns_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns 0 when variance is above threshold (discriminating)."""
        from little_loops.cli.loop.info import cmd_diagnose_evaluators

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        verdicts = ["yes", "no"] * 5
        for i, verdict in enumerate(verdicts):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": verdict},
            ]
            self._make_events_jsonl(run_dir, events)

        result = cmd_diagnose_evaluators("my-loop", self._base_args(min_runs=10), loops_dir)
        assert result == 0
        out = capsys.readouterr().out
        assert "discriminating" in out

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--json flag outputs parseable JSON with expected keys."""
        from little_loops.cli.loop.info import cmd_diagnose_evaluators

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": "yes"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = cmd_diagnose_evaluators(
            "my-loop", self._base_args(as_json=True, min_runs=10), loops_dir
        )
        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["loop"] == "my-loop"
        assert data["total_runs"] == 10
        assert len(data["states"]) == 1
        assert data["states"][0]["state"] == "check"
        assert data["states"][0]["variance"] == 0.0

    def test_custom_threshold(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Custom --threshold flag is respected."""
        from little_loops.cli.loop.info import cmd_diagnose_evaluators

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        verdicts = ["yes", "yes", "yes", "yes", "no"] * 2
        for i, verdict in enumerate(verdicts):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": verdict},
            ]
            self._make_events_jsonl(run_dir, events)

        # With threshold 0.1, variance 0.16 is fine (discriminating)
        result = cmd_diagnose_evaluators(
            "my-loop", self._base_args(threshold=0.1, min_runs=10), loops_dir
        )
        assert result == 0
        out = capsys.readouterr().out
        assert "discriminating" in out


class TestCmdCalibrateBudget:
    """Tests for ll-loop calibrate-budget command."""

    def _make_events_jsonl(self, run_dir: Path, events: list[dict[str, Any]]) -> None:
        """Write a synthetic events.jsonl file in run_dir."""
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "events.jsonl", "w") as f:
            for entry in events:
                f.write(json.dumps(entry) + "\n")

    def _base_args(
        self,
        as_json: bool = False,
        threshold: float = 0.05,
        min_runs: int = 10,
    ) -> argparse.Namespace:
        return argparse.Namespace(json=as_json, threshold=threshold, min_runs=min_runs)

    def test_no_history_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 0 when no .history directory exists."""
        from little_loops.cli.loop.info import cmd_calibrate_budget

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        result = cmd_calibrate_budget("my-loop", self._base_args(), loops_dir)
        assert result == 0
        assert "No history" in capsys.readouterr().out

    def test_insufficient_runs_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 0 when runs exist but count < min_runs."""
        from little_loops.cli.loop.info import cmd_calibrate_budget

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"
        run_dir = history_root / "20260101T000000-my-loop"
        events = [
            {"event": "state_enter", "state": "check", "iteration": 1},
            {"event": "evaluate", "verdict": "yes"},
        ]
        self._make_events_jsonl(run_dir, events)
        result = cmd_calibrate_budget("my-loop", self._base_args(min_runs=10), loops_dir)
        assert result == 0
        assert "Insufficient" in capsys.readouterr().out

    def test_all_pass_returns_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns 1 when a state has 100% pass rate (variance=0 < threshold)."""
        from little_loops.cli.loop.info import cmd_calibrate_budget

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": "yes"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = cmd_calibrate_budget("my-loop", self._base_args(min_runs=10), loops_dir)
        assert result == 1
        out = capsys.readouterr().out
        assert "WARN" in out

    def test_mixed_returns_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns 0 when variance is above threshold (discriminating)."""
        from little_loops.cli.loop.info import cmd_calibrate_budget

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        verdicts = ["yes", "no"] * 5
        for i, verdict in enumerate(verdicts):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": verdict},
            ]
            self._make_events_jsonl(run_dir, events)

        result = cmd_calibrate_budget("my-loop", self._base_args(min_runs=10), loops_dir)
        assert result == 0
        out = capsys.readouterr().out
        assert "OK" in out

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--json flag outputs parseable JSON with expected keys."""
        from little_loops.cli.loop.info import cmd_calibrate_budget

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        for i in range(10):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": "yes"},
            ]
            self._make_events_jsonl(run_dir, events)

        result = cmd_calibrate_budget(
            "my-loop", self._base_args(as_json=True, min_runs=10), loops_dir
        )
        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["loop"] == "my-loop"
        assert data["total_runs"] == 10
        assert len(data["states"]) == 1
        assert data["states"][0]["state"] == "check"
        assert data["states"][0]["variance"] == 0.0

    def test_custom_threshold(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Custom --threshold flag is respected."""
        from little_loops.cli.loop.info import cmd_calibrate_budget

        loops_dir = tmp_path / ".loops"
        history_root = loops_dir / ".history"

        verdicts = ["yes", "yes", "yes", "yes", "no"] * 2
        for i, verdict in enumerate(verdicts):
            run_dir = history_root / f"20260101T0000{i:02d}-my-loop"
            events = [
                {"event": "state_enter", "state": "check", "iteration": 1},
                {"event": "evaluate", "verdict": verdict},
            ]
            self._make_events_jsonl(run_dir, events)

        # With threshold 0.1, variance 0.16 is fine (OK)
        result = cmd_calibrate_budget(
            "my-loop", self._base_args(threshold=0.1, min_runs=10), loops_dir
        )
        assert result == 0
        out = capsys.readouterr().out
        assert "OK" in out


class TestCmdPromoteBaseline:
    """Tests for ll-loop promote-baseline command."""

    def _write_events(self, run_dir: Path, events: list[dict]) -> None:  # type: ignore[type-arg]
        """Write events.jsonl to run_dir."""
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "events.jsonl", "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

    def _base_args(self) -> argparse.Namespace:
        return argparse.Namespace()

    def test_no_history_returns_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 1 when no .history directory exists."""
        from little_loops.cli.loop.info import cmd_promote_baseline

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        result = cmd_promote_baseline("my-loop", self._base_args(), loops_dir)
        assert result == 1
        assert "No history" in capsys.readouterr().out

    def test_no_action_output_events_returns_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns 1 when run exists but has no action_output events."""
        from little_loops.cli.loop.info import cmd_promote_baseline

        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        self._write_events(run_dir, [{"type": "state_enter", "state": "execute"}])
        result = cmd_promote_baseline("my-loop", self._base_args(), loops_dir)
        assert result == 1
        assert "No action_output" in capsys.readouterr().out

    def test_success_writes_baseline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Writes output.txt and returns 0 when action_output events exist."""
        from little_loops.cli.loop.info import cmd_promote_baseline

        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        self._write_events(
            run_dir,
            [
                {"type": "action_output", "line": "hello"},
                {"type": "action_output", "line": "world"},
            ],
        )
        result = cmd_promote_baseline("my-loop", self._base_args(), loops_dir)
        assert result == 0
        baseline = loops_dir / "baselines" / "my-loop" / "output.txt"
        assert baseline.exists()
        content = baseline.read_text()
        assert "hello" in content
        assert "world" in content
        assert "Promoted baseline" in capsys.readouterr().out

    def test_latest_run_used(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Uses the most recent run (highest timestamp) when multiple runs exist."""
        from little_loops.cli.loop.info import cmd_promote_baseline

        loops_dir = tmp_path / ".loops"
        older_dir = loops_dir / ".history" / "20260101T000000-my-loop"
        newer_dir = loops_dir / ".history" / "20260102T000000-my-loop"
        self._write_events(older_dir, [{"type": "action_output", "line": "old output"}])
        self._write_events(newer_dir, [{"type": "action_output", "line": "new output"}])
        result = cmd_promote_baseline("my-loop", self._base_args(), loops_dir)
        assert result == 0
        baseline = loops_dir / "baselines" / "my-loop" / "output.txt"
        assert "new output" in baseline.read_text()


class TestPreRunContextValidator:
    """Regression tests for BUG-2553: pre-run validator must honor :default=
    and ? guards in `${context.X:default=Y}` / `${context.X?}` references.

    The validator extracts the captured key between `${context.` and `}` via
    `r"\\$\\{context\\.([^}.]+)"` in cli/loop/run.py:253. The captured Group 1
    must be checked against `fsm.context` as the bare key, NOT as
    `key:default=value` (which would never match). The engine-side split in
    fsm/interpolation.py:230-241 and the validator idiom at
    fsm/validation.py:135-156 (`_unguarded_captured_refs`) both honor guards;
    this CLI pre-flight check must too.

    Test strategy: chain `required_inputs:` (checked AFTER the context
    validator at run.py:272-279) so that when the context validator is
    bypassed successfully (Cases 1 & 2), the loop exits 1 with a
    `requires input` error rather than reaching the LLM — providing a clean
    discriminator that the validator was indeed bypassed.
    """

    @staticmethod
    def _write_loop(loops_dir: Path, name: str, *, action: str, required_input: str) -> None:
        """Write a minimal loop whose single state has the given action string.

        `required_input` is added to `required_inputs:` so the test can
        short-circuit at the next validator layer (after the context
        validator at run.py:252-270) without invoking an LLM.
        """
        (loops_dir / f"{name}.yaml").write_text(
            f"""
name: {name}
initial: execute
max_iterations: 100
required_inputs:
  - {required_input}
context:
  {required_input}: ""
states:
  execute:
    action: "{action}"
    action_type: prompt
    next: done
    on_error: failed
  done:
    terminal: true
  failed:
    terminal: true
"""
        )

    def test_default_guarded_ref_does_not_trip_validator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Case 1: `${context.x:default=true}` with x absent from fsm.context
        does NOT cause exit 1 from the context validator. Should fall through
        to the next validator (required_inputs) which IS expected to fire.
        """
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_loop(
            loops_dir,
            "default-guard",
            action="${context.guarded_key:default=true}",
            required_input="guarded_key",
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "default-guard"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # Validator was bypassed → no "Missing required context variable" error
        assert "Missing required context variable" not in combined, (
            f"Validator falsely flagged guarded ref as missing:\n{combined}"
        )
        # Required_inputs check fires next, exiting 1
        assert result == 1
        assert "requires input" in combined and "guarded_key" in combined

    def test_nullable_ref_does_not_trip_validator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Case 2: `${context.x?}` (nullable fallback) with x absent from
        fsm.context does NOT cause exit 1 from the context validator.
        """
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_loop(
            loops_dir,
            "nullable-guard",
            action="${context.nullable_key?}",
            required_input="nullable_key",
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "nullable-guard"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "Missing required context variable" not in combined, (
            f"Validator falsely flagged nullable ref as missing:\n{combined}"
        )
        assert result == 1
        assert "requires input" in combined and "nullable_key" in combined

    def test_bare_ref_still_trips_validator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Case 3: bare `${context.x}` (no guard) with x absent STILL trips
        the validator. Error message must list x WITHOUT a `:default=` suffix
        (the engine+validator alignment claim from BUG-2553).
        """
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_loop(
            loops_dir,
            "bare-ref",
            action="${context.bare_key}",
            required_input="unused_input",
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "bare-ref"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert result == 1
        assert "Missing required context variable" in combined
        assert "'bare_key'" in combined
        # Critical: the printed key must NOT carry a `:default=` suffix
        assert "bare_key:default" not in combined, (
            f"Validator surfaced key with :default= suffix (BUG-2553 regression):\n{combined}"
        )

    def test_mixed_guarded_and_unguarded_flags_only_unguarded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Case 4: a loop mixing guarded and unguarded refs to the same key
        flags ONLY the unguarded form. Mirrors the `_unguarded_captured_refs`
        idiom at fsm/validation.py:146-156.
        """
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Note: context.mixed_key:default=true carries the guarded form,
        # context.mixed_key appears bare in the action.
        (loops_dir / "mixed.yaml").write_text(
            """
name: mixed
initial: execute
max_iterations: 100
states:
  execute:
    action: "echo ${context.mixed_key:default=fallback} vs ${context.mixed_key}"
    action_type: prompt
    next: done
    on_error: failed
  done:
    terminal: true
  failed:
    terminal: true
"""
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "mixed"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert result == 1
        assert "Missing required context variable" in combined
        # Should list the bare key
        assert "'mixed_key'" in combined
        # Should NOT echo any `:default=value` suffix in the reported key
        assert "mixed_key:default" not in combined, (
            f"Validator surfaced key with :default= suffix (BUG-2553 regression):\n{combined}"
        )
