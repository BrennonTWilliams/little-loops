---
id: ENH-2992
status: open
priority: P2
captured_at: "2026-08-02T13:43:01Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to: [ENH-2995, ENH-2993]
---

# Route reconcile-issue on contradiction, not only on readiness plateau

## Summary

`/ll:reconcile-issue` exists specifically to rewrite an issue's directive
sections when they contradict its own accumulated research findings. It is
almost never invoked: **1,703 issues have been refined, 19 have been
reconciled**. The gate that triggers it — `check_reconcile_needed` in
`autodev.yaml` — fires only on a *readiness-score plateau*, at most once per
issue. A contradiction that does not happen to stall the confidence score never
reaches the remedy. Reconcile is also absent from `/ll:refine-issue`'s own
pipeline diagram and Next Steps block, so no human path leads to it either.

Trigger reconcile on the condition it was built for — detected contradiction —
in addition to the existing plateau predicate.

## Current Behavior

`commands/reconcile-issue.md` states the problem it solves, verbatim:

> Over a long refine/spike/confidence-check cycle, `/ll:refine-issue` and
> `/ll:confidence-check` only **append** new "Codebase Research Findings"
> bullets — they never rewrite the issue's own Implementation Steps /
> Acceptance Criteria / Files to Modify to match.

But the only automated route in is `check_reconcile_needed`
(`scripts/little_loops/loops/autodev.yaml:1406-1458`), whose predicate is a
readiness plateau — the score failing to improve against a pre-refine snapshot
— and which is armed as a **one-shot per issue** via a `reconcile_attempted`
marker (`autodev.yaml:1418`). Secondary entries at `autodev.yaml:1684` and
`autodev.yaml:1964` are fallbacks from other states, not contradiction
detection.

Measured across `.issues/` (2026-08-02):

| Signal | Count |
|---|---|
| Issues with a `/ll:refine-issue` session-log entry | 1,703 |
| Issues with a `/ll:reconcile-issue` session-log entry | 19 |
| Issues whose research-findings blocks contain correction language | 316 |

So ~316 issues carry the exact condition reconcile was written to fix, and 19
have been through it.

Additionally, `/ll:refine-issue` never mentions reconcile:
- Pipeline diagram (`commands/refine-issue.md:791`):
  `capture-issue → format-issue → refine-issue → decide-issue → wire-issue → ready-issue → manage-issue`
- `## NEXT STEPS` output block (`commands/refine-issue.md:753-758`) lists
  decide-issue, wire-issue, ready-issue, manage-issue, and issue-size-review —
  not reconcile-issue.

A user who reads refine's own output has no way to learn reconcile exists.

## Expected Behavior

1. **Contradiction is a trigger.** When a refine (or confidence-check) pass
   deposits findings that refute a directive section, `check_reconcile_needed`
   routes to `reconcile_current` regardless of whether the readiness score
   plateaued.
2. **The one-shot arms per contradiction, not per issue.** A second, distinct
   contradiction discovered on a later pass is eligible for a second reconcile.
   (Retain a bounded cap so this cannot loop.)
3. **The human path exists.** refine-issue's pipeline diagram and Next Steps
   block name `/ll:reconcile-issue` when the pass emitted correction language.

## Motivation

The append-only design is deliberate and correct — it protects human prose.
Reconcile is the designed release valve. A release valve that opens 1% of the
time it is needed is a design that has one half installed. The cost is paid by
headless implementers reading contradictory directive sections (see ENH-2995
for the measured shape of that).

This is cheap to fix relative to its reach: the detection signal is already
being written into the issue in plain text by refine itself.

## Proposed Solution

Two changes, independent:

**A. Widen the automated gate.** In `check_reconcile_needed`
(`autodev.yaml:1406-1458`), add a contradiction predicate OR'd with the
existing plateau predicate. `commands/reconcile-issue.md` already supports
`--check`, which "report[s] the plateau verdict without writing, for FSM
evaluators" — extend or reuse that as the detection call so the predicate is
computed in Python rather than judged by an LLM (MR-1: this state needs a
non-LLM evaluator in its routing chain).

Detection candidates, cheapest first:
- A Python check over the issue's directive sections vs its
  `### Codebase Research Findings` blocks. This is plausibly a new
  `ll-issues` subcommand rather than prose in a skill —
  `ll-verify-skill-prose` will flag a prose reimplementation of a
  string-matching algorithm.
- If ENH-2995 lands first, the superseded markers it writes are a direct,
  unambiguous signal: presence of a marker in a directive section ⇒
  reconcile-eligible. Prefer this if available; it removes the heuristic
  entirely.

**B. Surface the human path.** In `commands/refine-issue.md`:
- Add reconcile to the pipeline diagram (line 791) at its real position —
  after refine, conditional.
- Add a Next Steps entry (lines 753-758): when this pass deposited findings
  that refute an existing directive section, run `/ll:reconcile-issue [ID]`.

Change B is independently shippable and near-zero-risk.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `check_reconcile_needed` state
  (lines 1406-1458): add the contradiction predicate; revisit the
  `reconcile_attempted` one-shot arming (line 1418)
- `commands/refine-issue.md` — pipeline diagram (line 791) and `## NEXT STEPS`
  output block (lines 753-758)
- `commands/reconcile-issue.md` — if `--check` is extended to report a
  contradiction verdict alongside the plateau verdict

### Dependent Files (Callers/Importers)
- TBD — use grep to find references

### Similar Patterns
- `autodev.yaml:1684` and `autodev.yaml:1964` — existing fallback routes into
  `reconcile_current`; the new predicate should compose with these, not
  duplicate them
- FEAT-2751's `autodev-repair-cycle-count.txt` mechanism — the established
  pattern for bounding repeated repair-class attempts within a cycle; reuse it
  rather than inventing a new cap

### Tests
- TBD — identify test files to update. `scripts/tests/test_builtin_loops.py`
  holds the autodev structural test class.

### Documentation
- TBD — docs that need updates

### Configuration
- N/A

## Implementation Steps

TBD — requires codebase analysis

## Impact

- Closes the loop between the problem refine creates and the skill built to
  fix it.
- Affects ~316 existing issues and every future refine pass.
- Change B alone makes reconcile discoverable to humans at zero risk.

## Success Metrics

- Reconcile invocation rate rises from 1% of refined issues to approximately
  the contradiction rate (~24%), without a corresponding rise in autodev
  cycle count per issue.
- `ll-loop validate autodev` stays clean — in particular MR-1 (the new
  predicate must have a non-LLM evaluator in its routing chain).

## Scope Boundaries

- Does **not** change what reconcile rewrites — its Contract section
  (rewrite-eligible vs preserve-untouched) is unchanged.
- Does **not** amend the Preservation Rule; that is ENH-2995.
- Does **not** make reconcile unbounded — a per-issue cap remains.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/reconcile-issue.md` | Defines the remedy and its `--check` mode |
| `scripts/little_loops/loops/autodev.yaml` | Contains the gate being widened |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1 constrains the new predicate's evaluator |

## Session Log
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:56 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
