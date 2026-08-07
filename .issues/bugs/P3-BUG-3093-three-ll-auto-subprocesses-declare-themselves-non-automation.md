---
id: BUG-3093
type: BUG
title: Three ll-auto subprocesses omit automation_profile and now explicitly declare
  themselves non-automation
priority: P3
status: open
discovered_date: 2026-08-07
discovered_by: pre-implementation-review
captured_at: '2026-08-07T00:00:00Z'
labels:
- automation
- host-runner
- headless
testable: true
verify_verdict: VALID
relates_to:
- ENH-3081
- FEAT-3078
- ENH-2714
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3093: Three ll-auto subprocesses omit automation_profile and now explicitly declare themselves non-automation

## Summary

`process_issue_inplace` spawns its `claude -p` children through
`run_claude_command()`. Two of those call sites hardcode
`automation_profile="ll-auto"`:

- `scripts/little_loops/issue_manager.py:1237` — the implement subprocess
- `scripts/little_loops/issue_manager.py:1425` — the finalize-retry subprocess

Three others, on the same `ll-auto` run, pass no `automation_profile` at all:

- `:826` — `_run_ready()` (Phase 1, `/ll:ready-issue`)
- `:893` — the ready-issue fallback retry
- `:1089` — `/ll:decide-issue --auto`

All five are equally "under automation" — they are subprocesses of the same
`ll-auto` invocation, driving little-loops skills non-interactively. Only two
say so.

## Why this matters more after ENH-3081

Before `bab8c1fc` (ENH-3081), `_apply_automation_env()` set `LL_AUTOMATION`
only when `automation_profile is not None`. An omitted profile meant the key
was absent from the merged env, i.e. **inherit whatever the parent had** —
an unstated, permissive default.

ENH-3081 added the neutralizing `else` branch
(`scripts/little_loops/host_runner.py:1547-1564`):

```python
else:
    env["LL_AUTOMATION"] = ""
    env["LL_AUTOMATION_PROFILE"] = ""
```

So these three children now carry `LL_AUTOMATION=""` — an *explicit assertion*
that they are not under automation. Both runtime readers treat present-but-falsy
as off:

- `scripts/little_loops/hooks/session_start.py:110` — `_under_automation = bool(_os.environ.get("LL_AUTOMATION"))`
- `scripts/little_loops/cli/history_context.py:206` — `if _os.environ.get("LL_AUTOMATION"):`

ENH-3081 is correct on its own terms — clearing an inherited value is exactly
right for a genuine non-automation spawn. The defect is that these three sites
are not non-automation spawns; the omission was tolerable when it meant
"unspecified" and is wrong now that it means "no."

## Status

open — discovered during pre-implementation review of FEAT-3077/FEAT-3078
(2026-08-07). Not yet reproduced under instrumentation; the analysis is
static, from the call sites and the two env readers.

## Current Behavior

Of the five `run_claude_command()` call sites in `process_issue_inplace`, two
declare `automation_profile="ll-auto"` and three declare nothing. The three
silent ones therefore build a child env containing `LL_AUTOMATION=""`, which
both readers evaluate as "not under automation."

## Expected Behavior

All five subprocesses of a single `ll-auto` run identify as automation
children with `automation_profile="ll-auto"`, so `LL_AUTOMATION=1` reaches
every phase uniformly.

## Steps to Reproduce

1. Run `ll-auto --only <ID>` on any issue that reaches Phase 1.
2. Inspect the `/ll:ready-issue` child's environment (or instrument
   `hooks/session_start.py:110`).
3. Observe `LL_AUTOMATION=""` → `_under_automation` is `False`, while the
   `/ll:manage-issue` child in the same run has `LL_AUTOMATION=1`.

Automation-aware context handling (what ENH-2714/ENH-3081 exist to provide)
applies to implement and finalize-retry but not to Phase 1, Phase 1's retry,
or decide.

## Impact

1. Inconsistent automation-context handling across phases of a single run.
2. Blocks FEAT-3078: its gate is `disable_background_tasks and automation_profile
   is not None`, so `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` structurally cannot
   reach these three children. `/ll:ready-issue` and `/ll:decide-issue` would
   retain tool-level backgrounding while `/ll:manage-issue` loses it — the
   inconsistency FEAT-3060 was filed to remove, preserved in three places.
3. `LL_AUTOMATION_PROFILE` telemetry under-reports `ll-auto` activity.

## Proposed Solution

Pass `automation_profile="ll-auto"` at `issue_manager.py:826`, `:893`, and
`:1089`, matching `:1237` and `:1425`.

Note `:826` and `:893` reach `subprocess_utils.run_claude_command()` directly
rather than through the local `issue_manager.run_claude_command()` wrapper
(`:139-218`) — check which signature each actually calls before threading.

