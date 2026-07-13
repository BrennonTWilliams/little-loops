---
id: ENH-2620
type: ENH
priority: P3
status: open
captured_at: 2026-07-12 19:49:49+00:00
discovered_date: 2026-07-12
discovered_by: scope-epic
parent: EPIC-2616
depends_on:
- FEAT-2618
- FEAT-2619
confidence_score: 73
outcome_confidence: 73
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 18
size: Very Large  # reviewed: /ll:issue-size-review 2026-07-13, decomposition declined (single coupled doc task)
---

# Document `ll-loop queue` subcommand family

## Summary

Document the new `ll-loop queue list`/`ll-loop queue remove` subcommands in
`docs/reference/API.md` and add `queue` to the `ll-loop` bullet in the CLI
Tools section of `.claude/CLAUDE.md`.

## Integration Map

### Files to Modify

- `docs/reference/CLI.md` — **primary doc target** (not just API.md). The
  `ll-loop` subcommand reference lives here as `####`-level headings (e.g.
  `#### \`ll-loop validate <loop>\``, `docs/reference/CLI.md:666`). Add two new
  `####` sections after the existing queue material — model them on the
  `#### \`ll-loop list\`` (CLI.md:697) and `#### \`ll-loop status <loop>\``
  (CLI.md:716) sections. There is already a `##### Queue entries (.loops/.queue/)`
  subsection at `docs/reference/CLI.md:643` describing the entry schema and FIFO
  ordering — the new `queue list`/`queue remove` sections should cross-reference
  it rather than duplicate the schema. Note CLI.md:664 currently says "cleanup
  tooling may want to prune entries whose pid is no longer alive" — `queue list`
  (via `read_queue_entries`) now *is* that pruning tooling; update that sentence.
- `.claude/CLAUDE.md:197` — the single `ll-loop` bullet in the CLI Tools section.
  Append `queue list`/`queue remove` to its parenthetical, matching the existing
  inline style (`promote-baseline promotes...; edit-routes renders...`).
