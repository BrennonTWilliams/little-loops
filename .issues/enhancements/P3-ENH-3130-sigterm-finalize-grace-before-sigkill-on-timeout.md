---
id: ENH-3130
status: done
priority: P3
captured_at: '2026-08-09T05:58:12Z'
completed_at: '2026-08-10T06:50:37Z'
discovered_date: 2026-08-09
discovered_by: capture-issue
relates_to:
- ENH-3129
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 69
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 18
---

# ENH-3130: Give the automation timeout kill a SIGTERM finalize grace before SIGKILL

## Summary

When a wall-clock or idle timeout fires, `run_claude_command` sends an
immediate `SIGKILL` to the whole process group. An agent that is seconds from
finalizing gets no chance to land its work. Send `SIGTERM` first, allow a
bounded grace window for the host CLI to wind down, and escalate to `SIGKILL`
only if it does not exit.

## Current Behavior

`_kill_process_group` (`scripts/little_loops/subprocess_utils.py:313-317`) is
unconditionally lethal:

```python
try:
    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
except (ProcessLookupError, PermissionError, AttributeError):
    process.kill()
```

Both timeout paths call it directly (`subprocess_utils.py:475` wall-clock,
`:486` idle) and then `process.wait(timeout=10)`. That 10-second wait is only
*reaping* an already-SIGKILLed process — it is not a grace period, and nothing
can run during it. There is no `SIGTERM` anywhere in the path.

This is inconsistent with the clean-exit path, which already has a generous
wind-down: `post_stream_close_grace_seconds` (default 300,
`subprocess_utils.py:604`) exists specifically so in-flight work can finish
after the streams close (BUG-2718).

Observed consequence (FEAT-3078): the agent committed at `00:35:36`, the
SIGKILL landed at `00:35:51`. It happened to finish first — 15 seconds the
other way and the work would have been lost mid-write.

## Expected Behavior

On timeout:

1. `SIGTERM` the process group.
2. Wait up to a configurable grace window for a clean exit.
3. `SIGKILL` the group only if still alive after the window.
4. `subprocess.TimeoutExpired` is still raised either way, so callers —
   including the BUG-3131 verification in `issue_manager.py`'s handler — are
   unchanged.

## Motivation

The timeout is a blunt instrument applied at an arbitrary instant. Killing
mid-`git commit` or mid-file-write risks a genuinely corrupted working tree,
which is strictly worse than the run simply taking longer. A grace window
converts most timeout kills from "work destroyed" into "work landed, then
stopped" — and it composes with the BUG-3131 handler fix, which can only
detect a *completed* lifecycle. Making completion more likely to happen is the
other half of that fix.

## Proposed Solution

Give `_kill_process_group` an escalation parameter rather than adding a second
kill helper:

```python
def _kill_process_group(process, grace_seconds: float = 0.0) -> None:
    """SIGTERM the group, then SIGKILL after grace_seconds if still alive.

    grace_seconds=0 preserves the historical immediate-SIGKILL behavior for
    callers that need it.
    """
```

Both timeout call sites pass the configured grace; any other caller keeps the
default and is unaffected.

Add `automation.timeout_kill_grace_seconds` to the schema (suggested default
**30** — long enough for a commit and a lifecycle write, short enough not to
meaningfully extend a run), threaded to `run_claude_command` alongside the
existing `post_stream_close_grace_seconds` parameter (`subprocess_utils.py:337`).

**Caveat worth verifying during implementation**: whether the host CLI
(`claude`) actually handles `SIGTERM` gracefully — flushes, finishes the
in-flight tool call, exits — or just dies. If it dies on `SIGTERM` the same
way, the grace window buys nothing and the issue should be closed with that
finding recorded. A spike against the real binary is the cheap first step
(see `/ll:spike`). Note also that `SIGTERM` goes to the whole group, so any
tool subprocess the agent spawned receives it too.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `_kill_process_group` and the
  two timeout call sites at `:475` and `:486`
