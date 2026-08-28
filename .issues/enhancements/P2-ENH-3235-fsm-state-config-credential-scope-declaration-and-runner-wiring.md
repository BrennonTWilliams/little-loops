---
id: ENH-3235
type: ENH
title: FSM StateConfig credential scope declaration and fsm/runners.py wiring
priority: P2
status: open
parent: ENH-3203
epic: EPIC-3212
blocked_by: [ENH-3233]
discovered_by: /ll:issue-size-review
discovered_date: '2026-08-17'
testable: true
decision_needed: false
relates_to:
- ENH-3184
---

# ENH-3235: FSM StateConfig credential scope declaration and fsm/runners.py wiring

## Summary

Add a per-state scope-declaration field to loop YAML (`StateConfig`), following the existing
`tools:` allowlist precedent, and wire it into `DefaultActionRunner`'s shell branch
(`fsm/runners.py:266`) — the primary FSM-loop consumer — so a declaring state is denied every
undeclared credential variable using the deny-capable `project_child_env()`/
`HostInvocation.env_allow` chokepoint landed in ENH-3233.

## Parent Issue

Decomposed from ENH-3203: Declare and enforce per-task credential scope via deny-by-default env
projection. This child covers the FSM `StateConfig`/loop-YAML declaration surface only; the
`ActionSpec` surface is ENH-3234. Both converge on the shared chokepoint from ENH-3233, which
this issue depends on.

**Why a separate surface from ActionSpec, not a shared one**: see ENH-3234's Parent Issue section
— the two `bash -c` call sites share no common per-task object today, and unifying them is
explicitly out of scope for ENH-3203.

## Current Behavior

`fsm/runners.py`'s `DefaultActionRunner` shell branch (`fsm/runners.py:266-275`) builds
`cmd = ["bash", "-c", action]` and calls `subprocess.Popen(cmd, ..., env=project_child_env())`
with **zero arguments** — no `HostInvocation`, no scope, full inherit.

The `tools:` per-state allowlist (`fsm-loop-schema.json:590-596`, `StateConfig.tools: list[str] |
None = None`, `schema.py:686`) is the closest existing per-state declaration precedent: it flows
into `build_streaming(tools=...)` at `fsm/executor.py:2284`, only for prompt-mode states. Runners
that honor it read the flag directly (`ClaudeCodeRunner.build_streaming`, `host_runner.py:358-359`;
`OmpRunner`, `host_runner.py:1246-1247`); runners that decline it warn-and-drop via
`CapabilityNotSupported` (`CodexRunner`, `host_runner.py:645-654`; same shape in
`QwenRunner:1624-1627`, `KimiRunner:1411-1415`).

## Expected Behavior

- Loop YAML gains a per-state scope-declaration field (schema: `fsm-loop-schema.json`;
  dataclass: `StateConfig`, `schema.py`), resolved against ENH-3233's capability registry.
- `fsm/runners.py`'s `DefaultActionRunner` shell branch resolves the declared scopes into an
  `env_allow` set and passes it via the explicit kwarg ENH-3233 provides for invocation-less
  call sites — `project_child_env(env_allow=...)` — so everything not declared is denied. No
  synthetic `HostInvocation` is constructed.
- States with no declaration keep today's coarse (full-inherit) behavior — opt-in per state,
  matching ENH-3233's `env_allow=None` no-op default.

## Proposed Solution

Follow the `tools:` per-state precedent structurally (array/optional field in the schema, mirror
in the dataclass), but note the wiring gap the parent issue's research already surfaced: the
`tools:` field's existing wiring only reaches prompt-mode states via `build_streaming()`
(`fsm/executor.py:2284`) — the shell branch (`fsm/runners.py:266-275`) reads none of
`tools`/`agent`/`model`/`automation_profile` today. This issue must wire the new scope field into
the shell branch directly (not by reusing the `tools:` flow), since AC7.1 is specifically about
`DefaultActionRunner`'s `bash -c` path, which the `tools:` precedent does not already reach.

### Call Path
`StateConfig` (scope declared) → `fsm/runners.py::DefaultActionRunner` shell branch resolves
scopes → `env_allow` set → `project_child_env(env_allow=...)` (ENH-3233's kwarg; no
`HostInvocation` at this call site) → `subprocess.*`

### Round-trip
A new per-state field needs a symmetric `StateConfig.to_dict()` line (`fsm/schema.py:721`)
alongside whatever `from_dict()` addition lands, mirroring the existing `tools=data.get("tools")`
precedent at `fsm/schema.py:911` — otherwise the field silently fails to round-trip through
anything that serializes a `StateConfig` back to dict (loop export, `ll-loop show`, YAML
round-trip tests).

## Acceptance Criteria

- **AC1 (StateConfig half).** A loop-YAML state can declare the capability set its `bash -c`
  action requires.
