---
id: BUG-1375
type: BUG
priority: P2
status: open
captured_at: 2026-05-06 20:59:54+00:00
completed_at: 2026-05-06T21:43:04Z
discovered_date: 2026-05-06
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1375: `classify_failure` Misses "Prompt is too long" — Treats Context Exhaustion as Real Failure

## Summary

`classify_failure` in `issue_lifecycle.py` has no pattern matching `"prompt is too long"`, so API context-window exhaustion falls through to `FailureType.REAL`. This causes `ll-auto` to open a spurious P1 BUG issue and halt instead of attempting a continuation round.

## Current Behavior

When a `claude -p` subprocess exhausts the context window, the Claude CLI outputs:

```
Prompt is too long
```

`classify_failure` receives this in `error_output`, matches no known pattern, and returns `(FailureType.REAL, "Implementation error")`. `ll-auto` then:
1. Creates a new P1 BUG issue (e.g. BUG-1374) blaming an implementation failure
2. Marks the issue as failed and stops processing

Observed in practice: ENH-1115 implementation ran for ~20 minutes, completed all code and test changes, then hit "Prompt is too long" during the documentation phase. `ll-auto` treated this as a real failure and filed BUG-1374.

## Steps to Reproduce

1. Configure and start `ll-auto` to process a large issue (e.g., one requiring 15–20 min of implementation)
2. `ll-auto` spawns `claude --dangerously-skip-permissions -p <manage-issue prompt>` as a subprocess
3. The subprocess runs until the Claude CLI exhausts the context window
4. Observe: Claude CLI outputs `Prompt is too long` to stderr
5. Observe: `classify_failure` receives this text, matches no known pattern, returns `(FailureType.REAL, "Implementation error")`
6. Observe: `ll-auto` creates a spurious P1 BUG issue and halts processing

## Expected Behavior

`"prompt is too long"` should be classified as `FailureType.TRANSIENT` (or a new `FailureType.CONTEXT_EXHAUSTED`) so that:
1. No spurious BUG issue is created
2. `run_with_continuation` (or the caller) can attempt `--resume` to continue in a fresh context window
3. The failure is logged as a context exhaustion event, not an implementation error

## Motivation

Every context window exhaustion in `ll-auto` currently:
- Creates a spurious P1 BUG issue, polluting the backlog with false positives
- Marks the implementing issue as failed and stops processing
- Discards all completed work (code, tests, documentation) done before exhaustion

Large issues requiring 15–20 minutes of implementation are the most common victims — exactly the high-value issues automation is designed to handle.

## Root Cause

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `classify_failure()` (lines 54-145), `FailureType` enum (lines 43-52)
- **Cause**: `classify_failure()` checks `error_output.lower()` against five sequential pattern lists, returning `(FailureType.TRANSIENT, <reason>)` on the first match. With no match, control reaches the final line and returns `(FailureType.REAL, "Implementation error")`.

Pattern lists currently checked:
- `quota_patterns` — rate limits / 429 / "out of extra usage"
- `network_patterns` — connectivity (502/503/504, ECONNREFUSED, ENOTFOUND, ETIMEDOUT)
- `timeout_patterns` — "timeout", "timed out", "deadline exceeded"
- `resource_patterns` — disk full, OOM, "too many open files"
- `server_error_patterns` — "the server had an error", 529, "overloaded", "api error"

`"prompt is too long"` matches none of these → falls through to `FailureType.REAL`.

### Where `error_output` comes from

In `process_issue_inplace()` (`scripts/little_loops/issue_manager.py` ~line 622):

```python
error_output = result.stderr or result.stdout or "Unknown error"
failure_type, failure_reason_text = classify_failure(error_output, result.returncode)
```

Inside `run_claude_command()` (`scripts/little_loops/subprocess_utils.py`), all raw stderr lines are appended verbatim to `stderr_lines`, while stdout is JSON-decoded (only `assistant` text blocks pass through; `result`/`tool_use` events are skipped at line ~214). The Claude CLI emits `"Prompt is too long"` to stderr on context-window exhaustion — so it lands in `result.stderr` as raw text and reaches `classify_failure()` unmodified.

