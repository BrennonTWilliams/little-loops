---
id: EPIC-3336
type: EPIC
title: Loop YAMLs interpolate untrusted text into Python string literals inside shell
  actions
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
supersedes: [BUG-3331]
---

# EPIC-3336: Loop YAMLs interpolate untrusted text into Python string literals inside shell actions

## Summary

[Description extracted from input]

## Motivation

[Why this epic matters - business value, user impact, strategic goal]

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Tests
- TBD - identify shared test infrastructure

### Documentation
- TBD - docs that need updates

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Goal

## Scope

## Children
- **ENH-3337** — Make :shell interpolation suffix compose with :default= and ? (open)
- **ENH-3338** — Add static sweep detecting unsafe context/captured interpolation in loop YAMLs (open)
- **BUG-3339** — Convert python3 -c heredoc-unsafe invocations to quoted heredocs (11 files) (open)
- **BUG-3340** — Convert class-A scalar interpolations to :shell env-var binding (78 sites) (open)
- **BUG-3341** — Convert class-B LLM-output interpolations to heredoc-to-file (67 sites) (open)
- **ENH-3342** — Widen MR-11 lint and document the safe loop-interpolation idiom (open)







## Success Metrics

## Session Log
- `/ll:scope-epic` - 2026-08-27T17:51:44 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
