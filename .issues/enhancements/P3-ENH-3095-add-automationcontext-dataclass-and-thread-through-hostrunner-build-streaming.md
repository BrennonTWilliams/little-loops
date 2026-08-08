---
id: ENH-3095
type: ENH
title: Add AutomationContext dataclass and thread it through HostRunner.build_streaming()
priority: P3
status: open
parent: ENH-3094
discovered_date: 2026-08-07
discovered_by: /ll:issue-size-review
labels:
- automation
- host-runner
- refactor
- tech-debt
testable: true
decision_needed: false
relates_to:
- FEAT-3078
- FEAT-3033
- ENH-2714
---

# ENH-3095: Add AutomationContext dataclass and thread it through HostRunner.build_streaming()

## Summary

First of three children decomposed from ENH-3094 (collapse per-call automation
kwargs into a single `AutomationContext`). This child introduces the
`AutomationContext` dataclass itself and threads it through the
`HostRunner.build_streaming()` boundary — the 7 concrete runners
(`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`,
`GeminiRunner`, `OmpRunner`, `KimiRunner`) plus the `HostRunner` Protocol and
`_apply_automation_env()`.

This child must land before ENH-3096 (ActionRunner boundary) and ENH-3097
(run_claude_command / caller boundary) — both need to import the
`AutomationContext` type this child defines.

## Parent Issue

Decomposed from ENH-3094: Collapse the per-call automation kwargs into a
single AutomationContext dataclass. See that issue for the full motivation,
sequencing-after-FEAT-3078 decision, and Program Design section (types,
signatures, decision rules) — this child implements the `HostRunner` slice of
that design.

## Scope Boundaries

**In scope:** the `AutomationContext` dataclass; `HostRunner.build_streaming()`
Protocol and all 7 concrete implementations; `_apply_automation_env()`; the
deprecated `automation_profile` pass-through at this boundary; doc mirrors
that describe `build_streaming()`'s signature.

