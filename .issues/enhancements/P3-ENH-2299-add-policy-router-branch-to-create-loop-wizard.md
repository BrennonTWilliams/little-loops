---
id: ENH-2299
title: Add policy-router branch to create-loop wizard
type: ENH
priority: P3
status: open
discovered_date: 2026-06-26
discovered_by: capture-issue
captured_at: "2026-06-26T00:04:42Z"
---

# ENH-2299: Add policy-router branch to create-loop wizard

## Summary

Add a "Policy router (decision table)" loop type to `/ll:create-loop` so users can generate policy-routed FSM loops without hand-authoring the YAML. The wizard branch should wire `lib/policy-router.yaml` (and optionally `lib/rubric-router.yaml`), scaffold the three-state `score → parse_scores → policy_dispatch` pipeline, and let the user define their `context.policy_rules` decision table interactively.

## Current Behavior

`/ll:create-loop` offers no wizard path for the policy-router pattern. Users who want a decision-table-based loop (multi-dimensional score routing via `lib/policy-router.yaml`) must hand-author the FSM YAML, copy `policy-refine.yaml` as a starting point, and manually configure `context.policy_rules`, the `route:` dispatch map, and the fragment imports. The guide (`docs/guides/POLICY_ROUTER_GUIDE.md`) documents the pattern, but there is no guided scaffolding.

## Expected Behavior

A new wizard branch — "Policy router (decision table)" — appears in the Step 1 type-selection prompt. When selected, the wizard:

1. **Asks for the scoring source**: LLM rubric scorer (`lib/rubric-router.yaml`) or custom shell scorer that writes `rubric-dim-<name>.txt` files.
2. **Asks for the scored dimensions**: comma-separated list (e.g. `clarity,completeness,feasibility,security`).
3. **Asks for the subject artifact**: path or context variable to score (e.g. `artifact.md` or `${context.subject}`).
4. **Collects decision rules interactively**: presents an editable table (inline markdown grid) and writes them as `context.policy_rules`.
5. **Generates the FSM YAML** with the correct fragment imports, `score → parse_scores → policy_dispatch` pipeline, and a `route:` map that covers all action states plus `_:` and `_error:` catch-alls.
6. **Suggests `ll-loop edit-routes <name>`** in the completion message so users know they can re-edit the decision table after creation.

## Motivation

The policy-router pattern is the recommended approach for any loop that needs to branch on a combination of scores (e.g. "ship only if both confidence and security are high"). The guide and fragment library already exist; the wizard is the missing step that makes the pattern discoverable and prevents authoring errors (missing catch-alls, unmatched `route:` keys, MR-4 dead-ends) from the start.

## Proposed Solution

TBD - requires investigation

### Wizard Branch Parameters

| Parameter | Question | Default |
|-----------|----------|---------|
| Scoring source | LLM rubric or custom shell scorer? | LLM rubric |
| Dimensions | Comma-separated scored dimensions | `quality,feasibility,security` |
| Subject artifact | Path or context variable | `${context.subject}` |
| Initial policy rules | Inline decision table (editable) | catch-all `* -> repair` |
| Action states | Comma-separated target states | `done,repair,escalate` |
| Max iterations | Integer | 10 |

### Generated YAML Shape

```yaml
import:
  - lib/rubric-router.yaml      # or omitted for custom scorer
  - lib/policy-router.yaml

context:
  subject: "<artifact>"
  rubric_dimensions: "<dim1>|<dim2>|..."
  policy_rules: |
    <dim>:<op><val> -> <state>
    * -> repair

initial: score

states:
  score:
    fragment: rubric_score
    capture: scores
    next: parse_scores

  parse_scores:
    fragment: policy_parse_scores
    next: policy_dispatch

  policy_dispatch:
    fragment: policy_table_dispatch
    route:
      done: done
      repair: repair
      escalate: escalate
      _: repair
      _error: done

  repair:
    action_type: prompt
    action: "Repair {{context.subject}} based on rubric feedback."
    next: score

  escalate:
    terminal: true

  done:
    terminal: true
```

## Integration Map

### Files to Modify
- `skills/create-loop/templates.md` — add `policy-router` template block and wizard question flow
- `skills/create-loop/loop-types.md` — add `policy-router` entry to the type-selection list and question/generation section
- `skills/create-loop/SKILL.md` — update keyword inference map to route `"decision table"`, `"multi-score"`, `"policy router"` to the new type

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/policy-router.yaml` — fragment consumed by generated loops (no changes needed)
- `scripts/little_loops/loops/lib/rubric-router.yaml` — optional fragment for LLM scoring (no changes needed)
- `scripts/little_loops/loops/policy-refine.yaml` — canonical reference loop; may be cited in template as example

### Tests
- `scripts/tests/test_builtin_loops.py` — add smoke test for wizard-generated policy-router YAML (validate fragment imports, required context fields, route map completeness)

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add a "Using the Wizard" section cross-linking to `/ll:create-loop`
- `docs/guides/LOOPS_GUIDE.md` — update type list to include policy-router

### Configuration
- N/A

## Implementation Steps

1. Add `policy-router` type to the Step 1 `AskUserQuestion` options in `skills/create-loop/SKILL.md` and `templates.md`.
2. Add keyword mappings (`"decision table"`, `"multi-score"`, `"policy router"`, `"rubric route"`) to the type-inference block in `SKILL.md`.
3. Write the wizard question flow for `policy-router` in `loop-types.md` (parameters: scoring source, dimensions, subject, initial rules, action states, max iterations).
4. Write the `policy-router` YAML template in `templates.md` with substitution tokens for all wizard-collected values; ensure `route:` map always includes `_:` and `_error:` entries.
5. Add validation: reject empty dimension list, require at least one non-catch-all rule before generating YAML.
6. Emit `ll-loop edit-routes <name>` suggestion in the completion message.
7. Add a test in `test_builtin_loops.py` that generates a policy-router loop via the wizard parameters and validates the output YAML structure.
8. Update `POLICY_ROUTER_GUIDE.md` with a "Using the Wizard" section.

## Session Log
- `/ll:capture-issue` - 2026-06-26T00:04:42Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52c7663b-99b0-4ea2-9984-865b6cd49e08.jsonl`
