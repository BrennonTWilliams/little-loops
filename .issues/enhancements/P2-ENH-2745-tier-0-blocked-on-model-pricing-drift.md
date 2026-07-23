---
id: ENH-2745
type: ENH
title: Tier 0 before/after cost gate blocked on model-pricing drift
priority: P2
status: open
captured_at: '2026-07-23T01:37:52Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- observability
- pricing
relates_to:
- EPIC-2456
- ENH-2719
- FEAT-2470
- ENH-2518
---

# ENH-2745: Tier 0 before/after cost gate blocked on model-pricing drift

## Summary

ENH-2719's realized-savings verification pass found that FEAT-2470's Tier 0
before/after cost-delta gate cannot currently be computed against the ENH-2518
locked baseline. `MODEL_PRICING` (`scripts/little_loops/pricing.py`) has no
entries for `claude-sonnet-5` or `claude-opus-4-8` — the models every loop run
on disk from 2026-07-20 onward actually uses. `CostReport.from_usage_jsonl`
returns `cost_usd: 0.0` / `has_unknown_model: true` for any of these traces.

## Current Behavior

- The locked Tier 0 trace set (`scripts/tests/fixtures/tier0_traces/manifest.json`,
  owner ENH-2518) is pinned to `single_model_only: claude-sonnet-4-6`.
- The only post-FEAT-2470 `general-task` run on disk
  (`.loops/runs/general-task-20260707T133447/usage.jsonl`, 2026-07-07) uses
  `MiniMax-M3[1m]`, which is also unpriced.
- Every loop run since 2026-07-20 uses `claude-sonnet-5` or
  `claude-opus-4-8[1m]` — neither is in `MODEL_PRICING`.

## Expected Behavior

Either `MODEL_PRICING` carries entries for the fleet's current default
model(s), or a new Tier 0 baseline is locked against whichever model is
actually in production use, so a same-model (or same-regime) before/after
cost delta can be computed for FEAT-2470's success gate.

## Proposed Solution

1. Add `claude-sonnet-5` / `claude-opus-4-8` (and any other actively-used
   models found via `usage_events.model` in `.ll/history.db`) to
   `MODEL_PRICING` with current published pricing.
2. Decide whether to relock a new Tier 0 baseline against the current
   default model (superseding ENH-2518's `claude-sonnet-4-6` set) or keep
   the existing set as a historical reference and diff same-model traces
   only when they recur.
3. Re-run the Tier 0 before/after measurement once pricing/baseline is
   resolved; update `docs/observability/realized-savings-verification.md`.

## Impact

- **Priority**: P2 — blocks the only unmeasured piece of EPIC-2456's Tier 0
  gate; no user-facing behavior change.
- **Effort**: Small — pricing table entries are data, not logic changes;
  relocking a baseline follows the ENH-2518 precedent.
- **Risk**: Low.

## Labels

`token-cost`, `observability`, `pricing`, `captured`

## Status

**Open** | Created: 2026-07-23 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-23T01:37:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b068faa-9da8-4bec-af30-feafda6b3309.jsonl`
