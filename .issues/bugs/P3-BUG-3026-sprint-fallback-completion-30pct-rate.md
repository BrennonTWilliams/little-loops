---
id: BUG-3026
status: done
captured_at: '2026-08-03T17:14:59Z'
completed_at: '2026-08-03T17:54:17Z'
discovered_date: 2026-08-03
discovered_by: capture-issue
testable: false
decision_needed: false
confidence_score: 95
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# ll-sprint fallback completion path fired for 3 of 10 issues in a single sprint run

## Summary

In an `ll-sprint run epic-3008` execution (10 issues, 10 waves), 3 of 10
issues (BUG-3012, ENH-3011, ENH-3014) hit the sprint runner's fallback
completion path instead of `/ll:manage-issue` completing the lifecycle
itself. `verify_issue_completed()` (`issue_lifecycle.py:741-775`) found the
issue's status still `open` after the `manage-issue` subprocess returned
exit 0, logged `Warning: {id} status=open (expected done/cancelled)` at
`issue_lifecycle.py:774`, and `process_issue_inplace()`
(`issue_manager.py:619`, fallback block at `issue_manager.py:1240-1338`)
recovered by detecting changed files via `verify_work_was_done()` /
`check_content_markers()` and calling `complete_issue_lifecycle()`
(`issue_lifecycle.py:1036-1076+`, logs `"Completing lifecycle for {id}
(command may have exited early)..."` at line 1076).

This fallback is intentional — its docstring (`issue_lifecycle.py:1044-1069`)
explicitly says it's "the path BUG-2963 was filed against: it fires after an
abnormal subloop exit, exactly when the deliverable is most likely to be
sitting uncommitted." So the fallback firing at all isn't itself the defect;
a 30% hit rate for a single sprint run is high enough to warrant checking
whether the *primary* completion path is regressing, not just confirming the
safety net still catches it.

## Current Behavior

