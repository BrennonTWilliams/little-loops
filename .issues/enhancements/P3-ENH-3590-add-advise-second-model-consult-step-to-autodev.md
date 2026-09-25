---
id: ENH-3590
type: ENH
title: Add advise second-model consult step to autodev
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T03:36:09Z'
parent: EPIC-3565
---

# ENH-3590: Add advise second-model consult step to autodev

## Summary

Add an `/ll:advise` (second-model consult, `ll-advise`) step to `scripts/little_loops/loops/autodev.yaml` so autodev gets a review from a stronger/different model.

## Current Behavior

`autodev.yaml` never consults a stronger or different model. The only adversarial check is `run_go_no_go` (same-model `Agent` subagent debate, `oversized_atomic` deferrals only); `/ll:confidence-check` and `oracles/resolve-decision` run on the default model, and no state references `advise`, `ll-advise`, or a `model:` override.

## Expected Behavior

autodev can, when explicitly enabled, run a non-interactive `/ll:advise` consult at one or more decision points and route on a verdict persisted to frontmatter/JSON. When disabled (the default), behavior and cost are unchanged.

## Motivation

autodev currently has no review by a stronger or different model. Its only adversarial check is `run_go_no_go` (~line 2244, `/ll:go-no-go --auto`), a same-model (sonnet) `Agent` subagent debate that fires only for `oversized_atomic` deferrals; a GO verdict stamps `outcome_gate_waived: true`. `/ll:confidence-check` and `oracles/resolve-decision` also run on the default model, and neither `autodev.yaml` nor `oracles/resolve-decision.yaml` references `advise`, `ll-advise`, or a `model:` override.

## Proposed Solution

Add an advise state (alongside or after `run_go_no_go`, or before repair/defer decisions) that consults a stronger model via `/ll:advise --signal ... --question ...` non-interactively.

- Read the verdict back deterministically from frontmatter/JSON, never by parsing stdout (MR-1).
- Use the `with_rate_limit_handling` fragment (route `on_rate_limit_exhausted: finalize_rate_limited`).
- Resolve the host via `resolve_host()` / `host_runner`; add no new `"claude"` literals.
- Make it configurable and opt-out so it adds no cost by default.

## Scope Boundaries

- **In scope**: an opt-in advise state in `autodev.yaml` with a persisted, deterministically-read verdict; rate-limit handling via the existing fragment; a context flag to enable it.
- **Out of scope**: changing `/ll:advise` or `ll-advise` internals; replacing `run_go_no_go`; enabling the consult by default; consult steps in loops other than `autodev` (e.g. `oracles/resolve-decision`) unless the open questions resolve otherwise.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` - new advise state (near `run_go_no_go`, ~line 2236) plus an opt-in `context:` flag

### Dependent Files (Callers/Importers)
- `skills/advise/SKILL.md` - invoked by the new state via `/ll:advise`; the verdict-persistence contract must be confirmed here
- `scripts/little_loops/loops/lib/common.yaml` - provides the `with_rate_limit_handling` fragment

### Similar Patterns
- `run_go_no_go` in `autodev.yaml` - existing adversarial-review state and its `outcome_gate_waived` stamping
- States using `fragment: with_rate_limit_handling` with `on_rate_limit_exhausted: finalize_rate_limited` in `autodev.yaml`

### Tests
- `scripts/tests/test_autodev_loop.py` - state wiring, routing, default-off behavior
- `scripts/tests/test_fsm_validation_meta_rules.py` - MR rules (MR-1 no stdout parsing) still pass
- `scripts/tests/test_advise_skill.py`, `scripts/tests/test_cli_advise.py` - reference for advise invocation contract

### Documentation
- `docs/reference/CLI.md` - `ll-advise` reference (link only if the new flag is user-facing)

### Configuration
- New autodev `context:` flag, default off (name TBD in Open Questions resolution)

## Implementation Steps

1. Decide the decision point(s) and verdict semantics (see Open Questions); confirm how `/ll:advise` persists its verdict to frontmatter/JSON.
2. Add the opt-in context flag and the advise state to `autodev.yaml` using `with_rate_limit_handling` (`on_rate_limit_exhausted: finalize_rate_limited`), reading the verdict from persisted output, not stdout.
3. Route on the verdict; when the flag is off, skip the state so the existing flow is unchanged.
4. Add tests to `test_autodev_loop.py` covering default-off, enabled routing, and rate-limit exhaustion.
5. Verify with `ll-loop validate autodev` and `python -m pytest scripts/tests/test_autodev_loop.py scripts/tests/test_fsm_validation_meta_rules.py`.

## Impact

- **Priority**: P3 - quality improvement to autodev review, opt-in and not blocking
- **Effort**: Medium - one new state plus tests, but verdict persistence and decision points need design
- **Risk**: Low - disabled by default, so no change to existing runs
- **Breaking Change**: No

## Open Questions

- Which decision points warrant the consult (oversized_atomic deferral, repair/defer, decision resolution)?
- Can an advise verdict waive or override a go-no-go result?
- What cost/latency budget applies per issue and per run?

## Acceptance Criteria

- [ ] autodev has an advise state that invokes a second-model consult at the chosen decision point(s)
- [ ] Verdict is persisted to frontmatter/JSON and read back without stdout parsing
- [ ] Disabled by default; enabled via config/context flag
- [ ] `ll-loop validate autodev` passes

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-25T03:38:19 - `ad599d43-c063-4f11-b93f-27c8bb93bc23.jsonl`
- `/ll:capture-issue` - 2026-09-25T03:36:14 - `d36455b9-41a7-4bb9-9928-6288b5c7fed1.jsonl`
