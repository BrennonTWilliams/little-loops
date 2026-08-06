---
id: FEAT-3060
title: Hard-disable background tasks in headless automation instead of instructing
  against them
type: FEAT
priority: P3
status: done
testable: true
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T16:06:39Z'
relates_to:
- BUG-3058
- BUG-2408
- BUG-3026
- BUG-2729
- BUG-2730
labels:
- automation
- headless
- host-runner
decision_needed: false
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 45
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
size: Very Large
---

# FEAT-3060: Hard-disable background tasks in headless automation instead of instructing against them

## Summary

Every existing defense against "agent backgrounds a task, ends its turn, work is
lost" is an *instruction*. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` is a hard
lever documented in the vendored settings reference but referenced nowhere in
this codebase. Setting it for automation invocations would make the failure
structurally impossible rather than merely discouraged.

## Motivation

Three independent instruction-based mitigations already exist, and the failure
still recurs:

- `skills/manage-issue/SKILL.md:376-400` forbids backgrounding the final suite.
  BUG-3026 measured the agent violating it in 3 of 10 sprint runs.
- BUG-2730's stay-in-turn contract, now reaching `ll-auto` via BUG-3058.
- BUG-3058's finalize re-drive, which recovers after the fact rather than
  preventing.

Each narrows the window; none closes it. An LLM instructed not to background a
task can still background a task. The env var cannot be disregarded.

## Current Behavior

`grep -rn "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS" scripts/` returns nothing. The
only occurrence in the repo is `docs/claude-code/settings.md:772`, which
describes it as disabling "all background task functionality, including the
`run_in_background` parameter on Bash and subagent tools, auto-backgrounding".

`host_runner.py` builds the child environment and already injects
`LL_AUTOMATION` / `LL_AUTOMATION_PROFILE` when `automation_profile` is set
(`host_runner.py:351-353`), so the injection point exists and is exercised.

## Expected Behavior

Automation invocations that opt into an automation profile also disable
background tasks in the child, unless explicitly overridden. An agent in that
child cannot background its test suite, so it cannot end its turn waiting on one.

## Proposed Solution

Inject `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` alongside the existing
`LL_AUTOMATION` pair in the host runner's env-building blocks, gated on a new
config flag so the behavior can be turned off per project.

**The tradeoff that makes this a FEAT rather than a bug fix**: the same
`manage-issue` skill that forbids backgrounding the final suite explicitly
*permits* backgrounding for smoke tests — `SKILL.md:394-396` carves out "for
long-running processes (servers), start in background, wait briefly for startup,
then terminate." A blanket disable breaks that carve-out. Resolving this
requires deciding which of the two matters more in automation, or finding a
narrower mechanism than the all-or-nothing env var.

Open question worth answering before implementing: does the flag disable the
`Bash` `run_in_background` parameter only, or also the synchronous-agent paths
`ll-parallel` relies on? The documentation says "and subagent tools", which may
be broader than intended here.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

**Option A**: Thread a new `disable_background_tasks: bool` parameter through `build_streaming()`'s existing call chain (mirroring `automation_profile`'s Pattern A) and gate the `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` block in `ClaudeCodeRunner.build_streaming()` on `disable_background_tasks and automation_profile is not None`. Every caller that already threads `automation_profile` (`issue_manager.py:1213,1401`, `fsm/executor.py:1902`/`fsm/runners.py:191`, `runner_spec.py:145,176,182`) reads the new config flag once and passes it down alongside the existing profile name.

> **Selected:** Option A — the only one of the two documented live patterns that structurally satisfies AC2's per-invocation absence requirement.

**Option B**: Read the config flag directly inside `host_runner.py` via a new `apply_disable_background_tasks_from_config()`-style helper (mirroring `apply_host_cli_from_config()`, Pattern B) that mutates `os.environ` once ahead of `resolve_host()`.

**Recommended**: Option A — AC2 requires the variable to be *absent* whenever `automation_profile` is unset, i.e. gating must be per-invocation. Pattern B's `os.environ` mutation happens once at config-load time and persists process-wide for every subsequent `claude` subprocess spawned in that process, including interactive ones — it cannot satisfy a per-invocation absence requirement the way Pattern A's caller-threaded parameter can.

