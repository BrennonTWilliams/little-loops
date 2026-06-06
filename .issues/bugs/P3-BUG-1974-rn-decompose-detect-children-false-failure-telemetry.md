---
id: BUG-1974
title: 'rn-decompose: detect_children exits 1 for no-children routes to failed terminal,
  polluting telemetry'
type: BUG
priority: P3
status: open
captured_at: '2026-06-06T03:29:25Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
relates_to:
- BUG-1973
- ENH-1977
labels:
- rn-implement
- rn-decompose
- loop-defect
- telemetry
confidence_score: 93
outcome_confidence: 78
score_complexity: 25
score_test_coverage: 8
score_ambiguity: 20
score_change_surface: 25
---

# BUG-1974: rn-decompose detect_children false-failure routing

> **Coordination (2026-06-06):** Partially absorbed by **ENH-1977**. That issue's Fix 1/Fix 4 rewrite
> `detect_children` (token write + body-marker match), and its token channel makes the parent-level
> consequence moot. But the *sub-loop telemetry* flip this bug describes (`on_no: failed → done`) is
> **not** automatic — ENH-1977 must carry it explicitly, and now lists it as an acceptance criterion.
> Do not implement this bug in parallel with ENH-1977 (shared `detect_children` state); fold it in or
> serialize. Standalone fix remains valid if landed *before* ENH-1977.

## Summary

In rn-decompose, `detect_children` exits 1 to signal "no children found after size review." This is
the *expected* path when `issue-size-review` scores below the decomposition threshold (score < 5),
meaning no decomposition is warranted. However, the FSM routes `on_no: "failed"` — the terminal
failure state — so a fully correct, no-action-needed sub-loop run shows up as `final_state: failed`
in the event history and telemetry.

The parent (`run_decomposition.on_no → skip_issue`) recovers correctly, so there is no user-visible
harm. But sub-loop failure counts are inflated, making it harder to distinguish genuine decomposition
failures from expected "nothing to decompose" outcomes.

## Current Behavior

In `loops/rn-decompose.yaml`, the `detect_children` state uses `on_no: failed` routing. When `detect_children` exits 1 (signaling "no children found"), the FSM terminates in the `failed` terminal state. Every no-decomposition outcome records `final_state: failed` in event history and loop telemetry, inflating sub-loop failure counts.

## Expected Behavior

When `detect_children` exits 1 because no decomposition is warranted (size review score < 5), the loop should terminate in the `done` state. A no-children outcome is the expected success path — the issue was processed and correctly determined to not need splitting. Sub-loop runs that take the no-decomposition path should record `final_state: done`, not `final_state: failed`.

## Steps to Reproduce

Run `2026-06-06T032504` (rn-implement processing ENH-1924):

```
state: detect_children
exit_code: 1
output_preview: "No children found for ENH-1924"
verdict: no → route to failed
loop_complete: { final_state: "failed", terminated_by: "terminal" }
```

ENH-1924 correctly scored 4/11 (Medium, below decomposition threshold 5). The size review worked
as intended — no decomposition needed. But the sub-loop recorded as `failed`.

## Root Cause

- **File**: `loops/rn-decompose.yaml`
- **Anchor**: in state `detect_children`
- **Cause**: `on_no: failed` treats a no-children exit (exit code 1) as a loop failure. Exit code 1 in this state means "no children found after size review" — the expected outcome when `issue-size-review` returns score < 5. The routing should be `on_no: done` since the sub-loop completed its work successfully (determined that no decomposition is needed).

## Proposed Solution

In `loops/rn-decompose.yaml`, add a `done` routing for the no-children case:

```yaml
  detect_children:
    ...
    on_yes: enqueue_children
-   on_no: failed
+   on_no: done          # "No children found" is the expected success path when size review said no-split
    on_error: failed
```

Alternatively, have `detect_children` exit 0 in both cases and distinguish via `output_contains`:

```yaml
  detect_children:
    ...
    # Exit 0 always; output "FOUND" vs "NONE" to drive routing
    evaluate:
      type: output_contains
      pattern: "FOUND"
    on_yes: enqueue_children
    on_no: done
    on_error: failed
```

## Implementation Steps

1. Update `detect_children` state in `loops/rn-decompose.yaml`: change `on_no: failed` to `on_no: done`
2. Optionally refine to output-based routing (`output_contains: "FOUND"`) for explicit semantics
3. Run `ll-loop validate loops/rn-decompose.yaml` to confirm the change passes validation
4. Run a test iteration against an issue with size review score < 5 and confirm `final_state: done`

## Impact

- **Priority**: P3 — Low urgency; telemetry noise with no functional regression
- **Effort**: Small — single-line YAML change in `loops/rn-decompose.yaml`
- **Risk**: Low — changes only the terminal routing for the no-children path; `on_error: failed` is preserved
- **Breaking Change**: No
- **Severity**: LOW — cosmetic telemetry noise, no functional regression
- **Blast radius**: All rn-decompose runs where size review returns score < 5 (no decomposition)

## Status

**Open** | Created: 2026-06-06 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-06T03:42:00 - `97ec5bad-c4ae-4905-967e-fe34fe404a62.jsonl`
- `/ll:confidence-check` - 2026-06-05T23:27:00 - `fc2faaa1-72f4-4cc4-8c91-b3c75ba8ff97.jsonl`
