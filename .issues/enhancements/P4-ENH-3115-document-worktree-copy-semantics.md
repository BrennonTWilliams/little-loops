---
id: ENH-3115
title: Document what does and does not cross into an auto-created worktree
type: ENH
priority: P4
status: open
parent: EPIC-3111
testable: false
captured_at: '2026-08-08T20:32:03Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- worktree
- documentation
---

# ENH-3115: Document what does and does not cross into an auto-created worktree

## Summary

No documentation states which files an auto-created worktree inherits. Answering
"does my `.env` / `.ll/` / `history.db` reach the worktree?" currently requires
reading `worktree_utils.setup_worktree`, three call sites, the
`worktree_copy_files` default in `config/automation.py`, and the `.ll/` rules in
`.gitignore`. This documentation should state the contract in one place.

## Current Behavior

The behavior is spread across:
- `scripts/little_loops/worktree_utils.py:157-269` — git identity, `.claude/`
  `copytree`, `copy_files` loop, session marker
- `scripts/little_loops/config/automation.py:131` — the default
  `[".claude/settings.local.json", ".env"]`
- `scripts/little_loops/config-schema.json:360` — one-line schema description
- `.gitignore:99-147` — which `.ll/` content is tracked (and so arrives via
  checkout) versus ignored (and so does not)
- `worktree_utils.py:445` — the verify gate's `copy_files=[]` exception

`docs/reference/CLI.md` documents `--worktree` as a flag but not its file
semantics.

## Expected Behavior

A single documented reference answers, for each category, whether it crosses:

| Category | Crosses? | Mechanism |
|---|---|---|
| Tracked files | Yes | `git worktree add` checkout |
| `.claude/` (including gitignored contents) | Yes | wholesale `copytree` |
| git `user.name` / `user.email` | Yes | copied via `git config` |
| `worktree_copy_files` entries (`.env`, `settings.local.json` by default) | Yes, files only | `shutil.copy2` |
| Tracked `.ll/` content (`ll-config.json`, `decisions.d/`, `learning-tests/`) | Yes | checkout, because repo-root `.ll/` is tracked |
| Gitignored `.ll/` state (`ll.local.md`, `history.db`, `queue.db`, locks) | No | not copied |
| Other untracked/gitignored files outside `.claude/` | No | not copied |

Plus the exceptions: the verify-gate worktree passes `copy_files=[]`, so it gets
`.claude/` but no `.env`.

## Motivation

This is the question a user actually asks before trusting an autonomous
worktree run, and the answer is currently only derivable by reading source. The
documentation is also the natural place to record the *reasoning* behind the
sibling issues — why `history.db` is shared rather than copied (BUG-3112), and
which machine-local `.ll/` files deliberately do or don't follow a worktree
(ENH-3113).

## Proposed Solution

Add a worktree copy-semantics section to the docs — either a new
`docs/reference/WORKTREES.md` or a section in an existing reference doc,
whichever fits the current docs layout. Cross-link from:
- `docs/reference/CLI.md` at `ll-loop run --worktree`
- `config-schema.json:360`'s description (pointer only)

Write it **after** BUG-3112, ENH-3113, and ENH-3114 land, so it documents the
final contract rather than the current one.

## Implementation Steps

1. Confirm the final behavior once the sibling issues are resolved.
2. Choose the documentation location (new reference file vs. existing section).
3. Write the crossing table, the exceptions (verify gate), and the rationale for
   share-vs-copy of `history.db`.
4. Cross-link from `docs/reference/CLI.md` and run `/ll:audit-docs`.

## Integration Map

### Files to Modify
- `docs/reference/` — new or extended worktree reference
- `docs/reference/CLI.md` — cross-link at `--worktree`

### Dependent Files (Callers/Importers)
- N/A — documentation only

### Tests
- N/A — documentation only; existing link/anchor checks apply

### Documentation
- This issue is the documentation change

## Impact

- **Priority**: P4 - Discoverability; no functional defect
- **Effort**: Small - One reference section
- **Risk**: Low - Documentation only
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-08T20:35:50 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P4
