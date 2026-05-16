---
id: FEAT-1063
type: FEAT
priority: P4
status: completed
discovered_date: 2026-04-12
discovered_by: conversation
testable: true
confidence_score: 95
outcome_confidence: 90
---

# FEAT-1063: Sprint-Scoped Refine-and-Implement FSM Loop

## Summary

Add a new `sprint-refine-and-implement` FSM loop that runs the same refine → implement pipeline as `auto-refine-and-implement` but scoped to a named sprint's issue list, with the sprint name accepted as a clean positional argument.

## Motivation

`auto-refine-and-implement` processes the entire backlog in confidence/priority order. When a sprint is defined, there was no way to run the refine-and-implement pipeline over just that sprint's issues without manually passing `--only` flags.

Two designs were considered:
1. Add `sprint_name` as an optional context variable to `auto-refine-and-implement`
2. Create a separate loop that accepts sprint name as positional input

The separate loop was chosen because:
- `ll-loop run sprint-refine-and-implement my-sprint` is ergonomically cleaner than `ll-loop run auto-refine-and-implement --context sprint_name=my-sprint`
- The behavior differs meaningfully: sprint order vs. confidence ranking, bounded scope vs. open-ended
- Separate tmp file prefixes avoid any state collision between the two loops
- `auto-refine-and-implement` stays simple and single-purpose

## Implementation

**New file**: `scripts/little_loops/loops/sprint-refine-and-implement.yaml`

Key design decisions:
- `input_key: sprint_name` — positional arg is stored as `context.sprint_name` (not the default `context.input`), making the variable name semantically meaningful throughout the loop
- `get_next_issue` reads `.sprints/<sprint_name>.yaml`, walks the `issues:` list in sprint order, returns first issue not yet present in the skip file (using `grep -qxF` for exact-line matching)
- `capture: input` + `context_passthrough: true` in `refine_issue` — identical handoff pattern to `auto-refine-and-implement`, passes the issue ID to `recursive-refine` as `context.input`
- All tmp files prefixed `sprint-refine-and-implement-*` to avoid collisions with the backlog loop
- Error cases: missing sprint name prints usage and exits to `done`; sprint file not found prints error and exits to `done`

States mirror `auto-refine-and-implement` exactly: `get_next_issue` → `refine_issue` → `get_passed_issues` → `implement_next` → `implement_issue`, with `skip_and_continue` for refinement failures.

## Usage

```bash
ll-loop run sprint-refine-and-implement <sprint-name>
```

Sprint file must exist at `.sprints/<sprint-name>.yaml` (standard sprint location).

## Acceptance Criteria

- [x] `ll-loop list` shows `sprint-refine-and-implement` as a built-in loop
- [x] Positional sprint name stored in `context.sprint_name` via `input_key: sprint_name`
- [x] Sprint issues iterated in sprint YAML order (not confidence ranking)
- [x] Already-processed issues (in skip file) are skipped on resume
- [x] Missing sprint name → prints usage, transitions to `done`
- [x] Sprint file not found → prints error, transitions to `done`
- [x] No changes to `auto-refine-and-implement.yaml`
- [x] No state collision with `auto-refine-and-implement` (separate tmp file prefix)

## Resolution

**Resolved**: 2026-04-12 via direct implementation in conversation.

### Changes Made

- **New**: `scripts/little_loops/loops/sprint-refine-and-implement.yaml`

### Verification

```bash
ll-loop list | grep sprint-refine
# sprint-refine-and-implement  Like auto-refine-and-implement but scoped...  [built-in]
```

## Labels

`feat`, `fsm`, `loops`, `sprint`

## Status

**Completed** | Created: 2026-04-12 | Resolved: 2026-04-12 | Priority: P4
