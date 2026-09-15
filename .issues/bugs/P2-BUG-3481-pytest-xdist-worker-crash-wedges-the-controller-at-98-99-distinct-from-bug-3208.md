---
id: BUG-3481
type: BUG
title: pytest-xdist worker crash wedges the controller at 98-99%, distinct from BUG-3208
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T21:54:42Z'
program_design_not_applicable: true
---

# BUG-3481: pytest-xdist worker crash wedges the controller at 98-99%, distinct from BUG-3208

## Summary

`python -m pytest scripts/tests/` can wedge permanently, not just hang under
load: when a per-test `--timeout=120 --timeout-method=thread` watchdog fires
and kills an entire xdist worker process (`[gwN] node down: Not properly
terminated`), the surviving workers and controller go fully idle (0% CPU) and
never return an exit code. Observed live during `ll-auto --only ENH-3480`
(2026-09-15): PID 54510 + 6 xdist children sat idle for 20+ minutes with zero
progress before being killed manually. This blocks the `ready-issue` /
`manage-issue` / epic-verify gate, which all read the suite's exit code, the
same way BUG-3208 did — but BUG-3208 is closed and describes a different
signature (idle workers busy-spinning at 97-99% CPU from a stale pytest 9
resolving into the miniforge interpreter). This machine already has the
BUG-3208-safe pins installed (`pytest==8.4.2`, `pytest-xdist==3.7.0`) and the
wedge still occurred, with workers truly idle at 0% CPU rather than
busy-spinning — a distinct, still-open failure mode in the same
"suite wedges at the tail" family.

## Current Behavior

Tail of `.loops/tmp/scratch/enh3480-test-results.txt` from the run:

```
ssssssssss.............................................................. [ 96%]
...
....[gw4] node down: Not properly terminated
F<site-packages>/pytest_benchmark/logger.py:44: PytestBenchmarkWarning...
```

After that line, `ps aux` showed the controller (PID 54510) and all 6
`[pytest-xdist idle]` workers alive but at 0% CPU (`SN` state), unchanged for
20+ minutes. No further test output was ever written. `vm_stat`/`top` showed
no memory pressure (38G unused) and no OOM/jetsam kill in `log show` for the
window, ruling out the machine running out of resources — the crash was
test-timeout-driven, not environmental.

## Expected Behavior

A worker crash mid-run should not silently wedge the whole session. Either:
- pytest-xdist reschedules the crashed worker's remaining queued file(s) to a
  surviving worker and the run completes (reporting the timed-out test as a
  failure), or
- the controller detects the dead worker and fails fast with a non-zero exit
  and a clear error, within a bounded time.

Either outcome returns an exit code so `ll-auto`'s Phase 3 finalization does
not stall indefinitely waiting on a background task that will never notify.

## Motivation

