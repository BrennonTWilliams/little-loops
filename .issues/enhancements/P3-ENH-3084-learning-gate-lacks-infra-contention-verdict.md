---
id: ENH-3084
type: ENH
title: Learning gate has no verdict distinguishing infra contention from implementation
  failure
priority: P3
status: open
captured_at: '2026-08-06T16:17:02Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- learning-gate
- ll-auto
- autodev
- fsm-concurrency
relates_to:
- BUG-3083
- BUG-2864
- BUG-2833
---

# ENH-3084: Learning gate has no verdict distinguishing infra contention from implementation failure

## Summary

`run_learning_gate_for_issue()` returns one of four verdicts —
`passed` / `blocked` / `impl_failed` / `skipped` (`learning_tests/gate.py:65-71`).
There is no verdict for "the gate never ran." Every non-zero, non-
`FAILURE_TERMINAL_EXIT_CODE` exit — scope-lock conflict, missing binary, crash —
collapses to `impl_failed` (gate.py:156-170), which `issue_manager.py:1130-1147`
turns into `IMPLEMENT_FAILED <ID>` and a `failure_reason` of
"Learning gate: implementation failed."

That verdict is a deliberate improvement over BUG-2864's prior behavior (which
misreported these as `blocked`), but it is still wrong in the other direction:
an infra condition is reported as a claim about the implementation.

## Current Behavior

A scope-lock conflict produces:

```
[01:18:47] Learning gate impl-failed for ENH-3073: implementation failed
IMPLEMENT_FAILED ENH-3073
```

Downstream, `IMPLEMENT_FAILED` is the generic-failure marker that `autodev` /
`rn-remediate.yaml:907` route to remediation. So a transient lock contention
burns a remediation cycle on an issue whose implementation was never attempted,
and the run summary reports it as a failed implementation.

## Expected Behavior

A verdict that says the gate could not run, distinct from both "targets refuted"
and "implementation failed." Callers can then retry, skip the gate, or defer
with an accurate reason, instead of consuming remediation budget.

## Motivation

Failure-reason accuracy is what makes the automation loops' routing decisions
correct. A misclassified infra failure is worse than a loud crash: it produces a
plausible-looking but false statement about the issue ("implementation failed"),
which then drives the wrong remedy. This is the third iteration on the same
classification boundary (BUG-2833 split `impl_failed` from `blocked`; BUG-2864
split infra from `blocked`) — the missing axis is infra vs. impl.

## Current Pain Point

An operator reading the run summary sees `ENH-3073: Learning gate: implementation
failed` and has no signal that nothing was implemented at all. Recovering the
real reason requires reading the logged subprocess stderr.

## Proposed Solution

Add a fifth verdict, e.g. `infra_failed`, to the `Literal` return type:

```python
) -> Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]:
```

Return it from the three infra paths in the targets branch (non-terminal
non-zero exit, `TimeoutExpired`, `FileNotFoundError`), and keep `impl_failed`
for the `proof-first-task` fallback branch's genuine delegated-impl failures
(BUG-2833's case).

In `issue_manager.py`, handle `infra_failed` with its own marker and reason —
e.g. print `GATE_INFRA_FAILED <ID>` (mirroring the existing `LEARNING_GATE_BLOCKED`
/ `ENV_NOT_READY` token convention, ENH-2353) and set
`failure_reason="Learning gate could not run: <reason>"`. Loops that capture
`ll-auto --only ... 2>&1` can then route on the new token — retry or skip rather
than remediate.

Decide as part of implementation whether `ll-auto` should retry once in-process
on `infra_failed` before giving up, or leave the retry policy entirely to the
calling loop. Prefer leaving it to the loop unless a cheap bounded retry is
clearly safe.

## API/Interface

`run_learning_gate_for_issue()`'s return `Literal` widens by one member. All
call sites must handle it: `issue_manager.py:1110`, and check
`cli/sprint/run.py` (`_run_learning_gate_preflight()`) and
`parallel/worker_pool.py:88` for the same pattern.

## Scope Boundaries

- **In scope**: the verdict enum, the three infra return paths, the caller
  branches and their stdout markers, and the loop YAML routing that consumes
  the new token.
- **Out of scope**: fixing the scope-lock conflict itself (BUG-3083) and the
  queue-timeout budget mismatch (BUG-3085). This issue makes the failure
  *legible*; those make it *rare*.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/learning_tests/gate.py` | `run_learning_gate_for_issue` | New `infra_failed` verdict |
| `scripts/little_loops/issue_manager.py` | learning-gate block, ~1105-1147 | New branch + marker |
| `scripts/little_loops/cli/sprint/run.py` | `_run_learning_gate_preflight` | Handle new verdict |
| `scripts/little_loops/loops/rn-remediate.yaml` | outcome-token routing | Route the new token |
| `scripts/tests/test_learning_tests_gate.py` | — | Cover each infra path |

## Implementation Steps

1. Widen the `Literal` and return `infra_failed` from the infra paths.
2. Add the caller branch + stdout marker in `issue_manager.py`.
3. Sweep the other call sites for exhaustive handling (mypy will flag them).
4. Route the new token in the consuming loop YAMLs.
5. Tests: one per infra path, asserting the verdict and the emitted marker.

## Impact

Correct routing for a failure mode that currently consumes remediation cycles
and misreports outcomes. Low risk — additive to an enum with a small, statically
checkable set of call sites.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | `little_loops.learning_tests.gate` signature |
| `docs/reference/DEFERRAL_CODES.md` | Where an infra deferral code would be registered |

## Status

open


## Session Log
- `/ll:capture-issue` - 2026-08-06T16:20:22 - `ee676905-966c-42aa-ac9d-d7d4aaeea91d.jsonl`
