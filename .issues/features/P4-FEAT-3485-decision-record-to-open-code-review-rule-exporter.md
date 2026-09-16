---
id: FEAT-3485
type: FEAT
title: Decision-record to open-code-review rule exporter
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T04:15:42Z'
---

# FEAT-3485: Decision-record to open-code-review rule exporter

## Summary

Export little-loops decision records into open-code-review's (OCR, https://github.com/alibaba/open-code-review) rule format, so OCR's own shipped review plugins enforce little-loops decisions mechanically at review time. Decisions are currently recorded but only enforced via `.claude/CLAUDE.md` prose — nothing closes that loop mechanically.

This is piece 1 of a two-piece OCR integration; piece 2 (a delegate-mode review loop that runs `ocr delegate preview` / `ocr delegate rule` as FSM shell states) is planned separately, so the exported rule format must stay consumable by both.

## Implementation Notes

- Reuse `resolve_active` (`scripts/little_loops/decisions.py:495`) to select active decisions. The analysis that prompted this misattributed it to `decisions_sync.py`, which is a separate module.
- Expected size: a few dozen lines. A command or script emits OCR rule file(s) from the active decision set.

## Verify First

Unverified claims from the prompting analysis:

- OCR's actual rule/config format and how rules are consumed (file path, schema, path filters). Check the OCR repo docs before finalizing the export shape.

## Acceptance Criteria

1. Running the exporter emits rule file(s) covering all active (non-superseded) decisions; superseded ones are excluded via `resolve_active` semantics.
2. Idempotent: re-running over an unchanged decision set produces identical output.
3. Unit test with a fixture decision set covering active/superseded filtering.

## Priority Rationale

P4 — small, unblocked, and recommended as the first of the two OCR pieces.


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

## Use Case

## User Story

## Acceptance Criteria

## API/Interface

```python
# Example interface/signature
```

## Edge Cases

## UI/UX Details

## Data/API Impact


## Session Log
- `/ll:capture-issue` - 2026-09-16T04:15:49 - `b650788f-edb5-4a45-abe3-046c38ae23e3.jsonl`
