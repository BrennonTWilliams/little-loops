---
id: FEAT-1264
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-22
discovered_by: issue-size-review
blocked_by:
- FEAT-1156
- FEAT-1262
parent: FEAT-1159
relates_to:
- FEAT-1156
- FEAT-1262
- FEAT-1263
- FEAT-1113
confidence_score: 59
outcome_confidence: 72
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 12
score_change_surface: 22
---

# FEAT-1264: PreCompact Handoff — Event Log Integration

## Summary

Enhance `precompact-handoff.sh` (delivered by FEAT-1156) to read structured event records from `.ll/ll-session-events.jsonl` (delivered by FEAT-1262) instead of reconstructing state from git diff and ll-issues at compaction time. This replaces the FEAT-1156 fallback approach with a complete, accurate session history.

## Parent Issue

Decomposed from FEAT-1159: Continuous Session Event Capture with PreCompact Guarantee and SessionStart Injection

## Current Behavior

`precompact-handoff.sh` (delivered by FEAT-1156) reconstructs session state at compaction time using a fallback strategy: `git diff --name-only HEAD` for files edited, `ll-issues list --status in_progress` for active issue status, and `.ll/loops/` JSON for loop state. This approach misses files edited then reverted, tasks completed mid-session, and errors that were subsequently resolved.

## Expected Behavior

`precompact-handoff.sh` reads `.ll/ll-session-events.jsonl` (delivered by FEAT-1262) when available to produce a more accurate, deduplicated session snapshot: file edits sorted by recency with reverts excluded, only unresolved errors, and net task state where the last event per subject wins. When the event log is absent, the FEAT-1156 fallback path is used unchanged.

## Motivation

FEAT-1156 builds `precompact-handoff.sh` using a fallback strategy: `git diff --name-only HEAD` for files edited, `ll-issues list --status in_progress` for active issues, and `.ll/loops/` JSON for loop state. This is reasonably accurate but has gaps — it can't distinguish files edited early then reverted, tasks completed mid-session, or errors that were subsequently resolved.

With FEAT-1262's event log available, the snapshot builder can group events by type, deduplicate file edits, filter resolved errors, and produce a more accurate priority-tiered snapshot without any model involvement.

## Use Case

**Who**: A developer running `ll-auto`, `ll-parallel`, or a long interactive session.

**Context**: After an extended session, Claude Code triggers context compaction. `precompact-handoff.sh` runs before the compaction window closes to produce a session snapshot.

**Goal**: The snapshot accurately reflects what happened — files actually edited (not reverted), errors that remain unresolved, and tasks still in progress.

**Outcome**: The next context window opens with a precise, noise-free summary rather than stale references to reverted files, resolved errors, or completed tasks.

## Acceptance Criteria

- `precompact-handoff.sh` reads `.ll/ll-session-events.jsonl` when available
- File ops section derived from event log (deduplicated, sorted by recency) instead of `git diff --name-only HEAD`
- Error section includes only events where `type=error` with no subsequent `type=error` resolution for the same subject — i.e., unresolved errors only
- Task section reflects net task state (last event per subject wins) rather than a static `ll-issues` snapshot
- Fallback preserved: if `.ll/ll-session-events.jsonl` does not exist (FEAT-1262 not yet active), the FEAT-1156 git-diff/ll-issues approach continues to work unchanged
- Priority-tier size-capping and idempotency from FEAT-1156 remain intact
- Existing `TestPrecompactHandoff` tests (FEAT-1157) pass without modification
- New tests added to `TestPrecompactHandoff` covering event-log-driven path:
  - Snapshot built from synthetic JSONL input (not git diff)
  - Deduplication: multiple Write events for same file → one entry
  - Resolved errors excluded; unresolved errors included
  - Fallback path exercised when JSONL is absent

## Implementation

### Modify: `scripts/little_loops/hooks/pre_compact_handoff.py`

Add event-log read path to `handle()` before the existing fallback. Both the handler file and its adapter are FEAT-1156 deliverables; FEAT-1264 enriches `handle()` with JSONL parsing, deduplication, and error-resolution logic. The handler follows the same `handle(event: LLHookEvent) -> LLHookResult` pattern as `scripts/little_loops/hooks/pre_compact.py`.

