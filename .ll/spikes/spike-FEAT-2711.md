# Spike Plan: FEAT-2711 — compact-summary injection (Option B)

## Context

FEAT-2711's Decision Rationale selected **Option B** (compact-summary
injection via `compact_session()`/`compact_result_for_session()`) over Option A
(host-level `--continue`/`--resume`), because Option A inherits the confirmed
BUG-1385 "most-recent-session" concurrency hazard. But the issue's own
Confidence Check Notes flag that the Proposed Solution / Integration Map /
Acceptance Criteria were never rewritten for Option B and still describe
Option A end-to-end, and that:

> Outcome Risk Factors: No existing test exercises FSM-side session-ID capture
> or compact-summary injection at the state-transition layer — this is a novel
> mechanism within Option B that the current Integration Map (written for
> Option A) does not address.

Two concrete failures this spike must rule out (or confirm):

**(a) Zero precedent** — no FSM/host_runner code path captures a session ID
from a completed invocation today (confirmed by codebase research: neither
`run_claude_command()` nor any `build_streaming()` implementation returns or
threads a session ID; the existing `resume_session=True` callers in
`worker_pool.py`/`issue_manager.py` never capture one either — they just flip
`--continue` and let the host CLI resume "whichever session it considers
current").

**(b) No existing test exercises the risky core** — specifically, whether
`compact_session()` can produce a usable `summary_text` for a session
*immediately* after it finishes (in-process, same FSM state-transition), given
that `_compact_session_conn()` reads exclusively from the `message_events`
table, which is populated only by an explicit backfill step
(`_backfill_messages()`), not written live during a running session.

**Additional risk surfaced during spike scoping** (not yet in the issue's
Outcome Risk Factors, but directly bears on whether Option B is viable at all):
`_backfill_messages()` ingests only `type == "user"` JSONL records into
`message_events`; assistant text lives in a separate `assistant_messages`
table that `_compact_session_conn()` never joins. For a single FSM prompt-state
invocation, the "user" turn *is* the interpolated state prompt (already known
data) — the state's newly-derived understanding (file reads, analysis,
plan/design output) is entirely in the *assistant* turn. If `compact_session()`
is used unmodified, `summary_text` would summarize the prompt that was already
sent, not the reasoning FEAT-2711 wants to carry forward. This spike treats
that as a fourth thing to prove/disprove, since it materially changes Option
B's "reuses already-shipped, tested primitives" cost estimate in the Decision
Rationale.

## Approach

A standalone library + test class that builds the full Option B pipeline in
isolation, without touching FSM production code:

1. **`session_id_capture.py`** — a pure function that parses one line of
   Claude Code `stream-json` output (`type: "system", subtype: "init"`) and
   extracts `session_id`, proving the field is present/parseable in the
   existing event stream `run_claude_command()` already consumes (it currently
   discards it). Fixture-driven — no real host CLI invocation.
2. **`continuity_pipeline.py`** — orchestrates, against a real (temp,
   file-backed) `history.db` via `little_loops.session_store.connect()`:
   `sessions` seed → JSONL backfill (`_backfill_messages` +
   `_backfill_assistant_messages`, called directly, not through the full
   `backfill()` CLI entry point) → `compact_session()` → `compact_result_for_session()`.
   This is the real production code path (Critical files below), not a fake —
   the spike only fakes the LLM summarization call (mocked
   `subprocess.run`, matching the existing `test_compaction.py` pattern) and
   the "just-finished session" JSONL transcript (a small hand-written fixture
   file instead of a live host CLI run).
3. Test class exercises: (i) synchronous same-process backfill+compact works
   with no race (proves/disproves risk b), (ii) `summary_text` from unmodified
   `compact_session()` omits assistant-authored content proving the user-only
   `message_events` gap (the additional risk above), and (iii) an
   isolation-guard regression test.

## Critical files

Read-only references (production contracts the spike must honor, not modify):

- `scripts/little_loops/session_store.py::compact_session` (~line 3444),
  `_compact_session_conn` (~line 3117), `_backfill_messages` (~line 2713),
  `_backfill_assistant_messages` (~line 2765), `connect()`.
- `scripts/little_loops/compaction/result.py::compact_result_for_session`
  (~line 34), `CompactResult`.
- `scripts/little_loops/subprocess_utils.py::run_claude_command` stream-json
  event parser (~lines 434–482) — the `system`/`init` and `result` event
  shapes the session-ID parser must match.
- `scripts/tests/test_compaction.py::TestCompactResult` — LLM-mocking pattern
  (`patch("little_loops.session_store.subprocess.run")` + `_llm_response()`).

New spike paths: `scripts/tests/spike/fsm_continuity_compaction/`.

## Implementation

```
scripts/tests/spike/fsm_continuity_compaction/
├── __init__.py
├── session_id_capture.py     # parse_session_id_from_stream_json(line: str) -> str | None
├── continuity_pipeline.py    # backfill_and_compact(db, session_id, jsonl_path, config) -> CompactResult | None
├── driver.py                 # end-to-end: write a fixture transcript, run the pipeline, print summary_text
└── test_continuity_pipeline.py
```

API sketch:

```python
# session_id_capture.py
def parse_session_id_from_stream_json(line: str) -> str | None:
    """Extract session_id from a system/init stream-json event line, or None."""

# continuity_pipeline.py
def backfill_and_compact(
    db: Path, session_id: str, jsonl_path: Path, *, config: dict | None = None,
) -> CompactResult | None:
    """Seed sessions/message_events/assistant_messages from jsonl_path, then
    compact_session() + compact_result_for_session() — same-process, no
    external ll-session backfill CLI call."""
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_parses_session_id_from_init_event` | Risk (a): zero precedent for session-ID capture — proves the field exists and is parseable from the stream the runner already consumes | behavior |
| `test_backfill_then_compact_same_process_no_race` | Risk (b): unproven synchronous in-process backfill+compact for a just-finished session | behavior |
| `test_compact_summary_omits_assistant_derived_content` | Additional risk: unmodified `compact_session()` summarizes only user turns, not the assistant's derived understanding — documents whether Option B as scoped actually retires FEAT-2711's stated continuity-of-reasoning goal | behavior (expected to demonstrate the gap) |
| `test_spike_does_not_import_fsm_production_modules` | isolation guard — spike must not import `little_loops.fsm.*` | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/fsm_continuity_compaction/ -v
python -m pytest scripts/tests/test_compaction.py -v
python -m pytest scripts/tests/test_session_store.py -v -k "backfill or compact"
```

## Out of Scope

No changes to `fsm/schema.py`, `fsm/runners.py`, `fsm/executor.py`,
`fsm/validation.py`, `subprocess_utils.py`, or any loop YAML. No real host CLI
invocation — session_id parsing and JSONL transcripts are fixture-driven. The
`session_mode`/`SessionModeConfig` schema and FSM wiring stay untouched;
proving the underlying data-pipeline mechanism is the only goal.

## Promotion

On acceptance, promote `session_id_capture.py` (as a small addition to
`run_claude_command()`'s existing stream-json parser) and
`continuity_pipeline.py` (as a new `fsm`-side helper, e.g.
`scripts/little_loops/fsm/session_continuity.py`) in a separate PR, alongside
the actual `session_mode` schema/wiring work the issue's Integration Map
describes for Option A — that Integration Map still needs a full rewrite
against Option B regardless of this spike's outcome.
