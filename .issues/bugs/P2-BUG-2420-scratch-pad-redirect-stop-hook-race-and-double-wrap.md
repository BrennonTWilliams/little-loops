---
captured_at: '2026-07-01T01:30:40Z'
completed_at: '2026-07-01T02:52:59Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
status: done
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
confidence_score: 95
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
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
  scratch directory; scratch cleanup must run at *session termination*
  (`SessionEnd`), not at the end of every turn (`Stop`), so it can never delete
  output that pending background work depends on.

## Root Cause

- **Defect 1**: naive string concatenation of a user command with a trailing
  redirect, with no detection of existing redirects/compound structure.
- **Defect 2**: the scratch directory's lifetime is bound to the PreToolUse
  hook process, but the `Stop` event deletes it. `Stop` fires at **turn end**
  ("when Claude finishes responding" — once per response), *not* at session end;
  auto-backgrounded commands intentionally outlive the turn, so the `rm -rf` on
  `Stop` races them. The correct lifetime for scratch cleanup is **session end**
  (`SessionEnd`, "when a session terminates"), a distinct event that fires only
  once when the whole session ends. The directory is also created relative to a
  hook-side `mkdir`, not recreated inside the rewritten command at execution time.

## Integration Map

- `hooks/scripts/scratch-pad-redirect.sh:96` — `SCRATCH_PATH` built with the
  hook process's `$$` (unique filename; not itself the bug).
- `hooks/scripts/scratch-pad-redirect.sh:97` — `mkdir -p .loops/tmp/scratch` in
  the hook process (ephemeral; not recreated at command-execution time).
- `hooks/scripts/scratch-pad-redirect.sh:99` — the double-wrap concatenation.
- `hooks/scripts/session-cleanup.sh:17` — `rm -rf ".loops/tmp/scratch"` (runs on
  `Stop`, i.e. every turn — this is the racing delete).
- `hooks/hooks.json` — bindings: PreToolUse/`Bash` → `scratch-pad-redirect.sh`;
  Stop/`*` → `session-cleanup.sh`. **`hooks.json` registers no `SessionEnd` event
  key at all** — every current binding is `Stop` (turn end) or earlier. This fix
  must add the first genuine `SessionEnd` registration.
- `hooks/adapters/claude-code/session-end.sh` — thin adapter that pipes stdin to
  `python -m little_loops.hooks session_end` (the FEAT-1680 stale-ref sweep).
  **Name/event mismatch to be aware of:** despite the `session-end` filename and
  the `session_end` intent name, this handler is wired to the **`Stop`** event
  (`hooks.json` Stop array), so it fires at **turn end (every response)**, not at
  session termination. That naming comes from FEAT-1680, which described it as "a
  `Stop` hook that fires at the end of every … session" — itself conflating
  `Stop` (turn end) with `SessionEnd` (session end). Consequence for this fix:
  its shape is a fine *template* to copy, but it must **not** be reused as the
  cleanup site, because as a `Stop` handler it fires on the very event that
  causes the race. Also avoid the `session_end` intent name for the new handler
  to prevent compounding the confusion (use e.g. `scratch_cleanup` /
  `scratch-cleanup.sh`).
- `SessionEnd` is a distinct, documented Claude Code event — "When a session
  terminates" (`docs/claude-code/hooks-reference.md`), separate from `Stop`
  ("When Claude finishes responding"). It supports exit-reason matchers
  (`clear`, `logout`, `prompt_input_exit`, `bypass_permissions_disabled`,
  `other`). Other hosts (codex/opencode) do not replicate scratch cleanup, so no
  cross-adapter change is required for this fix.
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

**Fix Defect 1 — make the rewrite idempotent / composition-safe.** Two distinct
sub-cases must be handled differently (see Expected Behavior: "pass them through
unchanged **or** wrap the whole command as a group so a single redirect applies
atomically"):

1. **Already-managed output → pass through unchanged.** A command that already
   redirects or `tee`s its own output must not get a second redirect appended —
   the appended `> SCRATCH` would bind to the trailing segment and misroute the
   real output. Guard on the *output-managing* operators only (`>`, `>>`,
   `| tee`), **not** `;`/`|`:

   ```bash
   # Don't wrap commands that already manage their own output — appending a
   # second redirect binds to the trailing segment and misroutes the real output.
   case "$CMD" in
       *'>'*|*'| tee '*) allow_response ;;
   esac
   ```

2. **Bare compound command (`;` or `|` between segments) → group-wrap, don't
   pass through.** A bare allowlisted command such as `pytest a.py; pytest b.py`
   matches the allowlist on its first token, contains no `>`/`| tee`, and so is
   *not* caught by the guard above. Appending ` > SCRATCH 2>&1` binds only to the
   final `pytest b.py` — the first segment's output is lost (the same misroute
   class this bug is about, triggered by `;` instead of `>`). Passing it through
   unchanged is also wrong: its full (potentially huge) output would flood
   context, defeating the hook's purpose. Instead, **group-wrap** so a single
   redirect applies atomically across every segment:

   ```bash
   NEW_CMD="mkdir -p .loops/tmp/scratch; ( ${CMD} ) > ${SCRATCH_PATH} 2>&1; tail -${TAIL_LINES} ${SCRATCH_PATH}"
   ```

   Use a subshell group `( ${CMD} )` (robust against `${CMD}` shapes that would
   break `{ …; }` brace grouping; the subshell cost is negligible for these
   commands). This both captures *all* segments' output and preserves the
   oversized-output redirect for the common bare-command case.

