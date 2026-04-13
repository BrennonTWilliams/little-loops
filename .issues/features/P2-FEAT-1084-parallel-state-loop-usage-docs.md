---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1082
testable: false
confidence_score: 95
outcome_confidence: 85
---

# FEAT-1084: Parallel State Loop Usage Documentation

## Summary

Update `docs/guides/LOOPS_GUIDE.md`, `scripts/little_loops/loops/README.md`, and `docs/generalized-fsm-loop.md` to document the `parallel:` state type with YAML examples, table rows, and a dedicated fan-out section.

## Parent Issue

Decomposed from FEAT-1082: Parallel State Documentation

## Current Behavior

- `docs/guides/LOOPS_GUIDE.md:1653` "Composable Sub-Loops" section and comparison table (lines 1695–1700) describe only `loop:` and inline states; no `parallel:` row or YAML example
- `scripts/little_loops/loops/README.md:148` "Composing Loops" section references only the `loop:` field; no `parallel:` fan-out pattern
- `docs/generalized-fsm-loop.md` "Common Loop Patterns" table (lines 37-43) and Sub-Loop Composition section (~line 218) have no `parallel:` entry; Universal FSM Schema state definition block (~line 261) does not list a `parallel` field

## Expected Behavior

- `LOOPS_GUIDE.md` comparison table includes a `parallel:` row; a new "Parallel Fan-Out" YAML example section follows the Composable Sub-Loops section
- `loops/README.md` "Composing Loops" section describes `parallel:` fan-out pattern alongside `loop:`, with a minimal YAML snippet
- `docs/generalized-fsm-loop.md` has `parallel:` in the "Common Loop Patterns" table, a new "Parallel Fan-Out" section after Sub-Loop Composition, and `parallel` field in the Universal FSM Schema state definition

## Proposed Solution

### `docs/guides/LOOPS_GUIDE.md`

1. Add `parallel:` row to the "When to Use Sub-Loops vs. Inline States" comparison table at lines 1695–1700 (between `Sub-loop (loop:)` and `Inline states` rows)
2. Add a new `## Parallel Fan-Out (parallel:)` section after line 1689 (after the context-passthrough section), with:
   - Description of fan-out behavior
   - YAML example demonstrating a `parallel:` state with `items`, `loop`, `max_workers`, `isolation`, `fail_mode`
   - Routing conventions (`on_yes` / `on_partial` / `on_no`)

### `scripts/little_loops/loops/README.md`

Extend the "Composing Loops" section at line 161 (end of section) to describe `parallel:` fan-out alongside `loop:`:
- One paragraph explaining `parallel:` as concurrent fan-out over a list of items
- A minimal YAML snippet showing `parallel:` usage with required fields (`items`, `loop`)

### `docs/generalized-fsm-loop.md`

Three insertions:
1. **Lines 37-43** — Add `parallel:` row to the "Common Loop Patterns" table
2. **After ~line 218** (section 6 end / Sub-Loop Composition section end) — Add a new `## Parallel Fan-Out` section presenting `parallel:` as a peer concurrent mechanism alongside `loop:` (sequential single-loop invocation)
3. **~Line 261** (Universal FSM Schema state definition block) — Add `parallel` field alongside existing state fields

## Implementation Steps

1. Update `docs/guides/LOOPS_GUIDE.md` — add `parallel:` table row and new fan-out section with YAML example
2. Update `scripts/little_loops/loops/README.md` — extend Composing Loops section with `parallel:` description and YAML snippet
3. Update `docs/generalized-fsm-loop.md` — add to pattern table, add new section, add field to schema definition

## Integration Map

### Files to Modify

| File | Insertion Point | What to Add |
|------|----------------|-------------|
| `docs/guides/LOOPS_GUIDE.md` | Lines 1695–1700 (table), after line 1689 (new section) | `parallel:` table row; new `## Parallel Fan-Out (parallel:)` section with YAML |
| `scripts/little_loops/loops/README.md` | Line 161 (end of Composing Loops) | `parallel:` fan-out paragraph + YAML snippet |
| `docs/generalized-fsm-loop.md` | Lines 37-43 (table), ~line 218 (section), ~line 261 (schema) | Table row; new section; schema field |

### Similar Patterns

- `docs/guides/LOOPS_GUIDE.md:1653–1689` — Composable Sub-Loops section: format for YAML examples and section intro
- `docs/generalized-fsm-loop.md` existing sections for format reference

### YAML Example Pattern

```yaml
- name: process_items
  parallel:
    items: "${captured.fetch.output}"
    loop: process-single-item
    max_workers: 4
    isolation: worktree
    fail_mode: collect
  on_yes: done
  on_partial: handle_partial
  on_no: handle_failure
```

### Routing and Captures Reference

- Routing: `on_yes` (all succeeded), `on_partial` (mixed), `on_no` (all failed)
- Captures: `${captured.<state_name>.results}` contains `all_captures` (per-worker `captured` dicts)

## Dependencies

- FEAT-1074 (schema) and FEAT-1076 (runner) should be complete for exact field semantics; write against specified interface if not yet merged

## Acceptance Criteria

- `LOOPS_GUIDE.md` comparison table includes `parallel:` row and a new Parallel Fan-Out section with YAML example
- `loops/README.md` "Composing Loops" describes `parallel:` fan-out with YAML snippet
- `generalized-fsm-loop.md` pattern table, section, and schema definition all include `parallel:`

## Impact

- **Priority**: P2
- **Effort**: Small — 3 documentation files, targeted insertions
- **Risk**: Very Low — documentation-only
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/847acfcb-8aba-4124-8dc8-a98c7902e550.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
