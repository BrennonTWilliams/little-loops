---
id: ENH-2913
title: Config probe — .kimi-code/ll-config.json in _config_candidates()
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

# ENH-2913: Config probe — .kimi-code/ll-config.json in _config_candidates()

## Summary

Add `KIMI_CONFIG_DIR = ".kimi-code"` to the host-dir constants in
`scripts/little_loops/config/core.py` (:48-52) and one branch in
`_config_candidates()` (:85-113) that prepends `.kimi-code/ll-config.json`
when `host == "kimi-code"` or `state_dir == ".kimi-code"`.

## Motivation

Host-specific config probes let each host carry its own `ll-config.json`
without colliding with Claude's `.claude/` directory. kimi-code's native
config dir is `.kimi-code` per the FEAT-2911 spike. XS and fully independent
of the runner and hook-adapter work.

## Implementation Steps

1. Add `KIMI_CONFIG_DIR = ".kimi-code"` alongside the other host dir
   constants (`scripts/little_loops/config/core.py:48-52`).
2. Add one branch in `_config_candidates()` (:85-113) prepending
   `.kimi-code/ll-config.json` when `host == "kimi-code"` or
   `state_dir == ".kimi-code"`.
3. Extend the config probe tests to cover the kimi-code branch.

## Integration Map

### Files to Modify

- `scripts/little_loops/config/core.py` — constant + `_config_candidates()` branch
- `scripts/tests/` config probe tests — kimi-code branch coverage

### New Files

- None.

### Dependent Files

- `docs/reference/HOST_COMPATIBILITY.md` — config probe cell, flipped by ENH-2919

## Impact

- **Priority**: P3 — small additive probe; no user workflow blocked on it.
- **Effort**: XS (< 1 hour).
- **Risk**: Very low — additive branch, no existing probe path changes.
- **Breaking Change**: No.

## Session Log
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P3
