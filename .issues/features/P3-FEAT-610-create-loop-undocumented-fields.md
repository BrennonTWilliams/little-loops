---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
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

## Acceptance Criteria

- [ ] `reference.md` documents `scope` with usage example
- [ ] `reference.md` documents `on_partial` with usage example
- [ ] `reference.md` documents `capture` with usage example
- [ ] `paradigms.md` mentions scope in relevant wizard presets (if applicable)

## Impact

- **Priority**: P3 - Documentation gap for implemented features
- **Effort**: Small - Documentation-only changes
- **Risk**: Low - No code changes
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `documentation`

---

**Open** | Created: 2026-03-06 | Priority: P3
