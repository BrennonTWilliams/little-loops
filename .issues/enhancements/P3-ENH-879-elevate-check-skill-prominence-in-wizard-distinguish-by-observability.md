---
discovered_commit: 30872893
discovered_branch: main
discovered_date: 2026-03-24T00:00:00Z
discovered_by: capture-issue
confidence_score: 80
outcome_confidence: 100
---

# ENH-879: Elevate check_skill prominence in wizard — distinguish phases by observability, not cost

## Summary

The `create-loop` wizard currently lists `check_skill` as "Optional" and positions it 3rd among check phases. This framing misrepresents its qualitative value: `check_skill` is the only phase that exercises the feature as a real user would. The wizard should reorganize phase presentation around what each phase can *observe*, not what it costs, and elevate `check_skill` accordingly.

## Current Behavior

The wizard presents check phases ordered roughly by cost/complexity, with `check_skill` labeled "Optional" and appearing after `check_concrete` and before `check_semantic`. Users scanning quickly receive the implicit message that `check_skill` is a premium add-on rather than the highest-fidelity validation available.

## Expected Behavior

The wizard distinguishes phases by their observational scope, making clear that:

| Phase            | What it can catch                                                                 |
|------------------|-----------------------------------------------------------------------------------|
| `check_concrete` | Objective regressions (tests, types, lint)                                        |
| `check_skill`    | Actual user-observable behavior (the only phase that exercises the feature as a user would) |
| `check_semantic` | Self-assessment of output quality (bias-prone)                                    |
| `check_invariants` | Runaway scope                                                                   |

`check_skill` is presented as qualitatively different from `check_semantic` — not merely a more expensive version of self-assessment — and its "Optional" label is replaced or supplemented with a note explaining its unique observational value.

## Location

- **File**: `skills/create-loop/SKILL.md` (or equivalent wizard prompt)
- **Section**: Check phase selection step in the loop creation wizard

## Motivation

The highest-fidelity validation in the FSM loop system is browser/real-user evaluation — the kind that catches issues no static analysis or self-assessment can surface. `check_skill` is the mechanism for this. Burying it behind an "Optional" label after cheaper gates trains users to skip it, reducing loop quality for exactly the cases where it matters most. The guide's `check_skill` section already explains this distinction correctly; the wizard UI should match that framing.

## Proposed Solution

Reorganize the wizard's check phase selection to:

1. **Lead with the observability table** (or a text equivalent) before asking the user to choose phases — establish the mental model before asking for a selection
2. **Relabel `check_skill`** from "Optional" to something that conveys its unique capability, e.g., "Recommended — only phase that validates real user behavior"
3. **Separate `check_skill` from `check_semantic`** visually or textually so users understand they are not interchangeable — `check_skill` is external observation, `check_semantic` is self-report
4. **Keep cost information** but subordinate it to observability information — cost is a tiebreaker, not the primary organizing principle

## Scope Boundaries

- In scope: wizard text, labels, ordering, and framing of check phases
- In scope: any `check_skill` description or help text shown during wizard interaction
- Out of scope: changes to how `check_skill` executes at runtime
- Out of scope: changes to the guide documentation (already accurate)

## Success Metrics

- `check_skill` is no longer labeled "Optional" in the wizard's check phase selection step
- An observability table (or text equivalent) appears before the phase selection prompt
- Users can distinguish `check_skill` from `check_semantic` by observational scope, not cost

## API/Interface

N/A — No public API changes. This is a wizard text and framing change only.

## Implementation Steps

