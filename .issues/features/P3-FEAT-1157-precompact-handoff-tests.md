---
id: FEAT-1157
type: FEAT
priority: P3
status: deferred
discovered_date: 2026-04-18
discovered_by: issue-size-review
blocked_by: [FEAT-1112, FEAT-1156]
parent: FEAT-1113

relates_to: ['FEAT-1156', 'FEAT-1158']
---

# FEAT-1157: PreCompact Handoff Hook — Integration Tests

## Summary

Write `TestPrecompactHandoff` integration tests in `scripts/tests/test_hooks_integration.py` and review timing-sensitive existing tests that a fresh `ll-continue-prompt.md` write could break.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Acceptance Criteria

- `TestPrecompactHandoff` class added to `scripts/tests/test_hooks_integration.py`, modeled after `TestPrecompactState` (line 1468)
- Test coverage:
  - (a) Hook produces `ll-continue-prompt.md` ≤ 2KB
  - (b) Priority-tier dropping under size pressure with synthetic large input
  - (c) Idempotency: skip when prompt mtime > compacted_at
  - (d) Schema validation: produced file passes `/ll:resume` compatibility check (frontmatter + `## Intent` + `## Next Steps`)
- Timing-sensitive tests reviewed and confirmed (or fixed):
  - `test_hooks_integration.py:434` — `test_reminder_rate_limited_second_call`
  - `test_hooks_integration.py:489` — `test_state_contains_last_reminder_at_after_exit2`
  - `test_hooks_integration.py:531` — `test_fresh_state_with_handoff_file_sets_handoff_complete_false`
- Existing tests unbroken:
  - `scripts/tests/test_subprocess_utils.py:136` — `TestReadContinuationPrompt`
  - `scripts/tests/test_issue_manager.py` — patches `read_continuation_prompt`
  - `scripts/tests/test_worker_pool.py:2202` — patches `read_continuation_prompt`
  - `scripts/tests/test_cli_loop_lifecycle.py:665,715` — continuation prompt display

## Implementation

### New Test Class

Add to `scripts/tests/test_hooks_integration.py`:

```python
class TestPrecompactHandoff:
    """Tests for precompact-handoff.sh output and behavior."""
```

Model after `TestPrecompactState` (line 1468). Each test invokes the shell script with synthetic stdin JSON.

### Timing-Sensitive Test Review

These three tests rely on `ll-continue-prompt.md` mtime comparisons in `context-monitor.sh`:
- **line 434**: `test_reminder_rate_limited_second_call` — a fresh prompt write flips `handoff_complete=true` and silences further reminders. Verify this is intended or isolate the test from `precompact-handoff.sh` output.
- **line 489**: `test_state_contains_last_reminder_at_after_exit2` — same concern.
- **line 531**: `test_fresh_state_with_handoff_file_sets_handoff_complete_false` — if `precompact-handoff.sh` writes the file before `threshold_crossed_at` is set, this test's mtime assumptions may fail.

For each: read the test, understand the mtime assumption, confirm whether an auto-written prompt (from the new hook) would break or correctly satisfy the test.

## Files to Modify

- `scripts/tests/test_hooks_integration.py` — add `TestPrecompactHandoff` class; review lines 434, 489, 531

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- No `TestPrecompactHandoff` class in `scripts/tests/test_hooks_integration.py` ✓
- Blocked by FEAT-1156 (precompact-handoff.sh doesn't exist yet) ✓
- Feature not yet implemented ✓

## References

- Depends on: FEAT-1156 (hook must exist before these tests can pass)
- Docs: FEAT-1158

## Session Log
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

## Verification Notes

**Verdict**: DEFERRED (architecture supersession) — Verified 2026-05-14

This issue and its sibling series are **superseded by the hook-intent abstraction (FEAT-1116, completed)** and the follow-on series FEAT-1448–1460 (mostly completed). The implementation contracts in this file target `hooks/scripts/*.sh` shell scripts which are no longer the canonical hook layer.

Canonical pattern going forward:

- Python intent handlers under `scripts/little_loops/hooks/<intent>.py`
- Per-host adapters under `hooks/adapters/<host>/` (e.g., `claude-code/`, `opencode/`) that envelope host events into `LLHookEvent` and dispatch to `main_hooks()`
- Prompt text files under `hooks/prompts/` referenced from `hooks/hooks.json`

Parent epics are deferred: **FEAT-1113** (precompact auto-handoff) and **FEAT-1159** (session-event-capture + sessionstart-injection). The headless-mode rationale for FEAT-1113 explicitly notes the FSM signal path already provides automatic handoff.

**To resurrect**: rewrite implementation steps to author a new intent handler + adapter wiring rather than a `hooks/scripts/*.sh` script. Re-validate line anchors in referenced docs (`docs/ARCHITECTURE.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/SESSION_HANDOFF.md`) which have shifted since the recent hook-intent doc commits.

Moving to `.issues/deferred/` mirroring parents FEAT-1113 / FEAT-1159.
