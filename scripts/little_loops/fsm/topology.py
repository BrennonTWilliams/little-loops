"""Emit the static topology of an FSM loop YAML as JSON (fsm-viz contract).

This is the scene map a Three.js visualizer consumes — see
``prototypes/fsm-viz/EVENT-STREAM.md`` section 6 ("Static topology").

Usage::

    python3 -m little_loops.fsm.topology <path-to-loop.yaml>

Prints one JSON object to stdout::

    {
      "loop": "<loop name>",
      "states": [
        {"id": "...", "action_type": "prompt|slash_command|shell|mcp_tool|contract",
         "terminal": false, "failure": false, "sub_loop": null}
      ],
      "edges": [
        {"from": "...", "to": "...", "kind": "...", "verdict": null}
      ],
      "dynamic_edges": [
        {"from": "...", "kind": "...", "expr": "${...}"}
      ]
    }

``import``/``from``/``flow``/``fragment`` syntaxes are resolved (via
``fsm/fragments.py``) before parsing, so the emitted topology reflects the
fully-merged model. Transition values containing ``${...}`` are
runtime-interpolated and statically unresolvable — they are emitted in
``dynamic_edges`` with the raw expression, never in ``edges``.

Exit codes:
    0 - topology emitted on stdout
    1 - file missing, unparseable YAML, or invalid loop model
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from little_loops.fsm.fragments import (
    resolve_flow,
    resolve_fragments,
    resolve_inheritance,
)
from little_loops.fsm.schema import FSMLoop, StateConfig

# Shorthand on_* transition fields, in executor resolution order
# (fsm/executor.py:2055-2103). `on_success`/`on_failure` are YAML aliases
# already collapsed to `on_yes`/`on_no` by StateConfig.from_dict.
_SHORTHAND_KINDS = (
    "on_yes",
    "on_no",
    "on_error",
    "on_partial",
    "on_blocked",
    "on_maintain",
    "on_retry_exhausted",
    "on_rate_limit_exhausted",
    "on_throttle_hard",
)

# Loop-level limit transitions: (attribute, emitted kind).
_LOOP_LEVEL_KINDS = (
    ("on_max_steps", "on_max_steps"),
    ("on_max_iterations", "on_max_iterations"),
)


def _is_dynamic(target: str) -> bool:
    """Return True if the transition target is runtime-interpolated."""
    return "${" in target


def _action_type(state: StateConfig) -> str:
    """Declared action_type, else the executor heuristic (/ ⇒ slash_command)."""
    if state.action_type is not None:
        return state.action_type
    if state.action is not None and state.action.startswith("/"):
        return "slash_command"
    return "shell"


def _state_transitions(state: StateConfig) -> list[tuple[str, str | None, str]]:
    """All transitions out of a state as ``(kind, verdict, target)`` tuples.

    Mirrors the resolution semantics of ``fsm/executor.py:_route``: ``next``
    (unconditional) first, then the ``route:`` table with its verdict keys
    (``_`` = default, ``_error`` = error), then the shorthand ``on_*`` fields,
    then custom ``extra_routes`` verdicts, then the ``loop:`` cross-graph edge.
    """
    out: list[tuple[str, str | None, str]] = []
    if state.next is not None:
        out.append(("next", None, state.next))
    if state.route is not None:
        for verdict, target in state.route.routes.items():
            out.append(("route", verdict, target))
        if state.route.default is not None:
            out.append(("route", "_", state.route.default))
        if state.route.error is not None:
            out.append(("route", "_error", state.route.error))
    for kind in _SHORTHAND_KINDS:
        target = getattr(state, kind)
        if target is not None:
            out.append((kind, None, target))
    for verdict, target in state.extra_routes.items():
        out.append(("extra_route", verdict, target))
    if state.loop is not None:
        out.append(("loop", None, state.loop))
    return out


def load_fsm(path: Path) -> FSMLoop:
    """Load a loop YAML into an FSMLoop with fragments/flow/inheritance resolved."""
    with open(path) as f:
        data: Any = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"loop file must contain a YAML mapping, got {type(data).__name__}")
    data = resolve_inheritance(data, path.parent)
    data = resolve_flow(data)
    data = resolve_fragments(data, path.parent)
    return FSMLoop.from_dict(data)


def topology_dict(fsm: FSMLoop) -> dict[str, Any]:
    """Build the topology JSON dict from a parsed loop model."""
    states = [
        {
            "id": name,
            "action_type": _action_type(state),
            "terminal": bool(state.terminal),
            "failure": bool(state.failure),
            "sub_loop": state.loop,
        }
        for name, state in fsm.states.items()
    ]

    edges: list[dict[str, Any]] = []
    dynamic_edges: list[dict[str, Any]] = []

    # Per-state transitions; "$current" is a self-edge (executor.py:2115-2116).
    transitions: list[tuple[str | None, str, str | None, str]] = [
        (name, kind, verdict, target)
        for name, state in fsm.states.items()
        for kind, verdict, target in _state_transitions(state)
    ]
    # Loop-level limit edges apply from any state -> from is null.
    for attr, kind in _LOOP_LEVEL_KINDS:
        target = getattr(fsm, attr)
        if target is not None:
            transitions.append((None, kind, None, target))

    for from_state, kind, verdict, target in transitions:
        if _is_dynamic(target):
            dynamic_edges.append({"from": from_state, "kind": kind, "expr": target})
            continue
        to_state = from_state if target == "$current" else target
        edges.append({"from": from_state, "to": to_state, "kind": kind, "verdict": verdict})

    return {
        "loop": fsm.name,
        "states": states,
        "edges": edges,
        "dynamic_edges": dynamic_edges,
    }


def main() -> int:
    """Entry point for ``python3 -m little_loops.fsm.topology``."""
    parser = argparse.ArgumentParser(
        prog="python3 -m little_loops.fsm.topology",
        description="Emit the static topology of an FSM loop YAML as JSON.",
    )
    parser.add_argument("loop_yaml", help="Path to the loop YAML file")
    args = parser.parse_args()

    path = Path(args.loop_yaml)
    if not path.is_file():
        print(f"ERROR: loop file not found: {path}", file=sys.stderr)
        return 1
    try:
        fsm = load_fsm(path)
    except (OSError, yaml.YAMLError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: could not load loop {path}: {exc}", file=sys.stderr)
        return 1

    json.dump(topology_dict(fsm), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