**Out of scope:** `ActionRunner.run()` (ENH-3096), `run_claude_command()` and
its callers (ENH-3097), and anything ENH-3094 itself scoped out (the three
knobs' actual behavior, `HostRunner`'s non-automation parameters,
`_apply_automation_env()`'s env semantics).

## Proposed Solution

```python
@dataclass(frozen=True)
class AutomationContext:
    profile: str | None = None
    idle_timeout: float | None = None
    disable_background_tasks: bool = False
```

Replace the `automation_profile: str | None = None` parameter with
`automation: AutomationContext | None = None` across the `HostRunner` Protocol
and its 7 implementations, keeping `automation_profile` as a deprecated
keyword that constructs an `AutomationContext` internally. When both
`automation` and the legacy kwarg are supplied, the explicit context wins and
a deprecation warning is logged (no existing `DeprecationWarning` shim exists
in this codebase — see parent's Codebase Research Findings; the
`config.core` precedent referenced in `host_runner.py:114-115` is stale).

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `AutomationContext` dataclass
  alongside `HostInvocation`; replace `automation_profile` with
  `automation: AutomationContext | None` in `HostRunner` Protocol (`:216-248`)
  and the 7 concrete `build_streaming()` signatures; update
  `_apply_automation_env()` (`:1547`); register `AutomationContext` in
  `host_runner.py.__all__` (`:44-67`)
- `scripts/little_loops/__init__.py` — export `AutomationContext` (`:71-90`)
  alongside `HostInvocation`
- `scripts/little_loops/fsm/schema.py:449-450` — `PruningProfileConfig`
  docstring mirrors `build_streaming(..., automation_profile=...)`; update to
  cite `automation=`
- `docs/reference/API.md:9173-9188` — `HostRunner` Protocol mirror
- `docs/ARCHITECTURE.md:777` — `PruningProfileConfig` row citing
  `build_streaming(..., automation_profile=...)`
- `docs/guides/LOOPS_GUIDE.md:632` — advisory light-touch update; describes
  `automation_profile=None` env-signal clearing (ENH-3081), behavior
  unchanged but references the legacy kwarg name

### Tests
- `scripts/tests/test_host_runner.py:61-82` — `TestAutomationProfileEnvAcrossRunners`,
  table-driven across 5 real runners; re-point at `automation=`
- `scripts/tests/test_host_runner.py:996-1000` — `TestKimiRunner::test_automation_profile_env`;
  re-point at `automation=`
- `scripts/tests/test_host_runner.py` — new `TestAutomationContext` frozen-dataclass
  test (mirror `TestHostInvocation:1160-1183`) and a deprecated-shim test
  (context-wins + `DeprecationWarning`, `pytest.warns` pattern at `:1186-1199`)
- `scripts/tests/test_subprocess_utils.py:2321-2368` — `test_delegates_to_resolve_host`
  asserts the exact `build_streaming` kwarg set; update for `automation=`
- `scripts/tests/conftest.py:725-742` — `_CMD_RUN_ENV_VARS` scrub list; confirm
  no new env var is introduced by this child (env semantics are unchanged,
  only the parameter shape)
- `scripts/tests/test_runner_spec.py:33-38`, `scripts/tests/test_action.py:25-50`,
  `scripts/tests/test_cli_harness.py:29-38` — `FakeRunner.build_streaming(**_: object)`;
  verify these stay resilient with no signature change needed

## Acceptance Criteria

1. `AutomationContext` exists as a frozen dataclass (`profile`, `idle_timeout`,
   `disable_background_tasks`) in `scripts/little_loops/host_runner.py` and is
   exported from `host_runner.__all__` and `scripts/little_loops/__init__.py`.
2. `HostRunner.build_streaming()` Protocol and all 7 concrete runners accept
   `automation: AutomationContext | None = None` in place of
   `automation_profile`.
3. The `automation_profile` keyword still works, constructing an
   `AutomationContext` internally; when both are supplied the explicit
   `automation` context wins and a deprecation warning is emitted.
4. `_apply_automation_env()` reads `AutomationContext` fields.
5. `docs/reference/API.md` HostRunner Protocol mirror, `docs/ARCHITECTURE.md:777`,
   and `docs/guides/LOOPS_GUIDE.md:632` updated.
6. `python -m pytest scripts/tests/` passes.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

### Additional Research Findings
- `scripts/little_loops/config/automation.py` already defines an unrelated `AutomationConfig` (and `ParallelAutomationConfig`) dataclass family for project-level automation settings. The new `AutomationContext` in `host_runner.py` is a distinct, per-call runtime value with no relation to those — worth a docstring note on `AutomationContext` to prevent readers conflating the two similarly-named types.
- `scripts/tests/conformance/test_host_conformance.py` exercises `resolve_host()` + `build_streaming()` producing a valid `HostInvocation` across runners — check this still passes under the new `automation=` parameter shape even though it isn't in the issue's enumerated Tests list.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

### Types
`AutomationContext(profile: str | None = None, idle_timeout: float | None = None, disable_background_tasks: bool = False)`
- `AutomationContext` (frozen dataclass, `host_runner.py`, alongside `HostInvocation`): `profile: str | None = None`, `idle_timeout: float | None = None`, `disable_background_tasks: bool = False`

### Signatures
Old — `HostRunner.build_streaming()` Protocol and all 7 concrete runners:
`build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, automation_profile: str | None = None, workspace_root: Path | None = None) -> HostInvocation`

New:
`build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, automation: AutomationContext | None = None, workspace_root: Path | None = None) -> HostInvocation`

`_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None`

- Current — `HostRunner.build_streaming()` Protocol (`host_runner.py:216-227`) and all 7 concrete runners share an identical trailing parameter, `automation_profile: str | None = None`, at: `ClaudeCodeRunner:299-310`, `CodexRunner:590-602` (this one also inserts its own `sandbox_mode: str | None = None` between `tools` and `model` — unaffected by this change), `OpenCodeRunner:797-808`, `PiRunner:871-882`, `GeminiRunner:982-993`, `OmpRunner:1177-1188`, `KimiRunner:1363-1374`.
- New — replace `automation_profile: str | None = None` with `automation: AutomationContext | None = None` in the Protocol and all 7 implementations.
- `_apply_automation_env(env: dict[str, str], automation_profile: str | None) -> None` (`host_runner.py:1547-1564`) becomes `_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None`, reading `automation.profile` in place of the bare string — `automation is None` and `automation.profile is None` both take the existing "write `""`, not absent" opt-out branch.

### Call Path
`subprocess_utils.run_claude_command()` (`:402-409`) -> `runner.build_streaming(..., automation=...)` -> the 5 real runners each call `_apply_automation_env(env, automation)` (`:353` Claude, `:644` Codex, `:1034` Gemini, `:1219` Omp, `:1412` Kimi) -> sets `env["LL_AUTOMATION"]`/`env["LL_AUTOMATION_PROFILE"]` from `automation.profile`. `OpenCodeRunner`/`PiRunner` never reach `_apply_automation_env()` — both raise `HostNotConfigured` before touching any parameter, so their signature change is compile-only.

### Decision Rules
- Deprecated-kwarg shim: `automation_profile: str | None = None` stays as a parameter on the Protocol and all 7 implementations. If `automation` is `None` and `automation_profile` is not `None`, construct `AutomationContext(profile=automation_profile)` internally. If both are supplied, the explicit `automation` context wins and a `DeprecationWarning` is emitted via `warnings.warn(..., DeprecationWarning, stacklevel=2)`. No existing `DeprecationWarning` shim exists anywhere in `scripts/little_loops/` to copy — confirmed by direct search; `host_runner.py:114-115`'s docstring reference to a `config.core` precedent is stale (zero `warnings.warn`/`DeprecationWarning` occurrences in `config/core.py`). Do not reuse `CapabilityNotSupported(UserWarning)` (`host_runner.py:108-116`) for this — that class is reserved for host-capability mismatches (unsupported `agent`/`tools`/`workspace_root`), a semantically distinct case the parent's findings explicitly flag as not to be confused with this shim.
- `automation_profile=None` / `automation=None` remains an active opt-out (writes `LL_AUTOMATION=""`, not an absent key) — this ENH-3081 semantic is unchanged; only the parameter shape changes.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md` | Parent issue — full motivation, Program Design, decision rationale |
| `scripts/little_loops/host_runner.py:1547-1564` | `_apply_automation_env()`, the existing env-side consolidation |
| `scripts/tests/test_feat3033_idle_timeout.py:390-467` | Kwarg-gating compatibility template |


## Session Log
- `/ll:refine-issue` - 2026-08-07T22:51:21 - `596f76ed-c393-479b-9539-adbce5a6a72b.jsonl`
- `/ll:issue-size-review` - 2026-08-07T22:09:43 - `dec986a1-15de-4376-b5dd-5868a8d3e188.jsonl`
