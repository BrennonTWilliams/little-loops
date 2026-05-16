---
id: ENH-1492
type: ENH
priority: P4
status: open
captured_at: '2026-05-16T04:06:13Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
relates_to: BUG-1490
---

# ENH-1492: Confidence-check should distinguish wiring gaps from co-deliverable test files when setting `missing_artifacts`

## Summary

The `confidence-check` skill sets `missing_artifacts: true` when it detects absent files
in risk factors — but it conflates two semantically different cases:

1. **Pre-implementation wiring gaps**: configuration files, prerequisite issues, or
   integration wiring that must exist *before* the feature can be implemented
2. **Co-deliverable files**: test files or scripts that are *part of the feature delivery*
   and are expected to be absent before implementation starts

Setting `missing_artifacts: true` for case 2 misfires the `run_wire` repair path in
`autodev` (which resolves case 1), wastes a wire+refine cycle on an already-complete
issue, and can trigger unnecessary size-review via BUG-1490.

## Current Behavior

In FEAT-1486 (2026-05-16), `confidence-check` set `missing_artifacts: true` because
`test_adapt_skills_for_codex.py` does not exist. That file is a deliverable of FEAT-1486
itself — its absence is expected and correct for an unimplemented FEAT.

The risk factor text was: "Tests are co-deliverables: ... implement the tests first so
the adaptation script has automated validation before it touches real files." This is
**implementation-order advice**, not a wiring gap.

## Expected Behavior

`missing_artifacts: true` should only be set when absent files represent **pre-conditions
for implementation** — things that must exist before the feature work can start. Absent
files that are themselves the deliverable (scripts, test files, config stubs that the
issue will create) should NOT set this flag.

The implementation-order advice ("write tests first") belongs in the Implementation Steps
body text, where it already appears after the wire pass.

## Motivation

The `missing_artifacts` flag is a routing signal for FSM loops. Mis-setting it causes:
- `run_wire` to run on already-wired issues (wasted LLM call)
- BUG-1490: size-review on well-specified issues when the sub-loop lacks the gate
- Potential silent skips via BUG-1491 when the repair path finds nothing to fix

## Implementation Steps

1. **Define the distinction** in `skills/confidence-check/SKILL.md` or its prompt:
   - `missing_artifacts: true` ← absent pre-condition files (wiring, config, prerequisites)
   - `missing_artifacts: false` ← absent deliverable files (what the issue will create)
2. **Add detection heuristics** to the confidence-check evaluation logic:
   - If the absent file is listed in "files_to_create" in the Integration Map → co-deliverable → do NOT set flag
   - If the absent file is a prerequisite (must exist for the feature to work) → set flag
3. **Add a new optional flag** (e.g., `implementation_order_risk: true`) to capture
   ordering concerns that should not trigger the wiring repair path
4. **Update confidence-check prompt** to explicitly document the distinction

## Acceptance Criteria

- [ ] `missing_artifacts: true` is NOT set for files listed under `files_to_create` in
      the issue's Integration Map
- [ ] Test files that are co-deliverables of a FEAT/ENH do not trigger `missing_artifacts`
- [ ] Implementation-order risk (e.g., "write tests before running script") is captured
      separately or as body text, not as the `missing_artifacts` flag
- [ ] A FEAT with all wiring complete and only co-deliverable files absent gets
      `missing_artifacts: false`

## Scope Boundaries

- **In scope**: `confidence-check` skill logic for setting `missing_artifacts: true/false`; adding `implementation_order_risk` flag; updating skill documentation and prompt
- **Out of scope**: Changing how `autodev` or FSM loops consume `missing_artifacts` (handled by BUG-1490/1491); altering the wire repair path logic itself; redesigning the full risk-factor schema

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — update `missing_artifacts` detection logic; add `implementation_order_risk` flag definition

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — parses `missing_artifacts` from issue frontmatter; may need `implementation_order_risk` added to schema
- `scripts/little_loops/cli/issues/show.py` — displays `missing_artifacts` in `ll-issues show`

### Similar Patterns
- TBD — review how other boolean routing flags are documented in SKILL.md

### Tests
- `scripts/tests/test_confidence_check_skill.py` — add cases for co-deliverable files vs. pre-condition files
- `scripts/tests/test_issue_parser.py` — add `implementation_order_risk` to parser round-trip test
- `scripts/tests/test_builtin_loops.py` — verify routing logic isn't broken by new flag

### Documentation
- N/A — no external docs reference `missing_artifacts` semantics

### Configuration
- N/A

## Impact

- **Priority**: P4 — Reduces wasted wire+refine cycles in automation, but workaround is manual issue review
- **Effort**: Small — Changes confined to `skills/confidence-check/SKILL.md` and prompt; parser may need minor schema update
- **Risk**: Low — Additive change; new `implementation_order_risk` flag is opt-in; existing `missing_artifacts: true` behavior for real pre-conditions is unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `confidence-check`, `autodev`, `routing`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-05-16T04:10:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdf87445-2e6f-4176-b4f9-271ef09487e4.jsonl`
- `/ll:capture-issue` - 2026-05-16T04:06:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffbdb77c-d0c6-43e0-a45d-2fb26e8e53b6.jsonl`
