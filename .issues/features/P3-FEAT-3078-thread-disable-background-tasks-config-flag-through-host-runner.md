---
id: FEAT-3078
title: Thread a disable_background_tasks config flag through host_runner and all call sites
type: FEAT
priority: P3
status: open
testable: true
parent: FEAT-3060
depends_on:
- FEAT-3077
labels:
- automation
- headless
- host-runner
---

# FEAT-3078: Thread a disable_background_tasks config flag through host_runner and all call sites

## Summary

Implement the core mechanism from FEAT-3060: a new `disable_background_tasks`
config flag that, when enabled, causes `ClaudeCodeRunner.build_streaming()`
to inject `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` into the child environment
whenever `automation_profile` is set, mirroring the existing
`automation_profile`-threading pattern (Pattern A) used for
`LL_AUTOMATION`/`LL_AUTOMATION_PROFILE`.

## Parent Issue

Decomposed from FEAT-3060: Hard-disable background tasks in headless
automation instead of instructing against them. Resolves Acceptance Criteria
1, 2, 4, and 5.

## Dependency

Depends on FEAT-3077's decision on the carve-out policy — that decision sets
this config flag's default value (`true` if both known carve-outs are
retired, `false` if either is preserved).

## Decision Rationale (inherited from parent)

**Selected: Option A** — thread `disable_background_tasks` as a per-call
parameter through `build_streaming()`'s existing `automation_profile`-style
call chain, rather than a one-time `os.environ` mutation at config-load time
(Option B). Option B is disqualified on correctness grounds: a one-time
mutation ahead of `resolve_host()` persists for the rest of the process,
leaking the env var into later interactive/non-automation invocations sharing
that process — violating AC2's per-invocation absence requirement. Option A
reuses the already-proven, already-tested per-call gating pattern
(`automation_profile`, `host_runner.py:351-353`).

## Proposed Solution

Inject `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` alongside the existing
`LL_AUTOMATION` pair in `ClaudeCodeRunner.build_streaming()`'s env block,
gated on `disable_background_tasks and automation_profile is not None`, with
`disable_background_tasks` read from the new config flag threaded through
every caller down to `build_streaming()`.

### Files to Modify
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()` env block at lines 345-362; the new `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` conditional inserts here.
- `scripts/little_loops/config-schema.json` — `orchestration` object (line 1554) gains a new boolean property; the object is `additionalProperties: false`, so the schema entry is mandatory.
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig` dataclass (line 63) gains the matching field and `from_dict()` entry, alongside the existing `host_cli`.
- `scripts/little_loops/config/core.py:784-801` — `BRConfig`'s orchestration serializer block hand-lists fields (not a generic dataclass dump); the new field must be added explicitly or it silently disappears from serialized config output (e.g. `ll-config get`).
- `scripts/little_loops/host_runner.py:196,216` (`HostRunner` Protocol) and its 6 sibling `build_streaming()` signatures — `CodexRunner:590`, `OpenCodeRunner:799` (stub), `PiRunner:873` (stub), `GeminiRunner:984`, `OmpRunner:1181`, `KimiRunner:1369` — all need the new parameter for Protocol conformance, even where inert.