Same motivation as BUG-3208: the full suite *is* this project's CI (no hosted
runner per `.claude/CLAUDE.md` § Testing & CI Policy), so a wedge here is a
silent total outage of the merge gate, not an inconvenience. This is the
second distinct root cause (after BUG-3208's stale-pytest-9 busy-spin) to
produce the identical externally-visible symptom — a session that "waits for
the background test run" forever with no completion notification — so
without a fix, the same class of failure will keep recurring and keep getting
misdiagnosed as BUG-3208 (they must be told apart by CPU state: idle-0% here,
busy-spin-97-99% there).

## Proposed Solution

Not yet root-caused to a specific mitigation — this issue captures the
observation and reproduction signature; a fix requires further investigation
into why `pytest-xdist` 3.7.0's crash-recovery path doesn't reschedule or
finalize here. Candidate directions to evaluate, not yet chosen:

1. Identify and fix/mark-slow the specific test that exceeded 120s (requires
   a serial `-n0` rerun, or per-file `--durations`/verbose xdist output, to
   attribute the hang to a file — not done in this pass because a full serial
   rerun of a ~24.5k-test suite is expensive and shouldn't run unattended
   inside another automated retry).
2. Confirm/rule out whether `-x`/`--exitfirst` (injected by the `ll-auto`
   finalize/re-drive prompt, not part of `project.test_cmd` in
   `.ll/ll-config.json`, which is bare `python -m pytest scripts/tests/`) is
   required to trigger the no-recovery path, since xdist's exitfirst handling
   and its crash-requeue logic may be interacting.
3. Consider a wrapper-level watchdog (outside pytest itself) that detects a
   fully-idle xdist run past some grace period and kills+reports it, so the
   failure surfaces as "suite timed out" rather than an indefinite hang —
   mirrors the CI-side "master-side hang watchdog for BUG-3208" already built
   for the hosted-runner diagnosis effort (see `ci(diagnose): add
   master-side hang watchdog for BUG-3208` in git log), but for local/`ll-auto`
   runs which have no such watchdog today.

## Integration Map

### Files to Modify
- TBD - requires investigation per Proposed Solution above

### Dependent Files (Callers/Importers)
- `.ll/ll-config.json` (`project.test_cmd`)
- `scripts/pyproject.toml` (`[tool.pytest.ini_options]` addopts: `--timeout=120 --timeout-method=thread`, `-n logical --dist loadfile`)
- `scripts/tests/conftest.py` (`pytest_xdist_auto_num_workers`, `pytest_configure` renice, `_collapse_rate_limit_ladder`)
- Any `ll-auto`/`manage-issue` finalize/re-drive prompt path that shells out to run the test suite in the foreground

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:97-115` (`FINALIZE_RETRY_PROMPT`) — the literal `ll-auto` finalize/re-drive prompt text instructing the agent to "Run the test suite in the FOREGROUND and wait for it to finish"; the concrete resolution of the vague "Any ll-auto/manage-issue..." bullet above
- `scripts/little_loops/issue_manager.py:704` (`process_issue_inplace`), `:1537-1567` — the re-drive call site that invokes `FINALIZE_RETRY_PROMPT` via `run_claude_command` (`:144-206`)
- `skills/manage-issue/SKILL.md:376-400` ("Headless-Safe Final Test Run") — documents this same foreground-blocking test-run step as driven by `ll-auto`, `ll-parallel`, and `ll-sprint` via a single non-interactive `claude -p` turn
- `scripts/little_loops/worktree_utils.py:624-769` (`verify_epic_branch_before_merge`), `subprocess.run(...)` at `:755` — the epic-verify merge gate that runs `project.test_cmd` against a worktree with **no `timeout=` kwarg**; a second, independent foreground-blocking call site at risk of the same wedge
- `scripts/little_loops/parallel/orchestrator.py:1634-1653` (`_verify_epic_branch_before_merge`) — caller of the above
- `scripts/little_loops/fleet_improve.py:694-708` (`gate()`) — the only literal `-x`/exitfirst pytest invocation found in the tree; relevant to Proposed Solution #2's exitfirst question but scoped to `test_builtin_loops.py`/`test_builtin_loop_hardcode_gate.py`, not the full `scripts/tests/` suite
- FSM loop YAMLs that independently shell out to `project.test_cmd` and block on its exit code (same wedge risk at each): `scripts/little_loops/loops/general-task.yaml:52-80,911-921` (`run_final_tests`), `dead-code-cleanup.yaml:18-41,126`, `incremental-refactor.yaml:23-114`, `test-coverage-improvement.yaml:134-147`, `harness-multi-item.yaml:88-98`, `harness-single-shot.yaml:58-69`, `harness-plan-research-implement-report.yaml:126-135`, `rl-coding-agent.yaml:58-62`, `mechanize-skills.yaml:124-146`, `evaluation-quality.yaml:54-57`, `oracles/code-run-gate.yaml:79,155-259`, `auto-refine-and-implement.yaml:454-568,793`
- `scripts/little_loops/fsm/runners.py` (shell-command runner, ~lines 365-464) — the existing `idle_timeout`/wall-`timeout` dual-kill primitive (`output="idle_timeout"` vs. `subprocess.TimeoutExpired`) that any wrapper-level watchdog (Proposed Solution #3) would attach to, rather than inventing a new mechanism
- `scripts/little_loops/loops/lib/common.yaml:83-89` (`shell_exit` fragment doc block) — documents the existing `idle_timeout:` vs. `timeout:` convention ("prefer idle_timeout when the real risk is a wedged process") that Proposed Solution #3 should extend, not duplicate

### Similar Patterns
- BUG-3208 (closed) — same externally-visible "suite wedges near 98-99%"
  symptom, different root cause (stale pytest 9 vs. worker crash). Any fix
  here should preserve BUG-3208's pin rationale in `scripts/pyproject.toml`.

_Wiring pass added by `/ll:wire-issue`:_
- BUG-2524 (closed, `P3-BUG-2524-xdist-worker-crash-on-rate-limit-test.md`) — a prior, distinct-root-cause "xdist worker crashed" bug (single slow test exceeding xdist's tolerance under load). Fixed via `@pytest.mark.no_parallel` rerouting rather than a crash/recovery-path test; its own findings note no regression test was added asserting on the literal `worker 'gw<N>' crashed` string — same verification-gap pattern this issue would face

### Tests
- N/A until a specific slow/hung test is identified per Proposed Solution #1

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_conftest_cap.py` (`TestXdistAutoNumWorkers`, `TestPytestConfigureNice`, `TestRateLimitLadderCollapsed`, `TestNoParallelMarkerRouting`) — existing tests to update if a fix touches `pytest_xdist_auto_num_workers`, `pytest_configure`, or `_collapse_rate_limit_ladder`, all three already named in this issue's Dependent Files
- `scripts/tests/test_hook_session_start.py:712-765` (`TestAmbientAutomationEnvHermeticity.test_suite_passes_with_ambient_ll_automation`) — closest existing template for a watchdog-style test: spawns `python -m pytest` as a real subprocess with `timeout=300` and asserts `returncode == 0`, sentinel-guarded against recursion and pinned to `-n 0` to avoid nesting inside an xdist worker. Model any Proposed Solution #3 test after this, not from scratch
- `scripts/tests/test_policy_builder_node_gate.py:53-79` (`test_node_conformance_suite_passes`) — the repo's general "subprocess.run(..., timeout=N) + assert returncode == 0, skip-if-tool-absent" template (CLAUDE.md's external-toolchain-gate policy), a simpler analog to the above
- `scripts/tests/test_worktree_utils.py:1452-1541` (`TestVerifyEpicBranchBeforeMerge`) — existing coverage for the `worktree_utils.py:755` call site newly added to Dependent Files above; exercises a different flake (not the idle-wedge scenario), would need extending if that call site is where a fix lands

