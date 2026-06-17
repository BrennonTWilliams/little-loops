---
id: FEAT-1157
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: issue-size-review
blocked_by:
- FEAT-1112
- FEAT-1156
parent: FEAT-1113
relates_to:
- FEAT-1156
- FEAT-1158
confidence_score: 72
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 25
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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue adds `TestPrecompactHandoff` to `scripts/tests/test_hooks_integration.py`. FEAT-1262 also adds `TestSessionCapture` to the same file. No logical conflict exists (different test classes), but concurrent edits risk git merge conflicts. If worked in parallel, coordinate line insertions or serialize work on this shared test file.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-16_

**Readiness Score**: 72/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 85/100 → HIGH CONFIDENCE

### Concerns
- `pre_compact_handoff.py` and `precompact-handoff.sh` must be delivered (FEAT-1156) before any test in this class can be run; do not start until FEAT-1156 is merged
- Lines 434, 489, 531 in `test_hooks_integration.py` (rate-limit and mtime tests) need a read-and-decide pass before `TestPrecompactHandoff` is added — the new hook auto-writes `ll-continue-prompt.md`, which may flip `handoff_complete` and break existing mtime assertions; isolate if needed

## Session Log
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `582fb982-6866-45ba-b90e-d2cfdc139ff2.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
