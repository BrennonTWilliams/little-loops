"""Shared helpers for the FEAT-3561 phase D candidate/selection tests."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from little_loops.next_arena.actions import action_fingerprint, render_slash, slash_spec_for
from little_loops.next_arena.candidates import Candidate, CandidateAssessment, assess_candidates
from little_loops.next_arena.state import ProjectState
from tests.next_arena_support import collect, issue_text, make_project, write_issue

#: Frontmatter that passes both the readiness (85) and outcome (65) gates.
READY: Mapping[str, Any] = {"confidence_score": 90, "outcome_confidence": 80}

FORMAT_ENTRY = ("/ll:format-issue", "2026-09-01T10:00:00")
VERIFY_ENTRY = ("/ll:verify-issues", "2026-09-02T10:00:00")


def body(
    *,
    effort: str | None = "Small",
    sessions: Iterable[tuple[str, str]] = (),
    extra: str = "",
) -> str:
    """An issue body with an Impact section (effort) and a trailing Session Log."""
    lines = ["# Title", "", "## Summary", "", "Text.", ""]
    if effort is not None:
        lines += ["## Impact", "", "- **Priority**: P3", f"- **Effort**: {effort}", ""]
    if extra:
        lines += [extra, ""]
    entries = list(sessions)
    if entries:
        lines += ["## Session Log"]
        lines += [f"- `{cmd}` - {stamp} - `s.jsonl`" for cmd, stamp in entries]
        lines += [""]
    return "\n".join(lines) + "\n"


def issue(fm: Mapping[str, Any] | None = None, **body_kwargs: Any) -> str:
    """Full issue text from frontmatter and :func:`body` keyword arguments."""
    return issue_text(dict(fm) if fm is not None else None, body(**body_kwargs))


def ready_issue(extra_fm: Mapping[str, Any] | None = None, **body_kwargs: Any) -> str:
    """A ready issue (``READY`` scores) with optional extra frontmatter."""
    return issue({**READY, **(extra_fm or {})}, **body_kwargs)


def project(
    root: Path,
    files: Mapping[str, str],
    *,
    config: Mapping[str, Any] | None = None,
    order: Sequence[str] | None = None,
) -> ProjectState:
    """Write *files* (``{relpath-under-.issues: text}``) and collect with the fixed clock."""
    make_project(root, config=config)
    for rel in order if order is not None else list(files):
        write_issue(root, rel, text=files[rel])
    return collect(root)


def get(
    assessments: Iterable[CandidateAssessment], verb: str, issue_id: str
) -> CandidateAssessment:
    """The assessment of *issue_id* for *verb* (must exist exactly once)."""
    found = [a for a in assessments if a.action_type == verb and a.target == issue_id]
    assert len(found) == 1, f"expected one {verb} assessment of {issue_id}, found {len(found)}"
    return found[0]


def assess(state: ProjectState) -> list[CandidateAssessment]:
    """``assess_candidates`` (kept as a function so tests read declaratively)."""
    return assess_candidates(state)


def fake_candidate(
    verb: str,
    issue_id: str,
    rank: int,
    *,
    action_key: str | None = None,
    root: str = "/proj",
) -> Candidate:
    """A runnable :class:`Candidate` with a complete action for selection tests."""
    key = action_key or ("manage-issue:implement" if verb == "implement-issue" else "refine-issue")
    spec = slash_spec_for(key, issue_id, root)
    return Candidate(
        action_type=verb,
        action_key=key,
        action_fingerprint=action_fingerprint(spec),
        action_spec=spec,
        target=issue_id,
        target_key=f"issue:{issue_id}",
        display_command=render_slash(spec),
        axes={},
        gates={},
        utility=1.0 / rank,
        selection_score=1.0 / rank,
        bucket_rank=rank,
        pressure=None,
        selection_reason=f"rank {rank}",
        resolved_axes=1,
        applicable_axes=1,
        alternates=(),
        evidence={},
    )
