---
id: BUG-3574
type: BUG
title: PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
blocks:
- ENH-3577
blocked_by:
- BUG-3571
- BUG-3572
---

# BUG-3574: PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution

## Summary

In `refine-to-ready-issue.yaml`, `check_proposal_unsound` (ENH-3250) routes a
`verify_verdict: PROPOSAL_UNSOUND` to `check_reconcile_limit` → `/ll:reconcile-issue`. Its
comment describes the failure as the Proposed Solution itself contradicting the code. But
reconcile has a binding contract (`commands/reconcile-issue.md`, "Contract"). That contract
rewrites only
`## Implementation Steps`, `## Acceptance Criteria`, `## Integration Map` and, conditionally,
`## Scope Boundaries`. It does not rewrite `## Proposed Solution` or decision rationale.
Reconcile can fix drifted directives, but not a refuted chosen design.

## Current Behavior

A genuinely unsound proposal is sent to a remedy that cannot edit it. It burns the reconcile
budget and eventually defers.

## Expected Behavior

Directive drift goes to reconcile. A refuted selected proposal goes to a bounded design
revision (re-open the decision via `resolve-decision`), then wire and verify the revised
approach. An unsound proposal with no alternative stops with a distinct deferral reason.

## Steps to Reproduce

1. Take an issue whose Proposed Solution, implemented as written, contradicts the code it names
2. Run refine-to-ready-issue; verify-issues persists `verify_verdict: PROPOSAL_UNSOUND`
3. Observe the route to `/ll:reconcile-issue`, which leaves `## Proposed Solution` untouched per its contract; the verdict recurs until the reconcile budget is spent

## Motivation

Unsound proposals are exactly the cases where implementation would do the most damage. Routing them to a remedy that cannot touch the proposal guarantees a wasted budget and eventual deferral.

## Root Cause

- **One verdict, two remedies.** `commands/verify-issues.md` check B6 (ENH-3250) assigns
  `PROPOSAL_UNSOUND` for any consequence finding. Some B6 findings are fixable by editing
  directive sections alone — "AC coverage of identified integration points" (an AC gap) and
  often "test-fixture invalidation" (an Implementation Steps gap). Others refute the chosen
  mechanism itself (e.g. "exception-handler compatibility" when the selected design must
  raise through a handler it cannot pass). The verdict does not say which.
- **Reconcile anchors to the proposal.** `commands/reconcile-issue.md` § 3 reads "the
  selected option / decision under `### Decision Rationale`" and makes the directive
  sections describe **that** mechanism. Given a refuted proposal, reconcile re-derives
  directives from the refuted design.
