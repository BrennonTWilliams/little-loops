---
id: BUG-2357
title: "Scratch hook Read interception breaks Edit/Write tools for session"
type: BUG
priority: P2
status: done
captured_at: "2026-06-27T22:44:05Z"
discovered_date: 2026-06-27
discovered_by: capture-issue
labels: [scratch-hook, tooling, edit, read]
---

# BUG-2357: Scratch hook Read interception breaks Edit/Write tools for session

## Summary

When the scratch hook intercepts a `Read` tool call on a file exceeding `threshold_lines`, it
returns a hook error message rather than the file content. The `Edit` and `Write` tools both
enforce a "file has not been read yet" precondition — they require a prior successful `Read`
to have returned file content. Because the hook substitutes an error for real content, this
precondition is never satisfied, and `Edit`/`Write` are blocked for that file for the remainder
of the session.

## Root Cause

- **File**: `hooks/hooks.json` + the scratch-pad hook implementation
- **Anchor**: `scratch_pad` pre-tool-use hook on `Read`
- **Cause**: The hook intercepts `Read` and emits a `[scratch-pad] ... Use Bash instead` error
  message. From the Claude Code tool layer's perspective, `Read` ran but returned an error — the
  "has been read" precondition used by `Edit`/`Write` checks for a successful content response,
  not merely that the tool was called. As a result, any `.md`/`.py`/`.ts` (etc.) file over
  `threshold_lines` becomes permanently uneditable via `Edit`/`Write` for the session.

## Steps to Reproduce

1. Open any issue file that has grown past `threshold_lines` (default 200) via prior
   `/ll:format-issue` or `/ll:refine-issue` passes — e.g., a 250-line `.issues/**/*.md` file.
2. Attempt to `Read` the file in Claude Code.
3. Observe the scratch hook intercepting and returning: `[scratch-pad] ... has N lines
   (threshold 200). Use Bash instead: ...`
4. Attempt to `Edit` the file.
5. Observe: `File has not been read yet. Read it first before writing to it.`

Workaround: use `python3 -c "with open(path) as f: content = f.read(); ..."` in Bash — the
hook's `command_allowlist` does not include `python3`, so it is not intercepted.

## Expected Behavior

Either:
- **(A)** The scratch hook allows `Read` to succeed (returns actual content), then optionally
  also pipes a truncated copy to scratch for context management — both goals are satisfied.
- **(B)** The hook signals success (content returned) to the tool layer even while saving to
  scratch, so the `Edit`/`Write` precondition is satisfied.
- **(C)** The `Edit`/`Write` precondition is relaxed: instead of requiring a prior Read, it
  accepts a `--force` flag or inspects whether the file exists rather than whether `Read` ran.

## Current Behavior

- The hook returns a hard error instead of file content.
- `Edit` and `Write` are blocked for the file for the entire session.
- The only escape is Bash-based file manipulation (`python3`, `sed`, etc.), which defeats the
  purpose of the structured Edit/Write tools and produces no diff preview.

## Impact

- **Severity**: High when it occurs — any issue file that has been enriched past 200 lines
  (common after format + refine passes) becomes edit-locked for the session.
- **Affected workflows**: `/ll:refine-issue`, `/ll:wire-issue`, `/ll:ready-issue`, and any
  other command that reads-then-edits issue files.
- **Workaround exists**: `python3` Bash substitution, but it bypasses diff preview and audit.

## Integration Map

### Files to Modify
- `hooks/hooks.json` — scratch-pad pre-tool-use hook configuration
- Scratch-pad hook implementation (the handler that intercepts `Read`)

### Tests
- `scripts/tests/` — no current tests for hook behavior; may need a hook integration test

## Implementation Steps

1. Decide on fix approach (A), (B), or (C) from Expected Behavior above.
2. If approach (A): modify the hook to return real content AND save to scratch (dual output).
3. If approach (B): modify the hook's return shape so the tool layer sees a content response.
4. If approach (C): investigate whether `Edit`/`Write`'s read-precondition can be relaxed or
   bypassed with a flag when the caller has obtained content via Bash instead of Read.
5. Add regression test verifying that a file intercepted by the scratch hook can still be
   edited in the same session.

## Resolution

Fixed by **removing the Read interception entirely** rather than any of the proposed (A)/(B)/(C)
approaches — none of which were achievable under the Claude Code hook contract:

- (A)/(B) are infeasible: a `PreToolUse` hook can only `allow`/`deny`/rewrite *input*. It cannot
  fabricate a successful Read result or satisfy the harness's read-state tracking, so there is no
  return shape that makes the tool layer "see content."
- (C) — relaxing the Edit/Write precondition — is core Claude Code behavior we don't own.

The only lever we control is *not denying Read*. The Read branch also had near-zero upside: Read is
already self-capping (`offset`/`limit` pagination), and the redirect-to-scratch-then-tail-20 pattern
saves no context for the read-then-edit path (the agent must read the scratch copy in full anyway).
The Bash redirect — the genuinely valuable half, since Bash output is uncapped — is unchanged.

Changes:
- `hooks/hooks.json` — matcher `Bash|Read` → `Bash`.
- `hooks/scripts/scratch-pad-redirect.sh` — removed the `Read)` case, the Read matcher guard, the
  now-dead `threshold_lines` read, and updated the header comment to document why Read is exempt.
- `scripts/tests/test_hooks_integration.py` — `test_read_denied_over_threshold` →
  `test_read_over_threshold_allowed` (regression: large Read must be allowed, not denied).

ENH-2358 (threshold/exclude_patterns tuning) is superseded — with no Read interception, the
threshold no longer applies to Read at all.

## Acceptance Criteria

- [x] After a `Read` on a large file, `Edit` can still be used to modify that file in the same
      session (the hook no longer denies Read).
- [x] The fix does not require the user to switch to Bash-only file manipulation as a workaround.
- [x] Existing scratch-pad behavior (redirecting large Bash output to `.loops/tmp/scratch/`) is
      preserved.

## Session Log
- `/ll:capture-issue` - 2026-06-27T22:44:05Z - `567c4d00-9ba7-4b64-8c58-6d0231d254b8.jsonl`

---

## Status

**Current Status**: done
