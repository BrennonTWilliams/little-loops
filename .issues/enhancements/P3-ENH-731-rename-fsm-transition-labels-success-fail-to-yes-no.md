---
id: ENH-731
type: ENH
priority: P3
title: Rename FSM transition labels from success/fail to yes/no
status: open
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# ENH-731: Rename FSM transition labels from success/fail to yes/no

## Summary

FSM loop transition labels currently use "success" and "fail" as the standard outcome names for state transitions. These terms imply that a transition represents task completion or failure, but many FSM states are simply decision points (e.g., "did the check pass?", "is there more work?"). Renaming the labels to "yes" and "no" better reflects the conditional branching nature of FSM transitions without implying failure or completion semantics.

## Current Behavior

FSM loop YAML configurations use `success` and `fail` as transition outcome labels:

```yaml
transitions:
  - from: check_quality
    on: success
    to: done
  - from: check_quality
    on: fail
    to: fix_issue
```

The terms "success" and "fail" carry connotations of task outcome (pass/fail), which is misleading for states that are simply evaluating a condition rather than completing a task.

## Expected Behavior

FSM loop YAML configurations use `yes` and `no` as transition outcome labels:

```yaml
transitions:
  - from: check_quality
    on: yes
    to: done
  - from: check_quality
    on: no
    to: fix_issue
```

This language is neutral and works equally well for condition-checking states, decision gates, and terminal states.

## Motivation

The "success"/"fail" terminology creates a conceptual mismatch: a state like `has_more_issues` routing to `process_next` on "success" is confusing — it's not that the state succeeded, it's that the answer is "yes". Using "yes"/"no" maps naturally to how FSM states are described in documentation and conversations, reduces cognitive overhead when authoring loops, and avoids misleading implications in state diagrams and logs.

## Proposed Solution

1. Update the FSM engine to recognize `yes`/`no` as valid transition outcomes (in addition to or instead of `success`/`fail`)
2. Update all built-in loop YAML files to use `yes`/`no`
3. Update `ll-loop` display/rendering (status output, diagrams, history) to show `yes`/`no`
4. Update `create-loop` skill and `review-loop` skill to generate/validate `yes`/`no` labels
5. Update documentation (loop authoring guides, examples)
6. Consider deprecation path for `success`/`fail` if backwards compatibility needed

## Integration Map

### Files to Modify
- TBD - requires codebase analysis of FSM engine transition handling

### Dependent Files (Callers/Importers)
- TBD - use grep to find `success`/`fail` references in loop YAML and engine code

### Similar Patterns
- All existing loop YAML files in `loops/` or equivalent directory
- FSM diagram rendering code

### Tests
- TBD - tests that assert on transition outcome names

### Documentation
- `docs/` loop authoring documentation
- Skill files that show YAML examples (`create-loop`, `review-loop`)

### Configuration
- N/A

## Implementation Steps

1. Audit all uses of `success`/`fail` as FSM transition labels in engine, YAML files, skills, and docs
2. Update FSM engine to accept `yes`/`no` outcomes
3. Migrate existing YAML loop configs and skill examples to `yes`/`no`
4. Update rendering/display code (status, diagrams, history output)
5. Update tests
6. Verify with `ll-loop run` on a sample loop

## Impact

- **Priority**: P3 - Naming improvement, not blocking but affects authoring clarity and diagram readability
- **Effort**: Medium - Requires finding all uses of success/fail across engine, YAMLs, skills, docs, and tests
- **Risk**: Low - Rename with potential backwards compat shim; no logic changes
- **Breaking Change**: Yes (if `success`/`fail` removed without migration period)

## Scope Boundaries

- Out of scope: changing other transition label names beyond success/fail → yes/no
- Out of scope: changing the FSM state machine semantics or execution logic
- Out of scope: adding new transition types

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm`, `loops`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2acb782e-c208-43f1-8534-96bfd95ced6e.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
