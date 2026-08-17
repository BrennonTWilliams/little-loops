---
id: BUG-3249
type: BUG
title: refine-to-ready-issue has no check-design gate, so an issue missing Program
  Design routes to done
priority: P2
status: open
testable: true
relates_to:
- ENH-3250
- ENH-3248
- ENH-3247
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T20:04:01Z'
blocked_by:
- ENH-3248
---

# BUG-3249: refine-to-ready-issue has no check-design gate, so an issue missing Program Design routes to done

## Summary

`refine-to-ready-issue.yaml` drives an issue to ready-state through gates that
route on two integers (`confidence`, `outcome`) plus three deterministic
predicates. The Program Design verdict is not among them, so an issue with no
`## Program Design` section reaches the `done` terminal.

Observed on a real run: `ll-loop run refine-to-ready-issue BUG-3243` completed
`done` in 16 iterations / 17m49s / ~$1.47 while `ll-issues check-design
BUG-3243` was failing and `ll-issues format-check` reported `## Program Design`
and `## Status` both missing.

## Current Behavior

Terminal path taken:

```
confidence_check -> check_readiness (100 >= 85 OK) -> check_outcome (82 >= 65 OK) -> done
```

Both gates read `ll-issues show <ID> --json` and compare a single integer.
That JSON carries 50+ keys (`confidence`, `outcome`, `decision_needed`,
`missing_artifacts`, ...) and **none encodes the design-gate verdict**, so
neither state can observe the gap even in principle.

The loop's own oracle did detect it. `skills/confidence-check/SKILL.md:141`
runs `ll-issues check-design` and calls it "the single owned verdict"; that is
where these lines in the produced issue came from:

```
**Readiness Score**: 100/100 -> PROCEED (overridden -- see below)
`ll-issues check-design BUG-3243` fails, which forces `STOP -- ADDRESS GAPS`
```

The verdict was rendered as markdown prose. Routing reads integers. No state
bridges the two, so the finding was persisted and then discarded.

## Expected Behavior

A run that ends `done` implies `ll-issues check-design <ID>` exits 0. When the
design gate fails, the loop spends its unused refine budget instead of
terminating.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Add a deterministic `check_design` state on the edge between
`check_ac_automatable` and `confidence_check`, `on_no: check_refine_limit`,
`on_error: confidence_check` (fail-open, matching the sibling gates). Pure
shell, no model call. Port the predicate from `autodev.yaml:1799` rather than
writing a fourth copy -- see the existing issue on autodev re-deriving
`DESIGN_FAIL` in three inline blocks; a shared fragment under `loops/lib/`
would serve both.

Consider pairing a `format-check` gate on the same edge for the structural
debris (`stale_file_ref`, missing `## Status`), coordinating with ENH-3247
(`format-check --fix` repairing structural debris).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` -- new gate state; the
  routing-summary comment block at the top (lines 4-33) must be updated in the
  same edit, since it is the loop's only routing documentation.

### Dependent Files
- `scripts/little_loops/loops/autodev.yaml:1267,1799,2026` -- existing
  `DESIGN_FAIL` predicate to port from (or factor out with).
- `skills/confidence-check/SKILL.md:141` -- the oracle already computing this
  verdict; its `PD_FAIL` output is the contract being made routable.

### Related Issues
- ENH-3248 (triage the refine-to-ready-issue retry path by failure kind) --
  argues against routing every failure kind to `refine_followup`. A new gate
  that does exactly that conflicts; sequence these deliberately.
- ENH-3247 (`format-check --fix` repairing structural debris).
- The open issue on autodev re-deriving `DESIGN_FAIL` in three inline blocks.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

The gate exists and is already wired in the sibling loop, but not here:

```
autodev.yaml:1267,1273,1799,2026   -> ll-issues check-design (3 DESIGN_FAIL gates)
refine-to-ready-issue.yaml         -> 0 occurrences
```

The loop that *implements* checks the design verdict. The loop whose stated
purpose is "drives a single issue from backlog to ready-state" does not.
`format-check` is likewise absent (0 occurrences), which is why two
`stale_file_ref` findings also survived the run.

The three deterministic gates that *are* wired (`check-verify-verdict`,
`check-open-questions`, `check-acceptance-criteria`) all exit 0 on this issue,
so nothing forced a second pass: `refine_followup` never ran and
`check_refine_limit`'s allowance of 2 went entirely unused. The loop did not
try and fail -- it was never given a reason to iterate.

## Acceptance Criteria

- [ ] `refine-to-ready-issue.yaml` contains a state invoking `ll-issues
      check-design`, positioned so every path to `confidence_check` crosses it.
- [ ] An issue with no `## Program Design` section cannot reach the `done`
      terminal; it routes to `check_refine_limit`.
- [ ] The gate fails open on error, matching `check_hedges` /
      `check_ac_automatable`.
- [ ] `ll-loop validate refine-to-ready-issue` exits 0.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found by reviewing BUG-3243 by hand after `refine-to-ready-issue` reported
`done` on it. The manual review found a missing `## Program Design`, a missing
`## Status`, and an unresolved either/or in the Proposed Solution -- all three
were already named in the issue's own Confidence Check Notes by the loop that
had just declared it ready.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `fsm`, `issue-management`

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:53 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:capture-issue` - 2026-08-17T20:04:12 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
