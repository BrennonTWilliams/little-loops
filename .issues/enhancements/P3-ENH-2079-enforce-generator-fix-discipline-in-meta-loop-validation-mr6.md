---
id: ENH-2079
title: Enforce generator-fix discipline in meta-loop validation (MR-6)
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
---

# ENH-2079: Enforce generator-fix discipline in meta-loop validation (MR-6)

## Summary

Add MR-6 to `ll-loop validate`: detect hand-patching anti-patterns where a loop's `apply` action writes to a file also directly modified by a prior `shell` action in the same run. Emit a WARNING suggesting the fix be moved into the generator action instead. Include a `generator_fix_ok: true` suppression flag for intentional post-processing cases. Document MR-6 in `CLAUDE.md` alongside MR-1 through MR-5.

## Current Behavior

`ll-loop validate` enforces rules MR-1 through MR-5 but does not detect the hand-patching anti-pattern. A loop that emits an artifact via an `apply` action and then directly patches it via a `shell` action passes validation silently, producing fragile output that diverges from the generator on the next run.

## Expected Behavior

`ll-loop validate` emits a MR-6 WARNING when it detects a state where an `apply` action writes to a file also modified by a prior `shell` action in the same run. The WARNING message recommends moving the patch into the generator action. A `generator_fix_ok: true` flag at the loop top-level suppresses the warning for intentional post-processing cases.

## Motivation

Meta-loops that generate YAML, issue files, or FSM states frequently hand-patch the emitted artifact rather than fixing the generation logic. Hand-patching creates fragile output that diverges from the generator on the next run, undermining iterative refinement. The stable approach is to fix the generator — the loop's action/transition rules — so every subsequent run produces correct output automatically.

## Proposed Solution

Add rule MR-6 to `ll-loop validate`: detect states where an `apply` action writes to a file that was also directly modified by a prior `shell` action in the same run (a proxy for hand-patching). Emit a WARNING with a suggestion to move the fix into the generating action. Document the rule in `CLAUDE.md` under Loop Authoring alongside MR-1 through MR-5. Add `generator_fix_ok: true` as a suppression flag for cases where direct post-processing is intentional.

## Implementation Steps

1. Add MR-6 rule definition to the `ll-loop validate` rule registry
2. Implement heuristic: detect `shell` actions modifying the same file target as an `apply` action in the same loop run
3. Emit WARNING severity with remediation suggestion
4. Add `generator_fix_ok: true` suppression flag support at loop top-level
5. Document MR-6 in `CLAUDE.md` under Loop Authoring (alongside MR-1 through MR-5)
6. Add test cases for MR-6 detection and suppression

## Scope Boundaries

- **In scope**: Static detection at `ll-loop validate` time of `shell`-then-`apply` patterns targeting the same file
- **Out of scope**: Runtime hand-patch detection during loop execution
- **Out of scope**: Detecting hand-patching across multiple loop runs (single-run analysis only)
- **Out of scope**: Automatic fix rewriting — WARNING with suggestion only
- **Out of scope**: Changes to existing loops that use the pattern (opt-in suppression via flag)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validator.py` — add MR-6 rule definition and detection heuristic
- `.claude/CLAUDE.md` — document MR-6 in Loop Authoring section alongside MR-1 through MR-5

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `ll-loop validate` CLI entry point
- Loop YAML files that use `apply` + `shell` sequences — will surface new warnings

### Similar Patterns
- MR-1 through MR-5 implementations in `scripts/little_loops/fsm/validator.py` — follow same rule registration pattern
- `meta_self_eval_ok`, `shared_state_ok`, `partial_route_ok`, `artifact_versioning_ok` suppression flags — follow same top-level flag pattern

### Tests
- `scripts/tests/test_builtin_loops.py` — add MR-6 detection test (hand-patch pattern triggers WARNING)
- `scripts/tests/test_builtin_loops.py` — add `generator_fix_ok: true` suppression test

### Documentation
- `.claude/CLAUDE.md` — Loop Authoring section; add MR-6 entry with rationale

### Configuration
- Loop YAML top-level: `generator_fix_ok: true` suppression flag

## Acceptance Criteria

- [ ] `ll-loop validate` emits MR-6 WARNING when hand-patch pattern is detected
- [ ] WARNING message suggests moving the fix into the generator action
- [ ] `generator_fix_ok: true` suppresses the warning
- [ ] `CLAUDE.md` Loop Authoring section documents MR-6 with rationale
- [ ] Tests cover both detection and `generator_fix_ok` suppression

## Impact

- **Priority**: P3 — Low-urgency quality guardrail; hand-patching creates fragility but is not immediately blocking existing work
- **Effort**: Small — New rule added to existing `ll-loop validate` framework; follows established MR-1–5 pattern
- **Risk**: Low — Warning-only; no behavior change to existing loops; suppression flag available for intentional cases
- **Breaking Change**: No

## Labels

`validation`, `meta-loop`, `ll-loop`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-10T23:21:55 - `f88b676e-8236-495f-ac95-b57f4e70e306.jsonl`
