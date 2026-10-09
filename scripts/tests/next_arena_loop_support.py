"""Shared fixtures/helpers for the FEAT-3769 ``run-loop`` tests.

Built-in loops (about 110 definitions, ~2 s to validate) are replaced by a per-test directory
via :func:`isolate_builtins`, so most tests collect a handful of tiny loops instead.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from little_loops.next_arena.candidates import CandidateAssessment, assess_candidates
from little_loops.next_arena.state import ProjectState, collect_project_state
from tests.next_arena_support import AS_OF, make_project

RUN_LOOP = "run-loop"


def loop_yaml(
    name: str,
    *,
    action: str = "echo hello",
    extra: str = "",
    context: Mapping[str, Any] | None = None,
) -> str:
    """A minimal valid, warning-free single-state loop definition."""
    lines = [f"name: {name}", "initial: go", 'scope: ["."]']
    if context:
        lines.append("context:")
        lines.extend(f"  {key}: {json.dumps(value)}" for key, value in context.items())
    if extra:
        lines.append(extra.rstrip("\n"))
    lines += ["states:", "  go:", f"    action: {json.dumps(action)}", "    terminal: true", ""]
    return "\n".join(lines)


def isolate_builtins(monkeypatch: pytest.MonkeyPatch, directory: Path) -> Path:
    """Point every built-in-loop lookup (collection, loader, validation) at *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("little_loops.fsm.loop_paths.get_builtin_loops_dir", lambda: directory)
    monkeypatch.setattr(
        "little_loops.next_arena.loop_state.get_builtin_loops_dir", lambda: directory
    )
    monkeypatch.setattr(
        "little_loops.fsm.validation.reachability.get_builtin_loops_dir", lambda: directory
    )
    monkeypatch.setattr("little_loops.fsm.fragments._BUILTIN_LOOPS_DIR", directory)
    return directory


def write_loop(root: Path, relpath: str, text: str, *, base: str = ".loops") -> Path:
    """Write ``root/<base>/<relpath>`` (parents created) and return the path."""
    path = root / base / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_run(
    root: Path,
    stamp: str,
    logical_name: str,
    state: Mapping[str, Any] | str | list[Any] | None,
    *,
    base: str = ".loops",
) -> Path:
    """Archive one run folder ``<base>/.history/<stamp>-<logical_name>`` with a ``state.json``.

    *state* ``None`` writes no ``state.json``; a string is written verbatim (malformed JSON
    fixtures); anything else is JSON-encoded.
    """
    folder = root / base / ".history" / f"{stamp}-{logical_name}"
    folder.mkdir(parents=True, exist_ok=True)
    if state is not None:
        text = state if isinstance(state, str) else json.dumps(state)
        (folder / "state.json").write_text(text, encoding="utf-8")
    return folder


def completed_run(started: str, status: str = "completed") -> dict[str, Any]:
    """A minimal archived ``state.json`` payload."""
    return {"status": status, "started_at": started}


def loop_project(
    root: Path,
    *,
    config: Mapping[str, Any] | None = None,
) -> Path:
    """An issue-less project root with ``.ll/`` ready for loop fixtures."""
    make_project(root, config=config if config is not None else {"project": {"name": "t"}})
    return root.resolve()


def loop_state(root: Path, **kwargs: Any) -> ProjectState:
    """Collect the loop domain (and issues) with the fixed test clock."""
    kwargs.setdefault("as_of", AS_OF)
    kwargs.setdefault("include_loops", True)
    return collect_project_state(root, **kwargs)


def run_loop_assessments(state: ProjectState) -> dict[str, CandidateAssessment]:
    """``run-loop`` assessments keyed by exact command target."""
    return {a.target: a for a in assess_candidates(state) if a.action_type == RUN_LOOP}
