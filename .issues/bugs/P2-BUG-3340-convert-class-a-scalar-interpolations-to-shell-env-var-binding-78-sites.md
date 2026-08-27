---
id: BUG-3340
type: BUG
title: Convert class-A scalar interpolations to :shell env-var binding (78 sites)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
---

# BUG-3340: Convert class-A scalar interpolations to :shell env-var binding (78 sites)

## Summary

Convert the 78 class-A user/config-scalar interpolation sites to the LL_ARG_<NAME>=${context.x:shell} env-var idiom read via os.environ, across the affected loop files, with ll-loop validate clean and no new MR-11 warnings.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]


## Session Log
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
