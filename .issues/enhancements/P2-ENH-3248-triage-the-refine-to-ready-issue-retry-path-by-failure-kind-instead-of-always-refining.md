---
id: ENH-3248
type: ENH
title: Triage the refine-to-ready-issue retry path by failure kind instead of always
  refining
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:30:10Z'
blocked_by:
- ENH-3246
- ENH-3247
relates_to:
- ENH-3244
- BUG-3245
- ENH-3238
depends_on: []
confidence_score: 80
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3248: Triage the refine-to-ready-issue retry path by failure kind instead of always refining

## Summary

`check_refine_limit` routes every gate failure to a single remedy, `refine_followup`
(`/ll:refine-issue --auto --gap-analysis`), which is additive-only. Two of the four gates that reach
it need content *removed* or *rewritten*, so their remedy is structurally incapable of clearing
them. Route by failure kind: deterministic normalize, then self-referential reconcile, then
re-research refine.

## Current Behavior

Four gates in `scripts/little_loops/loops/refine-to-ready-issue.yaml` route to `check_refine_limit`
(`:482-502`), which routes uniformly to `refine_followup` (`:177-191`):

| Gate | Line | Failure means | Needs | `--gap-analysis` can do it |
|---|---|---|---|---|
| `check_verify_verdict` | `:289-299` | claims don't match the codebase | re-research | ✅ |
| `check_readiness` | `:360-390` | confidence below threshold | re-research | ✅ |
| `check_hedges` | `:301-310` | unresolved hedges / template debris | answer or **delete** | ❌ |
| `check_ac_automatable` | `:335-344` | manual-verification ACs | **rewrite ACs** | ❌ |

`refine_followup` is additive-only by contract (`:177-181`): *"Gap-analysis is additive-only (never
removes content) and does not consume max_refine_count."*

Observed on the ENH-3238 run
(`.loops/.history/2026-08-17T183652-refine-to-ready-issue/events.jsonl`, 27 routes):

```
refine_issue → wire_issue → verify_issue → VALID → check_hedges NO → hedge_attempts=1 → refine_followup
             → check_wire_done(=1) → verify_issue → VALID → check_hedges NO → hedge_attempts=2 → PROCEED
             → check_ac_automatable → confidence_check → done
```

`check_hedges` failed on template placeholders. Its remedy could not delete them. The retry produced
no improvement, `check_hedges` failed again, `check_hedge_attempts` hit its cap, and the loop
proceeded to `done` with the debris intact — plus new debris the additive retry itself created
(BUG-3245).

## Expected Behavior

A gate failure routes to a remedy capable of fixing that kind of failure, escalating cheapest-first:

```
normalize (deterministic, no LLM)  →  reconcile (self-referential)  →  refine (re-research)
```

- **Structural debris** → `ll-issues format-check --fix --apply` (ENH-3247). No model.
- **Unfilled placeholders / stale directive sections / non-automatable ACs** → `/ll:reconcile-issue`
  (ENH-3246). Reads the issue's own findings; no codebase research.
