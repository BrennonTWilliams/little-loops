---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 95
outcome_confidence: 88
---

# ENH-606: Deduplicate paradigm auto-compile logic across 4 call sites

## Summary

The paradigm auto-compile check (`"paradigm" in spec and "initial" not in spec`) is copy-pasted across 4 locations. `_helpers.py` already has `load_loop()` and `load_loop_with_spec()` that encapsulate this pattern, but `cmd_run` and `cmd_validate` bypass them and re-implement the logic inline. Additionally, `load_loop` duplicates the entire body of `load_loop_with_spec` — it could be a one-liner that delegates.

## Current Behavior

The same file-open + paradigm-detect + compile/validate pattern exists in:
1. `_helpers.py:60-70` — `load_loop()` (canonical)
2. `_helpers.py:89-98` — `load_loop_with_spec()` (canonical + returns spec)
3. `run.py:70-81` — `cmd_run()` (bypasses `load_loop`)
4. `config_cmds.py:78-89` — `cmd_validate()` (bypasses `load_loop`)

## Expected Behavior

All callers route through `load_loop()` or `load_loop_with_spec()`. `load_loop` delegates to `load_loop_with_spec` with `fsm, _ = load_loop_with_spec(...)`. Single source of truth for paradigm detection.

## Motivation

Four copy-paste instances of identical paradigm detection logic create a compounding maintenance risk:

- **Bug multiplication**: A fix to the detection condition (`"paradigm" in spec and "initial" not in spec`) must be applied in 4 places; missing one leaves a latent inconsistency
- **False confidence**: `_helpers.py` provides `load_loop()` and `load_loop_with_spec()` as canonical entrypoints, but `cmd_run` and `cmd_validate` bypass them — callers cannot rely on the helpers to be authoritative
- **`load_loop` redundancy**: `load_loop` duplicates the full body of `load_loop_with_spec` and discards the `spec` return value; it should be a one-liner delegation

## Scope Boundaries

**In scope:**
- Making `load_loop` delegate to `load_loop_with_spec`
- Routing `cmd_run` and `cmd_validate` through the shared helpers
- Consolidating the 4 copy-pasted blocks into a single source of truth

**Out of scope:**
- Refactoring the paradigm compilation pipeline itself
- Changing the public signatures of `load_loop` or `load_loop_with_spec`

## Proposed Solution

1. Replace `load_loop` body with: `fsm, _ = load_loop_with_spec(name_or_path, loops_dir, logger); return fsm`
2. Replace `cmd_run` lines 70-81 with a `load_loop()` or `load_loop_with_spec()` call
3. Replace `cmd_validate` lines 78-89 similarly

## Success Metrics

- [ ] `grep -n '"paradigm" in spec' scripts/` returns exactly 1 match (in `load_loop_with_spec`)
- [ ] `load_loop` body is a single delegation call to `load_loop_with_spec`
- [ ] All existing tests in `scripts/tests/` pass unchanged

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — make `load_loop` delegate to `load_loop_with_spec`; remove duplicate body (currently at lines 128 and 156)
- `scripts/little_loops/cli/loop/run.py` — replace inline paradigm detection (currently at line 42) with `load_loop_with_spec()` call
- `scripts/little_loops/cli/loop/config_cmds.py` — replace inline paradigm detection (currently at line 70) with `load_loop_with_spec()` call

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` calls `load_loop` (will now route through canonical helper)
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` calls inline detection (will be replaced)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — existing tests cover both `cmd_run` and `cmd_validate`; no new tests required; verify all pass after refactor

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Update `_helpers.py`: replace `load_loop` body with `fsm, _ = load_loop_with_spec(name_or_path, loops_dir, logger); return fsm`
2. Update `run.py` `cmd_run`: replace inline paradigm detection (line 42) with call to `load_loop()` or `load_loop_with_spec()`
3. Update `config_cmds.py` `cmd_validate`: replace inline paradigm detection (line 70) similarly
4. Run full test suite to confirm no regressions

## Impact

- **Priority**: P4 - Code quality, reduces maintenance burden
- **Effort**: Small - Replacing inline code with existing helper calls
- **Risk**: Low - Helpers already exist and are tested
- **Breaking Change**: No

## Labels

`enhancement`, `ll-loop`, `refactor`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: 4 sites confirmed — `_helpers.py:60-70` (load_loop), `_helpers.py:89-98` (load_loop_with_spec), `run.py:70-81` (cmd_run), `config_cmds.py:78-89` (cmd_validate); load_loop does not delegate to load_loop_with_spec
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — v2.0 format: added Motivation, restructured Scope Boundaries, Success Metrics, Integration Map, Implementation Steps; added confidence_score and outcome_confidence to frontmatter
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — Readiness: 95/100 PROCEED; Outcome: 88/100 HIGH CONFIDENCE
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: 4 copy-paste sites confirmed
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11c154b-ec01-40ba-bc51-c1eb3dd6ae2f.jsonl` — Supersedes ENH-628 (closed as duplicate)
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: 4 copy-paste sites confirmed (_helpers.py:128,156; run.py:42; config_cmds.py:70); updated Integration Map and Implementation Steps line refs

## Verification Notes

**Verdict**: VALID — Verified 2026-03-07

- All 4 `"paradigm" in spec` sites confirmed in codebase
- **DUPLICATE**: ENH-628 (`P4-ENH-628-yaml-load-paradigm-detect-duplicated-three-times.md`) describes the same issue (ENH-628 title says "three times" but the body covers the same 4 sites). Recommend merging — ENH-606 has more complete Integration Map and Implementation Steps; ENH-628 has more detailed discovery notes. Consider closing ENH-628 and keeping ENH-606, or vice versa based on implementation preference.

---

## Status

**Open** | Created: 2026-03-06 | Priority: P4

## Blocked By
- ENH-671