- **The fallback cannot fix it either.** After one reconcile (`check_reconcile_limit`,
  `target: 2` → one attempt per run), the route falls to `check_gate_refine_limit` →
  `/ll:refine-issue`, which is additive and never rewrites `## Proposed Solution` (see the
  BUG-3002 comment on autodev's `refine_for_design`). Only `/ll:decide-issue` changes the
  selected option.
- **No re-open mode.** `/ll:decide-issue` needs 2+ enumerable options and picks among them;
  it has no way to exclude an option shown to be refuted, so on an already-decided issue it
  would either find nothing to decide or re-select the same option.
- **Return route skips verify.** `resolve_decision_pre_breakdown.on_success` →
  `confidence_check`, so a revised selection would be scored without re-running wire and
  verify.

## Proposed Solution

1. **Split the verdict in `/ll:verify-issues --check`** (not in the gate). The alternative —
   `check_proposal_unsound` inspecting which section the evidence cites — parses prose in a
   gate, breaking the convention that gates read a written frontmatter field. Classify by
   **which section must change to fix the finding**, not by B6 sub-check:
   - `DIRECTIVE_DRIFT` — the fix is confined to Implementation Steps / Acceptance Criteria /
     Integration Map; the selected mechanism stands. → reconcile (today's route).
   - `PROPOSAL_UNSOUND` — the selected option / Proposed Solution must change. → decision
     revision.
   - Precedence: `EVIDENCE_UNVERIFIED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` (a refuted
     proposal makes directive drift moot).
2. **Reuse BUG-3572's refuted → `decision_needed` contract** — no new FSM remedy states.
   On `PROPOSAL_UNSOUND`, verify-issues also arms `decision_needed: true` and adds an
   `## Open Questions` item naming the refuted option, the B6 evidence, and the remaining
   alternatives.
3. **Decide-issue exclusion.** `/ll:decide-issue` treats an option named as refuted in an
   Open Questions item as ineligible. With ≥1 remaining option it selects and rewrites
   `### Decision Rationale`; with none it exits `NO_ACTIONABLE_DECISIONS`.
4. **Routing in refine-to-ready:**
   - `check_proposal_unsound` `on_yes` → `check_decide_attempts` (existing bound) →
     `resolve_decision_pre_breakdown`; write a run-dir marker
     `refine-to-ready-proposal-revision` first.
   - After `resolve_decision_pre_breakdown.on_success`, a new `check_proposal_revision`
     state routes to `wire_issue` when the marker exists (→ `normalize_structure` →
     BUG-3571's `clear_verify_verdict` → `verify_issue`), else `confidence_check` as today.
     Other decision paths are unchanged.
   - No remaining alternative → defer with a new reason code `proposal_unsound` rather than
     `decision_unresolved`, so triage can tell "no decision recorded" from "the only
     proposal is refuted".
   - New `check-verify-verdict --directive-drift` query mode routes `DIRECTIVE_DRIFT` to
     `check_reconcile_limit`.
5. **Legacy values need no migration**: BUG-3571 clears `verify_verdict` before every verify,
   so a persisted `PROPOSAL_UNSOUND` from an earlier run is never read.

## Program Design

### Types

- `DIRECTIVE_DRIFT` — new `verify_verdict` value, written by `/ll:verify-issues --check`.

### Signatures

- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — existing; gains a `--directive-drift` query mode (exit 0 when `verify_verdict == DIRECTIVE_DRIFT`, 1 otherwise), mirroring `--proposal-unsound`. Default mode treats `DIRECTIVE_DRIFT` as non-VALID (exit 1).

### Call Path

`cmd_check_verify_verdict` -> `parse_frontmatter`

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — §B6 verdict split by fix location; §C verdict table adds `DIRECTIVE_DRIFT`; § 2.5 frontmatter mapping; on `PROPOSAL_UNSOUND`, arm `decision_needed` and write the Open Questions item
- `skills/decide-issue/SKILL.md` — exclude options named refuted; `NO_ACTIONABLE_DECISIONS` when none remain
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `--directive-drift` query mode; default mode non-VALID for it
- `scripts/little_loops/cli/issues/__init__.py` — parser flag and `_USAGE` / help text
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new `check_directive_drift` gate (→ `check_reconcile_limit`); `check_proposal_unsound.on_yes` → marker + `check_decide_attempts`; new `check_proposal_revision` after `resolve_decision_pre_breakdown.on_success`; `proposal_unsound` deferral; header comment chain (lines ~15-20) and ENH-3250 comment on `check_proposal_unsound`

### Dependent Files (Callers/Importers)
- `commands/reconcile-issue.md` — unchanged contract; receives only `DIRECTIVE_DRIFT` now
- `scripts/little_loops/loops/autodev.yaml` — no direct `verify_verdict` reads (it sees the verdict only through the refine-to-ready sub-loop); confirm `decision_needed` armed by verify is handled by its existing decision gates

### Similar Patterns
- BUG-3572 refuted spike → `decision_needed` + Open Questions item
- autodev `refine_for_design` (BUG-3002): a dedicated remedy chosen because the default remedy's contract excludes the failing section

### Tests
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — `--directive-drift` query mode; default mode exits 1 on `DIRECTIVE_DRIFT`
- `scripts/tests/test_builtin_loops.py` — `check_proposal_unsound` routing assertions (incl. `test_check_verify_verdict_on_no_reaches_check_proposal_unsound`, ~3083) and new states; stub `ll-issues` on `PATH` running the real state `action`
- decide-issue skill contract test for option exclusion
- verify-issues command contract test for the split and the `decision_needed` write

### Documentation
- `docs/reference/CLI.md` — `ll-issues check-verify-verdict` query modes
- `docs/guides/LOOPS_REFERENCE.md` — claim-verification gate chain
- `docs/reference/DEFERRAL_CODES.md` — `proposal_unsound`
- Host mirrors of `commands/verify-issues.md` and `skills/decide-issue/SKILL.md`: `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply` (gated by `test_host_artifacts_are_not_stale`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `scripts/little_loops/issue_lifecycle.py` — `DeferReason` enum (`DECISION_UNRESOLVED = "decision_unresolved"` at ~line 78) is the registry the `ll-issues set-status --reason` argparse `choices` validate against; a `proposal_unsound` deferral code must be a member or the CLI rejects it, and the shell state's `|| true` hides the rejection
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_autodev_reason_codes` (~line 341) — parametrized list of registered reason codes; guards exactly the silent-rejection failure above
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — pins that each verdict appears in `commands/verify-issues.md` §C and as `verify_verdict: X` in §2.5; `DIRECTIVE_DRIFT` must satisfy the same contract
- `scripts/tests/test_decide_issue_skill.py` — existing contract test for `skills/decide-issue/SKILL.md`; the option-exclusion contract belongs alongside it
- Conventions in force: (1) `check-verify-verdict` query modes are mutually exclusive binary probes — exit 0 only when `verify_verdict` equals that value case-insensitively, exit 1 for absent/other/VALID, `NOT_<VERDICT>` on stderr (evidence: `check_verify_verdict.py` `cmd_check_verify_verdict`, `--evidence-unverified` and `--proposal-unsound` branches; tests are one class per flag in `test_ll_issues_check_verify_verdict.py`); (2) gate states in `refine-to-ready-issue.yaml` are `fragment: shell_exit` with `on_yes`/`on_no`/`on_error`, `on_error` failing open to the `on_no` target, chain order encoding precedence (`check_verify_verdict` → `check_evidence_unverified` → `check_proposal_unsound`); (3) each new gate state bumps the `max_steps` value (currently 60, line ~104) and its comment; (4) loop routing tests assert state existence, `fragment`, action flag, and each edge separately in `test_builtin_loops.py` (~3029-3160, `max_steps` test ~3243); (5) run-dir markers live under `${context.run_dir}/`, initialized in the init state and tested with `[ -f ... ]`; (6) deferral emit pattern is `mark_decision_unresolved` — write `refine-terminal-class`, skip if status already done/cancelled, then `ll-issues set-status "$ID" deferred --by automation --reason <code> || true`; `refine-terminal-class` values today are `gate_unmet`, `infra`, `decision_unresolved`, so `proposal_unsound` needs one too

## Implementation Steps

1. verify-issues: split B6 verdict by fix location; add `DIRECTIVE_DRIFT`; on `PROPOSAL_UNSOUND` arm `decision_needed` + Open Questions item
2. `check_verify_verdict.py`: `--directive-drift` query mode; default mode non-VALID for it
3. decide-issue: exclude refuted options; `NO_ACTIONABLE_DECISIONS` when none remain
4. refine-to-ready: `check_directive_drift` → reconcile; `PROPOSAL_UNSOUND` → marker → `check_decide_attempts` → decide → `check_proposal_revision` → `wire_issue`; `proposal_unsound` deferral
5. Tests for each route; docs and mirrors

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low-Medium — changes the verify-issues verdict taxonomy and adds a decide-issue exclusion rule.
- **Sequencing**: `blocked_by` BUG-3571 (same `check_verify_verdict.py` and verify gate band; its verdict clearing removes the legacy-value question) and BUG-3572 (defines the refuted → `decision_needed` contract reused here).

## Acceptance Criteria

- [ ] A refuted Proposed Solution is never routed only to reconcile
- [ ] Directive-only drift still routes to reconcile
- [ ] A refuted proposal with a remaining alternative is re-decided, then re-wired and re-verified before scoring
- [ ] `/ll:decide-issue` never re-selects an option named as refuted
- [ ] A refuted proposal with no alternative defers as `proposal_unsound`, not via exhausted reconcile/refine budgets

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-25T01:44:08 - `b5d091e6-10b4-4f2f-9812-d49831a68b8b.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