### Documentation
- N/A pending root cause

_Wiring pass added by `/ll:wire-issue`:_
- `pytest.ini` (repo root) — a stub that duplicates `scripts/pyproject.toml`'s `[tool.pytest.ini_options]` addopts (`--timeout=120 --timeout-method=thread`, `-n logical --dist loadfile`) and says to keep the two in sync; any addopts change must be mirrored here
- `docs/development/TESTING.md` § "Live Host-CLI Spawn Guard" (~lines 1105-1109) — currently conflates "un-killable BUG-3208 hang" with the busy-spin signature only; needs updating to distinguish busy-spin vs. this issue's idle-wedge signature once a fix lands
- `docs/development/TROUBLESHOOTING.md` § "xdist flake: subprocess signal-handling test times out" (`:821-835`) and § "Full-suite run makes macOS sluggish (beachball)" (`:837-846`) — the existing "suite wedges at the tail" family entries; neither covers this issue's signature today, a fix should add a third entry here
- `docs/observability/streaming-parity-traces.md:73` — secondary, low-priority consumer of the same `--timeout=120` value

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `.ll/learning-tests/pytest-timeout.md` — a "proven" learning-test record (dated 2026-09-12) asserting as fact that `--timeout-method=thread` calls `os._exit(1)` and orphans in-flight subprocess children; if a fix changes `--timeout-method` away from `thread`, this record's claims would need re-proving or marking `status: stale`
- `.github/workflows/ci.yml:81-88` (pin-assertion step) — greps `scripts/pyproject.toml` for the literal `pytest-xdist.*<3.8` pin string; would break independently of the actual fix if a fix direction changes that pin's spelling or bounds

## Implementation Steps

1. Reproduce deliberately: run the full suite with `-p no:cacheprovider
   --durations=0` (or a targeted subset) to find any test that legitimately
   takes close to or over 120s.
2. Once found, either speed it up, mark it `@pytest.mark.timeout(N)` with a
   larger bound, or fix whatever it's blocked on (lock, subprocess, network).
3. Separately/optionally, evaluate a local hang-watchdog for `ll-auto`'s
   foreground test-suite step so a future occurrence of this class of wedge
   fails loudly with a bounded timeout instead of hanging indefinitely.
4. Re-run the full suite to confirm a clean finish with no idle-wedge.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Audit `scripts/little_loops/worktree_utils.py:755` (`verify_epic_branch_before_merge`) — its `subprocess.run(...)` call has no `timeout=` kwarg, an independent foreground-blocking call site at risk of the same wedge as the `ll-auto`/`manage-issue` path
- If Proposed Solution #3 (wrapper-level watchdog) is chosen, extend the existing `idle_timeout`/`timeout` dual-kill primitive in `scripts/little_loops/fsm/runners.py` and the `shell_exit` fragment convention in `scripts/little_loops/loops/lib/common.yaml:83-89` rather than adding a new mechanism; the concrete edit target is `scripts/little_loops/loops/general-task.yaml:911-921`'s `run_final_tests` state (currently `timeout: 1800`, no `idle_timeout:`)
- Update `pytest.ini` (repo root) to mirror any `scripts/pyproject.toml` `[tool.pytest.ini_options]` addopts change
- Update `scripts/tests/test_conftest_cap.py` if the fix touches `pytest_xdist_auto_num_workers`, `pytest_configure`, or `_collapse_rate_limit_ladder`
- Add a third `docs/development/TROUBLESHOOTING.md` entry for this wedge signature, distinct from the existing xdist-flake and beachball entries
- Re-examine `.ll/learning-tests/pytest-timeout.md` for staleness if `--timeout-method` changes

