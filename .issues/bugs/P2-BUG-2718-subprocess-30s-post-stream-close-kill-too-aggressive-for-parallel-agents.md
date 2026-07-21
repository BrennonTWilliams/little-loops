---
id: BUG-2718
type: BUG
title: run_claude_command's fixed 30s post-stream-close kill fires while legitimate
  synchronous parallel subagent work is still in flight
priority: P2
status: done
captured_at: '2026-07-21T05:20:00Z'
completed_at: '2026-07-21T07:04:17Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
labels:
- subprocess
- automation
- hardening
relates_to:
- ENH-2717
- ENH-1999
- ENH-2712
confidence_score: 92
outcome_confidence: 78
score_complexity: 20
score_test_coverage: 21
score_ambiguity: 20
score_change_surface: 17
decision_needed: false
learning_tests_required:
- psutil
---

# BUG-2718: run_claude_command's fixed 30s post-stream-close kill fires while legitimate synchronous parallel subagent work is still in flight

## Summary

`run_claude_command` (`scripts/little_loops/subprocess_utils.py`) kills its child `claude` process if it doesn't exit within a **fixed 30 seconds** after its stdout/stderr streams close (`subprocess_utils.py:511-518`). This constant assumes the main session should self-terminate almost immediately once its own output stream is done. That assumption breaks for any skill that spawns multiple **synchronous, blocking** subagents in parallel (the documented `Agent` tool pattern: "spawn multiple in a single message... wait for all to complete") — legitimate multi-minute background work can still be in flight when the parent's own stdout/stderr close, and the fixed 30s grace force-kills the whole process group (`_kill_process_group`, SIGKILL) before that work finishes, silently discarding it.

This is the root cause behind [[ENH-2717]]: `/ll:decide-issue ENH-2712 --auto` was killed (`exit -9`) mid-turn while waiting on two parallel `codebase-pattern-finder` evidence-gathering agents (explicitly spawned with `run_in_background: false` per `skills/decide-issue/SKILL.md` Phase 4), losing the scoring work and leaving `decision_needed: true` unresolved. ENH-2717 only stops the FSM from compounding that loss with a redundant size-review call — it does not stop the kill itself from happening.

## Steps to Reproduce

1. Invoke a skill via `run_claude_command` (`scripts/little_loops/subprocess_utils.py`) whose prompt explicitly spawns two or more synchronous, blocking `Agent` tool calls in parallel — e.g. `/ll:decide-issue <ID> --auto`, whose `skills/decide-issue/SKILL.md` Phase 4 spawns two `codebase-pattern-finder` evidence-gathering agents with `run_in_background: false`.
2. Ensure at least one of those subagents takes noticeably longer than 30 seconds of wall-clock time to complete real multi-file codebase investigation (several tool calls spanning minutes).
3. Observe: the child `claude` process's own stdout/stderr streams close (or a stream-json `result` event fires early per the `subprocess_utils.py:389-395` comment) while the spawned subagents are still running.
4. Observe: `process.wait(timeout=30)` (`subprocess_utils.py:511-518`) expires, logging `Process <pid> did not exit within 30s after streams closed, killing`, followed by `_kill_process_group` SIGKILL and `exit: -9` — force-killing the whole process group, including the still-running subagents, discarding their in-flight work.

Reproduced in `.loops/.running/autodev-20260720T235236.log` (`[8/500] run_decide`), where the assistant's last narrated line was "I'm waiting on the second evidence agent (Option B) to finish before scoring both options" immediately before the kill fired.

## Current Behavior

In `run_claude_command`'s read loop (`subprocess_utils.py:389-509`): once both stdout and stderr hit EOF (or a stream-json `result` event breaks the loop early — the design intentionally does this because background Workflow/Task children can hold inherited FDs open forever, see the comment at `subprocess_utils.py:389-395` and [[ENH-1999]]), the code calls `process.wait(timeout=30)`. If the process hasn't exited by then, it force-kills the entire process group via `os.killpg(..., SIGKILL)`.

