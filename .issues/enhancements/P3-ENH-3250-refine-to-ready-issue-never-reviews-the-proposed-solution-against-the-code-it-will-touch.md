---
id: ENH-3250
type: ENH
title: refine-to-ready-issue never reviews the Proposed Solution against the code
  it will touch
priority: P3
status: in_progress
testable: true
relates_to:
- BUG-3249
- ENH-3248
- BUG-3243
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T20:04:02Z'
blocked_by: []
confidence_score: 100
outcome_confidence: 76
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 16
decision_needed: false
---

# ENH-3250: refine-to-ready-issue never reviews the Proposed Solution against the code it will touch

## Summary

Every LLM state in `refine-to-ready-issue.yaml` evaluates *descriptive* content
-- what the issue says about the code. No state evaluates the *prescriptive*
content -- what happens if the Proposed Solution is implemented as written.
Defects that only appear when the proposal is read against the code it will
touch pass the whole chain.

## Current Behavior

The four LLM states and the question each asks:

| state | question | on BUG-3243 |
|---|---|---|
| `refine_issue` | what's missing about the code? | worked -- diagnosis accurate |
| `wire_issue` | what else touches this? | worked -- found both call sites |
| `verify_issue --check` | are the issue's claims true? | worked -- every claim was true |
| `confidence_check` | score a rubric | 100 / 82 |

`verify_issue` is the only state that consults the codebase adversarially, and
its contract is claim verification: it tests assertions the issue makes. On
BUG-3243 every such assertion was correct, so it returned VALID -- correctly.

A manual review of the same issue then found three defects none of the four
could have surfaced:

1. The Proposed Solution said to add `timeout=` to a `subprocess.run` call
   whose handler is `except (OSError, ValueError)`. `subprocess.TimeoutExpired`
   subclasses `SubprocessError`, not `OSError`, so implementing the proposal
   verbatim converts a hang into an uncaught exception. This is not a false
   claim in the issue -- it is a consequence of the proposal.
2. Two existing tests patch `subprocess.run` with a single `return_value`; the
   proposal adds a second git call that would silently receive the same mock,
   putting the tests on a code path that contradicts the issue's own
   acceptance criteria.
3. An acceptance criterion was missing for the two CLI surfaces `wire_issue`
   had already correctly identified as affected -- the wiring pass found them,
   but nothing checks that the ACs cover what the wiring found.

## Scope Boundaries

**Design decisions settled 2026-08-19 — now implementation-ready.** This issue
was removed from the `refine-issue-pipeline` sprint on 2026-08-17 as
design-decision-first, gated on the three Open Questions below. All three are
now resolved (see `## Open Questions`), AC1 is satisfied, and `ll-issues
check-design ENH-3250` exits 0. The `/ll:spike` pass was declined on
2026-08-17 as the correct call: the open questions were decision ambiguity
(which of two known shapes to build), not an unproven internal mechanism —
both candidate shapes have working precedents in this repo. Re-schedule into a
sprint; no spike required.

**Out of scope:** replacing `check_verify_verdict`'s binary contract wholesale,
and adding any new LLM-invoking FSM state (that is Option A, rejected — see
`## Proposed Solution`). `implementation_order_risk` routing is also out of
scope; see the Decision Rationale for why it was dropped from the flag-routing
half.

The companion defect BUG-3249 stays in the sprint: it is a pure wiring omission
with a factored CLI already available, and does not depend on this issue's
outcome.

## Expected Behavior

Before an issue is declared ready, something evaluates the Proposed Solution
against the code it names and reports consequences the issue does not
anticipate -- exception-handling interactions, test fixtures the change
invalidates, acceptance criteria that do not cover the identified integration
points.

## Motivation

`refine-to-ready-issue` is the gate that declares an issue safe to hand to
`/ll:manage-issue` and to autonomous loops (`autodev`, `recursive-refine`,
`auto-refine-and-implement` all call it as a sub-loop). A `done` verdict from
it is a promise that implementing the issue as written will not surprise the
implementer. On BUG-3243 that promise was false in a way no state in the chain
could have caught: the proposal, implemented verbatim, would have converted a
hang into an uncaught exception and put two existing tests on a path
contradicting the issue's own acceptance criteria.

The cost lands downstream, where it is most expensive: an unsound proposal that
clears the gate is discovered mid-implementation, after a worktree, a branch,
and an LLM implementation pass have already been spent on it — and in
autonomous runs, often after a commit. Catching it during refinement costs
marginal tokens on a call that already loads the relevant code.

## Proposed Solution

**Option A**: New adversarial FSM state in `refine-to-ready-issue.yaml`, modeled
on `/ll:go-no-go`'s debate/judge shape, wired via the write-verdict/read-verdict
convention (a new `VERDICT_JSON` trailer plus a sibling `check_*` gate).

> **Selected:** Option B — Option A is rejected on cost (a fifth LLM call plus a
> new verdict shape and resolution path); see Decision Rationale below.

