# BUG-316: `max_continuations` listed under wrong config section in README - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-316-readme-max-continuations-wrong-section.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

### Key Discoveries
- `config-schema.json:424` defines `max_continuations` under `continuation.properties`
- `README.md:152` incorrectly shows `max_continuations` inside the `automation` JSON block
- `README.md:271` incorrectly lists `max_continuations` in the `automation` config table
- No `continuation` block exists in the Full Configuration Example (lines 119-213)
- No `#### continuation` config table section exists in the README
- The schema's `automation` section has `additionalProperties: false` (line 178), so `max_continuations` there would fail validation

### Note on Python Code Discrepancy
The Python code (`config.py:184`) has `max_continuations` on `AutomationConfig` and accesses it as `config.automation.max_continuations`. This is a **separate** schema-vs-code discrepancy noted in the issue file and is out of scope for this fix.

## Desired End State

The README should document `max_continuations` under the `continuation` section, matching `config-schema.json`.

### How to Verify
- `max_continuations` no longer appears in the `automation` block or table
- A `continuation` block exists in the Full Configuration Example
- A `#### continuation` config table section documents all continuation properties

## What We're NOT Doing

- Not changing Python code (`config.py`, `issue_manager.py`, tests) — separate issue
- Not changing `docs/API.md` — reflects Python code which is separate
- Not changing `configure.md` — already references `config.continuation.max_continuations`

## Implementation Phases

### Phase 1: Fix Full Configuration Example

#### Changes Required

**File**: `README.md`

1. Remove `"max_continuations": 3` from the `automation` block (line 152), leaving trailing comma fix on `stream_output`
2. Add a `continuation` block between `scan` and `context_monitor` (matching schema order)

#### Success Criteria
- [ ] `automation` block has exactly 5 properties (no `max_continuations`)
- [ ] `continuation` block exists with all 7 properties from schema

### Phase 2: Fix Configuration Sections Tables

#### Changes Required

**File**: `README.md`

1. Remove the `max_continuations` row from the `automation` config table (line 271)
2. Add a `#### continuation` section after `scan` (before `sprints`), following the established table pattern

#### Success Criteria
- [ ] `automation` table has 5 rows (no `max_continuations`)
- [ ] New `continuation` section has 7-row table matching schema defaults
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
