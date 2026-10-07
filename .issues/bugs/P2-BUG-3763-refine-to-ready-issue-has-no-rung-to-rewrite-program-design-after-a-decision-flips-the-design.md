---
id: BUG-3763
type: BUG
title: refine-to-ready-issue has no rung to rewrite Program Design after a decision
  flips the design
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:18Z'
relates_to:
- BUG-3764
- ENH-3765
---

# BUG-3763: refine-to-ready-issue has no rung to rewrite Program Design after a decision flips the design

## Summary

`refine-to-ready-issue` has no targeted repair that can rewrite a `## Program Design` section after `/ll:decide-issue` selects a different option than the one the section was written for. The observed run ended at `record_gate_unmet` → `failed` with this repair still unowned. Acceptance-criteria gaps also appeared during the run; the trace does not establish that every other gate was clean.

Observed on BUG-3761 (run `.loops/.history/2026-10-07T000313-refine-to-ready-issue`, 33 iterations, 38 min, `failed`):

1. `resolve_decision_mid_refine` ran `/ll:decide-issue --auto`, which selected Option B (predicates on existing columns, no migration). Program Design and the Impact Effort/Risk lines were written for rejected Option A (a `channel` column, migration). decide-issue Phase 7c is bounded-scope by design and reports the section as flagged, not edited.
2. `verify_issue` → `DIRECTIVE_DRIFT` → `check_reconcile_limit` → `reconcile_issue`. `/ll:reconcile-issue` fixed the Acceptance Criteria but refused Program Design and Impact as out of contract (its rewrite scope is Implementation Steps, Acceptance Criteria, Integration Map).
3. Second verify → `DIRECTIVE_DRIFT` → reconcile budget spent → `check_gate_refine_limit` → `refine_followup` (`/ll:refine-issue --gap-analysis`). Additive-only, so it cannot remove the Option A text; `ll-issues format-check` still reports `unapplied_decision`.
4. Third verify → `VERIFY:other` → `check_gate_refine_limit` counter hit 2 (limit `lt 2`) → `record_gate_unmet` → `failed`; run record `deferred`.

The routing worked as designed; the gap is capability. No rung in the repair ladder owns Program Design / Impact rewrites.

## Current Behavior

When `/ll:decide-issue --auto` selects an option different from the one `## Program Design` (and the Impact Effort/Risk lines) were written for, every repair rung declines the section: decide-issue Phase 7c flags it without editing, `/ll:reconcile-issue` refuses it as out of contract, and `/ll:refine-issue --gap-analysis` is additive-only. `ll-issues format-check` keeps reporting `unapplied_decision`, the `check_gate_refine_limit` counter reaches its `lt 2` limit, and the loop ends in `record_gate_unmet` → `failed`.

## Steps to Reproduce

1. Create a disposable fixture with competing options, a canonical selected-option callout, and a `## Program Design` section written for the rejected option. Include stale Impact Effort/Risk lines and preserved decision/research history. BUG-3761 has since been manually repaired, so its current file is not a reproducer.
2. Run the child-loop harness on that fixture, scripting `resolve_decision_mid_refine` to select Option B. Use a separate disposable live evaluation to assess actual model edits.
3. Observe `verify_issue` → `DIRECTIVE_DRIFT` → `reconcile_issue` (fixes Acceptance Criteria, refuses Program Design/Impact) → second `DIRECTIVE_DRIFT` → `refine_followup` (additive-only).
4. Observe the third verify → `VERIFY:other` → `check_gate_refine_limit` exhausted → `record_gate_unmet` → `failed`, with `ll-issues format-check` still reporting `unapplied_decision`.

## Expected Behavior

After a decision flips the design, the loop repairs Program Design and Impact to match the selected option (or routes to a rung that can), and only fails when that repair itself fails.

## Motivation

This fix would:
- Remove a loop-level dead end: any issue whose decision flips after Program Design was written fails `refine-to-ready-issue` even though every other gate is clean.
- Save ~38 min / 33 iterations of model time per failed attempt (BUG-3761 run).
- Remove the need for a manual Program Design/Impact edit between `/ll:decide-issue` and the loop's next verify pass.

