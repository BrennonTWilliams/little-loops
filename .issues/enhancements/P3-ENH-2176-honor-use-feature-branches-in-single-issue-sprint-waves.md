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

## Motivation

This enhancement would:
- Make `use_feature_branches` a first-class toggle: users who set it expect all sprint issues to land on feature branches, but dependency chains routinely produce single-issue waves that silently bypass the orchestrator — yielding inconsistent branch coverage with no diagnostic signal.
- Remove the silent no-op surprise: a flag whose effect depends on accidental wave-packing is not trustworthy; Option B delivers honest minimum behavior without touching the hot in-place path.
- Close the gap between advertised and actual behavior identified in EPIC-2171 without blocking the EPIC.

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

## Scope Boundaries

- **In scope**: Warning emission (once per sprint run) when `use_feature_branches`
  is set and a wave runs in-place — covers both single-issue waves and contention
  sub-waves, which share the same path. Documentation of the limitation at toggle
  surfaces in `docs/guides/SPRINT_GUIDE.md` (coordinate with ENH-2174).
- **Out of scope**: Routing single-issue waves through a feature-branch-aware
  worktree path (Option A — deferred as a follow-up enhancement). `ll-auto`
  (sequential, in-place by design) is explicitly excluded per EPIC-2171.

## Success Metrics

- Warning fires exactly once per in-place sprint run (deduplicated; not per-wave)
  when `use_feature_branches` is set.
- No warning fires when `use_feature_branches` is unset or absent.
- `docs/guides/SPRINT_GUIDE.md` contains a documented coverage-boundary paragraph
  (coordinate with ENH-2174 description text).
- All new tests pass; no regression on the multi-issue `else` branch
  (`cli/sprint/run.py:489`).

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

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/run.py` is invoked by `ll-sprint run`; the
  warning change is self-contained within this file and does not affect callers.
- `scripts/little_loops/cli/sprint/config.py` (or equivalent) — provides
  `config.parallel.use_feature_branches`; read-only, no changes needed.

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — add coverage-boundary paragraph (also listed in
  Files to Modify; ENH-2174 must coordinate toggle-surface wording).

### Configuration
- N/A — no new config keys; `parallel.use_feature_branches` already exists.

## Implementation Steps

1. Add a guarded one-time warning in `scripts/little_loops/cli/sprint/run.py` at the single-issue / contention sub-wave branch (~line 437): when `config.parallel.use_feature_branches` is set and the wave runs in-place, emit a warning naming the current branch (use a flag to suppress repeats within the same sprint run).
2. Update `docs/guides/SPRINT_GUIDE.md` to document the coverage boundary at the toggle surface; coordinate wording with ENH-2174's description text.
3. Add tests in `scripts/tests/` covering both Option B cases: warning emitted when flag is set + in-place wave; no warning when flag is unset.
4. Verify no regression on the multi-issue `else` branch (`cli/sprint/run.py:489`) — flag must still honor `use_feature_branches` normally there.

## API/Interface

N/A — No public API changes. The warning is emitted to the existing sprint logger only; no new CLI flags, config keys, or Python API surface are introduced.

## Impact

- **Priority**: P3 — directly undermines the EPIC's "first-class toggle" goal;
  Option B (decided) is small and removes the silent-no-op surprise.
- **Effort**: Small — a guarded warning + a docs paragraph.
- **Risk**: Low — does not alter the in-place execution path, only adds a warning.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:23 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T20:12:41 - `50c8117c-6f1e-4df2-8979-885c3ae158c7.jsonl`
- `/ll:format-issue` - 2026-06-15T20:10:07 - `50c8117c-6f1e-4df2-8979-885c3ae158c7.jsonl`
- decision - 2026-06-15 - Option B (warn + document) selected; Option A (extend coverage to single-issue waves) deferred as a follow-up.
- `/ll:capture-issue` - 2026-06-15T17:30:00Z - promoted from EPIC-2171 Out of Scope

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2173's `--feature-branches` CLI flag flows into `create_parallel_config()` on the multi-issue orchestrator path (~line 489) but does **not** update `config.parallel.use_feature_branches` as read by the single-issue / contention sub-wave path (~line 437). This issue's warning check must resolve `use_feature_branches` from the CLI-merged value — not the raw sprint config — to avoid silently not firing when the flag is set via CLI rather than config. Either read the resolved value from the `ParallelConfig` produced by `create_parallel_config()`, or share a `resolve_feature_branches_flag(args, config)` helper introduced in [ENH-2173].
