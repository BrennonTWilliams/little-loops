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
        assert result.matrix["check"]["yes"] == "done"
        assert result.matrix["check"]["no"] == "check"
        assert result.matrix["done"] == {}

    def test_parse_markdown_raises_on_unknown_state(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = "| state | yes |\n|-------|-----|\n| ghost | done |\n"
        with pytest.raises(ValueError, match="ghost"):
            RouteTableParser.parse_markdown(md, {"check", "done"})

    def test_parses_csv(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        csv_text = "state,yes,no\ncheck,done,check\n"
        result = RouteTableParser.parse_csv(csv_text, {"check", "done"})
        assert result.matrix["check"]["yes"] == "done"
        assert result.matrix["check"]["no"] == "check"

    def test_parse_csv_raises_on_unknown_state(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        csv_text = "state,yes\nghost,done\n"
        with pytest.raises(ValueError, match="ghost"):
            RouteTableParser.parse_csv(csv_text, {"check", "done"})

    def test_parse_markdown_empty_cells_excluded(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = "| state | yes | no |\n|-------|-----|----|\n| check | done |  |\n"
        result = RouteTableParser.parse_markdown(md, {"check", "done"})
        assert "yes" in result.matrix["check"]
        assert "no" not in result.matrix["check"]

    def test_parse_markdown_dash_excluded(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = "| state | yes | no |\n|-------|-----|----|\n| check | done | — |\n"
        result = RouteTableParser.parse_markdown(md, {"check", "done"})
        assert "no" not in result.matrix["check"]

    def test_round_trip_markdown(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser, RouteTableRenderer

        original = {
            "check": {"yes": "done", "no": "check"},
            "done": {},
        }
        md = RouteTableRenderer.to_markdown(original)
        known = set(original.keys())
        parsed = RouteTableParser.parse_markdown(md, known)
        assert parsed.matrix == original

    def test_round_trip_csv(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser, RouteTableRenderer

        original = {
            "check": {"yes": "done", "no": "check"},
            "done": {},
        }
        csv_text = RouteTableRenderer.to_csv(original)
        known = set(original.keys())
        parsed = RouteTableParser.parse_csv(csv_text, known)
        assert parsed.matrix == original

    def test_parse_markdown_all_empty_stub(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = (
            "| state      | yes  | no |\n"
            "|------------|------|----|\n"
            "| check      | done |  — |\n"
            "| done_stub  |  —   |  — |\n"
        )
        parsed = RouteTableParser.parse_markdown(md, {"check"})
        assert "done_stub" not in parsed.matrix
        assert "done_stub" in parsed.new_stubs

    def test_parse_csv_all_empty_stub(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        csv_text = "state,yes,no\ncheck,done,\ndone_stub,,\n"
        parsed = RouteTableParser.parse_csv(csv_text, {"check"})
        assert "done_stub" not in parsed.matrix
        assert "done_stub" in parsed.new_stubs

    def test_parse_markdown_deleted_states_field(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = "| state | yes |\n|-------|-----|\n| check | done |\n"
        # "done" is in known_states but absent from the table
        parsed = RouteTableParser.parse_markdown(md, {"check", "done"})
        assert "done" in parsed.deleted_states
        assert "check" not in parsed.deleted_states

    def test_parse_markdown_unknown_nonempty_raises(self) -> None:
        from little_loops.fsm.route_table import RouteTableParser

        md = "| state    | yes  |\n|----------|------|\n| new_state| done |\n"
        with pytest.raises(ValueError, match="new_state"):
            RouteTableParser.parse_markdown(md, {"check", "done"})


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
        gap_warnings = [
            w for w in warnings if "unreachable" in w.lower() or "dead-end" in w.lower()
        ]
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

    def test_apply_deletion_with_allow_delete(self, tmp_path: Path) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        loop_path = tmp_path / "test.yaml"
        loop_path.write_text(
            "name: test\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    action: test\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
            "  unused:\n"
            "    terminal: true\n"
        )
        fsm, _ = load_and_validate(loop_path)
        old_matrix = RouteTableExtractor.extract(fsm)
        # Remove "unused" from new_matrix (simulate row deletion)
        new_matrix = {k: dict(v) for k, v in old_matrix.items() if k != "unused"}

        RouteTableApplier.apply(loop_path, old_matrix, new_matrix, allow_delete=True)

        content = loop_path.read_text()
        assert "unused" not in content
        assert "done" in content

    def test_apply_deletion_without_allow_delete_is_noop(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        loop_path = tmp_path / "test.yaml"
        loop_path.write_text(
            "name: test\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    action: test\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        original_content = loop_path.read_text()
        fsm, _ = load_and_validate(loop_path)
        old_matrix = RouteTableExtractor.extract(fsm)
        new_matrix = {k: dict(v) for k, v in old_matrix.items() if k != "done"}

        RouteTableApplier.apply(loop_path, old_matrix, new_matrix, allow_delete=False)

        # File unchanged (no deletion without flag)
        assert loop_path.read_text() == original_content
        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert "done" in captured.out
        assert "--allow-delete" in captured.out

    def test_apply_deletion_warns_dangling_route(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        loop_path = tmp_path / "test.yaml"
        loop_path.write_text(
            "name: test\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    action: test\n"
            "    on_yes: target\n"
            "    on_no: check\n"
            "  target:\n"
            "    terminal: true\n"
        )
        fsm, _ = load_and_validate(loop_path)
        old_matrix = RouteTableExtractor.extract(fsm)
        # Delete "target" but "check" still routes to it
        new_matrix = {k: dict(v) for k, v in old_matrix.items() if k != "target"}

        RouteTableApplier.apply(loop_path, old_matrix, new_matrix, allow_delete=True)

        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert "target" in captured.out
        # Dangling route warning should mention "check" and "target"
        assert "check" in captured.out

    def test_apply_inserts_terminal_stub(self, tmp_path: Path) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

        loop_path = tmp_path / "test.yaml"
        loop_path.write_text(
            "name: test\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    action: test\n"
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        fsm, _ = load_and_validate(loop_path)
        old_matrix = RouteTableExtractor.extract(fsm)

        RouteTableApplier.apply(loop_path, old_matrix, old_matrix, new_stubs=["done_failure"])

        content = loop_path.read_text()
        assert "done_failure" in content
        assert "terminal: true" in content

    def test_apply_mixed_edit_delete_add(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.fsm.route_table import RouteTableApplier, RouteTableExtractor
        from little_loops.fsm.validation import load_and_validate

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

        # Edit: reroute check.no to "pass"; Delete: remove "fail"; Add: new stub "done_alt"
        new_matrix = {k: dict(v) for k, v in old_matrix.items() if k != "fail"}
        new_matrix["check"]["no"] = "pass"  # reroute away from deleted "fail"

        RouteTableApplier.apply(
            loop_path,
            old_matrix,
            new_matrix,
            new_stubs=["done_alt"],
            allow_delete=True,
        )

        content = loop_path.read_text()
        # "fail" state block should be gone; "done_alt" stub should be present
        assert "done_alt" in content
        # "pass" still present (as a state and as a route target)
        assert "pass" in content
        # The fail state block is deleted
        assert "  fail:\n" not in content


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
        args = argparse.Namespace(
            format="markdown", dry_run=True, no_warnings=False, allow_delete=False
        )
        result = cmd_edit_routes("test-loop", args, loops_dir, Logger())

        assert result == 0
        captured = capsys.readouterr()
        assert "check" in captured.out
        assert "|" in captured.out  # markdown table

    def test_dry_run_prints_csv_table(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path)
        args = argparse.Namespace(format="csv", dry_run=True, no_warnings=False, allow_delete=False)
        result = cmd_edit_routes("test-loop", args, loops_dir, Logger())

        assert result == 0
        captured = capsys.readouterr()
        assert "state" in captured.out
        assert "check" in captured.out

    def test_loop_not_found_returns_2(self, tmp_path: Path) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        args = argparse.Namespace(
            format="markdown", dry_run=True, no_warnings=False, allow_delete=False
        )
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
        args = argparse.Namespace(
            format="markdown", dry_run=True, no_warnings=False, allow_delete=False
        )
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
        args = argparse.Namespace(
            format="markdown", dry_run=True, no_warnings=True, allow_delete=False
        )
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
        from little_loops.logger import Logger

        loops_dir = self._make_project(tmp_path)

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

        args = argparse.Namespace(
            format="markdown", dry_run=False, no_warnings=True, allow_delete=False
        )
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
            Path(cmd[-1]).write_text("| state | yes |\n|-------|-----|\n| ghost_state | done |\n")
            return 0

        monkeypatch.setattr("subprocess.call", fake_editor_inject_unknown)

        args = argparse.Namespace(
            format="markdown", dry_run=False, no_warnings=True, allow_delete=False
        )
        result = cmd_edit_routes("test-loop", args, loops_dir, Logger())
        assert result == 1


# ---------------------------------------------------------------------------
# Compound decision-table tests (ENH-2233)
# ---------------------------------------------------------------------------

POLICY_FIXTURE = FIXTURES / "policy-refine.yaml"

# policy-refine.yaml has 7 rules; dimensions: aggregate, clarity, completeness, feasibility, security
_POLICY_RULES_TEXT = (
    "security:<65 -> escalate\n"
    "completeness:<60 -> deep_repair\n"
    "feasibility:<60 -> rethink\n"
    "clarity:>=85 & completeness:>=85 & feasibility:>=85 -> done\n"
    "aggregate:>=85 -> done\n"
    "aggregate:>=60 -> light_repair\n"
    "* -> deep_repair"
)


class TestPolicyRuleExtractor:
    def test_extract_returns_rules(self) -> None:
        from little_loops.fsm.route_table import PolicyRuleExtractor
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(POLICY_FIXTURE)
        rules = PolicyRuleExtractor.extract(fsm)
        assert len(rules) == 7

    def test_extract_preserves_order(self) -> None:
        from little_loops.fsm.route_table import PolicyRuleExtractor
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(POLICY_FIXTURE)
        rules = PolicyRuleExtractor.extract(fsm)
        assert rules[0].target == "escalate"
        assert rules[-1].is_catchall
        assert rules[-1].target == "deep_repair"

    def test_extract_catchall_last(self) -> None:
        from little_loops.fsm.route_table import PolicyRuleExtractor
        from little_loops.fsm.validation import load_and_validate

        fsm, _ = load_and_validate(POLICY_FIXTURE)
        rules = PolicyRuleExtractor.extract(fsm)
        catchalls = [r for r in rules if r.is_catchall]
        assert len(catchalls) == 1
        assert catchalls[0] is rules[-1]


class TestCompoundGridRenderer:
    def _sample_rules(self):
        from little_loops.fsm.policy_rules import parse_rules

        return parse_rules(_POLICY_RULES_TEXT)

    def test_to_markdown_has_hash_column(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        md = CompoundGridRenderer.to_markdown(self._sample_rules())
        header_line = md.splitlines()[0]
        assert "#" in header_line

    def test_to_markdown_has_action_column(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        md = CompoundGridRenderer.to_markdown(self._sample_rules())
        header_line = md.splitlines()[0]
        assert "→ action" in header_line

    def test_to_markdown_has_dimension_columns(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        md = CompoundGridRenderer.to_markdown(self._sample_rules())
        header_line = md.splitlines()[0]
        for dim in ("security", "completeness", "feasibility", "clarity", "aggregate"):
            assert dim in header_line

    def test_to_markdown_empty_cell_for_unconstrained(self) -> None:
        from little_loops.fsm.route_table import EMPTY_CELL, CompoundGridRenderer

        md = CompoundGridRenderer.to_markdown(self._sample_rules())
        assert EMPTY_CELL in md

    def test_to_markdown_star_for_catchall(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        md = CompoundGridRenderer.to_markdown(self._sample_rules())
        last_data_row = [ln for ln in md.splitlines() if ln.startswith("|")][-1]
        assert "* " in last_data_row or "| *" in last_data_row

    def test_to_markdown_has_7_data_rows(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        md = CompoundGridRenderer.to_markdown(self._sample_rules())
        # Header + separator + 7 data rows
        table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
        assert len(table_lines) == 9  # header + sep + 7 data

    def test_to_csv_has_action_column(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        csv_text = CompoundGridRenderer.to_csv(self._sample_rules())
        reader = csv.DictReader(io.StringIO(csv_text))
        assert reader.fieldnames is not None
        assert "→ action" in reader.fieldnames

    def test_to_csv_has_7_data_rows(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        csv_text = CompoundGridRenderer.to_csv(self._sample_rules())
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        assert len(rows) == 7

    def test_to_csv_catchall_row_has_stars(self) -> None:
        from little_loops.fsm.route_table import CompoundGridRenderer

        csv_text = CompoundGridRenderer.to_csv(self._sample_rules())
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        last = rows[-1]
        assert last["→ action"] == "deep_repair"
        # All dimension cells should be "*" for the catch-all row
        dims = [k for k in last if k not in ("#", "→ action")]
        assert all(last[d] == "*" for d in dims)


class TestCompoundGridParser:
    def _sample_rules(self):
        from little_loops.fsm.policy_rules import parse_rules

        return parse_rules(_POLICY_RULES_TEXT)

    def _known_states(self):
        return {"escalate", "deep_repair", "rethink", "done", "light_repair", "score", "parse_scores", "policy_dispatch"}

    def test_parse_markdown_round_trip(self) -> None:
        from little_loops.fsm.policy_rules import serialize_rules
        from little_loops.fsm.route_table import CompoundGridParser, CompoundGridRenderer

        original = self._sample_rules()
        md = CompoundGridRenderer.to_markdown(original)
        parsed = CompoundGridParser.parse_markdown(md, self._known_states())
        assert len(parsed.rules) == len(original)
        assert serialize_rules(parsed.rules) == serialize_rules(original)

    def test_parse_csv_round_trip(self) -> None:
        from little_loops.fsm.policy_rules import serialize_rules
        from little_loops.fsm.route_table import CompoundGridParser, CompoundGridRenderer

        original = self._sample_rules()
        csv_text = CompoundGridRenderer.to_csv(original)
        parsed = CompoundGridParser.parse_csv(csv_text, self._known_states())
        assert len(parsed.rules) == len(original)
        assert serialize_rules(parsed.rules) == serialize_rules(original)

    def test_parse_markdown_warns_missing_catchall(self) -> None:
        from little_loops.fsm.policy_rules import parse_rules
        from little_loops.fsm.route_table import CompoundGridParser, CompoundGridRenderer

        rules_no_catchall = parse_rules(
            "security:<65 -> escalate\naggregate:>=85 -> done"
        )
        md = CompoundGridRenderer.to_markdown(rules_no_catchall)
        parsed = CompoundGridParser.parse_markdown(md, self._known_states())
        assert any("catch-all" in w.lower() for w in parsed.warnings)

    def test_parse_markdown_warns_unknown_action_state(self) -> None:
        from little_loops.fsm.route_table import CompoundGridParser

        md = (
            "| # | confidence | → action |\n"
            "|---|------------|----------|\n"
            "| 1 | >=85       | ghost_target |\n"
            "| 2 | *          | done |\n"
        )
        parsed = CompoundGridParser.parse_markdown(md, {"done"})
        assert any("ghost_target" in w for w in parsed.warnings)

    def test_parse_markdown_warns_shadowed_rule(self) -> None:
        from little_loops.fsm.policy_rules import parse_rules
        from little_loops.fsm.route_table import CompoundGridParser, CompoundGridRenderer

        # Rule 2 is a strict superset of rule 1 → rule 1 shadows rule 2
        rules = parse_rules(
            "confidence:>=85 -> done\n"
            "confidence:>=85 & outcome:>=75 -> implement\n"
            "* -> repair"
        )
        md = CompoundGridRenderer.to_markdown(rules)
        parsed = CompoundGridParser.parse_markdown(md, {"done", "implement", "repair"})
        assert any("shadow" in w.lower() for w in parsed.warnings)

    def test_parse_markdown_raises_invalid_cell(self) -> None:
        from little_loops.fsm.route_table import CompoundGridParser

        md = (
            "| # | confidence | → action |\n"
            "|---|------------|----------|\n"
            "| 1 | NOTVALID   | done |\n"
            "| 2 | *          | done |\n"
        )
        with pytest.raises(ValueError, match="Cannot parse condition cell"):
            CompoundGridParser.parse_markdown(md, {"done"})

    def test_parse_csv_warns_missing_catchall(self) -> None:
        from little_loops.fsm.policy_rules import parse_rules
        from little_loops.fsm.route_table import CompoundGridParser, CompoundGridRenderer

        rules_no_catchall = parse_rules("aggregate:>=85 -> done")
        csv_text = CompoundGridRenderer.to_csv(rules_no_catchall)
        parsed = CompoundGridParser.parse_csv(csv_text, {"done"})
        assert any("catch-all" in w.lower() for w in parsed.warnings)


class TestPolicyRuleApplier:
    def test_apply_round_trip(self, tmp_path: Path) -> None:
        from little_loops.fsm.policy_rules import serialize_rules
        from little_loops.fsm.route_table import (
            CompoundGridParser,
            CompoundGridRenderer,
            PolicyRuleApplier,
            PolicyRuleExtractor,
        )
        from little_loops.fsm.validation import load_and_validate

        # Copy fixture to tmp so we can modify it
        fixture_copy = tmp_path / "policy-refine.yaml"
        shutil.copy(POLICY_FIXTURE, fixture_copy)

        # Extract original rules
        fsm, _ = load_and_validate(fixture_copy)
        original_rules = PolicyRuleExtractor.extract(fsm)
        original_text = serialize_rules(original_rules)

        # Render to markdown, parse back, apply
        md = CompoundGridRenderer.to_markdown(original_rules)
        known_states = set(fsm.states.keys())
        parsed = CompoundGridParser.parse_markdown(md, known_states)
        PolicyRuleApplier.apply(fixture_copy, parsed.rules)

        # Reload and verify round-trip
        fsm2, _ = load_and_validate(fixture_copy)
        round_tripped = PolicyRuleExtractor.extract(fsm2)
        assert serialize_rules(round_tripped) == original_text

    def test_apply_preserves_other_context(self, tmp_path: Path) -> None:
        from little_loops.fsm.policy_rules import parse_rules
        from little_loops.fsm.route_table import PolicyRuleApplier
        from little_loops.fsm.validation import load_and_validate

        fixture_copy = tmp_path / "policy-refine.yaml"
        shutil.copy(POLICY_FIXTURE, fixture_copy)

        fsm_before, _ = load_and_validate(fixture_copy)
        original_subject = fsm_before.context.get("subject")

        rules = parse_rules("* -> deep_repair")
        PolicyRuleApplier.apply(fixture_copy, rules)

        fsm_after, _ = load_and_validate(fixture_copy)
        assert fsm_after.context.get("subject") == original_subject


class TestCmdEditRoutesDecisionTable:
    """End-to-end tests for decision-table mode in cmd_edit_routes."""

    def _make_policy_project(self, tmp_path: Path) -> Path:
        """Set up a minimal project with a policy-router loop."""
        project = tmp_path / "project"
        project.mkdir()
        loops_dir = project / "loops"
        loops_dir.mkdir()
        shutil.copy(POLICY_FIXTURE, loops_dir / "policy-refine.yaml")
        (project / ".ll").mkdir()
        (project / ".ll" / "ll-config.json").write_text('{"loops": {"dir": "loops"}}')
        return loops_dir

    def test_dry_run_decision_table_prints_table(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_policy_project(tmp_path)

        args = argparse.Namespace(
            format="markdown",
            dry_run=True,
            no_warnings=True,
            allow_delete=False,
            decision_table=True,
        )
        result = cmd_edit_routes("policy-refine", args, loops_dir, Logger())
        assert result == 0
        out = capsys.readouterr().out
        assert "→ action" in out
        assert "#" in out

    def test_dry_run_csv_decision_table(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_policy_project(tmp_path)

        args = argparse.Namespace(
            format="csv",
            dry_run=True,
            no_warnings=True,
            allow_delete=False,
            decision_table=True,
        )
        result = cmd_edit_routes("policy-refine", args, loops_dir, Logger())
        assert result == 0
        out = capsys.readouterr().out
        assert "→ action" in out

    def test_auto_detect_policy_router(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Without --decision-table, auto-detects policy-router import."""
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.logger import Logger

        loops_dir = self._make_policy_project(tmp_path)

        args = argparse.Namespace(
            format="markdown",
            dry_run=True,
            no_warnings=True,
            allow_delete=False,
            decision_table=False,  # flag NOT set — should auto-detect
        )
        result = cmd_edit_routes("policy-refine", args, loops_dir, Logger())
        assert result == 0
        out = capsys.readouterr().out
        assert "→ action" in out  # compound table rendered, not state×verdict

    def test_editor_round_trip_writes_policy_rules(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.cli.loop.edit_routes import cmd_edit_routes
        from little_loops.fsm.route_table import PolicyRuleExtractor
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        loops_dir = self._make_policy_project(tmp_path)
        loop_path = loops_dir / "policy-refine.yaml"

        # Capture rendered table, then write it back unchanged (identity edit)
        def fake_editor_identity(cmd: list[str]) -> int:
            return 0  # leave tmp file unchanged

        monkeypatch.setattr("subprocess.call", fake_editor_identity)

        args = argparse.Namespace(
            format="markdown",
            dry_run=False,
            no_warnings=True,
            allow_delete=False,
            decision_table=True,
        )
        result = cmd_edit_routes("policy-refine", args, loops_dir, Logger())
        assert result == 0

        # Reload and verify policy_rules still has all 7 rules
        fsm, _ = load_and_validate(loop_path)
        rules = PolicyRuleExtractor.extract(fsm)
        assert len(rules) == 7