### Why `run_with_continuation()` doesn't catch it

`run_with_continuation()` (`scripts/little_loops/issue_manager.py:149-242`) only reacts to a cooperative `CONTEXT_HANDOFF: Ready for fresh session` signal in stdout (regex `CONTEXT_HANDOFF_PATTERN` in `subprocess_utils.py:31`, detected via `detect_context_handoff()`). When the Claude CLI itself runs out of context, no handoff signal is emitted — the process just exits non-zero with `"Prompt is too long"` on stderr. `run_with_continuation` breaks out of its loop without continuing, and `process_issue_inplace` then hands the failure to `classify_failure`.

## Proposed Solution

Add `"prompt is too long"` to an appropriate pattern list in `classify_failure`. Two options:

**Option A (minimal)**: Add to `quota_patterns` (or a new `context_patterns` list) → returns `FailureType.TRANSIENT` → existing retry logic applies:
> **Selected:** Option A (minimal) — Exact fit with the 5-block `*_patterns` idiom; both call sites already handle `TRANSIENT` correctly; FSM else-block behavior is explicitly correct for this case (12/12 vs 6/12).

```python
context_patterns = [
    "prompt is too long",
    "context length exceeded",
    "context window",
    "maximum context",
]
if any(pattern in error_lower for pattern in context_patterns):
    return (FailureType.TRANSIENT, "Context window exhausted")
```

**Option B (richer)**: Add `FailureType.CONTEXT_EXHAUSTED` and update callers to attempt `--resume` rather than a cold retry. Requires changes to `issue_manager.py:run_with_continuation` and `ll-auto` caller site.

Option A is sufficient as a quick fix; Option B is the right long-term shape.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-06.

**Selected**: Option A (minimal)

