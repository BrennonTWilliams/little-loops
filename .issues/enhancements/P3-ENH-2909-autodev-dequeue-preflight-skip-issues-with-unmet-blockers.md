---
id: ENH-2909
type: ENH
priority: P3
status: open
captured_at: "2026-07-29T02:59:11Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- loops
- fsm
- autodev
- efficiency
relates_to:
- BUG-2907
depends_on:
- BUG-2908
---

# ENH-2909: `autodev` dequeue pre-flight — park issues with unmet blockers before refining

## Summary

`autodev`'s `dequeue_next` hands any queued issue straight to the full
refine → wire → confidence-check → size-review chain without first checking
whether the issue is implementable. In the audited run, FEAT-108 spent ~34
minutes and 12 parent iterations completing that chain, only for
`implement_current` to discover it was blocked by an unresolved dependency ring
(`FEAT-108 → FEAT-123 → FEAT-122 → FEAT-108`) and do nothing. A pre-flight
blocker check at dequeue time would have parked it in seconds.

## Current Behavior

`dequeue_next` already performs pre-flight work — it snapshots the backlog to
`autodev-pre-ids.txt` for child detection and (per FEAT-2751) snapshots
pre-refine confidence to `autodev-pre-readiness.txt`. Downstream,
`check_status_at_dequeue` filters issues already `done`/`cancelled`/`deferred`
(ENH-2868), and `check_decision_at_dequeue` filters `decision_needed`.

There is no equivalent check for unmet `blocked_by` / `depends_on` edges, even
though `ll-issues show <ID> --json` exposes `blocked_by` directly and
`ll-deps` provides full cross-issue dependency analysis. The blocked issue
proceeds through the entire refine chain.

## Expected Behavior

At dequeue, an issue whose `blocked_by` / `depends_on` edges are not all
resolved (blocker status `done` or `cancelled` — per BUG-2897, `deferred` is
**non-terminal** and does *not* resolve an edge) is recorded in
`autodev-skipped.txt` with a reason stem (`blocked_by_unmet`, or
`blocked_by_cycle` when the issue participates in a dependency cycle) and the
queue advances without refining it. `finalize_done` surfaces the bucket
separately from generic skips, the way it already does for `already_*`,
`refine_failed_infra`, and gate-blocked issues.

## Motivation

A doomed issue consumes a full refine cycle — sub-loop `refine-to-ready-issue`
(12 iterations at depth 1) plus a nested `verify-confidence-scores` run — before
the loop learns it cannot be implemented. On a multi-issue queue this compounds:
each blocked entry costs a full cycle's wall-clock and tokens while producing no
closure.

## Motivation

Efficiency, not correctness — BUG-2907 and BUG-2908 make the *outcome* honest;
this makes the loop stop paying for a known-unwinnable attempt.

Worth noting explicitly so the implementer does not over-fit: **the refine pass
was not worthless.** It is what discovered and recorded the `blocked_by` edges in
the first place (`+blocked_by: [FEAT-122, FEAT-123, FEAT-124]`, confidence
80→87). An issue with *no* declared blockers that turns out to be blocked cannot
be caught by this pre-flight, and that is acceptable — the check is a cheap
filter on already-declared edges, not a dependency discovery mechanism.

## Proposed Solution

Add a dedicated state between `check_decision_at_dequeue` and `refine_current`
rather than growing `dequeue_next`'s action (which is already long, and whose
`on_yes`/`on_no` routing carries queue-empty semantics that a second predicate
would muddy). This mirrors the existing `check_status_at_dequeue` /
`check_decision_at_dequeue` chain shape:

```yaml
  check_blockers_at_dequeue:
    action: |
      ID="${captured.input.output}"
      ll-issues show "$ID" --json 2>/dev/null | python3 -c "
      import json, sys
      d = json.load(sys.stdin)
      blockers = d.get('blocked_by') or []
      print(','.join(blockers) if blockers else '')
      " > ${context.run_dir}/autodev-blockers.txt
      # unmet := any blocker whose status is not done/cancelled
      # (BUG-2897: deferred does NOT resolve an edge)
    action_type: shell
    on_yes: skip_blocked
    on_no: refine_current
    on_error: refine_current
```

Prefer `ll-deps` over hand-rolled graph walking if it already exposes an
"unmet blockers for ID" query — check its subcommand surface first; the
dependency-graph semantics (including BUG-2897's non-terminal `deferred` rule)
live in `issue_parser.find_issues_for_graph()` and should not be reimplemented in
bash.

`skip_blocked` records the reason and clears `autodev-inflight` (mirroring
`skip_inflight` / `mark_gate_blocked`), then routes `next: dequeue_next`.

Cycle detection is a refinement, not a prerequisite: `ll-auto` already logs
`Dependency cycle detected` and the loop can report `blocked_by_unmet` without
distinguishing a cycle. Add `blocked_by_cycle` as a distinct reason only if
`ll-deps` surfaces cycle membership cheaply.

## API/Interface

No public API change. New run-dir artifacts: `autodev-blockers.txt` (transient),
new reason stems in `autodev-skipped.txt`.

## Scope Boundaries

**In scope**: pre-flight check on declared `blocked_by` / `depends_on` edges at
dequeue; a `skip_blocked` state; `finalize_done` bucket surfacing.

**Out of scope**: discovering undeclared dependencies; auto-resolving or
reordering the queue to implement blockers first (a queue-scheduling change,
materially larger); changing `ll-auto`'s own blocked-issue handling (BUG-2907).

## Integration Map

- `scripts/little_loops/loops/autodev.yaml` — new `check_blockers_at_dequeue` +
  `skip_blocked` states between `check_decision_at_dequeue` and `refine_current`;
  `finalize_done` bucket rendering (which must be reconciled with BUG-2908's
  rewrite of that state — sequence this issue after BUG-2908 or expect a conflict)
- `scripts/little_loops/issue_parser.py` — `find_issues_for_graph()`,
  `DependencyGraph`; BUG-2897's non-terminal-`deferred` rule
- `scripts/little_loops/deps.py` / `ll-deps` — preferred query surface
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop`

## Implementation Steps

1. Check `ll-deps`' subcommand surface for an existing "unmet blockers for ID"
   query before writing any graph logic in the loop.
2. Add `check_blockers_at_dequeue` + `skip_blocked`; wire the routing.
3. Surface the new reason stem in `finalize_done`'s summary buckets.
4. Tests: an issue with a `done` blocker refines normally; one with an `open`
   blocker is skipped with reason; one with a `deferred` blocker is **also**
   skipped (BUG-2897 regression guard).
5. `ll-loop validate autodev` clean.

## Success Metrics

A queued issue with an unmet blocker is parked in one dequeue cycle instead of
consuming a full refine chain (~12 iterations / ~30 min in the observed case).

## Impact

- **Efficiency**: removes the dominant wasted-cycle case from `autodev` runs on
  dependency-heavy backlogs.
- **Ordering**: depends on BUG-2908 landing first — both edit `finalize_done`'s
  summary block, and BUG-2908 rewrites it substantially.
- **Risk**: a too-aggressive predicate would skip implementable issues. Confining
  the check to declared edges with terminal-status resolution keeps it
  conservative; the `on_error: refine_current` fallback fails open.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Issue File Format | `deferred` is non-terminal for dependency purposes (BUG-2897) |
| `docs/ARCHITECTURE.md` | dependency graph and orchestration layers |
| `audit-loop-run-autodev-2026-07-29T013824.md` | audit report with verbatim run evidence |

## Session Log
- `/ll:capture-issue` - 2026-07-29T02:59:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a15bf47-b270-4d12-a74c-47b9c005a000.jsonl`

---

## Status

`open`
