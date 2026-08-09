---
id: FEAT-3078
title: Thread a disable_background_tasks config flag through host_runner and all call
  sites
type: FEAT
priority: P3
status: done
testable: true
completed_at: '2026-08-09T05:35:08Z'
parent: FEAT-3060
depends_on:
- FEAT-3077
labels:
- automation
- headless
- host-runner
relates_to:
- BUG-3093
- ENH-3094
- ENH-3081
verify_verdict: VALID
confidence_score: 99
outcome_confidence: 80
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 20
decision_needed: false
---

# FEAT-3078: Thread a disable_background_tasks config flag through host_runner and all call sites

## Summary

Implement the core mechanism from FEAT-3060: a new `disable_background_tasks`
config flag that, when enabled, causes `ClaudeCodeRunner.build_streaming()`
to inject `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` into the child environment
whenever `automation_profile` is set, mirroring the existing
`automation_profile`-threading pattern (Pattern A) used for
`LL_AUTOMATION`/`LL_AUTOMATION_PROFILE`.

## Current Behavior

`ClaudeCodeRunner.build_streaming()` (`host_runner.py:299`) has no mechanism to
disable Claude Code's background-task capability. Automation sessions
(`ll-auto`, FSM loops) that spawn a `claude` child can have that child launch
tool-level background work (e.g. `Bash run_in_background: true`), which can
silently discard completed work if the parent session ends before the
background task's result is retrieved — see `## Impact` below for a concrete
recurrence.

## Expected Behavior

A new `orchestration.disable_background_tasks` config flag (defaulting to
`true` per FEAT-3077's resolved carve-out decision) threads through
`build_streaming()` and all its callers. When enabled and `automation_profile`
is set, the child environment carries `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`;
when `automation_profile` is unset, the variable is explicitly neutralized
rather than merely omitted. See `## Acceptance Criteria` for the full
contract.

## Use Case

As an automation pipeline (`ll-auto`, FSM loops) operator, I want spawned
Claude Code children to have background-task capability hard-disabled by
default so that completed work is never silently discarded because a
background task's result was never retrieved before the parent session ended.

## Parent Issue

Decomposed from FEAT-3060: Hard-disable background tasks in headless
automation instead of instructing against them. Resolves Acceptance Criteria
1, 2, 4, and 5.

## Dependency

FEAT-3077's carve-out decision is **recorded and resolved** (its
`### Decision Rationale`, Option C). The value this issue consumes:

> **`orchestration.disable_background_tasks` defaults to `true`.**

Rationale in one line: the `manage-issue` smoke-test carve-out is retired at
the tool level and restated in shell terms — shell-level `&` backgrounding is
outside the flag's reach, empirically verified in
`postmortems/feat-3077-verify/` — so defaulting on costs no capability; and
the `go-no-go` carve-out is not reachable under the `automation_profile` gate
today and degrades to sequential-but-correct if it ever is.

Consequences for this issue, beyond the default value itself:

