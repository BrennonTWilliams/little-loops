---
id: EPIC-3436
type: EPIC
title: 'Restore CI unit-suite signal: fix the 6 root causes behind the 7 chronic failures'
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
---

# EPIC-3436: Restore CI unit-suite signal: fix the 6 root causes behind the 7 chronic failures

## Summary

[Description extracted from input]

## Motivation

[Why this epic matters - business value, user impact, strategic goal]

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Tests
- TBD - identify shared test infrastructure

### Documentation
- TBD - docs that need updates

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Goal

## Scope

## Children
- **BUG-3437** — SSE fan-in backoff never engages; producers at max_clients re-probed ~10/s forever (open)
- **BUG-3438** — rn-refine commit_leaf reports COMMITTED without committing and routes failure to record_leaf_done (open)
- **BUG-3439** — FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above 128 KiB (open)
- **BUG-3440** — ll-doctor reports a corrupt history.db as healthy on Linux SQLite builds (open)
- **ENH-3441** — load_design_tokens falls back to packaged profiles when .ll/design-tokens/ mirror is absent (open)
- **BUG-3442** — CI shallow checkout makes the evidence gate structurally unable to pass (open)
- **BUG-3443** — test_env_var_overrides_cpu_count asserts against host CPU count instead of patching os.cpu_count (open)








## Success Metrics

## Session Log
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
