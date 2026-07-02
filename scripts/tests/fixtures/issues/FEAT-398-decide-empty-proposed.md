---
id: FEAT-398
title: Example feature snapshotted for the OPTIONS_MISSING golden test
type: feature
status: open
priority: P3
decision_needed: true
---

# FEAT-398: Example feature snapshotted for the OPTIONS_MISSING golden test

## Summary

Structurally-compliant issue whose `## Proposed Solution` has real subsections but no
enumerable implementation alternatives — no `### Option A/B/C`, no `**Option A**` bold
labels, no numbered `1./2.` alternatives, no `- (a)/(b)` bullet options. `ll-issues
format-check` reports this file as compliant (all required sections present and
non-empty); the gap is semantic, not structural (ENH-2443).

## Current Behavior

N/A — fixture only.

## Expected Behavior

N/A — fixture only.

## Proposed Solution

A single narrative approach is described below, not a set of competing options.

### Files to Add

- `scripts/little_loops/example_module.py`

### Files to Modify

- `scripts/little_loops/existing_module.py`

### Implementation Outline

Wire the new module into the existing call site and update the tests accordingly.

### Design Decisions to Make

_(intentionally empty — mirrors the FEAT-398 reproduction's empty stub subsection)_

## Labels

`feature`, `fixture`

---

## Status
**Open** | Created: 2026-07-02 | Priority: P3
