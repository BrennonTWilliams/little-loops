---
id: BUG-2311
title: "ll-init writes null leaves (build_cmd/run_cmd/mode) to generated config"
type: BUG
status: open
priority: P2
captured_at: "2026-06-26T21:55:52Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
labels:
- init
- config
relates_to:
- BUG-2310
---

# BUG-2311: ll-init writes null leaves (build_cmd/run_cmd/mode) to generated config

## Summary

A freshly generated `.ll/ll-config.json` contains `null`-valued leaf keys copied
verbatim from the project-type template and from `build_config`'s own defaults.
These nulls are noise at best and a footgun once config-merge semantics are
involved (a `None` is a key-removal sentinel for `deep_merge`).

## Current Behavior

`build_config()` copies the template project block via
`dict(data.get("project", {}))` (`scripts/little_loops/init/core.py:56`). The
project-type templates carry `build_cmd: null` / `run_cmd: null`, so every fresh
config gets:

```json
"project": { "build_cmd": null, "run_cmd": null }
```

And `build_config` itself writes (`core.py:121-127`):

```json
"loops": { "run_defaults": { "mode": null } }
```

This is the recurring "null template value" concern. `test_init_core.py:525`
currently asserts `mode is None` is intentional.

## Expected Behavior

Generated configs omit unset optional keys rather than persisting `null` leaves
(or, if a key must be present for schema reasons, it carries a real default, not
`null`).

## Root Cause

1. `build_config` shallow-copies template `project` including `null` leaves.
2. `build_config` explicitly sets `loops.run_defaults.mode = None`.

## Proposed Fix

Strip `None`-valued leaves before serialisation in `build_config` (recursively),
or omit `build_cmd`/`run_cmd`/`mode` when unset. Update
`test_init_core.py:511-538` to assert absence rather than `None`. Coordinate with
BUG-2310: stripping nulls is also what makes `deep_merge`-based re-init safe (a
`None` leaf would otherwise delete the user's key on merge).

## Impact

Cosmetic for fresh installs; correctness-relevant once BUG-2310's deep_merge lands
(null leaves would silently delete user keys). Worth fixing alongside BUG-2310.

## Labels

- init, config

## Session Log
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
