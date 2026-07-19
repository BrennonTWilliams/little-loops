---
id: ENH-2697
type: ENH
priority: P3
status: done
captured_at: 2026-07-13 19:40:00+00:00
completed_at: '2026-07-14T19:41:34Z'
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
This was the blocked half of ENH-2620. FEAT-2619 (`status: done`) has merged:
`cmd_queue_remove` now lives at `scripts/little_loops/cli/loop/queue.py:116`
and the `remove` subparser is wired in `scripts/little_loops/cli/loop/__init__.py:978`.
This issue is now unblocked.

## Parent Issue

Decomposed from ENH-2620: Document `ll-loop queue` subcommand family. The
`queue list` portion is tracked separately in ENH-2629 (unblocked, ships
first). This child covers only `queue remove`.

## Dependency

FEAT-2619 (`ll-loop queue remove <id>`) has merged. Document the CLI surface
exactly as implemented. Confirmed against `cmd_queue_remove()`
(`scripts/little_loops/cli/loop/queue.py:116`):
- `<id>` arg accepts a full uuid **or** an 8+-char prefix (resolved via
  `_resolve_queue_entries`)
- Exit codes: `0` on success (entry deleted), `1` for unknown **or** ambiguous id
- Flags: `--force` (bypass psutil identity check) and `--json`

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

- [x] FEAT-2619 has merged and `cmd_queue_remove`/`remove` subparser exist.
- [x] `docs/reference/CLI.md` has a `#### \`ll-loop queue remove <id>\`` section
      documenting the `<id>` arg spelling, exit codes, and any flags, verified
      against the merged implementation.
- [x] `.claude/CLAUDE.md:197` `ll-loop` bullet mentions `queue remove`.
- [x] `docs/guides/LOOPS_GUIDE.md` CLI Quick Reference table has an
      `ll-loop queue remove <id>` row, and the :1138 troubleshooting entry
      cross-links to it.
- [x] `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_cli_registry.py` has
      presence tuples for the new strings and
      `python -m pytest scripts/tests/test_wiring_cli_registry.py` passes.

## Resolution

Documented `ll-loop queue remove <id>` across all four surfaces, verified against
`cmd_queue_remove()` (`scripts/little_loops/cli/loop/queue.py:116`):
- `docs/reference/CLI.md` — new `#### \`ll-loop queue remove <id>\`` section after
  `queue list`, covering the uuid/8+-char-prefix `<id>` spelling, `0`/`1` exit codes
  (unknown or ambiguous id), `--force`/`--json` flags, the always-delete-on-SIGTERM
  behavior, and a cross-link to the shared `#queue-entries-loopsqueue` schema.
- `.claude/CLAUDE.md:197` — appended `queue remove` to the `ll-loop` bullet.
- `docs/guides/LOOPS_GUIDE.md` — CLI Quick Reference row plus a troubleshooting
  cross-link from the scope-conflict entry.
- `scripts/tests/test_wiring_cli_registry.py` — three `DOC_STRINGS_PRESENT` presence
  tuples (`ENH-2630`); `python -m pytest scripts/tests/test_wiring_cli_registry.py`
  passes (107 passed).

## Session Log
- `/ll:ready-issue` - 2026-07-14T19:12:32 - `7a7b9b41-71ed-40f8-8c3a-382543b2433e.jsonl`
- `/ll:issue-size-review` - 2026-07-13T19:40:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260713-190834-subloop-epic-epic-2616-ll-loop-queue-management-cli-list-remove/ded2c90d-228f-492a-9d17-cb57f6f69ac3.jsonl`