```python
# scripts/little_loops/hooks/pre_compact_handoff.py
import json
from pathlib import Path
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.file_utils import atomic_write_json

EVENT_LOG = Path(".ll/ll-session-events.jsonl")

def handle(event: LLHookEvent) -> LLHookResult:
    try:
        if EVENT_LOG.is_file():
            sections = _build_from_event_log(EVENT_LOG)
        else:
            sections = _build_fallback()  # FEAT-1156 fallback: git diff + ll-issues
        Path(".ll/ll-continue-prompt.md").write_text(_render_markdown(sections), encoding="utf-8")
    except Exception:
        return LLHookResult(exit_code=0)
    return LLHookResult(exit_code=2, feedback="[ll] Session snapshot written to .ll/ll-continue-prompt.md")

def _build_from_event_log(log_path: Path) -> dict:
    events = [json.loads(ln) for ln in log_path.read_text().splitlines() if ln.strip()]

    # File edits: last event per subject wins (deduplication; reverts naturally excluded)
    file_edits: dict[str, dict] = {}
    for ev in events:
        if ev.get("type") == "file":
            file_edits[ev["subject"]] = ev

    # Errors: unresolved = last event for that subject is still type=error
    # (error resolution heuristic defined canonically in FEAT-1262 § Event Semantics)
    last_by_subject: dict[str, dict] = {}
    for ev in events:
        last_by_subject[ev["subject"]] = ev
    unresolved_errors = [ev for ev in last_by_subject.values() if ev.get("type") == "error"]

    # Tasks: net state — last event per subject wins
    task_state: dict[str, dict] = {}
    for ev in events:
        if ev.get("type") == "task":
            task_state[ev["subject"]] = ev

    return {"file_edits": list(file_edits.values()), "errors": unresolved_errors, "tasks": list(task_state.values())}
```

The event log schema per FEAT-1262: each line is `{"ts": "...", "type": "file|task|git|error|decision|plan", "op": "...", "subject": "...", "status": "..."}`. The fallback (`_build_fallback()`) is the FEAT-1156 git-diff/ll-issues implementation, untouched.

### Error Resolution Heuristic

The error-resolution heuristic is defined canonically in FEAT-1262's `### Event Semantics` section. This issue is the consumer; cite that schema rather than redefining the rule here. If the heuristic needs to evolve, update FEAT-1262's schema first, then update this consumer to match.

### Size-Capping Compatibility

The event-log path builds the same tiered markdown sections as the fallback path. The existing `wc -c` size-capping and LIFO drop logic (FEAT-1156) applies to both paths without modification.

## Integration Map

### Files to Create (FEAT-1156 deliverables, required before FEAT-1264)
- `scripts/little_loops/hooks/pre_compact_handoff.py` — new Python hook handler; `handle()` is FEAT-1264's primary target
- `hooks/adapters/claude-code/precompact-handoff.sh` — thin 3-line passthrough: `echo "$INPUT" | python -m little_loops.hooks pre_compact_handoff`

### Files to Modify
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` at line ~82: add `"pre_compact_handoff": pre_compact_handoff.handle`; update `_USAGE` string (currently lists 6 intents, needs 7th)
- `hooks/hooks.json` — add second PreCompact array entry pointing to `precompact-handoff.sh` after existing `precompact.sh` entry; ordering is load-bearing

### Reads From (runtime)
- `.ll/ll-session-events.jsonl` — FEAT-1262 deliverable; reuse `EventBus.read_events(Path(".ll/ll-session-events.jsonl"))` from `scripts/little_loops/events.py` for malformed-line-safe JSONL parsing
- `.ll/ll-precompact-state.json` — written by `pre_compact.handle()` in `scripts/little_loops/hooks/pre_compact.py`

### Writes To
- `.ll/ll-continue-prompt.md` — session snapshot markdown; use `atomic_write` from `scripts/little_loops/file_utils.py` (not `atomic_write_json`; see pattern in `pre_compact.handle()`)

### Tests
- `scripts/tests/test_pre_compact.py` — unit test pattern to follow: `_event()` helper + `monkeypatch.chdir(tmp_path)` + synthetic JSONL fixture; class `TestHandleHappyPath` (line 28)
- `scripts/tests/test_hooks_integration.py` — adapter integration pattern: `TestPrecompactState` (line 2037); `TestPrecompactHandoff` is the FEAT-1157 deliverable to extend

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_pre_compact_handoff.py` — new dedicated unit test file; follow `test_pre_compact.py` pattern with `_event(intent="pre_compact_handoff")`; add `TestHandleHappyPath` and `TestEventLogPath` classes (dedup, unresolved-errors filter, fallback-when-absent scenarios)
- `scripts/tests/test_hook_intents.py` — add `test_dispatch_pre_compact_handoff_happy_path` (parallel to `test_dispatch_pre_compact_happy_path` at line 273); update `test_dispatch_table_merges_hook_intent_registry` to assert `"pre_compact_handoff" in table`
- `scripts/tests/test_claude_code_adapter.py` — add test in `TestClaudeCodeAdapterIntegration` asserting second `PreCompact` array entry in `hooks/hooks.json` points to `precompact-handoff.sh`
- `scripts/tests/test_hooks_integration.py` lines 435, 490, 532 — `test_reminder_rate_limited_second_call`, `test_state_contains_last_reminder_at_after_exit2`, `test_fresh_state_with_handoff_file_sets_handoff_complete_false` — confirm `tmp_path` isolation holds after new handler writes `ll-continue-prompt.md`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — adapter directory listing under `hooks/adapters/claude-code/`; add `precompact-handoff.sh` (owned by FEAT-1158)
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — "Lifecycle at a Glance" table and `## PreCompact` section; add second PreCompact row for `precompact-handoff.sh` → `pre_compact_handoff.handle` (owned by FEAT-1158)
- `docs/guides/SESSION_HANDOFF.md` — "How It Works" section; document PreCompact auto-trigger writing `ll-continue-prompt.md` (owned by FEAT-1158)
- `docs/development/TROUBLESHOOTING.md` — chmod block, manual invocation example, and lock timeout list; add `precompact-handoff.sh` entries (owned by FEAT-1158)
- `docs/reference/API.md` — adapter enumeration paragraph; add `precompact-handoff.sh` (owned by FEAT-1158)
- `docs/claude-code/write-a-hook.md` — adapter file list (line 180); add `precompact-handoff.sh` (owned by FEAT-1158)
- `commands/handoff.md` — `## Integration` section; mention PreCompact auto-trigger path (owned by FEAT-1158)
- `skills/configure/areas.md` — hook audit table; add second PreCompact row (owned by FEAT-1158)