**Option B**: Widen `verify_issue`'s mandate (`commands/verify-issues.md`) to
cover proposal-vs-code consequences (exception-handler compatibility,
mock-fixture reuse, AC coverage of `wire_issue`'s findings) alongside its
existing claim-verification pass — combined with routing one of
`confidence_check`'s currently-unread "Outcome Risk Factors" flags
(`spike_needed`) into a `check-flag` gate in `refine-to-ready-issue.yaml`.

> **Selected:** Option B, in three parts (B1/B2/B3 below). These labels are
> used verbatim in `## Implementation Steps` and in the Open Questions
> resolutions; there is no "Option C".

**B1 — widen the mandate.** Add a proposal-vs-code consequence check to
`commands/verify-issues.md` §B, as an explicitly separate labeled sub-check
from the existing claim-verification pass.

**B2 — give the new failure kind its own verdict and its own remedy.** Add a
`PROPOSAL_UNSOUND` verdict to §C's verdict table and carve it out of §2.5's
"any other verdict → `NON_VALID`" collapse, then route it to `reconcile_issue`
rather than `refine_followup`. Rationale under *Why the binary verdict must
split*, below.

**B3 — route `spike_needed`.** One new `check-flag`-shaped gate in
`refine-to-ready-issue.yaml`, using `autodev.yaml`'s two-field one-shot guard,
not the naive single-field shape.

### Decision Rationale

**Why the widened-mandate half (B1) over Option A:** AC4 requires the added cost
be measured against the observed baseline. Widening `verify_issue` adds zero new
FSM states and zero new LLM calls — it already loads the relevant code to check
claims, so widening its prompt to also trace proposal-vs-code consequences is
marginal token cost on a call that already runs, not a new agent spin-up.
Option A adds a fifth LLM call and requires building a new verdict shape
(`go-no-go`'s judge output is prose — `VERDICT: GO|NO-GO` — not the
`VERDICT_JSON` trailer the write-verdict/read-verdict convention needs) plus a
new failure-resolution path, since no `resolve-decision`-style sub-loop exists
yet for a from-scratch adversarial state.

**Why the binary verdict must split (B2 is not optional):**
`check_verify_verdict` (`refine-to-ready-issue.yaml:327-337`) is binary — its
`on_no` goes to `check_refine_limit` → `refine_followup` — and
`commands/verify-issues.md:239-242` collapses *every* non-VALID verdict to
`verify_verdict: NON_VALID`. Without B2, a widened `verify_issue` that finds
"the Proposed Solution contradicts the code it names" is remedied by *refine
again*: the always-refine pattern ENH-3248 removed for the
`check_ac_automatable` rung, applied to a failure kind refining cannot fix
(more research does not rewrite an unsound directive section). The correct
remedy already exists in this file: `reconcile_issue` (`:448`,
`/ll:reconcile-issue`), whose documented scope is rewriting directive sections
from the reviewer's own findings, bounded by `check_reconcile_limit` (`:423`,
one attempt per run). B2 wires the new failure kind to it. AC2 would be
technically satisfiable without B2 (a `NON_VALID` *is* a flag), but the loop
would spend its one refine budget on the wrong repair — so B2 is scoped in.

**Why §B is the right home for a prospective check:** §B check 5 (decisions-rule
conflict, `commands/verify-issues.md:130-155`) *already* reasons prospectively
about the Proposed Solution — it asks "does the issue's proposed solution
conflict with any active required rule". A proposal-vs-code consequence check is
the same kind of judgment against a different reference (the code rather than
the decisions log), not a foreign mandate bolted onto a retrospective command.
`DECISIONS_VIOLATION` is also the precedent for B2's new verdict value: §C's
table already carries a verdict that exists specifically for a prospective
finding.

**Why only `spike_needed` in the flag-routing half:** `implementation_order_risk`
is written by `set_flags.py` but consumed by **no loop, skill, or command
anywhere in the repo** — there is no precedent remedy to mirror and no defined
recourse for an `on_yes` branch. A gate whose `on_yes` has nowhere to go is
BUG-3249's defect inverted (a verdict computed and ignored → a gate fired with
no repair). It is dropped from scope; wiring it needs its own issue that first
defines the remedy. `spike_needed` keeps a precedent: `autodev.yaml:1315-1391`
(`check_spike_needed` → `run_spike`) and `scripts/little_loops/loops/spike-gate.yaml`.

**Why `spike_needed`'s gate must use the two-field guard:** all four `FlagRule`s
gate on `_outcome_risk_produced_factory(threshold)`
(`scripts/little_loops/cli/issues/set_flags.py:191-215`), and `spike_needed`
additionally on `_spike_precondition_factory` + `_score_test_coverage_gate`.
The flag stays `true` after a spike runs, so the single-field
`check_decision_needed`/`check_missing_artifacts` shape would re-fire on every
subsequent pass. `autodev.yaml:1315-1391` already solved this with an inline
`show --json` predicate reading `spike_needed AND NOT spike_attempted`
(`ll-issues check-flag` cannot express a two-field condition in one call).
Mirror that predicate; the gate is therefore `fragment: shell_exit` over inline
python, *not* a literal `check-flag` invocation.

**What the flag-routing half does and does not fix:** it improves routing on the
*already-failing* branch only. Every `FlagRule` shares the
`_outcome_risk_produced_factory(threshold)` precondition, so these flags are
only ever written when `outcome_confidence` is already sub-threshold — the same
branch `check_decision_needed`/`check_missing_artifacts` already sit on. It
cannot touch `check_outcome`'s `on_yes` → `done` path, which is the gap
`## Root Cause` identifies. B1+B2 is what covers that path (`verify_issue` runs
before `confidence_check` on every route). An earlier revision of this section
claimed the flag routing "independently fixes the exact routing gap" — that was
wrong and is corrected here.

**Risk accepted:** widening `verify_issue`'s mandate conflates two different
judgments (retrospective claim-checking vs. prospective consequence-reasoning)
into one state/prompt, which risks diluting either task's quality — the same
risk `## Root Cause` flags as the reason the current four-state chain misses
this class of defect in the first place. Mitigation: implement as two
explicit, separately-labeled sub-checks within the same `verify_issue`
prompt and verdict (not blended prose), so each judgment stays isolated even
though they share a call. If this proves to dilute quality in practice, that
is a concrete, measurable reason to fall back to Option A later — not a
reason to default to the more expensive option now.

**Blast radius outside this loop (constrains B1):** `/ll:verify-issues` also runs
standalone and in batch over every open issue, in non-check mode where it writes
files after user approval — the loop's single `--check` call is not the only
caller. The widened §B sub-check must therefore carry an explicit precondition:
**skip when the issue has no `## Proposed Solution`, or when that section is
still template boilerplate/`TBD`.** Without it, every batch run pays the added
cost on issues that have nothing prescriptive to check, and `PROPOSAL_UNSOUND`
becomes reachable for issues that never proposed anything. The AC4 cost
measurement must cover the batch path, not only the loop's single call.

