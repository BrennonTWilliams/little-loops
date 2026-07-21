---
id: ENH-2714
type: ENH
title: Automation-context static-prefix pruning for FSM invocations
priority: P2
status: done
captured_at: '2026-07-21T02:03:13Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- fsm
- orchestration
relates_to:
- EPIC-2456
- FEAT-2672
- FEAT-2711
- ENH-2486
confidence_score: 92
outcome_confidence: 68
score_complexity: 13
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 13
completed_at: '2026-07-21T02:44:55Z'
---

# ENH-2714: Automation-context static-prefix pruning for FSM invocations

## Summary

Every fresh FSM state invocation re-sends a large static prefix the state usually
doesn't need: the full skill/command catalog, the SessionStart hook's dump of the
resolved `ll-config.json` + `project_context` block, memory/session-digest
injection, and CLAUDE.md. Broaden the original catalog-only scope of this issue
to a general **automation-context static-prefix diet**: for a tight, controlled
FSM state whose prompt fully specifies the task, prune every prefix component we
control and suppress the rest where the host CLI allows it. Default remains the
full prefix; pruning is opt-in per loop/state.

This supersedes the session-resume approach (FEAT-2711) as EPIC-2456's default
per-invocation token lever: pruning makes every invocation strictly cheaper with
zero cross-state coupling, whereas resume amortizes the prefix but re-reads a
growing transcript each turn and has to un-break FSM state isolation
(fresh-on-retry/handoff, evaluator-independence guards) to stay correct.

## Motivation

`ll-verify-skill-budget` polices the catalog's total footprint, but every loop
state still pays for the whole listing — plus hook output and CLAUDE.md — on
every iteration. Most of that prefix is under our own control:

- **SessionStart hook output** (config JSON + project_context) is our code —
  trivially gated on an automation signal.