### Key Utilities
- `scripts/little_loops/hooks/types.py` — `LLHookEvent`, `LLHookResult`
- `scripts/little_loops/events.py` — `EventBus.read_events(path)` returns `list[LLEvent]`; handles blank lines and `json.JSONDecodeError` per line
- `scripts/little_loops/file_utils.py` — `acquire_lock()`, `atomic_write()`, `atomic_write_json()`

## Files to Modify

- `scripts/little_loops/hooks/pre_compact_handoff.py` — new file (FEAT-1156 deliverable); add `handle()` with event-log read path and fallback; FEAT-1264 enriches with JSONL parsing, deduplication, and error-resolution logic
- `scripts/little_loops/hooks/__init__.py` — add `"pre_compact_handoff": pre_compact_handoff.handle` to `_dispatch_table()` (currently at line ~82); update `_USAGE` string; update module-level docstring "Today it routes:" bullet list from 6 to 7 intents
- `hooks/adapters/claude-code/precompact-handoff.sh` — new 3-line passthrough adapter (FEAT-1156 deliverable): `echo "$INPUT" | python -m little_loops.hooks pre_compact_handoff`
- `hooks/hooks.json` — add second PreCompact array entry after existing `precompact.sh` entry; ordering is load-bearing

## Files to Add Tests To