**Model tier**: not a live decision under this approach. The widened
`verify_issue` reuses its existing invocation, which inherits whatever model
tier its invoking skill already pins (no loop in this codebase sets a
per-state `model:` override); there is no new state to assign a tier to.

## Integration Map

### Files to Modify
- `commands/verify-issues.md` -- three edits: **(B1)** widen §B "Verify Against
  Codebase" with a proposal-vs-code consequence sub-check, explicitly labeled
  separate from the claim-verification pass and preconditioned on a non-boilerplate
  `## Proposed Solution`; **(B2)** add `PROPOSAL_UNSOUND` to §C's verdict table
  (`:175-188`) and carve it out of §2.5's blanket non-VALID → `NON_VALID` mapping
  (`:239-242`) so it persists as its own `verify_verdict` value; also extend §2.5's
  `--check` exit-code contract to state that `PROPOSAL_UNSOUND` is still a
  nonzero/`exit 1` outcome (the split is in the persisted verdict, not the exit code)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` -- **(B2)** a new
  `check_proposal_unsound` gate spliced onto `check_verify_verdict`'s `on_no`
  (`:335`), routing `on_yes: check_reconcile_limit` (`:423` → `reconcile_issue`
  `:448`) and `on_no: check_refine_limit` (today's target, unchanged);
  `on_error: check_refine_limit` (fail-open to the existing behaviour, matching
  this file's convention). **(B3)** one new gate state routing `spike_needed`
  with `autodev.yaml`'s two-field one-shot predicate, plus its `on_yes` target
- `scripts/little_loops/cli/issues/check_verify_verdict.py` -- **(B2)** the
  reader for the new gate. **Do not** add a third exit code to
  `cmd_check_verify_verdict` (`:41`): `0`/`1` are load-bearing for every existing
  caller, `2` is reserved for infra error by the convention `check_outcome`
  documents (`:534-537`, BUG-2726), and `3` is already claimed repo-wide as
  ABSTAIN (`harness_exit`'s `abstain_on_exit_3`,
  `scripts/little_loops/loops/lib/common.yaml:23-35`). Add a
  `--proposal-unsound` query flag instead (exit 0 when
  `verify_verdict == PROPOSAL_UNSOUND`, 1 otherwise) so the new gate is a plain
  `fragment: shell_exit` binary probe. `PROPOSAL_UNSOUND` already falls through
  the existing binary reader as non-VALID → exit 1 with no code change (`:61-70`),
  so `check_verify_verdict`'s own contract and tests stay untouched

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/commands/verify-issues.toml` -- generated per-host mirror of
  `commands/verify-issues.md` (byte-for-byte prompt body inside a TOML
  wrapper); regenerate via `ll-adapt` after editing the canonical command, or
  this mirror silently keeps describing the old claim-verification-only
  mandate [Agent 1/2 finding]
- `.qwen/commands/ll/verify-issues.md` -- same generated-mirror staleness risk
  as the Gemini mirror above [Agent 1/2 finding]