### Decision Rationale

**Selected: Option A** — thread `disable_background_tasks` through `build_streaming()`'s existing `automation_profile`-style call chain.

Option B is disqualified on correctness grounds, not merely style: a one-time `os.environ` mutation ahead of `resolve_host()` persists for the rest of the process, so it would leak `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` into later interactive or non-automation invocations sharing that process — directly violating AC2's per-invocation absence requirement. Option A reuses an already-proven, already-tested per-call gating pattern (`automation_profile`, `host_runner.py:351-353`) with a near-identical conditional and a direct test template (`test_automation_profile_env`, `test_host_runner.py:962-966`) to copy.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 1 |
| Simplicity | 2 | 3 |
| Testability | 3 | 2 |
| Risk | 2 | 0 |
| **Total** | **10/12** | **6/12** |

Key evidence:
- `automation_profile` is threaded as a per-call parameter through `ClaudeCodeRunner.build_streaming()` and forwarded by every caller down the chain — the same shape this feature needs (`host_runner.py:297-353`).
- `apply_host_cli_from_config()` (`host_runner.py:1612-1637`), Option B's model, mutates `os.environ` once at config-load time with no per-call scoping or restoration — its only production call site (`cli/doctor.py:998,1050`) confirms it's a load-time toggle, not a call-time gate.
- `test_automation_profile_env()` (`test_host_runner.py:962-966`) asserts directly against `invocation.env` with no subprocess execution, and extends cleanly to also assert absence for AC2 — a first-of-kind assertion in that file per the issue's own research notes.

## Use Case

An operator runs `ll-auto` overnight across a sprint of eight issues and is not
present to observe it. On issue five, the implement agent hits a slow test suite,
backgrounds it to keep working, and ends its turn narrating that it will wait for
the completion notification. That signal never fires headlessly.

