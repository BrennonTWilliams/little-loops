---
id: ENH-2038
type: ENH
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
  - FEAT-1993
  - FEAT-1994
  - BUG-2034
decision_needed: true
---

# ENH-2038: Migrate rn-build refine_seed from issue-refinement to recursive-refine

## Summary

`rn-build`'s `refine_seed` phase delegates to `issue-refinement`
(`rn-build.yaml:417-421`), which is the **only** issue-refiner (besides the
soon-deprecated `greenfield-builder`) that does **not** handle size-review
decomposition: when an issue breaks down, `issue-refinement` returns to
`next-action` and re-selects it rather than processing the decomposed children.
Its sibling `recursive-refine` — used by `autodev`,
`sprint-refine-and-implement`, `sprint-build-and-validate`, and
`auto-refine-and-implement` — handles exactly this (depth-first child queue,
distinct skip categories: `skipped-decomposed`, `skipped-deadend`,
`skipped-budget`, …). Both delegate to the same `refine-to-ready-issue` engine.

Migrating `refine_seed` to `recursive-refine` gives rn-build decomposition
handling for free, aligns it with every other orchestration loop, and structurally
avoids the FEAT-032 churn captured in BUG-2034.

## Why this is a decision, not a drop-in

`rn-build`'s current wiring is **intentional**: the locked design in FEAT-1990
("Design (locked)") specifies `refine_seed loop: issue-refinement` and says to
reuse greenfield-builder's `refine_seed` state **verbatim**
(`greenfield-builder.yaml:164`). The rn-* modernization was deliberately scoped to
the *execution* half (goal-cluster → rn-implement), not the refine-seed phase.
Switching to `recursive-refine` is therefore a **deliberate divergence from a
locked design** and should be agreed before implementing — hence
`decision_needed: true`.

Reinforcing context: `greenfield-builder` (the source of the verbatim pattern) is
itself slated for deprecation in favor of rn-build (FEAT-1993). Carrying its
weaker refiner forward into its replacement is the specific thing worth
reconsidering.

## Interface gap to resolve

`issue-refinement` auto-discovers work via `ll-issues next-action` across all
active issues. `recursive-refine` instead takes an explicit issue-ID list (single
ID or comma-separated). So the migration must have `rn-build` enumerate the
newly-scoped EPIC's child issues after `scope_project`/`write_epic_id` and pass
them in (e.g. `ll-issues list --epic <EPIC-NNN>` → comma-joined IDs → `with:`
binding, or via `context.input`). Confirm `recursive-refine`'s input contract
(`recursive-refine.yaml` `parse_input`) and how to scope to one EPIC.

Caveat: `recursive-refine` also writes to bare `.loops/tmp/` — so this migration
does **not** resolve the MR-3 isolation concern (tracked separately in ENH-2036;
the same hardening would need applying to whichever refiner rn-build calls).

## Acceptance Criteria

- [ ] Decision recorded (proceed / keep issue-refinement) with rationale,
      referencing FEAT-1990's locked design and FEAT-1993.
- [ ] If proceeding: `rn-build.refine_seed` invokes `recursive-refine` scoped to
      the scoped EPIC's child issues.
- [ ] A spec with an issue that triggers size-review decomposition refines its
      children (no re-selection churn on the parent).
- [ ] `ll-loop validate rn-build` passes; `refine_seed` fire-and-proceed
      semantics (advance to `eval_harness` on either verdict) preserved.
- [ ] `docs`/FEAT-1994 (rn-build orchestration decision guide) updated to reflect
      the refiner choice.

## Scope Boundaries

- Touches `rn-build.yaml`'s `refine_seed` (and a small EPIC-children enumeration
  step). Does not modify `recursive-refine` or `refine-to-ready-issue` internals.
- Does not change the execution half (goal-cluster / rn-implement).
- The BUG-2034 fix to `issue-refinement` remains warranted regardless (other
  callers: `eval-driven-development`, `greenfield-builder`).

## Files

- `scripts/little_loops/loops/rn-build.yaml:417-421` — `refine_seed`
- `scripts/little_loops/loops/recursive-refine.yaml` — target sub-loop +
  input contract
- `.issues/features/P3-FEAT-1990-...md` — locked design (reference)
- `.issues/features/P3-FEAT-1993-deprecate-greenfield-builder.md` — deprecation
- `.issues/features/P3-FEAT-1994-rn-build-orchestration-decision-guide.md` — doc

## Impact

- **Priority**: P3 — quality/architecture improvement; BUG-2034 covers the
  immediate bug independently.
- **Effort**: Medium — sub-loop swap plus EPIC-children enumeration and input
  wiring.
- **Risk**: Medium — diverges from a locked design phase; needs validation that
  `recursive-refine` scopes cleanly to one EPIC and respects fire-and-proceed.
- **Breaking Change**: No (internal loop wiring).

## Labels

`loops`, `rn-build`, `recursive-refine`, `orchestration`, `enhancement`,
`decision-needed`, `captured`, `from-audit`

## Parent Issue

EPIC-1811 — Built-in orchestration loops

## Status

**Open** | Created: 2026-06-08 | Priority: P3
