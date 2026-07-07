---
id: ENH-2517
title: Real-subprocess SIGINT integration test + SIGKILL documentation
type: ENH
status: done
priority: P2
parent: ENH-2514
decision_needed: false
captured_at: '2026-07-07T06:36:33Z'
completed_at: 2026-07-07 11:18:42+00:00
discovered_date: '2026-07-07'
discovered_by: issue-size-review
relates_to:
- ENH-2514
- ENH-2515
- ENH-2516
- BUG-2501
- BUG-2513
labels:
- loops
- fsm
- ll-loop
- tests
- documentation
- subprocess
- signal
confidence_score: 96
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 17
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2517: Real-subprocess SIGINT integration test + SIGKILL documentation

## Summary

Add the net-new `subprocess.Popen` + `os.kill(pid, SIGINT)` integration test
for ENH-2514's audit-trail guarantee, and document the SIGKILL limitation in
the user-facing docs (`docs/reference/API.md` and
`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`).

## Parent Issue

Decomposed from ENH-2514: ll-loop should flush events.jsonl / state.json on
forced termination. The persistence-layer durability change is decomposed into
ENH-2515; the signal-handler modification is decomposed into ENH-2516. This
child covers the integration test (Step 5) and the documentation update (Step 4)
from ENH-2514's Implementation Steps.

## Background

Verified by codebase research: real-subprocess + signal-delivery tests do NOT
exist in `scripts/tests/`. The closest template is
`scripts/tests/test_hooks_integration.py:56-130`, which uses `subprocess.run`
with shell-scripts but does NOT exercise signal delivery. This is net-new
ground.

The `_loop_signal_handler` modification (ENH-2516) and the per-event
flush+fsync (ENH-2515) are individually testable via direct-call unit tests
(also covered by their respective children), but the end-to-end "kill a real
`ll-loop run` subprocess and assert the audit trail survives" path is the
user-visible contract that future audits (e.g. `/ll:audit-loop-run`) depend on.

## Current Behavior

- No end-to-end test exists that spawns a real `ll-loop run` subprocess and
  verifies the audit trail survives a SIGINT. The closest template
  (`scripts/tests/test_hooks_integration.py:56-130`) uses `subprocess.run` with
  shell scripts and does NOT exercise signal delivery.
- The `docs/reference/API.md` `ll-loop run` section and
  `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` do not document how the loop
  reacts to SIGINT, double-Ctrl-C, or SIGKILL. Users running `ll-loop run`
  under a shell, CI, or supervisor have no guidance on what data they can
  expect to recover from a forced kill.

## Expected Behavior

- A new pytest class `TestSubprocessSignalIntegration` in
  `scripts/tests/test_fsm_signal_integration.py` exercises the end-to-end
  contract: spawn `ll-loop run <short-loop> --foreground-internal` via
  `subprocess.Popen`, deliver SIGINT, then assert `state.json`,
  `events.jsonl`, and the `.history/<run_id>-<loop_name>/` archive all exist
  and parse.
- A second test (`test_second_signal_force_exit_archives`) proves
  ENH-2516's archive path runs before `sys.exit(1)` on a double-Ctrl-C.
- `docs/reference/API.md` `ll-loop run` section explicitly states:
  - SIGINT/SIGTERM → clean archive (per ENH-2515 + ENH-2516).
  - SIGKILL → cannot be trapped; recommend a supervisor / `nohup` / `tmux` /
    `screen` session.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` adds a "Signal handling"
  subsection describing first-Ctrl-C, second-Ctrl-C, and SIGKILL semantics.

## Motivation

- The `_loop_signal_handler` modification (ENH-2516) and the per-event
  flush+fsync (ENH-2515) are individually testable via direct-call unit
  tests, but the user-visible contract — "kill a real `ll-loop run`
  subprocess and the audit trail survives" — is the surface that future
  audits (e.g. `/ll:audit-loop-run`) and incident post-mortems (BUG-2501
  autodev kill-analysis) depend on.
- Without this test, regressions in the persistence layer or signal handler
  would only be caught by user-reported incidents. Adding it locks the
  end-to-end guarantee in CI.
- Without the SIGKILL doc note, users hit silent data loss when a CI runner
  or a misbehaving supervisor issues SIGKILL. The doc is the only place
  the supervisor workaround is discoverable.

## Proposed Solution

Two-part delivery:

1. **New integration test** at
   `scripts/tests/test_fsm_signal_integration.py`. Use `subprocess.Popen` (not
   `subprocess.run`) so the test can deliver SIGINT to a live process. Poll
   `.loops/running/<loop>.pid` with a bounded timeout, then `os.kill(pid,
   signal.SIGINT)` and `proc.wait(timeout=10)`. Assert `state.json` parses,
   `events.jsonl` contains a `loop_start` event, and the `.history/.../`
   archive exists. Add a second test that sends two SIGINTs back-to-back
   to cover ENH-2516's force-exit path.
2. **Doc updates** to `docs/reference/API.md` (`ll-loop run` section) and
   `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (new "Signal handling"
   subsection). State the SIGINT/SIGTERM/SIGKILL contract and the
   supervisor-workaround recommendation. Optionally add a short help-text
   snippet to `scripts/little_loops/cli/loop/run.py` if the existing
   `--help` text doesn't already mention signals.