- **Skill/command catalog** narrows via existing host flags (the original scope
  of this issue; CLI-path analogue of FEAT-2672's SDK-path deferred loading).
- **Memory / session digest / historical context** injection is ours to gate.
- **CLAUDE.md** is host-controlled; suppression needs a per-host capability
  check, but for mechanical shell/verdict states project conventions add nothing.

Savings compound per state per iteration and require no semantic changes to loop
execution. CLAUDE.md is likely the dominant component in this repo — the
measurement AC should break the delta down per component.

## Current Behavior

`fsm/runners.py` → `build_streaming()` invocations inherit the full skill/command
catalog, full SessionStart hook output, memory injection, and CLAUDE.md; only
bare tool names flow through `--tools` CSV and no state narrows anything.

## Expected Behavior

A loop (or state, state overrides loop) may declare a prefix-pruning profile;
the host invocation is built with narrowing flags and an automation env signal
so gated components emit nothing. Default behavior unchanged.

## Proposed Solution

1. **Automation signal**: FSM runner sets `LL_AUTOMATION=1` (and
   `LL_AUTOMATION_PROFILE=<profile>`) in the child environment for pruned
   invocations.
2. **Hook gating**: SessionStart (and other injection hooks: memory recall,
   session digest, historical context) check the signal and emit nothing (or a
   minimal stub) under an automation profile. This is pure hook-side change —
   works on every host that runs our hooks.
3. **Catalog narrowing** (original scope): loop-YAML `tools:` / `skills:`
   allowlist at loop and state level, mapped to each host's narrowing flags via
   `resolve_host()` (Claude `--tools`/`--disallowedTools`-family; confirm
   per-host capability via `ll-doctor` before mirroring — defer-until-confirmed
   posture).
4. **CLAUDE.md suppression**: where the host exposes a flag/env to skip project
   instructions, map it behind the same `ll-doctor` capability check; no-op
   cleanly where unsupported.
5. **Presets**: ship conservative pruning presets for builtin loops' mechanical
   states (shell/verdict states) rather than auditing every loop up front.
6. **Validation**: ERROR if a state's action references a skill excluded by its
   own allowlist; WARN if a state that invokes `/ll:*` skills runs under a
   profile that suppresses the catalog.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

7. Wire the pruning-profile field through `FSMExecutor._run_action`
   (`fsm/executor.py`) — the actual choke point that reads loop/state config
   and must pass it to `DefaultActionRunner.run()`.
8. Wire the same profile through `runner_spec.py`'s `run_action()`/
   `ActionSpec` so `ll-harness`/`ll-action`/`ll-loop` don't silently bypass
   pruning outside the FSM executor path.
9. Add the pruning-profile config block to `config/core.py` (nested
   dataclass, `HistoryConfig`/`session_digest` pattern) and mirror it in
   `config-schema.json`.
10. Update `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/API.md`,
    `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, and
    `.claude/CLAUDE.md`'s MR-rule table to reflect the new capability,
    config block, and validation rule(s).

## Acceptance Criteria

- [ ] Per-state allowlist reaches the host invocation; unlisted states unchanged.
- [ ] SessionStart/memory/digest injection emits nothing under the automation
      profile; interactive sessions unchanged.
- [ ] Validation catches self-contradictory allowlists and
      catalog-suppressed-but-skill-invoking states.
- [ ] Cross-host: narrowing/suppression applied only on hosts whose capability
      is confirmed via `ll-doctor`; others no-op cleanly.
- [ ] Measured per-invocation input-token delta on a locked trace, broken down
      per prefix component (catalog / hook output / CLAUDE.md), recorded before
      close.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Automation signal (proposal 1)** — no `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE`
signal exists today; the only related env var is `LL_NON_INTERACTIVE`, which
every `HostRunner.build_streaming()`/`build_blocking_json()`/`build_detached()`
implementation sets unconditionally (`scripts/little_loops/host_runner.py`,
e.g. lines 275, 322, 343, 530, 581, 898, 1065) — it suppresses interactive UI
prompting only, not any static-prefix content. `run_claude_command()`
(`scripts/little_loops/subprocess_utils.py`) merges `HostInvocation.env` on top
of `os.environ.copy()`, so a new `LL_AUTOMATION` var set by the FSM
executor/runner would propagate to the subprocess without extra plumbing —
the natural injection point is alongside the existing `LL_NON_INTERACTIVE`
literals in each `build_streaming()` implementation.

**Hook gating (proposal 2)** — `scripts/little_loops/hooks/session_start.py`
`handle()` has exactly one existing env-based gate:
`if _backfill_path is not None and not _os.environ.get("LL_NON_INTERACTIVE")`
(line 149), which skips only the detached backfill-worker subprocess spawn.
The config-JSON + `project_context` digest payload (built via
`project_digest()`/`render_project_context()`, gated only by
`HistoryConfig.session_digest.enabled`) is **not** currently gated by any
automation signal and is returned unconditionally as
`LLHookResult(..., stdout=stdout_payload)` — this is the exact "static prefix"
content the issue wants suppressed. `ll-history-context`
(`scripts/little_loops/cli/history_context.py`) is a separate, explicitly
invoked CLI (not hook-fired) whose only existing gate is `--for-skill` against
`history.planning_skills` — it has no automation/interactive distinction
either.

**Catalog narrowing (proposal 3)** — `--tools` (CSV) is the only existing
narrowing flag, wired in `ClaudeCodeRunner.build_streaming()` and
`OmpRunner.build_streaming()` only (`host_runner.py`); no `--disallowedTools`
flag exists anywhere in the file today. `HostCapabilities.tool_allowlist`
(line 94) is `True` only for `claude-code` (line 240) and `omp` (line 1030) —
`CodexRunner`/`GeminiRunner`/`OpenCodeRunner` declare `tool_allowlist=False`
(lines 422, 834, plus one more), so proposal 3 is inherently a
defer-until-confirmed, per-host feature, matching the issue's stated posture.
`State.tools: list[str] | None` (`fsm/schema.py`, ~line 564) already exists as
a per-state field that falls through to a loop default when unset — this is
the existing override idiom to extend for a skill/command catalog allowlist,
rather than inventing a new one.

**CLAUDE.md suppression (proposal 4)** — `ll-doctor`
(`scripts/little_loops/cli/doctor.py` `main_doctor()`) already resolves
`describe_capabilities()` → `CapabilityReport` of `CapabilityEntry(name,
status, note)` and exits 1 if any entry's `status == "unsupported"` — the
exact boolean pass/fail gate proposal 4 wants. Adding a
`CapabilityEntry("claude_md_suppression", ...)` per host (following the same
pattern as the existing `structured_output` (ENH-2627) and `tool_allowlist`
entries, e.g. line 1139's `CapabilityEntry("tool_allowlist", "full",
"--tools <comma-separated list>")`) is the direct extension point.

**Validation rule (proposal 6)** — `fsm/validation.py`'s MR-rule pattern is
uniform: a suppression flag on `FSMLoop` (`fsm/schema.py`, e.g.
`parse_swallow_ok` at line ~227 in the allowed-keys set), an early
`if fsm.<flag>_ok: return []` guard, a scan over `fsm.states.items()`, and
`ValidationError(message=..., path=f"states.{state_name}...",
severity=ValidationSeverity.WARNING|ERROR)` appended per violation — see
`_validate_parse_swallow()` (`fsm/validation.py:1993`, MR-10, the most
recently added rule) as the template, wired into the dispatcher via
`errors.extend(_validate_parse_swallow(fsm))` at `validate_fsm():1275`. A new
`_validate_<name>()` for the self-contradictory-allowlist check (ERROR) and
catalog-suppressed-but-skill-invoking check (WARN) follows this exact shape,
plus a matching update to `fsm/fsm-loop-schema.json` and the `to_dict()`/
`from_dict()` skip-if-default round-trip on `FSMLoop`.

**Measurement (AC 5)** — no existing before/after token-delta utility exists;
the closest templates are `scripts/little_loops/cli/ctx_stats.py`'s
`_aggregate_tool_events()`/`_render()` (computes `saved = max(0,
total_processed - in_context)` and `reduction_pct`) for a delta-style
breakdown, and the project-wide `len(text) // 4` token-estimate convention
(`session_store.py::_estimate_tokens()`, reused inline in
`fsm/executor.py`'s `prompt_size_warn` event as `size // 4`) for the per-
component numbers.

### Files to Modify
- `scripts/little_loops/host_runner.py` — inject `LL_AUTOMATION`/
  `LL_AUTOMATION_PROFILE` alongside existing `LL_NON_INTERACTIVE` literals in
  each `build_streaming()`; add `claude_md_suppression`-style
  `CapabilityEntry` per host's `describe_capabilities()`
- `scripts/little_loops/hooks/session_start.py` — gate the config-JSON +
  `project_context` digest payload (not just the backfill spawn) on the new
  automation signal
- `scripts/little_loops/cli/history_context.py` — add automation-signal gate
  alongside the existing `--for-skill` gate
- `scripts/little_loops/fsm/schema.py` — new `FSMLoop`/`State` fields for the
  pruning profile + suppression flag(s), following the `parse_swallow_ok`
  pattern
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema mirror for the
  new fields (must stay in sync with `schema.py`)
- `scripts/little_loops/fsm/validation.py` — new `_validate_*` MR rule(s) for
  self-contradictory allowlists and catalog-suppressed-but-skill-invoking
  states, wired into `validate_fsm()`
- `scripts/little_loops/cli/doctor.py` — surface the new capability entry in
  `_print_report()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action` (~line
  1506) is the actual choke point (same shape as `PromptSizeGuardConfig`
  consumption) that must read the new loop/state pruning-profile field and
  pass it through to `fsm/runners.py`'s `DefaultActionRunner.run()` → 
  `run_claude_command()`; currently missing from this list despite being the
  direct analog of the config already cited under "Similar Patterns"
- `scripts/little_loops/runner_spec.py` — `run_action()`, the shared
  `resolve_host()`/`build_streaming()` caller behind `ll-harness`/`ll-action`/
  `ll-loop` (ENH-2668's dispatcher); any new `build_streaming()` kwarg or
  `ActionSpec` field for the pruning profile must thread through here too, or
  those three CLIs silently bypass pruning
- `scripts/little_loops/config/core.py` — new nested dataclass for the
  pruning-profile config block, following the `HistoryConfig`/
  `session_digest` pattern; consulted by `session_start.py`'s `handle()` gate
- `scripts/little_loops/config-schema.json` — new schema entry for the
  pruning-profile config block, plus an update to `history.session_digest.
  enabled`'s description noting automation-profile suppression is an
  independent gate (not a change to `enabled`'s own semantics)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py` (`DefaultActionRunner.run()`) and
  `scripts/little_loops/subprocess_utils.py` (`run_claude_command()`) — the
  call chain from FSM state execution to `resolve_host().build_streaming()`
  that any new profile parameter must thread through
- `scripts/little_loops/issue_manager.py` and
  `scripts/little_loops/parallel/worker_pool.py` — independent callers of
  `run_claude_command()` outside the FSM executor; if pruning is meant to
  apply there too, these need the same signal wired in

### Similar Patterns
- `scripts/little_loops/fsm/schema.py` `PromptSizeGuardConfig` (ENH-2486) —
  loop-level dataclass config toggle (`enabled`, threshold), consulted at a
  single choke point in `FSMExecutor._run_action` (`fsm/executor.py`
  ~line 1506), emitting a structured event rather than changing routing — the
  closest existing analog for a new loop-level pruning-profile config block
- `hooks/scripts/scratch-pad-redirect.sh` — bash-hook automation-context gate
  via `ll_config_value("<ns>.automation_contexts_only", "true")` combined with
  a `permission_mode` check — the idiom for config-key-driven automation
  gating in bash hooks (parallel to the Python `LL_NON_INTERACTIVE` idiom)

### Tests
- `scripts/tests/test_host_runner.py` — existing `--tools` CSV flag
  construction tests (~lines 147, 502–510, 871–878) to extend for the new env
  var and capability entry
- `scripts/tests/test_hook_session_start.py` — existing SessionStart hook
  injection tests to extend with an automation-profile-suppressed case
  (currently no test covers the config/digest payload being gated — only the
  backfill-spawn gate is implicitly covered)
- `scripts/tests/test_fsm_validation.py` — existing MR-1..MR-11 test pattern
  to extend for the new rule(s)
- `scripts/tests/test_cli_doctor.py` — capability-report rendering tests to
  extend for the new entry
- `scripts/tests/test_subprocess_utils.py` (~lines 1786–1932) — `--tools`
  flag-construction tests at the `run_claude_command()` layer

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py::TestPromptSizeGuardConfig` (line 2718) —
  exact test-class template for the new pruning-profile dataclass:
  `test_defaults` / `test_from_dict_*` / `test_to_dict_omits_defaults` /
  `test_round_trip` / `test_fsmloop_default_omits_key` /
  `test_fsmloop_scoped_round_trip`
- `scripts/tests/test_fsm_validation.py::TestParseSwallow` (lines 3910–4017,
  MR-10) — exact test-class template for the new MR-rule(s): per-rule fixture
  helper, `test_mr{N}_fires_for_*`, `test_mr{N}_clean_with_*`,
  `test_mr{N}_suppressed_by_*_ok`, `test_mr{N}_wired_into_validate_fsm`,
  `test_mr{N}_*_ok_recognized_as_top_level_key`
- `scripts/tests/test_history_context_cli.py::TestForSkillFlag` (line 267) —
  existing config/env-driven gate-suppression pattern (returns 0 + empty
  stdout when suppressed) to model the new `LL_AUTOMATION` gate on
- `scripts/tests/test_runner_spec.py` — needs a case confirming the pruning
  profile threads through `run_action()`/`ActionSpec` for `ll-harness`/
  `ll-action`/`ll-loop`, not just the FSM executor path
- `scripts/tests/test_fsm_executor.py` — needs a new integration test class
  (pattern: `class TestRateLimitCircuit` at line 6924, one class per
  cross-cutting feature exercising `FSMExecutor` directly) for end-to-end
  pruning-profile behavior
- `scripts/tests/test_host_runner.py` — the `test_build_streaming_includes_
  non_interactive_env` family (lines 185–204, 536–554, 785–794, 911–928, one
  per host class) should be extended with `LL_AUTOMATION`/
  `LL_AUTOMATION_PROFILE` `.get()` assertions alongside the existing
  `LL_NON_INTERACTIVE` checks

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — capability table (~line 133) and
  the "Runnable Capability Check" enumerated prose (~lines 303–312) both
  explicitly list the current capability set; need a `claude_md_suppression`
  row/entry
- `docs/reference/API.md` — documents `CapabilityReport`/`HostInvocation`/
  `HostRunner`; needs the new capability entry and any new `build_streaming`
  kwarg
- `docs/reference/EVENT-SCHEMA.md` — if AC5's measurement breakdown is
  implemented as a structured event (parallel to `prompt_size_warn`, ~line
  473/1207), it needs a schema stub at `docs/reference/schemas/`, a table
  row, and `ll-generate-schemas` regeneration; `docs/observability/
  des-audit.md` coverage is required by `ll-verify-des-audit`'s gate
- `docs/guides/LOOPS_GUIDE.md` and `docs/generalized-fsm-loop.md` — canonical
  FSM-authoring references that describe `tools:`/`--tools` narrowing
  conceptually; need the new per-state/per-loop allowlist and pruning-profile
  block documented
- `docs/guides/HISTORY_SESSION_GUIDE.md` — references `session_digest`
  config; needs a note that automation-profile suppression is an independent
  gate from `session_digest.enabled`
- `.claude/CLAUDE.md` — the "Loop Authoring" MR-rule table needs a new row
  for the added rule(s), matching the existing MR-1..MR-11/policy-table
  format

## Impact

- **Priority**: P2 — promoted from P3; now the epic's default per-invocation
  lever, lower risk than session resume with comparable or better savings.
- **Effort**: Medium (~120–180 LOC + tests): schema + host-flag mapping +
  hook gating + presets.
- **Risk**: Low-Medium — an over-tight profile can break a state; validation,
  opt-in defaults, and conservative presets mitigate.

## Session Log
- `ll-auto` - 2026-07-21T02:44:55 - `6cefbe57-31f7-452d-9e09-a3270a725dce.jsonl`
- `/ll:confidence-check` - 2026-07-20T00:00:00 - `5b9fa682-b5e9-431b-a84c-f5970c746630.jsonl`
- `/ll:wire-issue` - 2026-07-21T02:28:01 - `e690f789-037c-4f8e-a379-0612e34215a8.jsonl`
- `/ll:refine-issue` - 2026-07-21T02:22:45 - `54636baa-a349-4db8-afaa-ae03f3f74780.jsonl`
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`
- Re-scoped 2026-07-20: broadened from catalog-only pruning to full
  static-prefix pruning; promoted P3→P2; supersedes FEAT-2711 as the epic's
  default per-invocation savings lever (FEAT-2711 re-scoped to
  continuity-of-reasoning chains).

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-20
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
