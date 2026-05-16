---
discovered_date: 2026-03-25
discovered_by: audit-architecture
focus_area: integration
confidence_score: 100
outcome_confidence: 86
---

# ENH-888: `BRConfig.to_dict()` missing parallel keys and uses wrong key names

## Summary

`BRConfig.to_dict()` — the backbone of `{{config.*}}` template substitution used by
skills and commands — exports an incomplete `parallel` section. Four keys present in both
the schema and the dataclass are omitted entirely, and two keys use different names than
the schema/config file, meaning template lookups via `resolve_variable()` silently return
`None` for these fields.

## Motivation

This enhancement ensures `BRConfig.to_dict()` — the backbone of `{{config.*}}` template substitution — is complete and schema-aligned:
- **Silent failures**: Six config fields silently return `None` when accessed via templates (`{{config.parallel.timeout_per_issue}}`, `{{config.parallel.stream_subprocess_output}}`, `{{config.parallel.worktree_copy_files}}`, etc.)
- **Broken skill configuration**: `skills/configure/areas.md` references two of these missing keys, producing broken template output
- **Technical debt**: Key-name mismatches between `to_dict()` and the schema create a hidden discrepancy that will surface new bugs as more templates use these keys

## Location

- **File**: `scripts/little_loops/config/core.py`
- **Lines**: 379–390
- **Method**: `BRConfig.to_dict()`

## Current Behavior

### Current State

```python
# core.py:379-390
"parallel": {
    "max_workers": self._parallel.base.max_workers,
    "p0_sequential": self._parallel.p0_sequential,
    "worktree_base": self._parallel.base.worktree_base,
    "state_file": self._parallel.base.state_file,
    "timeout_seconds": self._parallel.base.timeout_seconds,     # ← schema name: timeout_per_issue
    "max_merge_retries": self._parallel.max_merge_retries,
    "stream_output": self._parallel.base.stream_output,          # ← schema name: stream_subprocess_output
    "command_prefix": self._parallel.command_prefix,
    "ready_command": self._parallel.ready_command,
    "manage_command": self._parallel.manage_command,
    # worktree_copy_files   — MISSING
    # require_code_changes  — MISSING
    # use_feature_branches  — MISSING
    # remote_name           — MISSING
},
```

### Key-name mismatches (schema vs `to_dict()` output)

| Schema / config file key | `to_dict()` exports as | Effect |
|---|---|---|
| `parallel.timeout_per_issue` | `timeout_seconds` | `{{config.parallel.timeout_per_issue}}` → `None` |
| `parallel.stream_subprocess_output` | `stream_output` | `{{config.parallel.stream_subprocess_output}}` → `None` |

### Missing keys

| Schema / config file key | Present in dataclass | In `to_dict()`? |
|---|---|---|
| `parallel.worktree_copy_files` | `ParallelAutomationConfig.worktree_copy_files` | No |
| `parallel.require_code_changes` | `ParallelAutomationConfig.require_code_changes` | No |
| `parallel.use_feature_branches` | `ParallelAutomationConfig.use_feature_branches` | No |
| `parallel.remote_name` | `ParallelAutomationConfig.remote_name` | No |

### Affected template usage

`skills/configure/areas.md:190` uses `{{config.parallel.timeout_per_issue}}` and
`{{config.parallel.worktree_copy_files}}` — both currently return `None` when
resolved via `BRConfig.resolve_variable()`.

### automation section also missing `idle_timeout_seconds`

The `automation` section in `to_dict()` (lines 371–378) also omits `idle_timeout_seconds`,
which is defined in the schema, parsed by `AutomationConfig`, and configurable via `ll-auto
--idle-timeout`. This is lower severity but worth fixing at the same time.

## Expected Behavior

After the fix, `BRConfig.to_dict()` should:
- Export `timeout_per_issue` (not `timeout_seconds`) and `stream_subprocess_output` (not `stream_output`) in the `parallel` section
- Include all four previously omitted parallel keys: `worktree_copy_files`, `require_code_changes`, `use_feature_branches`, `remote_name`
- Include `idle_timeout_seconds` in the `automation` section
- Template lookups like `{{config.parallel.timeout_per_issue}}` resolve to correct values instead of `None`

## Proposed Solution

Update `to_dict()` to use schema-aligned key names and include all parsed fields:

```python
"parallel": {
    "max_workers": self._parallel.base.max_workers,
    "p0_sequential": self._parallel.p0_sequential,
    "worktree_base": self._parallel.base.worktree_base,
    "state_file": self._parallel.base.state_file,
    "timeout_per_issue": self._parallel.base.timeout_seconds,          # renamed
    "max_merge_retries": self._parallel.max_merge_retries,
    "stream_subprocess_output": self._parallel.base.stream_output,     # renamed
    "command_prefix": self._parallel.command_prefix,
    "ready_command": self._parallel.ready_command,
    "manage_command": self._parallel.manage_command,
    "worktree_copy_files": self._parallel.worktree_copy_files,         # added
    "require_code_changes": self._parallel.require_code_changes,       # added
    "use_feature_branches": self._parallel.use_feature_branches,       # added
    "remote_name": self._parallel.remote_name,                         # added
},
"automation": {
    "timeout_seconds": self._automation.timeout_seconds,
    "idle_timeout_seconds": self._automation.idle_timeout_seconds,     # added
    "state_file": self._automation.state_file,
    "worktree_base": self._automation.worktree_base,
    "max_workers": self._automation.max_workers,
    "stream_output": self._automation.stream_output,
    "max_continuations": self._automation.max_continuations,
},
```

