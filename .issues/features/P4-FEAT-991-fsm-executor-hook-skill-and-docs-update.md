---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 85
parent_issue: FEAT-988
---

# FEAT-991: FSMExecutor Hook Dispatch — Skill and Docs Update

## Summary

Update the `review-loop` skill (reference.md and SKILL.md) to warn (not error) on unknown `action_type` values, and update the API reference and architecture documentation to reflect the extension system registries added by FEAT-987.

## Parent Issue

Decomposed from FEAT-988: FSMExecutor Hook Dispatch — Tests and Wiring Pass

## Current Behavior

- `review-loop/reference.md` QC-3 check treats unknown `action_type` values as errors — after the schema widening in FEAT-990, contributed types like `webhook` are valid and should only warn
- `review-loop/SKILL.md` QC-3 block mirrors the same hardcoded list (`prompt`, `shell`, `slash_command`, `mcp_tool`) and also errors on unknown values
- `docs/reference/API.md` ActionRunner Protocol section describes `ActionRunner` only as a testing/customization interface, missing its role as the contributed-actions runtime dispatch interface
- `docs/ARCHITECTURE.md` extension component table does not list the three new registries: `_contributed_actions`, `_contributed_evaluators`, `_interceptors`

## Expected Behavior

- QC-3 in `review-loop/reference.md` warns (not errors) on unknown `action_type` values (any value not in the built-in list)
- QC-3 block in `review-loop/SKILL.md:128–198` matches the updated `reference.md` behavior
- `docs/reference/API.md:4040–4053` ActionRunner Protocol section notes it serves as the contributed-actions runtime dispatch interface
- `docs/ARCHITECTURE.md:454–458` extension component table includes `_contributed_actions`, `_contributed_evaluators`, `_interceptors`

## Proposed Solution

### 1. review-loop Reference Update

**`skills/review-loop/reference.md:103–132`** — QC-3 `action_type` mismatch check:

Change behavior so that values not in `["prompt", "slash_command", "shell", "mcp_tool"]` produce a **warning** (not an error). These are potential contributed types after FEAT-990 widens the schema.

Example updated language:
> QC-3: If `action_type` is set to a value not in `["prompt", "slash_command", "shell", "mcp_tool"]`, treat it as a potential contributed type and warn rather than fail. Contributed action types are dispatched via the extension registry.

### 2. review-loop SKILL.md Update

**`skills/review-loop/SKILL.md:128–198`** — QC-3 block:

Apply the same warn-not-error change as `reference.md`. Both files document the same QC-3 check and must stay in sync.

### 3. API.md Update

**`docs/reference/API.md:4040–4053`** — `ActionRunner Protocol` section:

Add a note that `ActionRunner` also serves as the contributed-actions runtime dispatch interface used by the extension system (not just for testing/customization). Extension plugins register runners against custom `action_type` strings.

### 4. ARCHITECTURE.md Update

**`docs/ARCHITECTURE.md:454–458`** — extension component table:

Add the three new registries introduced by FEAT-987:

| Component | Description |
|-----------|-------------|
| `_contributed_actions` | Registry mapping `action_type` strings to `ActionRunner` instances |
| `_contributed_evaluators` | Registry mapping evaluator type strings to `Evaluator` callables |
| `_interceptors` | List of `ExtensionProtocol` instances providing `before_route`/`after_route` hooks |

## Implementation Steps

1. Update `skills/review-loop/reference.md:103–132` QC-3 to warn (not error) on unknown `action_type` values
2. Update `skills/review-loop/SKILL.md:128–198` QC-3 block to match
3. Update `docs/reference/API.md:4040–4053` ActionRunner Protocol section to note contributed-actions dispatch role
4. Update `docs/ARCHITECTURE.md:454–458` extension component table to add the three new registries

## Integration Map

### Files to Modify

- `skills/review-loop/reference.md:103–132` — QC-3 update (warn not error on unknown action_type)
- `skills/review-loop/SKILL.md:128–198` — QC-3 block update (must match reference.md)
- `docs/reference/API.md:4040–4053` — ActionRunner Protocol section description update
- `docs/ARCHITECTURE.md:454–458` — extension component table; add three new registries

### Context Files (Read Before Editing)

- `scripts/little_loops/fsm/executor.py:54–77` — `RouteContext`, `RouteDecision` definitions; lines 492–499 (contributed action dispatch), 668–674 (contributed evaluator dispatch), 446–456 (interceptor loop)
- `scripts/little_loops/extension.py` — `ExtensionProtocol` definition with `before_route`/`after_route` hooks

## Acceptance Criteria

- [ ] QC-3 in `review-loop/reference.md` warns (not errors) on unknown `action_type` values
- [ ] QC-3 block in `review-loop/SKILL.md:128–198` matches updated `reference.md` behavior
- [ ] `docs/reference/API.md` ActionRunner Protocol section notes contributed-actions dispatch role
- [ ] `docs/ARCHITECTURE.md` extension component table includes `_contributed_actions`, `_contributed_evaluators`, `_interceptors`

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small — documentation-only edits in 4 files
- **Risk**: Very Low — docs and skill updates; no code changes
- **Depends On**: FEAT-990 (schema widening makes the warn-not-error change accurate)

## Labels

`feature`, `fsm`, `extension-hooks`, `documentation`, `decomposed`

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b5b8fb2-d663-482d-be59-6aa37de8e735.jsonl`
