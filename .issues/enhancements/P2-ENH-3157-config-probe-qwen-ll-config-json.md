---
id: ENH-3157
title: Config probe — .qwen/ll-config.json in _config_candidates()
type: ENH
status: done
priority: P2
parent: EPIC-3154
captured_at: '2026-08-13T01:28:37Z'
discovered_date: 2026-08-12
discovered_by: capture-issue
labels:
- qwen
- host-compat
completed_at: '2026-08-13T03:00:00Z'
---

# ENH-3157: Config probe — .qwen/ll-config.json in _config_candidates()

## Summary

Add a host-specific `ll-config.json` candidate for Qwen Code in
`scripts/little_loops/config/core.py`: `QWEN_CONFIG_DIR = ".qwen"` and a
`.qwen/ll-config.json` entry in `_config_candidates()`, following the
`.codex/` → `.gemini/` → `.omp/` → `.kimi-code/` precedent. Triggered by
`LL_HOOK_HOST` / `LL_STATE_DIR` as the existing candidates are.

## Motivation

Host-scoped config discovery lets ll find its config in the place a
Qwen-only repo keeps tool state, without forcing a shared `.ll/` dir. The
probe order matters: `.qwen/ll-config.json` must be probed BEFORE
`.ll/ll-config.json` (host-specific wins), and appended after the existing
host candidates so existing resolution is unchanged for current users.

## Implementation Steps

1. Add `QWEN_CONFIG_DIR = ".qwen"` constant.
2. Insert the `.qwen/ll-config.json` candidate in `_config_candidates()` at
   the position consistent with the established host ordering (after the
   existing host dirs, before `.ll/`).
3. Unit tests in the config test module mirroring the kimi-code candidate
   tests (candidate present, precedence vs `.ll/`, `LL_HOOK_HOST=qwen`
   trigger).

## Integration Map

### Files to Modify

- `scripts/little_loops/config/core.py` — `QWEN_CONFIG_DIR`, `_config_candidates()`
- config test module — candidate precedence tests (mirror kimi-code tests)

### New Files

- None.

### Dependent Files

- `ll-init` / `ll-doctor` config resolution consume the candidate list.

## Impact

- **Priority**: P2 — independent track; small but required for full host parity.
- **Effort**: XS — one constant, one candidate entry, tests.
- **Risk**: Low — additive; probe appended, no existing resolution change.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): `QWEN_CONFIG_DIR = ".qwen"` + `_config_candidates()`
branch landed in `config/core.py` (after the kimi-code candidate, before
`.ll/`), docstrings updated in `_config_candidates` and `resolve_config_path`.
Three tests added to `test_config.py` mirroring the kimi-code set
(`LL_HOOK_HOST=qwen` precedence, `LL_STATE_DIR=.qwen` trigger, ignored
without host env) — all green.

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2
