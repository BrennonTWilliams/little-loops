---
id: ENH-2028
title: session_digest.enabled defaults off — ambient history context never fires
type: ENH
priority: P4
status: open
captured_at: "2026-06-08T22:17:25Z"
discovered_date: 2026-06-08
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [ENH-1907, EPIC-1707]
---

# ENH-2028: session_digest.enabled defaults off — ambient history context never fires

## Summary

ENH-1907 implemented the project-context snapshot (ambient `<project_context>` block injected at session start via `session_start.py`), but `SessionDigestConfig.enabled` defaults to `False` and the little-loops project itself has no `history:` block in `.ll/ll-config.json`. As a result, the most frictionless form of history injection silently never fires on any install, including the one where it was built. The feature is effectively invisible post-install.

## Motivation

The EPIC-1707 vision is "prior corrections, file edits, and tool-use patterns inform agent outputs without the user manually surfacing context." The ambient session-start digest is the only mechanism that achieves this for *every* skill and conversation without requiring per-skill `ll-history-context` calls. Keeping it opt-in means users never discover it; the value proposition depends on it being always-on with a cap, not on users knowing to configure it.

## Current Behavior

`SessionDigestConfig.enabled` defaults to `False` (`scripts/little_loops/config/features.py:658`). `session_start.py` gates the entire digest path on `feature_enabled(merged_config, "history.session_digest.enabled")`. With no `history:` block in the project config, `enabled` is never set to `True`, so the block is never generated and the hook exits without injecting anything.

## Expected Behavior

One of:
1. **(Preferred)** Change `SessionDigestConfig.enabled` default to `True` with a conservative `char_cap` (e.g. 800 chars) — opt-out rather than opt-in. Projects that don't want it can set `history.session_digest.enabled: false`.
2. **(Lighter)** Keep the global default as `False` but enable it in this project's `.ll/ll-config.json` so at minimum little-loops itself dogfoods the feature.
3. Wire `/ll:init` and `/ll:configure` to prompt about enabling session_digest during setup.

Option 1 is the right long-term default; option 2 is a quick fix for this project.

## Implementation Steps

### Option 1: Change default to True

1. In `scripts/little_loops/config/features.py`, change `SessionDigestConfig.enabled: bool = False` to `True`.
2. Update `SessionDigestConfig.from_dict` to default `enabled` to `True`.
3. Update `config-schema.json` and `docs/reference/API.md` to reflect the new default.
4. Add a migration note to `CHANGELOG.md` (behavior change — previously silent, now injects a capped digest).
5. Add/update tests in `scripts/tests/test_session_start.py` to assert the digest fires when no config is present.

### Option 2: Enable in project config (quick fix)

Add to `.ll/ll-config.json`:
```json
"history": {
  "session_digest": {
    "enabled": true,
    "days": 7,
    "char_cap": 1200
  }
}
```

### Option 3: Wire into init/configure

Update `skills/init/SKILL.md` Phase 3 and `skills/configure/SKILL.md` to include a `session_digest` prompt block.

## API / Interface Changes

- `SessionDigestConfig.enabled` default value changes (if option 1).
- `config-schema.json` default annotation for `history.session_digest.enabled`.
- No CLI surface changes.

## Tests

- `scripts/tests/test_session_start.py` — assert digest fires with default config (option 1), or assert it fires when config sets `enabled: true` (option 2).
- `scripts/tests/test_config_features.py` — verify `SessionDigestConfig()` default matches intended behavior.

## Session Log
- `/ll:capture-issue` - 2026-06-08T22:17:25Z - `a20cfa81-f228-4cd0-9501-12f64feb6d30.jsonl`

---

**Open** | Created: 2026-06-08 | Priority: P4