**Fix Defect 2 — move scratch cleanup off `Stop` onto a new, deliberately-wired
`SessionEnd` binding (the durable fix).** `Stop` fires at the end of *every*
assistant turn — exactly when an auto-backgrounded command is still writing — so
deleting the scratch dir there races it. `SessionEnd` fires only "when a session
terminates" (Claude Code hooks reference), after which no background work
remains. Do this deliberately, in three concrete edits:

1. **Remove** `rm -rf ".loops/tmp/scratch"` from `session-cleanup.sh` (the `Stop`
   handler). Leave that script's lock/state/worktree cleanup untouched — only the
   scratch line moves.
2. **Add a new `SessionEnd` event block to `hooks/hooks.json`** (there is none
   today) bound to a small handler that performs the scratch `rm -rf`. Prefer a
   dedicated `hooks/scripts/scratch-cleanup.sh` (single responsibility, must never
   fail — mirror `session-cleanup.sh`'s `|| true` discipline and `exit 0`), e.g.:

   ```jsonc
   "SessionEnd": [
     {
       "hooks": [
         {
           "type": "command",
           "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scratch-cleanup.sh",
           "timeout": 5,
           "statusMessage": "Cleaning up scratch pad..."
         }
       ]
     }
   ]
   ```

   Do **not** reuse the `Stop` block, and do **not** fold this into the existing
   `session-end.sh` adapter. That adapter is *named* "session-end" but is bound to
   the **`Stop`** event (turn end) — folding the delete into it would keep it on
   the racing event and defeat the fix. Its misleading name traces to FEAT-1680,
   which treated `Stop` as "the end of every session"; re-homing that stale-ref
   sweep onto a real `SessionEnd` event to match its name is a reasonable
   follow-on but is **out of scope** here — see Out of Scope.
3. **Belt-and-suspenders (independent; keep in addition to the above):** recreate
   the dir inside the rewritten command so it exists at execution time no matter
   when the backgrounded command runs. This is the same rewritten form as the
   group-wrap in Fix Defect 1 §2:
   `NEW_CMD="mkdir -p .loops/tmp/scratch; ( ${CMD} ) > ${SCRATCH_PATH} 2>&1; tail …"`.

Rejected alternative: age-pruning on `Stop`
(`find .loops/tmp/scratch -type f -mmin +N -delete`) still runs on the racing
event and only narrows the window — a long-enough background command past the age
threshold would still lose its file. Wiring `SessionEnd` removes the race
entirely, so it is the chosen fix.

Fix Defect 2 is the important one: Defect 1 alone would let the *specific*
already-redirected command pass through, but the race still bites any bare
allowlisted long command — the common case under `ll-auto` / `ll-parallel` /
`ll-loop`.

## Implementation Steps

1. Guard `scratch-pad-redirect.sh` against double-wrapping — pass commands that
   already manage their own output (`>`, `>>`, `| tee`) through unchanged. Do
   **not** add `;`/`|` to this passthrough set: a bare compound command must be
   captured, not passed through (see step 2).
2. Group-wrap the rewritten command as `( ${CMD} ) > ${SCRATCH_PATH} 2>&1` (and
   recreate the scratch dir first: `mkdir -p .loops/tmp/scratch; ( ${CMD} ) …`)
   so a single redirect applies atomically across every `;`/`|` segment — this
   both captures all output of a bare compound command and ensures the dir exists
   at execution time regardless of when a backgrounded command runs.
3. Stop the `Stop` hook from racing background work — deliberately wire a **new
   `SessionEnd` binding**:
   a. Delete the scratch `rm -rf` line from `session-cleanup.sh` (Stop handler),
      leaving its lock/state/worktree cleanup intact.
   b. Add a `hooks/scripts/scratch-cleanup.sh` (must-never-fail: `|| true`
      guards, `exit 0`) that runs `rm -rf ".loops/tmp/scratch"`.
   c. Register a new `SessionEnd` event block in `hooks/hooks.json` bound to it
      (no `SessionEnd` key exists yet; do not reuse the `Stop` block).
4. Add the unit + regression tests (see Tests to Add).
5. Verify: run a long allowlisted command the harness auto-backgrounds and
   confirm output is captured; run an already-redirecting command and confirm it
   is not double-wrapped; run a bare compound command (`cmd a; cmd b`) and
   confirm **both** segments' output is captured in the scratch file.

## Tests to Add

- Unit test for `scratch-pad-redirect.sh`: a command containing `>` or `| tee`
  is passed through unchanged (no appended redirect).
- Unit test: a bare compound allowlisted command (`;` or `|` between segments,
  e.g. `pytest a.py; pytest b.py`) is group-wrapped as `( … ) > SCRATCH 2>&1` —
  assert the rewritten command contains the group wrapper and exactly one
  redirect, and (execution-level) that **both** segments' output lands in the
  scratch file, not just the trailing one.
- Unit test: a bare allowlisted command is rewritten to recreate the scratch dir
  before redirecting (dir exists at execution time even if pre-created dir is
  removed).
- Regression test asserting `session-cleanup.sh` (Stop) no longer contains the
  scratch `rm -rf` — cleanup has moved off the racing `Stop` event.
- Wiring test asserting `hooks/hooks.json` registers a `SessionEnd` event block
  bound to the new scratch-cleanup handler (the binding exists and points at the
  right script), and that `scratch-cleanup.sh` never exits non-zero even when the
  scratch dir is absent.

## Impact

- **Priority**: P2 — Silently drops command output for backgrounded/allowlisted
  commands, undermining automation reliability (this bug's own diagnosis was
  blocked by it), but recoverable via foreground runs or manual absolute-path
  redirect (no data loss to source).
- **Effort**: Small — a guard clause in one hook, plus moving one `rm -rf` out of
  the `Stop` handler into a new `scratch-cleanup.sh` and registering a new
  `SessionEnd` block in `hooks.json`.
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
- Re-homing the FEAT-1680 stale-ref sweep (`session-end.sh`, currently a
  **`Stop`/turn-end** handler despite its `session-end` name) onto a real
  `SessionEnd` event so its name matches its firing point. That is a reasonable
  follow-on but is not required to fix this race and is not part of this issue.
  (This bug adds a *new*, correctly-named `SessionEnd` handler for scratch
  cleanup; it does not touch the existing sweep's binding.)

## Resolution

Fixed both defects (2026-07-01).

**Defect 1 — double-wrap** (`hooks/scripts/scratch-pad-redirect.sh`):
- Added a passthrough guard on output-managing operators only
  (`case "$CMD" in *'>'*|*'| tee '*) allow_response ;;`). A command that already
  redirects or `tee`s its own output is passed through unchanged, so no second
  redirect is appended to misroute its trailing segment. `;`/`|` are deliberately
  NOT in the guard — a bare compound command must be captured, not passed through.
- Rewrote the redirect as a subshell group with a single atomic redirect and an
  execution-time `mkdir`:
  `mkdir -p .loops/tmp/scratch; ( ${CMD} ) > ${SCRATCH_PATH} 2>&1; tail -N ${SCRATCH_PATH}`.
  This captures *all* segments of a bare compound command (not just the last) and
  recreates the scratch dir at execution time (belt-and-suspenders for the race).
  Removed the now-redundant hook-process `mkdir`.

**Defect 2 — Stop-hook cleanup race**:
- Removed the scratch `rm -rf` from `hooks/scripts/session-cleanup.sh` (a `Stop`
  handler, fires every turn); left its lock/state/worktree cleanup untouched.
- Added `hooks/scripts/scratch-cleanup.sh` (must-never-fail: `|| true`, `exit 0`).
- Registered a new `SessionEnd` block in `hooks/hooks.json` bound to it — the
  first genuine `SessionEnd` registration. Did not reuse the `Stop` block and did
  not fold into the misnamed `session-end.sh` (`Stop`) adapter.

**Tests** (`scripts/tests/test_hooks_integration.py`): `TestScratchPadRedirectBug2420`
(passthrough for `>`/`| tee`; group-wrap of compound commands; `mkdir` in rewrite;
execution-level both-segments capture) and `TestScratchCleanupSessionEnd`
(session-cleanup no longer removes scratch; scratch-cleanup.sh removes-when-present /
never-fails-when-absent; hooks.json `SessionEnd` wiring). Written Red-first (all 10
failed pre-fix), now Green. Full suite: 13283 passed; the single failure
(`skills/manage-issue/SKILL.md` 500-line limit) is pre-existing and unrelated.

Out of scope (unchanged): re-homing the FEAT-1680 stale-ref sweep onto a real
`SessionEnd`; the harness auto-backgrounding heuristic; other-host adapters.

## Session Log
- `/ll:manage-issue` - 2026-07-01T02:52:59Z - `3e394fcf-f454-4f27-83c8-04afb80965f0.jsonl`
- `/ll:ready-issue` - 2026-07-01T02:30:42 - `94f01e4a-8995-4dd3-9a06-d06181dd9822.jsonl`
- `/ll:ready-issue` - 2026-07-01T01:53:11 - `94f01e4a-8995-4dd3-9a06-d06181dd9822.jsonl`
- `/ll:format-issue` - 2026-07-01T01:40:25 - `36499533-7bd1-4f6d-9bbf-d3658fc451c9.jsonl`
- `/ll:capture-issue` - 2026-07-01T01:30:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2c6847f-2f8d-4525-aec0-a80edae6a826.jsonl`
- `/ll:confidence-check` - 2026-07-01T01:45:02Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e0eeb92d-948c-475f-9b86-eebf3a96d842.jsonl`
- `/ll:confidence-check` - 2026-07-01T02:19:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8da409e8-6185-4be8-aaae-a039c7c68aef.jsonl`

---

## Status

**Current Status**: done
