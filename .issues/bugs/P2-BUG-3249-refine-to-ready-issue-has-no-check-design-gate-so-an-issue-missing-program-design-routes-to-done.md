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
`check_ac_automatable` and `confidence_check`. Pure shell, no model call:

```yaml
action_type: shell
action: ll-issues check-design "$ID"
evaluate: {type: exit_code}
```

**No predicate to port — it is already factored.** An earlier revision of this
issue proposed porting the `DESIGN_FAIL` predicate from `autodev.yaml:1799`, or
extracting a shared fragment under `loops/lib/`. Both are unnecessary:
**ENH-2967 is done** and already did that work. It added
`design_gate_failed(gaps: FormatGaps) -> bool` beside `FormatGaps` in
`issue_parser.py` as the single owner of the three-way OR, and exposed it as
`ll-issues check-design` (`cli/issues/check_design.py`). The three `autodev.yaml`
sites (`:1267`, `:1799`, `:2026`) are already just `if ll-issues check-design
"$ID"` shell calls -- that *is* the factored form. There is no fourth copy to
avoid; the new state is a one-line exit-code gate, the same shape as
`rn-remediate.yaml`'s `ensure_formatted` state (`:100-121`).

**Routing target: `refine_followup`, not `check_refine_limit`, and never
`reconcile_issue`.** This issue lands after ENH-3248 (see Blocked By), which
replaces the uniform `check_refine_limit` remedy with a cheapest-first ladder
(normalize -> reconcile -> refine). A design-gap failure is **research-shaped**,
so it enters that ladder at the refine rung and skips the two cheaper ones. Two
completed issues settle this rather than leaving it to judgment:

- **BUG-3001** (done) -- *"refine-issue never populates `## Program Design`
  despite being the prescribed remedy for the gate"* -- was the reason refine
  was not a trustworthy remedy. It is fixed, so refine now *is* capable.
- **BUG-3002** (done) -- *"autodev routes `design_gate_failed` to
  reconcile-issue, whose contract excludes the Program Design section"* --
  establishes that reconcile is the **wrong** remedy for this failure kind.
  Routing here through ENH-3248's reconcile rung would re-create that exact bug.

`on_error: confidence_check` (fail-open, matching the sibling gates
`check_hedges` / `check_ac_automatable`).

Consider pairing a `format-check` gate on the same edge for the structural
debris (`stale_file_ref`, missing `## Status`), coordinating with ENH-3247
(`format-check --fix` repairing structural debris).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` -- new gate state; the
  routing-summary comment block at the top (lines 4-33) must be updated in the
  same edit, since it is the loop's only routing documentation.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_design.py` -- the `ll-issues
  check-design` entry point the new state calls. Unchanged; consumed as-is.
- `scripts/little_loops/issue_parser.py` -- `design_gate_failed(gaps:
  FormatGaps) -> bool`, the single owner of the predicate (added by ENH-2967).
  Unchanged; listed so it is not re-derived.
- `scripts/little_loops/loops/autodev.yaml:1267,1799,2026` -- the three existing
  `ll-issues check-design` call sites. **Reference shape only, not a port
  target** -- they are already thin shell calls over the factored predicate.
- `skills/confidence-check/SKILL.md:141` -- the oracle already computing this
  verdict; its `PD_FAIL` output is the contract being made routable.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

