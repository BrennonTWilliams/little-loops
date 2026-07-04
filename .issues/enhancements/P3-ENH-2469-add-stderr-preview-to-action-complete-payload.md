---
id: ENH-2469
title: "Add `stderr_preview` field to FSM `action_complete` event payload; surface shell-action stderr to operators"
type: ENH
status: done
priority: P3
captured_at: '2026-07-02T23:30:00Z'
discovered_date: '2026-07-02'
discovered_by: manual
relates_to:
- BUG-2468
- BUG-1640
- BUG-1815
labels:
- enhancement
- fsm
- observability
- shell-actions
- silent-failures
---

# ENH-2469: Add `stderr_preview` field to FSM `action_complete` event payload; surface shell-action stderr to operators

## Summary

The FSM executor's `action_complete` event currently exposes only
`output_preview` (last 2000 chars of stdout). Stderr from shell
actions is captured into `self.captured[state.capture].stderr` only
when the state declares `capture:` — and most shell-action states
don't. The result: when a shell action crashes silently (e.g., a
Python heredoc with an uncaught `SyntaxError`), neither the event
log nor the human-readable post-mortem contains the actual error
message. The failure looks like `exit_code: 1, output_preview: null`
with no diagnostic.

## Motivation

Discovered while investigating BUG-2468 (brainstorm `dedup_novelty`
silent crash). A brainstorm run completed in 3m 2s with
`Loop completed: done`, but `ideas.jsonl` and `brainstorm.md` were
0 bytes. `dedup_novelty` exited with code 1 in 201 ms, `output_preview`
was `null`, and the event stream contained no trace of the actual
Python exception. The crash trigger remains an informed guess
because we have no stderr to read.

This affects **every loop using shell actions**: brainstorm,
qa-pipeline, prompt-across-issues, rn-implement, etc. Brainstorm
is the most recent victim, not the only one.

## Current Behavior

`scripts/little_loops/fsm/executor.py:1285-1307` emits `action_complete`:

```python
preview = result.output[-2000:].strip() if result.output else None
payload: dict[str, Any] = {
    "exit_code": result.exit_code,
    "duration_ms": result.duration_ms,
    "output_preview": preview,
    "is_prompt": action_mode == "prompt",
}
```

`result.stderr` is captured into `self.captured[state.capture].stderr` (line 1313) **only if the state declares `capture:`**. Most shell-action states don't. Stderr is otherwise lost.

The combined `output + stderr` is read by `classify_failure` at line 1157 for rate-limit / api-error detection, but that is an internal classification — it does not surface the stderr to the event log or to the operator.

## Expected Behavior

Every `action_complete` event payload includes a `stderr_preview` field:

- `stderr_preview`: last 2000 chars of `result.stderr`, stripped, or `None` if stderr was empty.
- The field is additive — existing consumers of `output_preview` are unaffected.
- When a shell action crashes silently, the operator can inspect `events.jsonl` and see the actual error message.

## Proposed Solution

### Primary: additive `stderr_preview` field

Edit `scripts/little_loops/fsm/executor.py:1285-1307`:

```python
preview = result.output[-2000:].strip() if result.output else None
stderr_preview = result.stderr[-2000:].strip() if result.stderr else None
payload: dict[str, Any] = {
    "exit_code": result.exit_code,
    "duration_ms": result.duration_ms,
    "output_preview": preview,
    "stderr_preview": stderr_preview,  # NEW
    "is_prompt": action_mode == "prompt",
}
```

The capture dict at line 1310-1316 is unchanged (still records stderr when capture mode is set; this is now a redundancy).

### Fallback (if additive field is rejected for schema reasons)

Merge stderr into stdout via `2>&1` in the shell runner when capture mode is set:

```python
# In the shell runner subprocess invocation:
if state.capture:
    process = subprocess.Popen(
        [...],
        stderr=subprocess.STDOUT if state.capture else subprocess.PIPE,
    )
```

This is **lossy** (loses line ordering between stdout and stderr) and changes the shape of `output_preview`. Use only if the additive field is blocked.

### Trade-off table

