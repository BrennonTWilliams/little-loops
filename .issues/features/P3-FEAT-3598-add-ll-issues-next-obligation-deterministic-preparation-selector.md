---
id: FEAT-3598
type: FEAT
title: Add ll-issues next-obligation deterministic preparation selector
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:49Z'
blocks:
- ENH-3599
- ENH-3601
parent: EPIC-3565
relates_to:
- ENH-3577
- ENH-3602
---

# FEAT-3598: Add ll-issues next-obligation deterministic preparation selector

## Summary

Add `ll-issues next-obligation ID --format json`: one deterministic selector that reads the
issue once, runs the format/design/AC/decision/proof/score checks, and returns the first
unmet obligation. Adopt it inside `refine-to-ready-issue` first, replacing its inline
predicates. Step B of the ENH-3577 decomposition.

## Current Behavior

Readiness predicates are copied across states: `ll-issues show` appears 12× in
`refine-to-ready-issue.yaml` and 37× in `autodev.yaml`; inline Python predicates 7× and 32×.
Individual gates already exist as separate subcommands (`format-check`, `check-design`,
`check-acceptance-criteria`, `check-unresolved-decisions`, `check-gate`, `spike-verdict`,
`check-readiness`), each invoked and interpreted ad hoc.

## Expected Behavior

`ll-issues next-obligation ID --format json` emits
`{issue_id, obligation, reason, evidence}` where `obligation` is one of `FORMAT`, `DESIGN`,
`ACCEPTANCE_CRITERIA`, `DECISION`, `PROOF`, `SCORES`, `NONE` (checked in that order, first
unmet wins). Deterministic; no LLM calls.

## Use Case

A loop state (or a developer) needs to know what an issue still lacks before it is
implementation-ready. Today each state re-derives that with its own `ll-issues show` +
inline Python; with this command it runs `ll-issues next-obligation ENH-123 --format json`
and routes on `obligation`.

## Proposed Solution

- `select_next_obligation(config: BRConfig, issue_id: str) -> Obligation` composing the
  existing check functions (`check_format_gaps` in `little_loops.issue_parser`, and the
  functions behind `check-design`, `check-acceptance-criteria`,
  `check-unresolved-decisions`, `spike-verdict`, `check-readiness`) — reuse, don't
  reimplement.
- `cmd_next_obligation(config, args) -> int` subcommand wrapper; exit 0 always on a
  successful assessment, non-zero only on read errors.
- Replace the child's per-gate predicate states with a single dispatch on `obligation`
  where the mapping is 1:1; leave any state whose semantics differ, and note it.
- Keep distinct skills for research, wiring, decisions and reconciliation — the selector
  only chooses which runs next.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` (register subcommand)
- `scripts/little_loops/cli/issues/next_obligation.py` (new)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local mirror of the loop)
- `docs/reference/CLI.md`

### Tests
- Unit tests per obligation, plus ordering tests (two unmet → first wins)
- Behavioral set must pass unchanged: `test_spike_verdict_routing.py`,
  `test_format_probe_routing.py`, `test_arm_proposal_revision.py`,
  `test_ll_issues_check_verify_verdict.py`, `test_check_readiness.py`

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - new subcommand composing existing checks, plus child predicate replacement
- **Risk**: Medium - replaces predicate states in refine-to-ready-issue
- **Breaking Change**: No

## Program Design

### Types

- `Obligation: Enum` — `FORMAT`, `DESIGN`, `ACCEPTANCE_CRITERIA`, `DECISION`, `PROOF`, `SCORES`, `NONE`

### Signatures

- `select_next_obligation(config: BRConfig, issue_id: str) -> Obligation` — reads the issue once and returns the first unmet obligation
- `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` — CLI wrapper emitting `{issue_id, obligation, reason, evidence}`

### Call Path

`cmd_next_obligation` -> `select_next_obligation` -> `check_format_gaps`

## Scope Boundaries

- Deterministic only: no LLM calls, no file writes.
- Adoption in `autodev.yaml` is out of scope (ENH-3599 / ENH-3601).

## Acceptance Criteria

- [ ] `ll-issues next-obligation` returns the documented JSON for every obligation
- [ ] The selector calls existing check functions; no duplicated predicate logic
- [ ] `refine-to-ready-issue` uses the selector for at least the format/design/AC/decision gates
- [ ] Behavioral test set passes unchanged

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `PROOF` obligation delegates to `little_loops.learning_tests.assess_proof` once ENH-3602 lands, rather than deriving staleness/refutation independently. Sequence the PROOF branch after ENH-3602 or record a follow-up swap.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:20 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
