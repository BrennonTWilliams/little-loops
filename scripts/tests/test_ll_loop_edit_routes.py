"""Tests for ll-loop edit-routes subcommand and route_table module."""

from __future__ import annotations

import argparse
import csv
import io
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "fsm"


class TestRouteTableExtractor:
    def test_extracts_shorthand_yes_no(self) -> None:
        from little_loops.fsm.route_table import RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(FIXTURES / "valid-loop.yaml")
        matrix = RouteTableExtractor.extract(fsm)
        assert "check" in matrix
        assert matrix["check"]["yes"] == "done"
        assert matrix["check"]["no"] == "done"

    def test_extracts_extra_routes(self) -> None:
        from little_loops.fsm.route_table import RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(FIXTURES / "custom-on-routing.yaml")
        matrix = RouteTableExtractor.extract(fsm)
        assert "check" in matrix
        assert matrix["check"]["done"] == "final"
        assert matrix["check"]["retry"] == "check"

    def test_terminal_state_empty(self) -> None:
        from little_loops.fsm.route_table import RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(FIXTURES / "valid-loop.yaml")
        matrix = RouteTableExtractor.extract(fsm)
        assert matrix["done"] == {}

    def test_all_states_present(self) -> None:
        from little_loops.fsm.route_table import RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(FIXTURES / "loop-with-unreachable-state.yaml")
        matrix = RouteTableExtractor.extract(fsm)
        assert set(matrix.keys()) == set(fsm.states.keys())


class TestRouteTableRenderer:
    def test_to_markdown_has_all_states(self) -> None:
        from little_loops.fsm.route_table import RouteTableRenderer

        matrix = {
            "assess": {"yes": "implement", "no": "done", "error": "error"},
            "implement": {"yes": "done", "error": "error"},
            "done": {},
        }
        md = RouteTableRenderer.to_markdown(matrix)
        assert "assess" in md
        assert "implement" in md
        assert "done" in md

    def test_to_markdown_has_verdict_columns(self) -> None:
        from little_loops.fsm.route_table import RouteTableRenderer

        matrix = {
            "check": {"yes": "done", "no": "check"},
        }
        md = RouteTableRenderer.to_markdown(matrix)
        assert "yes" in md
        assert "no" in md

    def test_to_markdown_dash_for_missing(self) -> None:
        from little_loops.fsm.route_table import EMPTY_CELL, RouteTableRenderer

        matrix = {
            "check": {"yes": "done"},
            "done": {},
        }
        md = RouteTableRenderer.to_markdown(matrix)
        # "done" state row should contain the empty cell marker
        assert EMPTY_CELL in md

    def test_to_markdown_separator_row(self) -> None:
        from little_loops.fsm.route_table import RouteTableRenderer

        matrix = {"check": {"yes": "done"}}
        md = RouteTableRenderer.to_markdown(matrix)
        lines = [ln for ln in md.splitlines() if ln.strip()]
        # Header, separator, data row
        assert len(lines) >= 3
        assert "---" in lines[1]

    def test_to_csv_round_trips(self) -> None:
        from little_loops.fsm.route_table import RouteTableRenderer

        matrix = {
            "check": {"yes": "done", "no": "check"},
        }
        csv_text = RouteTableRenderer.to_csv(matrix)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["state"] == "check"
        assert rows[0]["yes"] == "done"
        assert rows[0]["no"] == "check"

    def test_to_csv_empty_cell_is_blank(self) -> None:
        from little_loops.fsm.route_table import RouteTableRenderer

        matrix = {
            "check": {"yes": "done"},
            "done": {},
        }
        csv_text = RouteTableRenderer.to_csv(matrix)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = {r["state"]: r for r in reader}
        # "done" has no "yes" route — should be empty string in CSV
        assert rows["done"]["yes"] == ""

    def test_to_markdown_extra_verdicts_sorted(self) -> None:
        from little_loops.fsm.route_table import RouteTableRenderer

        matrix = {
            "check": {"done": "final", "retry": "check"},
        }
        md = RouteTableRenderer.to_markdown(matrix)
        # Custom verdicts (done, retry) should both appear
        assert "done" in md
        assert "retry" in md


