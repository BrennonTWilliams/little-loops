---
id: ENH-3559
type: ENH
title: Symlink-safe artifact writes and umask-preserving atomic_write
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
parent: EPIC-3556
---

# ENH-3559: Symlink-safe artifact writes and umask-preserving atomic_write

## Summary

Route dashboard, render, policy_builder, design_md and extract output writes through atomic_write/atomic_write_bytes and fix atomic_write globally to keep the umask-derived mode instead of mkstemp 0600, with symlink-replacement and mode tests.

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
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
