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
(`fsm/runners.py:297`) — the primary FSM-loop consumer — so a declaring state is denied every
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

`fsm/runners.py`'s `DefaultActionRunner` shell branch (`fsm/runners.py:297-305`) builds
`cmd = ["bash", "-c", action]` and calls
`subprocess.Popen(cmd, ..., env=project_child_env(extra={"LL_PYTHON": sys.executable}))` — it
already passes an `extra` kwarg to inject `LL_PYTHON`, but no `env_allow`/deny-list argument;
no `HostInvocation`, no scope, full inherit otherwise.

The `tools:` per-state allowlist (`fsm-loop-schema.json:590-596`, `StateConfig.tools: list[str] |
None = None`, `schema.py:686`) is the closest existing per-state declaration precedent: it flows
into `build_streaming(tools=...)` at `fsm/executor.py:2284`, only for prompt-mode states. Runners
that honor it read the flag directly (`ClaudeCodeRunner.build_streaming`, `host_runner.py:358-359`;
`OmpRunner`, `host_runner.py:1246-1247`); runners that decline it warn-and-drop via
`CapabilityNotSupported` (`CodexRunner`, `host_runner.py:645-654`; same shape in
`QwenRunner:1624-1627`, `KimiRunner:1411-1415`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Confirmed hard blocker still in force: `project_child_env()` (`host_runner.py:1865-1895`) has
  only its ENH-3184 signature (`invocation`, `extra`) today; `HostInvocation`
  (`host_runner.py:156-173`) has exactly its original 5 fields. A repo-wide grep for `env_allow`
  returns zero hits under `scripts/` — ENH-3233 (`status: open`) does not yet provide the
  `env_allow` kwarg this issue's AC7.1 requires, so `blocked_by: [ENH-3233]` remains a currently
  true, mandatory block, not stale bookkeeping.
- Several line citations in this issue have drifted since the 2026-09-03 Verification Notes pass:
  `StateConfig.tools` is now at `fsm/schema.py:727` (not 686), its `to_dict()` guard is at
  `schema.py:830-831` (not 721), its `from_dict()` line is at `schema.py:952` (not 911),
  `TestAgentToolsStateConfig` is at `test_fsm_schema.py:2536` (not 2502), `MockActionRunner` in
  `test_fsm_persistence.py` is at line 825 (not 766), and in `test_fsm_executor.py` at line 41
  (not 37). `fsm-loop-schema.json`'s `tools:` block is at lines 582-598 (was cited 590-596).
- The `tools:` field's `build_streaming()` wiring is not reached by `DefaultActionRunner`'s shell
  branch under any condition: `fsm/executor.py:2495-2505` passes `tools=state.tools if
  action_mode == "prompt" else None` — the shell branch always receives `tools=None` regardless of
  `state.tools`'s value, confirming there is no existing partial reach into the shell branch to
  build on.

## Expected Behavior

- Loop YAML gains a per-state scope-declaration field (schema: `fsm-loop-schema.json`;
  dataclass: `StateConfig`, `schema.py`), resolved against ENH-3233's capability registry.
- `fsm/runners.py`'s `DefaultActionRunner` shell branch resolves the declared scopes into an
  `env_allow` set and passes it via the explicit kwarg ENH-3233 provides for invocation-less
  call sites — `project_child_env(extra={"LL_PYTHON": sys.executable}, env_allow=...)` — so
  everything not declared is denied, alongside the existing `LL_PYTHON` injection. No synthetic
  `HostInvocation` is constructed.
- States with no declaration keep today's coarse (full-inherit) behavior — opt-in per state,
  matching ENH-3233's `env_allow=None` no-op default.

## Proposed Solution

Follow the `tools:` per-state precedent structurally (array/optional field in the schema, mirror
in the dataclass), but note the wiring gap the parent issue's research already surfaced: the
`tools:` field's existing wiring only reaches prompt-mode states via `build_streaming()`
(`fsm/executor.py:2284`) — the shell branch (`fsm/runners.py:297-305`) reads none of
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
- **AC7.1.** `fsm/runners.py:297` (`DefaultActionRunner` shell branch) — the FSM-loop path, the
  primary consumer — is covered by the same projection as the host-CLI paths, with a test proving
  an undeclared credential variable is absent from the shell action's environment. Mandatory:
  covering only the `ActionSpec` path (ENH-3234) leaves FSM loops unscoped.
- **AC5 (this surface).** States without a declaration keep working with today's coarse behavior —
  no regression to any existing loop YAML in `loops/*.yaml`.

## Program Design

### Types
- `StateConfig.<new-field>: list[str] | None = None` — mirrors the existing
  `StateConfig.tools: list[str] | None = None` (`fsm/schema.py:727`, drifted from the field's
  earlier `schema.py:686` citation); field name is not fixed here, only the shape.

### Signatures
- `project_child_env(invocation: HostInvocation | None = None, *, extra: dict[str, str] | None = None) -> dict[str, str]`
  (`host_runner.py:1865-1895`) — **current, confirmed signature**. `env_allow` does not exist on it
  today: a repo-wide grep for `env_allow` returns zero hits under `scripts/` (all 4 hits are
  `.issues/*.md` prose for ENH-3203/3233/3234/3235). `HostInvocation` (`host_runner.py:156-173`)
  still has exactly its original 5 fields (`binary`, `args`, `env`, `capabilities`,
  `cleanup_paths`) — no `env_allow` field. ENH-3233 is `status: open` and has not yet added the
  kwarg; `blocked_by: [ENH-3233]` remains a mandatory, currently-true block.

- `ActionRunner.run(self, action: str, timeout: int, is_slash_command: bool, ..., tools: list[str] | None = None, ...) -> ActionResult`
  (Protocol, `fsm/runners.py:40-95`) — there is no generic/dynamic passthrough from `StateConfig`
  to this Protocol; every field requires its own explicit named parameter here. The new scope
  field needs one, and it must reach both implementers: `DefaultActionRunner.run()`
  (`fsm/runners.py:117-134`) and `SimulationActionRunner.run()` (`fsm/runners.py:428-445`, which
  discards every optional param it doesn't use via an explicit `del (...)` at line 469).
  Existing `ActionRunner` test doubles (`RssActionRunner`, `MockActionRunner` ×4,
  `ShutdownAfterFirstActionRunner`, `_TamperingActionRunner`, `_ActionRunner`) all end their
  parameter list with `**kwargs: Any`, so this addition is safe and additive for every one of
  them — none enumerate every current parameter without a trailing catch-all.

### Call Path
`StateConfig.<new-field>` (declared) → `fsm/executor.py:2495-2505` dispatch call site — **must
NOT** be gated to `action_mode == "prompt"` the way `tools`/`agent`/`model` are today, since the
new field's target is the shell branch, not the prompt-mode branch → new named parameter on
`ActionRunner.run()` → `DefaultActionRunner.run()`'s shell branch (`fsm/runners.py:297-305`,
confirmed exact current call: `subprocess.Popen(cmd, ..., env=project_child_env(extra={"LL_PYTHON":
sys.executable}))`, no other kwargs) → `project_child_env(extra=..., env_allow=...)` (the
`env_allow` kwarg does not exist yet — pending ENH-3233) → `subprocess.Popen`.

### Decision Rules
N/A — no new decision logic. This issue declares a scope list and resolves it against ENH-3233's
registry; the registry's fail-loud/allow/deny rules are ENH-3233's surface, not this one's.

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
  `MockActionRunner` (`scripts/tests/test_fsm_persistence.py:825`,
  `scripts/tests/test_usage_journal.py:17`, `scripts/tests/test_fsm_executor.py:41`),
  `ShutdownAfterFirstActionRunner` (`scripts/tests/test_fsm_executor.py:3880`) /
  `_TamperingActionRunner` (`scripts/tests/test_fsm_executor.py:11973`) / `_ActionRunner`
  (`scripts/tests/test_fsm_executor.py:12329`). Kept optional (matching the `tools=` precedent),
  these are unaffected — worth an explicit check pass either way.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Test shape confirmed: `TestAgentToolsStateConfig` (`test_fsm_schema.py:2536`) and
  `TestModelStateConfig` (`test_fsm_schema.py:2624`) both use the same seven-test convention per
  field (`defaults_to_none`, `accepts_<field>`, `to_dict_includes_<field>_when_set`,
  `to_dict_excludes_<field>_when_none`, `from_dict_with_<field>`,
  `from_dict_without_<field>_defaults_none`, `round_trip_<field>`) — either one class per field or
  one class covering a closely-related pair are both established precedent.
- All `ActionRunner` test doubles end their parameter list with `**kwargs: Any`
  (`RssActionRunner` — `test_host_guard.py:62`; `MockActionRunner` — `test_fsm_executor.py:56-73`,
  `test_fsm_persistence.py:833-845`, `test_usage_journal.py:25-37`,
  `test_cost_ceiling_enforcement.py:29`; `ShutdownAfterFirstActionRunner` —
  `test_fsm_executor.py:3880-3895`; `_TamperingActionRunner` — `test_fsm_executor.py:11973`;
  `_ActionRunner` — `test_fsm_executor.py:12329`) — a new optional kwarg on `ActionRunner.run()` is
  additive-safe against every one of them.

- `test_enh3184_spawn_site_guard.py`'s per-module spawn-count table already has entries for
  `little_loops/fsm/runners.py` (line 26) and `little_loops/runner_spec.py` (line 28) — this
  issue's wiring is a new consumer of an already-tracked spawn site, not a new entry.
- ENH-3234 (the sibling `ActionSpec` surface) already has its own dispatch/env test precedents to
  mirror the shape of: `test_runner_spec.py::test_cmd_dispatch_matches_legacy_shape` (line 190)
  and `test_cmd_dispatch_sets_ll_python_env` (line 196).
- No shared "declare capability, decline gracefully" helper exists for `CapabilityNotSupported`
  warn-and-drop: `CodexRunner`, `GeminiRunner`, `KimiRunner`, `QwenRunner` each independently
  inline their own `if <param>: warnings.warn(..., CapabilityNotSupported, stacklevel=2)` block in
  `build_streaming()`. Not directly relevant to this issue's shell-branch-only scope (Scope
  Boundaries already excludes prompt-mode extension), but confirms there is nothing to reuse if
  that scope ever expands.