- **AC7.1.** `fsm/runners.py:266` (`DefaultActionRunner` shell branch) — the FSM-loop path, the
  primary consumer — is covered by the same projection as the host-CLI paths, with a test proving
  an undeclared credential variable is absent from the shell action's environment. Mandatory:
  covering only the `ActionSpec` path (ENH-3234) leaves FSM loops unscoped.
- **AC5 (this surface).** States without a declaration keep working with today's coarse behavior —
  no regression to any existing loop YAML in `loops/*.yaml`.

## Program Design

### Tests
- `scripts/tests/test_fsm_schema.py::TestAgentToolsStateConfig` (line 2502) — the direct
  precedent for testing a new `StateConfig` field: default→`None`, construct→accepts, `to_dict`
  include-when-set/omit-when-none, `from_dict` deserialize/default, round-trip. The new per-state
  scope field should follow this same six/seven-test shape.
- New shell-branch test proving AC7.1 (undeclared credential variable absent from
  `DefaultActionRunner`'s `bash -c` environment) — no existing test targets this branch directly
  per the parent issue's research; add one alongside `fsm/runners.py`'s existing test coverage.
- FSM-path `ActionRunner` test doubles whose `.run()` signature may need a new kwarg if the
  per-state scope declaration is threaded through `.run()` (mirroring how `tools=`/`agent=` reach
  `fsm/executor.py:2284`): `RssActionRunner` (`scripts/tests/test_host_guard.py:55`),
  `MockActionRunner` (`scripts/tests/test_fsm_persistence.py:766`,
  `scripts/tests/test_usage_journal.py:17`, `scripts/tests/test_fsm_executor.py:37`),
  `ShutdownAfterFirstActionRunner` / `_TamperingActionRunner` / `_ActionRunner`
  (`scripts/tests/test_fsm_executor.py`). Kept optional (matching the `tools=` precedent), these
  are unaffected — worth an explicit check pass either way.
- Verify `scripts/tests/test_enh3184_spawn_site_guard.py` still passes against the modified
  `project_child_env()` chokepoint (landed in ENH-3233, but this issue's wiring is a new consumer
  of it).

### Documentation
- `docs/guides/LOOPS_GUIDE.md:590` — the `tools:` per-state allowlist table is the natural
  insertion point for the new per-state scope-declaration row, following the
  `suppress_catalog:` staged-rollout wording precedent at line 633
  (`DECLARATIVE-ONLY (not yet implemented)`).
- `docs/reference/HOST_COMPATIBILITY.md` — the capability support matrix (~line 243) keyed on
  `agent_select`/`tool_allowlist`/etc., and the `CapabilityNotSupported` narrative section (~lines
  300, 325), are the established place a new scoping-capability row or decline-narrative would
  land, if any host runner declines scope enforcement for prompt-mode states that also use
  `tools:`.

## Scope Boundaries

Out of scope for this child:

- The `ActionSpec` declaration surface and `runner_spec.py::_run_cmd()` wiring — that's ENH-3234.
- The chokepoint's deny logic, capability registry, and baseline — that's ENH-3233, a hard
  dependency of this issue.
- Extending the new scope field to prompt-mode states via `build_streaming()` — AC7.1 only
  requires the `DefaultActionRunner` shell branch; extending scope enforcement to host-CLI
  prompt-mode invocations is not required by any AC in the parent issue (those paths already
  route through `HostInvocation`/`project_child_env()` via ENH-3233's chokepoint once a caller
  populates `env_allow`, but no AC mandates populating it from `tools:`-style state config for
  prompt-mode states in this decomposition).
- Retrofitting declarations onto this repo's own existing `loops/*.yaml` — AC5 keeps undeclared
  states working; migrating real loops to declare scopes is follow-on work per ENH-3203's Scope
  Boundaries.

## Impact

- **Priority**: P2 — matches parent.
- **Effort**: Medium — schema field, dataclass field with round-trip, and new wiring into a shell
  branch that today reads none of the state config's optional fields (no existing flow to
  piggyback on, unlike the `tools:` precedent for prompt-mode).
- **Risk**: Medium — `DefaultActionRunner`'s shell branch is the primary FSM-loop consumer; a
  baseline gap surfacing here (rather than in ENH-3233's own report-only testing) would break
  real loop runs. Mitigated by ENH-3233 landing and validating the baseline against this repo's
  own `loops/*.yaml` first.
- **Breaking Change**: No — declaration is opt-in per state.

## Status

**Open** | Created: 2026-08-17 | Priority: P2 | Blocked by: ENH-3233

## Session Log
- `/ll:issue-size-review` - 2026-08-17T16:32:35 - `bcf99734-092e-4d7b-9a71-2d6fb04c8246.jsonl`