All 3 fallback cases in this run shared a pattern in the session transcript:
the implementing agent explicitly waited on a **backgrounded
`python -m pytest scripts/tests/` run** via monitor/task notifications
("I'll wait for the background test run's completion notification rather
than poll", "I'll wait for the monitor to report the test suite finishing")
before proceeding to Phase 5 (finalize lifecycle: append session log, inject
`completed_at`, set status, commit). In each of these 3 cases, the
`manage-issue` subprocess returned exit 0 without status ever having been
flipped to `done`, and the sprint runner's fallback had to complete the
lifecycle and commit on its own behalf.

The other 7 issues in the same sprint run (all of which also ran the full
test suite in the foreground or background) completed normally through the
primary path with `Verified: {id} status=done`.

## Expected Behavior

`/ll:manage-issue` should reliably complete its own lifecycle (status flip +
commit) whenever it does the underlying work, without needing the sprint
runner's fallback to detect and repair an early exit. If the pattern is
specifically tied to backgrounded test-suite waits truncating the
`manage-issue` subprocess's turn before Phase 5 runs, that's the mechanism
to isolate and, if fixable, close.

## Motivation

The fallback path works, so no issue was silently lost in this run — but a
~30% rate on one sprint is high enough that it should be tracked rather than
assumed to be noise. If the root cause is a race between a backgrounded
subprocess (like a long `pytest` run) and the harness's turn/session
lifecycle for the `manage-issue` invocation, it will recur in every sprint
that runs the full suite per issue, and each recovery relies on
`verify_work_was_done()`'s file-diff heuristic correctly attributing changes
— a heuristic, not a guarantee.

## Steps to Reproduce

1. Run `ll-sprint run <epic-id>` on an epic with several issues that require
   running the full `python -m pytest scripts/tests/` suite as part of
   verification.
2. Observe that for a subset of issues, the `manage-issue` subprocess logs
   indicate it explicitly waited on a backgrounded test run via
   Monitor/task-notification before finalizing.
3. Check `ll-sprint`'s wave log for `Warning: {id} status=open (expected
   done/cancelled)` followed by `Fallback completion succeeded for {id}`
   for those issues, versus a clean `Verified: {id} status=done` for others.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `in process_issue_inplace()`, fallback block at lines 1240-1338
- **Cause**: Not yet root-caused. Hypothesis from the transcript pattern:
  when the implementing agent backgrounds a long-running command (e.g. the
  full pytest suite) and explicitly defers finishing its turn until a
  notification arrives, something in the `manage-issue` subprocess's
  exit/turn-completion handling may return control (exit 0) to the sprint
  runner before the agent's own Phase 5 (finalize lifecycle) actually runs —
  possibly a turn-boundary or timeout interaction specific to
  backgrounded/monitored waits inside a non-interactive `claude -p`
  invocation. This needs to be confirmed by inspecting how `ll-sprint`
  invokes `manage-issue` (subprocess timeout/turn limits) alongside how the
  background-wait pattern behaves under `--dangerously-skip-permissions -p`
  batch mode specifically, since interactive sessions may not exhibit it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- **Confirmed** (was "Not yet root-caused" in prior pass): `ClaudeCodeRunner.build_streaming()` (`host_runner.py:297-369`) constructs a single-shot `-p` invocation. `subprocess_utils.run_claude_command()` treats the stream-json `"result"` event as the canonical end-of-turn signal and breaks its read loop on it (`result_seen = True` at `subprocess_utils.py:567`, break at `:582-586`) — this detection has no visibility into whether a backgrounded child process (started via a `run_in_background`-style Bash call or Monitor) is still pending. When the implementing agent explicitly defers its remaining prompt logic (Phase 5: finalize lifecycle) until a background-task notification arrives, the underlying `claude` CLI process still emits `"result"` and subsequently exits 0 — because a single headless `-p` invocation has no mechanism to inject a continuation turn when that notification later lands.
- **Contrast with a host that already handles this**: `KimiCodeRunner`'s docstring (`host_runner.py:1330-1355`, echoed at `:1466-1470`) documents `print_background_mode=steer`: "the process stays alive while background tasks are pending, feeding completions back as synthetic user messages." A grep for `steer`/`print_background_mode` across `host_runner.py` returns hits only in the `KimiCodeRunner` section (`host_runner.py:271-450` for `ClaudeCodeRunner` has none) — so this is a real capability gap between hosts, not a universal constraint of headless batch mode.
- **Not the same bug as BUG-2731 or the pipe-EOF hang fix**, though all three are anchored on the same `result_seen` signal in `subprocess_utils.py`: the EOF-hang fix (`subprocess_utils.py:453-460`) stops the reader from waiting forever on a pipe that inherited background FDs; BUG-2731's `INFRA_RETRY` classifies a SIGTERM-after-result teardown as retryable infra, not a code defect. BUG-3026's mechanism is the inverse of both — the reader correctly returns on `result`, and the *process* correctly exits 0, but the agent's own turn logic (Phase 5) never got to run before that happened.
- `run_with_continuation()` (`issue_manager.py:219-298`) — the `ll-sprint` call path's subprocess wrapper — does not thread the existing `on_result_seen`/`INFRA_RETRY` signal to `run_claude_command()`; `issue_manager.py:1192-1194` documents this gap in-line: "this non-FSM path doesn't thread `ActionResult.result_seen` through, so `classify_failure()` never actually returns `INFRA_RETRY` here today; included for exhaustiveness."

## Proposed Solution

TBD - requires investigation. Two independent angles to check:
1. Whether `manage-issue`'s own prompt logic ever completes without
   reaching its Phase 5 finalize step when the implementing agent used a
   background/Monitor wait mid-turn — i.e., is Phase 5 actually being
   skipped, or is it running but its output isn't being captured/observed
   before the subprocess returns.
2. Whether `verify_work_was_done()` / `check_content_markers()` in the
   fallback path could be made to also record *why* the primary path
   didn't finish (e.g. tag the fallback commit or log line with a captured
   reason), so future occurrences carry a root-cause signal instead of just
   "may have exited early."

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

Root cause is now confirmed (see Root Cause → Codebase Research Findings): the fallback fires because the Claude Code host's single-shot `-p` invocation has no continuation-on-background-completion mode, unlike `KimiCodeRunner`'s existing `steer` mode. Research surfaced two independently viable, non-mutually-exclusive angles:

**Option A**: Extend `ClaudeCodeRunner` (or the streaming loop in `subprocess_utils.run_claude_command()`) with a Kimi-style steer mode — keep the subprocess/session alive across pending background tasks, feeding the completion back as a synthetic continuation turn, so `manage-issue`'s own Phase 5 always runs before the subprocess is considered done. This closes the gap that causes early exit in the first place, but depends on whether the upstream Claude Code CLI exposes an equivalent capability (or whether an ll-side polling+re-prompt loop can approximate it without one).

> **Selected:** Option B — plumbing already exists and is proven (FSM path precedent); Option A's "existing precedent" turned out to be external CLI behavior, not reusable ll code.

**Option B**: Wire the existing `on_result_seen`/`INFRA_RETRY` signal into `run_with_continuation()` (`issue_manager.py:219-298`, gap documented in-line at `issue_manager.py:1192-1194`) so a `manage-issue` subprocess that ends on a `result` event with content markers absent but a background task still outstanding is classified distinctly from genuine completion, and can be retried/continued by `ll-sprint`'s primary path before ever reaching the fallback's file-diff heuristic. This doesn't prevent the early exit but makes the primary path smarter about recognizing and recovering from it.

**Recommended**: ~~Option A for v1~~ Superseded by codebase research (see Decision Rationale below) — Option B for v1.

### Decision Rationale

**Selected: Option B** (wire `on_result_seen`/`INFRA_RETRY` into `run_with_continuation()`)

Codebase research (parallel `codebase-pattern-finder` agents, one per option) overturned the issue's original "Recommended: Option A" call:

- **Option A's precedent is illusory.** `KimiCodeRunner`'s "steer mode" is not ll Python code — it's an upstream capability of the `kimi` CLI binary itself that ll merely observes via a `print_background_mode` flag. There is no stdin-feeding, keep-alive, or continuation-turn logic anywhere in `host_runner.py`/`subprocess_utils.py` to extend; `ClaudeCodeRunner.build_streaming()` has no equivalent, and there's no evidence the `claude` CLI's `-p` mode accepts a follow-up prompt on an already-open process. Implementing Option A would mean building net-new process-keepalive machinery against an unconfirmed upstream capability, not reusing a proven pattern.
- **Option B reuses proven, working plumbing.** `ResultSeenCallback`/`on_result_seen` is already implemented end-to-end in `subprocess_utils.run_claude_command()` (sets `result_seen` on the stream-json `result` event, invokes the callback) and already consumed by the FSM path (`fsm/executor.py:2679-2706`) via the same mutable-closure pattern `run_with_continuation()` already uses for `on_usage` (`issue_manager.py:274-285`). Wiring it through for the `ll-sprint` path is additive and low-risk.
- **Caveat carried forward, not resolved**: as scoped, `classify_failure()`/`INFRA_RETRY` only fires on `returncode == 143` (SIGTERM-after-result, the BUG-2731 case), and is skipped entirely for `returncode == 0`. BUG-3026's failure mode is a *clean* exit (returncode 0) with a background task still pending — Option B's wiring alone doesn't cover that path. Closing this bug fully will require extending the classification logic to also flag "returncode 0 + result_seen + background task still outstanding" as a distinct, retryable case, not just threading the callback through. This is scoped as follow-up work under the same option, not a reason to prefer Option A.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 0 | 3 |
| Simplicity | 0 | 2 |
| Testability | 0 | 3 |
| Risk | 0 | 2 |
| **Total** | **0/12** | **10/12** |

Option A scored 0/12 across the board: no reusable implementation pattern exists in this codebase, it depends on an unconfirmed upstream CLI capability outside ll's control, and it can't be tested or scoped without first confirming that capability exists. Option B scored 10/12: it mirrors an existing, tested pattern (`scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandResultBreak`) almost verbatim, and is additive/low-risk — docked only for not yet covering the `returncode == 0` case central to this bug, which is the next concrete step once wired through.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()` (`:297-369`); the single-shot `-p` builder with no continuation-on-background-completion mode
- `scripts/little_loops/subprocess_utils.py` — end-of-turn detection (`:453-460`, result-event handling `:536-586`); `result_seen` short-circuits the read loop independent of pending background task state
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` (`:219-298`) does not thread `on_result_seen`/`INFRA_RETRY` to `run_claude_command()`; Phase 2 invocation (`:1090-1145`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/run.py:75`, `:834` — sprint runner call sites into `process_issue_inplace()`
- `scripts/little_loops/issue_lifecycle.py:741-775` (`verify_issue_completed()`), `:1036-1166` (`complete_issue_lifecycle()`) — downstream of the same root cause; already working as designed, not implicated in a fix
- `scripts/little_loops/cli/sprint/run.py:49-99` (`_run_issue_with_wall_clock_timeout()`) — outer wall-clock guard; confirmed unrelated to this bug's mechanism (issues completed well inside budget)

