---
captured_at: "2026-05-24T13:15:53Z"
discovered_date: 2026-05-24
discovered_by: capture-issue
status: open
labels: [fsm-loops, general-task, resilience, loop-config]
---

# ENH-1677: Apply retry hardening to `general-task.yaml` using existing `max_retries`

## Summary

Update `continue_work` and `execute` states in `scripts/little_loops/loops/general-task.yaml` to use the `max_retries`/`on_retry_exhausted` fields (delivered in ENH-713) so that transient infrastructure failures (API socket disconnect, file lock races) do not immediately terminate the loop via `diagnose → failed`.

## Motivation

In run `2026-05-24T093122`, an API socket disconnect during `continue_work` (iteration 7, exit code 1) routed directly to `diagnose → failed` because `continue_work` has `on_error: diagnose`. The ENH-713 retry mechanism is already available but not wired into `general-task.yaml`. A lightweight YAML-only change makes the loop resilient to one-off infrastructure failures without requiring any framework changes.

Note: ENH-1675 proposes a complementary `retryable_exit_codes` filter to limit retries to known-transient codes. This issue can be implemented independently using the existing unconditional retry mechanism.

## Expected Behavior

**`continue_work`** retries up to 3 times on failure before routing to `diagnose`:
```yaml
continue_work:
  action: "..."
  on_error: continue_work
  max_retries: 3
  on_retry_exhausted: diagnose
  next: check_done
```

**`execute`** retries up to 2 times on failure before falling through to `continue_work` (where `check_done` can catch and remediate the gap):
```yaml
execute:
  action: "..."
  on_error: execute
  max_retries: 2
  on_retry_exhausted: continue_work
  next: check_done
```

## Acceptance Criteria

- [ ] `continue_work` has `on_error: continue_work`, `max_retries: 3`, `on_retry_exhausted: diagnose`
- [ ] `execute` has `on_error: execute`, `max_retries: 2`, `on_retry_exhausted: continue_work`
- [ ] `ll-loop validate general-task` exits 0 after the changes
- [ ] A transient failure (exit code 1) in `continue_work` retries and does not immediately route to `diagnose`

## Implementation Steps

1. In `scripts/little_loops/loops/general-task.yaml`, add to `continue_work`:
   - `on_error: continue_work` (was `diagnose`)
   - `max_retries: 3`
   - `on_retry_exhausted: diagnose`
2. Add to `execute`:
   - `on_error: execute` (was `diagnose`)
   - `max_retries: 2`
   - `on_retry_exhausted: continue_work`
3. Run `ll-loop validate general-task` to confirm schema validity.
4. (Optional) If ENH-1675 is also implemented, add `retryable_exit_codes: [1, 137]` to limit retries to known-transient codes.

## Success Metrics

- Transient infrastructure failures in `continue_work` or `execute` no longer produce immediate `failed` state transitions when retries remain available
- Zero change to loop behavior on genuine task failures (retries exhaust → `diagnose` or `continue_work` as configured)

## Scope Boundaries

- **In scope**: `continue_work` and `execute` states in `general-task.yaml`; YAML-only change using the existing retry mechanism from ENH-713
- **Out of scope**: Framework or Python changes; other loop YAML files; the `retryable_exit_codes` filter (tracked in ENH-1675)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — update `continue_work` and `execute` state config

### Validation
- `ll-loop validate general-task` — confirms schema validity after changes

## Impact

- **Priority**: P3
- **Effort**: Trivial — YAML-only change, no Python
- **Risk**: Very Low — uses an existing, tested mechanism; no schema changes
- **Breaking Change**: No
- **Depends on**: ENH-713 (already done)

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-24): ENH-1677 (retry hardening for `continue_work` + `execute`) and ENH-1655 (retry hardening for `check_done` evaluate step) are complementary halves of a complete general-task retry-hardening effort — they target different states but the same class of infra failures in the same loop. Both should land together in a single sprint for full coverage. ENH-1677 explicitly acknowledges ENH-1675 (`retryable_exit_codes` filter) as a follow-up; ENH-1655 addresses the evaluate-specific path that ENH-1677 does not touch.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T13:37:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c29e127-5f7b-421f-9734-c94217103bba.jsonl`
- `/ll:format-issue` - 2026-05-24T13:19:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5566ccd-518b-4732-b99c-7c2788c9b64d.jsonl`
- `/ll:capture-issue` - 2026-05-24T13:15:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bfd5e964-4cba-4f63-8354-255b3fbb9f18.jsonl`
