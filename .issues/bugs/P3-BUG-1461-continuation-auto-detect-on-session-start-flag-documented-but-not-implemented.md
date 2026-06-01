---
id: BUG-1461
title: `continuation.auto_detect_on_session_start` flag is documented but not read by any code
type: BUG
priority: P3
status: open
testable: false
discovered_date: 2026-05-14
discovered_by: verify-issues
relates_to: [FEAT-948]
decision_needed: false
---

# BUG-1461: `continuation.auto_detect_on_session_start` flag is documented but not read by any code

## Summary

The `continuation.auto_detect_on_session_start` boolean is documented in `docs/guides/SESSION_HANDOFF.md`, `docs/reference/CONFIGURATION.md`, and declared in `config-schema.json` as if it were a working setting, but no code anywhere reads it. Setting it to `false` has no effect.

## Current Behavior

- `config-schema.json:552` defines the property with `type: boolean` and description "Check for continuation prompt when session starts".
- `docs/reference/CONFIGURATION.md:120,411` shows it in example config and the settings table.
- `docs/guides/SESSION_HANDOFF.md:292,314,331` documents the on/off behavior and states: "When `continuation.auto_detect_on_session_start` is `true` (the default), little-loops checks for an existing `.ll/ll-continue-prompt.md` at the beginning of each session."
- A grep across `scripts/`, `hooks/`, and `commands/` for `auto_detect_on_session_start` finds **only** the schema and doc references — no implementation reads the flag.

## Steps to Reproduce

1. In a little-loops project, set `continuation.auto_detect_on_session_start: false` in `.ll/ll-config.json`.
2. Drop a `.ll/ll-continue-prompt.md` file into the project to simulate a pending continuation prompt.
3. Start a new Claude Code session in the project.
4. Observe: the continuation-detection behavior is unchanged by the flag — code never reads it, so toggling the value has no effect.

## Root Cause

- **File**: `scripts/little_loops/hooks/session_start.py` (and any other SessionStart handler)
- **Anchor**: no reader exists — grep for `auto_detect_on_session_start` returns 0 hits outside `config-schema.json` and the two docs files.
- **Cause**: The flag was added to the schema and documented in advance of (or in parallel with) the SessionStart inject feature work tracked under FEAT-1315/1316/1317, but the corresponding handler code to consult the flag was never wired up. The continuation-detection feature itself is also not implemented today, so the gap went unnoticed until `/ll:verify-issues` cross-checked schema/docs against code.

## Expected Behavior

Either:

1. **Implement the flag**: have the SessionStart hook intent (`scripts/little_loops/hooks/session_start.py`) check the flag before printing the continuation-prompt detection notice — or
2. **Remove the documentation**: delete the flag from `config-schema.json`, both docs files, and the example configs, since it does nothing today.

Option 2 is likely the right move if the SessionStart inject feature stays deferred (FEAT-1315 was deferred by the same verify pass that found this).

## Motivation

Users who read the docs and try to disable continuation auto-detection by setting `continuation.auto_detect_on_session_start: false` get no behavior change, eroding trust in the documented configuration surface. Cleaning this up — by either implementing the flag or removing it — keeps `config-schema.json` and the docs honest about what little-loops actually does, which matters more than the flag itself given the underlying feature is deferred.

## Integration Map

### Files to Modify (Option 2 — remove)
- `config-schema.json` — drop the `continuation.auto_detect_on_session_start` property.
- `docs/reference/CONFIGURATION.md` — remove references at lines 120 and 411.
- `docs/guides/SESSION_HANDOFF.md` — remove references at lines 292, 314, 331.
- `templates/*/ll-config.json` (if any reference the flag in example configs).

### Files to Modify (Option 1 — implement)
- `scripts/little_loops/hooks/session_start.py` — read the flag and gate the continuation-detection notice on it.
- `config-schema.json` — keep as-is (already declared).