Today the run either recovers by inference (dirty-tree fallback), recovers by
re-drive (BUG-3058), or loses the work outright if anything else vetoes. With
this feature the agent's `run_in_background: true` call is rejected by the host,
so it runs the suite in the foreground and reaches Phase 5 normally. The operator
returns to eight completed issues rather than seven and a forensic exercise.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()` env block at lines 345-362; the new `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` conditional inserts here, the only correct site since the var is Claude-Code-specific.
- `scripts/little_loops/config-schema.json` — `orchestration` object (line 1554) gains a new boolean property; the object is `additionalProperties: false`, so the schema entry is mandatory, not optional.
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig` dataclass (line 63) gains the matching field and `from_dict()` entry, alongside the existing `host_cli`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:784-801` — `BRConfig`'s orchestration serializer block hand-lists `host_cli`, `request_path`, `composer.adaptive.*`, `cluster.*`; it is not a generic dataclass dump, so the new field silently disappears from serialized config output (e.g. `ll-config show --json`) unless added here explicitly.
- `scripts/little_loops/host_runner.py:196,216` (`HostRunner` Protocol) and its 6 sibling `build_streaming()` signatures — `CodexRunner:590`, `OpenCodeRunner:799` (stub), `PiRunner:873` (stub), `GeminiRunner:984`, `OmpRunner:1181`, `KimiRunner:1369` — all declare `automation_profile` for Protocol conformance even where inert (the two stubs raise before reaching env-injection code). A new parameter needs the same signature-parity addition across all 7 to keep the Protocol satisfied, even though only `ClaudeCodeRunner` acts on it.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:320` `run_claude_command()` — merges `invocation.env` into `os.environ.copy()` (lines 412-413) immediately before `subprocess.Popen`; the single chokepoint where any env change actually reaches the child process.
- `scripts/little_loops/issue_manager.py:1213,1401` — hardcode `automation_profile="ll-auto"` directly (the BUG-3058 fix), rather than threading a caller-supplied value. Any new flag gated on `automation_profile` being set inherits this same hardcoding at these two call sites.
- `scripts/little_loops/fsm/executor.py:1902` — sets `extra_kwargs["automation_profile"]` from `PruningProfileConfig` when enabled — a second, config-driven origin for `automation_profile`, distinct from the `"ll-auto"` literal above.
- `scripts/little_loops/fsm/runners.py:191` and `scripts/little_loops/runner_spec.py:145,176,182` — both forward `automation_profile` straight into `resolve_host().build_streaming(...)`, same chokepoint as `subprocess_utils.py`.
- `scripts/little_loops/host_runner.py:644,1036,1223,1418` — sibling `if automation_profile is not None:` env blocks in `CodexRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner` build envs the same structural way but for non-Claude binaries, where `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` has no meaning. `OpenCodeRunner`/`PiRunner` are stub runners (every method `raise HostNotConfigured(...)`) with no env-building logic at all.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:139-218` — a **second, previously unlisted** `run_claude_command()` wrapper, distinct from the imported `subprocess_utils.run_claude_command` (aliased `_run_claude_base` at `issue_manager.py:66`). It already threads `automation_profile` as a parameter (line 151) and forwards it explicitly at line 217; a new `disable_background_tasks` parameter needs the same threading here, or it never reaches this wrapper's callers. All of the following call THIS local wrapper, not `subprocess_utils` directly: `issue_manager.py:340` (inside `run_with_continuation`, itself a further wrapper defined at `issue_manager.py:268` that also threads `automation_profile` and would need the new param too), `:520`, `:826`, `:893`, `:1089`, `:1391` (hardcodes `automation_profile="ll-auto"` at `:1401`, same pattern as the already-known `:1213` hardcode inside `run_with_continuation`).

### Conventions in Force
- Config sections in this codebase are `@dataclass`es with a `from_dict(cls, data)` classmethod using `.get(key, default)` (lenient — never raises on missing keys), mirrored by a `config-schema.json` object entry that is `additionalProperties: false` with a documented `default` — evidence: `scripts/little_loops/config/orchestration.py:63-103`, `scripts/little_loops/config-schema.json:1554-1631`.
- Two disagreeing patterns exist in this codebase for getting a config value into `host_runner.py`'s child env, and both are live:
  - Pattern A — the value is a caller-supplied parameter threaded through every call site down to `build_streaming()`, never read from config inside `host_runner.py` itself. Evidence: `automation_profile` (`host_runner.py:351-353` and its four siblings at `:644`, `:1036`, `:1223`, `:1418`).
  - Pattern B — the value is read from config once via a dedicated `apply_*_from_config()` helper that writes directly to `os.environ` before `resolve_host()` runs. Evidence: `apply_host_cli_from_config()` (`host_runner.py:1612-1637`).
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` would be this codebase's second host-scoped-only env var; the existing precedent (`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`, `host_runner.py:345-348`) is written directly into `ClaudeCodeRunner`'s dict literal with no shared cross-runner helper — there is no shared "build base env" function in this file.

