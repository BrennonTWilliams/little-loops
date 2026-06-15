---
id: ENH-2180
title: Add per-run disable for use_feature_branches (--no-feature-branches)
type: ENH
status: open
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T00:00:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, sprint, cli, feature-branches, dx]
relates_to: [ENH-2173, ENH-2174]
---

# ENH-2180: Add per-run disable for use_feature_branches (--no-feature-branches)

## Summary

Make the `use_feature_branches` CLI override symmetric: add a
`--no-feature-branches` form so a user can turn feature-branch mode **off** for a
single run when the config default is `true`, mirroring the `--feature-branches`
enable flag from ENH-2173.

## Motivation

ENH-2173 adds `--feature-branches` (a `store_true` flag, default `None`) that can
only *enable* feature-branch mode for a run. ENH-2174 makes the config flag
discoverable and easy to set, so users will start setting
`parallel.use_feature_branches: true` as their default. Once that default is on,
there is **no way to disable it for a single run** — the user must hand-edit
config and revert it afterward, which is exactly the friction ENH-2173 set out to
remove, just in the opposite direction.

A genuinely first-class toggle is symmetric: it can be flipped on *and* off per
run without touching config. Today's design only covers half of that.

## Current Behavior (post-ENH-2173)

- `cli/parallel.py` exposes `--feature-branches` as `store_true` (default `None`);
  `args.feature_branches or None` is passed to `create_parallel_config()`.
- With `store_true`, an unset flag is indistinguishable from "leave at config
  default" — there is no token that means "force off". So when config is `true`,
  the flag can never override to `false`.
- Same gap on `ll-sprint run --feature-branches`.

## Expected Behavior

- `ll-parallel --no-feature-branches` forces feature-branch mode **off** for that
  run regardless of the config value.
- `ll-parallel --feature-branches` forces it **on** (unchanged from ENH-2173).
- Omitting both falls back to the config value (no behavior change for existing
  users).
- `ll-sprint run` honors both forms identically.

## Proposed Solution

Replace the `store_true` flag with a tri-state that distinguishes on / off /
unset. Preferred: `argparse.BooleanOptionalAction` (Python 3.9+), which yields
`--feature-branches` / `--no-feature-branches` from a single `add_argument` with
`default=None`:

1. In `cli/parallel.py`, change the `--feature-branches` entry to
   `action=argparse.BooleanOptionalAction, default=None`.
2. Pass `args.feature_branches` straight through (it is already `True` / `False` /
   `None`); drop the `or None` coercion so an explicit `False` survives.
3. `create_parallel_config(use_feature_branches=...)` (ENH-2173) already resolves
   `None → config default`, so `False` now correctly forces off with no further
   change.
4. Apply the same flag swap in `cli/sprint/run.py`.

This composes cleanly with ENH-2173 — it is the same parameter, just a richer
flag surface. If ENH-2173 has already landed with `store_true`, this issue is the
follow-up that upgrades it; if not yet landed, fold this into ENH-2173's flag
definition.

## API/Interface

- CLI: `ll-parallel --feature-branches` / `--no-feature-branches`;
  `ll-sprint run --feature-branches` / `--no-feature-branches`.
- No change to `create_parallel_config()`'s signature beyond ENH-2173 (it already
  accepts `use_feature_branches: bool | None`).

## Acceptance Criteria

1. `ll-parallel --no-feature-branches` forces feature-branch mode off even when
   `parallel.use_feature_branches: true` in config.
2. `ll-parallel --feature-branches` forces it on even when config is `false`
   (ENH-2173 behavior preserved).
3. Omitting both flags falls back to the config value.
4. `ll-sprint run` honors both forms.
5. Tests cover the full truth table: `--feature-branches` → True;
   `--no-feature-branches` → False; neither + config True → True;
   neither + config False → False.

## Scope Boundaries

- **In scope**: the negation flag and the tri-state plumbing on `ll-parallel` and
  `ll-sprint run`.
- **Out of scope**: changing the config default value; any change to
  feature-branch *behavior* (push/PR is BUG-2172); negation for the push/PR
  sub-flags (can follow the same pattern later if those flags get CLI surfaces).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/parallel.py` — swap `--feature-branches` to
  `BooleanOptionalAction`; pass the tri-state value through unchanged
- `scripts/little_loops/cli/sprint/run.py` — same flag swap; thread into
  `create_parallel_config`
- `scripts/little_loops/config/core.py` — no change expected (ENH-2173's
  `None`-means-default resolution already handles explicit `False`); verify

### Similar Patterns
- ENH-2173's `--feature-branches` definition — this issue upgrades it in place
- Any existing `BooleanOptionalAction` usage in the CLI argument builders

### Tests
- `scripts/tests/test_config.py` — `create_parallel_config(use_feature_branches=False)`
  forces off when config is `True`
- CLI argument-parsing tests for `ll-parallel` / `ll-sprint run` — both flag forms

### Dependencies
- **ENH-2173** — defines the override parameter and the enable flag this issue
  makes symmetric. Sequence after ENH-2173 (or fold the negation into it).

## Impact

- **Priority**: P3 — completes the "first-class toggle" goal (symmetric on/off per
  run); without it the toggle is one-directional once config is on.
- **Effort**: Small — a single argparse change per CLI entry + tests.
- **Risk**: Low — additive; `None` default preserves current behavior.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15 - added to EPIC-2171 (symmetric-toggle gap identified during EPIC review)