- `docs/reference/API.md` — optional. The `ll-loop` surface is documented in
  CLI.md, not API.md; API.md covers Python module reference. Only touch API.md if
  documenting the `read_queue_entries()` helper (currently in
  `scripts/little_loops/cli/loop/_helpers.py:172`) as a public API — likely out
  of scope for a CLI-doc issue.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:834-856` — the `## CLI Quick Reference` table
  enumerates every `ll-loop` subcommand as `| Command | Description |` rows but
  has **no `queue` row** (Agent 2 finding). Add `ll-loop queue list` and
  `ll-loop queue remove <id>` rows to keep the table complete — this is the one
  additional stale-enumeration surface besides CLI.md and CLAUDE.md. Optionally
  cross-link from the `--queue` run-flag mention at LOOPS_GUIDE.md:856 ("wait on
  scope conflicts") to note that queued waiters can now be inspected/cancelled.
- `docs/reference/API.md` — reconfirmed **optional** (Agent 2): no other
  `docs/*.md`, `README.md`, `CONTRIBUTING.md`, `commands/*.md`, or
  `skills/*/SKILL.md` documents `.loops/.queue/`, the queue entry schema, or an
  exhaustive `ll-loop` subcommand list. `skills/cleanup-loops/SKILL.md` covers
  the scope-lock mechanism but does not treat queued waiters as a
  listable/removable resource, so it is thematically adjacent, not stale — no
  edit required there.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_cli_registry.py:20` — the consolidated doc-wiring
  gate (`DOC_STRINGS_PRESENT`, a hand-maintained `(doc_rel, needle, issue_id)`
  table; ENH-1963 pattern). Add presence tuples so the new doc lines are
  enforced, e.g. `("docs/reference/CLI.md", "ll-loop queue list", "ENH-2620")`,
  `("docs/reference/CLI.md", "ll-loop queue remove", "ENH-2620")`,
  `(".claude/CLAUDE.md", "queue list", "ENH-2620")`,
  `("docs/guides/LOOPS_GUIDE.md", "ll-loop queue list", "ENH-2620")` (Agent 3
  finding). This is the established convention for proving a doc-only change
  landed — extend the shared table, do **not** create a new per-feature test
  file. If any stale wording is replaced, add matching `DOC_STRINGS_ABSENT`
  tuples.
- No change needed to `scripts/tests/test_cli_loop_queue.py` (tests
  `read_queue_entries`/`_is_earliest_waiter`/`cmd_run`, unaffected by docs) or
  `scripts/tests/test_cli_docs.py` (tests the `ll-verify-docs`/`ll-check-links`
  entrypoints with mocks — it does not assert real-repo doc content or CLI
  subcommand parity). Confirmed by Agent 2/3: **no argparse-introspection or
  subcommand-count gate exists**, so adding `queue` rows to CLI.md/LOOPS_GUIDE.md
  needs no verify-docs update. If a `[...](#anchor)` cross-reference is added,
  the applicable gate is running the real `ll-check-links` (not the mocked
  pytest tests).

### Source of Truth (read before writing prose)

- `scripts/little_loops/cli/loop/_helpers.py:172` — `read_queue_entries(queue_dir)`:
  the shared helper from ENH-2617. Reads every `*.json`, **prunes (unlinks) dead-PID
  entries** (BUG-1360), skips malformed/unreadable entries, returns survivors sorted
  ascending by `enqueuedAt`. Returns `[]` when the dir is absent. Both `queue list`
  and `_is_earliest_waiter()` consume it. Document the pruning side effect: `queue
  list` mutates the queue dir (removes orphans) as a side effect of listing.
- `scripts/little_loops/cli/loop/run.py:355-369` — where entries are written
  (`<loops_dir>/.queue/<uuid>.json`), and the exact entry shape (`id`, `loopName`,
  `enqueuedAt`, `context.{waitingFor, scope, pid}`).
- `scripts/little_loops/cli/loop/__init__.py:119` — `subparsers = parser.add_subparsers(dest="command")`;
  follow the existing `add_parser(...)` + `set_defaults(command=...)` pattern (e.g.
  `list_parser` at line 339) for how the `queue` subcommand family should surface in
  `--help`. Confirm the final `queue list --json` flag and `queue remove <id>` arg
  spelling against the shipped parser once FEAT-2618/2619 land.

### Dependency Note

Blocked on **FEAT-2618** (`queue list`) and **FEAT-2619** (`queue remove <id>`) —
both must ship before this doc issue can be verified. Document the CLI surface
exactly as implemented; do not document flags/behavior that differ from the merged
code. Verify the `--json` output field names and exit codes from the final
implementation, not from this issue's assumptions.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

1. Add `ll-loop queue list` / `ll-loop queue remove <id>` rows to the
   `## CLI Quick Reference` table in `docs/guides/LOOPS_GUIDE.md:834-856`
   (previously only CLI.md and CLAUDE.md were tracked).
2. Extend `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_cli_registry.py`
   with presence tuples for the new doc strings across all three doc files, so
   `python -m pytest scripts/tests/test_wiring_cli_registry.py` enforces that the
   documentation landed.
3. Verify no anchor-based cross-references break `ll-check-links` (run the real
   CLI if a `[...](#...)` link into the new queue sections is added).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-13_

**Readiness Score**: 73/100 → STOP — ADDRESS GAPS (dependencies unmet)
**Outcome Confidence**: 73/100 → Moderate

### Gaps to Address
- FEAT-2618 (`ll-loop queue list`) is still `status: open` — the `queue` subcommand does not exist in `scripts/little_loops/cli/loop/__init__.py` yet
- FEAT-2619 (`ll-loop queue remove <id>`) is still `status: open` — same blocker
- This doc issue cannot be implemented accurately until both dependencies merge; documenting now risks describing `--json` field names/exit codes that differ from what ships

### Outcome Risk Factors
- Ambiguity axis: the exact `--json` flag shape and exit codes are explicitly unconfirmed pending FEAT-2618/FEAT-2619 landing — the issue itself flags this as a verify-against-merged-code step

## Session Log
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
- `/ll:refine-issue` - 2026-07-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e07d3b82-65ac-4d0e-9a55-4a17f6c8c8e4.jsonl`
- `/ll:wire-issue` - 2026-07-13T12:45:00 - session JSONL unresolved
- `/ll:confidence-check` - 2026-07-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260713-123048-subloop-epic-epic-2616-ll-loop-queue-management-cli-list-remove/e42e1aa3-2c95-4ce2-b812-3b8279000b31.jsonl`
- `/ll:refine-issue` - 2026-07-13T12:30:00 - session JSONL unresolved
