---
captured_at: '2026-07-01T00:04:14Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
status: open
priority: P2
type: BUG
relates_to:
- BUG-2409
- BUG-280
- BUG-1538
---

# BUG-2408: manage-issue implement flow stalls on backgrounded final test + notification wait in headless ll-auto turn

## Summary

Under `ll-auto` (headless `claude --dangerously-skip-permissions -p`), the
`/ll:manage-issue` implement phase can finish all edits and then launch the
final full-suite `pytest` with `run_in_background`, after which the agent adopts
an interactive-session pattern — *"I'll wait for the scheduled wakeup or
completion notification."* That notification/scheduled-wakeup loop does not
exist inside a single headless `-p` turn, so the turn ends before the agent
reaches its finalization steps (**git commit + `ll-issues set-status <ID>
done`**). The implementation is left uncommitted in the working tree and the
issue stays `open`, even though the work is complete and validated.

Observed in the `ll-auto --only ENH-2406` run (2026-06-30): Phase 2 completed
in 16.3 min, all 126 targeted tests passed and both loops validated clean, but
the run reported "Issues processed: 0" and left the ENH-2406 changes uncommitted
(`rn-implement.yaml`, `rn-remediate.yaml`, three docs guides, two test files).

## Current Behavior

1. The implement agent completes edits and enters a verification step.
2. It runs the full test suite via a **backgrounded** process (`run_in_background`
   / `&`-style), then narrates that it will wait for a "completion notification"
   or "scheduled wakeup."
3. In a headless `claude -p` turn there is no interactive wakeup/notification
   mechanism — that is an affordance of interactive sessions only. With no
   further output to emit, the agent ends its turn.
4. The subprocess runner (`subprocess_utils.py`, see the comment at ~line 380)
   correctly breaks on the headless result marker and logs
   `Phase 2 (implement) completed in N minutes` — a **normal** completion, not a
   timeout.
5. The agent never reached **commit** or **`ll-issues set-status done`**, so the
   working tree holds uncommitted changes and the issue frontmatter still reads
   `status: open`.

This is **not** a timeout: the default `automation.timeout_seconds` is 3600s and
`idle_timeout_seconds` is 0 (disabled) (`config/automation.py:17-18`); the phase
ran ~978s and was emitting output throughout. A timeout would have killed the
process group and raised `subprocess.TimeoutExpired`
(`subprocess_utils.py:391-411`), producing a different log signature.

## Expected Behavior

Within a single headless turn, the implement flow must reach a terminal,
self-contained finish:

- The final verification test run must be **foreground-blocking** (or routed
  through the scratch-pad redirect that pipes to a file and tails the summary),
  so the agent has the result *within the same turn*.
- The agent must not depend on an interactive "scheduled wakeup / completion
  notification" to resume — that signal never fires under `claude -p`.
- After tests pass, the agent must complete finalization in-turn: **commit the
  scoped changes** and **`ll-issues set-status <ID> done`** before the turn ends.

## Root Cause

`skills/manage-issue/SKILL.md` guidance (the implement/verify step) does not
forbid the background-test-then-await pattern and does not require the final
verification run to be foreground-blocking. The `run_in_background` + "wait for
notification" idiom is valid in interactive sessions but is a dead-end in a
single headless automation turn: the turn boundary arrives before the awaited
event, so the commit + status-update tail never executes.

## Integration Map

- `skills/manage-issue/SKILL.md` — implement/verify phase; add a headless-safe
  rule for the final test run and finalization ordering.
- `scripts/little_loops/subprocess_utils.py:~380` — existing comment documents
  why background child processes hang pipe EOF; corroborates the mechanism.
- `scripts/little_loops/issue_manager.py:880-920` — Phase 2 invocation via
  `run_with_continuation`; the turn ends here without a `CONTEXT_HANDOFF` marker.
- `.claude/CLAUDE.md` § Automation: Scratch Pad — the scratch-pad-redirect
  pattern is the intended vehicle for large foreground command output.

## Steps to Reproduce

1. Pick an issue whose implementation ends with a long full-suite test run.
2. Run `ll-auto --only <ID>`.
3. Observe the implement agent background the final `pytest` and narrate waiting
   for a wakeup/notification.
4. Observe Phase 2 "completed" normally, the issue left `status: open`, and the
   changes uncommitted in the working tree.

## Proposed Solution

In `skills/manage-issue/SKILL.md`, add an explicit headless-safety rule:

- Run the final verification suite **foreground-blocking**, e.g. via the
  scratch-pad redirect (`... > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 ...`),
  never `run_in_background` when the agent's next action depends on the result.
- Never wait on an interactive "scheduled wakeup" / "completion notification"
  inside a headless turn.
- Enforce finalization ordering: tests pass → commit scoped files →
  `ll-issues set-status <ID> done`, all within the same turn.

## Implementation Steps

1. Edit `skills/manage-issue/SKILL.md` implement/verify step: require the final
   verification suite to run foreground-blocking (scratch-pad redirect), never
   `run_in_background` when the next action depends on the result.
2. Add an explicit prohibition on the "background test → await scheduled
   wakeup / completion notification" idiom inside a headless `-p` turn.
3. Codify finalization ordering in the skill: tests pass → commit scoped files →
   `ll-issues set-status <ID> done`, all within the same turn.
4. Add a SKILL.md lint/guard assertion (mirroring existing skill-content checks)
   verifying the implement/verify section carries the foreground-blocking +
   no-background-wait guidance.
5. Verify with a headless `ll-auto --only <ID>` run on an issue whose
   implementation ends in a long full-suite test: confirm the turn finishes with
   changes committed and the issue `status: done`.

## Tests to Add

- A SKILL.md lint/guard assertion (mirroring existing skill-content checks) that
  the implement/verify section contains the foreground-blocking + no-background-wait
  guidance.

## Acceptance Criteria

- `ll-auto --only <ID>` on an issue with a long final test run finishes the turn
  with the changes **committed** and the issue **`status: done`**.
- The implement flow never narrates waiting for a wakeup/notification under `-p`.

## Impact

Silent under-completion: an issue is fully implemented and validated but reported
as "0 processed," left `open`, and its changes stranded uncommitted in the working
tree — where a subsequent re-run would re-plan from a dirty tree and risk
duplicate/conflicting edits. Wastes a full implement slot and erodes trust in the
run summary.

## Related Issues

- **BUG-2409** — the Phase-3 verify heuristic that *masks* this by parking the
  issue as "plan awaiting approval" instead of surfacing the completed-but-
  uncommitted state.
- **BUG-280** (done) — false verification failure when a plan is *genuinely*
  awaiting approval (inverse case; agent stopped at planning).
- **BUG-1538** (done) — verification missed *committed* work + rejected a status
  synonym (different failure mode; work was committed).

## Out of Scope

- Changing `ll-auto` timeout/idle-timeout defaults (not the cause here).
- The Phase-3 detection fix (tracked separately in BUG-2409).

## Labels

manage-issue, ll-auto, headless, automation, finalization

## Session Log
- `/ll:format-issue` - 2026-07-01T00:09:07 - `ac278041-8972-4118-8e20-9572ae7f75f4.jsonl`
- `/ll:capture-issue` - 2026-07-01T00:04:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50bef1ad-9ed2-44c2-9376-d53bca2305b4.jsonl`

---

## Status

**Current Status**: open