## Proposed Solution

Pick one (needs a decision):

- **A.** Extend the `reconcile-issue` rewrite contract to Program Design and Impact Effort/Risk, so the existing `DIRECTIVE_DRIFT` → `reconcile_issue` rung can clear `unapplied_decision`.
- **B.** Add a rung that runs `/ll:refine-issue --full-rewrite` (or a targeted Program Design rewrite) when `format-check` reports a residual `unapplied_decision` after reconcile.
- **C.** Have decide-issue Phase 7c rewrite Program Design/Impact when the rejected option's text dominates the section.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `reconcile_issue`, `refine_followup`, `check_gate_refine_limit`, `record_gate_unmet` (Option B adds a rung)
- `commands/reconcile-issue.md` / `skills/ll-reconcile-issue/SKILL.md` — rewrite contract currently limited to Implementation Steps, Acceptance Criteria, Integration Map (Option A)
- `skills/decide-issue/SKILL.md` — Phase 7c "Propagate Selection" bounded-scope rule (Option C)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `FormatGaps.unapplied_decision` / `unapplied_decision_detail` is the residual signal any new rung must clear (surfaced by `scripts/little_loops/cli/issues/format_check.py`)
- `scripts/little_loops/cli/issues/next_obligation.py` — `select_next_obligation` routes `VERIFY:*` tokens consumed by `route_pre_score_obligation`

### Similar Patterns
- The existing `check_reconcile_limit` → `reconcile_issue` and `check_gate_refine_limit` → `refine_followup` budget/rung pairs in `refine-to-ready-issue.yaml`

### Tests
- `scripts/tests/test_reconcile_issue_command.py` — contract assertions if reconcile's scope widens
- `scripts/tests/test_builtin_loops.py` — loop-structure assertions if a state is added
- TBD (Option B/C): fixture test for a selected-Option-B issue with Option-A Program Design

### Documentation
- `docs/reference/CLI.md` / loop docs if a new rung or flag is added (check `refine-to-ready-issue` mentions)

### Configuration
- N/A

## Program Design

### Types

- `unapplied_decision_detail: list[{section: str, identifier: str}]` — existing `format-check --format json` field; the repair rung's input and its pass/fail signal

### Signatures

- Option A: widen the `reconcile-issue` rewrite contract text to include `## Program Design` and Impact Effort/Risk (no new code identifier)
- Option B: new loop state `rewrite_program_design` (shell/prompt state in `refine-to-ready-issue.yaml`) gated by a new `check_program_design_rewrite_limit` budget state
- Option C: extend decide-issue Phase 7c rewrite categories (`skills/decide-issue/reference.md`) to cover whole-section rewrite when the rejected option dominates

### Call Path

`route_pre_score_obligation` -> `reconcile_issue` (Option A) | `rewrite_program_design` (Option B) -> `verify_issue` -> `record_gate_unmet` (fail-closed when residual `unapplied_decision` persists)

## Implementation Steps

1. Decide between Options A/B/C (`/ll:decide-issue BUG-3763`).
2. Implement the chosen rung/contract change in the files above.
3. Add a fixture issue (selected Option B, Program Design describing rejected Option A) and a regression test that it clears `unapplied_decision` within one budget.
4. Run `python -m pytest scripts/tests/test_reconcile_issue_command.py scripts/tests/test_builtin_loops.py` and `ll-loop validate refine-to-ready-issue`.

## Impact

- **Severity**: Loop-level dead end for any issue whose decision flips after Program Design was written; wastes ~38 min of model time per attempt.
- **Affected**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`, `skills/ll-reconcile-issue/SKILL.md`, `skills/decide-issue/SKILL.md`.

## Acceptance Criteria

- A fixture issue with a selected Option B and a Program Design section describing rejected Option A reaches `done` (or a ready state) in `refine-to-ready-issue` without manual edits.
- `ll-issues format-check` reports no `unapplied_decision` after the repair.
- The repair does not run more than once per `check_*_limit` budget and still fails closed to `record_gate_unmet` when it cannot converge.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-07 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-10-07T00:52:19 - `8092456a-7bf3-47b0-86f7-42712002052b.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:49:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