- The JSON-Schema `description` needs **default-on** phrasing (state what
  changes when enabled, and that `false` restores today's behavior) — not the
  `epic_worktree.enabled` / `rubric_gated_compaction.enabled` "when false
  (default), behavior is preserved unchanged" template, which assumes
  default-off.
- This is a **behavior change on upgrade** for any consuming project with
  `project.run_cmd` configured, since their smoke-test step loses tool-level
  backgrounding. AC6 covers the release note. (Note: this repo's own
  `run_cmd` is `null`, so the local test suite will not surface it.)
- FEAT-3077 must land first, or `manage-issue`'s skill prose will still
  instruct agents toward a capability the default now removes.

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
`LL_AUTOMATION` pair, gated on `disable_background_tasks and
automation_profile is not None`, with `disable_background_tasks` read from the
new config flag threaded through every caller down to `build_streaming()`.

### ⚠️ Superseding correction — ENH-3081 (`bab8c1fc`, 2026-08-07) landed after this issue was refined

Two structural premises below are **stale** and must be re-read before
implementing. Sections not corrected here (config schema, dataclass, docs,
test templates) are unaffected.

**(a) The five env blocks are now one helper.** This issue's *Files to Modify*
and *Dependent Files* describe five hand-written sibling
`if automation_profile is not None:` blocks at `host_runner.py:644,1036,1223,1418`,
and *Conventions in Force* asserts there is "no shared cross-runner helper."
Both are obsolete. ENH-3081 extracted `_apply_automation_env(env, automation_profile)`
(`host_runner.py:1547-1564`), called identically from all five real runners at
`:353, 644, 1034, 1219, 1412`.

Consequences:

- **AC3's survey shrinks to one function** — but this *inverts the default*.
  Adding the var inside the helper injects it for Codex/Gemini/Omp/Kimi too,
  contradicting AC6's "Claude-Code-only and inert for the other five runners."
- `scripts/tests/test_host_runner.py:62-82` (ENH-3081's own presence/absence
  test for the clear branch) is a closer template for AC4 than the
  `:962-966` `test_automation_profile_env()` this issue currently cites, and
  is the natural place to extend.

### Design Decision (AC3) — where does the new var get added?

**RESOLVED (`/ll:decide-issue`, 2026-08-08) — see Decision Rationale below.**
The helper extraction above inverted AC3's default: injecting inside
`_apply_automation_env()` unconditionally would have leaked the var to the
four non-Claude runners it currently doesn't touch.

**Option A**: Add the var directly in `ClaudeCodeRunner.build_streaming()`,
adjacent to the `_apply_automation_env()` call, keeping the helper
host-agnostic. Matches the existing precedent for host-scoped vars —
`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` is written directly into
`ClaudeCodeRunner`'s dict literal (`host_runner.py:347-350`) and was
deliberately left out of the ENH-3081 extraction.

> **Selected:** Option A — a one-line addition to the existing
> `ClaudeCodeRunner` dict literal, mirroring the already-precedented
> `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` pattern, with zero blast radius
> on the other four runners.

**Option B**: Extend `_apply_automation_env()` (`host_runner.py:1547`) with a
host guard (e.g. a `runner_kind` parameter) so the helper stays the single
env-construction site named by AC3, but conditionally skips the new var for
non-Claude runners.

### Decision Rationale (AC3 design decision)

**Selected: Option A** — add `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` directly
in `ClaudeCodeRunner.build_streaming()`'s env dict literal, leaving
`_apply_automation_env()` untouched.

Scoring (0–3 per dimension, evidence gathered by parallel codebase-pattern
agents against `host_runner.py`):

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A (direct in `ClaudeCodeRunner`) | 3 | 3 | 3 | 3 | **12/12** |
| B (host-guarded helper) | 2 | 2 | 2 | 1 | 7/12 |

- **Option A** matches an exact, already-shipped precedent:
  `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` (`host_runner.py:348`) is
  written directly into `ClaudeCodeRunner`'s dict literal and was
  deliberately excluded from the ENH-3081 `_apply_automation_env()`
  extraction — the exact same shape as this new var (a `CLAUDE_CODE_*`
  var meaningful only to the `claude` CLI). It requires a single-line
  addition, no signature changes anywhere, and zero blast radius on the
  four non-Claude runners (`CodexRunner`, `GeminiRunner`, `OmpRunner`,
  `KimiRunner`).
- **Option B** would require adding a `runner_kind` (or similar) parameter
  to `_apply_automation_env()` and updating all 5 call sites
  (`host_runner.py:353,644,1034,1219,1412`), plus a conditional branch
  inside a helper whose docstring and current 5x identical usage establish
  it as strictly host-agnostic (`LL_AUTOMATION`/`LL_AUTOMATION_PROFILE`
  only). No existing precedent for a host/runner conditional branch inside
  a shared helper was found anywhere in `host_runner.py` — host-specific
  behavior currently lives in per-class methods, not branches inside a
  shared function. Viable, but it inverts the helper's single-purpose
  contract for one host-scoped var, and touches more surface for no
  functional gain over Option A.

**(b) AC2's "the variable is absent" is now the wrong contract.**
`_apply_automation_env()`'s docstring states the semantics explicitly:

> `env` is merged over `os.environ` at every spawn site, so an absent key means
> "inherit the parent's value", never "clear".

That is why ENH-3081 added the neutralizing `else` branch setting
`LL_AUTOMATION=""`. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` sits on the same
gate and inherits the same leak vector: an interactive or non-automation
`claude` spawned from inside an automation session would silently keep the
flag and lose backgrounding, with no way to tell why. **AC2 must become
"explicitly neutralized on the `automation_profile is None` path," not
"absent"** — see the revised AC2 below.

### Open Question (blocking AC2) — what value turns the flag off?

`LL_AUTOMATION=""` works as an off-switch because *our own* readers
(`hooks/session_start.py:110`, `cli/history_context.py:206`) test truthiness of
the string. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is read by the **host**, not
by us, and its falsy-value handling is unverified — three candidate
neutralizing values, decision needed before implementing AC2:

**Option A**: Set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=""` (empty string) on
the `automation_profile is None` path — mirrors the `LL_AUTOMATION=""`
neutralization `_apply_automation_env()` already uses, so the two vars stay
symmetric.

> **Selected:** Option A — mirrors the codebase's only existing precedent for
> this exact leak concern (`LL_AUTOMATION=""`); Options B and C have no
> supporting precedent and C actively violates AC2. See Decision Rationale
> below — the empirical probe against the real `claude` host remains required
> before implementation closes out AC2.

**Option B**: Set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="0"` on that path —
only correct if the host's flag parser treats the literal string `"0"` (not
merely absence/emptiness) as its off value.

**Option C**: Pop the key from `env` entirely on that path, restoring pure
inheritance from the parent process rather than asserting an explicit falsy
value — the only option that does NOT mirror the `LL_AUTOMATION` precedent.

Resolve with a fourth probe using the FEAT-3076/3077 harness (real `claude -p`
child, stream-json capture, record under `postmortems/feat-3078-verify/`):
spawn with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=""` and again with `="0"`, and
check whether a `Bash run_in_background: true` call succeeds. Cheap, and AC2's
correctness depends on the answer.

### Decision Rationale

**Selected: Option A** — set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=""` on the
`automation_profile is None` path.

Scoring (0–3 per dimension, evidence gathered by parallel codebase-pattern
agents against `host_runner.py`, `docs/claude-code/settings.md`, and this
issue's own text):

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A (`""`) | 2 | 3 | 3 | 2 | **10/12** |
| B (`"0"`) | 0 | 3 | 3 | 1 | 7/12 |
| C (pop key) | 0 | 3 | 2 | 0 | 5/12 |

- **Option A** is the only candidate with internal precedent:
  `_apply_automation_env()` (`host_runner.py:1547-1562`) already neutralizes
  `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` with `""` for the identical
  "inherited-value would leak" scenario this issue's AC2 describes, keeping
  the two vars symmetric.
- **Option B** (`"0"`) has zero supporting precedent — no other env var in
  this codebase is turned off via literal `"0"`, and `docs/claude-code/settings.md:772`
  documents only `"1"` for this specific flag (the sibling
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY` row does define a `"0"` meaning, but a
  distinct one — "force on" — showing `"0"` semantics are flag-specific and
  don't transfer).
- **Option C** (pop the key) is disqualified on correctness, not just
  convention: `_apply_automation_env()`'s own docstring states an absent key
  means "inherit the parent's value," never "clear" — exactly the leak AC2
  was written to rule out ("explicitly neutralized... not merely omitted").
  Automation sessions do spawn nested `claude` children, so this is a live
  leak path, not a hypothetical one.

**✅ RESOLVED (2026-08-08)** — the fourth probe has been run against a real
`claude -p` child (`claude --version` 2.1.219), recorded under
`postmortems/feat-3078-verify/`: both `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=""`
and `="0"` restore `Bash run_in_background: true` to genuine async-launch
behavior, matching the unset-var control from `postmortems/feat-3076-verify/`.
Option A's off-value (`""`) is confirmed correct — no fallback needed. AC2 can
be marked satisfied on this point once implemented.

### Files to Modify
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()` env block at lines 345-362; the new `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` conditional inserts here.
- `scripts/little_loops/config-schema.json` — `orchestration` object (line 1554) gains a new boolean property; the object is `additionalProperties: false`, so the schema entry is mandatory.
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig` dataclass (line 63) gains the matching field and `from_dict()` entry, alongside the existing `host_cli`.
- `scripts/little_loops/config/core.py:784-801` — `BRConfig`'s orchestration serializer block hand-lists fields (not a generic dataclass dump); the new field must be added explicitly or it silently disappears from serialized config output (e.g. `ll-config get`).
- `scripts/little_loops/host_runner.py:196,216` (`HostRunner` Protocol) and its 6 sibling `build_streaming()` signatures — `CodexRunner:590`, `OpenCodeRunner:799` (stub), `PiRunner:873` (stub), `GeminiRunner:984`, `OmpRunner:1181`, `KimiRunner:1369` — all need the new parameter for Protocol conformance, even where inert.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/runners.py:39-53` — the `ActionRunner` Protocol's `run()` signature itself declares `automation_profile: str | None = None`; the issue previously only cited the `:191` forwarding call, not this source signature that `:191` reads from. Needs `disable_background_tasks: bool = False` added here for Protocol conformance.
- `scripts/little_loops/fsm/runners.py:98-135` (`DefaultActionRunner.run()`) — concrete implementation whose explicit signature mirrors the Protocol; needs the same new parameter before it can forward it at `:191`.
- `scripts/little_loops/fsm/runners.py:352-409` (`SimulationActionRunner.run()`) — needs the parameter added to its own signature (mirroring `automation_profile`), not just a survey note as the existing AC3 entry implies; confirmed its `del (...)` no-op list at `:404` already omits `automation_profile`, so add both `automation_profile` and `disable_background_tasks` to that list together.

### Dependent Files (Callers/Importers) — threading `disable_background_tasks` through
- `scripts/little_loops/subprocess_utils.py:320` `run_claude_command()` — the chokepoint where `invocation.env` reaches `subprocess.Popen`.
- `scripts/little_loops/issue_manager.py:1213,1401` — hardcode `automation_profile="ll-auto"`; the new flag inherits the same hardcoding pattern at these two call sites.
- `scripts/little_loops/issue_manager.py:139-218` — a second, previously unlisted local `run_claude_command()` wrapper (aliased `_run_claude_base` in `subprocess_utils`); already threads `automation_profile` (line 151, forwarded at line 217) and needs the same threading for `disable_background_tasks`. Six further call sites forward through this wrapper: `:340` (inside `run_with_continuation`, itself a wrapper at `:268` needing the same param), `:520`, `:826`, `:893`, `:1089`, `:1401`.
- `scripts/little_loops/fsm/executor.py:1902` — sets `extra_kwargs["automation_profile"]` from `PruningProfileConfig`; a second, config-driven origin for `automation_profile` that needs the same wiring.
- `scripts/little_loops/fsm/runners.py:191` and `scripts/little_loops/runner_spec.py:145,176,182` — forward `automation_profile` straight into `resolve_host().build_streaming(...)`.
- `scripts/little_loops/host_runner.py:644,1036,1223,1418` — sibling `if automation_profile is not None:` env blocks in `CodexRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner`; survey and either add a no-op parity entry or document as deliberately excluded (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` has no meaning for non-Claude binaries). `OpenCodeRunner`/`PiRunner` are stub runners with no env-building logic.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/conftest.py:725-742` (`_CMD_RUN_ENV_VARS`, `_restore_cmd_run_env_vars`) — the autouse fixture scrubs `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` specifically because they leak into descendant `pytest` processes when a test run is itself launched from inside an `ll-auto`/FSM-loop session (documented at `:713-724`, historically broke 48 tests). `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is injected in the identical `if automation_profile is not None:` block per this issue's own gate, so it is subject to the same leak vector and must be added to `_CMD_RUN_ENV_VARS`.
- `scripts/little_loops/fsm/executor.py:1886-1910` (`_execute_action` `extra_kwargs` assembly) — correction to the existing Call Path claim: `extra_kwargs["automation_profile"]` at `:1902` is sourced from `PruningProfileConfig` (a per-loop/per-state declarative field via `state.pruning_profile or self.fsm.pruning_profile`), not from `OrchestrationConfig`. `disable_background_tasks` lives on `OrchestrationConfig` (a global config object), a structurally different source with no existing per-call read in this block — the memoized `FSMExecutor._get_br_config()` (`:2063-2073`, already used elsewhere for `cache`/`deferred_tools`/`learning_tests` dispatch) is the accessor to consult here, not a copy of the `PruningProfileConfig` pattern.

