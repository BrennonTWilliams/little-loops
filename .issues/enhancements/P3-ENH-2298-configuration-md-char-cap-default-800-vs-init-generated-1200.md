---
title: CONFIGURATION.md documents char_cap default as 800 but ll-init generates 1200
priority: P3
type: ENH
status: done
discovered_by: audit-docs
captured_at: 2026-06-25 00:00:00+00:00
completed_at: 2026-06-25 22:56:18+00:00
labels:
- docs
- config
---

# ENH-2298: CONFIGURATION.md documents char_cap default as 800 but ll-init generates 1200

## Summary

`docs/reference/CONFIGURATION.md` documents `history.session_digest.char_cap` default as `800`, but `scripts/little_loops/init/core.py:115` always writes `1200` to the generated config and `scripts/little_loops/history_reader.py:1021` uses `1200` as its function parameter default. Any user who ran `ll-init` has `1200` in their config; the docs should reflect the init-generated value.

## Motivation

Users who consult `docs/reference/CONFIGURATION.md` to understand the `char_cap` default get the wrong value (`800` instead of `1200`), which can lead to misconfigured settings if they rely on the documented default. Every project created with `ll-init` has `1200` in its config, creating a silent divergence between what users read and what their tools actually use.

## Current Behavior

`docs/reference/CONFIGURATION.md:544` table row:

```
| `history.session_digest.char_cap` | `integer` | `800` | Hard character ceiling on the injected block. Truncates with `+N more`. |
```

But:
- `scripts/little_loops/init/core.py:115` writes `"char_cap": 1200` to generated configs
- `scripts/little_loops/history_reader.py:1021` uses `char_cap: int = 1200` as function default
- `config-schema.json` and `config/features.py:SessionDigestConfig` use `800`

## Expected Behavior

The documentation, schema, init-generated value, and function defaults should all agree on `1200` as the `char_cap` default value.

## Proposed Solution

**Option B (recommended)** — Align all four sources to `1200` (single source of truth):
- Update `config-schema.json` default to `1200`
- Update `SessionDigestConfig.char_cap` field default to `1200` and `SessionDigestConfig.from_dict` fallback to `1200`
- Remove the explicit `"char_cap": 1200` from `build_config` in `init/core.py` (let schema default flow through)
- Update `CONFIGURATION.md` table row to `1200`
- `render_project_context` in `history_reader.py` already uses `1200` — no change needed

**Option A** (doc-only fix): Update only `CONFIGURATION.md` to say `1200`, with a note that the schema default is `800` and `ll-init` generates `1200`. Faster but leaves technical debt.

## Integration Map

- `docs/reference/CONFIGURATION.md` — table row for `history.session_digest.char_cap` default value
- `config-schema.json` — `properties.history.properties.session_digest.properties.char_cap.default`
- `scripts/little_loops/config/features.py` — `SessionDigestConfig.char_cap` field default; `SessionDigestConfig.from_dict` dict fallback
- `scripts/little_loops/init/core.py` — `build_config` explicit `"char_cap": 1200` write (remove if Option B)
- `scripts/little_loops/history_reader.py` — `render_project_context` parameter default `char_cap: int = 1200` (already correct, no change needed)

## Implementation Steps

1. Decide Option A vs B (recommendation: B — single source of truth)
2. Update `config-schema.json` default to `1200`
3. Update `SessionDigestConfig.char_cap` to `1200` and `data.get("char_cap", 1200)`
4. Remove the explicit `"char_cap": 1200` from `init/core.py` (let the schema default flow)
5. Update `CONFIGURATION.md:544` table row to `1200`
6. Verify `history_reader.py` function parameter is already `1200` (no change needed)

## Scope Boundaries

- Out of scope: changing behavior for projects with `char_cap` explicitly set in their config (explicit values always take precedence over defaults)
- Out of scope: changing what `char_cap` controls or adding new configuration options
- Out of scope: migrating existing configs — the default change only affects projects where `char_cap` is absent from their config

## Impact

**Priority**: P3 — Minor docs/config inconsistency; no user-visible breakage (both values produce a working config)
**Effort**: Small — one table cell + two Python files + one JSON schema
**Risk**: Low — changing from `800` to `1200` only affects projects with no explicit `char_cap` set; those projects will get a slightly larger session digest block (1200 vs 800 chars)
**Breaking Change**: No — default change only; explicit configs are unaffected

## Status

**Open** | Created: 2026-06-25 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-25T22:50:23 - `8250e2ae-7235-4c3e-b708-0ac406dbb582.jsonl`
- `/ll:format-issue` - 2026-06-25T22:48:06 - `479964a1-4504-41c8-af31-5efe7fedd357.jsonl`