- The nearest shape precedent for a fixed-name-set resolved against a registry is
  `MUTATING_TOOLS` (`mcp_server/policy.py:55-65`, a bare `frozenset[str]` with no per-entry
  metadata and no fail-loud-on-unknown-name behavior) — a shape precedent only; the actual
  registry is ENH-3233's surface. "Resolve name against fixed set, raise directly on miss" (not
  warn-and-drop) is the codebase's convention elsewhere: `adapters/core.py::resolve_emitter`
  (line 76-78) and `CodexRunner._sandbox_args` (`host_runner.py:612-619`).

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

## Blocks

- ENH-3204
- ENH-3205

## Status

**Open** | Created: 2026-08-17 | Priority: P2 | Blocked by: ENH-3233

## Verification Notes (2026-09-03)

- `fsm/runners.py` shell branch re-verified at lines 297-305 (was cited 266-275).
- Corrected the factual claim that the `project_child_env()` call passes "zero arguments" — it
  already passes `extra={"LL_PYTHON": sys.executable}`; only `env_allow` is missing.
- Added missing `## Blocks` backlink: ENH-3204 and ENH-3205 both declare
  `blocked_by: ENH-3235` but this issue had no `## Blocks` section.

## Verification Notes (2026-09-03, second pass)

- `_TamperingActionRunner`'s citation was wrong, not just drifted: the same `refine-issue` pass
  that corrected other lines introduced `test_fsm_executor.py:3981-3995` for it; the class is
  actually at line 11973 (confirmed by both `grep` and `ll-code defines`). Corrected in the Tests
  and Codebase Research Findings sections above.
