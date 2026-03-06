---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 78
---

# FEAT-610: `create-loop` skill undocumented `scope`, `on_partial`, `capture` fields

## Summary

The FSM schema defines `on_partial` (shorthand routing for partial verdict), `capture` (store action output in a named variable), and `scope` (paths for concurrency lock control) as first-class fields. These are implemented and functional in the runtime, but the `create-loop` skill's `reference.md` and `paradigms.md` do not document them. Users of the wizard have no guidance on when or how to use these features.

## Current Behavior

- `reference.md` Advanced State Configuration section only documents `action_type` and `on_handoff`
- `paradigms.md` does not mention `scope`, `on_partial`, or `capture` in wizard presets
- `cmd_show` at `info.py:1042-1043` already surfaces `scope` in display output

## Expected Behavior

`reference.md` documents all three fields with usage examples:
- `scope`: When to use for concurrency control with `ll-parallel`
- `on_partial`: Shorthand for routing partial verdicts without full `transitions` blocks
- `capture`: How to pass action output between states via named variables

## Use Case

A user creating a loop via `/ll:create-loop` wants to run it safely alongside other loops via `ll-parallel`. They need to know about the `scope` field to prevent file conflicts. The wizard should surface this option when appropriate.

## Scope Boundaries

**In Scope**:
- Add `scope` field documentation to `reference.md` with examples
- Add `on_partial` field documentation to `reference.md` with examples
- Add `capture` field documentation to `reference.md` with examples
- Update `paradigms.md` to mention scope in relevant presets

**Out of Scope**:
- Code changes to the FSM runtime (already implemented)
- UI changes to the wizard interface
- New field functionality (only documentation)

## Proposed Solution

1. Extend `skills/create-loop/reference.md` "Advanced State Configuration" section:
   - Add `scope` subsection with definition and usage example (file paths for ll-parallel concurrency)
   - Add `on_partial` subsection with definition and usage example (shorthand routing)
   - Add `capture` subsection with definition and usage example (pass output between states)

2. Update `skills/create-loop/paradigms.md`:
   - Add scope field to presets that benefit from concurrency (if applicable)
   - Add note in relevant paradigm descriptions mentioning when to use scope/on_partial/capture

3. Add cross-reference from `skills/create-loop/SKILL.md` to advanced configuration in reference.md

## API/Interface

**Fields documented**:
- `state.scope` (array of file/directory paths for concurrency lock control)
- `state.on_partial` (routing dict for partial verdict routing)
- `state.capture` (string: variable name to store action output)

**Files modified**:
- `skills/create-loop/reference.md`
- `skills/create-loop/paradigms.md`

## Acceptance Criteria

- [ ] `reference.md` documents `scope` with usage example
- [ ] `reference.md` documents `on_partial` with usage example
- [ ] `reference.md` documents `capture` with usage example
- [ ] `paradigms.md` mentions scope in relevant wizard presets (if applicable)

## Implementation Steps

1. Open `skills/create-loop/reference.md`
2. Locate "Advanced State Configuration" section
3. Add subsections for `scope`, `on_partial`, `capture` with:
   - Field name and type
   - Description (when/why to use)
   - YAML example from actual paradigms
   - Link to FSM schema documentation
4. Update `paradigms.md` presets to reference scope/on_partial/capture where applicable
5. Verify all acceptance criteria checkboxes pass
6. Test `/ll:create-loop` wizard output mentions new fields

## Impact

- **Priority**: P3 - Documentation gap for implemented features
- **Effort**: Small - Documentation-only changes
- **Risk**: Low - No code changes
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `documentation`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `scope`, `on_partial`, `capture` absent from `skills/create-loop/reference.md` and `skills/create-loop/paradigms.md`
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — Added Scope Boundaries, Proposed Solution, API/Interface, Implementation Steps sections
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — confidence_score: 100, outcome_confidence: 78
- `/ll:format-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — added missing ## Status heading (required section per feat-sections.json)

---

## Status

**Open** | Created: 2026-03-06 | Priority: P3
