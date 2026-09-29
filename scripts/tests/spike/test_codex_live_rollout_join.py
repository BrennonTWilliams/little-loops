"""ENH-3655: fixture-backed evidence for the proposed Codex span join.

This is a research test, not a production coverage selector. A candidate match
does not establish identity when the producer emits no live turn ID.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from little_loops.session_store.sessions import parse_codex_rollout

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "codex"
COMPONENTS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")


@dataclass(frozen=True)
class Span:
    thread_id: str
    turn_id: str
    start: int
    end: int | None
    usage: tuple[int, ...] | None


def _read(name: str) -> list[dict]:
    return [json.loads(line) for line in (FIXTURES / name).read_text().splitlines()]


def _tokens(usage: dict) -> tuple[int, ...]:
    return tuple(usage[key] for key in COMPONENTS)


def _live(name: str) -> tuple[str, tuple[int, ...]]:
    events = _read(name)
    assert [event["type"] for event in events] == [
        "thread.started",
        "turn.started",
        "turn.completed",
    ]
    return events[0]["thread_id"], _tokens(events[-1]["usage"])


def _spans(name: str) -> list[Span]:
    records = _read(name)
    thread_id = records[0]["payload"]["id"]
    opened: dict[str, int] = {}
    usage: dict[str, list[tuple[int, ...]]] = {}
    closed: dict[str, int] = {}
    for record in records:
        payload = record["payload"]
        kind = payload.get("type") if record["type"] == "event_msg" else record["type"]
        turn_id = payload.get("turn_id")
        if kind == "task_started":
            assert turn_id not in opened
            opened[turn_id] = record["ordinal"]
        elif kind == "token_usage_record":
            assert payload["thread_id"] == thread_id
            usage.setdefault(turn_id, []).append(_tokens(payload["usage"]))
        elif kind == "task_complete":
            closed[turn_id] = record["ordinal"]
    return [
        Span(
            thread_id,
            turn_id,
            start,
            closed.get(turn_id),
            tuple(map(sum, zip(*usage[turn_id], strict=True))) if turn_id in usage else None,
        )
        for turn_id, start in sorted(opened.items(), key=lambda pair: pair[1])
    ]


def _candidate_status(
    live: list[tuple[str, tuple[int, ...]]],
    spans: list[Span],
    *,
    capture_complete: bool = True,
    concurrent_resume: bool = False,
    window_changed: bool = False,
) -> str:
    """Check proposed necessary conditions, without certifying a producer join."""
    if not capture_complete or concurrent_resume or window_changed:
        return "overlap_unresolved"
    if len(live) != len(spans):
        return "overlap_unresolved"
    if any(span.end is None or span.usage is None for span in spans):
        return "overlap_unresolved"
    if any(
        thread != span.thread_id or tokens != span.usage
        for (thread, tokens), span in zip(live, spans, strict=True)
    ):
        return "overlap_unresolved"
    return "candidate_consistent_only"


def test_current_producer_resume_refutes_raw_positional_sum() -> None:
    live = [_live("exec-json-v0.158.0.jsonl"), _live("exec-json-resume-v0.158.0.jsonl")]
    spans = _spans("rollout-exec-resume-v0.158.0.jsonl")
    assert len(spans) == 2
    assert spans[0].end is not None and spans[1].end is not None
    assert spans[0].end < spans[1].start
    assert live[0][0] == live[1][0] == spans[0].thread_id == spans[1].thread_id
    assert live[0][1] == spans[0].usage
    assert live[1][1] != spans[1].usage
    assert live[1][1] == tuple(a + b for a, b in zip(spans[0].usage, spans[1].usage, strict=True))
    assert _candidate_status(live, spans) == "overlap_unresolved"


def test_fork_has_own_thread_but_live_total_includes_parent_history() -> None:
    parent = _spans("rollout-exec-resume-v0.158.0.jsonl")
    fork = _spans("rollout-fork-v0.158.0.jsonl")
    live_thread, live_total = _live("exec-json-fork-v0.158.0.jsonl")
    meta = _read("rollout-fork-v0.158.0.jsonl")[0]["payload"]
    assert len(fork) == 1
    assert live_thread == meta["id"] == meta["session_id"] == fork[0].thread_id
    assert meta["forked_from_id"] == parent[0].thread_id != live_thread
    assert meta["history_base"]["thread_id"] == parent[0].thread_id
    assert meta["forked_from_ordinal_exclusive"] == meta["history_base"]["end_ordinal_exclusive"]
    assert meta["forked_from_ordinal_exclusive"] < fork[0].start
    assert live_total != fork[0].usage
    assert live_total == tuple(
        a + b + c for a, b, c in zip(parent[0].usage, parent[1].usage, fork[0].usage, strict=True)
    )
    assert _candidate_status([(live_thread, live_total)], fork) == "overlap_unresolved"


def test_parser_preserves_current_usage_record_and_fork_identity() -> None:
    events = list(parse_codex_rollout(FIXTURES / "rollout-fork-v0.158.0.jsonl"))
    assert all(event.host == "codex" for event in events)
    meta = next(event.payload for event in events if event.type == "session_meta")
    usage = next(event.payload for event in events if event.type == "token_usage_record")
    assert meta["id"] == usage["thread_id"]
    assert meta["forked_from_id"] != meta["id"]
    assert usage["turn_id"] and usage["response_id"]
    assert usage["turn_token_usage"] == usage["usage"]
    assert usage["thread_token_usage"] != usage["usage"]
    for name in (
        "exec-json-v0.158.0.jsonl",
        "exec-json-resume-v0.158.0.jsonl",
        "exec-json-fork-v0.158.0.jsonl",
    ):
        assert all("turn_id" not in event and "response_id" not in event for event in _read(name))


def test_incomplete_extra_ambiguous_and_mismatched_cases_stay_unresolved() -> None:
    live = [_live("exec-json-v0.158.0.jsonl")]
    span = _spans("rollout-exec-resume-v0.158.0.jsonl")[0]
    assert _candidate_status(live, [span]) == "candidate_consistent_only"
    assert (
        _candidate_status(live, [Span(span.thread_id, span.turn_id, span.start, None, span.usage)])
        == "overlap_unresolved"
    )
    assert (
        _candidate_status(live, [Span(span.thread_id, span.turn_id, span.start, span.end, None)])
        == "overlap_unresolved"
    )
    assert _candidate_status(live, [span], capture_complete=False) == "overlap_unresolved"
    assert _candidate_status(live, [span, span]) == "overlap_unresolved"  # extra interactive turn
    assert _candidate_status(live, [span], concurrent_resume=True) == "overlap_unresolved"
    assert _candidate_status(live, [span], window_changed=True) == "overlap_unresolved"
    wrong = tuple(x + 1 for x in live[0][1])
    assert _candidate_status([(live[0][0], wrong)], [span]) == "overlap_unresolved"
    # Equal counts and equal sums leave two same-usage spans exchangeable.
    assert _candidate_status(live * 2, [span, span]) == "candidate_consistent_only"