- `scripts/tests/test_pre_compact.py` — add unit tests following `TestHandleHappyPath` pattern: `monkeypatch.chdir(tmp_path)`, write synthetic `.ll/ll-session-events.jsonl`, call `pre_compact_handoff.handle(LLHookEvent(host="claude-code", intent="pre_compact_handoff"))`
- `scripts/tests/test_hooks_integration.py` — extend `TestPrecompactHandoff` (FEAT-1157 deliverable; see `TestPrecompactState` at line 2037 for subprocess/adapter pattern) with event-log-path tests:
  - Snapshot built from synthetic JSONL input (not git diff)
  - Deduplication: multiple Write events for same file → one entry
  - Resolved errors excluded; unresolved errors included
  - Fallback path exercised when JSONL is absent

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_pre_compact_handoff.py` — create new dedicated unit test file (do NOT add to `test_pre_compact.py` — that file tests `pre_compact.handle()`, a separate handler); follow `test_pre_compact.py` pattern exactly: `_event()` factory with `intent="pre_compact_handoff"`, `TestHandleHappyPath`, `TestEventLogPath` (synthetic JSONL fixture, dedup, unresolved-errors, fallback)
- `scripts/tests/test_hook_intents.py` — (1) add `test_dispatch_pre_compact_handoff_happy_path` in `TestHooksMainModule`, modeled on `test_dispatch_pre_compact_happy_path` (line 273); (2) add `assert "pre_compact_handoff" in table` to `test_dispatch_table_merges_hook_intent_registry`
- `scripts/tests/test_claude_code_adapter.py` — add method to `TestClaudeCodeAdapterIntegration` asserting second `PreCompact` array entry exists in `hooks/hooks.json` and references `precompact-handoff.sh`

## Scope Boundary

This issue modifies only `pre_compact_handoff.py`. It does NOT modify:
- `session_capture` / `session-capture.sh` (FEAT-1262) — that issue owns the writer
- `session_start_inject` / `session-start-inject.sh` (FEAT-1263) — that issue owns the injector
- The FEAT-1156 fallback path (`_build_fallback()`) — it must remain working unchanged

**MVP Designation** (2026-05-01 audit): FEAT-1264 is the MVP for "reconstruct PreCompact summary at handoff" — the JSONL+jq path defined here. FEAT-1112's SQLite/FTS5-backed reconstruction is a future replacement that reuses the same snapshot-builder API surface (input → markdown sections). Designing the snapshot builder as a stable interface allows the SQLite implementation to swap in without changes to `precompact-handoff.sh` consumers. The error-resolution heuristic lives canonically in FEAT-1262's Event Semantics section.

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `hooks/scripts/precompact-handoff.sh` does not exist (FEAT-1156 not yet delivered) ✓
- `.ll/ll-session-events.jsonl` not produced (FEAT-1262 not yet delivered) ✓
- Both upstream dependencies (FEAT-1156, FEAT-1262) still open — this issue is blocked ✓
- Feature not yet implemented ✓

## References

- Parent: FEAT-1159
- Modifies deliverable from: FEAT-1156 (`pre_compact_handoff.py` + `precompact-handoff.sh` adapter)
- Reads from: FEAT-1262 (`ll-session-events.jsonl`)
- Downstream beneficiary: FEAT-1263 (richer snapshot → richer injection)
- Original vision: FEAT-1159 Component 2 integration notes

## Impact

- **Priority**: P3 — Enhances session snapshot accuracy for long sessions; not blocking but meaningfully improves handoff quality
- **Effort**: Medium — Adds event-log read path to `pre_compact_handoff.handle()` (Python); extends `TestPrecompactHandoff` with new test scenarios
- **Risk**: Low — New path is additive; FEAT-1156 fallback preserved unchanged; isolated to a single script
- **Breaking Change**: No

## Labels

`hooks`, `session-events`, `precompact`, `integration`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's implementation plan references `hooks/scripts/precompact-handoff.sh` as the target file to modify. Per FEAT-1156's Scope Boundary, that path does not exist. FEAT-1156 delivers a Python handler at `scripts/little_loops/hooks/pre_compact_handoff.py` and a 3-line passthrough adapter at `hooks/adapters/claude-code/precompact-handoff.sh` (no logic to modify). The event-log integration code shown in the implementation section (bash `jq` extraction into `FILES_EDITED`, `ERRORS`, etc.) must be rewritten as Python inside `pre_compact_handoff.handle()` in `scripts/little_loops/hooks/pre_compact_handoff.py`. The fallback/primary-path structure and size-capping logic remain as described, just in Python rather than bash.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-16_

**Readiness Score**: 59/100 → STOP — NOT READY
**Outcome Confidence**: 72/100 → MODERATE

### Gaps to Address
- FEAT-1156 must be fully delivered (`pre_compact_handoff.py` + `precompact-handoff.sh`) before implementation can start
- FEAT-1262 must be fully delivered (`.ll/ll-session-events.jsonl` must be populated) before the event-log path can be implemented or tested
- Fix "Files to Modify" section: the target is `scripts/little_loops/hooks/pre_compact_handoff.py` (Python), not `hooks/scripts/precompact-handoff.sh` (bash) — the scope boundary note already documents this correction but the body has not been updated

### Outcome Risk Factors
- **Specification inconsistency** — the "Files to Modify" section and implementation pseudocode reference the wrong file (bash); the Python rewrite is implied by the scope boundary note but not explicit in the implementation steps — correct this before starting to avoid implementing in the wrong place
- **Two hard blockers outstanding** — `pre_compact_handoff.py` (FEAT-1156) and `ll-session-events.jsonl` (FEAT-1262) must both exist before this issue can be implemented or tested

## Status

**Open** | Created: 2026-04-22 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-06-17T00:17:38 - `8f14b8d0-32b9-47cb-993c-65efba894965.jsonl`
- `/ll:refine-issue` - 2026-06-17T00:04:39 - `29ccaf76-4677-49ce-a7cc-916069d28d00.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `582fb982-6866-45ba-b90e-d2cfdc139ff2.jsonl`
- `/ll:format-issue` - 2026-06-16T23:26:53 - `6859bdb6-28b4-4bbd-942d-3775826e1d79.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
