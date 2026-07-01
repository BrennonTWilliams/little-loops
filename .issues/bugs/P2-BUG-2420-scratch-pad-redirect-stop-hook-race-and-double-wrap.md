---
captured_at: '2026-07-01T01:30:40Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
status: open
priority: P2
type: BUG
relates_to:
- BUG-2357
- BUG-2407
labels:
- hooks
- scratch-pad
- automation
- concurrency
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-2420: scratch-pad-redirect races the Stop-hook cleanup and double-wraps commands that already redirect

## Summary

Two independent defects in the scratch-pad hooks cause backgrounded/allowlisted
Bash command output to be **silently lost**:

1. **Double-redirect wrapping** — `scratch-pad-redirect.sh` blindly appends its
   own `> SCRATCH 2>&1; tail SCRATCH` to *any* allowlisted command, even one that
   already contains its own redirect or `;`/pipe. The appended redirect binds to
   the command's trailing segment (e.g. a user's own `tail`), not to the real
   producer, so the intended output is misrouted.
2. **Stop-hook cleanup race** — the scratch directory is created by the
   PreToolUse hook but deleted by the `Stop` hook (`session-cleanup.sh`
   `rm -rf .loops/tmp/scratch`). When the harness auto-backgrounds a long
   allowlisted command and the turn ends, the Stop hook fires and removes the
   directory **before** the backgrounded command opens its redirect →
   `no such file or directory`, non-zero exit, and **zero output captured**.

Observed while running the full pytest suite (`python -m pytest scripts/tests/`,
~9 min) during BUG-2409 work: three separate background runs failed with
`(eval):1: no such file or directory: .loops/tmp/scratch/python-<pid>.txt`. The
suite actually ran (13233 passed) only because a manual absolute-path redirect
was used as a workaround.

## Current Behavior

**Defect 1 (double-wrap):** `hooks/scripts/scratch-pad-redirect.sh:99`:

```bash
NEW_CMD="${CMD} > ${SCRATCH_PATH} 2>&1; tail -${TAIL_LINES} ${SCRATCH_PATH}"
```

`${CMD}` is spliced verbatim. If `${CMD}` is already
`pytest … > A.txt 2>&1; tail -20 A.txt`, the result is
`… ; tail -20 A.txt > SCRATCH 2>&1; tail SCRATCH` — the hook's redirect attaches
to the user's `tail`, not to pytest. The hook assumes `${CMD}` is a single bare
command with no redirects/sequencing and has no guard for compound commands.

**Defect 2 (cleanup race):**

1. PreToolUse `scratch-pad-redirect.sh` runs `mkdir -p .loops/tmp/scratch`
   (`:97`) in the *hook* process and rewrites the command to write there (`:96`,
   `:99`).
2. The harness auto-backgrounds the slow command; the assistant turn ends.
3. The `Stop` hook `hooks/scripts/session-cleanup.sh:17` runs
   `rm -rf ".loops/tmp/scratch"`, deleting the directory the backgrounded
   command is about to write into.
4. The backgrounded command opens its redirect → target dir gone →
   `no such file or directory`, exit non-zero, no captured output.

Empirically confirmed: the backgrounded command's CWD **is** the project root
(so it is not a path/CWD bug), yet `.loops/tmp/scratch` was `missing` at
execution time because the Stop hook had swept it. Foreground commands never hit
this because the turn has not stopped between the PreToolUse rewrite and
execution.

## Expected Behavior

- The redirect hook must not corrupt commands that already manage their own
  output (redirect/pipe/sequence) — it should pass them through unchanged or wrap
  the whole command as a group so a single redirect applies atomically.
- Backgrounded allowlisted commands that outlive the turn must still find their
  scratch directory; the Stop-hook cleanup must not delete output that pending
  background work depends on.

## Root Cause

- **Defect 1**: naive string concatenation of a user command with a trailing
  redirect, with no detection of existing redirects/compound structure.
- **Defect 2**: the scratch directory's lifetime is bound to the PreToolUse
  hook process, but the `Stop` event deletes it — and auto-backgrounded commands
  intentionally outlive the turn, so the `rm -rf` on `Stop` races them. The
  directory is also created relative to a hook-side `mkdir`, not recreated inside
  the rewritten command at execution time.

## Integration Map

- `hooks/scripts/scratch-pad-redirect.sh:96` — `SCRATCH_PATH` built with the
  hook process's `$$` (unique filename; not itself the bug).
- `hooks/scripts/scratch-pad-redirect.sh:97` — `mkdir -p .loops/tmp/scratch` in
  the hook process (ephemeral; not recreated at command-execution time).
- `hooks/scripts/scratch-pad-redirect.sh:99` — the double-wrap concatenation.
- `hooks/scripts/session-cleanup.sh:17` — `rm -rf ".loops/tmp/scratch"`.
- `hooks/hooks.json` — bindings: PreToolUse/`Bash` → `scratch-pad-redirect.sh`;
  Stop/`*` → `session-cleanup.sh`.
- `.ll/ll-config.json` — `scratch_pad.command_allowlist` (which commands are
  rewritten), `scratch_pad.tail_lines`, `scratch_pad.automation_contexts_only`.

