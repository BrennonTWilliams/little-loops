---
id: BUG-3497
title: 'Fix issue capture: issue_capture jinja2 break and non-atomic next-id'
type: BUG
priority: P1
status: open
discovered_date: '2026-09-16'
labels:
- issue-capture
- concurrency
- hub
---

# Fix issue capture: issue_capture jinja2 break and non-atomic next-id

## Summary

Two defects make the issue-filing path unsafe, and together they have caused
two ID collisions in production use: on 2026-09-15 an operator filed three
issues by hand while concurrent automated processes allocated the same IDs
(the files had to be renumbered afterward), and on 2026-09-16 a second
collision occurred between two concurrent automated allocators, again forcing
renumbering.

1. **`issue_capture` is broken.** The atomic capture path returns
   `No module named 'jinja2'` and cannot run, forcing callers onto the manual
   `next-id` + write path.
2. **`ll-issues next-id` + manual write is non-atomic.** `next-id` reads the
   highest ID, but nothing locks or reserves that ID between the read and the
   file write. Concurrent automated processes (research mining, reconcile
   sweeps) allocate in the same window, so any gap is a collision window.

## Current Behavior

- The issue_capture MCP tool is reported to fail with
  `No module named 'jinja2'`, forcing callers onto the manual
  `ll-issues next-id` + hand-written file path instead. Its handler is
  `_tool_issue_capture` in `little_loops/mcp_server/tools.py`, which calls
  `create_issue` in `little_loops/cli/issues/create.py`.
- `ll-issues next-id` (`cmd_next_id` in `little_loops/cli/issues/next_id.py`,
  which calls `get_next_issue_number` in `little_loops/issue_parser.py`) only
  reads the current highwater ID; nothing reserves it. Two callers on that
  manual path (or a manual write racing an
  automated allocator) can read the same number and write colliding files,
  as happened twice in production on 2026-09-15 and 2026-09-16.

## Expected Behavior

- `issue_capture` files an issue with a fresh, unique ID end-to-end without
  raising an import error.
- Two concurrent captures, or a capture racing a manual `next-id` + write,
  can never produce the same ID.
- `next-id` is either made atomic or clearly documented as a read-only hint
  that must not be used for allocation.

## Steps to Reproduce

1. Call the `issue_capture` MCP tool (or invoke it via whatever harness path
   currently reaches `_tool_issue_capture`) from the environment where the
   failure was observed (the MCP server process) — observe
   `No module named 'jinja2'` instead of a created issue.
   **Verification note (added during formatting):** `create_issue` and its
   `_render_issue_content` helper have no `jinja2` import in the current
   codebase (`little_loops/cli/issues/create.py` uses
   `little_loops.issue_template.assemble_issue_body`, not a Jinja renderer),
   and `scripts/pyproject.toml` already declares `jinja2>=3.1` as of
   2026-09-15 (FEAT-3036) — one commit before this issue's discovery date.
   Reproduce this step fresh before implementing; the failing import may be
   coming from a different call path (e.g. `ll-artifact render`, which does
   import `jinja2` in `artifact_templates.py`) or from a stale environment
   rather than a missing dependency declaration.
2. Run `ll-issues next-id` twice in quick succession from two separate
   processes (or race one `next-id` call against an automated allocator that
   calls `create_issue` directly) and write issue files by hand using each
   returned number — observe both processes reporting the same number.

## Root cause (confirmed 2026-09-16)

- **jinja2:** `little_loops/cli/artifact/templatize.py` and `dashboard.py`
  import jinja2 and render the `.j2` templates under `little_loops/templates/`,
  but jinja2 is NOT declared in `pyproject.toml`. So `issue_capture` works where
  jinja2 is transitively present (the Hermes venv) and fails with
  `No module named 'jinja2'` in a leaner environment (the MCP server). Fix: add
  `jinja2` to the `pyproject.toml` dependencies.
- **next-id:** `little_loops/cli/issues/__init__.py` (the `ll-issues next-id`
  subcommand) reads the max ID with no lock or reservation before the file
  write. Fix: reserve-then-write under a lock, or an ID-reservation table, so
  two concurrent allocators can never hand out the same ID.

## Acceptance

- `issue_capture` files an issue with a fresh, unique ID end-to-end.
- Two concurrent captures (or a capture racing a manual write) can never produce
  the same ID.
- `next-id` is either atomic or clearly documented as a read-only hint.

## Program Design

### Signatures

- `create_issue(config: BRConfig, spec: IssueSpec, now: datetime | None = None) -> CreatedIssue`
  (`little_loops/cli/issues/create.py`) — already atomic: allocates under
  `acquire_lock(lock_path, timeout=10.0)` on `.issues/.id-alloc.lock` and
  writes with exclusive-create (`open(path, "x")`), retrying up to 5 times on
  collision.
- `get_next_issue_number(config: BRConfig, category: str | None = None) -> int`
  (`little_loops/issue_parser.py`) — read-only highwater scan, no lock.
- `cmd_next_id(config: BRConfig, count: int = 1) -> int`
  (`little_loops/cli/issues/next_id.py`) — calls `get_next_issue_number`
  directly, outside any lock; this is the unsafe path when combined with a
  manual file write.

### Call Path

`ll-issues next-id` (`cmd_next_id`) -> `get_next_issue_number` (unlocked) —
vs. — `issue_capture` (`_tool_issue_capture`) -> `create_issue` ->
`acquire_lock(.id-alloc.lock)` -> `get_next_issue_number` (locked).

**Open question, not yet resolved by this formatting pass:** the stated
jinja2 root cause does not match the current call path — `create_issue` and
its `_render_issue_content` helper (`little_loops/cli/issues/create.py`) have
no `jinja2` import, and `scripts/pyproject.toml` already declares
`jinja2>=3.1` (added 2026-09-15, FEAT-3036), one day before this issue's
discovery date. The actual `jinja2` importers in the tree are
`little_loops/artifact_templates.py` and `cli/artifact/dashboard.py`, which
back `ll-artifact render`, not `issue_capture`. Confirm the real failing
import path (fresh env vs. stale editable install vs. a different tool)
before treating "add jinja2 to pyproject.toml" as the fix — see the
Steps to Reproduce verification note above.

## Impact

- **Priority**: P1 - two confirmed production ID collisions in two days
  (2026-09-15, 2026-09-16), each requiring manual file renumbering; the
  atomic `issue_capture` path is currently unusable, forcing every caller
  onto the unsafe manual path.
- **Effort**: Small - the next-id race has a direct fix by reusing the
  existing `.id-alloc.lock` pattern from `create_issue`; the jinja2 piece may
  already be resolved pending the verification above.
- **Risk**: Low - the fix follows an already-proven locking pattern in the
  same module; no schema or public API changes.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-16 | Priority: P1


## Session Log
- `/ll:format-issue` - 2026-09-17T04:09:09 - `2a99ae96-959a-42e3-af68-3fbdce04f9f0.jsonl`