Observed in `.loops/.running/autodev-20260720T235236.log` (`[8/500] run_decide`): the assistant's last narrated line was *"I'm waiting on the second evidence agent (Option B) to finish before scoring both options"* — synchronous work explicitly still pending — followed immediately by `Process 48056 did not exit within 30s after streams closed, killing` and `exit: -9`.

30 seconds is nowhere near enough for two parallel research subagents doing multi-file codebase investigation (each agent's own transcript in this run shows many tool calls spanning minutes). The fixed constant has no way to distinguish "process is genuinely hung/zombied" from "process is alive and doing real, synchronous, in-flight work."

## Expected Behavior

The post-stream-close grace period should not force-kill a process that is still doing legitimate work. At minimum:
- Don't apply a flat, short timer as the sole signal — check process/process-group liveness (e.g., whether the process group still has live children consuming CPU, via `psutil`) before killing, and only kill once the group is genuinely idle/exited or a much longer absolute cap is hit.
- If a liveness check is out of scope for now, raise the 30s constant substantially (e.g., to the order of minutes) for call sites known to invoke skills with the synchronous-parallel-agent pattern, since 30s directly contradicts the `Agent` tool's own documented usage guidance.

## Root Cause

`subprocess_utils.py:511-518`:

```python
try:
    process.wait(timeout=30)
except subprocess.TimeoutExpired:
    logger.warning(
        "Process %s did not exit within 30s after streams closed, killing",
        process.pid,
    )
    _kill_process_group(process)
```

The `30` is a hardcoded magic number with no config surface, no liveness awareness, and — per the log evidence above — actively fires against a documented, intended usage pattern (synchronous parallel `Agent` tool calls) rather than only against genuinely hung processes.

**Unresolved ambiguity worth instrumenting before the fix**: it's not yet certain from the log alone whether (a) the stream-json `result` event fired prematurely (turn ended from the CLI's perspective before the blocking Task/Agent tool calls returned — possibly a host-CLI-level issue outside this codebase's control) or (b) the read loop hit natural EOF on both pipes without a `result` event (suggesting something else closed the streams while the process was still alive and working). Add a debug-level log of the terminal stream-json event type (or "natural EOF, no result event") immediately before the `process.wait(30)` call, so the next occurrence can distinguish these cases conclusively.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed via `codebase-analyzer`: `result_seen` (`subprocess_utils.py:490,508-509`) is a local variable never logged, so the ambiguity above is real and currently undiagnosable from logs — nothing in the current code distinguishes the natural-EOF-while-alive path from the early `result`-event-break path before hitting `process.wait(timeout=30)` at `subprocess_utils.py:511-518`.
- Both exit paths (natural EOF at `subprocess_utils.py:398-509` and the `result_seen` break at lines 508-509) funnel into the identical post-loop `process.wait(timeout=30)` block — there is no branching today that could privilege one path with a longer grace period without first adding the diagnostic log this issue proposes.
- `_kill_process_group()` (`subprocess_utils.py:273-283`) always sends `SIGKILL` directly (no SIGTERM-first escalation) via `os.killpg(os.getpgid(pid), SIGKILL)`, relying on `start_new_session=True` (line 363) to target the whole process group. The only "grace" anywhere in `run_claude_command` after a kill decision is a second `process.wait(timeout=10)` reap-confirmation (lines 519-525), not a pre-kill SIGTERM step — any fix that adds liveness polling would need to decide whether to keep this SIGKILL-only mechanic or add an escalation.
- If the post-kill `process.wait(timeout=10)` also expires, `process.returncode` can still be `None`; the final `CompletedProcess` at `subprocess_utils.py:530-535` falls back to a literal `-9` in that case rather than reading it from the OS — worth preserving in any rewrite since callers (e.g. log-grep-based detection mentioned in Steps to Reproduce) rely on `-9` as the kill signal.

## Proposed Solution

1. Add the diagnostic logging above (terminal event type / EOF-without-result) so the next occurrence is conclusive rather than guesswork.
2. Replace (or supplement) the flat 30s `process.wait()` with a liveness-aware wait: poll `psutil.Process(process.pid).children(recursive=True)` (or process-group CPU-time delta) at short intervals up to a much longer absolute cap (e.g., 300s), only killing once the group is confirmed idle or the cap is hit.
3. If liveness polling is deemed too heavy for this call site, raise the flat constant to something compatible with the documented multi-agent pattern (minutes, not seconds) and note the tradeoff (a genuinely hung process now takes longer to reap).
4. Regression test: simulate a child that keeps a grandchild process alive and writing past the old 30s mark; assert it is not killed prematurely.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Steps 2 and 3 above are two distinct implementation paths without a committed choice. Codebase research on each:

**Option A**: Liveness-aware wait — poll `psutil.Process(process.pid).children(recursive=True)` (or process-group CPU-time delta) at short intervals up to a much longer absolute cap (e.g., 300s), only killing once the group is confirmed idle or the cap is hit. No existing precedent for `children(recursive=True)`/CPU-time polling in this codebase: the only current `psutil` usage (`scripts/little_loops/cli/loop/queue.py:88-113`, `_verify_queue_pid_identity()`) does PID-identity verification (`cmdline()`, `create_time()`), not children/liveness polling — this would be new infrastructure. `scripts/little_loops/fsm/host_guard.py` deliberately avoids `psutil` in favor of `vm_stat`/`/proc/meminfo` parsing, a relevant counter-example if a lighter-weight non-psutil probe is preferred instead.

**Option B**: Raise the flat 30s constant to something compatible with the documented multi-agent pattern (minutes, not seconds), optionally exposed as a config key.

> **Selected:** Option B — reuses the established 3-part config-promotion pattern (`AutomationConfig` + schema + `resolve_variable()`) with no new dependency on process-tree polling. This codebase already has an established 3-part pattern for promoting a subprocess timeout literal to a resolvable config key — `AutomationConfig.timeout_seconds`/`idle_timeout_seconds` (`scripts/little_loops/config/automation.py:13-36`) + matching `config-schema.json` entries (`scripts/little_loops/config-schema.json:263-309`) + exposure via `BRConfig.to_dict()`/`resolve_variable()` (`scripts/little_loops/config/core.py:623-626,863-885`) — a new `post_stream_close_grace_seconds`-style key would follow this exact shape, with `run_claude_command`'s signature (`subprocess_utils.py:286-302`) gaining a new parameter alongside the existing `timeout`/`idle_timeout` params, threaded from callers like `parallel/worker_pool.py:862,867` the same way those two already are.

**Recommended**: Option B for v1 — it reuses an established config-promotion pattern with no new dependency on process-tree polling, directly unblocks the `decide-issue`-style multi-agent workflows in Steps to Reproduce, and defers the higher-complexity psutil liveness approach (Option A) to a follow-on if a flat raised cap still proves insufficient in practice.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-21.

**Selected**: Option B — Raise the flat 30s constant via config

**Reasoning**: Option B reuses a 3-part config-promotion pattern (`AutomationConfig` dataclass field + `config-schema.json` entry + generic `resolve_variable()`/`to_dict()` exposure) that already repeats at least 3 times in this codebase, and `run_claude_command` already threads config-sourced `timeout`/`idle_timeout` params from 7 live call sites — a direct template for one more parameter of the same shape. Option A (psutil liveness polling) has zero precedent for the specific primitives it needs (`children(recursive=True)`/`cpu_times()` — confirmed absent via grep across `scripts/`), and `fsm/host_guard.py` shows this codebase deliberately avoids psutil for a closely related resource-probing need (memory pressure), preferring OS-text-file parsing instead.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (liveness polling) | 0/3 | 0/3 | 1/3 | 1/3 | 2/12 |
| Option B (raise constant via config) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: No existing `psutil` children/CPU-time polling anywhere in `scripts/`; the only existing psutil usage (`cli/loop/queue.py:88-113`) is a single-shot PID-identity check, not liveness polling, and `fsm/host_guard.py` explicitly avoids psutil for a similar need — this option is wholly new infrastructure with no test scaffolding for a live grandchild process.
- Option B: The 3-part config-promotion pattern (`config/automation.py:13-36` + `config-schema.json:263-309` + `config/core.py:623-631,863-885`) repeats 3+ times already, `run_claude_command` already threads config-sourced timeouts from 7 call sites, and `test_subprocess_utils.py::TestRunClaudeCommandWaitTimeout` already targets the exact block this option changes — though the FSM dispatch paths (`fsm/executor.py`, `fsm/runners.py`) use a divergent per-state fallback-chain convention that will need reconciling for full call-site coverage.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` (lines 286-536), specifically the post-stream-close wait/kill block at lines 511-525; add the diagnostic `result_seen` logging here too
- `scripts/little_loops/config/automation.py` — `AutomationConfig` dataclass (lines 13-36), if a new grace-period config key is added (Option B)
- `scripts/little_loops/config-schema.json` — `automation` block (lines 263-309), matching schema entry for the new key

### Dependent Files (Callers of `run_claude_command`)
- `scripts/little_loops/parallel/worker_pool.py:862,867` — passes `timeout`/`idle_timeout` from `self.parallel_config`; the clearest existing example of a config-sourced (not literal) caller a new grace-period parameter should follow
- `scripts/little_loops/fsm/executor.py`, `scripts/little_loops/fsm/runners.py` — FSM dispatch paths that invoke `run_claude_command`
- `scripts/little_loops/host_runner.py` — host CLI abstraction layer
- `scripts/little_loops/issue_manager.py`, `scripts/little_loops/workflow_sequence/__init__.py`, `scripts/little_loops/cli/generate_skill_descriptions.py`, `scripts/little_loops/cli/auto.py`, `scripts/little_loops/cli/parallel.py` — other direct call sites (17 total references found via grep for `run_claude_command(`)

### Similar Patterns
- `scripts/little_loops/cli/loop/queue.py:88-113` — `_verify_queue_pid_identity()`, the only existing `psutil` usage in the codebase (identity check via `cmdline()`/`create_time()`, not children/CPU liveness polling)
- `scripts/little_loops/fsm/concurrency.py:56,429` — `_process_alive(pid)`, a plain `os.kill(pid, 0)` liveness probe (non-psutil)
- `scripts/little_loops/config/automation.py:13-36` + `scripts/little_loops/config-schema.json:263-309` + `scripts/little_loops/config/core.py:623-626,863-885` — the 3-part config-promotion pattern (dataclass field + schema entry + `to_dict()`/`resolve_variable()` exposure) a new grace-period key should mirror

### Tests
- `scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandWaitTimeout` (lines 1222-1385) — existing coverage of the exact 30s wait/kill block, e.g. `test_kills_process_when_normal_wait_times_out` (mocks `wait.side_effect`, asserts `os.killpg` called with `SIGKILL`, asserts the `logger.warning` message) and `test_wait_has_timeout_on_normal_completion` (~line 1297, `mock_process.wait.assert_called_once_with(timeout=30)` — will need updating if the constant changes)
- `scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandTimeout` (lines 701-793) — wall-clock/idle-timeout tests using the same kill mechanics; useful pattern reference
- No existing test spawns a real subprocess with a slow-exiting grandchild — all current kill tests use `Mock()`/`io.StringIO` with monkeypatched `time.time`/`os.getpgid`/`os.killpg`. Step 4's regression test ("simulate a child that keeps a grandchild process alive") needs new test infrastructure, not just an extension of the existing mock pattern
- `scripts/tests/test_cli_loop_queue.py:426-492` — psutil-mock test pattern (`patch(".psutil.Process", ...)`) to model a new test after if Option A (liveness polling) is chosen instead

### Related Prior Issues
- `.issues/bugs/P2-BUG-2206-ll-loop-stop-orphaned-child-processes-survive-kill.md`, `P3-BUG-420-missing-timeout-on-process-wait-after-kill.md`, `P2-BUG-231-zombie-process-after-timeout-kill.md`, `P1-BUG-685-returncode-or-zero-masks-killed-process-as-success.md`, `P2-BUG-1381-subprocess-output-parser-silently-discards-result-events.md` — prior process-kill bugs in this same area worth checking for regressions once this fix lands

## Impact

- **Priority**: P2 — silently discards real, paid-for agent work (tokens + time) and produces incorrect downstream state (e.g., ENH-2712 was deferred as `low_readiness` when the real cause was an infrastructure kill, not a genuine readiness problem). Affects any skill following the documented parallel-`Agent` pattern, not just `decide-issue`.
- **Effort**: Small for the diagnostic logging; Medium for the liveness-aware wait.
- **Risk**: Low — the change only extends how long we wait before killing; it doesn't change kill mechanics for genuinely hung processes.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-21_

**Readiness Score**: 92/100 → GO
**Outcome Confidence**: 78/100 → HIGH

Re-assessed after `/ll:decide-issue` resolved the Proposed Solution's open design decision (Option B — raise the flat 30s constant via config — selected 2026-07-21, see Decision Rationale). All file:line claims in Root Cause, Codebase Research Findings, and Integration Map were re-verified directly against current `subprocess_utils.py`, `config/automation.py`, and `parallel/types.py` and remain accurate. No unresolved concerns remain.

## Resolution

Implemented Option B (raise the flat 30s constant via the established
config-promotion pattern):

- `scripts/little_loops/subprocess_utils.py` — added a `post_stream_close_grace_seconds: int = 300`
  parameter to `run_claude_command()`, replacing the hardcoded `process.wait(timeout=30)`
  in the post-stream-close block. Default raised 30s → 300s so the default behavior
  of every existing caller (17 call sites) is fixed without any caller changes.
  Added a debug-level log line immediately before the wait, recording whether the
  loop exited via the stream-json `result` event or natural EOF-without-result,
  resolving the diagnostic ambiguity called out in Root Cause.
- `scripts/little_loops/config/automation.py` — added `AutomationConfig.post_stream_close_grace_seconds`
  (default `300`) following the existing `timeout_seconds`/`idle_timeout_seconds` pattern.
- `scripts/little_loops/config-schema.json` — added the matching `automation.post_stream_close_grace_seconds`
  schema entry (`minimum: 30`).
- `scripts/little_loops/config/core.py` — exposed the new key via `BRConfig.to_dict()`
  so it resolves through `resolve_variable()` like the other automation timeouts.
- Docs updated: `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`.

**Scope note**: per the issue's "Files to Modify" list, this did not thread a
config-sourced override through all 17 `run_claude_command()` call sites (e.g.
`worker_pool.py`, `fsm/executor.py`) — the raised default alone fixes the
reported failure mode for every caller. Wiring an explicit override per call
site is deferred as a follow-on if 300s proves insufficient in practice.
Option A (psutil liveness polling) was not pursued per the Decision Rationale,
so the `psutil` learning-test requirement captured at intake is no longer
applicable to this issue's implementation.

Tests: extended `test_subprocess_utils.py::TestRunClaudeCommandWaitTimeout`
with a config-override test and a real-subprocess regression test (child
closes stdout/stderr but keeps running past the old 30s default; asserts no
kill within the new grace period). Updated the four existing assertions that
hardcoded `timeout=30` to the new `300` default. Added `AutomationConfig` and
`BRConfig.to_dict()` coverage in `test_config.py`. Full suite:
`python -m pytest scripts/tests/` → 15712 passed, 38 skipped.

## Session Log
- `/ll:manage-issue` - 2026-07-21T07:03:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0542e06b-277e-4576-829b-0ae2c6bd8e7b.jsonl`
- `/ll:confidence-check` - 2026-07-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f685efb4-34cf-40b7-9ea6-372f205909b1.jsonl`
- `/ll:decide-issue` - 2026-07-21T06:43:46 - `0c9c9ae5-8bff-40af-ad75-0f351865d21d.jsonl`
- `/ll:refine-issue` - 2026-07-21T06:39:31 - `18109255-11e7-4e5f-a9fa-278fe601c334.jsonl`
- `/ll:confidence-check` - 2026-07-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57932f3f-45da-45c0-b7c7-a6d471a6fe56.jsonl`
- `/ll:format-issue` - 2026-07-21T06:31:11 - `d1056e19-cd86-401a-93df-69d393607b79.jsonl`
- `/ll:capture-issue` - 2026-07-21T05:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/255186e7-f4f9-45b7-b959-38186bd122ed.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
