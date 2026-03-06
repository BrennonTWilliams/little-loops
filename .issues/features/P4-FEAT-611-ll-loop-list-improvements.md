---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
---

# FEAT-611: `ll-loop list` improvements: status filter, paradigm type, description

## Summary

`ll-loop list` currently shows only loop file stems (names) with no metadata. The `--running` flag calls `list_running_loops()` but shows only `loop_name`, `current_state`, and `iteration` — omitting `status`, elapsed time, and `updated_at` which are available on `LoopState`. There is also no way to filter by status (e.g., show only `interrupted` or `awaiting_continuation` loops).

## Current Behavior

Available loops display:
```
Available loops:
  my-loop
  quality-gate
  invariants  [built-in]
```

Running loops display:
```
Running loops:
  my-loop: check_types (iteration 3)
```

No paradigm type, description, status, or elapsed time shown. No `--status` filter.

## Expected Behavior

Available loops show paradigm and optional description:
```
Available loops:
  my-loop         [goal]     Ensure tests pass
  quality-gate    [invariants]
  invariants      [invariants]  [built-in]
```

Running loops show status and elapsed time:
```
Running loops:
  my-loop: check_types (iteration 3) [running] 2m 15s
```

A `--status <value>` flag filters running loops by status.

## Use Case

A developer managing multiple loops wants to quickly see which are `interrupted` (needing manual resume) vs `awaiting_continuation` (paused handoff). They run `ll-loop list --status interrupted` to find loops that need attention.

## Acceptance Criteria

- [ ] `ll-loop list` shows paradigm type for each available loop
- [ ] `ll-loop list --running` shows status and elapsed time
- [ ] `ll-loop list --status <value>` filters by `LoopState.status`
- [ ] Description shown if available in the loop spec

## Impact

- **Priority**: P4 - Nice-to-have UX improvement for loop management
- **Effort**: Small-Medium - Needs to load loop specs for paradigm/description
- **Risk**: Low - Display-only changes, additive CLI flags
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `cli`, `ux`

---

**Open** | Created: 2026-03-06 | Priority: P4