### Open Question

Whether `decide-issue`'s parallel `ll:codebase-pattern-finder` agents
(`skills/decide-issue/SKILL.md:335`) are affected. They specify
`run_in_background: false` and wait synchronously, so they should be unaffected
by FEAT-3078's flag — confirm rather than assume, since fixing `:1089` is what
first brings that skill under the flag.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Call-site routing resolved**: The issue's note ("check which signature each actually calls before threading") is resolved — all three broken sites (`:826`, `:893`, `:1089`) call the module-local `run_claude_command()` wrapper (`issue_manager.py:139`), not `subprocess_utils.run_claude_command()` directly. The wrapper already accepts `automation_profile` at its signature (line 151) and forwards it at line 217. The fix is purely additive: pass `automation_profile="ll-auto"` at each of the three sites, matching `:1237` and `:1425`.
- **Open Question resolved — decide-issue parallel agents**: The `ll:codebase-pattern-finder` agents spawned by `skills/decide-issue/SKILL.md:335` are in-process Claude Code Agent-tool subagent spawns (not `claude -p` subprocesses via `run_claude_command`). They specify `run_in_background: false` and are awaited synchronously in-turn. Once `:1089` is fixed (passing `automation_profile="ll-auto"`), the decide-issue subprocess will carry `LL_AUTOMATION=1` and its in-process subagents will inherit it. They are structurally unaffected by FEAT-3078's `disable_background_tasks` gate regardless — they are not `claude -p` children and do not receive env flags via `build_streaming`.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **BUG-3058 precedent**: The same class of defect — an `automation_profile` omission at a `process_issue_inplace` subprocess site became a bug after ENH-3081's clear-branch semantic change. Fixed by adding `automation_profile="ll-auto"` at the Phase 2 implement call site (`issue_manager.py:1237`), with its rationale comment at `:1230-1236`. The three sites in this issue are the recurrence of the same omission pattern.
- **Call chain confirmed**: All five call sites (`:826`, `:893`, `:1089`, `:1237`, `:1425`) route through the module-local `run_claude_command()` wrapper (`issue_manager.py:139`), not `subprocess_utils.run_claude_command()` directly. The wrapper already accepts and forwards `automation_profile` at line 217. The Proposed Solution's caution about checking which signature each calls is resolved — all three broken sites already call a signature that accepts the kwarg.
- **`worker_pool.py` omission (out of scope)**: `scripts/little_loops/parallel/worker_pool.py:_run_claude_command` (`:885-934`) calls `_run_claude_base` without `automation_profile` — the same omission pattern for the `ll-parallel` driver. Not covered by BUG-3093 (scoped to `ll-auto`/`issue_manager.py`), but the implementer should be aware it exists.
- **`build_blocking_json`/`build_detached` surface**: These `HostRunner` methods (`host_runner.py:371-400`, `:410-421`) do not accept `automation_profile` at all and build their own env dictionaries without `LL_AUTOMATION`. Spawn sites using these methods (e.g., `runner_spec.py:290`, `fsm/evaluators.py:1120`, `parallel/worker_pool.py:805`) are on a different spawn surface that structurally cannot carry automation-profile threading today.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/ready_issue.py` — `run_ready_issue_with_retry` re-invokes the same `run` callable (`_run_ready`) on UNKNOWN-verdict retries at `ready_issue.py:123`, so the `:826` fix automatically covers the retry child too (a hidden fifth site, not explicitly listed in the issue) [Agent 1/2 finding]
- `scripts/little_loops/cli/sprint/run.py` — calls `process_issue_inplace` directly at `:75` and `:839`; after the fix ll-sprint's Phase 1 ready/decide children carry `LL_AUTOMATION=1`, consistent with its already-profiled implement child. Behavior note, not a code change — ll-sprint's own `_run_claude_command` (`parallel/worker_pool.py:885-934`) remains out of scope [Agent 2 finding]
- `commands/ready-issue.md:132` — the ready-issue child's `ll-history-context {{issue_id}}` call is pruned once the child carries `LL_AUTOMATION=1` (`cli/history_context.py:206`, `automation_pruning.enabled` defaults true), so the "Historical Concerns" validation section loses its input under ll-auto — the same tradeoff `manage-issue` already lives under [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py:2184` (`test_forwards_on_usage_detailed_to_ready_issue_call`) — extend to assert `automation_profile == "ll-auto"` on the Phase 1 ready call (covers `:826`) [Agent 3 finding]
- `scripts/tests/test_issue_manager.py:2219` (`test_fallback_ready_issue_failure_returns_error`) or `:443` (`test_manage_issue_uses_path_after_fallback`) — assert the fallback retry call's `automation_profile == "ll-auto"` (covers `:893`) [Agent 3 finding]
- `scripts/tests/test_issue_manager.py:4713` (`test_decide_issue_invoked_when_decision_needed`) — extend to assert `automation_profile == "ll-auto"` on the decide call (covers `:1089`) [Agent 3 finding]
- AC 2's regression test should be three phase-level drives of `process_issue_inplace` (no narrow-unit seam exists for the ready/decide sites), capturing `kwargs.get("automation_profile")` in a `run_claude_command` side_effect like `test_forwards_automation_profile_to_subprocess` (`:1390-1412`). No existing test asserts exact kwargs on `run_claude_command`, so nothing breaks from the added kwarg [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2626-2658` — the `issue_manager`-local `run_claude_command` doc signature omits `automation_profile` (pre-existing drift on the touched function, predates this issue; optionally sync while implementing) [Agent 2 finding]
- `.issues/features/P3-FEAT-3077-decide-carve-out-policy-for-disable-background-tasks.md:101-104` — its enumeration of profile-carrying sites (`issue_manager.py:1213,1401`) goes stale once BUG-3093 makes it five; update when BUG-3093 lands [Agent 2 finding]

