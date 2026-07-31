# ENH-2936: decide-issue: score un-preferenced decision directives instead of NO_ACTIONABLE_DECISIONS

---
id: ENH-2936
type: ENH
priority: P2
status: open
captured_at: "2026-07-31T21:54:57Z"
discovered_date: 2026-07-31
discovered_by: capture-issue
relates_to: [ENH-2715, ENH-2443, ENH-2866, ENH-2666]
---

## Summary

`/ll:decide-issue --auto` declines to act on the one decision shape where its scoring
pipeline would add the most value: an issue that names 2+ concrete alternatives plus an
explicit imperative to decide ("stamp it or move it to Out of scope with a stated reason
— do not leave it unaddressed") but states **no preference**. Phase 3b's Pattern D
(ENH-2715) requires a stated preference to materialize inline alternatives, so this shape
falls through every extraction pattern, the skill exits `NO_ACTIONABLE_DECISIONS`, and
`decision_needed: true` survives indefinitely. Three coupled changes fix it:

1. **Skill**: add an "un-preferenced decision directive" shape to Phase 3b — materialize
   the named alternatives as `**Option A**`/`**Option B**` blocks (reusing ENH-2715
   step 1's machinery) and route to Phase 4–7 evidence-based scoring, which exists
   precisely to pick a winner when no preference is stated.
2. **Companion CLI**: teach `ll-issues check-decidable` the same pattern so the FSM
   pre-gate agrees with the skill. (Note: exit 1 does not permanently divert to refine —
   both `autodev.yaml` and `rn-remediate.yaml` bound the `deposit_options` detour to one
   retry and fall through to decide anyway. The parity fix buys gate agreement and skips
   a wasted refine call per issue; it is not load-bearing for the skill fix.)
3. **Orchestrator visibility**: close the one remaining gap on the score-failing path.
   Autodev already routes "decide ran, flag still armed" to `record_decision_unresolved`
   on the score-passing path (`assert_decision_cleared`, BUG-2595) and the error path
   (`check_decision_after_decide_error`, ENH-2717). The gap is `recheck_after_decide` →
   `on_no: snap_and_size_review` → `recheck_after_size_review`, whose deferral cascade
   checks design-gate/stagnation/low-readiness but never consults `decision_needed` —
   the exact path ENH-2866 took (outcome 56 < threshold).

## Motivation

ENH-2866 postmortem: the issue was deferred `readiness_stagnated` (2026-07-31) with
outcome confidence capped at 56/100, despite being unusually well-researched. Root cause
was not missing research — a `/ll:decide-issue --auto` run (2026-07-31T02:57:31, session
`ffa285f4-3818-4fef-a251-cc2e4a030e29.jsonl`) correctly identified the real open item
(ll-queue run: stamp it or exempt it) but classified it as not a decidable option pair
because no preference was stated, logged `NO_ACTIONABLE_DECISIONS`, and wrote no
`.ll/decisions.d/` fragment. Every subsequent pass (refine, wire, reconcile,
confidence-check ×3) re-flagged the item as still-open. The remedy chain has a genuine
hole: nothing converts "decide before implementation" into `decided: X because Y` unless
a human edits the issue directly. The Ambiguity subscore (Criterion C, capped 8/25) can
never recover through automation.

Secondary failure: the deferral reason lied. `readiness_stagnated` means "every remedy
was attempted and readiness didn't move"; the truthful reason was `decision_unresolved`
("a human needs to make a scope call"). `ll-issues deferred-triage` therefore surfaces
the wrong ask.

## Current Behavior

- Phase 3b Pattern D (skills/decide-issue/SKILL.md) only accepts inline alternatives
  accompanied by a stated preference (declarative recommendation marker, or an
  Open-Questions item with "could do X or Y" + stated leaning). Alternatives + imperative
  decide-marker + no preference → zero candidates → `NO_ACTIONABLE_DECISIONS`, exit 0,
  `decision_needed` unchanged.
- The scan scope for the ENH-2715 inline shape is `## Open Questions`; ENH-2866's
  directive lived in `## Scope Boundaries` prose.
- `ll-issues check-decidable` (`scripts/little_loops/cli/issues/check_decidable.py`, a
  thin wrapper over `issue_parser.locate_enumerable_options()`) counts enumerable option
  blocks only; it exits 1 on this shape, sending `rn-remediate`/`autodev` on a bounded
  one-retry `deposit_options` detour through `/ll:refine-issue --auto` (which cannot
  resolve it either) before falling through to decide.
- autodev's edges to `record_decision_unresolved` cover the score-passing path
  (`assert_decision_cleared`) and the decide-error path
  (`check_decision_after_decide_error`), but NOT the score-failing path: the
  `recheck_after_size_review` deferral cascade (design-gate → stagnation →
  low-readiness) never checks `decision_needed`, so the issue defers as
  `readiness_stagnated` (or `low_readiness`).

## Expected Behavior

- In `--auto` mode with `decision_needed: true`, a passage naming 2+ concrete
  alternatives alongside an imperative decide-marker ("decide before implementation",
  "do not leave unaddressed", "stamp it or exempt it", "X or Y — pick one") with no
  stated preference is treated as decidable: alternatives are materialized as
  `**Option A**`/`**Option B**` blocks under `## Proposed Solution` (verbatim from the
  existing text, never invented), then routed through Phase 4–7 full scoring. Phase 7
  annotates the winner, sets `decision_needed: false`, and writes the decisions-log
  entry as usual.
- Scan scope covers unresolved `## Open Questions` items AND directive sections where
  such imperatives live (`## Scope Boundaries`, `## Proposed Change` /
  `## Proposed Solution`).
- `ll-issues check-decidable` exits 0 on the same shape (same regex/heuristic family,
  pure Python, no LLM).
- When decide still ends `NO_ACTIONABLE_DECISIONS` with `decision_needed: true`, the
  orchestrating loop defers the issue as `decision_unresolved`, not
  `readiness_stagnated`/`low_readiness`.

## Proposed Solution

**Guardrail rationale**: the imperative marker is what distinguishes this from the
settled-informal-list case that Pattern 4's auto-mode conservatism protects against
(automation must not re-litigate a list the author already settled). Here the issue text
explicitly *asks* for a decision, so scoring it re-litigates nothing. Fire only when
`AUTO_MODE = true` AND `decision_needed: true` AND the imperative marker co-occurs
(within ~3 lines) with the named alternatives.

1. **skills/decide-issue/SKILL.md** — add Provisional Pattern E (un-preferenced decision
   directive) to Phase 3b: match 2+ concrete alternatives ("X or Y", enumerated
   alternatives in one passage) co-located with an imperative decide-marker and no
   preference marker. Resolution: reuse ENH-2715 step 1 materialization → re-scan →
   route to Phase 4 scoring (the step-2 path). Update the Pattern D "Requirement" note
   to point at Pattern E for the no-preference case.
2. **`ll-issues check-decidable`** — add the Pattern E heuristic in
   `scripts/little_loops/issue_parser.py` (alongside `locate_enumerable_options()`) so
   the FSM pre-gate agrees with the skill; `check_decidable.py` calls it. Keep the
   heuristic tight (2+ named alternatives co-located within ~3 lines of an imperative
   decide-marker, no preference marker) — bare "X or Y" prose must keep exiting 1.
3. **Orchestrator wiring** — in `scripts/little_loops/loops/autodev.yaml`, add a
   `decision_needed` re-check to `recheck_after_size_review`'s deferral cascade
   (after the design-gate branch, before the `readiness_stagnated` branch): when the
   flag is still armed, defer as `decision_unresolved` via the same set-status idiom
   `record_decision_unresolved` uses. Re-checking the flag is the established idiom
   (`assert_decision_cleared`, `check_decision_after_decide_error`) — do NOT invent
   `NO_ACTIONABLE_DECISIONS` outcome-token parsing.

**Alternative considered (softer variant)**: have Pattern E score the options but write
the result only as a recommendation, leaving `decision_needed: true` for manual
clearing. Rejected as the default because it reintroduces the human-in-the-loop stall
for every such issue; the full-scoring path already leaves an audited rationale
(annotation + decisions-log fragment) reviewable at go/no-go.

## Scope Boundaries

- **In scope**: Phase 3b pattern addition; check-decidable parity; autodev/rn-remediate
  deferral-reason wiring; tests for all three.
- **Out of scope**: resolving factual contradictions between issue sections (that is
  `/ll:reconcile-issue`'s charter — see ENH-2937); interactive-mode behavior changes;
  authoring alternatives not named in the issue text.

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` (Phase 3b patterns + resolution logic). **The file is
  at 491/500 lines** (ll-verify-skills cap), so overflow extraction to
  `skills/decide-issue/reference.md` (currently 107 lines) is guaranteed, not
  contingent — plan the split up front per the ENH-494 companion pattern.
- `scripts/little_loops/issue_parser.py` (Pattern E heuristic, shared home so
  `check_decidable.py` and any future probe reuse it)
- `scripts/little_loops/cli/issues/check_decidable.py` (call the new heuristic as a
  fallback when `locate_enumerable_options()` finds 0)
- `scripts/little_loops/loops/autodev.yaml` (`recheck_after_size_review` deferral
  cascade only; `rn-remediate.yaml` needs no change — its decide path already
  escalates via `check_convergence`)

### Tests
- Existing issue_parser/check-decidable tests from ENH-2443 (extend with
  un-preferenced fixtures, both with and without the imperative marker)
- Loop-validation tests for the autodev routing change (`scripts/tests/test_builtin_loops.py`)

### Documentation
- `docs/reference/API.md` if check-decidable's documented pattern set is enumerated there

## Acceptance Criteria

- [ ] A fixture issue with `decision_needed: true` and a Scope-Boundaries passage of the
      shape "stamp it or move it to Out of scope — do not leave it unaddressed" is
      materialized into Option A/B blocks and scored to a winner by
      `/ll:decide-issue --auto`; `decision_needed` flips to `false` and a decisions-log
      entry is written.
- [ ] The same fixture without the imperative marker (bare "X or Y" prose) is NOT
      treated as decidable (guardrail holds).
- [ ] `ll-issues check-decidable` exits 0 on the first fixture and 1 on the second.
- [ ] On the score-failing path (decide ran, `decision_needed` still `true`, scores
      below threshold), `recheck_after_size_review`'s deferral cascade defers the issue
      with reason `decision_unresolved` (not `readiness_stagnated`/`low_readiness`) —
      structural assertion in `test_builtin_loops.py`.
- [ ] `python -m pytest scripts/tests/` passes.

## Session Log
- `/ll:capture-issue` - 2026-07-31T21:54:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da828f8-33c5-4a86-bdb0-74648c03bab5.jsonl`
