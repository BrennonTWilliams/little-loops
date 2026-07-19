---
id: ENH-2696
type: ENH
priority: P3
status: done
captured_at: 2026-07-13 19:40:00+00:00
completed_at: '2026-07-14T00:33:13Z'
discovered_date: 2026-07-13
discovered_by: issue-size-review
parent: EPIC-2616
testable: false
relates_to:
- ENH-2620
confidence_score: 100
outcome_confidence: 93
score_complexity: 23
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 23
---

# Document `ll-loop queue list` (and bare `ll-loop queue`) surface

## Summary

Document the shipped `ll-loop queue list` subcommand — and the bare
`ll-loop queue` (no-verb) help/exit-code behavior — in `docs/reference/CLI.md`,
`.claude/CLAUDE.md`, and `docs/guides/LOOPS_GUIDE.md`. This is the unblocked
half of ENH-2620: FEAT-2618 (`queue list`) has merged (commit `0a755ba3`), so
this surface can be documented exactly as implemented today, without waiting
on FEAT-2619 (`queue remove`).

## Parent Issue

Decomposed from ENH-2620: Document `ll-loop queue` subcommand family. This
child covers the `queue list` (and no-subcommand) portion; the `queue remove`
portion is tracked separately in ENH-2630 pending FEAT-2619.

## Files to Modify

- `docs/reference/CLI.md` — primary doc target. Add a new `#### \`ll-loop queue
  list\`` `####`-level section after the existing queue material, modeled on
  `#### \`ll-loop list\`` (CLI.md:697) / `#### \`ll-loop status <loop>\``
  (CLI.md:716). Cross-reference the existing `##### Queue entries
  (.loops/.queue/)` subsection (CLI.md:643) rather than duplicating the entry
  schema. Update CLI.md:664 — it currently says "cleanup tooling may want to
  prune entries whose pid is no longer alive"; `queue list` (via
  `read_queue_entries`) now *is* that pruning tooling.
- `.claude/CLAUDE.md:197` — the `ll-loop` bullet in the CLI Tools section.
  Append `queue list` to its parenthetical, matching the existing inline style
  (`promote-baseline promotes...; edit-routes renders...`).
- `docs/guides/LOOPS_GUIDE.md:834-856` — the `## CLI Quick Reference` table.
  Add an `ll-loop queue list` row.

## Content to Document (confirmed shipped surface)

- Command tree: `ll-loop queue list` — nested subparser under a `queue` parent
  (`scripts/little_loops/cli/loop/__init__.py:884-899`,
  `set_defaults(command="queue")`, `queue_command="list"`). Bare `ll-loop queue`
  with no subcommand prints the queue parser help and returns exit code `1`
  (`__init__.py:955-958`; locked in by
  `scripts/tests/test_cli_loop_dispatch.py:1087-1095`,
  `test_queue_no_subcommand_prints_help`).
- Flag: `-j` / `--json` (`action="store_true"`) — emits a JSON array via
  `print_json`; empty queue emits `[]`. Exit code `0` in all cases.
- Handler: `cmd_queue_list()` in `scripts/little_loops/cli/loop/queue.py`.
  Human output prints `Pending queue entries (N):` header then one line per
  entry: `<short_id(8)>  <loopName>  pid=<pid>  alive  <YYYY-MM-DD HH:MM:SS>`.
  Empty queue prints `Queue is empty`.
- Pruning side effect: `queue list` calls `read_queue_entries()`
  (`scripts/little_loops/cli/loop/_helpers.py:172`), which **unlinks
  dead-PID entries** as a side effect of listing — every rendered entry is
  `alive` by construction. Document this explicitly.

## Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — **advisory, not in scope as written.** EPIC-2616's
  `## Success Metrics` states `queue list`/`queue remove` should be documented
  "in `docs/reference/API.md`". API.md today documents Python *modules*
  (`little_loops.*`), not `ll-loop` CLI subcommands, and does not enumerate the
  queue family (grep for "queue" returns only unrelated `IssuePriorityQueue`/
  merge-queue hits). Neither ENH-2629 nor sibling ENH-2630 lists API.md in
  Files to Modify. This is a pre-existing EPIC↔child scope inconsistency, not a
  defect in this issue's plan — CLI.md is the correct home for CLI-subcommand
  docs. Resolve by either (a) reconciling the EPIC Success Metric to point at
  CLI.md, or (b) adding a `little_loops.cli.loop.queue` module entry to API.md
  if the new `cmd_queue_list`/`read_queue_entries` functions warrant module-ref
  coverage. No action required to keep ENH-2629 internally correct. [Agent 2]
