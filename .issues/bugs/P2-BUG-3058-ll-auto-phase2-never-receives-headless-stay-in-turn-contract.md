---
id: BUG-3058
title: ll-auto Phase 2 never receives the headless stay-in-turn contract, and has
  no recovery when the turn ends unfinalized
type: BUG
priority: P2
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-05
captured_at: '2026-08-05T05:42:22Z'
completed_at: '2026-08-05T05:42:22Z'
relates_to:
- BUG-2408
- BUG-3026
- BUG-2729
- BUG-2730
- BUG-2409
- ENH-2714
- BUG-3054
labels:
- automation
- headless
- ll-auto
---

# BUG-3058: ll-auto Phase 2 never receives the headless stay-in-turn contract, and has no recovery when the turn ends unfinalized

## Summary

Three separate defects let an `ll-auto` implement phase do all its work and then
abandon it:

1. `issue_manager.py` never passes `automation_profile`, so `LL_AUTOMATION=1` is
   never set for the Phase 2 subprocess and BUG-2730's "never end your turn while
   tasks are running" instruction never reaches the phase that most needs it.
2. That instruction is emitted only on the ENH-2714 pruning early-return, so
   setting `history.automation_pruning.enabled: false` — an escape hatch meant to
   restore *more* hook output for debugging — silently removes it.
3. When the turn does end cleanly without finalizing the lifecycle, Phase 3 drops
   straight to the evidence-of-work fallback, which can only *infer* completion
   from a dirty tree. Nothing re-drives the primary path.

## Steps to Reproduce

1. Run `ll-auto --only <ID>` on any issue whose implement phase runs a long test
   suite.
2. Inspect the Phase 2 child process environment: `LL_AUTOMATION` is unset.
   Equivalently, `grep -rn "automation_profile" scripts/little_loops/issue_manager.py`
   returns nothing.
3. Have the agent background its final suite (`run_in_background: true`) and end
   its turn narrating that it will wait for a completion notification. Under
   `claude -p` that signal never fires.
4. Observe Phase 3: `Warning: <ID> status=open (expected done/cancelled)`, then
   `Command returned success but issue not moved - checking for evidence of
   work... (turn ended cleanly (result event observed) without finalizing the
   issue lifecycle - possibly still waiting on a backgrounded task when the turn
   ended)`.
5. No retry occurs. The run either completes via the inference fallback or, if
   anything vetoes it, fails outright with the work uncommitted.

For defect 2 in isolation: set `history.automation_pruning.enabled: false`, set
`LL_AUTOMATION=1`, invoke the SessionStart hook, and observe the stay-in-turn
text is absent from stdout.

## Current Behavior

**Defect 1.** `host_runner.py:351-353` injects `LL_AUTOMATION` /
`LL_AUTOMATION_PROFILE` only when `automation_profile` is passed. The only
callers that pass it are `runner_spec.py` and `fsm/runners.py` (set from
`fsm/executor.py:1902`). The `ll-auto` path — `process_issue_inplace` →
`run_with_continuation` → `issue_manager.run_claude_command` →
`subprocess_utils.run_claude_command` — never threaded the parameter at all.

**Defect 2.** `hooks/session_start.py:110-123` returns
`_STAY_IN_TURN_INSTRUCTION` inside `if _pruning_gate_enabled:`. When the gate is
disabled the function falls through to the normal payload and the instruction is
dropped entirely.

**Defect 3.** `issue_manager.py:1280` enters the fallback on
`not verified and result.returncode == 0`. BUG-3026 added `_phase2_result_seen`
plumbing and used it only to tag a log line; its Deviations section records that
the retry classification was deliberately deferred.

`skills/manage-issue/SKILL.md:376-400` does forbid backgrounding the final suite,
but it is prose with no enforcing hook — BUG-3026 measured the agent violating it
in 3 of 10 sprint runs.

## Expected Behavior

- The Phase 2 subprocess runs under an automation profile, so the SessionStart
  hook injects the stay-in-turn contract.
- That contract is emitted whenever `LL_AUTOMATION` is set, pruned or not — it is
  a property of running headlessly, not of pruning.
- A clean result event with an unfinalized lifecycle triggers exactly one
  re-drive of the primary path with an explicit finalize instruction, before any
  inference-based fallback runs. If the re-drive finalizes the issue, no fallback
  is needed.

## Root Cause

`automation_profile` was introduced by ENH-2714 as an opt-in pruning control and
wired only into the FSM path. BUG-2730 then attached the stay-in-turn contract to
that same opt-in, which coupled a *safety* contract to a *token-budget*
mechanism. `ll-auto`, which never opted into pruning, silently inherited neither.