### Dependent Files (Callers/Importers) — threading `disable_background_tasks` through
- `scripts/little_loops/subprocess_utils.py:320` `run_claude_command()` — the chokepoint where `invocation.env` reaches `subprocess.Popen`.
- `scripts/little_loops/issue_manager.py:1213,1401` — hardcode `automation_profile="ll-auto"`; the new flag inherits the same hardcoding pattern at these two call sites.
- `scripts/little_loops/issue_manager.py:139-218` — a second, previously unlisted local `run_claude_command()` wrapper (aliased `_run_claude_base` in `subprocess_utils`); already threads `automation_profile` (line 151, forwarded at line 217) and needs the same threading for `disable_background_tasks`. Six further call sites forward through this wrapper: `:340` (inside `run_with_continuation`, itself a wrapper at `:268` needing the same param), `:520`, `:826`, `:893`, `:1089`, `:1401`.
- `scripts/little_loops/fsm/executor.py:1902` — sets `extra_kwargs["automation_profile"]` from `PruningProfileConfig`; a second, config-driven origin for `automation_profile` that needs the same wiring.
- `scripts/little_loops/fsm/runners.py:191` and `scripts/little_loops/runner_spec.py:145,176,182` — forward `automation_profile` straight into `resolve_host().build_streaming(...)`.
- `scripts/little_loops/host_runner.py:644,1036,1223,1418` — sibling `if automation_profile is not None:` env blocks in `CodexRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner`; survey and either add a no-op parity entry or document as deliberately excluded (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` has no meaning for non-Claude binaries). `OpenCodeRunner`/`PiRunner` are stub runners with no env-building logic.

### Conventions in Force
- Config sections are `@dataclass`es with a `from_dict(cls, data)` classmethod using `.get(key, default)` (lenient), mirrored by a `config-schema.json` object entry that is `additionalProperties: false` with a documented `default` — evidence: `scripts/little_loops/config/orchestration.py:63-103`, `scripts/little_loops/config-schema.json:1554-1631`.
- Pattern A (caller-threaded parameter, never read from config inside `host_runner.py`) is the only pattern that satisfies AC2's per-invocation absence requirement — evidence: `automation_profile` (`host_runner.py:351-353` and its four siblings).
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` would be this codebase's second host-scoped-only env var; the existing precedent (`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`, `host_runner.py:345-348`) is written directly into `ClaudeCodeRunner`'s dict literal with no shared cross-runner helper.

### Signatures
- `ClaudeCodeRunner.build_streaming(self, prompt: str, ..., automation_profile: str | None = None) -> HostInvocation` — existing, `host_runner.py:297`; env-building block at `:351` gains the new var, plus a new `disable_background_tasks: bool = False` parameter.
- `resolve_host() -> HostRunner` — existing, unchanged entry point.
- `run_claude_command(command: str, ..., automation_profile: str | None = None) -> subprocess.CompletedProcess[str]` — existing, `subprocess_utils.py:320`; gains the new parameter, forwards to the runner.

### Call Path
`process_issue_inplace` (`issue_manager.py:619`) -> `run_with_continuation` (`issue_manager.py:224`) -> `run_claude_command` (`subprocess_utils.py:320`) -> `resolve_host` -> `ClaudeCodeRunner.build_streaming` (`host_runner.py:297`), whose env block at `:351-353` already injects `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` and is the single insertion point. The FSM path reaches the same block via `fsm/runners.py:191`.

### Decision Rules
- Gate: inject `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` only when the new config flag is enabled AND `automation_profile is not None` on the same `build_streaming()` call — mirrors the existing `LL_AUTOMATION` gate (`host_runner.py:351`), so AC2 holds structurally rather than via a separate check.
- Escape hatch: the existing `automation_profile is None` path (interactive sessions) already bypasses the block entirely; the config default (from FEAT-3077's decision) is the only other override needed.

### Tests
- `scripts/tests/test_host_runner.py:962-966` — `test_automation_profile_env()`, the closest precedent for asserting a new conditional env key directly against `invocation.env` (no subprocess execution); extend for presence and — a first-of-kind assertion in this file — absence.
- `scripts/tests/test_subprocess_utils.py:2318-2368` (`TestRunClaudeCommandHostRunner.test_delegates_to_resolve_host`) — will break: asserts `mock_runner.build_streaming.assert_called_once_with(...)` with an exact kwarg set. Update to include the new kwarg.
- `scripts/tests/test_config.py:3406-3474` (`TestOrchestrationConfig`) — mirror the `request_path` default/override pair (`:3467-3473`) for the new boolean field's `from_dict()` default and explicit-`True` cases.
- `scripts/tests/test_config.py:3476-3510` (`TestBRConfigOrchestration`) — add a `.ll/ll-config.json` file-read-through test mirroring `test_orchestration_host_cli_from_file`.
- `scripts/tests/test_config_schema.py:787-823` — add a structural schema test mirroring `test_orchestration_host_cli_in_schema`.
- `scripts/tests/test_issue_manager.py:1390-1435` (`test_forwards_automation_profile_to_subprocess`/`test_automation_profile_defaults_to_none`) — template pair to copy for the `issue_manager.py:139-218` local wrapper's `disable_background_tasks` forwarding.

### Documentation
- `docs/reference/API.md` (~5769-5789 `ActionRunner` Protocol block, ~9173-9198 `HostRunner` Protocol block) — hand-maintained signature mirrors; both need the new parameter added, matching the pattern used when `idle_timeout` (FEAT-3033) was added.
- `docs/guides/LOOPS_GUIDE.md:604-636` — line 632 states "This env-signal path is the only part that is implemented," describing the `automation_profile` gate; needs updating now that a second unconditional env var shares the gate.
- `docs/ARCHITECTURE.md` (~line 777, `PruningProfileConfig` row) — needs a note or row for `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`.
- `docs/reference/CONFIGURATION.md:1199-1269` (`orchestration` table, `:1203-1206`) — needs a new row for the config flag, following the `host_cli`/`request_path` pattern.

## Acceptance Criteria

1. When `automation_profile` is set and the new config flag is enabled, the child
   environment carries `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.
2. When `automation_profile` is unset, the variable is absent — interactive
   sessions are unaffected.
3. All env-injection blocks in `host_runner.py` are surveyed and either updated
   for parity or documented as deliberately excluded.
4. A test asserts presence and absence of the variable across both branches.
5. The config flag's default value matches FEAT-3077's carve-out decision, and
   `docs/reference/CONFIGURATION.md`/`docs/ARCHITECTURE.md`/`docs/reference/API.md`/`docs/guides/LOOPS_GUIDE.md`
   are updated.

## Impact

Closes the last gap in a failure mode that silently discards completed work. The
2026-08-04 `ll-auto --only ENH-3046` run lost 21.6 minutes of correct,
fully-tested work this way, and BUG-3026 shows a 30% recurrence rate in one
sprint.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/claude-code/settings.md:772` | The only description of the flag's scope |
| `docs/reference/HOST_COMPATIBILITY.md` | Whether non-Claude hosts have an equivalent |


## Session Log
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
