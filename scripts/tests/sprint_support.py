"""Shared builders for the ``run-sprint`` generator tests (FEAT-3713)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from little_loops.config import NextConfig
from little_loops.next_arena.candidates import CandidateAssessment, assess_candidates
from little_loops.next_arena.state import ProjectState
from tests.next_arena_candidates_support import issue, ready_issue
from tests.next_arena_support import collect, make_project, write_issue

SETTINGS = NextConfig().resolve_arena_settings()


def feat(n: int, slug: str = "x", prio: str = "P2") -> str:
    return f"features/{prio}-FEAT-{n:03d}-{slug}.md"


def bug(n: int, slug: str = "x", prio: str = "P2") -> str:
    return f"bugs/{prio}-BUG-{n:03d}-{slug}.md"


def write_sprint(
    root: Path,
    name: str,
    issues: Sequence[str] | None = None,
    *,
    extra: Mapping[str, Any] | None = None,
    text: str | bytes | None = None,
    directory: str = ".sprints",
    suffix: str = ".yaml",
    declared_name: Any = ...,
) -> Path:
    """Write ``<directory>/<name><suffix>`` (a sprint definition) and return its path."""
    path = root / directory / f"{name}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        document: dict[str, Any] = {"name": name if declared_name is ... else declared_name}
        document["description"] = f"{name} sprint"
        document["issues"] = list(issues or [])
        document.update(extra or {})
        text = yaml.safe_dump(document, sort_keys=False)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def build(
    root: Path,
    issues: Mapping[str, str],
    sprints: Mapping[str, Sequence[str]] | None = None,
    *,
    config: Mapping[str, Any] | None = None,
) -> Path:
    """Create a project with *issues* (``{relpath-under-.issues: text}``) and sprints."""
    make_project(root, config=config)
    for rel, text in issues.items():
        write_issue(root, rel, text=text)
    for name, members in (sprints or {}).items():
        write_sprint(root, name, members)
    return root


def sprint_state(root: Path, **kwargs: Any) -> ProjectState:
    """Collect a state with the sprint domain (no history) and the shared fixed clock."""
    return collect(root, include_sprints=True, **kwargs)


def assess_sprints(state: ProjectState) -> list[CandidateAssessment]:
    return [a for a in assess_candidates(state, settings=SETTINGS) if a.action_type == "run-sprint"]


def sprint_of(state: ProjectState, name: str) -> CandidateAssessment:
    found = [a for a in assess_sprints(state) if a.target == name]
    assert len(found) == 1, f"expected one run-sprint assessment of {name}, found {len(found)}"
    return found[0]


def run_for(root: Path, name: str, **kwargs: Any) -> CandidateAssessment:
    return sprint_of(sprint_state(root, **kwargs), name)


def ready(extra: Mapping[str, Any] | None = None, **kw: Any) -> str:
    return ready_issue(extra, **kw)


def plain(extra: Mapping[str, Any] | None = None) -> str:
    """An issue without readiness scores (fails the implementation gates)."""
    return issue(dict(extra) if extra is not None else None)


def ids(items: Sequence[Any]) -> list[str]:
    return [getattr(i, "issue_id", i) for i in items]


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)