**Signatures**
- `design_gate_failed(gaps: FormatGaps) -> bool` — `scripts/little_loops/issue_parser.py:576-590`. Single owner of the three-way OR (`program_design_nonspecific` truthy, or `"Program Design"` in `gaps.missing`, or in `gaps.empty`). Fails open (returns `False`) on projects that haven't armed the gate.
- `cmd_check_design(config, args) -> int` — `scripts/little_loops/cli/issues/check_design.py:19-39`. Resolves the issue, calls `check_format_gaps(path)`, returns 1 if `design_gate_failed(gaps)` else 0 (also 1, with a stderr message, if the issue id doesn't resolve). Exit 0 = pass/inert, exit 1 = fail-or-not-found.
- New FSM state (not yet added): a one-line `action_type: shell` gate calling `ll-issues check-design "$ID"` with `evaluate: {type: exit_code}`, matching the shape of state ensure_formatted, `scripts/little_loops/loops/rn-remediate.yaml:100-121` (which calls the broader `format-check` rather than `check-design` specifically, but is the same one-liner + `evaluate: exit_code` + three-way yes/no/error routing template).

**Call Path**
ll-loop run refine-to-ready-issue -> state check_ac_automatable, `scripts/little_loops/loops/refine-to-ready-issue.yaml:335-344` (currently routes its yes-branch straight to state confidence_check, `scripts/little_loops/loops/refine-to-ready-issue.yaml:346-358`) -> new state check_design (not yet added), action `ll-issues check-design "$ID"` -> shells out to `cmd_check_design` (`scripts/little_loops/cli/issues/check_design.py:19`) -> which calls `check_format_gaps()` and returns exit 1 iff `design_gate_failed()` (`scripts/little_loops/issue_parser.py:576`) is true -> `evaluate: {type: exit_code}` -> yes-branch -> state confidence_check, `scripts/little_loops/loops/refine-to-ready-issue.yaml:346-358` (unchanged path) -> no-branch -> state refine_followup, `scripts/little_loops/loops/refine-to-ready-issue.yaml:177-191` -> error-branch -> state confidence_check, `scripts/little_loops/loops/refine-to-ready-issue.yaml:346-358` (fail-open).

Confirmed: state refine_followup, `scripts/little_loops/loops/refine-to-ready-issue.yaml:177-191` (action `/ll:refine-issue ${captured.issue_id.output} --auto --gap-analysis`) and state check_refine_limit, `scripts/little_loops/loops/refine-to-ready-issue.yaml:482-502` (the state that currently routes its yes-branch to refine_followup) already exist in that file today, prior to ENH-3248 landing — so the routing target this issue names is already wired and reachable. ENH-3248 (still a hard blocker) is expected to modify refine_followup's behavior into a remedy ladder, not create the state from scratch.

Reference shape for the compound form (not a template to replicate — the new gate here should stay a plain one-liner per Proposed Solution): the three existing check-design call sites in `scripts/little_loops/loops/autodev.yaml` — state recheck_scores, `scripts/little_loops/loops/autodev.yaml:1251-1278` (action at `scripts/little_loops/loops/autodev.yaml:1265-1274`), the state with action at `scripts/little_loops/loops/autodev.yaml:1797-1843`, and the state with action at `scripts/little_loops/loops/autodev.yaml:1797-2087` — all fold the design check into a larger compound shell block computing pass/fail shell variables, rather than gating on check-design's exit code alone.

**Decision Rules**
- Gate predicate: exit code of `ll-issues check-design "$ID"` (`scripts/little_loops/cli/issues/check_design.py:19-39`) — 0 = pass (or inert on an unarmed project), 1 = fail or issue-not-found.
- On failure (no-branch): route to state refine_followup, `scripts/little_loops/loops/refine-to-ready-issue.yaml:177-191` — never directly to check_refine_limit and never to reconcile_issue — per BUG-3001 (refine now populates Program Design) and BUG-3002 (reconcile's contract excludes Program Design, so routing a design-gap failure there would reproduce that bug).
- On error (CLI/exception failure, not a design-gap failure): fail-open, route to state confidence_check, `scripts/little_loops/loops/refine-to-ready-issue.yaml:346-358` — matching the existing error-branch targets of state check_hedges, `scripts/little_loops/loops/refine-to-ready-issue.yaml:301-310` and state check_ac_automatable, `scripts/little_loops/loops/refine-to-ready-issue.yaml:335-344`.
- No new copy of the design-gate predicate is introduced in YAML and no `loops/lib/` fragment is created — `design_gate_failed()` (`scripts/little_loops/issue_parser.py:576-590`) via `ll-issues check-design` (ENH-2967) is reused as-is.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

1. `refine-to-ready-issue.yaml` contains a `check_design` state, positioned on the edge between `check_ac_automatable` (`:335-344`) and `confidence_check` (`:346-358`), so every path reaching `confidence_check` crosses it first.
2. The gate re-derives nothing: its action is `ll-issues check-design "$ID"` with `evaluate: {type: exit_code}`; no new copy of the design predicate is added to any YAML and no `loops/lib/` fragment is introduced.
3. `on_no` routes to `refine_followup` (`:177-191`), `on_error` routes to `confidence_check` (`:346-358`) fail-open — matching the sibling gates `check_hedges`/`check_ac_automatable`.
4. The top-of-file routing-summary comment block (`:4-33`) is updated in the same edit to include the new state, since it is the loop's only routing documentation.
5. `ll-loop validate refine-to-ready-issue` exits 0 and `python -m pytest scripts/tests/` passes, including a regression test asserting an issue with no `## Program Design` section cannot reach the `done` terminal.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

The gate exists as a factored, reusable CLI (ENH-2967) and is already wired in
the sibling loop, but not here:

```
autodev.yaml:1267,1273,1799,2026   -> ll-issues check-design (3 DESIGN_FAIL gates)
refine-to-ready-issue.yaml         -> 0 occurrences
```

So this is a pure wiring omission, not a missing capability: the predicate, the
CLI, and the calling idiom all already exist.

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
      terminal; it routes into ENH-3248's remedy ladder at the **refine** rung
      (`refine_followup`), not at `normalize_structure` or `reconcile_issue`.
- [ ] The gate re-derives nothing: it shells out to `ll-issues check-design` and
      routes on exit code. No new copy of the `DESIGN_FAIL` predicate is added
      to any YAML, and no `loops/lib/` fragment is introduced (ENH-2967 already
      factored this).
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

## Related Issues

- **ENH-3248** (triage the retry path by failure kind) -- hard prerequisite, see
  Blocked By. The earlier conflict ("a new gate routing everything to
  `check_refine_limit` is exactly the always-refine pattern ENH-3248 argues
  against") is **resolved**: this gate enters ENH-3248's ladder at the refine
  rung, and ENH-3248 records the design-gap exception in its escalation table.
- **ENH-2967** (done) -- factored `design_gate_failed()` into `issue_parser.py`
  and shipped `ll-issues check-design`. This is why the Proposed Solution needs
  no predicate port and no `loops/lib/` fragment.
- **BUG-3001** (done) -- made `/ll:refine-issue` actually populate
  `## Program Design`, which is what makes `refine_followup` a capable remedy for
  this gate's failure.
- **BUG-3002** (done) -- established that `/ll:reconcile-issue` is the wrong
  remedy for a design-gap failure (its contract excludes Program Design).
- **ENH-3247** (`format-check --fix` repairing structural debris) -- supplies the
  paired `format-check` gate this issue may add on the same edge.
- **ENH-3250** -- companion coverage gap in the same loop, captured in the same
  pass. Deliberately *not* co-sequenced: it is design-decision-first and is being
  worked as a spike rather than alongside this fix.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `fsm`, `issue-management`

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-18T14:52:51 - `1b75a5d5-cd19-4f54-9db4-f0438e3206cc.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:53 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:capture-issue` - 2026-08-17T20:04:12 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