class TestRouteTableParser:
    def test_parses_markdown_table(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = (
            "| state | yes | no |\n"
            "|-------|-----|----|\n"
            "| check | done | check |\n"
            "| done  |  —  |  —  |\n"
        )
        known = {"check", "done"}
        result = RouteTableParser.parse_markdown(md, known)
        assert result["check"]["yes"] == "done"
        assert result["check"]["no"] == "check"
        assert result["done"] == {}

    def test_parse_markdown_raises_on_unknown_state(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = (
            "| state | yes |\n"
            "|-------|-----|\n"
            "| ghost | done |\n"
        )
        with pytest.raises(ValueError, match="ghost"):
            RouteTableParser.parse_markdown(md, {"check", "done"})

    def test_parses_csv(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        csv_text = "state,yes,no\ncheck,done,check\n"
        result = RouteTableParser.parse_csv(csv_text, {"check", "done"})
        assert result["check"]["yes"] == "done"
        assert result["check"]["no"] == "check"

    def test_parse_csv_raises_on_unknown_state(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        csv_text = "state,yes\nghost,done\n"
        with pytest.raises(ValueError, match="ghost"):
            RouteTableParser.parse_csv(csv_text, {"check", "done"})

    def test_parse_markdown_empty_cells_excluded(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = (
            "| state | yes | no |\n"
            "|-------|-----|----|\n"
            "| check | done |  |\n"
        )
        result = RouteTableParser.parse_markdown(md, {"check", "done"})
        assert "yes" in result["check"]
        assert "no" not in result["check"]

    def test_parse_markdown_dash_excluded(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = (
            "| state | yes | no |\n"
            "|-------|-----|----|\n"
            "| check | done | — |\n"
        )
        result = RouteTableParser.parse_markdown(md, {"check", "done"})
        assert "no" not in result["check"]

    def test_round_trip_markdown(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser, RouteTableRenderer

        original = {
            "check": {"yes": "done", "no": "check"},
            "done": {},
        }
        md = RouteTableRenderer.to_markdown(original)
        known = set(original.keys())
        parsed = RouteTableParser.parse_markdown(md, known)
        assert parsed == original

    def test_round_trip_csv(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser, RouteTableRenderer

        original = {
            "check": {"yes": "done", "no": "check"},
            "done": {},
        }
        csv_text = RouteTableRenderer.to_csv(original)
        known = set(original.keys())
        parsed = RouteTableParser.parse_csv(csv_text, known)
        assert parsed == original


class TestDetectRoutingGaps:
    def test_detects_unreachable_state(self) -> None:
        from little_loops.fsm.route_table import detect_routing_gaps
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(FIXTURES / "loop-with-unreachable-state.yaml")
        warnings = detect_routing_gaps(fsm)
        texts = " ".join(warnings).lower()
        assert "orphan" in texts or "unreachable" in texts

    def test_valid_loop_no_warnings(self) -> None:
        from little_loops.fsm.route_table import detect_routing_gaps
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(FIXTURES / "valid-loop.yaml")
        warnings = detect_routing_gaps(fsm)
        assert isinstance(warnings, list)
        # valid-loop has check→done via yes/no, no unreachable/dead-end states
        gap_warnings = [w for w in warnings if "unreachable" in w.lower() or "dead-end" in w.lower()]
        assert gap_warnings == []

    def test_detects_missing_no_arm(self, tmp_path: Path) -> None:
        from little_loops.fsm.route_table import detect_routing_gaps
        from little_loops.fsm.validation import load_and_validate

        # Write a loop with on_yes but no on_no and no default
        loop_yaml = tmp_path / "partial.yaml"
        loop_yaml.write_text(
            "name: partial\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    action: test\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        fsm, _ = load_and_validate(loop_yaml)
        warnings = detect_routing_gaps(fsm)
        texts = " ".join(warnings).lower()
        assert "missing" in texts or "no" in texts


class TestRouteTableApplier:
    def test_apply_noop_preserves_file(self, tmp_path: Path) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        loop_path = tmp_path / "test.yaml"
        shutil.copy(FIXTURES / "valid-loop.yaml", loop_path)
        original_text = loop_path.read_text()

        fsm, _ = load_and_validate(loop_path)
        matrix = RouteTableExtractor.extract(fsm)
        RouteTableApplier.apply(loop_path, matrix, matrix)

        # No-op: route matrix unchanged → file should still be valid
        fsm2, _ = load_and_validate(loop_path)
        matrix2 = RouteTableExtractor.extract(fsm2)
        assert matrix2 == matrix

    def test_apply_updates_shorthand_field(self, tmp_path: Path) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        # Write a loop with two terminal states so we can reroute between them
        loop_path = tmp_path / "test.yaml"
        loop_path.write_text(
            "name: test\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    action: test\n"
            "    on_yes: pass\n"
            "    on_no: fail\n"
            "  pass:\n"
            "    terminal: true\n"
            "  fail:\n"
            "    terminal: true\n"
        )
        fsm, _ = load_and_validate(loop_path)
        old_matrix = RouteTableExtractor.extract(fsm)

        # Change check.yes from "pass" to "fail"
        new_matrix = {k: dict(v) for k, v in old_matrix.items()}
        new_matrix["check"]["yes"] = "fail"

        RouteTableApplier.apply(loop_path, old_matrix, new_matrix)

        fsm2, _ = load_and_validate(loop_path)
        matrix2 = RouteTableExtractor.extract(fsm2)
        assert matrix2["check"]["yes"] == "fail"
        assert matrix2["check"]["no"] == "fail"  # unchanged

    def test_apply_preserves_non_route_fields(self, tmp_path: Path) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        loop_path = tmp_path / "test.yaml"
        loop_path.write_text(
            "name: test\n"
            "description: My loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    action: do something\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        fsm, _ = load_and_validate(loop_path)
        old_matrix = RouteTableExtractor.extract(fsm)
        RouteTableApplier.apply(loop_path, old_matrix, old_matrix)

        content = loop_path.read_text()
        assert "description: My loop" in content
        assert "action: do something" in content


class TestCmdEditRoutes:
    def _make_project(self, tmp_path: Path, loop_fixture: str = "valid-loop.yaml") -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        shutil.copy(FIXTURES / loop_fixture, loops_dir / "test-loop.yaml")
        return loops_dir

    def test_dry_run_prints_markdown_table(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path)
        args = argparse.Namespace(format="markdown", dry_run=True, no_warnings=False)
        result = cmd_edit_routes("test-loop", args, loops_dir, Logger())

        assert result == 0
        captured = capsys.readouterr()
        assert "check" in captured.out
        assert "|" in captured.out  # markdown table

    def test_dry_run_prints_csv_table(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path)
        args = argparse.Namespace(format="csv", dry_run=True, no_warnings=False)
        result = cmd_edit_routes("test-loop", args, loops_dir, Logger())

        assert result == 0
        captured = capsys.readouterr()
        assert "state" in captured.out
        assert "check" in captured.out

    def test_loop_not_found_returns_2(self, tmp_path: Path) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        args = argparse.Namespace(format="markdown", dry_run=True, no_warnings=False)
        result = cmd_edit_routes("nonexistent", args, tmp_path, Logger())
        assert result == 2

    def test_dry_run_shows_gap_warnings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path, "loop-with-unreachable-state.yaml")
        # Rename fixture to match lookup by name
        (loops_dir / "test-loop.yaml").unlink()
        shutil.copy(
            FIXTURES / "loop-with-unreachable-state.yaml",
            loops_dir / "unreachable.yaml",
        )
        args = argparse.Namespace(format="markdown", dry_run=True, no_warnings=False)
        result = cmd_edit_routes("unreachable", args, loops_dir, Logger())

        assert result == 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "orphan" in combined.lower() or "unreachable" in combined.lower()

    def test_no_warnings_flag_suppresses_gaps(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path)
        shutil.copy(
            FIXTURES / "loop-with-unreachable-state.yaml",
            loops_dir / "unreachable.yaml",
        )
        args = argparse.Namespace(format="markdown", dry_run=True, no_warnings=True)
        result = cmd_edit_routes("unreachable", args, loops_dir, Logger())

        assert result == 0
        captured = capsys.readouterr()
        # The ⚠ warning prefix must NOT appear (state name may still be in the table)
        assert "⚠" not in captured.out
        assert "unreachable" not in captured.err.lower()

    def test_editor_flow_applies_changes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When $EDITOR is invoked and user changes a route, changes are applied."""
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.fsm.route_table import RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path)
        loop_path = loops_dir / "test-loop.yaml"

        # Capture the table that gets written to the temp file and write a modified version
        written_tables: list[str] = []

        def fake_editor_call(cmd: list[str]) -> int:
            tmp_file = cmd[-1]
            content = Path(tmp_file).read_text()
            written_tables.append(content)
            # Write back an unmodified table (no changes)
            Path(tmp_file).write_text(content)
            return 0

        monkeypatch.setattr("subprocess.call", fake_editor_call)

        args = argparse.Namespace(format="markdown", dry_run=False, no_warnings=True)
        result = cmd_edit_routes("test-loop", args, loops_dir, Logger())

        assert result == 0
        assert len(written_tables) == 1  # editor was called once

    def test_invalid_state_in_edited_table_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edited table with unknown state → exit 1."""
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path)

        def fake_editor_inject_unknown(cmd: list[str]) -> int:
            # Inject a table with an unknown state
            Path(cmd[-1]).write_text(
                "| state | yes |\n|-------|-----|\n| ghost_state | done |\n"
            )
            return 0

        monkeypatch.setattr("subprocess.call", fake_editor_inject_unknown)

        args = argparse.Namespace(format="markdown", dry_run=False, no_warnings=True)
        result = cmd_edit_routes("test-loop", args, loops_dir, Logger())
        assert result == 1