### Conventions in Force
- Host-specific process-lifecycle differences are resolved through per-host adapter classes in `host_runner.py`, not ad hoc branching — evidence: `KimiCodeRunner`'s steer-mode docstring (`host_runner.py:1330-1355`) vs. `ClaudeCodeRunner` (`host_runner.py:271-450`), which has no equivalent
- Races between subprocess exit and background work are diagnosed by anchoring on the stream-json `"result"` event as the single source of truth, then extended via a mutable-closure callback rather than widening return types — evidence: the BUG-2731 precedent (`subprocess_utils.py:43-47`, `ResultSeenCallback`)
- Completion-lifecycle correctness bugs (once the fallback fires) in this codebase carry a `## Decision Rationale` section with a scored table (Consistency/Simplicity/Testability/Risk), separate from `## Proposed Solution` — evidence: BUG-2963, the fallback-commit-safety precedent this issue's own docstring references

### Tests
- `scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandResultBreak` (`:2440-2546`) — existing pattern for testing result-event/EOF races via a fake never-EOF stdout + mocked selector
- `scripts/tests/test_issue_manager.py::TestFallbackVerification` (`:2727-2900+`) — existing pattern for testing `process_issue_inplace()`'s fallback path via nested `patch()` of every collaborator
- `scripts/tests/test_issue_lifecycle.py::TestVerifyIssueCompleted` (`:712-820+`) — existing pattern for testing `verify_issue_completed()` directly against a real `tmp_path` issue file with varying frontmatter `status`

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

