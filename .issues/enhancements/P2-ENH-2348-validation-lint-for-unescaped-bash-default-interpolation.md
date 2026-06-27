---
id: ENH-2348
title: "Add ll-loop validate lint for unescaped ${ns.path:-default} bash-default interpolation"
type: ENH
status: open
priority: P2
captured_at: "2026-06-27T21:16:24Z"
discovered_date: "2026-06-27"
discovered_by: capture-issue
labels:
- loops
- fsm
- validation
- linting
relates_to:
- BUG-2346
---

# ENH-2348: Add validation lint for unescaped ${ns.path:-default} interpolation

## Summary

Add a static validation rule (surfaced by `ll-loop validate`, implemented in
`scripts/little_loops/fsm/validation.py`) that flags FSM action strings containing an
unescaped `${namespace.path:-...}` — bash parameter-expansion default syntax that the FSM
interpolator does not support. The message should point authors at the two supported forms:
`${namespace.path:default=...}` (engine-native default) or `$${VAR:-...}` (escaped, handled
by the shell).

## Motivation

BUG-2346 shipped 7 instances of this exact pattern across two builtin loops, one of which
(`recursive-refine.yaml:50`) made the loop dead-on-arrival for ~2 weeks. The interpolation
engine already special-cases `:default=` (`validation.py:128`) and the test suite documents
the trap (`test_fsm_interpolation.py:221,364`), yet `ll-loop validate` had no gate to catch
authors mixing bash `:-` into an interpolated `${context.X}` token. This is the
"shift the gate left" pattern already used for the meta-loop rules (MR-1..MR-6) in
`.claude/CLAUDE.md`.

## Current Behavior

`ll-loop validate` validates `:default=` defaults but has no rule for the unsupported
`${ns.path:-...}` form. A loop author can write `${context.order:-queue}`, pass validation,
and only discover the crash at runtime as `Path 'order:-queue' not found in context`.

## Expected Behavior

`ll-loop validate <loop>` reports a finding (WARNING or ERROR) on any unescaped
`${namespace.path:-...}` occurrence, e.g.:

```
[ERROR] interpolation: ${context.order:-queue} uses unsupported bash ':-' default.
Use ${context.order:default=queue} (engine default) or $${ORDER:-queue} (shell, escaped).
  at recursive-refine.yaml:50 (state: parse_input)
```

## API / Interface

- New rule in `scripts/little_loops/fsm/validation.py`. Detect `${` + namespace.path + `:-`
  where the leading `$` is not doubled (`$${` is the legitimate escaped form and must be
  exempted). Reuse the existing `${...}` extraction the `:default=` check already uses.
- Choose severity: ERROR is defensible (the pattern always crashes at runtime), but WARNING
  is acceptable if there is concern about edge cases; recommend ERROR.

## Implementation Steps

1. Add a detector that scans every interpolated string field (actions, captures, etc.) for
   unescaped `${<ns>.<path>:-`.
2. Exempt `$${...}` (escaped) and `:default=` forms.
3. Emit a finding with file/line/state and the corrective hint.
4. Add tests covering: crashing form flagged, `:default=` not flagged, `$${VAR:-x}` not
   flagged.
5. Confirm it fires on the BUG-2346 sites before they are fixed, and is clean after.

## Acceptance Criteria

- [ ] `ll-loop validate` flags `${context.X:-default}` with a corrective message.
- [ ] `$${VAR:-default}` and `${context.X:default=Y}` are not flagged.
- [ ] Tests cover flagged and exempt forms.
- [ ] Rule documented alongside the existing validation rules.

## Session Log
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md

---

## Status

open