### Tests
- `scripts/tests/test_host_runner.py:962-966` — `test_automation_profile_env()`, the closest precedent for asserting a new conditional env key directly against `invocation.env` (no subprocess execution).
- `scripts/tests/test_host_runner.py:1334-1382` — `TestApplyHostCliFromConfig`, the `monkeypatch.setenv`/`delenv` plus fake-config pattern used for Pattern-B-style config→env-var helpers.
- No existing test in this file asserts *absence* of an env key — AC2 ("variable is absent") would be this file's first such test.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_utils.py:2318-2368` (`TestRunClaudeCommandHostRunner.test_delegates_to_resolve_host`) — **will break**: asserts `mock_runner.build_streaming.assert_called_once_with(...)` with an exact kwarg set (no `disable_background_tasks`). Adding the new kwarg to `subprocess_utils.run_claude_command()`'s call to `build_streaming()` fails this test's exact-match assertion until updated.
- `scripts/tests/test_config.py:3406-3474` (`TestOrchestrationConfig`) — mirror the `request_path` default/override pair (`test_from_dict_request_path_defaults_cli`/`test_from_dict_request_path_batch`, `:3467-3473`) for the new boolean field's `from_dict()` default and explicit-`True` cases.
- `scripts/tests/test_config.py:3476-3510` (`TestBRConfigOrchestration`) — add a `.ll/ll-config.json` file-read-through test mirroring `test_orchestration_host_cli_from_file`.
- `scripts/tests/test_config_schema.py:787-823` — add a structural schema test mirroring `test_orchestration_host_cli_in_schema`/`test_orchestration_request_path_batch_in_schema` asserting the new property's `type`/`default` in `config-schema.json`.
- `scripts/tests/test_issue_manager.py:1390-1435` (`test_forwards_automation_profile_to_subprocess`/`test_automation_profile_defaults_to_none`) — template pair to copy for the `issue_manager.py:139-218` local wrapper's `disable_background_tasks` forwarding, once that wrapper is in scope (see Dependent Files above).
- No end-to-end test exercises `automation_profile`/env propagation via a real subprocess anywhere in the suite (`test_fsm*.py`, `test_issue_manager.py`, `test_subprocess_utils.py` all mock `Popen`/`resolve_host`) — AC6 ("verified against a real host invocation") has no existing harness to extend and will need a manual or new integration check.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (~5769-5789 `ActionRunner` Protocol block, ~9173-9198 `HostRunner` Protocol block) — hand-maintained signature mirrors (not generated); both need the new parameter added, matching the pattern used when `idle_timeout` (FEAT-3033) was added.
- `docs/guides/LOOPS_GUIDE.md:604-636` — line 632 states "This env-signal path is the only part that is implemented," describing the `automation_profile` gate. Adding a second unconditional env var on the same gate makes this sentence stale; needs updating.
- `docs/ARCHITECTURE.md` (~line 777, `PruningProfileConfig` row) — documents the `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` injection mechanism this feature extends; needs a note or row for `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`.
- `docs/reference/CONFIGURATION.md:1199-1269` (`orchestration` table, `:1203-1206`) — needs a new row for the config flag, following the `host_cli`/`request_path` pattern.
- `skills/go-no-go/SKILL.md:174,274,278` — a **second backgrounding carve-out** beyond `manage-issue`'s smoke-test one: launches two agents concurrently with `run_in_background: true` (line 174), then waits for both before a foreground judge step (line 278). AC3 currently names only the `manage-issue` carve-out; this location would also break under a blanket disable if `/ll:go-no-go` runs under an `automation_profile`-set session, and should be accounted for in AC3's resolution.

## Program Design

### Signatures

- `ClaudeCodeRunner.build_streaming(self, prompt: str, ..., automation_profile: str | None = None) -> HostInvocation` — existing, `host_runner.py:297`; env-building block at `:351` gains the new var.
- `resolve_host() -> HostRunner` — existing, `host_runner.py`; unchanged entry point.
- `run_claude_command(command: str, ..., automation_profile: str | None = None) -> subprocess.CompletedProcess[str]` — existing, `subprocess_utils.py:320`; unchanged, forwards to the runner.

### Call Path

`process_issue_inplace` (`issue_manager.py:619`) -> `run_with_continuation` (`issue_manager.py:224`) -> `run_claude_command` (`subprocess_utils.py:320`) -> `resolve_host` -> `ClaudeCodeRunner.build_streaming` (`host_runner.py:297`), whose env block at `host_runner.py:351-353` already injects `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` and is the single insertion point. The FSM path reaches the same block via `fsm/runners.py:191`. Four sibling env blocks exist in `host_runner.py` (`:644`, `:1036`, `:1223`, `:1418`) and must be surveyed for parity before implementing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Decision Rules
- Gate: inject `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` only when the new config flag is enabled AND `automation_profile is not None` on the same `build_streaming()` call — mirrors the existing `LL_AUTOMATION` gate (`host_runner.py:351`), so AC2 ("variable absent when automation_profile is unset") holds structurally rather than via a separate check.
- Escape hatch: the existing `automation_profile is None` path (interactive sessions) already bypasses the block entirely; AC3's "defaults off" requirement is the only other override needed.

## Acceptance Criteria

