---
id: BUG-3552
title: refine-to-ready-issue threshold states let ll-config shadow the --context override
type: BUG
priority: P3
status: open
discovered_date: '2026-09-24'
labels:
- loops
- refine-to-ready-issue
---

# refine-to-ready-issue threshold states let ll-config shadow the --context override

## Summary

The loop's `context:` comment documents `--context readiness_threshold=NN` as the
per-run override, and `fsm/context_seed.py:seed_confidence_thresholds` implements
the precedence `--context` > YAML > `commands.confidence_gate.*` > defaults. But
`check_readiness`, `check_outcome` and `check_scores_from_file` each re-read
`.ll/ll-config.json` inside their heredoc and use the context value only as the
fallback: `cg.get('readiness_threshold', <context>)`. Whenever the project config
sets `confidence_gate` the override is silently ignored.

## Current Behavior

`ll-loop run refine-to-ready-issue X --context readiness_threshold=70` in a
project whose config sets `readiness_threshold: 85` gates on 85.

## Expected Behavior

The states compare against `${context.readiness_threshold}` /
`${context.outcome_threshold}` directly — the runner has already seeded them
from config when no override was given.

## Steps to Reproduce

1. Set `commands.confidence_gate.readiness_threshold: 85` in `.ll/ll-config.json`.
2. Run the loop with a CLI override: `ll-loop run refine-to-ready-issue X --context readiness_threshold=70` on an issue scored 75.
3. `check_readiness` exits 1 (75 < 85) instead of 0 — the config value shadows the CLI override.

## Proposed Solution

Drop the in-state config read from the three heredocs; use the env var bound
from `${context.*_threshold:shell}`.

Out of scope: `check_lifetime_limit` has the same config-first shape for
`max_refine_count`, but the YAML `context:` literal (and recursive-refine's
passthrough literal) make an explicit override indistinguishable from the
default inside the state, so config-first is the only way config can win there.
Fixing it needs runner-side seeding like BUG-2767.

## Program Design

Loop YAML only (`scripts/little_loops/loops/refine-to-ready-issue.yaml`),
reusing `seed_confidence_thresholds` precedence; no Python changes.

## Impact

- **Priority**: P3 — documented override is dead in any configured project.
- **Effort**: Small.
- **Risk**: Low — values are identical when no override is passed.

## Acceptance Criteria

- No `ll-config.json` read remains in `check_readiness` / `check_outcome` / `check_scores_from_file`.
- A regression test asserts the states do not read config.

## Related

- BUG-2767 (runner seeding), BUG-3551, BUG-3553

## Status

Open