**Reasoning**: Option A is a textbook extension of the existing five `*_patterns` blocks — the `context_patterns` list + `any()` idiom is already used identically five times, both `classify_failure` call sites dispatch on `FailureType.TRANSIENT` without any reason-string matching needed for this fix, and the FSM executor's else-block handling of an unknown-reason `TRANSIENT` is explicitly documented as correct behavior. Option B's `worker_pool` fourth-file gap and the absence of a `--resume` semantic at the FSM action-template level make it a non-trivial design problem that exceeds the "~30 lines" estimate and introduces medium risk with no proportional gain for this bug.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (minimal) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (richer) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- **Option A**: Reuse score 3/3 — 5 existing identical `*_patterns` blocks in `classify_failure()` (lines 70–145); both call sites (`issue_manager.py:624`, `fsm/executor.py:673`) already dispatch on `FailureType.TRANSIENT`; parametrize-tuple test pattern in `TestClassifyFailure` (lines 749–808) is direct copy; no caller changes needed.
- **Option B**: Reuse score 2/3 — `worker_pool._run_with_continuation` (lines 453–465) does not call `classify_failure` at all and would need its own `CONTEXT_EXHAUSTED` branch; FSM `_handle_context_exhausted` would need new behavior (action-level `--resume` has no handler precedent in the existing ~150-line `_handle_rate_limit`); post-loop control-flow path in `run_with_continuation` is a new design, not a natural extension.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — add `context_patterns` list to `classify_failure()` (Option A); for Option B also extend the `FailureType` enum
- `scripts/tests/test_issue_lifecycle.py` — add regression cases to `TestClassifyFailure.test_classify_failure_patterns` parametrize list (lines 746-846)
- `scripts/little_loops/issue_manager.py` — (Option B only) extend `process_issue_inplace()` dispatch (~lines 622-663) and `run_with_continuation()` (lines 149-242) to handle `FailureType.CONTEXT_EXHAUSTED`
- `scripts/little_loops/fsm/executor.py` — (Option B only) extend `_execute_state()` reason-string dispatch (lines 671-690) if `CONTEXT_EXHAUSTED` should map to a new FSM retry handler

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:624` — `process_issue_inplace()` calls `classify_failure()` and dispatches on `FailureType.TRANSIENT` (~lines 626-639) vs `FailureType.REAL` (~lines 641-663, calls `create_issue_from_failure()`)
- `scripts/little_loops/fsm/executor.py:673` — `_execute_state()` calls `classify_failure()` and **branches on the returned reason string** (`"rate limit"`, `"quota"`, `"api server error"`) to pick a retry handler. A new `"Context window exhausted"` reason will fall through to the default reset block — fine for Option A; needs a new `_handle_context_exhausted()` for Option B parity
- `scripts/little_loops/__init__.py:20-24, 83-84` — re-exports `FailureType` and `classify_failure` in package public API; if a new enum variant is added (Option B), no changes here, but downstream importers should be audited
- `scripts/little_loops/parallel/worker_pool.py:749-755` — uses the same `f"{command} --resume"` pattern as `run_with_continuation`; Option B should keep both paths in sync

### Similar Patterns
- `quota_patterns`, `network_patterns`, `timeout_patterns`, `resource_patterns`, `server_error_patterns` in `classify_failure()` — all follow the shape: lowercase string list + `any(p in error_lower for p in <list>)` + early `return (FailureType.TRANSIENT, "<reason>")`. New `context_patterns` should follow the same style
- `server_error_patterns` was added in ENH-1293 (`.issues/completed/P3-ENH-1293-executor-transient-error-retry-and-sub-loop-budget-forwarding.md`) — that PR is the closest precedent for adding a new pattern category to `classify_failure`
- `CONTEXT_HANDOFF_PATTERN` regex in `subprocess_utils.py:31` and `HANDOFF_SIGNAL` in `fsm/signal_detector.py:74` show how cooperative context-exhaustion signals are detected today; Option B could extend either

### Tests
- `scripts/tests/test_issue_lifecycle.py:746-846` — `TestClassifyFailure` class with parametrized fixture `test_classify_failure_patterns`. Add new tuples to the `pytest.mark.parametrize` list following the existing format: `("Prompt is too long", "TRANSIENT", "context")` (the third element is the lowercase substring expected in the returned reason)
- `scripts/tests/test_issue_manager.py:940-1166` — `TestRunWithContinuation`; if Option B is chosen, add cases asserting that `FailureType.CONTEXT_EXHAUSTED` triggers a `--resume` continuation
- `scripts/tests/test_subprocess_utils.py` — exists for `run_claude_command()` and handoff detection; only relevant if Option B extends signal detection

### Documentation
- `docs/reference/API.md` — documents `classify_failure` and `FailureType`; update if a new enum variant is added (Option B)
- `docs/ARCHITECTURE.md` — references failure classification; mention new pattern category if non-trivial
- `docs/guides/SESSION_HANDOFF.md` — describes context-monitor / handoff flow; cross-reference if Option B integrates with continuation
- `CHANGELOG.md` — add Fixed/Changed entry under the next concrete `## [X.Y.Z] - DATE` section (not under `[Unreleased]`)

### Configuration
- N/A

## Implementation Steps

### Option A (minimal — recommended quick fix)

1. Add `context_patterns` block to `classify_failure()` in `scripts/little_loops/issue_lifecycle.py` between `server_error_patterns` and the default fallthrough — follows the exact shape of the surrounding pattern blocks (lowercase strings + `any(p in error_lower ...)` + early return).
2. Add regression cases to `scripts/tests/test_issue_lifecycle.py:TestClassifyFailure.test_classify_failure_patterns` parametrize list — append tuples like `("Prompt is too long", "TRANSIENT", "context")`, `("Context length exceeded for model", "TRANSIENT", "context")`. The third element must appear lowercase in the returned reason string (e.g., reason `"Context window exhausted"`).
3. Run `python -m pytest scripts/tests/test_issue_lifecycle.py::TestClassifyFailure -v` to confirm all parametrized cases pass.
4. Verify behavior in `process_issue_inplace()` (`scripts/little_loops/issue_manager.py:622-663`): `FailureType.TRANSIENT` branch logs and returns without calling `create_issue_from_failure()` — no spurious BUG file is written.
5. Note FSM executor side-effect: `fsm/executor.py:671-690` branches on reason string content; a `"Context window exhausted"` reason falls through to the default reset block (no rate-limit/api-error handler invoked). This is the desired behavior for Option A.