- No other doc file needs updating: `docs/ARCHITECTURE.md`,
  `docs/development/TROUBLESHOOTING.md`, `CONTRIBUTING.md`, and
  `docs/guides/LOOPS_REFERENCE.md` do not enumerate `ll-loop` subcommands.
  CLI.md:664's stale "cleanup tooling may want to prune..." sentence is a
  **single-occurrence** fix — no duplicate claim exists in LOOPS_GUIDE.md or
  elsewhere to correct in parallel. [Agent 2]
- No overlap with sibling ENH-2630 (`queue remove` docs): the two issues
  partition CLI.md/CLAUDE.md/LOOPS_GUIDE.md cleanly (ENH-2630 adds its `#### `
  section *after* ENH-2629's and cross-links LOOPS_GUIDE.md:1138, which
  ENH-2629 does not touch). Land ENH-2629's `queue list` section first; leave
  `queue remove` fully undocumented for ENH-2630. [Agent 2]

## Tests

- `scripts/tests/test_wiring_cli_registry.py:20` — extend the
  `DOC_STRINGS_PRESENT` table (append before the closing `]` at line 146) with
  presence tuples proving the doc lines landed, e.g.:
  - `("docs/reference/CLI.md", "ll-loop queue list", "ENH-2629")`
  - `(".claude/CLAUDE.md", "queue list", "ENH-2629")`
  - `("docs/guides/LOOPS_GUIDE.md", "ll-loop queue list", "ENH-2629")`
  This is the established convention (ENH-1963 pattern) for proving a doc-only
  change landed — extend the shared table, do not create a new test file.
- No change needed to `scripts/tests/test_cli_loop_queue.py` (tests
  `read_queue_entries`/`_is_earliest_waiter`/`cmd_run`, unaffected by docs).

## Acceptance Criteria

- [x] `docs/reference/CLI.md` has a `#### \`ll-loop queue list\`` section
      documenting the `--json` flag, human/JSON output shapes, the
      no-subcommand help/exit-1 behavior, and the pruning side effect.
- [x] CLI.md:664's stale "cleanup tooling may want to..." sentence is updated
      to reflect that `queue list` now performs this pruning.
- [x] `.claude/CLAUDE.md:197` `ll-loop` bullet mentions `queue list`.
- [x] `docs/guides/LOOPS_GUIDE.md` CLI Quick Reference table has an
      `ll-loop queue list` row.
- [x] `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_cli_registry.py` has
      presence tuples for the new strings and
      `python -m pytest scripts/tests/test_wiring_cli_registry.py` passes.

## Codebase Research Findings

_Added by `/ll:refine-issue` — anchors re-verified against the current worktree
(all resolve; safe to implement as written):_

- `cmd_queue_list()` confirmed at `scripts/little_loops/cli/loop/queue.py:12`;
  prints `Queue is empty` (queue.py:28) and the `Pending queue entries (N):`
  header (queue.py:31); the in-code comment at queue.py:38 already documents the
  "every returned entry is `alive` by construction" pruning invariant — quote it
  when writing the CLI.md pruning note.
- No-subcommand dispatch confirmed at
  `scripts/little_loops/cli/loop/__init__.py:955-960`: `command == "queue"` with
  `queue_command != "list"` falls through to `args._queue_parser.print_help()` +
  `return 1`. `set_defaults(command="queue")` is at __init__.py:888,
  `add_subparsers(dest="queue_command")` at __init__.py:890.
- Pruning side effect confirmed in `read_queue_entries()`
  (`scripts/little_loops/cli/loop/_helpers.py:172`): dead-PID entries are dropped
  **and** unlinked via `f.unlink(missing_ok=True)` at _helpers.py:194.
- Doc targets confirmed: `.claude/CLAUDE.md:197` (the `ll-loop` bullet, current
  parenthetical is `promote-baseline...; edit-routes...`); CLI.md:643 (`##### Queue
  entries`), CLI.md:664 (stale "cleanup tooling may want to prune..." sentence),
  CLI.md:697 (`#### \`ll-loop list\``) and CLI.md:716 (`#### \`ll-loop status\``)
  are all present as cited — use them as the model/insertion anchors.

## Session Log
- `/ll:issue-size-review` - 2026-07-13T19:40:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260713-190834-subloop-epic-epic-2616-ll-loop-queue-management-cli-list-remove/ded2c90d-228f-492a-9d17-cb57f6f69ac3.jsonl`
- `/ll:refine-issue` - 2026-07-14T00:25:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260713-190834-subloop-epic-epic-2616-ll-loop-queue-management-cli-list-remove/1544b89e-a0b3-4c31-afa5-dc5a097ffe21.jsonl`
- `/ll:wire-issue` - 2026-07-13T19:28:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260713-190834-subloop-epic-epic-2616-ll-loop-queue-management-cli-list-remove/37ab2125-e176-43b5-8dfe-4206e55dd50c.jsonl`
