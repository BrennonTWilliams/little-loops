---
discovered_commit: 30872893
discovered_branch: main
discovered_date: 2026-03-24T00:00:00Z
discovered_by: capture-issue
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

1. Read the current check phase selection step in `skills/create-loop/SKILL.md`
2. Add an observability table (or concise text equivalent) before the phase selection prompt to establish the mental model
3. Relabel `check_skill` from "Optional" to something that conveys its unique capability (e.g., "Recommended — only phase that validates real user behavior")
4. Separate `check_skill` from `check_semantic` visually or textually with explanatory distinction (external observation vs. self-report)
5. Subordinate cost information to observability framing (cost as tiebreaker, not primary organizer)
6. Review the wizard flow for consistency with the guide's existing `check_skill` description

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — wizard prompt text for check phase selection

### Files to Read for Context
- `skills/review-loop/SKILL.md` — may reference check phase descriptions
- `docs/` — any loop configuration guide that describes check phases

### Dependent Files (Callers/Importers)
- N/A — wizard prompt text; no callers/importers

### Similar Patterns
- `skills/review-loop/SKILL.md` — check phase descriptions may use similar framing; review for consistency

### Tests
- N/A — wizard text change; no automated tests to update

### Documentation
- Covered in Files to Read for Context above

### Configuration
- N/A

---

## Impact

- **Priority**: P3 — improves wizard UX but does not block any functionality
- **Effort**: Small — wizard text and framing change only; no runtime code changes
- **Risk**: Low — no behavioral changes to loop execution or check phase logic
- **Breaking Change**: No

## Labels

`enhancement`, `wizard`, `create-loop`, `ux`

## Status

Open

## Session Log
- `/ll:format-issue` - 2026-03-25T01:57:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cecd92d-7688-41c8-8c77-72f94f04500c.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee142cb2-b955-483a-a13b-7ca611c8d2cf.jsonl`
