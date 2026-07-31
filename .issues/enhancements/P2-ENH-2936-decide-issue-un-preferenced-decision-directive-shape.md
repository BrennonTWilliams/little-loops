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
2. **Companion CLI**: teach `ll-issues check-decidable` the same pattern, or the FSM
   gate keeps exiting 1 and routing loops to `/ll:refine-issue` instead of decide —
   making the skill fix dead code in automation.
3. **Orchestrator visibility**: a decide run that ends `NO_ACTIONABLE_DECISIONS` while
   `decision_needed` stays `true` should feed autodev's existing `decision_unresolved`
   deferral code (ENH-2666, `record_decision_unresolved`), not fall through to
   `readiness_stagnated`.

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
- `ll-issues check-decidable` re-implements Patterns 1–4 only; it exits 1 on this shape,
  so `rn-remediate`/`autodev` route to `/ll:refine-issue --auto` (which cannot resolve
  it either) instead of decide.
- autodev has no edge from a completed-but-declined decide run to
  `record_decision_unresolved`; the issue eventually defers as `readiness_stagnated`
  (or `low_readiness`).

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
2. **`ll-issues check-decidable`** (scripts/little_loops/ — locate the existing
   implementation from ENH-2443) — add the Pattern E heuristic to the counting logic so
   the FSM pre-gate agrees with the skill.
3. **Orchestrator wiring** — in `loops/autodev.yaml` (and `rn-remediate` if it consumes
   decide results), detect the `NO_ACTIONABLE_DECISIONS` outcome token (or re-check
   `decision_needed` still true after a decide run) and route to the existing
   `record_decision_unresolved` deferral state instead of continuing to the
   readiness-stagnation path.

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
- `skills/decide-issue/SKILL.md` (Phase 3b patterns + resolution logic; mind the 500-line
  cap — overflow goes to `skills/decide-issue/reference.md` per the ENH-494 companion
  pattern)
- `ll-issues check-decidable` implementation (locate via `grep -r "check-decidable" scripts/`)
- `loops/autodev.yaml` (and possibly `loops/rn-remediate.yaml`) deferral routing

### Tests
- Existing check-decidable tests from ENH-2443 (extend with un-preferenced fixtures)
- Loop-validation tests if autodev routing changes (`scripts/tests/test_builtin_loops.py`)

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
- [ ] After a decide run ending `NO_ACTIONABLE_DECISIONS` with `decision_needed: true`,
      autodev defers the issue with reason `decision_unresolved` (not
      `readiness_stagnated`).
- [ ] `python -m pytest scripts/tests/` passes.

## Session Log
- `/ll:capture-issue` - 2026-07-31T21:54:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da828f8-33c5-4a86-bdb0-74648c03bab5.jsonl`
