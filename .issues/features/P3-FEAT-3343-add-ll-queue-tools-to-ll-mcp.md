---
id: FEAT-3343
type: FEAT
title: Add ll-queue tools to ll-mcp
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T19:37:22Z'
completed_at: '2026-08-27T19:50:10Z'
---

# FEAT-3343: Add ll-queue tools to ll-mcp

## Summary

Add a queue tool surface to `ll-mcp`, wrapping `little_loops.queue_store` directly (no CLI
subprocess), following the tier-1 read / tier-2 guarded-mutation pattern already used for
issue tools in `scripts/little_loops/mcp_server/tools.py`.

Implemented in a working session (uncommitted at capture time):

- New tier-1 read tools: `queue_list` (wraps `queue_store.list_entries`), `queue_get` (wraps
  `queue_store.resolve_entry`, accepts full id or 8+-char prefix).
- New tier-2 guarded mutation tools (dry-run by default, `apply: true` to write, registered in
  `policy.MUTATING_TOOLS`): `queue_add` (wraps `cli.queue._classify_action` +
  `queue_store.add_entry`), `queue_remove` (pending-only, wraps `queue_store.remove_entry`),
  `queue_requeue` (running-only, wraps `queue_store.reset_to_pending`).
- Deliberately no tool for `ll-queue run`/`--watch` — that's a long-lived drainer process, not
  a stateless request/response call, so it doesn't fit the MCP tool-call model.
  `mcp_server/tasks.py`'s "Decision 2: Scope ll-loop only, no ll-queue dispatch" note is about
  the FEAT-3151 task-polling wrapper specifically (which tools get async task envelopes), not a
  blanket ban on queue tools — confirmed it does not block this addition.
- Found and fixed a latent correctness bug while wiring this up: `queue_store._resolve_queue_db_path`
  had no way to anchor `.ll/queue.db` at an explicit project root — it always re-resolved via
  `resolve_ll_dir()` (cwd-based) for any "default-shaped" path, silently discarding a
  caller-supplied project_root whenever it differed from cwd. Same bug class as BUG-3181
  (history.db), never previously hit because the `ll-queue` CLI always runs with cwd==project
  root; ll-mcp's ENH-3171 project_root threading is the first caller where they can diverge.
  Fixed by threading a `root: Path | None = None` kwarg through
  `_resolve_queue_db_path`/`ensure_db`/`connect`/`add_entry`/`list_entries`/`get_entry`/
  `resolve_entry`/`remove_entry`/`reset_to_pending`, mirroring
  `session_store.db.resolve_history_db`'s `root=` pattern exactly. Backward compatible (kwarg
  defaults to `None`; no behavior change for existing CLI callers).
- Updated existing tests that hardcoded tier-1/tier-2 tool-name lists and ordering
  (`test_mcp_server.py`, `test_feat_3149_mcp_mutation_tools.py`) and the line-number-keyed
  priority-regex allowlist in `test_issue_parser.py` (the new tool insertions shifted two
  pre-existing JSON-schema-pattern lines).
- Added `scripts/tests/test_feat_queue_mcp_tools.py`: dry-run/apply coverage for all 5 tools
  plus a regression test proving queue tools now anchor at `project_root` rather than process
  cwd (fails without the `root=` fix).
- Full suite: 21786 passed; 3 pre-existing unrelated failures (`test_verify_evidence`,
  `test_packaging_duplicate_files`, `test_prose_dep_sweep_gate`) confirmed via `git stash` to
  already fail on `main` before this work — not caused by this change.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Remaining Work

- Update `docs/reference/CLI.md` and `docs/guides/MCP_SERVER_GUIDE.md` tool-count references
  (currently describe a "ten-tool catalog"; the surface is now fifteen tools).
- Stage and commit the changes — nothing from this session has been committed yet.

## Files Touched

- `scripts/little_loops/mcp_server/tools.py` — 5 new tool schemas + handlers, `_TOOL_HANDLERS`
  registrations, updated docstrings/counts.
- `scripts/little_loops/mcp_server/policy.py` — `MUTATING_TOOLS` gains `queue_add`,
  `queue_remove`, `queue_requeue`.
- `scripts/little_loops/queue_store.py` — `root=` kwarg threaded through the path-resolution
  and CRUD functions.
- `scripts/tests/test_mcp_server.py`, `scripts/tests/test_feat_3149_mcp_mutation_tools.py`,
  `scripts/tests/test_issue_parser.py` — updated to match the new tool catalog.
- `scripts/tests/test_feat_queue_mcp_tools.py` — new test file.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-27 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-27T19:37:30 - `7839b9c3-7a0f-4732-a76a-0e00fbd4022d.jsonl`
