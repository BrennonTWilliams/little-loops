---
id: BUG-2540
title: "Orphan pytest-xdist worker sweep was shipped as a built-in hook rather than registered locally"
type: BUG
priority: P3
status: done
captured_at: '2026-07-08T02:43:58Z'
discovered_date: 2026-07-07
discovered_by: review
size: Small
completed_at: '2026-07-08T02:43:58Z'
labels:
- hooks
- distribution
- documentation
- pytest-xdist
---

# BUG-2540: Orphan pytest-xdist worker sweep was shipped as a built-in hook rather than registered locally

## Summary

ENH-2531 added `hooks/scripts/orphan-worker-sweep.sh` as a SessionEnd handler
and registered it in `hooks/hooks.json`, which made it a built-in plugin hook
shipped to every target project that installs `ll`. That was the wrong
distribution channel:

1. **Category mismatch.** The hook fixes a defect in another tool's ecosystem
   (`pytest-xdist`'s `setproctitle` behavior). It has nothing to do with
   little-loops' workflow scope (issues, sprints, context, handoff).
2. **No-op for the vast majority of consumers.** Only Python projects running
   `pytest -n` can produce these orphans; for every other consumer project
   (any non-xdist project, all JS/Go/Rust consumers, etc.) the script runs
   `ps | awk` and matches zero rows.
3. **Pattern violation.** Every other built-in hook is scoped to state
   little-loops created: `scratch-cleanup.sh` only removes scratch files
   bearing the `-<pid>` suffix produced by `scratch-pad-redirect.sh`
   (BUG-2525), `session-cleanup.sh` removes locks/state/scratch files this
   session wrote, `check-duplicate-issue-id*` operates on files under
   `issues.base_dir`. The orphan-worker-sweep touched processes the plugin
   did not create — the PPID-1 reparented check was a partial mitigation,
   not a scope guarantee.
4. **Trust-surface area.** Every shipped hook runs in every consumer's
   session. Built-in hooks should earn their slot by being obviously
   valuable to a Claude Code workflow.

## Resolution

Moved the registration from `hooks/hooks.json` (plugin-shipped) into
`.claude/settings.local.json` (gitignored, dev-only), and removed the entry
from `docs/guides/BUILTIN_HOOKS_GUIDE.md`. The script itself stays at
`hooks/scripts/orphan-worker-sweep.sh` to minimize churn — its wiring
changed, not its location.

The script continues to fire for the developers of this repo (who have a
`settings.local.json`) and continues to copy into `ll-parallel` worker
worktrees (since `.claude/settings.local.json` is already listed in
`worktree_copy_files` per `scripts/little_loops/parallel/types.py`). It
does not ship to fresh marketplace installs.

`ll-init` was deliberately NOT changed to inject the entry into fresh
installs. "Local-only hook" was the explicit scope; widening the
distribution back into `ll-init` would re-create the original problem.

## Files changed

- `hooks/hooks.json` — removed the orphan-worker-sweep SessionEnd entry
  (the second block in the SessionEnd array). SessionEnd now contains only
  `scratch-cleanup.sh`.
- `.claude/settings.local.json` — added a new top-level `"hooks"` key with
  `SessionEnd → bash "$CLAUDE_PROJECT_DIR"/hooks/scripts/orphan-worker-sweep.sh`
  (timeout 5, no `statusMessage`). Uses the canonical `"$CLAUDE_PROJECT_DIR"`
  quoting pattern from `docs/claude-code/hooks-reference.md`.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — reworded the intro on line 11 to
  say "All **built-in** little-loops hooks are declared in `hooks/hooks.json`"
  with a parenthetical acknowledging that local-only hooks can live in
  `.claude/settings.local.json`. Deleted the entire "Orphan pytest-xdist
  worker sweep" subsection under SessionEnd (heading + body). The lifecycle
  table SessionEnd row at line 68 was unchanged — it never listed the
  orphan hook.
- `scripts/tests/test_claude_code_adapter.py` — added
  `test_hooks_json_session_end_no_longer_references_orphan_worker_sweep`
  directly after the BUG-2483 regression test, mirroring its shape. The
  companion `test_hooks_json_registers_session_end_scratch_cleanup` (at
  `scripts/tests/test_hooks_integration.py:2638`) continues to pass — we
  kept `scratch-cleanup.sh` in SessionEnd.

The ENH-2531 issue body was not retroactively rewritten (status was already
`done`); the plan file
`/Users/brennon/.claude/plans/make-it-a-local-only-groovy-stallman.md` and
the git commit serve as the change record.

## Verification

- `python3 -m json.tool hooks/hooks.json` and
  `python3 -m json.tool .claude/settings.local.json` both exit 0.
- `python -m pytest scripts/tests/test_claude_code_adapter.py scripts/tests/test_hooks_integration.py -v` — 118 passed.
- `python -m pytest scripts/tests/` — 14,220 passed, 35 skipped.
- `bash -n hooks/scripts/orphan-worker-sweep.sh` — OK.
- `bash hooks/scripts/orphan-worker-sweep.sh` — exit 0 (no-op with no orphans).
- New regression test
  `TestClaudeCodeAdapterIntegration::test_hooks_json_session_end_no_longer_references_orphan_worker_sweep`
  passes; the test asserts `orphan-worker-sweep` does NOT appear in any
  SessionEnd command string in `hooks/hooks.json`.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-08T02:44:20 - `fcdcf0dd-048e-402a-9cb3-99a186397f3e.jsonl`