### Types
- No new data shape required. The relevant signal already exists as `result_seen: bool` in `subprocess_utils.py` and as `ActionResult.result_seen` in the FSM path (`fsm/types.py`) — this bug is about wiring an existing signal into an unwired path, not introducing a new one.

### Signatures
- `run_claude_command(on_result_seen: ResultSeenCallback) -> CompletedProcess` — existing parameter in `subprocess_utils.py`, not currently passed by `run_with_continuation()` (`issue_manager.py:219-298`) in the `ll-sprint` call path
- `run_with_continuation(on_result_seen: ResultSeenCallback) -> CompletedProcess` — target signature in `issue_manager.py:219` if Option B (wiring `on_result_seen` through) is chosen; currently accepts no such parameter
- `ClaudeCodeRunner.build_streaming(prompt: str) -> list[str]` — existing single-shot `-p` argv builder, `host_runner.py:297`
- `KimiCodeRunner.build_detached(prompt: str, print_background_mode: str) -> list[str]` — existing steer-capable builder on the Kimi host, `host_runner.py:1466`, cited as precedent for Option A

### Call Path
`ll-sprint` (`cli/sprint/run.py` wave loop) -> `process_issue_inplace()` (`issue_manager.py:619`) -> `run_with_continuation()` (`issue_manager.py:219`) -> `issue_manager.run_claude_command()` (`issue_manager.py:117`) -> `subprocess_utils.run_claude_command()` (`subprocess_utils.py:320`) -> `resolve_host().build_streaming()` -> `ClaudeCodeRunner.build_streaming()` (`host_runner.py:297`) — the read loop breaks on `result_seen` (`subprocess_utils.py:536-586`) independent of whether a backgrounded child process the agent is waiting on has itself finished.

