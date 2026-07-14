---
id: ENH-2630
type: ENH
priority: P3
status: open
captured_at: 2026-07-13 19:40:00+00:00
discovered_date: 2026-07-13
discovered_by: issue-size-review
parent: ENH-2620
depends_on:
- FEAT-2619
---

# Document `ll-loop queue remove <id>` subcommand

## Summary

Document the `ll-loop queue remove <id>` subcommand in `docs/reference/CLI.md`,
`.claude/CLAUDE.md`, and `docs/guides/LOOPS_GUIDE.md` once FEAT-2619 ships.
This is the blocked half of ENH-2620: no `cmd_queue_remove` handler or
`remove` subparser exists in `scripts/little_loops/cli/loop/` yet, so this
issue cannot be implemented until FEAT-2619 (`status: open`) merges.

## Parent Issue

Decomposed from ENH-2620: Document `ll-loop queue` subcommand family. The
`queue list` portion is tracked separately in ENH-2629 (unblocked, ships
first). This child covers only `queue remove`.

## Dependency

**Blocked on FEAT-2619** (`ll-loop queue remove <id>`). Do not start until it
merges — document the CLI surface exactly as implemented, not from
assumptions. In particular, confirm against the merged code before writing:
- `<id>` arg spelling: full id vs. 8-char short id (short id is the display
  format used by `queue list`, per `cmd_queue_list()` in
  `scripts/little_loops/cli/loop/queue.py`)
- Exit codes for not-found vs. removed
- Any `--json` / `--force` flags

## Files to Modify

- `docs/reference/CLI.md` — add a new `#### \`ll-loop queue remove <id>\``
  section after the `queue list` section added by ENH-2629, modeled on the
  same `#### \`ll-loop list\`` (CLI.md:697) / `#### \`ll-loop status <loop>\``
  (CLI.md:716) style. Cross-reference the `##### Queue entries
  (.loops/.queue/)` subsection (CLI.md:643) rather than duplicating the entry
  schema.
- `.claude/CLAUDE.md:197` — the `ll-loop` bullet in the CLI Tools section.
  Append `queue remove` to its parenthetical (alongside `queue list` from
  ENH-2629), matching the existing inline style.
- `docs/guides/LOOPS_GUIDE.md:834-856` — the `## CLI Quick Reference` table.
  Add an `ll-loop queue remove <id>` row.
- `docs/guides/LOOPS_GUIDE.md:1138` — the troubleshooting entry for "Scope
  conflict error... re-run with `--queue` to wait". Cross-link to
  `queue remove` as the way to cancel a queued waiter, now that both
  `queue list` (ENH-2629) and `queue remove` are documented.

## Tests

- `scripts/tests/test_wiring_cli_registry.py:20` — extend the
  `DOC_STRINGS_PRESENT` table (append before the closing `]` at line 146) with
  presence tuples proving the doc lines landed, e.g.:
  - `("docs/reference/CLI.md", "ll-loop queue remove", "ENH-2630")`
  - `("docs/guides/LOOPS_GUIDE.md", "ll-loop queue remove", "ENH-2630")`
  This is the established convention (ENH-1963 pattern) for proving a doc-only
  change landed — extend the shared table, do not create a new test file.
- If a `[...](#anchor)` cross-reference is added at LOOPS_GUIDE.md:1138, run
  the real `ll-check-links` (no mocked pytest gate exists for this).

## Acceptance Criteria

- [ ] FEAT-2619 has merged and `cmd_queue_remove`/`remove` subparser exist.
- [ ] `docs/reference/CLI.md` has a `#### \`ll-loop queue remove <id>\`` section
      documenting the `<id>` arg spelling, exit codes, and any flags, verified
      against the merged implementation.
- [ ] `.claude/CLAUDE.md:197` `ll-loop` bullet mentions `queue remove`.
- [ ] `docs/guides/LOOPS_GUIDE.md` CLI Quick Reference table has an
      `ll-loop queue remove <id>` row, and the :1138 troubleshooting entry
      cross-links to it.
- [ ] `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_cli_registry.py` has
      presence tuples for the new strings and
      `python -m pytest scripts/tests/test_wiring_cli_registry.py` passes.

## Session Log
- `/ll:issue-size-review` - 2026-07-13T19:40:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260713-190834-subloop-epic-epic-2616-ll-loop-queue-management-cli-list-remove/ded2c90d-228f-492a-9d17-cb57f6f69ac3.jsonl`