- `scripts/little_loops/config-schema.json` — `automation` block
- `scripts/little_loops/config/automation.py` — dataclass + `from_dict`
- `scripts/little_loops/config/core.py` — `to_dict` serializer

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/types.py` — `ParallelConfig` dataclass
  (`:353-437`) is the actual config source for the `ll-parallel`/`ll-sprint`
  worker-pool path (`worker_pool.py`'s `timeout=self.parallel_config.timeout_per_issue`
  / `idle_timeout=self.parallel_config.idle_timeout_per_issue`), and it has no
  `post_stream_close_grace_seconds` or `timeout_kill_grace_seconds` field at
  all — not in the dataclass fields, `to_dict()` (`:488-502`), or its
  construction path. Threading grace into the parallel/worktree path requires
  a new field here, not just on `config/automation.py::AutomationConfig`
  [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — passes automation timeouts through
- `scripts/little_loops/parallel/worker_pool.py` — `ll-parallel`/`ll-sprint`
  share `run_claude_command`; confirm they get sane behavior or an explicit
  default
- any other `_kill_process_group` caller (grep before changing the signature)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:347, :528, :835, :908, :1108, :1439` —
  exact call sites of the module-local `run_claude_command` wrapper; each
  passes `idle_timeout=config.automation.idle_timeout_seconds` but no grace
  param, so each needs `timeout_kill_grace_seconds=...` added alongside
  [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py:2801` (`FSMExecutor::_run_baseline_arm`)
  — calls `run_claude_command` directly, does not thread any grace value
  [Agent 1 finding]
- `scripts/little_loops/fsm/runners.py:189` (`DefaultActionRunner::run`, slash
  command path) — calls `run_claude_command` directly, does not thread any
  grace value [Agent 1 finding]
- `scripts/little_loops/runner_spec.py:144, :177` (`_run_skill`) — calls
  `run_claude_command` directly, does not thread any grace value
  [Agent 1 finding]
- `scripts/little_loops/config/automation.py` —
  `ParallelAutomationConfig.from_dict` (`:105-119`) composes a `base:
  AutomationConfig` but does not forward `post_stream_close_grace_seconds`
  into it; a new `timeout_kill_grace_seconds` field would inherit the same
  drop unless this method is also updated [Agent 2 finding]
- `scripts/little_loops/cli/auto.py:80-81` — existing precedent for a CLI flag
  overriding an `automation.*` config key before a run (`idle_timeout`); no
  equivalent flag is required by this issue's Proposed Solution, noted only
  as the pattern to follow if one is added later [Agent 2 finding]

### Similar Patterns
- `post_stream_close_grace_seconds` (`subprocess_utils.py:337`, `:604`) — the
  existing grace-window parameter to model naming and threading on

### Tests
- `scripts/tests/test_subprocess_utils.py` — signal-order assertions
- `scripts/tests/test_feat3033_idle_timeout.py` — idle path must escalate too
- `scripts/tests/test_fsm_signal_integration.py` — check for interaction

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_utils.py` — beyond the wall-clock/idle
  signal-order tests, these will also break because they assert a single
  unconditional `SIGKILL` call with no SIGTERM stage:
  `test_falls_back_to_process_kill_on_process_lookup_error` (`:2725-2751`),
  `test_falls_back_to_process_kill_on_permission_error` (`:2753-2780`),
  `test_falls_back_to_process_kill_when_killpg_absent` (`:2782+`), and the
  post-stream-close fallback test (`~:2700-2723`, the third `_kill_process_group`
  call site at `:611`) [Agent 3 finding]
- `scripts/tests/test_config.py` — round-trip precedent to replicate for
  `timeout_kill_grace_seconds`: `TestAutomationConfig.test_from_dict_with_all_fields`
  / `test_from_dict_with_defaults` (`:320-354`) and
  `TestBRConfig.test_to_dict_automation_post_stream_close_grace_seconds`
  (`:923-934`, cites BUG-2718) [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — no existing test covers
  `automation.post_stream_close_grace_seconds`/`idle_timeout_seconds`/
  `timeout_seconds`; add a schema-conformance test for the new
  `timeout_kill_grace_seconds` key following the `additionalProperties: false`
  guard pattern in `test_observability_in_schema` (`:31-52`) [Agent 3 finding]

### Documentation
- `docs/reference/CONFIGURATION.md` — new key
- `docs/development/TROUBLESHOOTING.md` — timeout-kill behavior

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### run_claude_command` section (`~:2805-2844`)
  documents the `issue_manager`-local wrapper's signature and includes a
  "Process-group cleanup" paragraph (`~:2844`) stating cleanup "sends SIGKILL
  to the entire process group" on timeout — becomes inaccurate once
  SIGTERM-first escalation lands and needs rewriting [Agent 2 finding]
- `docs/reference/API.md` — `### AutomationConfig` section (`~:495-510`) is a
  hand-maintained mirror of the `config/automation.py` dataclass fields
  (already lists `post_stream_close_grace_seconds` at `:504`); needs a
  matching line added for `timeout_kill_grace_seconds` [Agent 2 finding]

### Configuration
- `scripts/little_loops/config-schema.json`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Third, unlisted call site**: `_kill_process_group` is also called at `subprocess_utils.py:611`, inside `run_claude_command`'s clean-exit post-stream-close path (the `except subprocess.TimeoutExpired:` handler after `process.wait(timeout=post_stream_close_grace_seconds)` fires, `:596-618`). This site is not gated by `timeout`/`idle_timeout` and would stay behaviorally unchanged under a `grace_seconds=0.0` default, since the Proposed Solution only threads the new config into the two timeout branches (`:475`, `:486`) — confirm this site is intentionally left out of scope.
- **Independent `_kill_process_group` callers not routed through `run_claude_command`** (so a config-only fix at the two timeout branches does not reach them): `scripts/little_loops/mcp_call.py:248, 257, 287, 320, 330` (5 sites in MCP server spawn/handshake/cleanup), `scripts/little_loops/runner_spec.py:260` (`_run_cmd`, CMD-runner FSM action), `scripts/little_loops/fsm/executor.py:2209` (`FSMExecutor::_run_subprocess`, MCP-type FSM action), `scripts/little_loops/fsm/runners.py:334` (`DefaultActionRunner::run`, CMD-type FSM action). All are source-compatible with a `grace_seconds` parameter added at `_kill_process_group`'s current single-argument signature, but none gain the SIGTERM grace unless separately updated to pass a nonzero value — the issue's scope as written only reaches the two `run_claude_command` timeout branches.
- **`post_stream_close_grace_seconds` threading gap** (the parameter this issue models its own config key on): no call site in the codebase actually reads `AutomationConfig.post_stream_close_grace_seconds` and forwards it into `run_claude_command(post_stream_close_grace_seconds=...)` — `issue_manager.py`'s wrapper (`:139-153`) forwards `idle_timeout` but not this key, and `worker_pool.py`'s `_run_claude_command` (`:885-940`) omits it too, so both always ride the hardcoded `300` function default rather than any config override. A new `timeout_kill_grace_seconds` key threaded the same way would inherit this same gap (schema/dataclass/serializer complete, but never read at a call site) unless those two wrapper functions are also updated to forward it.
- **Existing two-stage (SIGTERM-then-SIGKILL) precedents already in this codebase**, independent of `_kill_process_group` and each other — worth reconciling with rather than inventing a third shape:
  - `scripts/little_loops/cli/loop/lifecycle.py:88-114` (`_kill_with_timeout`) — process-group-based (`os.killpg`/`os.getpgid`, same fallback shape as `_kill_process_group`), escalates via a polled `time.sleep(1)` loop (fixed 10 iterations).
  - `scripts/little_loops/parallel/worker_pool.py:255-264` (`WorkerPool.terminate_all_processes`) — `Popen.terminate()`/`.wait(timeout=5)`/`.kill()` directly (not process-group signaling), single blocking wait rather than a poll loop.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Test patterns for asserting signal order**, from the two existing two-stage-kill implementations — neither uses a strict call-order assertion on `call_args_list`; order is established indirectly:
  - Blocking-wait style (matches `worker_pool.py`'s implementation): `scripts/tests/test_worker_pool.py:332-346` (`test_terminate_all_processes_kills_if_sigterm_fails`) — mocks `process.wait.side_effect = [subprocess.TimeoutExpired(...), None]`, then asserts `.terminate()` and `.kill()` were each called once.
  - Poll-loop style (matches `lifecycle.py`'s implementation): `scripts/tests/test_cli_loop_lifecycle.py:438-472` and `:474-507` — filters `mock_killpg.call_args_list` by signal (`c[0][1] == signal.SIGTERM` / `signal.SIGKILL`) to assert presence/absence of each stage, combined with a `_process_alive` mock driven by a `side_effect` sequence and `patch(...time.sleep)` to avoid real sleeping.
  - `scripts/tests/test_subprocess_utils.py` currently has no signal-order test — its existing kill-related assertions (e.g. `:556-578`, `:2665-2783`) all assert a single `mock_killpg.assert_called_once_with(pid, signal.SIGKILL)`, consistent with today's unconditional-SIGKILL implementation and needing new escalation-specific assertions.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Stale file reference**: `### Dependent Files` cites `scripts/little_loops/worker_pool.py`, but no such path exists — the module is at `scripts/little_loops/parallel/worker_pool.py` (`WorkerPool._run_claude_command`, `:885-940`). Same threading gap noted above applies there: it omits `post_stream_close_grace_seconds` from its `_run_claude_base(...)` call.

## Program Design

### Deviations

_Added by `/ll:manage-issue` — 2026-08-10:_

- The FSM/runner_spec wiring (`fsm/executor.py::_run_baseline_arm`,
  `fsm/runners.py::DefaultActionRunner.run`, `runner_spec.py::_run_skill`)
  gained a source-compatible `timeout_kill_grace_seconds` parameter (default
  `0.0`) threaded down to `run_claude_command`, matching the existing
  per-call parameter-passing precedent used by sibling values
  (`automation_profile`, `disable_background_tasks`, `idle_timeout`) in the
  same functions. It is **not** wired to a live `AutomationConfig` value:
  none of these three call sites had access to the global `BRConfig`/
  `AutomationConfig` object before this change (FSM timeouts are sourced
  from the loop YAML's `state.timeout`/`fsm.default_timeout`, not
  `.ll/ll-config.json`'s `automation` block — confirmed no
  `post_stream_close_grace_seconds` threading exists there either, the
  precedent this issue models itself on). Wiring a live value would require
  either injecting global config into the hot per-action path (I/O per
  action, architecturally inconsistent with the FSM's loop-scoped timeout
  model) or adding new FSM-loop YAML schema surface for a
  `default_timeout_kill_grace_seconds` field — both judged out of proportion
  for this issue's stated scope (Decision Rules: "no new gap kind, gate,
  keyword list, or threshold"). `runner_spec.py::_run_skill` reads its value
  from `spec.args.get("timeout_kill_grace_seconds", 0.0)`, so a future CLI
  (`ll-harness`/`ll-action`) can opt in by populating that args key without
  further plumbing changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

### Signatures

- `_kill_process_group(process: subprocess.Popen, grace_seconds: float = 0.0) -> None` — proposed signature; current signature (`subprocess_utils.py:307-317`) takes only `process` and unconditionally sends `SIGKILL` via `os.killpg`/`os.getpgid`, falling back to `process.kill()` on `ProcessLookupError`, `PermissionError`, or `AttributeError`.
- `run_claude_command`'s current full parameter list (`subprocess_utils.py:320-342`): `command, timeout=3600, working_dir=None, stream_callback=None, on_process_start=None, on_process_end=None, idle_timeout=0, on_model_detected=None, on_usage=None, on_usage_detailed=None, agent=None, tools=None, resume_session=False, model=None, automation_profile=None, disable_background_tasks=False, post_stream_close_grace_seconds=300, on_result_seen=None, on_session_id_detected=None, on_tool_call=None, workspace_root=None`. A new `timeout_kill_grace_seconds` parameter sits in this same keyword list.
- Precedent parameter it's modeled on: `post_stream_close_grace_seconds` (`subprocess_utils.py:337`, schema `config-schema.json:275-280`, dataclass `config/automation.py:22` and `:39`, serializer `config/core.py:732`) — schema-enforces `minimum: 30` (0 is not a valid value for this key, unlike `idle_timeout_seconds` which documents 0-as-disable).

### Call Path

Wall-clock/idle timeout branches (`subprocess_utils.py:471-494`, inside `run_claude_command`'s `while sel.get_map():` read loop) -> `_kill_process_group(process, grace_seconds=...)` -> `process.wait(timeout=10)` (reap only) -> `raise subprocess.TimeoutExpired(...)` (unchanged either way) -> caught by callers that read `exc.output == "idle_timeout"` to distinguish kill kind (`fsm/runners.py:211`, `issue_manager.py:2031`) -> `issue_manager.py`'s BUG-3131 verification handler (`:2006-2058`) checks whether the issue was already finalized before overwriting `result` with success.

Config threading (if using the `post_stream_close_grace_seconds` precedent literally): schema (`config-schema.json` `automation` block) -> `AutomationConfig` dataclass (`config/automation.py`) -> `to_dict` (`config/core.py:732`) -> `run_claude_command` parameter default. Note this precedent is schema/dataclass/serializer-complete but never read at a call site today — neither `issue_manager.py`'s wrapper (`:139-153`) nor `worker_pool.py`'s `_run_claude_command` (`:885-940`) forwards `post_stream_close_grace_seconds` from config, so both always use the function's hardcoded default rather than a config override. A new `timeout_kill_grace_seconds` key threaded the same way would need those two wrapper functions updated to actually forward it, or it inherits the same dead-config gap.

### Decision Rules

N/A — no new gap kind, gate, keyword list, or threshold; this is a signal-escalation change to an existing kill path, not new classification logic.

## Implementation Steps

1. Spike first: does `claude` exit cleanly on `SIGTERM`? If not, stop and close
   this issue with the finding.
2. Add the `grace_seconds` parameter to `_kill_process_group`, defaulting to 0
   so existing callers are byte-identical.
3. Thread `automation.timeout_kill_grace_seconds` through schema, dataclass,
   serializer, and `run_claude_command`.
4. Pass it at both timeout call sites.
5. Tests asserting SIGTERM-then-SIGKILL ordering and that the escalation
   actually fires when the child ignores SIGTERM.
6. Docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Thread `timeout_kill_grace_seconds` through `issue_manager.py`'s
  `run_claude_command` wrapper and its six call sites (`:347, :528, :835,
  :908, :1108, :1439`)
- Thread it through `fsm/executor.py:_run_baseline_arm` (`:2801`),
  `fsm/runners.py:DefaultActionRunner.run` (`:189`), and
  `runner_spec.py:_run_skill` (`:144, :177`) — all call `run_claude_command`
  directly without a grace param today
- Add a `timeout_kill_grace_seconds` field to `parallel/types.py::ParallelConfig`
  and thread it through `worker_pool.py`'s `_run_claude_command`, since the
  `ll-parallel`/`ll-sprint` path sources its config from `ParallelConfig`, not
  `AutomationConfig`
- Fix `config/automation.py::ParallelAutomationConfig.from_dict` (`:105-119`)
  to forward grace fields into the composed `AutomationConfig`, or the new key
  is dropped on that path too
- Update `docs/reference/API.md`'s `run_claude_command` "Process-group
  cleanup" paragraph and `AutomationConfig` field mirror
- Update/add tests: the `test_subprocess_utils.py` fallback-kill tests that
  assert single unconditional SIGKILL, the `test_config.py` round-trip tests
  modeled on `post_stream_close_grace_seconds`, and a new
  `test_config_schema.py` conformance test for the key

## Impact

- **Risk**: Medium. Touches the kill path shared by every automation driver; a
  bug here means processes that never die. The `grace_seconds=0` default keeps
  the blast radius to the two call sites that opt in.
- **Benefit**: Fewer corrupted working trees; more timeout kills that leave
  committed, verifiable work behind.

## Scope Boundaries

- Out of scope: the third `_kill_process_group` call site at
  `subprocess_utils.py:611` (the clean-exit post-stream-close path) keeps its
  immediate-kill behavior — it is not gated by `timeout`/`idle_timeout` and the
  Proposed Solution only threads grace into the two timeout branches.
- Out of scope: the independent `_kill_process_group` callers not routed
  through `run_claude_command` — `mcp_call.py` (5 sites), `runner_spec.py`'s
  `_run_cmd`, `fsm/executor.py`'s `_run_subprocess`, and `fsm/runners.py`'s
  CMD-type action — gain a source-compatible `grace_seconds` parameter but do
  not receive a nonzero grace value in this issue.
- Out of scope: reconciling this new escalation shape with the two existing
  two-stage-kill implementations (`cli/loop/lifecycle.py`'s
  `_kill_with_timeout`, `parallel/worker_pool.py`'s
  `terminate_all_processes`) — noted as precedent, not unified.
- Out of scope: a CLI flag to override `timeout_kill_grace_seconds` per-run
  (the `cli/auto.py:80-81` `idle_timeout` pattern is noted only as a
  follow-up precedent if one is added later).
- In scope: fixing the `post_stream_close_grace_seconds`-style dead-config gap
  for the *new* `timeout_kill_grace_seconds` key specifically — i.e. the
  wrapper functions (`issue_manager.py`, `worker_pool.py`) must actually
  forward it, not just declare it in schema/dataclass.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CONFIGURATION.md` | Documents the new `automation.*` grace key |
| `docs/development/TROUBLESHOOTING.md` | Timeout and hung-process guidance |
| `docs/reference/API.md` | `little_loops.subprocess_utils` module reference |

## Status

- **Current**: open
- **Blockers**: None

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-10_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Outcome Risk Factors
- Core premise is unproven: the whole fix hinges on `claude` actually winding down cleanly on `SIGTERM` rather than dying the same as `SIGKILL`. Implementation Steps sequences a spike first and correctly stops/closes the issue if that assumption fails, but that means the entire outcome is gated on one untested external-CLI behavior.
- Broad enumeration across many sites: the wiring pass identified 10+ call sites across `issue_manager.py` (6 sites), `fsm/executor.py`, `fsm/runners.py`, `runner_spec.py`, `parallel/types.py`, and `worker_pool.py` that need the new grace parameter threaded through to actually take effect — a config-only fix at the two `subprocess_utils.py` timeout branches would silently not reach the `ll-parallel`/`ll-sprint` path or the FSM action runners. The `post_stream_close_grace_seconds` precedent this issue models itself on has exactly this failure mode already (schema/dataclass complete, never forwarded at two wrapper call sites) — same class of gap could recur here without care.

## Session Log
- `/ll:manage-issue` - 2026-08-10T06:50:14 - `1259f5ba-5f93-470c-a585-23c94cb7dbd8.jsonl`
- `/ll:ready-issue` - 2026-08-10T06:09:59 - `b9dc77c4-e003-4263-83b0-e374f8df0e8a.jsonl`
- `/ll:confidence-check` - 2026-08-10T06:07:16 - `3c39311b-8d57-4438-bea7-0c282337c8e4.jsonl`
- `/ll:verify-issues` - 2026-08-10T06:04:45 - `8f34e6e4-a4cf-4b3a-afbe-2f422e5c2a53.jsonl`
- `/ll:wire-issue` - 2026-08-10T06:02:24 - `da400e40-485c-4efd-a7db-91f78a758d15.jsonl`
- `/ll:refine-issue` - 2026-08-10T05:52:30 - `83d5b0c3-c363-4019-af7e-76193e7e90bc.jsonl`
- `/ll:capture-issue` - 2026-08-09T05:59:57 - `ce451e9a-4952-45a2-828c-106f17467622.jsonl`