## Impact

- **Priority**: P2 - silent, total outage of the only merge gate when it
  triggers, identical in severity to BUG-3208; observed live blocking an
  active `ll-auto` run.
- **Effort**: Unknown until the specific slow/hung test is identified;
  likely Small once found (BUG-3208 precedent: diagnosis was the cost, not
  the fix).
- **Risk**: Low to investigate (read-only reproduction); risk of the eventual
  fix depends on what's found.
- **Breaking Change**: No.

## Steps to Reproduce

1. Run `python -m pytest scripts/tests/` (or with `-x`) to completion many
   times; this is intermittent/tail-of-suite, not deterministically
   reproducible on demand.
2. Watch `ps aux | grep pytest` during a run that reaches ~98-99%.
3. If a worker exits (visible as `[gwN] node down: Not properly terminated`
   in the pytest output), watch whether the controller and remaining workers
   drop to and stay at 0% CPU (`SN` state) rather than completing or
   busy-spinning.
4. Confirm via `ps -o pid,etime,stat -p <pids>` that elapsed time keeps
   climbing with `STAT` staying `SN`/idle and no further output is written.

## Root Cause

- **File**: `scripts/pyproject.toml` (`[tool.pytest.ini_options]` addopts:
  `--timeout=120`, `--timeout-method=thread`) interacting with pytest-xdist's
  worker-crash handling.
- **Anchor**: pytest-timeout's thread-method watchdog (kills the whole worker
  process via `os._exit()` when a test exceeds the timeout, since a
  thread-based watchdog cannot cleanly abort a hung call in the test thread —
  see `scripts/tests/conftest.py:517`'s `_collapse_rate_limit_ladder`
  docstring, which already documents this tradeoff for a different reason);
  pytest-xdist's session-finish path in the 3.7.0 controller.
- **Cause**: Not fully isolated. The immediate trigger is some test exceeding
  120s wall-clock (not yet identified — the ENH-3480 diff itself, docstring
  presence assertions in `test_wiring_skills_and_commands.py`, is trivial and
  an unlikely culprit). The trigger kills the worker outright rather than
  just failing the test. Downstream of that crash, pytest-xdist 3.7.0's
  controller does not reschedule the dead worker's remaining queued items nor
  finalize the session — it simply stops making progress. Whether `-x`
  (injected by the `ll-auto` re-drive prompt, not the project's `test_cmd`)
  is required for the no-recovery path is unconfirmed.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (correction below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

- Every other file/line citation in Integration Map, Implementation Steps, and
  Root Cause checked against current codebase state (graph: provider=`codegraph`
  freshness=`fresh`) — all accurate, including `worktree_utils.py:755`'s missing
  `timeout=` kwarg, `general-task.yaml:911`'s `timeout: 1800` with no
  `idle_timeout:`, the `pytest-xdist>=3.0,<3.8` pin, BUG-3208's closed status and
  distinct root cause, and BUG-2524's content.
- `ll-verify-evidence --json`: clean (`ok: true`, 0 findings) — no fabricated
  evidence quotes.
- No active required decision rules to check against (`ll-issues decisions list`
  returned none).
- One citation had drifted: `scripts/tests/test_hook_session_start.py:669-763`
  actually starts inside the *preceding* unrelated class
  (`TestSessionStartDesignTokensValidation`); `TestAmbientAutomationEnvHermeticity`
  itself spans 712-765. Corrected in the Tests section above.
- `## Proposed Solution` is explicitly non-prescriptive (three "candidate
  directions... not yet chosen") — the proposal-vs-code consequence check (B6)
  does not apply; there is no single as-written change to trace.

## Status

**Open** | Created: 2026-09-15 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-09-15T22:29:03 - `74d0e714-5fa8-4d36-8d26-f70b1e11f439.jsonl`
- `/ll:wire-issue` - 2026-09-15T22:22:26 - `d2ee88e4-436e-400b-a42b-568c16a51760.jsonl`
- `/ll:refine-issue` - 2026-09-15T22:12:30 - `1daaf7af-e74b-4b5d-b1aa-a57797ab5fda.jsonl`
- `/ll:format-issue` - 2026-09-15T22:08:41 - `4ed27b03-8e1c-4cb5-ad0c-8aea21116e0d.jsonl`