| Aspect | `stderr_preview` field (primary) | `2>&1` merge (fallback) |
|---|---|---|
| Mechanism | New structured field in `action_complete` payload; preserves stdout/stderr separation | Redirects stderr to stdout in the shell runner when capture mode is set |
| Information loss | None — stdout and stderr are preserved separately | Stderr text interleaves into stdout, losing line-order |
| Discovery | Field is queryable by name in downstream tooling | Buried in `output_preview`; requires regex to distinguish |
| Backward compatibility | Fully backward-compatible (additive field) | Changes the shape of `output_preview` for shell states with capture mode |
| Cross-loop impact | Applies to every prompt and shell action (additive) | Only applies to shell actions with `capture:` set; prompt actions already get stderr via the host CLI |
| Cost of implementation | ~5 lines in executor.py + 1 event-bus schema field | ~3 lines in executor.py, but couples capture mode to output redirection |
| Test coverage | Can add a test that asserts `stderr_preview` is non-null on a deliberate `print(..., file=sys.stderr)` action | Requires capturing output to verify; harder to test |

The `2>&1` merge is simpler but **changes semantics** — the existing `output_preview` field becomes a mix of stdout and stderr. Anything downstream that parses `output_preview` for stdout-specific content (e.g., the dedup_novelty heredoc's expected stdout `print(len(novel))`) will receive different input.

`stderr_preview` is strictly additive — existing consumers of `output_preview` are unaffected, and new consumers (operators, debuggers, post-mortem tooling) can opt in.

## Acceptance Criteria

- [ ] `action_complete` events include a `stderr_preview` field (additive).
- [ ] `stderr_preview` is `None` for actions with no stderr; non-null for actions that wrote to stderr.
- [ ] A test in `scripts/tests/test_fsm_executor.py` asserts `stderr_preview` is populated for a shell action that prints to stderr (`echo ERROR >&2; exit 1`).
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_host_runner.py -v`.
- [ ] `ll-loop validate` for affected loops remains clean (no schema warnings).

## Implementation Steps

1. Edit `scripts/little_loops/fsm/executor.py:1285-1307` to add `stderr_preview` field.
2. Add a test in `scripts/tests/test_fsm_executor.py` that runs a shell action with `echo ERROR >&2; exit 1` and asserts `action_complete["stderr_preview"]` contains "ERROR".
3. Run `python -m pytest scripts/tests/test_fsm_executor.py -v` to confirm green.
4. Run `ll-loop validate brainstorm` and 1-2 other shell-action loops to confirm no schema warnings.

## References

- `scripts/little_loops/fsm/executor.py:1285-1307` — `action_complete` payload construction
- `scripts/little_loops/fsm/executor.py:1310-1316` — `captured[state.capture]` dict (records stderr only when capture mode is set)
- `scripts/little_loops/fsm/executor.py:1157` — internal use of `result.stderr` for `classify_failure` (precedent for combining output and stderr)
- **BUG-2468** — motivating concrete failure (brainstorm `dedup_novelty` silent crash). The full failure trace is in `.loops/reviews/brainstorm-20260702-225858-failure.md`.
- **BUG-1640** / **BUG-1815** — sibling short-circuit logic for non-zero exit codes (related observability improvement).

## Impact

- **Priority**: P3 — observability gap, not a correctness bug. Workaround exists (read `.log` file).
- **Effort**: Small. ~3 lines in executor.py + 1 test.
- **Risk**: Low. The change is additive (no consumers of `output_preview` are affected). The new field is optional in event consumers' schema.
- **Breaking Change**: No.

## Scope Boundaries

**In scope**:
- Adding the `stderr_preview` field to `action_complete` events in `fsm/executor.py`.
- Test coverage for the new field in `scripts/tests/test_fsm_executor.py`.
- Schema documentation update if the project maintains a JSON Schema for `action_complete` (verify in `docs/reference/schemas/`).
- One-line validation that affected loops still pass `ll-loop validate`.

**Out of scope**:
- Changes to `classify_failure` or any internal stderr-using logic (line 1157 in `executor.py`) — those are not affected by the additive field.
- Changes to the MCP or baseline runners' stderr handling (separate runners, separate concerns).
- Adding `stderr_preview` for prompt-mode actions where the LLM response is the output (always `None` for normal prompt runs; can be added later if useful).
- Refactoring `output_preview` truncation strategy (e.g., head vs tail, byte vs char limits) — separate concern.
- Backfilling stderr into historical `events.jsonl` files from prior runs (not feasible; logs are immutable).

## Status

Done | Created: 2026-07-02 | Completed: 2026-07-03 | Priority: P3 | Type: ENH

Implemented the primary (additive) option: `stderr_preview` (last 2000 chars of `result.stderr`, stripped, `None` when empty) added to the `action_complete` payload in `FSMExecutor._run_action`. Tests in `scripts/tests/test_fsm_executor.py::TestStderrPreview` cover a failing shell action (`echo ERROR >&2; exit 1`), the None case, and tail truncation. `ll-loop validate brainstorm` / `autodev` remain clean.