- The `fsm-loop-schema.json` `tools:`-block "correction" to lines 582-598 was also backwards: the
  block is still at its originally-cited 590-596 (confirmed by `grep -n '"tools"'` and direct
  read) — 582-598 spans the unrelated `agent`/`tools`/`pruning_profile` neighborhood, not the
  `tools:` block itself. Left as-is above since the body text doesn't hard-cite the wrong range in
  a way that needs a line edit, but flagging here so a future pass doesn't re-introduce it.
- All other citations re-verified clean: `project_child_env()`/`HostInvocation` signatures
  (`host_runner.py:1865-1895`, `156-173`), `StateConfig.tools` (`schema.py:727`, `831`, `952`),
  `fsm/executor.py:2495-2505`'s prompt-mode gating, `ENH-3233` still `status: open`, decisions log
  present with no active required-rule conflict, `ll-verify-evidence` clean (0 findings).
- Verdict: **NEEDS_UPDATE** — the blocking dependency and technical claims all hold; only two
  stale/incorrect line citations needed correction.

## Session Log
- `/ll:verify-issues` - 2026-09-03T20:03:03 - `e7ab64a8-d990-4865-a8d8-f889f6c44694.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:17:32 - `35fa9aa4-b416-4202-92c2-dce942749180.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:issue-size-review` - 2026-08-17T16:32:35 - `bcf99734-092e-4d7b-9a71-2d6fb04c8246.jsonl`