## Implementation Steps

### Part A: Subprocess SIGINT integration test

1. Create new file `scripts/tests/test_fsm_signal_integration.py`.
2. Add a pytest class (e.g. `TestSubprocessSignalIntegration`) that exercises
   the end-to-end contract:
   - Spawn `ll-loop run <short-loop> --foreground-internal` via
     `subprocess.Popen` (NOT `subprocess.run` — needs to keep running so the
     test can deliver SIGINT).
   - Poll `.loops/running/<loop>.pid` until the PID file appears OR poll the
     run dir for `events.jsonl`.
   - `os.kill(pid, signal.SIGINT)`, then `proc.wait(timeout=10)`.
   - Assert `<run_dir>/state.json` exists AND parses (use
     `json.loads(state.json.read_text())` to validate).
   - Assert `<run_dir>/events.jsonl` exists AND contains ≥1 `loop_start` event.
   - Assert `.history/<run_id>-<loop_name>/events.jsonl` was archived (the
     audit-trail deliverable).
   - Clean up: `proc.kill()` if still alive after timeout, `tmp_path` fixture
     handles dir cleanup.
3. Add a `test_second_signal_force_exit_archives` variant that:
   - Spawns the loop, waits for PID file.
   - Sends TWO SIGINTs in rapid succession (simulating user double-Ctrl-C).
   - Asserts the archive still landed (proves ENH-2516's
     `archive_run_only()` call fires before `sys.exit(1)`).

### Part B: SIGKILL limitation documentation

4. Update `docs/reference/API.md` (`ll-loop run` section) to note:
   - SIGINT/SIGTERM now archives cleanly (per ENH-2515 + ENH-2516).
   - SIGKILL cannot be trapped; recommend running `ll-loop run` under a
     supervisor / in a detachable session (e.g. `nohup`, `tmux`, `screen`).
5. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (`ll-loop run` guidance
   section) to add a "Signal handling" subsection:
   - First Ctrl-C: graceful shutdown (current behavior, unchanged).
   - Second Ctrl-C: force-exit with audit-trail archive (new behavior,
     ENH-2516).
   - SIGKILL: data loss possible; document the supervisor workaround.
6. Verify `ll-loop run --help` text. The help is generated from `@click.command`
   decorators in `scripts/little_loops/cli/loop/run.py`; if no option text
   mentions signal handling, add a short `help=` snippet on `cmd_run`'s
   surrounding context (e.g. near line 90-300). This is optional — the doc
   updates are the primary deliverable.

## API/Interface

