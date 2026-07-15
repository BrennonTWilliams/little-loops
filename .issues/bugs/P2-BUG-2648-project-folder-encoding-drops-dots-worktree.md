---
id: BUG-2648
type: bug
status: open
priority: P2
captured_at: "2026-07-15T18:22:18Z"
discovered_date: 2026-07-15
discovered_by: capture-issue
---

# BUG-2648: get_project_folder encoding drops dots, breaks session resolution in worktrees

## Summary

`get_project_folder()` maps the cwd to the host's session-log directory using a
naive `path_str.replace("/", "-")` encoding (`scripts/little_loops/user_messages.py:382`).
Claude Code's actual project-folder encoding replaces **all** non-alphanumeric
characters (including `.`) with `-`, not just slashes. Any cwd containing a
dotted path segment therefore resolves to a folder that does not exist, so
`get_project_folder()` returns `None` and every session-JSONL lookup silently
fails.

This surfaces most often under git **worktrees**, whose paths contain
`.worktrees/` — exactly how `ll-parallel` / `ll-sprint` waves / subloop epics
lay out isolated checkouts. An autodev FSM subloop running in
`ll-labs/cards/.worktrees/…` reported:

> The ll-issues append-log failed to resolve a session JSONL

## Root Cause

**File**: `scripts/little_loops/user_messages.py`
**Function**: `get_project_folder` → `_get_claude_project_folder`

```python
# user_messages.py:382
encoded_path = path_str.replace("/", "-")   # only handles "/"
```

Concrete divergence for a worktree cwd
`/Users/brennon/AIProjects/ai-workspaces/ll-labs/cards/.worktrees/20260715-125040-subloop-epic-epic-495-…`:

| source | encoded folder |
|---|---|
| little-loops produces | `…cards-.worktrees-20260715-…` (dot kept) |
| Claude Code created on disk | `…cards--worktrees-20260715-…` (`/.` → `--`) |

`_get_claude_project_folder` does `project_folder.exists()` → `False` →
`get_project_folder` returns `None` →
`session_log.get_current_session_jsonl()` returns `None` →
`append_session_log_entry()` returns `False` →
`ll-issues append-log` prints "could not resolve session JSONL; entry not written."
(`scripts/little_loops/cli/issues/append_log.py:29`).

## Impact

The base project path (no dots) resolves fine, so this only manifests in dotted
cwds — but that includes every `.worktrees/`-based run. Beyond `append-log`, the
same broken resolver feeds:

- `get_current_session_id()` — issue-event `session_id` stamping (ENH-2462)
- the FSM prompt-mode payload builder
- `complete_issue_lifecycle` session linking

All silently degrade under worktrees (no session id recorded, empty session
links), so worktree-run history/analytics lose session provenance.

## Implementation Steps

1. In `_get_claude_project_folder` (and, host-scheme permitting, the codex /
   opencode / pi variants), encode with the full non-alphanumeric rule instead
   of slash-only: `re.sub(r"[^a-zA-Z0-9]+", "-", path_str)`. Move the encoding
   into each `_get_*_project_folder` so per-host schemes can diverge, rather than
   encoding once before the host branch at line 382.
2. Confirm Claude Code's exact sanitization (single vs collapsed dashes for
   consecutive specials) against on-disk folders before finalizing the regex —
   the observed `--` shows consecutive specials each map to a dash.
3. Keep the `.exists()` guard; if no encoding matches, still return `None`.

## Acceptance Criteria

- [ ] A cwd containing `.worktrees/` resolves to the correct
      `~/.claude/projects/…` folder.
- [ ] `ll-issues append-log` succeeds (writes the entry) when run from a worktree
      checkout that has a live session JSONL.
- [ ] Regression test asserts `get_project_folder` maps a dotted path
      (e.g. `.worktrees/…`) to the dash-collapsed folder name, using a tmp fake
      `~/.claude/projects` layout.
- [ ] Non-worktree (dotless) paths continue to resolve as before.

## Session Log
- `/ll:capture-issue` - 2026-07-15T18:22:18Z - `689f0076-ace7-401e-be3c-6a6b5718157a.jsonl`

---

## Status

open