## Program Design

### Types
N/A — no new data types; three call sites gain an existing keyword argument.

### Signatures
No signature changes — both already accept the parameter; this issue only passes it.

- `run_claude_command(command: str, logger, *, timeout: int | None = None, stream_output: bool = False, idle_timeout: float | None = None, automation_profile: str | None = None) -> subprocess.CompletedProcess[str]` — `subprocess_utils.py:320`, unchanged.
- `_apply_automation_env(env: dict[str, str], automation_profile: str | None) -> None` — `host_runner.py:1547`, unchanged.

### Call Path
`process_issue_inplace` → `_run_ready` (`:826`) / ready-retry (`:893`) /
decide (`:1089`) → `run_claude_command` → `resolve_host().build_streaming()` →
`_apply_automation_env()` (`host_runner.py:1547`), which currently takes the
`else` branch and writes `LL_AUTOMATION=""`.

### Decision Rules
- `automation_profile="ll-auto"` is the correct value at all three sites — same
  run, same driver, same profile as `:1237`/`:1425`. No new profile name.
- Do not "fix" this by removing ENH-3081's `else` branch: clearing an inherited
  value is correct for genuine non-automation spawns. The defect is the call
  sites' silence, not the helper's semantics.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Pass `automation_profile="ll-auto"` at `issue_manager.py:826` (`_run_ready`), `:893` (ready fallback retry), and `:1089` (decide-issue) — the three sites pass no profile today; the module-local wrapper (`issue_manager.py:139`) already accepts/forwards the kwarg.
- Note the `:826` fix also covers `run_ready_issue_with_retry`'s UNKNOWN-verdict retry re-invocation (`ready_issue.py:123`), which reuses the same `_run_ready` callable.
- Extend the three phase-level tests listed in the Integration Map `### Tests` subsection to assert `automation_profile == "ll-auto"`, and add the AC 2 phase-level regression test.
- Update `.issues/features/P3-FEAT-3077-decide-carve-out-policy-for-disable-background-tasks.md` — the profile-carrying-site enumeration (`issue_manager.py:1213,1401`) becomes 2 → 5 sites.
- Optionally sync `docs/reference/API.md` — the `issue_manager`-local `run_claude_command` doc signature block (`:2626-2658`) to include `automation_profile`.

## Acceptance Criteria

1. All five `run_claude_command()` call sites in `process_issue_inplace` declare
   `automation_profile="ll-auto"`.
2. A test asserts the Phase 1 / retry / decide subprocesses receive
   `LL_AUTOMATION=1`, mirroring
   `scripts/tests/test_issue_manager.py:1390-1435`
   (`test_forwards_automation_profile_to_subprocess`).
3. `python -m pytest scripts/tests/` passes.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/host_runner.py:1547-1564` | `_apply_automation_env()`, the inherit-vs-clear semantics |
| `scripts/tests/test_host_runner.py:62-82` | ENH-3081's own regression test for the clear branch |
| `.issues/features/P3-FEAT-3078-thread-disable-background-tasks-config-flag-through-host-runner.md` | Blocked-by consumer of this fix |


## Session Log
- `/ll:confidence-check` - 2026-08-07T21:19:17 - `6d826167-8397-4056-a786-b172be706357.jsonl`
- `/ll:verify-issues` - 2026-08-07T21:16:24 - `77f825ac-c931-4911-95a5-cc391c8d5be4.jsonl`
- `/ll:wire-issue` - 2026-08-07T21:14:31 - `0c541e46-ca5a-4956-958d-0371db51651b.jsonl`
- `/ll:refine-issue` - 2026-08-07T21:03:49 - `74d06e2c-50d1-4334-8131-0e7076c3754a.jsonl`