- `.kimi-code/skills/ll-verify-issues/SKILL.md` -- same generated-mirror
  staleness risk, produced by the same `ll-adapt` emitter family [Agent 1/2
  finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` -- calls `refine-to-ready-issue`
  as a sub-loop (`loop: refine-to-ready-issue`), so the two new gate states
  sit on a path this loop also traverses; separately, `autodev.yaml` already
  implements a *different*, tested `spike_needed` gating shape
  (`check_spike_needed`/`run_spike`, `:1315-1391`) with a two-field one-shot
  guard (`spike_needed == 'true' AND spike_attempted != 'true'`) -- this
  contradicts the issue's own Codebase Research Findings claim that "there is
  no existing resolve-decision-style sub-loop for either flag": a working
  precedent for `spike_needed` specifically already exists here and should be
  mirrored (or explicitly diverged from) rather than inventing an unrelated
  shape [Agent 1/2 finding]
- `scripts/little_loops/loops/recursive-refine.yaml` -- calls
  `refine-to-ready-issue` as a sub-loop [Agent 1 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` -- delegates to
  `refine-to-ready-issue` [Agent 1 finding]
- `scripts/little_loops/loops/spike-gate.yaml` -- separate loop already using
  `ll-issues check-flag` for `spike_needed`/`spike_completed`; a naming/shape
  precedent to check the new gate against [Agent 1 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` -- uses `ll-issues
  check-flag` for `decision_needed` in the same single-field-gate shape being
  mirrored here [Agent 1 finding]

### Related Issues
- ENH-3248 (triage the refine-to-ready-issue retry path by failure kind
  instead of always refining) -- **`done` 2026-08-18; now a dependency, not a
  parallel design.** Its `check_reconcile_limit`/`reconcile_issue` rung
  (`refine-to-ready-issue.yaml:423-461`) is exactly the remedy B2 routes
  `PROPOSAL_UNSOUND` to. The original "design these together" note has been
  discharged: the failure kind here ("proposal is unsound") does need a
  different remedy than "refine again", and ENH-3248 already built it.
- BUG-3249 (refine-to-ready-issue has no `check-design` gate) -- companion
  defect in the same loop, captured in the same pass.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Write-verdict/read-verdict is the established shape for gating on a prior LLM state's output** — never read raw LLM structured output directly in a later gate. `verify_issue` (`scripts/little_loops/loops/refine-to-ready-issue.yaml:279-287`) persists `verify_verdict: VALID|NON_VALID` to frontmatter; `check_verify_verdict` (`:289-299`) reads it via `ll-issues check-verify-verdict` (`scripts/little_loops/cli/issues/check_verify_verdict.py`). The same pair-shape recurs at `check_decision_mid_refine` (`:200`, reads `decision_needed` via `ll-issues check-flag`) and `check_missing_artifacts` (`:471-480`, reads `missing_artifacts`). Any new adversarial state should write a persisted verdict and add a sibling gate to read it, not branch on raw LLM output inline.
- **The routing gap is concrete and already located**: `check_outcome` (`refine-to-ready-issue.yaml:392`) routes `on_yes` straight to `done` (`:434`) when `outcome_confidence` clears `outcome_threshold` — bypassing `check_decision_needed` (`:438-449`), which is reachable only via `check_outcome`'s `on_no` path. A `decision_needed: true` flag stamped by `confidence-check`'s Phase 4.6 write-back (`skills/confidence-check/SKILL.md:425-439`, via `ll-issues set-flags` → `apply_flags_from_notes()` in `scripts/little_loops/cli/issues/set_flags.py:238-331`) is therefore never consulted on the passing-outcome path — this is the exact routing gap that let BUG-3243's recorded "either/or" risk factor go unrouted to `done`.
- **`confidence_check` is a `loop:`-call to a self-contained oracle sub-loop**, not inlined prompt states: `refine-to-ready-issue.yaml:346-358` calls `oracles/verify-confidence-scores.yaml`. A second oracle example with a deterministic (non-LLM) `classify`/`route:` aggregation shape is `oracles/code-run-gate.yaml:399-468`. A new adversarial-review state, if added as its own oracle, would follow this `loop:`-call convention rather than being written inline.
- **`/ll:go-no-go` (`skills/go-no-go/SKILL.md`) is not wired into any FSM loop.** `grep go-no-go scripts/little_loops/loops/` matches only a comment in `autodev.yaml:2001` describing a manually-or-go-no-go-stamped `outcome_gate_waived` frontmatter flag, read at `recheck_after_size_review` (`autodev.yaml:1990-2013`) via the same read-a-frontmatter-flag shape as above — not a direct state invocation. `go-no-go` already exposes a `--check` flag (`SKILL.md:41`, Phase 5, `:444-461`) documented as integrating with FSM `evaluate: type: exit_code` routing, the same contract `verify_issue --check` uses — so it is FSM-portable if wired, but isn't today. Its judge verdict (`VERDICT: GO|NO-GO`, `SKILL.md:307-333`) is prose, not a tagged-JSON trailer like `confidence-check`'s `VERDICT_JSON` convention (`skills/confidence-check/rubric.md:412-418`, consumed in `scripts/little_loops/cli/action.py`) — a new state modeled on go-no-go would need to add that trailer to fit the write-verdict/read-verdict shape above.
- **`verify_issue --check`'s contract is claim-verification only**, not prescriptive review: `commands/verify-issues.md` §B "Verify Against Codebase" (`:126-130`) checks "files exist / line numbers / code snippets / is the described behavior accurate" — it loads related code only to corroborate claims about *current* state, never to trace consequences of implementing the Proposed Solution (exception-handler compatibility, mock-fixture reuse, AC-vs-integration-point coverage). This confirms the issue's own Current Behavior table.
- **Model tier**: no loop in `scripts/little_loops/loops/*.yaml` (incl. `oracles/`) currently sets the per-state `model:` schema field (`scripts/little_loops/fsm/fsm-loop-schema.json:611-617`, exists but unused repo-wide). Model tier is pinned at the invoked skill's frontmatter instead — `skills/go-no-go/SKILL.md:4` and `skills/confidence-check/SKILL.md:5` both declare `model: sonnet`; `skills/analyze-history/SKILL.md:5` is the one `haiku` exception found. A new state invoking a slash-command/skill inherits that skill's pinned model rather than needing its own override.
- **The cited baseline (4 LLM calls, 17m49s, ~$1.47/run) has no backing artifact.** No postmortem, run log, or `.loops/.history` entry for BUG-3243 contains these figures (`postmortems/**/*3243*` and `.loops/.history/**/*3243*` both empty). BUG-3243's own `## Session Log` records `/ll:wire-issue` 19:42:10, `/ll:verify-issues` 19:43:38, `/ll:confidence-check` 19:45:58 — a ~4-minute span across three of the four states, with no `/ll:refine-issue` entry logged — consistent with but not itself establishing the cited numbers.

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- **Line numbers in the Codebase Research Findings above are stale — confirmed still structurally accurate.** `refine-to-ready-issue.yaml` changed 2026-08-18 (after this issue's 2026-08-17 refine pass): two new gate states landed upstream of `confidence_check` — `check_design` (BUG-3249) and `check_reconcile_limit`/`reconcile_issue` (ENH-3248) — shifting everything after them by a constant +115–120 lines with no rename or removal. Current locations: `check_outcome` `:512-556` (was `:392`), its `on_yes: done` at `:554` (was `:434`), `check_decision_needed` `:558-569` (was `:438-449`), `confidence_check`'s `loop:`-call to `oracles/verify-confidence-scores.yaml` `:466-478` (was `:346-358`), `verify_issue`'s `verify_verdict` write `:317-325` and `check_verify_verdict`'s read `:327-337` (was `:279-287`/`:289-299`).
- **The routing gap is unchanged at current line numbers**: `check_outcome`'s `on_yes` (`:554`) still routes straight to `done` (`:723-724`) on a pure numeric `outcome_confidence >= outcome_threshold` compare — no re-read of the Proposed Solution against the codebase on that path. `check_decision_needed`/`check_missing_artifacts` (`:558-569`, `:591-600`) only fire on the *failing*-score branch, and even there they read pre-recorded frontmatter flags, not a fresh adversarial pass.
- **Two frontmatter flags `set_flags.py` already writes have no gate state reading them anywhere in `refine-to-ready-issue.yaml`**: `implementation_order_risk` and `spike_needed` (`FlagRule` phrase tables, `scripts/little_loops/cli/issues/set_flags.py:35-76`, written by `apply_flags_from_notes()` `:238-331`). Only `decision_needed` (`check_decision_mid_refine` `:215-226`, `check_decision_mid_wire` `:269-278`, `check_decision_needed` `:558-569`) and `missing_artifacts` (`check_missing_artifacts` `:591-600`) are consumed via `ll-issues check-flag`. This is the lowest-new-surface variant of Option (b): no new CLI, no new phrase rules, just two more `check-flag` gate states in the existing shape — though unlike `decision_needed` there is no existing `resolve-decision`-style sub-loop for either flag, so their failure-path handling would need to be authored new.
- **`oracles/resolve-decision.yaml` is the sub-loop `check_decision_needed`'s three call sites route through** (`resolve_decision_mid_refine` `:228-239`, `resolve_decision_mid_wire` `:280-290`, `resolve_decision_pre_breakdown` `:571-589`) — each is `loop: oracles/resolve-decision`, `with: {issue_id: ...}`, `on_success:` resuming the parent chain, `on_failure:`/`on_error:` both routing to a shared `record_decision_unresolved` state. A new adversarial state's own resolution path would need an analogous sub-loop or resolution state, not just the gate itself.
- **`/ll:go-no-go --check`'s exit-code contract is unused by any built-in loop** (`grep go-no-go scripts/little_loops/loops/` matches only a comment in `autodev.yaml:2001`) despite already matching the `evaluate: type: exit_code` shape `verify_issue`/`confidence_check` use (`skills/go-no-go/SKILL.md:41,444-461`). Its verdict is prose (`VERDICT: GO|NO-GO` / `NO-GO REASON: CLOSE|REFINE|SKIP`, `SKILL.md:309-310,337`), not a `VERDICT_JSON:` tagged trailer like `confidence-check`'s (`skills/confidence-check/rubric.md:428-433`, consumed by `_record_verdict()` in `scripts/little_loops/cli/action.py`) — Option (a) would need to add that trailer to fit the write-verdict/read-verdict shape the rest of the file uses.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` -- `ll-issues check-flag` entry (`:1908-1927`)
  already enumerates all four flags `set-flags` writes
  (`decision_needed`/`missing_artifacts`/`implementation_order_risk`/`spike_needed`)
  but doesn't say which gate states consume which flag; worth a one-line
  addition once the two new gate states exist [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` -- `TestRefineToReadyIssueSubLoop`
  class (`:1366`+) is where new tests for the two new gate states
  (`check_proposal_unsound`, the `spike_needed` gate) belong, one set
  each mirroring the five-assertion template already used for
  `check_decision_needed`/`check_missing_artifacts` (state-exists,
  `fragment == "shell_exit"`, action-contains-check-flag-and-field-name,
  `on_yes` routing, `on_no`/`on_error` routing -- see e.g.
  `test_check_missing_artifacts_state_exists` `:2422`,
  `test_check_missing_artifacts_uses_shell_exit_fragment` `:2429`,
  `test_check_decision_needed_on_yes_routes_to_resolve_decision_pre_breakdown`
  `:2459`). Also re-verify (not necessarily rewrite)
  `test_max_steps_at_least_40` (`:2555`, currently no upper-bound/exact-count
  assertion exists) and any routing test on the state the new gates get
  spliced adjacent to (e.g. `test_check_outcome_on_no_routes_to_...` if
  inserted near `check_outcome`) [Agent 1/3 finding]
- `scripts/tests/test_enh3238_verify_issues_causal_claims.py` -- exact
  precedent test shape to follow for the widened §B mandate: strips YAML
  frontmatter, flattens whitespace, then asserts the new rule text is present
  and sits after the `#### B. Verify Against Codebase` heading (see
  `test_rule_present`, `test_rule_sits_outside_graph_assisted_block`). A new
  test file for this issue's proposal-vs-code consequence check should follow
  the same pattern [Agent 3 finding]
- `scripts/little_loops/loops/autodev.yaml` /
  `scripts/tests/test_autodev_decision_gate.py` --
  `test_check_spike_needed_predicate_reads_both_flags` is the closest existing
  precedent if the new `spike_needed` gate needs the same one-shot guard
  (`spike_needed AND NOT spike_attempted`) rather than the simpler
  single-field `check_decision_needed`/`check_missing_artifacts` shape [Agent
  3 finding]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- **Confidence-check's "Outcome Risk Factors" is two layers, only one machine-readable.** Layer 1 (prose): `## Confidence Check Notes` → `### Outcome Risk Factors`, written by `skills/confidence-check/SKILL.md` Phase 4.5 (`:411-425`, template `skills/confidence-check/rubric.md:569-593`) whenever `HAS_FINDINGS` is true (i.e. `outcome_confidence < outcome_threshold`) — free-text bullets, no schema. Layer 2 (machine-readable, derived from layer 1): Phase 4.6 (`SKILL.md:445-459`) calls `ll-issues set-flags [ISSUE-ID]`, which re-scans that just-written prose against four `FlagRule` phrase tables (`_DECISION_NEEDED_PHRASES`, `_MISSING_ARTIFACTS_PHRASES`, `_IMPLEMENTATION_ORDER_RISK_PHRASES`, `_SPIKE_NEEDED_PHRASES`, `scripts/little_loops/cli/issues/set_flags.py:35-76`) and stamps booleans via `apply_flags_from_notes()` (`:238-331`). All four `FlagRule`s share `precondition = _outcome_risk_produced_factory(threshold)` (`:123-127,191`) — they only fire when outcome score is already sub-threshold, so a Proposed Solution that scores *above* threshold is never phrase-scanned regardless of what the prose would have said (consistent with layer 1 only writing findings in that case, not a separate gap). This substring-phrase-over-LLM-prose match is "machine-readable" only in the sense of a deterministic pass over LLM-authored text — it never re-executes an adversarial review against the code, which is precisely the gap this issue is about.
- **`cmd_check_flag()`** (`scripts/little_loops/cli/issues/check_flag.py:13-33`) — the reader every `check-flag`-based gate calls: `fm.get(field) == 'true'`, a simple frontmatter boolean check, no content inspection.
- **Error-handling convention any new gate would need to replicate**: `check_outcome` (`:512-556`) distinguishes an infra failure (`ll-issues show` nonzero exit / unparseable JSON, both `sys.exit(2)` per inline comment `:534-537` guarding against BUG-2726) from a genuine low score — `on_error: diagnose` (`:556`), never misrouted through `on_no`. `check_decision_needed`/`check_missing_artifacts` both fail open on error (`on_error` targets the same state as their `on_no` branch, `:569,:600`), the same fail-open convention used by `check_hedges`/`check_ac_automatable`/`check_design` elsewhere in this file.
- **Cycle-termination precedent**: the `check_outcome` → `check_decision_needed` → `resolve_decision_pre_breakdown` → `confidence_check` loop (header comment `:571-582`) terminates because the `resolve-decision` sub-loop's `done` terminal asserts `decision_needed: false` before returning, so the second pass through `check_decision_needed` falls through `on_no` and cannot spin. Any new prescriptive gate that re-enters `confidence_check` on resolution needs the same asserted-false-before-resume guarantee to avoid an infinite cycle.

### Types
- `verify_verdict: VALID|NON_VALID` — frontmatter field written by `verify_issue` (`refine-to-ready-issue.yaml:279-287`), read by `ll-issues check-verify-verdict`
- `decision_needed` / `missing_artifacts` / `implementation_order_risk` / `spike_needed` — frontmatter flags written by `apply_flags_from_notes()` (`scripts/little_loops/cli/issues/set_flags.py:238-331`), each read via `ll-issues check-flag <flag>` (`fragment: shell_exit`)
- Any new adversarial verdict this issue introduces must follow the same shape: a frontmatter-persisted enum/bool, not a value read directly off LLM output — this is required by the "write-verdict/read-verdict" convention documented in Integration Map above, not optional stylistic preference

### Signatures
- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/check_verify_verdict.py:41`, invoked as `ll-issues check-verify-verdict ${captured.issue_id.output}`
- `apply_flags_from_notes(config: BRConfig, issue_id: str, notes: str | None, dry_run: bool) -> FlagResult` — `scripts/little_loops/cli/issues/set_flags.py:238-331`, invoked via `ll-issues set-flags [ISSUE-ID]` from `skills/confidence-check/SKILL.md:429-437`

### Call Path
`apply_flags_from_notes` (`scripts/little_loops/cli/issues/set_flags.py:238`) -> `cmd_set_flags` (`:360`, invoked as `ll-issues set-flags`) writes `decision_needed` to frontmatter -> `cmd_check_verify_verdict` (`scripts/little_loops/cli/issues/check_verify_verdict.py:41`, invoked as `ll-issues check-verify-verdict`) is the sibling read-side pattern a new adversarial verdict's own read-gate would mirror. The FSM-level routing gap these resolve against (state names, not Python symbols, so not cited as anchors here) is documented with exact `refine-to-ready-issue.yaml` line numbers in Integration Map above: `check_outcome`'s `on_yes` reaches `done` without passing through `check_decision_needed`.

### Decision Rules

Verdict assignment inside the widened §B (B1/B2):

| Condition | Verdict |
|---|---|
| `## Proposed Solution` absent, `TBD`, or still template boilerplate | sub-check skipped entirely; verdict unchanged by it |
| Proposal, implemented as written, contradicts the code it names (exception-handler mismatch, invalidated test fixture, contradicted AC) | `PROPOSAL_UNSOUND` |
| ACs do not cover an integration point already listed in the issue's Integration Map | `PROPOSAL_UNSOUND` |
| Proposal is sound but a claim about *current* state is wrong | existing verdicts (`OUTDATED`/`INVALID`/`NEEDS_UPDATE`) — unchanged |
| Both a claim defect and a proposal defect | claim verdict wins (existing `NON_VALID` → `refine_followup` path repairs the research the proposal check depends on) |

Routing (B2), on `check_verify_verdict`'s `on_no` branch:

| `verify_verdict` | `check_proposal_unsound` | Next state |
|---|---|---|
| `PROPOSAL_UNSOUND` | exit 0 | `check_reconcile_limit` → `reconcile_issue` |
| any other non-VALID | exit 1 | `check_refine_limit` (today's behaviour) |
| probe error | — | `check_refine_limit` (fail-open, matching this file's convention) |

Gate predicate (B3): fire only when `spike_needed == 'true'` AND
`spike_attempted != 'true'` — the one-shot guard from `autodev.yaml:1315-1391`.

## Implementation Steps

1. **Capture the baseline (must precede any edit — see AC4).** Run `ll-loop run
   refine-to-ready-issue <ID>` on an untouched issue and record LLM-call count,
   wall time, and cost from the run's own artifacts. The `4 calls / 17m49s /
   ~$1.47` figures in this issue have no backing artifact (see Codebase Research
   Findings) and must not be used as the comparison point.
2. **B1 — widen `commands/verify-issues.md` §B** with a proposal-vs-code
   consequence sub-check, written as an explicitly separate labeled sub-check
   (not blended prose) from the claim-verification pass, covering the three
   defect classes in `## Current Behavior`: exception-handler compatibility,
   test-fixture invalidation, and AC coverage of the integration points already
   listed in the issue's Integration Map. Precondition it on a present,
   non-boilerplate `## Proposed Solution`.
3. **B2 — split the verdict.** Add `PROPOSAL_UNSOUND` to §C's verdict table,
   carve it out of §2.5's blanket non-VALID collapse (it persists as its own
   `verify_verdict` value but still exits 1 in `--check`), add
   `--proposal-unsound` to `ll-issues check-verify-verdict`, and splice
   `check_proposal_unsound` onto `check_verify_verdict`'s `on_no` so the remedy
   is `reconcile_issue`, not `refine_followup`.
4. **B3 — route `spike_needed`** with a new gate using `autodev.yaml:1315-1391`'s
   two-field one-shot predicate (`spike_needed AND NOT spike_attempted`, inline
   `show --json`, `fragment: shell_exit`), and decide its `on_yes` target against
   `scripts/little_loops/loops/spike-gate.yaml` / `autodev`'s `run_spike`.
5. **Regenerate the per-host mirrors** and update docs (see Wiring Phase below).
6. **Verification**: new tests per `## Tests`; `ll-loop validate
   refine-to-ready-issue` exits 0; `python -m pytest scripts/tests/` exits 0;
   re-run the step-1 loop on a comparable issue and report the measured delta
   for AC4, including the effect on a batch `/ll:verify-issues` run.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Regenerate the generated per-host mirrors of `commands/verify-issues.md`
  (`.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`,
  `.kimi-code/skills/ll-verify-issues/SKILL.md`) via `ll-adapt` after widening
  §B, so they don't silently keep describing the old claim-verification-only
  mandate
- Add new tests to `TestRefineToReadyIssueSubLoop` in
  `scripts/tests/test_builtin_loops.py` for both new gate states
  (`check_proposal_unsound`, the `spike_needed` gate), mirroring the
  five-assertion template used for `check_decision_needed`/
  `check_missing_artifacts` -- with the `spike_needed` gate's action-content
  assertion adjusted for the inline-python predicate rather than a literal
  `ll-issues check-flag` string
- Add a new test file (following `test_enh3238_verify_issues_causal_claims.py`'s
  frontmatter-strip / flatten / assert-rule-present-and-placed pattern) for
  the widened §B proposal-vs-code consequence check
- One-line addition to `docs/reference/CLI.md`'s `ll-issues check-flag` entry
  (`:1908-1927`) naming which gate states consume which flag -- and noting that
  `implementation_order_risk` remains written-but-unconsumed repo-wide (it is
  out of scope here; see Decision Rationale)
- Document the new `check-verify-verdict` query flag (to be added by B2; it does
  not exist yet) in `docs/reference/CLI.md` alongside the existing
  `check-verify-verdict` entry

## Impact

- **Priority**: P3 - A correctness gap in a quality gate, not a broken gate. The
  chain still catches the defect classes it was built for; this closes a class it
  never covered. Deferrable, but it compounds: every issue that clears the gate
  with an unsound proposal costs an implementation pass to discover.
- **Effort**: Medium - No new LLM states and no new prompt design (B1 is a
  section edit to an existing command), but the change spans four surfaces
  (command markdown, loop YAML, a CLI flag, three generated host mirrors) plus
  two new test suites and a before/after cost measurement.
- **Risk**: Medium - Two distinct risks. (1) B1 conflates retrospective and
  prospective judgment in one prompt, which may dilute either; mitigated by
  separately-labeled sub-checks and measurable via the existing claim-check
  verdict distribution. (2) B2 touches `check_verify_verdict`'s branch band,
  which every refine run traverses; mitigated by making the new gate purely
  additive on the existing `on_no` path and fail-open to today's target.
- **Breaking Change**: No - `verify_verdict` gains a value rather than changing
  meaning; `check-verify-verdict`'s existing exit-code contract, callers, and
  tests are unchanged; the new CLI surface is an added opt-in flag.

## Root Cause

The chain has no adversarial pass over the Proposed Solution. `/ll:go-no-go`
is the closest existing shape and is not invoked anywhere in this loop.
`confidence_check` scores a rubric rather than reasoning about implementation
consequences; a proposal can score well on every axis (specific, unambiguous,
small, testable) and still not survive contact with the code.

A related observation, cheaper to fix and possibly sufficient on its own:
`confidence_check` *did* record the Proposed Solution's unresolved either/or
under "Outcome Risk Factors", and the loop terminated `done` anyway. The gap
there is not detection but that a recorded risk factor routes nowhere.

## Open Questions

- Is a new adversarial state warranted, or is it enough to make
  `confidence_check`'s already-recorded "Outcome Risk Factors" routable? The
  latter is far cheaper and would have caught defect 3 (the either/or) though
  not 1 or 2.
  > ✅ **RESOLVED** (2026-08-19) — Neither alone. **Option B** is selected:
  > widen `verify-issues` (B1) rather than add a new adversarial state, split
  > the verdict so the new failure kind gets `reconcile_issue` as its remedy
  > (B2), and route `spike_needed` (B3) as a low-cost addition. Risk-factor
  > routing is insufficient on its own — the flags are only written when the
  > outcome score is *already* sub-threshold, so it cannot touch the
  > `check_outcome → done` path this issue is about.
  > `implementation_order_risk` is explicitly excluded (no remedy exists for
  > it anywhere in the repo). See Proposed Solution → Decision Rationale.
- Does this belong in `refine-to-ready-issue` at all, or in `verify-issues` as
  a widened mandate (claims *and* proposals)? `verify_issue` already loads the
  relevant code, so a widened prompt may cost little beyond tokens.
  > ✅ **RESOLVED** (2026-08-19) — Both, split by concern. The *mandate* widens
  > in `verify-issues` (B1), chosen on cost grounds: it reuses the call and the
  > code `verify_issue` already loads, versus a new FSM state and a new LLM
  > call. The *remedy routing* stays in `refine-to-ready-issue` (B2), because
  > `verify-issues` has no say in which repair state the loop enters.
  > See Proposed Solution → Decision Rationale.
- Model tier: all four states ran on sonnet in the observed run. Depth of
  adversarial reasoning is model-sensitive; measure before adding a state.
  > ✅ **RESOLVED** (2026-08-19) — Not a live question under the chosen
  > approach: Option B reuses `verify_issue`'s existing invocation, which
  > inherits whatever model tier its invoking skill already pins. There is no
  > new state to assign a tier to.

## Acceptance Criteria

- [x] Design decision recorded for the three Open Questions above before any
      implementation.
- [x] An issue whose Proposed Solution contradicts the code it names (e.g. the
      `TimeoutExpired` case above) does not reach `done` unflagged. Implemented:
      `commands/verify-issues.md` §B6 (proposal-vs-code consequence check) traces
      exception-handler compatibility, test-fixture invalidation, and AC coverage;
      a match assigns `PROPOSAL_UNSOUND`, which `check_verify_verdict`'s widened
      `on_no` no longer lets fall straight through to `done`-reachable states
      unflagged. Not empirically re-verified against a live LLM run on the
      original `TimeoutExpired` case (see note on the unmeasured AC below) — this
      is structural/prompt-level verification, not a live behavioral test.
- [x] That failure is remedied by `reconcile_issue`, not `refine_followup`:
      `verify_verdict: PROPOSAL_UNSOUND` routes through `check_proposal_unsound`
      to `check_reconcile_limit`, asserted by a test in
      `TestRefineToReadyIssueSubLoop` (`test_check_proposal_unsound_on_yes_routes_to_check_reconcile_limit`,
      `test_check_verify_verdict_on_no_routes_to_check_proposal_unsound`).
- [x] Acceptance criteria are checked for coverage of the integration points
      `wire_issue` identified. Implemented as the third named defect class in
      §B6 ("AC coverage of identified integration points").
- [x] The widened §B sub-check is a no-op on issues with an absent or
      boilerplate `## Proposed Solution` (batch `/ll:verify-issues` does not pay
      for it on non-prescriptive issues). Implemented as an explicit precondition
      in §B6's prompt text, asserted by
      `test_rule_has_skip_precondition` in
      `test_enh3250_verify_issues_proposal_vs_code.py`.
- [ ] **Not done.** Added cost is measured as a before/after delta on the *same*
      issue: a baseline `ll-loop run refine-to-ready-issue` captured before any
      edit and a comparable post-change run, both reported with LLM-call count,
      wall time, and cost from the runs' own artifacts. This requires two live
      `ll-loop run` invocations against a real issue (the original baseline
      alone was reported as ~18 minutes); running both live LLM-driving loop
      invocations was deliberately not done autonomously in this session —
      spending real API budget on an uncontrolled ~30-40 minute two-run
      measurement is exactly the kind of costly, hard-to-bound action this
      project's operating guidance says to confirm first rather than run
      unilaterally. **Follow-up required**: run
      `ll-loop run refine-to-ready-issue <untouched-issue-id>` on a comparable
      issue and report the LLM-call-count/wall-time/cost delta against this
      change to close this AC.
- [x] `ll-loop validate refine-to-ready-issue` exits 0.
- [x] `python -m pytest scripts/tests/` exits 0. (19924 passed, 46 skipped.)

## Notes

Discovered by hand-reviewing BUG-3243 after `ll-loop run refine-to-ready-issue
BUG-3243` reported `done`. Distinct from the missing `check-design` gate: that
one is a routing defect (the verdict existed and was ignored); this one is a
coverage gap (the verdict was never computed).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `fsm`, `issue-management`

## Status

**Open** | Created: 2026-08-17 | Priority: P3


## Confidence Check Notes

> ⚠️ **SUPERSEDED — do not gate on this block.** The scores and concerns below
> were written on 2026-08-17, before the design decisions landed on 2026-08-19.
> Every finding in it is now stale: `ll-issues check-design ENH-3250` exits **0**,
> a concrete Proposed Solution exists (Option B / B1–B3), all three Open
> Questions are resolved, and frontmatter records 90 readiness / 72 outcome. The
> `blocked_by: ENH-3248` override cleared on 2026-08-18 when ENH-3248 reached
> `done`; its "design these together" framing in Related Issues was revisited —
> ENH-3248's `reconcile_issue` rung is now a *dependency* of this issue's B2, not
> a parallel design. Re-run `/ll:confidence-check` to replace this block.

_Added by `/ll:confidence-check` on 2026-08-17 — superseded, retained for history_

**Readiness Score**: 50/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 9/100 → VERY LOW

### Concerns
- ~~Hard override: `ll-issues check-design ENH-3250` fails (Program Design gate
  not satisfied)~~ — stale as of 2026-08-19: the gate exits 0.
- ~~Hard override: `blocked_by: ENH-3248` is unresolved~~ — resolved 2026-08-18:
  ENH-3248 is now `done`.

### Gaps to Address
- ~~All three design decisions remain unresolved~~ — all three resolved
  2026-08-19; AC1 satisfied. The `/ll:spike` pass was declined as
  decision-ambiguity rather than mechanism-risk (see Scope Boundaries).
- ~~No concrete Proposed Solution exists to assess Architecture Compliance or
  Change Surface against.~~ — Option B (B1/B2/B3) is now specified with an
  Integration Map and Implementation Steps.

### Outcome Risk Factors
- ~~Approach is fundamentally undetermined (three unresolved design decisions)~~
  — resolved 2026-08-19.
- Named ENH-3248's design outcome as a compounding source of uncertainty; that
  dependency resolved 2026-08-18 when ENH-3248 reached `done`.

## Session Log
- `/ll:manage-issue` - 2026-08-19T14:13:09 - `105361e4-7a8e-4239-bc56-4d61420d21ae.jsonl`
- `/ll:ready-issue` - 2026-08-19T13:56:32 - `81b0242e-0d86-4141-b923-d945df205d55.jsonl`
- `/ll:confidence-check` - 2026-08-19T13:49:57 - `641db8d3-2f9b-4cc7-95b8-2e05825e9301.jsonl`
- `/ll:confidence-check` - 2026-08-19T04:01:30 - `8d3838d8-fc35-4284-8dd8-4eaeaef2f5fd.jsonl`
- `/ll:wire-issue` - 2026-08-19T03:55:08 - `7bf6aa72-5505-4742-b30d-0fcc3999794b.jsonl`
- `/ll:decide-issue` - 2026-08-19T03:48:45 - `c1531e01-3784-4d60-9605-401610930e6b.jsonl`
- `/ll:decide-issue` - 2026-08-19T03:40:48 - `c1531e01-3784-4d60-9605-401610930e6b.jsonl`
- `/ll:refine-issue` - 2026-08-19T03:39:47 - `c1531e01-3784-4d60-9605-401610930e6b.jsonl`
- `/ll:spike (declined — decision ambiguity, not a mechanism risk)` - 2026-08-17T21:38:52 - `71139c18-5abb-4bd8-97d3-e9c138f42ce3.jsonl`
- `/ll:refine-issue` - 2026-08-17T21:36:15 - `d6cdea96-295f-4261-adf4-630f2bde0344.jsonl`
- `/ll:confidence-check` - 2026-08-17T21:34:52 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:capture-issue` - 2026-08-17T20:04:12 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