1. When `automation_profile` is set and the new config flag is enabled, the child
   environment carries `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.
2. When `automation_profile` is unset, the variable is absent — interactive
   sessions are unaffected.
3. The config flag defaults are decided and documented, with the
   `manage-issue` server-smoke-test carve-out (`SKILL.md:394-396`) explicitly
   addressed in the decision: either the carve-out is retired, or the flag
   defaults off.
4. All env-injection blocks in `host_runner.py` are surveyed and either updated
   for parity or documented as deliberately excluded.
5. A test asserts presence and absence of the variable across both branches.
6. The flag's actual scope is verified against a real host invocation — whether
   it disables only `Bash` `run_in_background` or also the synchronous agent
   paths `ll-parallel` depends on.

## Impact

Closes the last gap in a failure mode that silently discards completed work. The
2026-08-04 `ll-auto --only ENH-3046` run lost 21.6 minutes of correct,
fully-tested work this way, and BUG-3026 shows a 30% recurrence rate in one
sprint.

Cost is loss of legitimate backgrounding in automation contexts. If the
server-smoke-test carve-out turns out to matter, this should be scoped down or
closed in favor of the instruction-based defenses.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/claude-code/settings.md:772` | The only description of the flag's scope |
| `skills/manage-issue/SKILL.md:376-400` | The instruction this would replace, and the carve-out it would break |
| `docs/reference/HOST_COMPATIBILITY.md` | Whether non-Claude hosts have an equivalent |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-06_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 45/100 → LOW

### Gaps to Address
- `stale_cli_flag` claim gap (advisory, capped Criterion 4 to 10/20): the "Current Behavior" section cites `ll-config show --json` as an example command, but `ll-config` only has a `get` subcommand — no `show` subcommand exists. Correct the reference or drop the example.

### Outcome Risk Factors
- Wide, partly-hidden call-site fanout: the `/ll:wire-issue` pass surfaced a second, previously-unlisted local `run_claude_command` wrapper in `issue_manager.py` (lines 139-218) with 6 further call sites (`:340`, `:520`, `:826`, `:893`, `:1089`, `:1391`) needing the new parameter threaded, on top of the already-enumerated `subprocess_utils.py`/`fsm/runners.py`/`runner_spec.py`/sibling-runner sites — total call sites exceed 11, raising the risk that a site is missed during threading.
- AC6 ("the flag's actual scope is verified against a real host invocation") has no existing test harness to extend — every test in `test_fsm*.py`, `test_issue_manager.py`, and `test_subprocess_utils.py` mocks `Popen`/`resolve_host`, so confirming whether `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` disables only `Bash run_in_background` or also the synchronous agent paths `ll-parallel` relies on will require a manual, out-of-suite verification step.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-06
- **Reason**: Issue too large for single session (size score 11/11, Very Large)

### Decomposed Into
- FEAT-3076: Verify actual scope of CLAUDE_CODE_DISABLE_BACKGROUND_TASKS via a real host invocation
- FEAT-3077: Decide and document the smoke-test/go-no-go carve-out policy for CLAUDE_CODE_DISABLE_BACKGROUND_TASKS
- FEAT-3078: Thread a disable_background_tasks config flag through host_runner and all call sites

## Status

**Done** (decomposed)

## Session Log
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
- `/ll:confidence-check` - 2026-08-06T05:07:33 - `3d243a8e-120f-43de-b25f-cdf16ffa7a9e.jsonl`
- `/ll:verify-issues` - 2026-08-06T05:04:56 - `97bcaf78-1228-465e-bd3b-1ab844110936.jsonl`
- `/ll:wire-issue` - 2026-08-06T05:01:07 - `04d887ad-8511-4879-ac4c-993ed515d9ac.jsonl`
- `/ll:decide-issue` - 2026-08-06T04:51:51 - `9a0bc23d-54cd-4a9e-9555-02eca4ffdbbd.jsonl`
- `/ll:refine-issue` - 2026-08-06T04:47:52 - `78388c39-2537-4486-8c66-c9667a139f0c.jsonl`
- `/ll:capture-issue` - 2026-08-05T16:09:36 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- `/ll:capture-issue` - 2026-08-05 - Captured from the ENH-3046 run forensics
  session; recorded as an explicit decision rather than an unstated omission.
