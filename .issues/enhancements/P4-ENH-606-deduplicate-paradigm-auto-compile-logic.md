---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
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

## Scope Boundaries

- **In scope**: Consolidating the 4 copy-pasted blocks into shared helpers
- **Out of scope**: Refactoring the paradigm compilation pipeline itself

## Proposed Solution

1. Replace `load_loop` body with: `fsm, _ = load_loop_with_spec(name_or_path, loops_dir, logger); return fsm`
2. Replace `cmd_run` lines 70-81 with `load_loop()` or `load_loop_with_spec()` call
3. Replace `cmd_validate` lines 78-89 similarly

## Impact

- **Priority**: P4 - Code quality, reduces maintenance burden
- **Effort**: Small - Replacing inline code with existing helper calls
- **Risk**: Low - Helpers already exist and are tested
- **Breaking Change**: No

## Labels

`enhancement`, `ll-loop`, `refactor`

---

**Open** | Created: 2026-03-06 | Priority: P4