No API changes. Test-only + doc-only delivery.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_signal_integration.py` — NEW file (the integration
  test, this issue's primary deliverable).
- `docs/reference/API.md` — add SIGINT/SIGTERM/SIGKILL contract note to the
  `ll-loop run` section.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add a "Signal handling"
  subsection to the `ll-loop run` guidance.
- `scripts/little_loops/cli/loop/run.py` — OPTIONAL: add a `help=` snippet
  on `cmd_run`'s surrounding context (only if existing text doesn't mention
  signals).

### Dependent Files (Callers/Importers)
- N/A — this is a test + doc change; no production callers are affected.

### Similar Patterns
- `scripts/tests/test_hooks_integration.py:56-130` — uses `subprocess.run`
  with shell scripts. Reference this for fixture / `tmp_path` conventions
  but DO NOT copy the signal-delivery pattern (it does not exercise
  signals).

### Tests
- `scripts/tests/test_fsm_signal_integration.py` — new file (this issue's
  primary deliverable).
- `scripts/tests/test_hooks_integration.py` — referenced for pattern
  consistency; no changes to that file.

### Documentation
- `docs/reference/API.md` — update `ll-loop run` section.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add signal-handling
  subsection.

### Configuration
- N/A

## Scope Boundaries

- **In scope**: Subprocess SIGINT integration test + SIGKILL doc updates.
- **Out of scope**: Direct-call unit tests for `append_event` flush/fsync
  (covered by ENH-2515).
- **Out of scope**: Direct-call unit test for `_loop_signal_handler`
  modification (covered by ENH-2516).
- **Out of scope**: Other long-running subprocesses (`ll-sprint`,
  `ll-parallel`) — separate future enhancement per ENH-2514 Scope Boundaries.

## Impact

- **Priority**: P2 — Required to verify the ENH-2514 contract end-to-end.
- **Effort**: Medium — net-new test file with subprocess timing concerns; doc
  updates are small.
- **Risk**: Medium — subprocess + signal delivery introduces timing-dependent
  failure modes. Mitigation: poll `.loops/running/<loop>.pid` with a bounded
  timeout, hard-kill if subprocess exceeds deadline, isolate test in a fresh
  `tmp_path`.
- **Breaking Change**: No — test + doc only.

## Dependencies

Blocked by:
- ENH-2515 (persistence-layer flush+fsync) — must land before this test can
  pass for the SIGKILL partial-trail guarantee.
- ENH-2516 (second-SIGINT archive path) — must land before the double-SIGINT
  test can pass.

## Related Key Documentation

- `docs/reference/API.md` — `ll-loop run` section (the section this issue
  updates with the SIGINT/SIGTERM/SIGKILL contract).
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — the guide this issue adds
  a "Signal handling" subsection to.
- `docs/ARCHITECTURE.md` — covers the FSM executor / signal-handling
  architecture that this end-to-end test exercises.
- `.claude/CLAUDE.md` — `ll-loop run` CLI entry (for context on the
  current command surface and CLI table-of-contents).

## Status

**Done** | Created: 2026-07-07 | Priority: P2 | Resolved: 2026-07-07

## Resolution

Delivered both parts:

1. **Integration test** at `scripts/tests/test_fsm_signal_integration.py`
   (`pytestmark = pytest.mark.integration`, two tests):
   - `test_sigint_archives_audit_trail` — spawns `ll-loop run
     sigint-test-loop --foreground-internal --instance-id <id> --no-llm
     --no-lock` via `subprocess.Popen`, polls `events.jsonl` for
     `loop_start`, delivers `SIGINT`, asserts clean exit (returncode 0),
     `state.json` parses, and `.history/<run_id>-<loop_name>/` archive
     contains both `state.json` and `events.jsonl` with `loop_start`.
   - `test_second_signal_force_exit_archives` — same setup; delivers
     `SIGINT` then `SIGTERM` (POSIX merges duplicate `SIGINT` deliveries
     so two different signal types are required to trigger two handler
     invocations), asserts `returncode == 1` and the
     `.history/<run_id>-<loop_name>/` archive still lands (proves
     ENH-2516's `archive_run_only(terminated_by="interrupted_force")`
     fires before `sys.exit(1)`).

2. **Documentation updates**:
   - `docs/reference/API.md` — added a "Signal handling (`ll-loop run`)"
     table to the `main_loop` section covering SIGINT/SIGTERM/SIGKILL
     and the supervisor/nohup/tmux/systemd mitigation for SIGKILL.
   - `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — added a "Signal
     Handling (`ll-loop run`)" section with first/second-Ctrl-C
     semantics, SIGKILL data-loss warning, and a mitigation table
     (CI runner / tmux / nohup / systemd). Cross-references the
     `test_fsm_signal_integration.py` contract test.

The `sleep 60` action in the test loop keeps the subprocess blocked long
enough for the signal handler's child-process-kill path (BUG-592/818) to
exercise naturally; a terminal `done` state is included only because the
FSM validator requires one (it is unreachable from `spin → spin`).

## Session Log
- `/ll:ready-issue` - 2026-07-07T10:52:23 - `11770094-301a-493e-80d8-ad89f0a94fc4.jsonl`
- `/ll:confidence-check` - 2026-07-07T10:49:24Z - `380379ce-991d-48a5-bb70-d72116f35fea.jsonl`
- `/ll:format-issue` - 2026-07-07T10:45:26 - `3f75ce5e-9228-4dff-9a25-dd8d13dc467c.jsonl`
- `/ll:issue-size-review` - 2026-07-07T06:36:33Z - `fc70cacc-0621-41d5-a7b3-89f8f15d4569.jsonl`
- `/ll:manage-issue` - 2026-07-07T11:18:42Z - `1332b893-bbf3-42d7-9d93-7c9c7085caa1.jsonl`