## Steps to Reproduce

1. Ensure `scratch_pad.enabled: true` and an allowlisted command (e.g. `pytest`).
2. Run a long allowlisted command that the harness auto-backgrounds, e.g.
   `python -m pytest scripts/tests/` (full suite).
3. Let the turn end (auto-background). Observe the task fail with
   `no such file or directory: .loops/tmp/scratch/<name>-<pid>.txt` and no
   captured output. (Defect 2.)
4. Separately, run an allowlisted command that already redirects
   (`pytest … > out.txt 2>&1; tail out.txt`) and observe the hook append a second
   redirect that misroutes the trailing `tail`. (Defect 1.)

## Proposed Solution

**Fix Defect 1 — make the rewrite idempotent / composition-safe.** In
`scratch-pad-redirect.sh`, before rewriting, skip commands that already manage
their own output:

```bash
# Don't wrap commands that already redirect/pipe their own output — appending a
# second redirect binds to the trailing segment and misroutes the real output.
case "$CMD" in
    *'>'*|*'| tee '*) allow_response ;;
esac
```

**Fix Defect 2 — stop the Stop-hook from racing background work (the durable
fix).** Deleting the scratch dir on *every* `Stop` is wrong because
auto-backgrounded tasks intentionally outlive the turn. Options (prefer the
first):

- Move `rm -rf ".loops/tmp/scratch"` out of `session-cleanup.sh` (Stop) into a
  `SessionStart`/`SessionEnd` hook, **or** prune by age instead of nuking the dir:
  `find .loops/tmp/scratch -type f -mmin +N -delete`.
- Belt-and-suspenders: recreate the dir inside the rewritten command so it exists
  at execution time regardless of when the command runs:
  `NEW_CMD="mkdir -p .loops/tmp/scratch; ${CMD} > ${SCRATCH_PATH} 2>&1; tail …"`.

Fix Defect 2 is the important one: Defect 1 alone would let the *specific*
already-redirected command pass through, but the race still bites any bare
allowlisted long command — the common case under `ll-auto` / `ll-parallel` /
`ll-loop`.

## Implementation Steps

1. Guard `scratch-pad-redirect.sh` against double-wrapping — pass commands that
   already manage their own output (`>`, `| tee`, `;`) through unchanged.
2. Recreate the scratch dir inside the rewritten command
   (`mkdir -p .loops/tmp/scratch; ${CMD} …`) so it exists at execution time
   regardless of when a backgrounded command runs.
3. Stop the `Stop` hook from racing background work — relocate the scratch
   `rm -rf` in `session-cleanup.sh` to `SessionStart`/`SessionEnd`, or prune by
   age instead of nuking the directory.
4. Add the unit + regression tests (see Tests to Add).
5. Verify: run a long allowlisted command the harness auto-backgrounds and
   confirm output is captured; run an already-redirecting command and confirm it
   is not double-wrapped.

## Tests to Add

- Unit test for `scratch-pad-redirect.sh`: a command containing `>` or `| tee`
  is passed through unchanged (no appended redirect).
- Unit test: a bare allowlisted command is rewritten to recreate the scratch dir
  before redirecting (dir exists at execution time even if pre-created dir is
  removed).
- Regression test asserting `session-cleanup.sh` (Stop) does not delete scratch
  output that a pending background task depends on (or that cleanup moved off the
  Stop event).

## Impact

- **Priority**: P2 — Silently drops command output for backgrounded/allowlisted
  commands, undermining automation reliability (this bug's own diagnosis was
  blocked by it), but recoverable via foreground runs or manual absolute-path
  redirect (no data loss to source).
- **Effort**: Small — a guard clause in one hook plus relocating/softening one
  `rm -rf` in another.
- **Risk**: Low-Medium — touches shared hook behavior used by every automation
  context; must preserve the intended "redirect oversized output" behavior for
  bare commands.
- **Breaking Change**: No.

## Related Issues

- **BUG-2357** — the same hook's Read-interception hazard (edit-lock); shows this
  hook has prior subtle-interaction bugs.
- **BUG-2407** — `python -m <module>` allowlist unwrapping in this same hook
  (adjacent scratch-pad-redirect correctness work).

## Out of Scope

- The harness's auto-backgrounding heuristic for long Bash commands (host
  behavior, not a little-loops hook).
- Broader `session-cleanup.sh` worktree/lock cleanup logic (only the scratch
  `rm -rf` is implicated here).

## Session Log
- `/ll:ready-issue` - 2026-07-01T01:53:11 - `94f01e4a-8995-4dd3-9a06-d06181dd9822.jsonl`
- `/ll:format-issue` - 2026-07-01T01:40:25 - `36499533-7bd1-4f6d-9bbf-d3658fc451c9.jsonl`
- `/ll:capture-issue` - 2026-07-01T01:30:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2c6847f-2f8d-4525-aec0-a80edae6a826.jsonl`
- `/ll:confidence-check` - 2026-07-01T01:45:02Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e0eeb92d-948c-475f-9b86-eebf3a96d842.jsonl`

---

## Status

**Current Status**: open
