---
id: ENH-3096
type: ENH
title: Thread AutomationContext through ActionRunner.run() and fsm/executor.py
priority: P3
status: open
parent: ENH-3094
blocked_by:
- ENH-3095
discovered_date: 2026-08-07
discovered_by: /ll:issue-size-review
labels:
- automation
- fsm
- refactor
- tech-debt
testable: true
decision_needed: false
relates_to:
- FEAT-3078
- FEAT-3033
- ENH-2714
verify_verdict: VALID
---

# ENH-3096: Thread AutomationContext through ActionRunner.run() and fsm/executor.py

## Summary

Second of three children decomposed from ENH-3094. This child threads the
`AutomationContext` dataclass (introduced in ENH-3095) through the
`ActionRunner` Protocol boundary in `fsm/runners.py` — `DefaultActionRunner`,
`SimulationActionRunner` — and the `extra_kwargs` assembly in `fsm/executor.py` — and collapses the
largest cluster of hand-written test mocks that currently raise `TypeError`
on any new kwarg.

**Blocked by ENH-3095**: this child imports `AutomationContext` from
`host_runner.py`, which ENH-3095 defines. Can proceed in parallel with
ENH-3097 once ENH-3095 lands — they touch disjoint files except for a shared
edit to `fsm/executor.py` (different line ranges: this child touches the
`extra_kwargs` assembly at `:1886-1910`; ENH-3097 touches the baseline arm's
direct call at `:2771-2774`).

## Parent Issue

Decomposed from ENH-3094: Collapse the per-call automation kwargs into a
single AutomationContext dataclass. See that issue for full motivation,
sequencing decision, and Program Design section — this child implements the
`ActionRunner` slice of that design.

## Scope Boundaries

**In scope:** `ActionRunner.run()` Protocol and its `DefaultActionRunner` /
`SimulationActionRunner` implementations; the `extra_kwargs` assembly in
`fsm/executor.py:1886-1910`; the `SimulationActionRunner` `del` no-op
asymmetry noted below; the `docs/reference/API.md` ActionRunner mirror; the
associated test-mock signatures.

**Out of scope:** `HostRunner.build_streaming()` (ENH-3095, a dependency);
`run_claude_command()` and its callers, including `fsm/executor.py`'s
baseline-arm direct call at `:2771-2774` (ENH-3097).

## Proposed Solution

Replace `automation_profile` / `idle_timeout` keyword arguments with
`automation: AutomationContext | None = None` across the `ActionRunner`
Protocol and its two implementations. Collapse the `extra_kwargs` dict
assembly in `fsm/executor.py:1886-1910` into constructing one
`AutomationContext` and passing it as `automation=`. Keep the legacy kwargs as
deprecated pass-throughs per the parent's Decision Rules (explicit
`automation` context wins over legacy kwargs; deprecation warning logged).

### Codebase Research Findings (from parent)

- **`SimulationActionRunner` `del (...)` asymmetry** (`fsm/runners.py:404`):
  the `del` no-op list includes `idle_timeout` but omits `automation_profile`,
  leaving `automation_profile` an unreferenced declared parameter today.
  Collapsing both into one `automation` parameter fixes this asymmetry as a
  side effect.
- **`idle_timeout` never reaches `build_streaming()`**: it is consumed
  entirely in `subprocess_utils.py:478` and the shell/mcp selector loops in
  `fsm/runners.py:287,313` / `fsm/executor.py:2150,2169` — those selector-loop
  consumption sites are unaffected by this parameter-shape change.

### Files to Modify
- `scripts/little_loops/fsm/runners.py` — replace `automation_profile`/`idle_timeout`
  kwargs with `automation: AutomationContext | None` in `ActionRunner`
  Protocol (`:39-53`) and 2 implementations (`DefaultActionRunner:98-112`,
  `SimulationActionRunner:370-384`); fix the `del` no-op asymmetry noted above