1. Open `skills/create-loop/loop-types.md` and navigate to Step H3 (line ~603)
2. Add an observability table as a blockquote context block before the `AskUserQuestion` yaml — model after `docs/guides/LOOPS_GUIDE.md:895-904`; include phase name, what it can observe, and latency
3. Relabel `check_skill` option from `"Skill-based evaluation (Optional)"` (line 620) to `"Skill-based validation (Recommended — only phase that validates real user behavior)"`
4. Reorder options: move skill-based validation to 2nd position (after tool-based gates, before LLM-as-judge) to reflect observational hierarchy
5. Update LLM-as-judge description to clarify it's self-report/bias-prone, distinguishing it from skill-based external observation
6. Update default selection note (line 630) to reinforce that skill-based validation is the highest-fidelity gate, not just an optional extra
7. No changes to `review-loop/SKILL.md` — no check phase text present
8. (Optional consistency follow-up) Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:339-344` to match the new wizard framing — it mirrors the old wizard H3 step verbatim; and update the `# OPTIONAL: check_skill` comment in `loops/harness-single-shot.yaml:91`

## Integration Map

### Files to Modify
- `skills/create-loop/loop-types.md:603-631` — Step H3: Evaluation Phases — the actual wizard question block; `SKILL.md` delegates to this file for type-specific question flows

### Files to Read for Context
- `docs/guides/LOOPS_GUIDE.md:895-904` — observability table already present; model the wizard framing after this table
- `skills/create-loop/SKILL.md:83` — confirms harness type states: `discover, execute, check_concrete, check_semantic, check_invariants, advance, done`

### Dependent Files (Callers/Importers)
- N/A — wizard prompt text; no callers/importers

### Similar Patterns
- `docs/guides/LOOPS_GUIDE.md:895-904` — correct observability framing already used in guide docs; wizard should match

### Tests
- N/A — wizard text change; no automated tests to update

### Documentation
- `skills/review-loop/SKILL.md` — no check phase descriptions present; no consistency changes needed

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact location**: `skills/create-loop/loop-types.md:607-631` — Step H3 contains the full wizard question block with the "Optional" label
- **Current "Optional" label**: Line 620 — `label: "Skill-based evaluation (Optional)"` with description "Invoke a skill to act as a user and verify the feature end-to-end"
- **Current ordering**: Tool-based gates → LLM-as-judge → Diff invariants → Skill-based evaluation (last position)
- **Default note at line 630**: "Skill-based evaluation is unselected by default — add it when a skill can verify something the other phases cannot observe"
- **Guide framing (model)** at `docs/guides/LOOPS_GUIDE.md:895-904`: already has the correct observability table with latency column — wizard should echo this framing
- **`review-loop/SKILL.md`**: no check phase text; no changes required for consistency
- **Consistency targets (out of scope per issue boundaries, but worth noting)**:
  - `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:339-344` — guide renders the wizard H3 step verbatim with the same "Optional" label; will need a follow-up update for consistency
  - `loops/harness-single-shot.yaml:91` — shipped example has `# OPTIONAL: check_skill` header comment; reinforces the wrong framing
- **State list discrepancy**: `skills/create-loop/SKILL.md:83` lists harness states as `discover, execute, check_concrete, check_semantic, check_invariants, advance, done` — `check_skill` is absent, though `loop-types.md:689` generates it conditionally; this may need separate correction

---

## Impact

- **Priority**: P3 — improves wizard UX but does not block any functionality
- **Effort**: Small — wizard text and framing change only; no runtime code changes
- **Risk**: Low — no behavioral changes to loop execution or check phase logic
- **Breaking Change**: No

## Labels

`enhancement`, `wizard`, `create-loop`, `ux`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-24_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- **Implementation already exists in working tree**: All five prescribed changes from ENH-879 are already applied to `skills/create-loop/loop-types.md` (unstaged). The work is done — verify correctness and close this issue rather than re-implementing.

## Status

Completed — 2026-03-24. All prescribed changes applied to `skills/create-loop/loop-types.md`: observability table added, `check_skill` relabeled and elevated to 2nd position, LLM-as-judge distinguished as self-report/bias-prone, default note strengthened.

## Session Log
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:refine-issue` - 2026-03-25T02:04:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9d20766-f11c-4f34-906a-8e749b37605d.jsonl`
- `/ll:format-issue` - 2026-03-25T01:57:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cecd92d-7688-41c8-8c77-72f94f04500c.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee142cb2-b955-483a-a13b-7ca611c8d2cf.jsonl`