- **Claim/codebase mismatch, low readiness** → `refine_followup`. Unchanged.
- **Missing/failing Program Design (BUG-3249's new `check_design` gate)** → `refine_followup`
  **directly**, skipping both cheaper rungs. See Decision Rules › Design-gap exception.

A retry escalates to `refine_followup` only when the cheaper remedies cannot clear the gate — except
for the design-gap kind, where the cheaper rungs are known-incapable rather than merely untried.

## Motivation

The uniform remedy is the defect — not the BUG-3170 cap, and not `--gap-analysis`, which is correct
for the two research-shaped failures. Half the triggers get a remedy that cannot fix them, so their
retry is guaranteed waste: it spends the shared refine budget, produces no progress toward the gate
it was invoked for, and (per BUG-3245) actively degrades the file.

Cost matters here. On the observed run `refine_issue` billed ~$0.65 and `refine_followup` ~$0.43,
against a total run cost of ~$2.53 for 22 minutes. A deterministic normalize is effectively free and
a reconcile pass is a bounded rewrite with no codebase research. Ordering cheapest-first converts the
most common failure kinds into the cheapest remedies.

## Proposed Solution

1. **Add a `normalize_structure` state** running `ll-issues format-check ${issue_id} --fix --apply`
   (ENH-3247). Deterministic, no LLM, unconditional after `refine_issue` / `refine_followup` /
   `wire_issue`. Non-fatal on error.
2. **Add a `reconcile_issue` state** invoking `/ll:reconcile-issue ${issue_id}`, with a
   `pruning_profile` matching the other slash-command states in this loop.
3. **Retarget the two mismatched gates**:
   - `check_ac_automatable.on_no` → `reconcile_issue` (ACs are in reconcile's unconditional rewrite
     list) instead of `check_refine_limit`.
   - `check_hedges` / ENH-3244's placeholder gate → `normalize_structure`, then `reconcile_issue`,
     escalating to `check_refine_limit` only if the gate still fails.
4. **Leave `check_verify_verdict` and `check_readiness` routing unchanged** — `refine_followup` is
   the correct remedy for both.
5. **Bound the new states** with per-run attempt counters in `${context.run_dir}`, mirroring
   `check_refine_limit` (`:482-502`) and `check_hedge_attempts` (`:312-333`), so a gate that a
   reconcile cannot clear escalates rather than spinning.
6. **Raise `max_steps`** to cover the added states, with the arithmetic recorded in a comment as the
   file already does for ENH-3031 (`:38-43`) and BUG-3065 (`:44-51`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the two new states, the retargeted
  gates, the attempt counters, `max_steps`, and the routing-summary comment block (`:4-33`), which
  is maintained as documentation and must be updated to match.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:78-90` — `resolve_issue` initializes the
  per-run counter files; new counters must be initialized there too.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:606-766` — the `diagnose` /
  `write_failure_evidence` / `classify_terminal` chain enumerates captured states by name. New
  states with `capture:` must be added to those blocks or their failures will be invisible in the
  evidence file.
- `scripts/little_loops/loops/autodev.yaml` — nests this loop; a changed step budget and terminal
  behavior affect it. The `refine-broke-down` / `refine-terminal-class` artifacts it reads must keep
  their current meaning.
- `scripts/little_loops/fsm/validation/` — `ll-loop validate` must pass on the modified YAML.

### Similar Patterns
- `autodev.yaml:1557-1608` (`check_reconcile_needed`) and `:1921` (`reconcile_current`) — the
  existing reconcile call state, including its `pruning_profile` shape and one-shot guard. Model the
  new `reconcile_issue` state on it.
- `check_hedge_attempts` (`:312-333`) — the per-run attempt-counter idiom to mirror for the new
  bounds.

### Tests
- `scripts/tests/` — `ll-loop validate refine-to-ready-issue` exits 0 (MR-1..MR-14 plus routing
  reachability); every state named in the `diagnose` / `write_failure_evidence` blocks exists; the
  routing-summary comment matches the actual `on_yes`/`on_no` targets.
- A routing test asserting `check_ac_automatable.on_no` reaches `reconcile_issue` and that
  `check_verify_verdict.on_no` still reaches `check_refine_limit`.

### Documentation
- The in-file routing summary (`:4-33`) is the authoritative description and must be updated.

### Configuration
- N/A — new counters are run-scoped files under `${context.run_dir}`, not config.

## Program Design

### Call Path

`check_ac_automatable` -> `reconcile_current` -> `cmd_format_check`

- `check_ac_automatable` (`refine-to-ready-issue.yaml:335-344`) currently routes `on_no` to
  `check_refine_limit`; retargeted to the new `reconcile_issue` state.
- `reconcile_current` (`scripts/little_loops/loops/autodev.yaml:1921`) is the existing reconcile call
  state whose shape the new state copies.
- `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py:191`) backs the new
  `normalize_structure` state via `--fix --apply` (ENH-3247).

### Decision Rules

- **Escalation order**: deterministic → self-referential → re-research. Never invoke a more expensive
  remedy before a cheaper one that can address the same failure kind.
- **Remedy-capability match**: a gate routes to a remedy only if that remedy can perform the
  operation the failure requires (delete / rewrite / research). This is the invariant the current
  design violates.
- **Design-gap exception: cheapest-first is subordinate to remedy-capability.** BUG-3249 adds a
  `check_design` gate to this loop. Its failure kind routes **straight to `refine_followup`**, not
  through `normalize_structure` or `reconcile_issue`. This is not a violation of the escalation order
  — it is the capability rule taking precedence, and two completed issues make it a fact rather than
  a judgment call:
  - **BUG-3002** (done) — *"autodev routes `design_gate_failed` to reconcile-issue, whose contract
    excludes the Program Design section"*. Reconcile **cannot** write `## Program Design`. Sending a
    design-gap failure down the reconcile rung re-creates a bug that was already fixed once.
  - **BUG-3001** (done) — *"refine-issue never populates `## Program Design` despite being the
    prescribed remedy for the gate"*. Now fixed, so refine is the capable remedy.

  A missing design section is *absent research*, not *stale or malformed text*, so no deterministic
  normalize and no self-referential rewrite can produce it. Generalized: **the ladder is ordered by
  cost only among remedies that are capable; an incapable rung is skipped, not tried.**
- **Escalation is mandatory, not optional**: every new state is bounded by a per-run counter and
  falls through to `check_refine_limit`, so a failure the cheap remedies cannot fix still reaches
  refine and ultimately `breakdown_issue`.
- **Unchanged routing**: `check_verify_verdict` and `check_readiness` keep `refine_followup`.

### Signatures
- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int` — backs the new
  `normalize_structure` state and returns 1 when gaps remain, giving that state a deterministic
  exit-code gate; defined at `scripts/little_loops/cli/issues/format_check.py:191`.

## Implementation Steps

1. Land ENH-3247 (`format-check --fix` structural repairs) and ENH-3246 (widened reconcile mandate)
   — both are hard prerequisites; see Blocked By.
2. Add `normalize_structure` and `reconcile_issue` states with `capture:` and pruning profiles.
3. Initialize the new attempt counters in `resolve_issue`.
4. Retarget `check_ac_automatable.on_no` and the hedge/placeholder path; leave verify/readiness
   routing untouched.
5. Add the new states to the `diagnose`, `write_failure_evidence`, and `classify_terminal` blocks.
6. Recompute `max_steps` and update the routing-summary comment.
7. `ll-loop validate refine-to-ready-issue` exits 0; add the routing tests.
8. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Eliminates a guaranteed-waste retry for half the gates that trigger one, and
  cuts cost by matching remedy to failure. Not P1: the loop still terminates correctly today, just
  with unfixed debris and a wasted pass.
- **Effort**: Medium - two states, counter plumbing, four enumeration blocks to keep in sync,
  `max_steps` arithmetic, and validation. The FSM's diagnose/evidence blocks make every state
  addition wider than it first appears.
- **Risk**: Medium - routing changes in a 40-step FSM with a stall-detection circuit
  (`circuit.repeated_failure`, `:72-75`). New cycles risk phantom convergence if the attempt
  counters are wrong. Mitigated by mirroring the existing counter idiom and by `ll-loop validate`.
- **Breaking Change**: No - external artifacts (`refine-broke-down`, `refine-terminal-class`) keep
  their meaning.

## Scope Boundaries

**This does not fix the substantive-error class.** ENH-3238's two real defects — a wrong edit site
and a wrong generated-file claim — required *probing the codebase*, which only `verify_issue` does.
No amount of retry triage catches them; that is ENH-3238's subject. This issue is about not wasting
a pass on failures the retry cannot fix.

**Not touching BUG-3170's cap.** The cap on genuine prose hedges is correct and stays. This issue
changes what a retry *does*, not how many are allowed.

**Not making `--gap-analysis` destructive.** Its additive-only contract is deliberate and is what
makes it safe to run repeatedly. Removal capability comes from the other two remedies.

## Blocked By

- ENH-3246 — reconcile must be permitted to rewrite the Integration Map subsections before routing
  placeholder failures to it is worthwhile.
- ENH-3247 — `format-check --fix` must be able to repair structural debris before
  `normalize_structure` has anything to do.

## Related Issues

- ENH-3244 — **supplies the placeholder signal this triage routes, and nothing more.** ENH-3244 is
  detection-only by decision: it adds the `format-check` gap class and JSON key, and this issue owns
  every `refine-to-ready-issue.yaml` edit. Both previously proposed adding a gate to that file, which
  would have been a merge collision in the same sprint wave.
- BUG-3249 — adds the `check_design` gate to this loop. Sequenced **after** this issue, and its
  failure kind takes the design-gap exception in Decision Rules (straight to `refine_followup`).
- BUG-3245 — removes the debris the current additive retry creates.
- BUG-3001, BUG-3002 (both done) — the evidence behind the design-gap exception.
- ENH-3238 — the run that surfaced this.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- BUG-3249
- ENH-3250

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (hard override; would otherwise be PROCEED WITH CAUTION)
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- Both `blocked_by` dependencies (ENH-3246, ENH-3247) are still `open`, not `done`/`cancelled` — the
  Implementation Steps section itself calls both "hard prerequisites," so this issue cannot be
  implemented as written until they land.

### Gaps to Address
- Land ENH-3247 (`format-check --fix` structural repairs) before `normalize_structure` has anything
  to call.
- Land ENH-3246 (widened reconcile mandate) before routing placeholder/AC failures to
  `reconcile_issue` is safe.

### Outcome Risk Factors
- Moderate complexity: the change is concentrated in one file
  (`scripts/little_loops/loops/refine-to-ready-issue.yaml`) but touches many distinct locations
  (two new states, two retargeted gates, counter init, four enumeration blocks, `max_steps`
  arithmetic), with real risk of phantom convergence against the existing
  `circuit.repeated_failure` stall detector if the new attempt counters are wired incorrectly.

## Session Log
- `/ll:confidence-check` - 2026-08-17T21:35:01 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:13:03 - `ffec4b47-4ed9-4eda-baf1-3dc49ac82fa1.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