- `scripts/little_loops/fsm/executor.py` — collapse `extra_kwargs` assembly
  (`:1886-1910`) into constructing one `AutomationContext`
- `docs/reference/API.md:5769-5785` — `ActionRunner` Protocol mirror

### Tests
- `scripts/tests/test_fsm_executor.py:35-118` — `MockActionRunner` (primary
  mock, explicit `run()` signature)
- `scripts/tests/test_fsm_executor.py:10946-10985` — `_ContinuityRunner`
  (inline fake, includes `automation_profile`, no `idle_timeout`)
- `scripts/tests/test_fsm_executor.py:11184-11228` — `_TamperingActionRunner`
  (inline fake, includes `automation_profile`)
- `scripts/tests/test_fsm_executor.py` — ~11 more inline fakes with explicit
  `run()` signatures and no `**kwargs`: `FailingRunner:2518`,
  `ShutdownAfterFirstActionRunner:3351`, `TimeoutCapturingRunner:5261`,
  `CapturingRunner:6373`, and others — safe only under the kwarg-gating
  contract (legacy kwargs stay omitted when unset)
- `scripts/tests/test_fsm_persistence.py:766-792` — `MockActionRunner` (stops
  at `model`; no `working_dir`/`automation_profile`/`idle_timeout` today)
- `scripts/tests/test_usage_journal.py:17-52` — `MockActionRunner` (stops at
  `model`; no automation kwargs today)
- `scripts/tests/test_fsm_runners.py:435-600` — patches `run_claude_command`,
  captures kwargs at `:485`
- `scripts/tests/test_feat3033_idle_timeout.py:390-467` — kwarg-gating
  compatibility template; imports `MockActionRunner` from `test_fsm_executor.py:28`;
  `test_idle_disabled_omits_kwarg_for_old_runners` proves the backward-compat
  contract for `automation=`
- `scripts/tests/test_bug3032_wall_clock_cap.py:24,39` — imports
  `MockActionRunner` from `test_fsm_executor`, drives it with `idle_timeout=60`;
  update in lockstep with the shared mock
- `scripts/tests/test_learning_state.py:46` — `_MockRunner.run()` explicit, no
  `**kwargs`; safe only if `automation=` stays kwarg-gated

## Acceptance Criteria

1. `ActionRunner.run()` Protocol, `DefaultActionRunner`, and
   `SimulationActionRunner` accept `automation: AutomationContext | None = None`
   in place of `automation_profile`/`idle_timeout`.
2. The `extra_kwargs` assembly in `fsm/executor.py:1886-1910` builds one
   `AutomationContext` instead of a per-knob dict.
3. `SimulationActionRunner`'s `del` no-op list includes both `automation` and
   any legacy kwargs it declares for Protocol conformance (fixes the
   pre-existing `automation_profile` omission).
4. The `automation_profile`/`idle_timeout` keywords still work, constructing
   an `AutomationContext` internally, per the ENH-3095 shim pattern.
5. `docs/reference/API.md` ActionRunner Protocol mirror updated.
6. `python -m pytest scripts/tests/` passes.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

### Types
- Imports `AutomationContext` from `host_runner.py` (defined by ENH-3095, not yet landed — this issue is `blocked_by: [ENH-3095]`).

### Signatures
Old — `ActionRunner.run()` Protocol, `DefaultActionRunner.run()`, `SimulationActionRunner.run()`:
`run(self, action: str, timeout: int, is_slash_command: bool, on_output_line: Callable[[str], None] | None = None, agent: str | None = None, tools: list[str] | None = None, on_usage: UsageCallback | None = None, on_usage_detailed: DetailedUsageCallback | None = None, model: str | None = None, working_dir: Path | None = None, automation_profile: str | None = None, idle_timeout: int = 0) -> ActionResult`

New:
`run(self, action: str, timeout: int, is_slash_command: bool, on_output_line: Callable[[str], None] | None = None, agent: str | None = None, tools: list[str] | None = None, on_usage: UsageCallback | None = None, on_usage_detailed: DetailedUsageCallback | None = None, model: str | None = None, working_dir: Path | None = None, automation: AutomationContext | None = None) -> ActionResult`

