---
captured_at: '2026-07-06T03:18:28Z'
completed_at: '2026-07-06T03:18:28Z'
discovered_date: 2026-07-06
discovered_by: user-report
status: done
priority: P2
type: BUG
relates_to:
- BUG-2420
- BUG-2408
- BUG-2488
labels:
- hooks
- scratch-pad
- automation
---

# BUG-2491: scratch-pad-redirect masks the wrapped command's exit code (reports 0 for a failing pytest/mypy)

## Summary

`scratch-pad-redirect.sh` rewrote an allowlisted Bash command as
`mkdir …; ( ${CMD} ) > SCRATCH 2>&1; tail -N SCRATCH`. Because the shell
returns the exit status of the **last** command in a `;` list, the rewritten
command always returned `tail`'s status (≈always `0`) — the real status of
`pytest`/`mypy` was discarded. A full suite that exited non-zero with failing
tests was reported to the caller as exit `0`.

Observed during the `ll-auto` run implementing ENH-2481 (2026-07-05, ~21:46):
the agent ran the final suite foreground (correctly, per BUG-2408), then
narrated **"Exit code 0 but 5 failures reported"** — it only caught the failure
by reading the tail text, not the exit code.

## Current Behavior

`hooks/scripts/scratch-pad-redirect.sh:113`:

```bash
NEW_CMD="mkdir -p .loops/tmp/scratch; ( ${CMD} ) > ${SCRATCH_PATH} 2>&1; tail -${TAIL_LINES} ${SCRATCH_PATH}"
```

The trailing `tail` is the last command in the `;` list, so the overall exit
status is `tail`'s (0 whenever the scratch file exists), regardless of whether
`${CMD}` passed or failed. Any consumer that trusts the exit code — the agent's
own `&&` chaining, or an `ll-auto` / `ll-parallel` step keyed on exit status —
treats a run with failing tests as green.

Scope note: this is a Claude Code PreToolUse hook, so it only rewrites **agent
Bash calls**. FSM `shell` states (run directly by the Python executor) are not
routed through it and were never affected.

## Expected Behavior

The rewritten command reports the wrapped command's real exit status while
still printing the inline `tail` summary. A failing `pytest`/`mypy` surfaces a
non-zero exit code; a passing one reports 0.

## Root Cause

Naive `;`-sequencing: `( CMD ) > file 2>&1; tail file` discards `$?` of the
producer because `tail` runs last and its status becomes the command's status.
The BUG-2420 rewrite that introduced the group-wrap + execution-time `mkdir`
never captured or re-raised the producer's exit code.

## Discovery Context (the ENH-2481 run)

Two independent things went wrong in that run; only the first is fixed here:

1. **Auto-background swallowed the inline summary (host behavior, NOT fixed
   here).** The combined suite+mypy runtime exceeded the harness's foreground
   timeout, so Claude Code auto-backgrounded the whole rewritten command; the
   `tail` ran inside the detached process and no summary appeared inline. The
   agent read this as "scratch redirect misfired," retried, and had to poll for
   completion. This is the same auto-background interaction BUG-2420 explicitly
   declared **out of scope (host behavior, not a little-loops hook)**. Likely
   aggravated by BUG-2488 (landed 2026-07-05), whose `os.nice(10)` + 7-worker
   cap in `scripts/tests/conftest.py` lengthens suite wall-clock under `ll-auto`
   CPU contention, pushing the full suite over the auto-background threshold
   more reliably. Tracked as a separate follow-up (see Out of Scope).
2. **Exit-code masking (this bug).** Surfaced as "Exit code 0 but 5 failures
   reported." Once auto-backgrounded output is polled, the fix here makes that
   exit code truthful.

## Proposed Solution (applied)

Capture `$?` of the wrapped command and re-raise it via an **outer subshell**,
so the `exit` scopes to that subshell (never the harness's persistent shell)
while `tail` still prints the inline summary.

`hooks/scripts/scratch-pad-redirect.sh:113`:

```bash
NEW_CMD="mkdir -p .loops/tmp/scratch; ( ( ${CMD} ) > ${SCRATCH_PATH} 2>&1; rc=\$?; tail -${TAIL_LINES} ${SCRATCH_PATH}; exit \$rc )"
```

Preserves every BUG-2420 property: single atomic redirect across all `;`/`|`
segments, execution-time `mkdir`, and the double-wrap passthrough guard
(`:99-101`) is untouched. `mkdir`'s status is intentionally discarded.

## Integration Map

### Files Modified
- `hooks/scripts/scratch-pad-redirect.sh` — line ~113 rewrite (the fix).
- `scripts/tests/test_hooks_integration.py` — two new execution-level tests in
  `TestScratchPadRedirectBug2420`.

### Tests
- `test_rewrite_preserves_nonzero_exit_code` — an allowlisted command that
  fails (`ls /definitely-nonexistent-path-xyz`) executes through the rewritten
  command; asserts the non-zero status propagates AND the tail summary is still
  captured to scratch.
- `test_rewrite_preserves_zero_exit_code` — a succeeding command reports exit 0
  (no false failure).

## Steps to Reproduce

1. `scratch_pad.enabled: true`, `automation_contexts_only: true` (default),
   session `permission_mode == "bypassPermissions"`.
2. Run an allowlisted command that exits non-zero (e.g. `python -m pytest …`
   with a failing test, or `ls /nonexistent`).
3. Observe the Bash tool report exit code 0 despite the failure (pre-fix).

## Impact

- **Priority**: P2 — silently reports failing verification runs as green in
  automation; an `ll-auto` / `ll-parallel` step keyed on exit status could
  commit code with failing tests. Recoverable only by reading the tail text.
- **Effort**: Small — one-line hook rewrite + two regression tests.
- **Risk**: Low — additive `$?` capture inside an outer subshell; all BUG-2420
  behaviors preserved.
- **Breaking Change**: No.

## Related Issues

- **BUG-2420** — introduced the group-wrap/`mkdir` rewrite this fix extends;
  declared auto-backgrounding out of scope.
- **BUG-2408** — foreground-final-suite guidance (held this run, but
  auto-background defeated it anyway).
- **BUG-2488** — the same-day renice that lengthens suite wall-clock and makes
  auto-background more likely.

## Out of Scope

- The harness auto-backgrounding heuristic for long Bash commands (host
  behavior; same exclusion as BUG-2420). The "misfire / wait for completion"
  flailing is a separate, lower-priority follow-up — durable levers are
  reducing final-suite wall-clock in automation and guidance to poll the
  scratch file rather than declare a misfire.

## Resolution

Fixed (2026-07-06).

- `hooks/scripts/scratch-pad-redirect.sh`: wrapped-command exit status captured
  as `rc=$?` and re-raised via an outer subshell; `tail` summary preserved.
- `scripts/tests/test_hooks_integration.py`: added
  `test_rewrite_preserves_nonzero_exit_code` and
  `test_rewrite_preserves_zero_exit_code` to `TestScratchPadRedirectBug2420`.

### Verification Results
- `python -m pytest scripts/tests/test_hooks_integration.py -k ScratchPad` —
  17 passed (both new tests + all BUG-2420 tests).
- `python -m pytest scripts/tests/test_hooks_integration.py` — 110 passed.

## Status

**Current Status**: done


## Session Log
- `hook:posttooluse-status-done` - 2026-07-06T03:19:29 - `fc93908f-ee19-4813-9d50-755bdc513242.jsonl`
