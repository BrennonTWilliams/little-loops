---
id: BUG-1256
priority: P3
captured_at: "2026-04-22T17:02:49Z"
discovered_date: "2026-04-22"
discovered_by: capture-issue
source_loop: autodev
source_state: implement_current
---

# BUG-1256: implement_current treats ll-auto decision-gate skip as success

## Summary

When `ll-auto --only <ISSUE_ID>` is called by `implement_current` in `autodev.yaml` and the issue has `decision_needed: true`, `ll-auto` prints the ✗ decision gate message and declines to implement — but **exits 0 (success)**. The `implement_current` state uses `next: dequeue_next` (not `fragment: shell_exit`), so it routes forward unconditionally regardless of outcome. Autodev records the issue as processed and moves on, even though nothing was implemented and the issue file was not moved to `completed/`.

## Current Behavior

```
implement_current: ll-auto --only ENH-1243
  → ll-auto hits decision gate (decision_needed: true)
  → prints "✗ Decision gate: this issue has competing implementation options"
  → exits 0
  → autodev routes to dequeue_next (queue now empty)
  → loop_complete: done
  → ENH-1243 not implemented, not in completed/, autodev reports no warning
```

Observed in run `2026-04-22T000300-autodev`. The `ll-auto` output preview contained the explicit ✗ gate message and "Processed 0 issue(s)", yet `action_complete` recorded `exit_code: 0`.

## Expected Behavior

`ll-auto --only` exits non-zero when the decision gate blocks implementation, so `implement_current` can detect and handle the skip. The issue must not silently vanish from the queue when implementation is blocked.

## Root Cause

Two contributing factors:

1. **`ll-auto` exit code** — `ll-auto` (or the underlying `ll-auto --only` path) does not distinguish between "processed all issues" and "skipped all issues due to gates". It exits 0 in both cases. See `scripts/little_loops/auto.py` (the `--only` execution path and verification step).

2. **`implement_current` routing** — `autodev.yaml:165–175` uses `action_type: shell` with `next: dequeue_next`, meaning the state always advances regardless of exit code. No failure path exists to detect a zero-exit-but-did-nothing outcome.

## Proposed Fix

Make `ll-auto --only` exit non-zero when it processed 0 issues due to gates/skips. The existing "Processed 0 issue(s)" log line is the signal — exit 1 when that count is 0 and the reason is a gate (not an empty input). Then change `implement_current` in `autodev.yaml` to use `fragment: shell_exit` with `on_no: dequeue_next` (skip) and a new `on_yes` successor state that routes normally.

## Integration Map

- `scripts/little_loops/auto.py` — `--only` path, verification step, exit code logic
- `scripts/little_loops/loops/autodev.yaml:165–175` — `implement_current` state definition
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` class; needs a test for the decision-gate-skip scenario

## Acceptance Criteria

- [ ] `ll-auto --only <ID>` where `<ID>` has `decision_needed: true` exits non-zero
- [ ] `implement_current` detects the non-zero exit and does NOT silently route to `dequeue_next` as if successful
- [ ] The in-flight issue is surfaced (written to a needs-decision list or re-queued)
- [ ] Test added to `TestAutodevLoop` covering this scenario

## Labels

`bug`, `autodev`, `ll-auto`, `decision-gate`, `silent-skip`

## Status

**Open** | Created: 2026-04-22 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-22T17:02:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c3dd3b0-98a8-494a-8720-4fa7296292d6.jsonl`