- Current — `ActionRunner.run()` Protocol (`fsm/runners.py:39-53`) and its two implementations `DefaultActionRunner.run()` (`:98-112`) and `SimulationActionRunner.run()` (`:370-384`) share identical trailing parameters `automation_profile: str | None = None, idle_timeout: int = 0`.
- New — replace that pair with `automation: AutomationContext | None = None`. Note the type widening this requires: `AutomationContext.idle_timeout` is `float | None` (ENH-3095's dataclass) versus the current `idle_timeout: int = 0` parameter — the shim's internal construction must map `0` (today's "disabled" default) to a value distinct from `None` (unset), not conflate the two.

### Call Path
- `fsm/executor.py:1883-1931` `extra_kwargs` assembly (today builds a kwarg-gated dict: `working_dir` if `self.working_dir is not None`; `automation_profile` if `action_mode == "prompt"` and a resolved, enabled pruning-profile config exists; `idle_timeout` if the resolved value is truthy) collapses into constructing one `AutomationContext(profile=..., idle_timeout=...)` and passing it as `automation=` — kept kwarg-gated (only added to `extra_kwargs` when non-default) so implementations without an `automation` parameter still work, per the existing pattern's own inline comments at `:1883-1885`, `1893-1895`, `1904-1907`.
- Inside `DefaultActionRunner.run()`: `automation_profile`/`idle_timeout` forwarded to `run_claude_command(...)` (`runners.py:191-192`) becomes forwarding `automation=automation`. `idle_timeout` is additionally read directly by this method's own shell-command selector loop (`runners.py:287,313`) — those reads become `automation.idle_timeout if automation else 0` (or equivalent), since `automation_profile` has no effect on that branch today and none is being added.
- Inside `SimulationActionRunner.run()`: extend the `del` no-op list at `:404` to include `automation` in place of the current `idle_timeout` entry — this both replaces and fixes the pre-existing asymmetry where `idle_timeout` is deleted but `automation_profile` (declared but never referenced) is not.

### Decision Rules
- Same shim pattern as ENH-3095: `automation_profile`/`idle_timeout` keywords stay as deprecated pass-throughs on `ActionRunner.run()` and both implementations; explicit `automation` wins when both are given; deprecation warning logged, per ENH-3095's shim.
- Kwarg-gating must be preserved end to end: `extra_kwargs` only sets `automation` when at least one of profile/idle_timeout resolves non-default, so the ~11 inline test-fake `ActionRunner`s enumerated in this issue's Tests section (explicit `run()` signatures, no `**kwargs`, no `automation` parameter) keep working unmodified when automation context isn't in use. This is the exact contract `test_feat3033_idle_timeout.py:390-467`'s `test_idle_disabled_omits_kwarg_for_old_runners` already proves for the pre-collapse shape — the collapsed version must keep it green.
- The `contributed`-action branch's separate, adjacent kwarg-gating in `fsm/executor.py:1860-1879` (its own `_contrib_extra` dict, `idle_timeout`-only, no `automation_profile` today) is out of this issue's stated scope (`ActionRunner.run()` and `:1886-1910` only) — do not fold it into this change.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md` | Parent issue — full motivation, Program Design, decision rationale |
| `.issues/enhancements/P3-ENH-3095-add-automationcontext-dataclass-and-thread-through-hostrunner-build-streaming.md` | Dependency — defines `AutomationContext` |
| `scripts/tests/test_feat3033_idle_timeout.py:390-467` | Kwarg-gating compatibility template |


## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:10 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:refine-issue` - 2026-08-07T22:51:22 - `596f76ed-c393-479b-9539-adbce5a6a72b.jsonl`
- `/ll:issue-size-review` - 2026-08-07T22:09:43 - `dec986a1-15de-4376-b5dd-5868a8d3e188.jsonl`