## Program Design

### Signatures

- `run_claude_command(command: str, logger: Logger, timeout: int = 3600, ..., automation_profile: str | None = None) -> subprocess.CompletedProcess[str]` — `issue_manager.py:118`, new trailing kwarg.
- `run_with_continuation(initial_command: str, logger: Logger, ..., automation_profile: str | None = None) -> subprocess.CompletedProcess[str]` — `issue_manager.py:224`, new trailing kwarg.
- `FINALIZE_RETRY_PROMPT: str` — new module constant, `issue_manager.py`.
- `handle(event: LLHookEvent) -> LLHookResult` — existing, `hooks/session_start.py:86`.

### Call Path

`process_issue_inplace` (`issue_manager.py:619`) -> `run_with_continuation` (`issue_manager.py:224`) -> `run_claude_command` (`issue_manager.py:118`) -> `subprocess_utils.run_claude_command` (`subprocess_utils.py:320`) -> `ClaudeCodeRunner.build_streaming` (`host_runner.py:297`), which injects `LL_AUTOMATION` at `host_runner.py:351`. In the child, `handle` (`hooks/session_start.py:86`) reads it and emits `_STAY_IN_TURN_INSTRUCTION`. The retry re-enters `run_claude_command` directly and re-checks via `verify_issue_completed` (`issue_lifecycle.py:789`).

The parameter is threaded as a keyword with a `None` default at every hop, so
callers that never opted in are unaffected. Phase 2 passes
`automation_profile="ll-auto"`; `run_with_continuation` forwards it to both of
its `run_claude_command` sites (initial round and the Option E `--continue`
round) so continuations carry the contract too.

In `hooks/session_start.py`, the `LL_AUTOMATION` check is hoisted into
`_under_automation`, and the final return prepends `_STAY_IN_TURN_INSTRUCTION` to
`stdout_payload` on the unpruned path.

The retry is a plain single-shot block inside `if not verified`: it calls
`run_claude_command` with `FINALIZE_RETRY_PROMPT`, then re-reads the issue via
`verify_issue_completed`. It cannot loop, because the surrounding
`if not verified and result.returncode == 0:` guard is re-evaluated immediately
after against freshly-read frontmatter.

`FINALIZE_RETRY_PROMPT` states the constraint that was violated: run the suite in
the foreground, never `run_in_background`, never wait on a notification, and do
not re-implement work already on disk.

## Implementation Steps

1. Add `automation_profile: str | None = None` to
   `issue_manager.run_claude_command` and forward it to `_run_claude_base`.
2. Add the same parameter to `run_with_continuation`; forward at both
   `run_claude_command` call sites.
3. Pass `automation_profile="ll-auto"` at the Phase 2 call site.
4. Add module-level `FINALIZE_RETRY_PROMPT`.
5. Insert the single-shot re-drive in Phase 3, gated on `_phase2_result_seen[0]`,
   ahead of the existing evidence fallback.
6. Hoist `_under_automation` in `hooks/session_start.py`; prepend the instruction
   on the unpruned return.
7. Tests: profile forwarding and its `None` default; `FINALIZE_RETRY_PROMPT`
   content guards; update
   `test_pruning_gate_disabled_falls_through_to_normal_payload` to assert the
   instruction is now present.

## Impact

Silent loss of completed work. The 2026-08-04 `ll-auto --only ENH-3046` run
implemented the issue correctly, passed lint and types, and then ended its turn
awaiting a background suite; Phase 5 never ran. Combined with BUG-3054's veto,
the run reported `verification failed` and marked the issue to be skipped on
future runs, leaving 21.6 minutes of correct work uncommitted.

The escape-hatch defect is the worst of the three in character: the setting an
operator reaches for when a headless run misbehaves is precisely the one that
removes the guardrail against the most common headless failure.

## Resolution

All three defects fixed. `automation_profile` threaded through the `ll-auto`
Phase 2 path; the stay-in-turn contract now emitted on both hook paths; the
single-shot finalize re-drive added ahead of the evidence fallback.

Note this narrows but does not eliminate the failure mode — the contract is an
instruction, not an enforcement. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`
(documented in `docs/claude-code/settings.md:772`, referenced nowhere in this
codebase) remains an unpulled hard lever, deliberately left alone because it
would also block legitimate server-smoke-test backgrounding.

## Status

**Completed** — 2026-08-05

## Session Log
- `hook:posttooluse-status-done` - 2026-08-05T05:44:01 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- run-forensics - 2026-08-05 - Root-caused from the failed `ll-auto --only
  ENH-3046` run; all three defects fixed with tests.