_Wiring pass added by `/ll:wire-issue` — 2026-08-08:_
- `scripts/little_loops/parallel/worker_pool.py:885-934` (`WorkerPool._run_claude_command()`) — a **third** un-listed local wrapper around `run_claude_command` (imported `as _run_claude_base` at `:40`), alongside the `issue_manager.py:139-218` wrapper. Confirmed via read: its call to `_run_claude_base()` at `:924-933` does not forward `automation_profile` at all today, so it needs the same `disable_background_tasks` parameter added to its own signature (`:885-891`) and threaded into the `_run_claude_base(...)` call for `ll-parallel`/`ll-sprint` worker sessions to get parity with the `issue_manager.py` and FSM paths.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:36-70` (`MockActionRunner.run()`) — hand-written mock with an explicit (non-`**kwargs`) parameter list including `automation_profile`/`idle_timeout`; will raise `TypeError` once the FSM path passes `disable_background_tasks` through `extra_kwargs`, unless the mock's signature and `del (...)` line are updated. Also imported into `test_feat3033_idle_timeout.py:28` — update propagates there too.
- `scripts/tests/test_fsm_executor.py` (additional inline fake `ActionRunner` implementations around `:10963-10980`, `:11201-11220`) — same explicit-signature break risk as `MockActionRunner`; confirm and update alongside it.
- `scripts/tests/test_fsm_persistence.py:774` and `scripts/tests/test_usage_journal.py:25` — inline `run()` fakes mirroring the Protocol's explicit parameter list; same break risk.
- `scripts/tests/test_feat3033_idle_timeout.py:390-467` (`TestIdleTimeoutPrecedence`, esp. `test_idle_disabled_omits_kwarg_for_old_runners`) — direct template for a `disable_background_tasks` kwarg-gating regression test (asserts a runner predating a new kwarg still runs when that kwarg is omitted/default).
- `scripts/tests/test_feat3033_idle_timeout.py:90-105` (`test_idle_timeout_forwarded_to_run_claude_command`) — template for asserting `disable_background_tasks` is forwarded from the FSM path to `run_claude_command` via `patch(...)` + captured kwargs.
- `scripts/tests/test_fsm_runners.py:101-171` (`TestSimulationActionRunnerScenarios`) and `scripts/tests/test_fsm_executor.py:3850+` (`TestSimulationActionRunner`) — neither currently passes or asserts `automation_profile`/`idle_timeout` no-op behavior; genuine gap, add a case asserting `SimulationActionRunner.run(..., disable_background_tasks=True)` still returns the scenario-driven `ActionResult` unchanged.
- `scripts/tests/conformance/test_host_conformance.py:70-89` (`test_golden_path_invocation`, `isolated_env` fixture) — the `isolated_env` fixture clears `LL_HOST_CLI`/`LL_HOOK_HOST` but not `LL_AUTOMATION`-style vars; consider whether `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` needs a golden-path case per host for conformance coverage.

_Wiring pass added by `/ll:wire-issue` — 2026-08-08:_
- `scripts/tests/test_fsm_runners.py:445-598` (`TestDefaultActionRunnerSlashCommands`, e.g. `test_working_dir_kwarg_forwarded` at `:585`, `test_agent_kwarg_forwarded` at `:517`) — established one-test-per-forwarded-kwarg pattern for `DefaultActionRunner.run()`; add `test_disable_background_tasks_kwarg_forwarded` following this template. No such test exists today (confirmed: zero matches for `disable_background_tasks`/`background_tasks` anywhere under `scripts/`).
- Additional explicit-signature `ActionRunner`/`run()` fakes without a `**kwargs` catch-all that will `TypeError` once `disable_background_tasks` is added, beyond the `MockActionRunner` instances already cited above — confirmed via read of surrounding context: `scripts/tests/test_fsm_executor.py:2518,2564,3351,3446,3681,5261,6373,6415,9101,9218`; `scripts/tests/test_fsm_persistence.py:2251,2322,2418,2486`; `scripts/tests/test_learning_state.py:48` (class-level fake, params end at `model: str | None = None` with no `**kwargs`). Contrast — already-safe `**kwargs`-tolerant fakes needing no change: `test_fsm_persistence.py:2667,2726`, `test_host_guard.py:62`, `test_autodev_decision_gate.py:49`, `test_learning_state.py:547,632`, `test_action.py:37`, `test_fsm_executor.py:11113,11349,11454`.
- `scripts/tests/test_config.py:1012-1048` (`test_to_dict_orchestration`, `test_to_dict_orchestration_defaults_when_unset`) — `BRConfig.to_dict()` round-trip coverage for the `orchestration` block; asserts individual keys (won't break from a new field) but is the natural place to add a `disable_background_tasks` default-value assertion, not currently present.

### Documentation
- `docs/reference/API.md` (~5769-5789 `ActionRunner` Protocol block, ~9173-9198 `HostRunner` Protocol block) — hand-maintained signature mirrors; both need the new parameter added, matching the pattern used when `idle_timeout` (FEAT-3033) was added.
- `docs/guides/LOOPS_GUIDE.md:604-636` — line 632 states "This env-signal path is the only part that is implemented," describing the `automation_profile` gate; needs updating now that a second unconditional env var shares the gate.
- `docs/ARCHITECTURE.md` (~line 777, `PruningProfileConfig` row) — needs a note or row for `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`.
- `docs/reference/CONFIGURATION.md:1199-1269` (`orchestration` table, `:1203-1206`) — needs a new row for the config flag, following the `host_cli`/`request_path` pattern.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py:439-466` (`PruningProfileConfig` docstring, esp. the `.. warning::` block at `:455-466`) — a second, source-level (not `docs/*.md`) description of the env-injection mechanism; its "**Only the env-signal path is implemented**" claim becomes stale once a second, unconditional env var (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, sourced from `OrchestrationConfig` rather than `PruningProfileConfig`) shares the same gate. Needs a note distinguishing the two env vars' distinct config origins.

