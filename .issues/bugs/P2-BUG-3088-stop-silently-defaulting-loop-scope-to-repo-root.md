---
id: BUG-3088
type: BUG
title: Stop silently defaulting unscoped loops' lock to the repo root
priority: P2
status: open
parent: BUG-3083
captured_at: '2026-08-06T16:17:02Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- fsm-concurrency
- learning-gate
- ll-auto
- loop-authoring
relates_to:
- BUG-2864
- BUG-3083
- BUG-3087
- BUG-3085
---

# BUG-3088: Stop silently defaulting unscoped loops' lock to the repo root

## Summary

This is the durable-fix half of BUG-3083 ("Unscoped issue-management loops
lock the whole repo, false-conflicting every narrowly-scoped loop"). Giving
individual loops real scopes ([[BUG-3087]]) fixes the loops we know about
today, but any of the remaining 84 built-in loops (and any loop authored in
the future) that omits `scope:` still silently acquires a repo-root lock via
`cmd_run()`'s `scope = resolve_scope(fsm.scope or ["."], fsm.context)`
(`run.py:363`). This issue addresses that policy gap directly, so a missing
`scope:` stops being silently promoted to "this loop owns the entire
repository."

Do not treat `--queue` as the fix. It converts a hard failure into a long
wait and is orthogonal to loops over-claiming scope (see BUG-3085).

## Parent Issue

Decomposed from [BUG-3083](P2-BUG-3083-unscoped-loops-lock-whole-repo-false-gate-conflicts.md):
Unscoped issue-management loops lock the whole repo, false-conflicting every
narrowly-scoped loop.

## Root Cause

`little_loops.cli.loop.run.cmd_run` — `scope = resolve_scope(fsm.scope or ["."], fsm.context)`
(`run.py:363`). The `or ["."]` fallback means "loop author did not think
about scope" is silently promoted to "this loop owns the entire repository."
The same fallback is independently duplicated in `run_background()`
(`cli/loop/_helpers.py:1552`) and defensively again in
`LockManager.acquire()` (`fsm/concurrency.py:163-164`).

## Current Behavior

84 of the 91 built-in loops declare no `scope:` and therefore lock the repo
root at runtime. `cmd_info`'s loop-detail display only prints a `scope:`
line when `fsm.scope` is truthy, so an unscoped loop is shown as having no
scope even though it locks the repo root — there's no visibility into the
effective behavior.

## Expected Behavior

A loop that has not declared `scope:` should either (a) be nudged by
tooling to declare a real scope, or (b) not be silently treated as owning
the repo root by default — chosen per the decision below.

## Proposed Solution

Decide between the two options below, then implement consistently across
every fallback site. Prerequisite: audit the 84 scope-less loops and
classify each as genuinely repo-wide vs. should-be-narrow, recording the
classification in this issue before making the change — the chosen option
must not silently narrow (or fail to narrow) loops that legitimately need a
broad scope, e.g. `fix-quality-and-tests.yaml`, `incremental-refactor.yaml`.

- **Option A — lint warning**: `ll-loop validate` warns when a loop declares
  no `scope:` (mirrors the MR-1..MR-14 lint surface), so new loops get a
  scope at authoring time. Follow the shape of
  `_validate_input_key_without_guard`
  (`fsm/validation/structural_rules.py:1195-1217`) — single-condition
  early-return, one `ValidationError(severity=ValidationSeverity.WARNING)`,
  actionable message.
- **Option B — narrow the implicit default**: change the default to
  `["${context.run_dir}"]` and require an explicit `scope: ["."]` for loops
  that genuinely mutate the whole repo. This is a behavior change and
  depends on the audit above to avoid breaking loops that need the broad
  scope.

Whichever option is chosen must be applied at **every** fallback site, not
just `cmd_run()`:

- `scripts/little_loops/cli/loop/run.py:363` — `cmd_run()`'s
  `resolve_scope(fsm.scope or ["."], fsm.context)`.
- `scripts/little_loops/cli/loop/_helpers.py:1552` — `run_background()`'s
  independent, second occurrence of the identical fallback (the pre-flight
  check used for `--background` runs), plus its own
  `"Scope conflict with running loop"` / `"Conflicting scope"` print at
  lines 1559-1560.
- `scripts/little_loops/fsm/concurrency.py:163-164` — `LockManager.acquire()`'s
  own redundant `if not scope: scope = ["."]` defensive fallback at the
  lock-manager layer, independent of both CLI-layer fallbacks.

Also update, once the option is chosen:

- `scripts/little_loops/cli/loop/info.py:1540-1541` — `cmd_info`'s
  loop-detail display should reflect the resolved effective scope, not just
  the declared one.
- `scripts/little_loops/cli/sprint/run.py:198-262` —
  `_run_learning_gate_preflight()` shells out to
  `ll-loop run ready-to-implement-gate` with no `--queue` and no inline
  comment acknowledging the scope-conflict mechanism; add one.
- `scripts/little_loops/parallel/worker_pool.py:52-89` —
  `_run_per_worktree_proof_first_gate()` explicitly mirrors
  `cli/sprint/run.py`'s preflight ordering (line 66) and has the same gap.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/cli/loop/run.py` | `cmd_run`, line 363 | Default-scope policy |
| `scripts/little_loops/cli/loop/_helpers.py` | `run_background()`, line 1552 | Same default-scope policy, kept in sync with `run.py` |
| `scripts/little_loops/fsm/concurrency.py` | `LockManager.acquire()`, lines 163-164 | Same default-scope policy at the lock-manager layer |
| `scripts/little_loops/fsm/validation/structural_rules.py` | new rule, pattern of `_validate_input_key_without_guard` (lines 1195-1217) | Optional no-scope WARNING lint rule (Option A) |
| `scripts/little_loops/fsm/validation/__init__.py` | `__all__` | Export the new rule if Option A is chosen |
| `scripts/little_loops/cli/loop/info.py` | lines 1540-1541 | Reflect resolved effective scope, not just declared |
| `scripts/little_loops/cli/sprint/run.py` | `_run_learning_gate_preflight()`, lines 198-262 | Acknowledge scope-conflict mechanism |
| `scripts/little_loops/parallel/worker_pool.py` | `_run_per_worktree_proof_first_gate()`, lines 52-89 | Acknowledge scope-conflict mechanism |

### Documentation

- `docs/guides/LOOPS_GUIDE.md:786-816,848-849` — "Scope-Based Concurrency"
  section documents `scope:` mechanics but has no mention of the current
  `["."]` default-when-absent behavior; the "Notes" bullet at line 849
  ("Loops with non-overlapping scopes run concurrently") is inaccurate for
  any unscoped loop today.
- `docs/development/TROUBLESHOOTING.md:812-827,1285` — existing
  "Scope conflict" troubleshooting entries describe stale-lock symptoms
  only, not the false-conflict-from-unscoped-loop mechanism.
- `docs/reference/API.md:5179,6162-6207` — mirrors `FSMLoop.scope` field
  docstring and the `LockManager`/`resolve_scope` reference block; update if
  the fallback's shape changes.
- `docs/reference/CLI.md:789-812` — enumerates every `ll-loop validate`
  structural/meta-loop lint rule in a fixed format (severity, trigger,
  rationale, suppression flag); add a new no-scope WARNING rule here in the
  same format if Option A is chosen.

### Tests

- `scripts/tests/test_cli_loop_background.py::TestRunBackground` —
  `test_scope_conflict_returns_1` (line 671),
  `test_no_lock_bypasses_scope_conflict` (line 733),
  `test_queue_bypasses_preflight_check` (line 706) are **break-risk**: they
  rely on the `my-loop.yaml` fixture (line 190-197, no `scope:` field)
  resolving to `["."]` and conflicting with a `["."]`-scoped `blocker` lock.
  If Option B is chosen, update this fixture and these three tests so they
  still exercise a genuine conflict.
- `scripts/tests/test_fsm_validation_structural.py::TestRequiredInputsValidation`
  (line 1539) — pattern to follow if Option A is chosen: `_make_fsm()`
  helper, direct-call trigger/non-trigger tests, plus
  `..._wired_into_validate_fsm` variants asserting dispatch from
  `validate_fsm()`.

## Implementation Steps

1. Audit the 84 `scope:`-less loops and classify: genuinely repo-wide vs.
   should-be-narrow. Record the classification in the issue before editing.
2. Decide Option A (lint warning) vs. Option B (narrow the default).
3. Implement the chosen option at all three fallback sites (`run.py:363`,
   `_helpers.py:1552`, `concurrency.py:163-164`).
4. Update `info.py`'s scope display, the two preflight-gate callers
   (`cli/sprint/run.py`, `parallel/worker_pool.py`), and the break-risk
   fixture/tests in `test_cli_loop_background.py` if Option B is chosen.
5. Update `LOOPS_GUIDE.md`, `TROUBLESHOOTING.md`, `API.md`, and `CLI.md`.

## Impact

- **Severity**: silent, non-deterministic loss of automated work for any
  future unscoped loop, not just the six named in [[BUG-3087]].
- **Blast radius**: broad — touches at least three independent CLI/lock
  fallback sites plus two preflight-gate callers; a change that misses one
  site leaves it un-narrowed while the others move.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM concurrency / scope-lock design |
| `.claude/CLAUDE.md` § Loop Authoring | Where a `scope:` authoring rule would live |

## Status

open


## Session Log
- `/ll:issue-size-review` - 2026-08-06T16:59:24 - `23212449-a121-4dca-9bc5-bc0a0164c75f.jsonl`