### Option B (richer — long-term shape, only if selected)

6. Add `FailureType.CONTEXT_EXHAUSTED = "context_exhausted"` to the enum in `issue_lifecycle.py:43-52`.
7. Update `classify_failure()` to return `(FailureType.CONTEXT_EXHAUSTED, "Context window exhausted")` for the new patterns.
8. Update `process_issue_inplace()` dispatch in `issue_manager.py` to add a third branch: on `CONTEXT_EXHAUSTED`, invoke a `--resume`-style continuation rather than logging-and-returning.
9. Update `run_with_continuation()` (`issue_manager.py:149-242`): currently it only loops on cooperative `CONTEXT_HANDOFF` stdout signals. Extend it to also continue on a `CONTEXT_EXHAUSTED` post-process classification — re-invoke with `f"{resume_command} --resume"` (matching the pattern in `parallel/worker_pool.py:749-755`).
10. Update FSM executor `_execute_state()` (`fsm/executor.py:671-690`) to branch on `FailureType.CONTEXT_EXHAUSTED` if FSM-driven loops should also resume rather than treat as terminal.
11. Update `docs/reference/API.md` and `docs/guides/SESSION_HANDOFF.md` to describe the new failure type and resume-on-classify flow.
12. Add `TestRunWithContinuation` cases in `scripts/tests/test_issue_manager.py:940-1166` asserting `CONTEXT_EXHAUSTED` triggers `--resume` continuation.

## Impact

- **Severity**: High — every context exhaustion in `ll-auto` currently creates a false BUG issue and drops completed work
- **Effort**: Low (Option A: ~5 lines) / Medium (Option B: ~30 lines + caller changes)
- **Risk**: Low
- **Breaking Change**: No

## Labels

`bug`, `automation`, `context-monitor`, `ll-auto`, `issue-lifecycle`

---

## Resolution

**Fixed** via Option A (minimal): Added `context_patterns` block to `classify_failure()` in `scripts/little_loops/issue_lifecycle.py` between `server_error_patterns` and the default fallthrough. Patterns added: `"prompt is too long"`, `"context length exceeded"`, `"context window"`, `"maximum context"`. Returns `(FailureType.TRANSIENT, "Context window exhausted")` — no spurious BUG issue created, no `create_issue_from_failure()` call triggered.

Four regression test cases added to `TestClassifyFailure.test_classify_failure_patterns` parametrize list. All 34 tests pass.

## Status

**Completed** | Created: 2026-05-06 | Priority: P2

## Related Issues

- BUG-035 (completed): Context monitor hook not visible to Claude in non-interactive mode
- BUG-1374 (open): Spurious failure issue created by this bug
- ENH (to be filed): Parse stream-json result events for accurate token counts
- BUG (to be filed): PostToolUse hook exit 2 feedback unreliable in -p mode

## Session Log
- `/ll:ready-issue` - 2026-05-06T21:41:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/63fad009-7663-49aa-ac6a-4ad5eb77b1de.jsonl`
- `/ll:confidence-check` - 2026-05-06T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c4d0565c-f405-43f9-a3a8-094dac6c0ee8.jsonl`
- `/ll:decide-issue` - 2026-05-06T21:37:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b538b8cd-7293-4e35-8d90-f2fef6cc5e19.jsonl`
- `/ll:refine-issue` - 2026-05-06T21:24:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f57123e2-1986-44c4-ab9f-027c29ad190c.jsonl`
- `/ll:format-issue` - 2026-05-06T21:10:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/291cabfe-e58a-41a8-a54c-5ae0200e8ef1.jsonl`
- `/ll:capture-issue` - 2026-05-06T20:59:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/381e1f9c-a749-4e5e-9040-a1d4e3d3e647.jsonl`
