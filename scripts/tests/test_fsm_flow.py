"""Tests for FSM loop linear-mode shorthand via ``flow:`` (ENH-552).

Tests cover:
- resolve_flow: bare names, ternary entries, terminal states, state_defs merging,
  mutual exclusion with states, malformed ternary, no-op when absent.
- Integration with load_and_validate (KNOWN_TOP_LEVEL_KEYS, no spurious warnings).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from little_loops.fsm.fragments import resolve_flow
from little_loops.fsm.validation import load_and_validate


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip())
    return path


# ---------------------------------------------------------------------------
# resolve_flow unit tests
# ---------------------------------------------------------------------------


class TestResolveFlowUnit:
    def test_no_flow_field_returns_unchanged(self) -> None:
        data = {"name": "foo", "initial": "a", "states": {"a": {"action": "x"}}}
        result = resolve_flow(data)
        assert result == data

    def test_flow_overrides_states(self) -> None:
        data = {
            "name": "override",
            "initial": "a",
            "flow": ["a", "done"],
            "states": {"a": {"action": "old"}, "old_state": {"action": "x"}},
        }
        result = resolve_flow(data)
        assert "old_state" not in result["states"]
        assert "a" in result["states"]
        assert "done" in result["states"]

    def test_bare_names_expand_to_next(self) -> None:
        data = {
            "name": "linear",
            "initial": "start",
            "flow": ["start", "middle", "end"],
        }
        result = resolve_flow(data)
        assert "states" in result
        assert "flow" not in result
        assert result["states"]["start"]["next"] == "middle"
        assert result["states"]["middle"]["next"] == "end"
        assert result["states"]["end"].get("terminal") is True

    def test_ternary_expands_to_on_yes_on_no(self) -> None:
        data = {
            "name": "ternary",
            "initial": "scan",
            "flow": ["scan", "check?done:retry", "done"],
        }
        result = resolve_flow(data)
        assert result["states"]["check"]["on_yes"] == "done"
        assert result["states"]["check"]["on_no"] == "retry"
        assert result["states"]["scan"]["next"] == "check"
        assert result["states"]["done"].get("terminal") is True

    def test_terminal_only_applied_to_last_entry(self) -> None:
        data = {
            "name": "multi",
            "initial": "a",
            "flow": ["a", "b", "c", "done"],
        }
        result = resolve_flow(data)
        for name in ("a", "b", "c"):
            assert "terminal" not in result["states"][name]
        assert result["states"]["done"].get("terminal") is True

    def test_state_defs_merged_into_skeletons(self) -> None:
        data = {
            "name": "defs",
            "initial": "scan",
            "flow": ["scan", "check?done:retry", "done"],
            "state_defs": {
                "scan": {"prompt": "Look for issues", "action": "scan-code"},
                "check": {"evaluate": {"type": "exit_code"}},
            },
        }
        result = resolve_flow(data)
        scan = result["states"]["scan"]
        assert scan["prompt"] == "Look for issues"
        assert scan["action"] == "scan-code"
        assert scan["next"] == "check"

        check = result["states"]["check"]
        assert check["evaluate"] == {"type": "exit_code"}
        assert check["on_yes"] == "done"
        assert check["on_no"] == "retry"

    def test_state_defs_not_in_result(self) -> None:
        data = {
            "name": "clean",
            "initial": "a",
            "flow": ["a", "done"],
            "state_defs": {"a": {"action": "x"}},
        }
        result = resolve_flow(data)
        assert "state_defs" not in result

    def test_flow_not_in_result(self) -> None:
        data = {
            "name": "clean",
            "initial": "a",
            "flow": ["a", "done"],
        }
        result = resolve_flow(data)
        assert "flow" not in result

    def test_malformed_ternary_missing_colon(self) -> None:
        data = {
            "name": "bad",
            "initial": "a",
            "flow": ["a", "check?done"],
        }
        with pytest.raises(ValueError, match="Malformed ternary"):
            resolve_flow(data)

    def test_malformed_ternary_empty_target(self) -> None:
        data = {
            "name": "bad",
            "initial": "a",
            "flow": ["a", "check?done:"],
        }
        with pytest.raises(ValueError, match="Malformed ternary"):
            resolve_flow(data)

    def test_flow_not_a_list_raises(self) -> None:
        data = {
            "name": "bad",
            "initial": "a",
            "flow": "not-a-list",
        }
        with pytest.raises(ValueError, match="flow.*must be a list"):
            resolve_flow(data)

    def test_flow_empty_list_raises(self) -> None:
        data = {
            "name": "bad",
            "initial": "a",
            "flow": [],
        }
        with pytest.raises(ValueError, match="flow.*must contain at least"):
            resolve_flow(data)

    def test_single_entry_flow(self) -> None:
        data = {
            "name": "minimal",
            "initial": "done",
            "flow": ["done"],
        }
        result = resolve_flow(data)
        assert result["states"]["done"].get("terminal") is True


# ---------------------------------------------------------------------------
# resolve_flow integration tests
# ---------------------------------------------------------------------------


class TestResolveFlowIntegration:
    def test_linear_chain_loads_and_validates(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "linear.yaml",
            """
            name: linear-test
            initial: start
            flow: [start, process, done]
            state_defs:
              start:
                action: "echo start"
                next: process
              process:
                action: "echo process"
            """,
        )
        fsm, warnings = load_and_validate(path)
        assert fsm.name == "linear-test"
        assert fsm.initial == "start"
        assert "start" in fsm.states
        assert "process" in fsm.states
        assert "done" in fsm.states
        assert fsm.states["done"].terminal is True

    def test_ternary_chain_loads_and_validates(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "ternary.yaml",
            """
            name: ternary-test
            initial: scan
            flow: [scan, "check?done:scan", done]
            state_defs:
              scan:
                action: "ruff check ."
              check:
                evaluate:
                  type: exit_code
            """,
        )
        fsm, warnings = load_and_validate(path)
        assert fsm.states["check"].on_yes == "done"
        assert fsm.states["check"].on_no == "scan"
        assert fsm.states["scan"].next == "check"

    def test_flow_overrides_inherited_states(self, tmp_path: Path) -> None:
        """flow: overrides states inherited via from: — child redefines the chain."""
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: start
            context:
              shared_var: "hello"
            states:
              start:
                action: "echo start"
                next: done
              done:
                terminal: true
            """,
        )
        child_path = _write(
            tmp_path,
            "child.yaml",
            """
            name: child
            from: parent
            initial: scan
            flow: [scan, "check?done:scan", done]
            state_defs:
              scan:
                action: "scan-code"
              check:
                evaluate:
                  type: exit_code
            """,
        )
        fsm, warnings = load_and_validate(child_path)
        assert fsm.name == "child"
        assert "scan" in fsm.states
        assert "check" in fsm.states
        # Inherited non-state fields survive
        assert fsm.context.get("shared_var") == "hello"

    def test_no_spurious_unknown_key_warnings(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "no-warn.yaml",
            """
            name: no-warn
            initial: start
            flow: [start, done]
            """,
        )
        fsm, warnings = load_and_validate(path)
        unknown_warnings = [w for w in warnings if "Unknown" in w.message]
        assert unknown_warnings == []

    def test_verbose_equivalent_matches_flow(self, tmp_path: Path) -> None:
        flow_path = _write(
            tmp_path,
            "flow.yaml",
            """
            name: compare-flow
            initial: scan
            flow: [scan, "check?done:scan", done]
            state_defs:
              scan:
                action: "ruff check ."
              check:
                evaluate:
                  type: exit_code
            """,
        )
        verbose_path = _write(
            tmp_path,
            "verbose.yaml",
            """
            name: compare-verbose
            initial: scan
            states:
              scan:
                action: "ruff check ."
                next: check
              check:
                evaluate:
                  type: exit_code
                on_yes: done
                on_no: scan
              done:
                terminal: true
            """,
        )
        fsm_flow, _ = load_and_validate(flow_path)
        fsm_verbose, _ = load_and_validate(verbose_path)

        # Same state names and routing
        assert set(fsm_flow.states) == set(fsm_verbose.states)
        assert fsm_flow.states["scan"].next == fsm_verbose.states["scan"].next
        assert fsm_flow.states["check"].on_yes == fsm_verbose.states["check"].on_yes
        assert fsm_flow.states["check"].on_no == fsm_verbose.states["check"].on_no
        assert fsm_flow.states["done"].terminal == fsm_verbose.states["done"].terminal


class TestBuiltinLoopRegression:
    def test_all_builtin_loops_still_load(self) -> None:
        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        yaml_files = sorted(loops_dir.glob("*.yaml"))
        assert len(yaml_files) > 0, "No builtin loops found"
        for loop_path in yaml_files:
            fsm, warnings = load_and_validate(loop_path)
            assert fsm is not None, f"Failed to load {loop_path.name}"
