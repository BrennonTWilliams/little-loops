---
id: ENH-2187
title: Config probe — add .gemini/ll-config.json to _config_candidates()
type: enhancement
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179]
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, config]
---

# ENH-2187: Config probe — .gemini/ll-config.json in _config_candidates()

## Summary

Add `.gemini/ll-config.json` as a probe path in
`scripts/little_loops/config/core.py _config_candidates()`, mirroring the
existing host-conditional `.codex/ll-config.json` probe. The gemini candidate
must be added under a `host == "gemini"` branch (prepended ahead of the
unconditional `.ll/ll-config.json` and root `ll-config.json` candidates) — not
appended to an always-present list. There is no `.claude/ll-config.json` probe
to mirror: `_config_candidates()` (config/core.py:91-96) only conditionally
prepends `.codex/ll-config.json` when `host == "codex"`, then unconditionally
appends `.ll/ll-config.json` and root `ll-config.json`.

Gemini projects use `.gemini/` as their per-project config directory
(confirmed by FEAT-2179: `.gemini/settings.json` is Gemini's settings file).

## Use Case

A user with a Gemini project wants to place their little-loops config in
`.gemini/ll-config.json` alongside their Gemini settings. Without this probe,
they must use `.ll/ll-config.json` exclusively.

## Implementation Steps

1. Open `scripts/little_loops/config/core.py`, find `_config_candidates()`.
2. Add a `host == "gemini"` branch that prepends `.gemini/ll-config.json`,
   mirroring the existing `host == "codex"` branch — ahead of the unconditional
   `.ll/ll-config.json` and root `ll-config.json` candidates.
3. Add a test in `scripts/tests/test_config.py`:
   - `test_config_probe_finds_gemini_config` — verify `.gemini/ll-config.json`
     is resolved when present.

## Acceptance Criteria

- `_config_candidates()` includes `.gemini/ll-config.json`, prepended only under
  the `host == "gemini"` branch.
- A project with `.gemini/ll-config.json` resolves that file as the config source
  when `host == "gemini"`.
- Existing candidates (`.codex/ll-config.json` host-conditional probe,
  unconditional `.ll/ll-config.json` and root `ll-config.json`) are unaffected.
- Test passes.

## API/Interface

### Files to Modify

- `scripts/little_loops/config/core.py` — `_config_candidates()`
- `scripts/tests/test_config.py` — probe test

## Impact

- **Effort**: XS (< 30 minutes)
- **Risk**: Very low — additive probe; no existing config behavior changes
- **Breaking Change**: No

---

## Verification Notes

2026-06-18 (ACCURATE): `_config_candidates()` in `scripts/little_loops/config/core.py` does not include `.gemini/ll-config.json`. FEAT-2179 confirmed `.gemini/settings.json` as Gemini's settings file. Change is unimplemented; XS effort estimate appears correct.

- **2026-06-26** (/ll:verify-issues): Removed false claim of an existing `.claude/ll-config.json` probe (no such probe exists); reframed Summary, step 2, and Acceptance Criteria so the gemini candidate is added host-conditionally under a `host == "gemini"` branch, mirroring the `.codex/` branch rather than appended to an unconditional list.

**Open** | Created: 2026-06-15 | Priority: P4