### Dependent Files (Callers/Importers)
- N/A — no current readers of this flag (that's the bug).

### Similar Patterns
- Other `continuation.*` settings under `config-schema.json:552` — check whether they are wired up before assuming this is an isolated oversight.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/config/features.py:feature_enabled()` — the standard utility for boolean flag gates used by all other hooks (`post_tool_use.py`, `user_prompt_submit.py`). Not yet imported in `session_start.py`. Usage: `feature_enabled(merged_config, "continuation.auto_detect_on_session_start")` (returns `False` when key is absent, so pass `True` as the sentinel default if needed via raw dict access).
- `scripts/little_loops/hooks/session_start.py:_validate_features()` — existing pattern in this exact file: reads nested config keys via `config.get("sync", {})` and emits warning lines into `feedback_lines`. This is the correct channel and pattern for Option 1 to follow.
- `scripts/little_loops/hooks/post_tool_use.py:_maybe_auto_commit()` — canonical early-return guard: `if not feature_enabled(config, "issues.auto_commit"): return`.
- **All 7 `continuation.*` schema keys are unwired** (lines 553–596 of `config-schema.json`): `enabled`, `auto_detect_on_session_start`, `include_todos`, `include_git_status`, `include_recent_files`, `max_continuations`, `prompt_expiry_hours`. If choosing Option 2, consider removing the entire `continuation` block or auditing all 7. Note: `continuation.max_continuations` in schema is a dead duplicate of `automation.max_continuations` which IS wired via `AutomationConfig.from_dict()` in `scripts/little_loops/config/automation.py`.
- No `ContinuationConfig` dataclass exists in `scripts/little_loops/config/` — raw dict access is the pattern: `merged_config.get("continuation", {}).get("auto_detect_on_session_start", True)`.

### Tests
- Option 1: add a test in `scripts/tests/hooks/` asserting the SessionStart handler suppresses the continuation-detection notice when the flag is `false`.
- Option 2: no tests needed (text-only change); `ll-verify-docs` should pass afterward.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact file**: `scripts/tests/test_hook_session_start.py` — add to `TestSessionStartFeatureValidation` class. The helper `_run_with(root, cfg)` already handles writing a config and calling `handle()`. Pattern: call `_run_with(in_tmp, {"continuation": {"auto_detect_on_session_start": False}})` and assert the continuation notice is absent from `result.feedback`.
- **Integration test**: `scripts/tests/test_hooks_integration.py:TestSessionStartValidation` — adapter-level tests follow the same shape via subprocess.
- **Config write fixture pattern** (from `test_hook_post_tool_use.py:_write_config()`): write `{"continuation": {"auto_detect_on_session_start": false}}` to `(tmp_path / ".ll" / "ll-config.json")`.

### Documentation
- `docs/reference/CONFIGURATION.md`, `docs/guides/SESSION_HANDOFF.md` (see above).

### Configuration
- `.ll/ll-config.json` example snippets in templates (if present).

## Source

Discovered during `/ll:verify-issues` on 2026-05-14 while verifying the FEAT-1315/1316/1317 session-start-inject series. The hook-verification agent surfaced it as a separate doc-accuracy concern from the architecture supersession.

## Implementation Steps

### Option 1 — Implement the flag

1. **`scripts/little_loops/hooks/session_start.py`**: Add `from little_loops.config.features import feature_enabled` to imports (mirrors `post_tool_use.py`). In `handle()`, after the DB bootstrap block (~line 132), gate any continuation-detection logic on `merged_config.get("continuation", {}).get("auto_detect_on_session_start", True)`. There is no `ContinuationConfig` dataclass — use raw dict access.
2. **`scripts/tests/test_hook_session_start.py`**: Add test(s) to `TestSessionStartFeatureValidation`. Use existing `_run_with(in_tmp, cfg)` helper. Test `{"continuation": {"auto_detect_on_session_start": False}}` → notice absent; default (no key) → notice present.

### Option 2 — Remove the undocumented stub (recommended while FEAT-1315 is deferred)

> **Selected:** Option 2 — Remove the undocumented stub — text-only change across 6 files; FEAT-1315 is firmly deferred by architecture supersession with no live code reading any of the 7 `continuation.*` keys

1. **`config-schema.json`**: Remove `continuation.auto_detect_on_session_start` property (lines 562–566). Audit all 7 `continuation.*` keys in the same block (lines 553–596) — all are unwired; consider removing the entire `continuation` object rather than just this one key.
2. **`docs/reference/CONFIGURATION.md`**: Remove entry at line 120 (example config block) and line 411 (settings table row).
3. **`docs/guides/SESSION_HANDOFF.md`**: Remove flag references at lines 292, 314, and 331.
4. **Templates**: Confirmed no `templates/` files reference `continuation` — no template changes needed.
5. **Verify**: Run `python -m pytest scripts/tests/ -v` and `ll-verify-docs` — both should pass with no `continuation.auto_detect_on_session_start` references remaining.
6. **Also remove from skill files** (not listed in original Option 2 steps — discovered by `/ll:decide-issue`): `skills/init/SKILL.md:209`, `skills/init/interactive.md:705-706`, `skills/configure/areas.md:491,506`, `skills/configure/show-output.md:112`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-01.

**Selected**: Option 2 — Remove the undocumented stub

**Reasoning**: All 7 `continuation.*` schema keys are confirmed unwired — zero code reads any of them in `scripts/` or `hooks/`. FEAT-1315 is deferred by architecture supersession (verified 2026-05-14) and would require a full rewrite before the flag could ever be used. Option 1 would add a guard for continuation-detection logic that does not exist, producing no observable behavioral change — it would be another dead stub. Option 2 is text-only, zero-risk, and keeps schema/docs honest.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 — Implement flag | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option 2 — Remove stub | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option 1**: Import/guard pattern exists in 2 sibling hooks; `TestSessionStartFeatureValidation._run_with()` ready to use; blocked by `feature_enabled()` having a `False` default (raw dict access required) and the continuation-detection notice not yet existing — implementing the guard alone leaves no observable difference.
- **Option 2**: 6 source files to touch (3 skill files not in original issue steps); FEAT-1315 `status: deferred` with architecture-supersession note; `additionalProperties: false` on `continuation` object makes removal schema-migration-safe; `.ll/ll-config.json` has no `continuation` key.

## Acceptance Criteria

- Pick a direction (implement OR remove) and apply it consistently across `config-schema.json`, `docs/guides/SESSION_HANDOFF.md`, `docs/reference/CONFIGURATION.md`.
- If removing: also remove from example configs and any `ll-config.json` files in `templates/`.
- If implementing: add a test that asserts the flag suppresses the continuation-detection notice when set to `false`.

## Impact

- **Severity**: Low — misleading documentation, but no functional regression (the underlying continuation-detection feature itself is not wired up either).
- **Effort**: Small — text-only change (Option 2) or small handler edit + test (Option 1).
- **Risk**: Low.

## Labels

`bug`, `documentation`, `hooks`, `verify-issues`

**Open** | Created: 2026-05-14 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-30_

**Verdict: VALID** — All claims confirmed:
- `auto_detect_on_session_start` declared in `config-schema.json:552` ✓
- Documented in `docs/guides/SESSION_HANDOFF.md` and `docs/reference/CONFIGURATION.md` ✓
- Zero code references to `auto_detect_on_session_start` in `scripts/` — flag is never read ✓
- Issue still needs a decision (implement or remove) — no progress since 2026-05-14 discovery ✓

## Session Log
- `/ll:decide-issue` - 2026-06-01T19:47:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a55d1f6-d02f-419b-9e9c-78a18b1ba60c.jsonl`
- `/ll:refine-issue` - 2026-06-01T19:41:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34f84fcf-43f5-4359-b8a7-255b2b1e5f21.jsonl`
- `/ll:verify-issues` - 2026-05-31T20:34:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52d78c58-d750-467e-9092-de587a96595e.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-23T16:51:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9c6d1a1-0ff3-429d-82ba-98b024c1337c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-14T21:23:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
