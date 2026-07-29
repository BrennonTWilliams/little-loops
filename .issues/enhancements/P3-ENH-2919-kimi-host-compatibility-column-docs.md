---
id: ENH-2919
title: HOST_COMPATIBILITY.md kimi-code column + docs/kimi/ onboarding
type: ENH
status: open
priority: P3
parent: EPIC-2910
captured_at: "2026-07-29T15:55:00Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- kimi
- host-compat
---

# ENH-2919: HOST_COMPATIBILITY.md kimi-code column + docs/kimi/ onboarding

## Summary

Complete the kimi-code column across the remaining
`docs/reference/HOST_COMPATIBILITY.md` tables and land the `docs/kimi/`
onboarding trio mirroring `docs/codex/`. Final gate for EPIC-2910 — closes
once every cell is ✓, ✗+footnote, or N/A.

## Motivation

The parity matrix column is the epic's end-state acceptance. The adapter row
already landed with FEAT-2916 (atomic requirement); this child completes the
rest as the implementation children land, so the matrix never carries unknown
or untracked cells. `docs/ARCHITECTURE.md` gains `KimiRunner` in the
component table, and new kimi users get a dedicated onboarding path.

## Implementation Steps

1. Complete the kimi-code column across the remaining tables: hook intents,
   discovery, runner capabilities, orchestration CLI, config probe, state
   directory, installation, env vars (adapter row already landed with
   FEAT-2916).
2. Cells are ✓ / ✗+footnote / N/A; add the spike-linked footnote to
   `thoughts/research/kimi-cli-surface.md`; bump Last Updated/Verified.
3. Add `KimiRunner` to the `docs/ARCHITECTURE.md` component table.
4. Write the `docs/kimi/` onboarding trio mirroring `docs/codex/`: install,
   hook events, automation quickstart.
5. Keep `ll-doctor --full` green.

## Integration Map

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — kimi-code column completion
- `docs/ARCHITECTURE.md` — `KimiRunner` in component table

### New Files

- `docs/kimi/` — onboarding trio (install, hook events, automation quickstart)

### Dependent Files

- `thoughts/research/kimi-cli-surface.md` — footnote target (FEAT-2911, done)
- All implementation children (ENH-2912/2913, FEAT-2914/2915/2916/2917, ENH-2918) — cell sources

## Impact

- **Priority**: P3 — final gate; lands last.
- **Effort**: S — documentation only.
- **Risk**: Low — docs; main risk is flipping cells before their children land.
- **Breaking Change**: No.

## Session Log
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P3
