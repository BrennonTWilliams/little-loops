---
id: BUG-3434
type: BUG
title: Hook config resolution does not walk up from subdirectory cwd
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T19:27:53Z'
---

# BUG-3434: Hook config resolution does not walk up from subdirectory cwd

## Summary

`user_prompt_submit.handle()` (scripts/little_loops/hooks/user_prompt_submit.py:97-98) and
`session_start.py` (lines 73, 94, 105) both call `resolve_config_path(Path.cwd())` directly.
`resolve_config_path()` (scripts/little_loops/config/core.py:157-181) only checks
`<project_root>/.ll/ll-config.json` (and host-specific variants) under the exact path passed
in — it does not walk up parent directories. This is unlike `find_project_root()`
(scripts/little_loops/paths.py:14-42), which walks up to the nearest ancestor with both
`.ll/` and `.git`, and is the pattern used elsewhere in the codebase for cwd resolution.

Consequence: if the tool's cwd is left inside a subdirectory of the project (e.g. after a
`cd scripts/` for a build step) when a UserPromptSubmit hook fires, `resolve_config_path`
looks for `.ll/ll-config.json` directly under that subdirectory. If none exists there — even
though the real project root two levels up has one — `_load_config` returns `None`, and:

1. The hook prints the false warning `[little-loops] No config found. Run ll-init to set up
   little-loops for this project.` even though the project *is* configured.
2. `analytics_active` becomes `False`, so `record_correction`, `record_skill_event`, and
   `record_prompt_opt_event` are all silently skipped for that turn — real data loss, not just
   a cosmetic message.
3. `handle()` returns early at line 142 before ever checking `prompt_optimization.enabled`,
   so prompt optimization is silently disabled for that turn regardless of config.

Reproduced live in little-loops' own repo: after running `hatch build`/`hatch publish` from
`scripts/` (which has a stray `.ll/` holding only `ll-doc-drift-state.json`, no
`ll-config.json`), the next prompt submitted with cwd still at `scripts/` triggered the false
warning. The repo's real config is at `.ll/ll-config.json` two directories up.

## Root Cause

`scripts/little_loops/hooks/user_prompt_submit.py:97-98`:
```python
cwd = Path.cwd()
config = _load_config(cwd)
```
and `_load_config` (line 55-63) passes `cwd` straight into `resolve_config_path(cwd)`
(scripts/little_loops/config/core.py:157) without first resolving it to the project root via
`find_project_root()`. `session_start.py` has the identical pattern at lines 73/94/105 but is
less exposed since SessionStart normally fires once at session launch when cwd is still the
project root.

## Proposed Fix

Resolve the project root before calling `resolve_config_path`, consistent with how the rest
of the codebase locates `.ll/`:

```python
from little_loops.paths import find_project_root

cwd = find_project_root(Path.cwd()) or Path.cwd()
config = _load_config(cwd)
```

Apply the same change at both call sites (`user_prompt_submit.py` and `session_start.py`).
Confirm no other `resolve_config_path(Path.cwd())` call sites share the gap.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Root Cause

- **File**: `path/to/file.py`
- **Anchor**: `in function buggy_func()`
- **Cause**: [Explanation of why bug happens]

## Error Messages

## Environment

## Frequency

## Location

- **File**: `path/to/file`
- **Line(s)**: [lines] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()`
- **Code**:
```
# Relevant code snippet
```

## Reproduction Steps

## Proposed Fix


## Session Log
- `/ll:capture-issue` - 2026-09-10T19:28:01 - `0827d96d-3211-4f52-b581-bef5a439a36a.jsonl`
