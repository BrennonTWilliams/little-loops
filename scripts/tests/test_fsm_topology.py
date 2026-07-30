"""Tests for the FSM static-topology JSON emitter (fsm/topology.py).

Covers:
- topology_dict: exact JSON for an inline loop exercising next / on_yes /
  on_no / on_error / on_maintain ($current self-edge) / route table /
  extra_routes / terminal+failure flags / ${...} dynamic target / sub-loop
  state / loop-level on_max_steps, plus action_type declared-vs-heuristic.
- load_fsm: import/flow/fragment resolution happens before parsing.
- main(): exit codes and stdout/stderr contract.
- Smoke test: real-loop topology for loops/autodev.yaml.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from little_loops.fsm.topology import load_fsm, main, topology_dict

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip())
    return path


INLINE_LOOP = """\
    name: topo-test
    initial: start
    on_max_steps: done
    states:
      start:
        action: /analyze
        on_yes: review
        on_no: start
        on_error: failed_step
        on_maintain: $current
        on_custom_verdict: review
      review:
        action: echo review
        route:
          "yes": done
          "no": fix
          _: fix
          _error: failed_step
      fix:
        action_type: prompt
        action: fix things
        next: "${next_state}"
      sub:
        loop: child-loop
        next: done
      done:
        terminal: true
      failed_step:
        terminal: true
        failure: true
"""

EXPECTED_TOPOLOGY = {
    "loop": "topo-test",
    "states": [
        {
            "id": "start",
            "action_type": "slash_command",
            "terminal": False,
            "failure": False,
            "sub_loop": None,
        },
        {
            "id": "review",
            "action_type": "shell",
            "terminal": False,
            "failure": False,
            "sub_loop": None,
        },
        {
            "id": "fix",
            "action_type": "prompt",
            "terminal": False,
            "failure": False,
            "sub_loop": None,
        },
        {
            "id": "sub",
            "action_type": "shell",
            "terminal": False,
            "failure": False,
            "sub_loop": "child-loop",
        },
        {
            "id": "done",
            "action_type": "shell",
            "terminal": True,
            "failure": False,
            "sub_loop": None,
        },
        {
            "id": "failed_step",
            "action_type": "shell",
            "terminal": True,
            "failure": True,
            "sub_loop": None,
        },
    ],
    "edges": [
        {"from": "start", "to": "review", "kind": "on_yes", "verdict": None},
        {"from": "start", "to": "start", "kind": "on_no", "verdict": None},
        {"from": "start", "to": "failed_step", "kind": "on_error", "verdict": None},
        {"from": "start", "to": "start", "kind": "on_maintain", "verdict": None},
        {
            "from": "start",
            "to": "review",
            "kind": "extra_route",
            "verdict": "custom_verdict",
        },
        {"from": "review", "to": "done", "kind": "route", "verdict": "yes"},
        {"from": "review", "to": "fix", "kind": "route", "verdict": "no"},
        {"from": "review", "to": "fix", "kind": "route", "verdict": "_"},
        {"from": "review", "to": "failed_step", "kind": "route", "verdict": "_error"},
        {"from": "sub", "to": "done", "kind": "next", "verdict": None},
        {"from": "sub", "to": "child-loop", "kind": "loop", "verdict": None},
        {"from": None, "to": "done", "kind": "on_max_steps", "verdict": None},
    ],
    "dynamic_edges": [
        {"from": "fix", "kind": "next", "expr": "${next_state}"},
    ],
}


class TestTopologyDict:
    def test_inline_loop_exact_json(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "loop.yaml", INLINE_LOOP)
        assert topology_dict(load_fsm(path)) == EXPECTED_TOPOLOGY

    def test_on_success_on_failure_aliases_collapse(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "loop.yaml",
            """\
            name: alias-test
            initial: a
            states:
              a:
                action: echo hi
                on_success: b
                on_failure: c
              b:
                terminal: true
              c:
                terminal: true
            """,
        )
        kinds = {(e["from"], e["to"], e["kind"]) for e in topology_dict(load_fsm(path))["edges"]}
        assert ("a", "b", "on_yes") in kinds
        assert ("a", "c", "on_no") in kinds

    def test_flow_shorthand_resolved_before_parsing(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "loop.yaml",
            """\
            name: flow-test
            initial: one
            flow:
              - one
              - two
              - done
            state_defs:
              one:
                action: echo one
              two:
                action: echo two
              done:
                terminal: true
            """,
        )
        topo = topology_dict(load_fsm(path))
        assert [s["id"] for s in topo["states"]] == ["one", "two", "done"]
        assert {tuple(sorted(e.items())) for e in topo["edges"]} == {
            tuple(sorted({"from": "one", "to": "two", "kind": "next", "verdict": None}.items())),
            tuple(sorted({"from": "two", "to": "done", "kind": "next", "verdict": None}.items())),
        }


class TestMain:
    def test_success_prints_json_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write(tmp_path, "loop.yaml", INLINE_LOOP)
        monkeypatch.setattr(sys, "argv", ["topology", str(path)])
        assert main() == 0
        out = capsys.readouterr().out
        assert json.loads(out) == EXPECTED_TOPOLOGY

    def test_missing_file_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["topology", str(tmp_path / "nope.yaml")])
        assert main() == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "not found" in captured.err

    def test_unparseable_yaml_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write(tmp_path, "bad.yaml", "states: [unclosed\n")
        monkeypatch.setattr(sys, "argv", ["topology", str(path)])
        assert main() == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "ERROR" in captured.err

    def test_non_mapping_yaml_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write(tmp_path, "scalar.yaml", "just a string\n")
        monkeypatch.setattr(sys, "argv", ["topology", str(path)])
        assert main() == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "ERROR" in captured.err


class TestAutodevSmoke:
    def test_autodev_topology(self) -> None:
        path = LOOPS_DIR / "autodev.yaml"
        topo = topology_dict(load_fsm(path))

        state_ids = {s["id"] for s in topo["states"]}
        assert len(topo["states"]) == 73

        # Every edge endpoint is a known state id, or the target of a
        # declared sub-loop (`loop:`) cross-graph edge. `from` may be null
        # only on loop-level limit edges.
        sub_loop_names = {s["sub_loop"] for s in topo["states"] if s["sub_loop"]}
        for edge in topo["edges"]:
            if edge["from"] is not None:
                assert edge["from"] in state_ids, edge
            else:
                assert edge["kind"] in ("on_max_steps", "on_max_iterations"), edge
            assert edge["to"] in state_ids or edge["to"] in sub_loop_names, edge

        for dyn in topo["dynamic_edges"]:
            assert dyn["from"] is None or dyn["from"] in state_ids, dyn
            assert "${" in dyn["expr"], dyn