### Test coverage

Update `test_config.py` to assert `to_dict()` contains all schema-aligned keys.

## API/Interface

`BRConfig.to_dict()` output changes (breaking for any code relying on old key names):
- `parallel.timeout_seconds` → `parallel.timeout_per_issue` (renamed)
- `parallel.stream_output` → `parallel.stream_subprocess_output` (renamed)
- New keys added (non-breaking): `parallel.worktree_copy_files`, `parallel.require_code_changes`, `parallel.use_feature_branches`, `parallel.remote_name`, `automation.idle_timeout_seconds`

Internal use only within little-loops; no public API surface affected.

## Implementation Steps

1. Update the `parallel` dict in `BRConfig.to_dict()` (`core.py` lines 379–390): rename `timeout_seconds` → `timeout_per_issue` and `stream_output` → `stream_subprocess_output`, add four missing keys
2. Add `idle_timeout_seconds` to the `automation` dict in `BRConfig.to_dict()` (`core.py` lines 371–378)
3. Update `scripts/tests/test_config.py` to assert all schema-aligned keys are present in the `to_dict()` output
4. Run `python -m pytest scripts/tests/` to verify all tests pass

## Scope Boundaries

- **In scope**: Fix key names and add missing keys in the `parallel` and `automation` sections of `BRConfig.to_dict()`; update `test_config.py`
- **Out of scope**: Changing underlying dataclass field names; auditing other `to_dict()` sections (tracked separately); adding new config features; updating caller templates that already use incorrect key names

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()` method (parallel section ~line 379, automation section ~line 371)
- `scripts/tests/test_config.py` — add assertions for all 6 corrected/added keys

### Dependent Files (Callers/Importers)
- `skills/configure/areas.md:189-192` — uses `{{config.parallel.timeout_per_issue}}`, `{{config.parallel.worktree_copy_files}}`, `{{config.parallel.stream_subprocess_output}}`
- `skills/configure/show-output.md:43-52` — uses `{{config.parallel.timeout_per_issue}}`, `{{config.parallel.stream_subprocess_output}}`, `{{config.parallel.worktree_copy_files}}` (also affected, not just areas.md)
- `commands/cleanup-worktrees.md:19,27` — uses `{{config.parallel.worktree_base}}` (resolves correctly, not affected)
- `skills/init/interactive.md:369` — uses `{{config.parallel.worktree_base}}` (resolves correctly, not affected)

### Similar Patterns
- Other sections in `BRConfig.to_dict()` (issues, sprint, etc.) should be audited for similar mismatches — see ENH-889

### Tests
- `scripts/tests/test_config.py` — extend to assert all schema-aligned parallel and automation keys
- Follow the style of `test_dependency_mapping_in_to_dict` (line 1077): assert each key present by name, then spot-check values
- Existing `test_to_dict` (line 583) only asserts `result["parallel"]["max_workers"]` — add sibling assertions for all renamed/added keys
- `conftest.py:96-107` sample_config fixture uses `timeout_seconds: 1800` under `parallel` — no fixture update needed; `ParallelAutomationConfig.from_dict()` accepts `timeout_seconds` as fallback (automation.py:69), so `base.timeout_seconds` will equal 1800 and the new assertion `result["parallel"]["timeout_per_issue"] == 1800` will pass

### Dataclass Source
- `ParallelAutomationConfig` is defined in `scripts/little_loops/config/automation.py:40-90` (not core.py)
  - Own fields: `p0_sequential` (48), `max_merge_retries` (49), `command_prefix` (50), `ready_command` (51), `manage_command` (52), `worktree_copy_files` (53), `require_code_changes` (56), `use_feature_branches` (57), `remote_name` (58)
  - Shared base fields via `self._parallel.base.*` (`AutomationConfig`): `max_workers`, `timeout_seconds`, `stream_output`, `state_file`, `worktree_base`, `max_continuations`
- `AutomationConfig` is defined in `scripts/little_loops/config/automation.py:14-36`
  - `idle_timeout_seconds` is at line 18 and parsed by `from_dict` at line 30

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Severity**: Medium (template substitution correctness)
- **Effort**: Small (data class field additions + tests)
- **Risk**: Low — `to_dict()` output is consumed by Claude Code templates, not Python logic
- **Breaking Change**: Minor — key renames (`timeout_seconds` → `timeout_per_issue`,
  `stream_output` → `stream_subprocess_output`) may break any external code relying on
  the old names. Internal use only within little-loops.

## Labels

`enhancement`, `config`, `template-substitution`, `auto-generated`

## Session Log
- `/ll:ready-issue` - 2026-03-26T00:05:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe164423-7552-47e3-ad03-c3c2b19f008e.jsonl`
- `/ll:refine-issue` - 2026-03-25T23:31:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:format-issue` - 2026-03-25T23:26:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:confidence-check` - 2026-03-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`

---

## Resolution

**Completed** 2026-03-25

- Renamed `parallel.timeout_seconds` → `parallel.timeout_per_issue` in `BRConfig.to_dict()`
- Renamed `parallel.stream_output` → `parallel.stream_subprocess_output` in `BRConfig.to_dict()`
- Added four missing parallel keys: `worktree_copy_files`, `require_code_changes`, `use_feature_branches`, `remote_name`
- Added missing `automation.idle_timeout_seconds`
- Added `test_to_dict_parallel_schema_aligned_keys` and `test_to_dict_automation_idle_timeout` to `scripts/tests/test_config.py`
- All 113 tests pass

## Status

**Completed** | Created: 2026-03-25 | Priority: P3