### Deviations

_2026-08-03 — `/ll:manage-issue`:_ Implemented the plumbing half of Option B exactly as designed — `on_result_seen` now threads through `issue_manager.run_claude_command()` and `run_with_continuation()` (both call sites, including the Option E explicit-handoff round) and is exposed to `process_issue_inplace()`. Did **not** implement the "returncode 0 + result_seen + background task still outstanding" retryable classification in `classify_failure()`/`INFRA_RETRY` that the Decision Rationale flagged as the undesigned central mechanism — that piece has no concrete detection signal available at a clean exit (no error text to pattern-match, unlike the existing 143/SIGTERM case) and was explicitly called out as needing further design, not incidental wiring. Instead, scoped this pass to Proposed Solution's item 2: `process_issue_inplace()`'s Phase 3 fallback (`issue_manager.py`, the "Command returned success but issue not moved" branch) now tags its log line with whether `result_seen` was True or False for the Phase 2 subprocess, giving future occurrences a captured root-cause signal instead of just "may have exited early." Retrying/continuing the primary path before falling back (rather than just diagnostic tagging) remains open follow-up work.

## Impact

- **Priority**: P3 - The fallback correctly recovers the work today, so no
  issues were lost, but a 30% rate on a single sprint run is a real
  regression signal worth tracking before it's assumed pre-existing/normal.
- **Effort**: Medium - requires reproducing the timing/race under
  `ll-sprint`'s actual subprocess invocation, not just reading code.
- **Risk**: Low - investigation-only; any fix would be internal to lifecycle
  completion detection, not user-facing surface area.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-03 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-03_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Cross-module shared-state complexity: `run_with_continuation()`'s new `on_result_seen` param (issue_manager.py) must thread through to `classify_failure()` (issue_lifecycle.py) as a distinct decision input, not just a passthrough — the callback-plumbing itself mirrors the proven `on_usage` pattern, but connecting it to a real "returncode 0 + result_seen + background task still outstanding" verdict is new cross-module logic, not a mechanical copy.
- Central mechanism left undesigned: the Decision Rationale explicitly defers "how to detect a still-outstanding background task at clean exit" as a "next concrete step" rather than specifying it — this is the actual fix for the bug's mechanism, not incidental wiring, so ambiguity here has outsized effect on outcome risk despite the readiness score being high.
_(no additional risk factors)_

## Session Log
- `/ll:manage-issue` - 2026-08-03T17:53:58 - `84700ac8-eb76-40e0-b593-e5745fc15709.jsonl`
- `/ll:confidence-check` - 2026-08-03T17:33:13 - `2545e198-4432-4252-9129-6ee84ab242aa.jsonl`
- `/ll:decide-issue` - 2026-08-03T17:30:16 - `4698f57f-5aa4-41c8-89d0-a2140baa5e7c.jsonl`
- `/ll:refine-issue` - 2026-08-03T17:24:55 - `3ea88edb-a334-4efe-a42e-28744037b527.jsonl`
- `/ll:capture-issue` - 2026-08-03T17:16:22 - `4ad49473-6f8b-44cc-afa6-91e971b86c04.jsonl`
