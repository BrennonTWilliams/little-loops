> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-18"
discovered_by: review
captured_at: "2026-04-18T00:00:00Z"
related_issues: [FEAT-1074, FEAT-1076]
---

# ENH-1173: Extend Unresolved-Context-Variable Pre-Scan to Cover `state.parallel.items`

<!-- NOTE: Originally captured as ENH-1169; renumbered to 1173 to avoid collision with FEAT-1169. -->

## Summary

The FSM runner's pre-scan for unresolved `{{ ... }}` context variables currently inspects `state.action` only. It does not inspect `state.parallel.items`. A `parallel:` state whose `items` field references a context variable that fails to resolve at runtime (e.g., `{{ captured.issue_list.output }}` when `issue_list` was never captured) will split on an empty string or on literal-brace text with no early warning — fanning out zero workers or fanning out against garbage item strings.

## Current Behavior

`cli/loop/run.py:107-115` pre-scans `state.action` for unresolved `{{ }}` context-variable expressions before the FSM executor runs. When an unresolved expression is found, the runner emits an actionable error identifying the variable and the state.

The same pre-scan does **not** inspect `state.parallel.items` (or any other field of `state.parallel`). Consequences at runtime:
- `items` containing unresolved `{{ X }}` will be passed verbatim to `ParallelRunner`, which splits on newlines.
- The split produces either an empty list (if the expression happened to resolve to `""`) or a list containing literal `{{ X }}` text.
- Empty list → 0 workers fan out; the parallel state completes with verdict `"yes"` (vacuously) and routes `on_yes` — a silent no-op where the author almost certainly intended work to happen.
- Literal text → workers are launched against nonsense item strings; sub-loops fail in opaque ways.

Either way, the author gets no early signal pointing at the missing context variable.

## Expected Behavior

The pre-scan at `cli/loop/run.py:107-115` is extended so that, for every state with `state.parallel is not None`, it also scans `state.parallel.items` for unresolved `{{ }}` expressions and emits the same class of actionable error it already emits for `state.action`.

- Error message identifies the state name, the `parallel.items` field, and the unresolved variable name
- Message is emitted **before** the FSM executor runs; no worker fan-out has occurred yet
- States without a `parallel:` block are unaffected

## Motivation

Parallel fan-out errors are particularly expensive to debug without this pre-scan:
- A silent zero-worker fan-out routes `on_yes` and the loop appears to succeed, masking the bug until a downstream state reads empty captures
- A garbage-item fan-out spawns N workers (possibly with `isolation: worktree`, which means N `git worktree add` calls) before anyone discovers the items string was bogus
- The existing `state.action` pre-scan has been consistently useful for exactly this reason — extending it to cover `parallel.items` closes the matching gap in the new `parallel:` code path

This is the same class of guard as the existing `state.action` pre-scan; the omission is incidental, not intentional.

## Proposed Solution

Locate the existing pre-scan in `cli/loop/run.py:107-115`. It iterates states and inspects `state.action`. Extend the per-state inspection to also include `state.parallel.items` when `state.parallel is not None`:

```python
for state_name, state in fsm.states.items():
    # existing state.action scan ...
    if state.parallel is not None:
        _scan_for_unresolved_context_vars(
            text=state.parallel.items,
            path=f"states.{state_name}.parallel.items",
            ctx=initial_context,
            errors=errors,
        )
```

The exact function/call shape should match whatever helper the existing `state.action` scan uses — extract a helper if the current inline form doesn't factor cleanly. Do not change the error class or severity; it should behave identically to the existing `action` pre-scan.

## Implementation Steps

1. Read `cli/loop/run.py:107-115` and identify the helper (or inline code) that performs the `state.action` pre-scan
2. Extract the pre-scan into a reusable helper if it is not already one; the helper should take `(text, path, ctx, errors)` or equivalent
3. Add a second call site within the same loop that invokes the helper against `state.parallel.items` when `state.parallel is not None`
4. Write a test in `scripts/tests/test_cli_loop_run.py` (or wherever the existing `state.action` pre-scan is tested) that loads a loop with an unresolved variable in `parallel.items` and asserts the pre-scan error fires before executor start
5. Verify no regression in the existing `state.action` pre-scan behavior

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — extend the pre-scan loop at lines 107-115
- `scripts/tests/test_cli_loop_run.py` (or equivalent) — add `parallel.items` pre-scan test

### Similar Patterns
- Existing `state.action` pre-scan at `cli/loop/run.py:107-115` — same error format and severity
- `state.parallel` check pattern in `validation.py` (added by FEAT-1074) — follow the same `state.parallel is not None` guard form

### Tests
- One new test: unresolved `{{ }}` in `parallel.items` produces a pre-scan error identifying the variable and `states.<name>.parallel.items` path
- Regression: existing `state.action` pre-scan tests still pass

## Dependencies

- **Soft dependencies**: FEAT-1074 (adds `state.parallel` field), FEAT-1076 (adds executor dispatch). This enhancement is only meaningful once `parallel:` states actually exist; it can be written against the FEAT-1074 spec ahead of merge and landed any time after FEAT-1074 is in.
- **Related issues**: referenced from FEAT-1074 and FEAT-1076 Integration Maps as the follow-up that closes the pre-scan gap those issues leave open.

## Acceptance Criteria

- Pre-scan at `cli/loop/run.py:107-115` covers both `state.action` and `state.parallel.items`
- Unresolved `{{ X }}` in `parallel.items` produces an actionable error naming the state and the `parallel.items` field, emitted before executor start (no worker fan-out occurs)
- States without a `parallel:` block behave identically to today
- Test coverage added for the new code path; existing `state.action` pre-scan tests still pass

## Impact

- **Priority**: P3 — Not a correctness bug today (the code path it guards doesn't exist until FEAT-1074/1076 ship); becomes a real footgun as soon as users author `parallel:` states
- **Effort**: Very Small — Extend one loop, one helper call, one test
- **Risk**: Very Low — Additive guard on a narrow new code path
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `cli`, `validation`, `developer-experience`

---

## Session Log
- Captured 2026-04-18 from review of Parallel FSM Loops issue set (follow-up to FEAT-1074/1076).

---

**Open** | Created: 2026-04-18 | Priority: P3