_Wiring pass added by `/ll:wire-issue` — 2026-08-08:_
- `skills/manage-issue/SKILL.md:~376-401` ("Headless-Safe Final Test Run") — confirmed via read: line 397 already names `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` explicitly, explaining why the shell-level `cmd & pid=$!; sleep N; kill $pid` `run_cmd` smoke-test pattern is exempt (the `Bash` tool's own backgrounding parameter is never set for it). This is the shipped explanation of the FEAT-3077 carve-out this issue's own Dependency section refers to as "restated in shell terms" — re-verify it still reads correctly once the flag defaults to `true`.
- `skills/go-no-go/SKILL.md:~172-176` ("Step 3b: Launch Adversarial Agents") — instructs launching two `Agent` tool calls with `run_in_background: true`; this is the "go-no-go carve-out" the Decision Rationale calls "not reachable under the `automation_profile` gate today." Confirmed via grep across `scripts/little_loops/loops/` that `go-no-go` is invoked from `oracles/resolve-decision.yaml`, `auto-refine-and-implement.yaml`, `rn-remediate.yaml`, `hitl-compare.yaml`, `brainstorm.yaml`, `autodev.yaml`, `recursive-refine.yaml`, `refine-to-ready-issue.yaml` — several of which could run under `automation_profile`, so this carve-out is dormant but real, not hypothetical.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Sequencing vs. ENH-3094/3095/3096/3097 — confirmed, not a conflict

Verified against current code and all four issue files: no `AutomationContext`
class exists anywhere in `scripts/little_loops/` (`grep -r "class AutomationContext"`
returns zero matches). `ENH-3094` (the AutomationContext-collapse proposal) is
`status: done`/`Decomposed` into three children — `ENH-3095` (add the dataclass,
thread through `HostRunner.build_streaming()`), `ENH-3096` (thread through
`ActionRunner.run()`, `blocked_by: [ENH-3095]`), `ENH-3097` (thread through
`run_claude_command()` and callers, `blocked_by: [ENH-3095]`) — all three still
`open`, none implemented. `ENH-3095`'s proposed `AutomationContext` dataclass
already carries a `disable_background_tasks: bool = False` field, pre-designed
to absorb this issue's output once it lands — confirming this issue's
raw-parameter approach (Pattern A, mirroring `automation_profile`) is the
correct, currently-conventional route and the ENH-309x collapse is a genuine
second pass, not rework this issue should preempt.

**Risk this surfaces, not this issue's to fix**: the "FEAT-3078 lands first"
ordering exists only as prose (this issue's own text, and each ENH-309x
issue's `## Parent Issue` section) — none of `ENH-3095`/`3096`/`3097` carries
`blocked_by: [FEAT-3078]` in frontmatter. Nothing in the current issue graph
would stop an automation pipeline that only respects `blocked_by`/`depends_on`
edges from picking up `ENH-3095` before this issue lands.

### Documentation edit contention — docs/ARCHITECTURE.md:777

Both this issue (AC5/AC6, adding a `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` note)
and `ENH-3095` (renaming the cited kwarg form from `automation_profile=...` to
`automation=...` once `AutomationContext` lands) target the identical
`PruningProfileConfig` row at `docs/ARCHITECTURE.md:777`. Current verbatim
content at that line still reads `automation_profile=...` (confirms no drift
since this issue's last refine pass). Whichever issue lands first will change
what the other needs to edit at that line — not a blocker, but the implementer
of whichever lands second should re-read the line rather than trust this
issue's own quoted wording.

### Open Questions Raised During Decision Review (2026-08-06)

Neither is resolved; both should be settled before or during implementation.

1. **Env override.** `orchestration.host_cli` has `LL_HOST_CLI`. Should this
   flag have `LL_DISABLE_BACKGROUND_TASKS`? Debugging a loop where the agent
   suddenly cannot background anything is far easier with a one-shot env
   override than a config edit — and the default is now `true`, so the
   surprising case is the common case. Either add it or record that it is
   deliberately config-only.
2. **Third parameter through the same Protocol.** — **RESOLVED: filed as
   ENH-3094** (2026-08-07). `automation_profile`, then `idle_timeout`
   (FEAT-3033), now `disable_background_tasks` — each costs seven runner
   signatures, the `ActionRunner` Protocol plus three implementations, and
   roughly eight test files of hand-written explicit-signature mocks. That is
   the majority of this issue's change surface, and the next flag pays it
   again. ENH-3094 proposes an `AutomationContext` dataclass and recommends
   sequencing it **after** this issue, so the collapse has three proven
   consumers rather than two. Not a blocker — but if the mock-signature churn
   stalls this implementation, flip the order rather than adding `**kwargs`
   escape hatches to the mocks.

### Pattern B Precedent Now Located
The Decision Rationale's rejected Option B ("a one-time `os.environ` mutation at config-load time") is not hypothetical — a live example of that exact pattern exists at `apply_host_cli_from_config()` (`scripts/little_loops/host_runner.py:1612`), which reads `config.orchestration.host_cli` and writes `LL_HOST_CLI` into `os.environ` once, before `resolve_host()` runs, with no per-call scoping. This is useful evidence for why Option A (per-call parameter) was chosen over mirroring this existing precedent: `apply_host_cli_from_config()`'s host_cli use case doesn't need per-invocation scoping (host selection is stable for a whole process), whereas `disable_background_tasks` does (per AC2), so the two config-threading patterns coexisting in this codebase are each correct for their own field, not in tension.

## Acceptance Criteria

1. When `automation_profile` is set and the new config flag is enabled, the child
   environment carries `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.
2. When `automation_profile` is unset, the variable is **explicitly neutralized**
   in the built env — not merely omitted. Omission means "inherit the parent's
   value" (`_apply_automation_env()` docstring, `host_runner.py:1552-1556`), which
   would leak the flag into interactive and non-automation children spawned from
   inside an automation session. The neutralizing value is whatever the Open
   Question probe establishes the host treats as off.
3. The `_apply_automation_env()` helper (`host_runner.py:1547`) and
   `ClaudeCodeRunner.build_streaming()` are the only env-construction sites;
   the recorded design decision (helper-with-host-guard vs. Claude-only line)
   is applied, and the other five runners are documented as deliberately
   excluded.
4. A test asserts, in both the automation and non-automation branches, that the
   variable is set to `1` and neutralized respectively — extending
   `scripts/tests/test_host_runner.py:62-82` (ENH-3081's clear-branch test),
   which already has this exact shape for `LL_AUTOMATION`.
5. `orchestration.disable_background_tasks` defaults to `true` (FEAT-3077's
   recorded decision), with a default-on schema `description`, and
   `docs/reference/CONFIGURATION.md`/`docs/ARCHITECTURE.md`/`docs/reference/API.md`/`docs/guides/LOOPS_GUIDE.md`
   are updated.
6. Because the default is on, the change is user-visible on upgrade for
   projects with `project.run_cmd` configured: a CHANGELOG entry records the
   behavior change and names `disable_background_tasks: false` as the opt-out.
   `docs/reference/HOST_COMPATIBILITY.md` records that the var is
   Claude-Code-only and inert for the other five runners (the other half of
   AC3's "documented as deliberately excluded").

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Threading Gap — now filed as BUG-3093
Three `run_claude_command()` call sites in `issue_manager.py` — `:826` (`_run_ready` inside Phase 1), `:893` (retry_result), `:1089` (decide_result) — omit `automation_profile` entirely (it defaults to `None`). Because the gate is `disable_background_tasks and automation_profile is not None`, threading the new flag alone will NOT activate it at these three sites.

**Escalated 2026-08-07: this is a defect in its own right, filed as BUG-3093**, not merely a scoping footnote. Post-ENH-3081 these three children now receive `LL_AUTOMATION=""` — an *explicit assertion* that they are not under automation, read as such by `hooks/session_start.py:110` and `cli/history_context.py:206` — even though they are `ll-auto` subprocesses of the same run as `:1237`/`:1425`, which do declare `automation_profile="ll-auto"`.

Consequence for this issue: without BUG-3093, `/ll:ready-issue` and `/ll:decide-issue` keep tool-level backgrounding under `ll-auto` while `/ll:manage-issue` loses it — preserving in three places the exact inconsistency FEAT-3060 was filed to remove. BUG-3093 is small (three call sites plus one test) and **should land with or before this issue**; if it does not, AC6's release note must name the three phases as not-yet-covered.

### Additional No-Op Site for AC3 Survey
`SimulationActionRunner.run()` (`fsm/runners.py:382`) declares `automation_profile` in its signature but ignores it by design (docstring: "Ignored in simulation"). Not previously listed among the sites AC3 requires surveying; add it to the parity survey as a fourth deliberately-excluded site (alongside `OpenCodeRunner`/`PiRunner` stubs), since `ActionRunner` implementations are exactly the surface AC3's "all env-injection blocks... surveyed" language covers.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
N/A — no new data shape is introduced; `disable_background_tasks` is a single boolean flag threaded as a parameter, not a new record type.

### Signatures
- `ClaudeCodeRunner.build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, automation_profile: str | None = None, workspace_root: Path | None = None) -> HostInvocation` — `host_runner.py:297-308`, gains `disable_background_tasks: bool = False`.
- `OrchestrationConfig` dataclass (`config/orchestration.py:62-73`) currently has only `host_cli`, `request_path`, `composer`, `cluster` — gains `disable_background_tasks: bool` field plus a `.get("disable_background_tasks", <default>)` entry in `from_dict()` (`:95-103`).
- `run_claude_command(command: str, ..., automation_profile: str | None = None) -> subprocess.CompletedProcess[str]` — `subprocess_utils.py:320`, gains the matching parameter, forwarded to `resolve_host().build_streaming(...)` at `:400-408`.

### Call Path
Automation entry point: `process_issue_inplace` (`issue_manager.py:676+`) -> `run_with_continuation` (`issue_manager.py:252`, forwards `automation_profile="ll-auto"` hardcoded at `:1213`/`:1401`) -> local `run_claude_command` wrapper (`issue_manager.py:139`, forwards at `:217`) -> `subprocess_utils.run_claude_command` (`:320`) -> `resolve_host().build_streaming` (`host_runner.py:297`), env block `:351-353` (the single insertion point).

FSM/loop path: `fsm/executor.py:_execute_action` (env-kwarg assembly `:1882-1910`, sets `extra_kwargs["automation_profile"]` from `PruningProfileConfig` at `:1902`) -> `ActionRunner.run` (Protocol `fsm/runners.py:39-53`, `DefaultActionRunner.run` `:98-112`) -> same `run_claude_command` (`:191`). `SimulationActionRunner` (`fsm/runners.py:382`) also declares the kwarg but ignores it by design ("Ignored in simulation") — a third no-op site for AC3's survey, not previously listed in Integration Map.

Spec-driven path: `runner_spec.py:128` originates `automation_profile: str | None = spec.args.get("automation_profile")` (not previously cited as the origination point — only the forwarding lines `:145,176,182` were listed) -> forwarded at `:145,176` -> `resolve_host().build_streaming(...)` directly at `:182`.

### Decision Rules
See `### Decision Rules` under `## Proposed Solution` — already states the gate (`disable_background_tasks and automation_profile is not None`) and escape hatch; not duplicated here to avoid two sources of truth for the same rule.

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


## Status

Open. All design decisions resolved (AC2 neutralizing value, AC3 helper vs.
direct-write placement); dependencies `FEAT-3077` and `BUG-3093` are `done`.
Ready for implementation.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 99/100 → PROCEED
**Outcome Confidence**: 80/100 → HIGH

### Since Last Check
- Both open design decisions flagged in the prior check are now resolved and
  recorded in the issue text: the AC2 neutralizing-value question resolved to
  Option A (`""`), confirmed by a real fourth probe against `claude -p`
  (verified on disk: `postmortems/feat-3078-verify/d1_empty_string.jsonl`,
  `d2_zero_string.jsonl`); the AC3 design decision (direct write in
  `ClaudeCodeRunner` vs. host-guarded helper) resolved to Option A via
  `/ll:decide-issue` (2026-08-08), scored 12/12 against Option B's 7/12.
- Dependencies now fully clear: `depends_on: FEAT-3077` and the related
  `BUG-3093` both show `status: Completed`.
- Re-verified against current code: no `disable_background_tasks`/
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` reference exists anywhere in
  `scripts/` yet (no duplicate work), and `_apply_automation_env()`
  (`host_runner.py:1547`) with its five callers (`:353,644,1034,1219,1412`)
  match the issue's line citations exactly.
- Remaining risk is unchanged in kind: this is a wide mechanical fanout
  (~34 file:line citations across runners, config, FSM plumbing, and ~15 test
  files). Each site is a uniform parameter-threading edit with a named test
  template, but there is no single automated completeness check tying all
  dependent call sites together — a missed site silently defaults to
  off/`None` rather than failing loudly.

## Session Log
- `/ll:manage-issue` - 2026-08-09T05:34:24 - `b7457e6e-9654-45e5-a9bd-43e1bcddbd28.jsonl`
- `/ll:ready-issue` - 2026-08-09T04:35:11 - `1a82e4d3-075a-4637-833a-bd558746e44f.jsonl`
- `/ll:confidence-check` - 2026-08-09T03:38:13 - `078e9245-e490-4404-8597-4895b11b1e76.jsonl`
- `/ll:decide-issue` - 2026-08-09T03:30:22 - `83bf90ea-254d-4998-aaa3-1f6e622ec8d9.jsonl`
- `/ll:confidence-check` - 2026-08-09T03:04:16 - `3f55b9b9-4ca3-4793-ac1c-ac23bd73138c.jsonl`
- `/ll:wire-issue` - 2026-08-09T03:00:45 - `d6eb2d4e-2ab1-4ee2-9817-a4e5989f03cb.jsonl`
- `/ll:decide-issue` - 2026-08-09T02:53:38 - `6431dd81-8b40-4678-a555-981e5457f142.jsonl`
- `/ll:confidence-check` - 2026-08-09T02:44:03 - `949315da-0b72-4a22-a42d-0493ed4f18c1.jsonl`
- `/ll:refine-issue` - 2026-08-09T02:04:44 - `e39c0eb4-7919-44f8-957b-3516c6ae853a.jsonl`
- `/ll:confidence-check` - 2026-08-06T20:25:34 - `70105668-3d2b-42b6-9a2d-3321c9e583d9.jsonl`
- `/ll:confidence-check` - 2026-08-06T20:05:56 - `6c2620d2-aa67-44ea-8afe-5abae5a9b234.jsonl`
- `/ll:verify-issues` - 2026-08-06T20:02:48 - `de53cd9d-a131-4b06-884e-b0b516bc04e2.jsonl`
- `/ll:refine-issue` - 2026-08-06T19:55:59 - `c721496d-ea12-4b5c-888c-b28707f79159.jsonl`
- `/ll:verify-issues` - 2026-08-06T19:50:56 - `b7dcfe12-1edc-4611-8efa-f277da09acfa.jsonl`
- `/ll:wire-issue` - 2026-08-06T19:46:10 - `9bd75941-bf4b-41b7-becc-e0c44aaa00f0.jsonl`
- `/ll:refine-issue` - 2026-08-06T19:35:57 - `6539e50d-3e51-42e1-bbc0-e1420a206a6f.jsonl`
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
