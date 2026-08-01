---
id: ENH-2952
title: Consolidate the duplicated 15-line flag-parse block across 17 skill/command
  files
type: ENH
priority: P3
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T11:24:59Z'
parent: EPIC-2938
epic: EPIC-2938
decision_needed: false
program_design_not_applicable: true
relates_to:
- ENH-2939
labels:
- skills
- cleanup
- context-efficiency
confidence_score: 98
outcome_confidence: 92
score_complexity: 23
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2952: Consolidate the duplicated flag-parse block

## Summary

An identical ~15-line block (`--dangerously-skip-permissions` / `LL_NON_INTERACTIVE` /
`DANGEROUSLY_SKIP_PERMISSIONS` → `AUTO_MODE`, then `--auto`/`--check`/`--all`/`--sprint`)
is duplicated across 17 files: skills `audit-issue-conflicts`, `audit-loop-run`,
`confidence-check`, `decide-issue`, `debug-loop-run`, `go-no-go`, `init`, `format-issue`,
`issue-size-review`, `map-dependencies`, `spike`, `wire-issue`; commands
`normalize-issues`, `commit`, `prioritize-issues`, `refine-issue`, `verify-issues`.

Split out of ENH-2939 because the obvious fix is not obviously a win, and bundling it
would have blocked that issue's two clean sweeps.

## Current Behavior

~255 lines of identical shell boilerplate, paid on every invocation of any of the 17
files. It is not *drift-prone* the way an algorithm is (the block is stable), so the harm
is context cost, not correctness.

## Expected Behavior

One of the options below, chosen on measured evidence. The block appears at most once, or
is documented as deliberately duplicated with the measurement that justified it.

## Proposed Solution

### Option A — Shared companion doc

Define the block once in a companion file (e.g. `skills/_shared/flag-parse.md`) and
replace the 17 sites with a one-line pointer.

- **Pro**: single definition; matches the ENH-494 companion-file precedent.
- **Con**: skills are loaded independently by the host — each site still costs a pointer,
  and the model must read a second file to act on it. Net context saving may be near zero
  or negative for a 15-line block, and it adds a load-order failure mode.

### Option B — CLI-parsed flags

`ll-action parse-flags "$@" --json` → `{auto, check, all, sprint, issue_id}`, replacing
the shell block with one call.

- **Pro**: deterministic, testable, genuinely removes the prose; consistent with the
  epic's thesis.
- **Con**: a subprocess per invocation for argument parsing; the 17 sites still each need
  the one-line call plus the result-consumption prose.

### Option C — Leave as-is, document the decision

> **Selected:** Option C — Leave as-is, document the decision — measured token cost is
> small and per-invocation (not cumulative), Option A yields ~0 net savings by its own
> stated con, and Option B's savings don't justify building new CLI surface for a P3,
> non-drift-prone item.

Record that the duplication is intentional (stable, no divergence risk) and drop it from
EPIC-2938's scope.

- **Pro**: zero risk; the epic's real target is *algorithmic* drift, which this is not.
- **Con**: leaves ~255 lines of boilerplate in the catalog.

### Decision Rationale

**Selected: Option C — Leave as-is, document the decision**

A direct token measurement of the block (as it appears in `skills/decide-issue/SKILL.md`
Phase 1) put it at 609 chars / ~150 tokens — paid once per invocation of whichever single
file contains it, not summed across all 17 sites, since skills/commands are loaded
independently by the host. Against that baseline:

- **Option A** (companion-doc pointer) confirms its own documented con: following the
  pointer still requires reading the full ~150-token companion file, for a net saving of
  ~0 tokens plus a new load-order failure mode.
- **Option B** (CLI-parsed flags) has no existing `ll-action parse-flags` (or equivalent)
  subcommand to call — it would need genuinely new CLI surface built and tested, then all
  17 sites updated to shell out and parse JSON, to save at most ~half the block
  (~70-90 tokens) per invocation. That's a real engineering cost for a P3, explicitly
  non-drift-prone, "lowest-value child in EPIC-2938" saving.
- **Option C** has zero implementation risk and correctly scopes the duplication as
  stable prose, not the algorithmic drift the epic targets.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A — Shared companion doc | 2 | 2 | 1 | 1 | 6/12 |
| B — CLI-parsed flags | 2 | 1 | 3 | 2 | 8/12 |
| C — Leave as-is, document | 3 | 3 | 3 | 3 | 12/12 |

Key evidence: measured block size ~150 tokens (609 chars, `skills/decide-issue/SKILL.md`
Phase 1 block); no pre-existing `parse-flags`-style CLI entry point found in
`scripts/little_loops/cli/action.py` (Option B would be net-new, not a swap-in call).

## Implementation Steps

1. **Measure first**: token cost of the block at one representative site vs. the
   pointer-plus-companion-read cost (Option A) and the call-plus-consumption cost
   (Option B). Use `ll-ctx-stats` / a direct token count — do not decide from intuition.
2. Decide via `/ll:decide-issue` on the measurement.
3. Apply across the 17 sites, or record Option C in `.ll/decisions.d/` and close.

## Scope Boundaries

- In scope: the 17 flag-parse sites and the choice between A/B/C.
- Out of scope: changing flag *semantics* (`AUTO_MODE` derivation, flag names), other
  duplicated prose (siblings own those), new arg-parsing mechanisms beyond Option B.

## Impact

- **Priority**: P3 - Pure context cost, no correctness or drift risk; lowest-value child in EPIC-2938
- **Effort**: Small - Mechanical once decided; the measurement is the real work
- **Risk**: Low - Reversible markdown edits

## Status

**Open** | Created: 2026-07-31 | Priority: P3

## Acceptance Criteria

- [x] A token-cost measurement for at least Options A and B is recorded in the issue
- [x] The chosen option is stamped via `/ll:decide-issue` with rationale
- [ ] If A or B: the block appears at most once and `ll-verify-skills` stays green
- [x] If C: a decision fragment records why, and EPIC-2938's scope note is updated

## Notes

This is the one child where "delete the duplication" may be the wrong answer. Do not
apply it unmeasured.


## Session Log
- `/ll:manage-issue` - 2026-08-01T11:24:44 - `768a3086-7997-4dc7-a142-4d0fc9944d80.jsonl`
- `/ll:confidence-check` - 2026-08-01T11:23:16 - `03c58e8e-8efb-434f-b9f1-2aea223a2d44.jsonl`
- `/ll:decide-issue` - 2026-08-01T11:22:10 - `89b58182-1f60-430a-ad13-9405e1640bd8.jsonl`
