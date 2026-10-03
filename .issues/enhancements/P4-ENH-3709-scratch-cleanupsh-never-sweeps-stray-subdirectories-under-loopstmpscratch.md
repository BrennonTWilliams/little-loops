---
id: ENH-3709
type: ENH
title: scratch-cleanup.sh never sweeps stray subdirectories under .loops/tmp/scratch
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:30:29Z'
relates_to:
- ENH-3706
- BUG-3705
---

# ENH-3709: scratch-cleanup.sh never sweeps stray subdirectories under .loops/tmp/scratch

## Summary

`hooks/scripts/scratch-cleanup.sh` enumerates `find "$SCRATCH_DIR" -maxdepth 1 -type f`, so subdirectories under `.loops/tmp/scratch` are never swept and accumulate forever. At ENH-3706 review (2026-10-03) the directory held stray subdirs `.ll`, `split`, `head`, `pbuild`, and `__pycache__`. Beyond clutter, a stray `scratch/.ll` shadows `find_project_root()` for any tool run with that directory as cwd (breaks git-grep symbol resolution and the Program Design gate).

Spun out of the ENH-3706 pre-implementation review, where it was explicitly out of scope. Relates to ENH-3706 and BUG-3705.

Needs a policy decision before implementation: (a) an age-based `rmdir`/removal of empty or fully-aged subdirs in the sweep, vs (b) fixing whatever creates them (ll tooling or shell commands run with cwd set to the scratch dir). Whichever is chosen, the sweep must never delete a subdirectory that contains a live-pid file or a file younger than the retention threshold.


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

## Current Pain Point

## Success Metrics

## Acceptance Criteria

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-10-03T17:30:52 - `782c403d-3c0b-47cc-a461-f433badb1263.jsonl`
