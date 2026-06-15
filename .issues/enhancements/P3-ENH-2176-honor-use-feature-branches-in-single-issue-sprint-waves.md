---
id: ENH-2176
title: Honor use_feature_branches in single-issue sprint waves (flag silently no-ops)
type: ENH
status: open
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T17:30:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, sprint, feature-branches, workflow, dx, coverage]
relates_to: [BUG-2172, ENH-2174]
---

# ENH-2176: Honor use_feature_branches in single-issue sprint waves (flag silently no-ops)

## Summary

`parallel.use_feature_branches` only takes effect for issues dispatched through
`ParallelOrchestrator`. In `ll-sprint`, any wave with exactly one issue — **or**
any contention sub-wave — runs **in-place sequentially** and never touches the
orchestrator, so the flag has zero effect for those issues. Because dependency
chains and file-contention splits routinely produce single-issue waves, toggling
`use_feature_branches` yields feature branches for *some* issues in a sprint and
not others, with no signal as to which. A toggle whose effect depends on
accidental wave-packing is not first-class.

This was noted as "Out of Scope" in EPIC-2171's initial capture; it is promoted
here to a tracked child because it is the single biggest gap between the flag's
advertised behavior and what users observe.

## Current Behavior

- `cli/sprint/run.py:437` — `if len(wave) == 1 or is_contention_subwave:` runs
  each issue in-place via `_run_issue_with_wall_clock_timeout(...)` on the
  current branch. No worktree, no `feature/<id>-<slug>` branch, no
  `ParallelOrchestrator`, so `use_feature_branches` is never consulted.
- `cli/sprint/run.py:489` — only the multi-issue `else` branch constructs a
  `ParallelOrchestrator` (via `create_parallel_config`) that honors the flag.
- Net: in a sprint, whether an issue lands on a feature branch depends solely on
  whether it shared a wave with another non-overlapping issue. `ll-auto`
  (sequential, in-place) is separately out of scope by design — see EPIC-2171.

## Steps to Reproduce

1. Set `parallel.use_feature_branches: true` in `.ll/ll-config.json`.
2. Build a sprint whose issues form a dependency chain (so each wave has one issue).
3. Run `ll-sprint run <sprint>`.
4. Observe: no `feature/<id>-<slug>` branches are created; work lands on the
   current branch. The flag was silently ignored for every wave.

## Decision

**Option B (warn + document) — DECIDED.** Keep the in-place path as-is, but when
`use_feature_branches` is set and a wave runs in-place (single-issue wave or
contention sub-wave), emit a clear one-time warning
("feature-branch mode does not apply to single-issue / contention sub-waves;
these run in-place on `<branch>`") and document the limitation at the toggle
surfaces (coordinate with ENH-2174's description text). This is the minimum to
make the toggle honest without regressing the hot in-place path.

Option A (extend coverage — route single-issue waves through a feature-branch-aware
worktree/in-place path) is **deferred as a follow-up**: it is materially larger
(the in-place path is deliberately worktree-free for speed), touches the hot
sprint path, and should not block the EPIC. If branch-per-issue for single-issue
waves proves valuable, capture it as a separate enhancement.

## Expected Behavior

Toggling `use_feature_branches` produces honest, predictable behavior across a
sprint: when the flag is set and a wave runs in-place, the user is warned once
that those issues are not getting feature branches, and the coverage boundary is
documented at the toggle surfaces. No silent no-op.

## Acceptance Criteria

1. With `use_feature_branches` set, a sprint composed entirely of single-issue
   waves no longer silently ignores the flag — a clear (one-time) warning is
   emitted naming the branch the work lands on, and the limitation is documented
   at the toggle surfaces (coordinate with ENH-2174).
2. The behavior is the same for contention sub-waves (they share the in-place
   path) — they trigger the same warning.
3. `ll-auto` remains explicitly out of scope (documented, not silently divergent).
4. Tests cover Option B: a warning is emitted when `use_feature_branches` is set
   and a wave runs in-place; no warning when the flag is unset.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint/run.py` — single-issue / contention sub-wave
  branch (~line 437): add a guarded one-time warning when
  `config.parallel.use_feature_branches` is set and the wave runs in-place
- `docs/guides/SPRINT_GUIDE.md` — document the coverage boundary

### Deferred (Option A follow-up, not this issue)
- `scripts/little_loops/parallel/worker_pool.py` — would reuse branch-naming
  (`feature/<id>-<slug>`, ~line 245) to give the single-issue path a real feature
  branch; out of scope here.

### Similar Patterns
- The multi-issue `else` branch (`cli/sprint/run.py:489`) — the
  `create_parallel_config` + `ParallelOrchestrator` path that already honors the flag

### Tests
- `scripts/tests/` sprint run tests — single-issue wave behavior under the flag

## Impact

- **Priority**: P3 — directly undermines the EPIC's "first-class toggle" goal;
  Option B (decided) is small and removes the silent-no-op surprise.
- **Effort**: Small — a guarded warning + a docs paragraph.
- **Risk**: Low — does not alter the in-place execution path, only adds a warning.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- decision - 2026-06-15 - Option B (warn + document) selected; Option A (extend coverage to single-issue waves) deferred as a follow-up.
- `/ll:capture-issue` - 2026-06-15T17:30:00Z - promoted from EPIC-2171 Out of Scope
