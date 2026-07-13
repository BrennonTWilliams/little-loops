---
id: FEAT-2618
type: FEAT
priority: P3
status: done
captured_at: 2026-07-12 19:49:49+00:00
completed_at: '2026-07-13T18:10:15Z'
discovered_date: 2026-07-12
discovered_by: scope-epic
parent: EPIC-2616
depends_on:
- ENH-2617
confidence_score: 100
outcome_confidence: 89
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 24
---

# `ll-loop queue list` subcommand

## Summary

Add `ll-loop queue list` to show pending entries in the process-backed run
queue (`.loops/.queue/*.json`) — id, loop name, PID, liveness, and enqueued
time — with a `--json` output mode, using the shared queue-entry helper from
ENH-2617.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Dependency status**: ENH-2617 (the shared helper) is **done** (completed
2026-07-13, commit `ff06492a`). `read_queue_entries()` already exists and is the
intended consumer point for this subcommand — no helper work remains.

**The shared helper** — `read_queue_entries(queue_dir: Path) -> list[dict]` at
`scripts/little_loops/cli/loop/_helpers.py:172-200`:
- Returns `[]` if `queue_dir` doesn't exist.
- Loads every `*.json`, prunes entries whose `context.pid` fails
  `_process_alive()` (unlinks the file as a side effect — BUG-1360), silently
  skips malformed/unreadable files.
- Returns entries **sorted ascending by `enqueuedAt`** (ISO-8601 string → lexical
  sort is chronological). Its docstring names `ll-loop queue` subcommands as the
  intended reuse target.
- **Liveness caveat**: because dead-PID entries are pruned during the read, every
  entry `read_queue_entries()` returns is by construction *live*. A `list` display
  showing a "liveness" column that reads from `read_queue_entries()` alone would
  always show "alive". To surface dead/stale entries in the listing, the command
  must read raw `*.json` files directly (bypassing the pruning helper) OR the
  helper's pruning suffices and "liveness" is implicitly always-live. **This is a
  design point to resolve during implementation** (see Open Questions).

**Queue entry JSON schema** (written by `run.py:353-369`, file named
`{uuid}.json`):
```json
{
  "id": "<uuid4>",
  "loopName": "<fsm.name of the waiting loop>",
  "enqueuedAt": "<ISO-8601 UTC, datetime.now(UTC).isoformat()>",
  "context": {
    "waitingFor": "<loop_name holding the conflicting lock>",
    "scope": "<contended scope string>",
    "pid": <int, os.getpid()>
  }
}
```
Fields the summary asks for map as: id → `id`, loop name → `loopName`, PID →
`context.pid`, liveness → derived via `_process_alive(context.pid)`, enqueued
time → `enqueuedAt`.

**PID liveness** — `_process_alive(pid)` at
`scripts/little_loops/fsm/concurrency.py:56-68` (classic `os.kill(pid, 0)` probe;
`ESRCH`=dead, `EPERM`/other=alive).

**No `queue` subcommand exists yet.** `ll-loop` uses a *flat* argparse verb tree
(no nested `<group> <verb>` precedent in `cli/loop/__init__.py`). Because the epic
adds both `queue list` (this issue) and `queue remove` (FEAT-2619), the natural
shape is a nested subparser group — model it on `ll-issues decisions <verb>`
(the codebase's existing two-level pattern), since `ll-loop` has none.

**`--json` output convention** — mirror `cmd_list()` in
`scripts/little_loops/cli/loop/info.py:102`: check `getattr(args, "json", False)`
early, short-circuit **before** any human-readable/color rendering, emit via
`print_json()` (`scripts/little_loops/cli/output.py:213`, a plain
`json.dumps(data, indent=2)`). Empty-result case prints `print_json([])` in JSON
mode vs. a friendly message otherwise. Timestamp display convention:
`enqueuedAt[:19].replace("T", " ")` (from `_list_archived_runs`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — register the `queue` subcommand:
  add `"queue"` to the `known_subcommands` set (lines 53-84) so
  `ll-loop queue list` isn't misparsed as a bare loop-name shorthand; add
  `subparsers.add_parser("queue", ...)` with a nested `add_subparsers` for the
  `list` verb (and a `-j/--json` flag on `list`); add an
  `elif args.command == "queue":` dispatch branch (near lines 895-936) calling the
  new command function; import that function inside the `cli_event_context` block
  (lines 25-40).

### Files to Create
- `scripts/little_loops/cli/loop/queue.py` (suggested) — new module holding
  `cmd_queue_list(args, loops_dir) -> int` (and later `cmd_queue_remove` for
  FEAT-2619). Keeps the giant `__init__.py`/`info.py` from growing. Alternatively
  add `cmd_queue_list` to `info.py` alongside `cmd_list`.

### Reused (do not modify)
- `read_queue_entries()` — `scripts/little_loops/cli/loop/_helpers.py:172-200`
- `_process_alive()` — `scripts/little_loops/fsm/concurrency.py:56-68` (only if
  raw-read liveness display is chosen)
- `print_json()` — `scripts/little_loops/cli/output.py:213`

### Similar Patterns
- `cmd_list()` — `scripts/little_loops/cli/loop/info.py:102` (canonical
  human/JSON dual-output list subcommand)
- `_list_archived_runs()` — `scripts/little_loops/cli/loop/info.py:884` (status
  table with ANSI colors, timestamp truncation, footer hint)

### Tests
- `scripts/tests/test_cli_loop_queue.py` — add a `TestQueueListCommand` class.
  Existing queue tests (`TestReadQueueEntries` line 260, `TestQueueFifoOrdering`
  line 163) call helpers directly; add CLI-level tests that build a
  `.loops/.queue/` fixture (write `{uuid}.json` files) and invoke the command
  function / `main_loop()` argv, asserting on both human and `--json` output and
  the empty-queue case. Reuse the fixture idiom from `TestReadQueueEntries`
  (write `{uuid}.json` with `enqueuedAt`/`context.pid`); keep these a thin
  render-assertion layer — `read_queue_entries()` prune/sort/malformed-skip
  correctness is already fully covered by `TestReadQueueEntries`, don't re-derive it.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_dispatch.py` — **the canonical end-to-end dispatch
  test file** (`TestMainLoopDispatch`); the issue only named
  `test_cli_loop_queue.py`. Adding `"queue"` to `known_subcommands` + the new
  `elif args.command == "queue":` branch means this file needs: (1) a
  `cmd_queue_list`/`cmd_queue` entry in the `_mock_handlers()` fixture (line 26),
  keyed on the new `little_loops.cli.loop.queue` module path, and (2) a routing
  test (model on `test_list_routes_to_handler` line 161 /
  `TestMainLoopListFlagForwarding` line 854) asserting `ll-loop queue list` routes
  to the handler and `--json` is forwarded. Also add a bare-`ll-loop queue`
  (no verb) test mirroring `test_cli_decisions.py::TestDecisionsCLINoSubcommand`
  (asserts `print_help()` + return 1) to cover the two-level group's
  no-subcommand branch. [Agent 3 finding]
- `scripts/tests/test_json_output_contracts.py` — advisory: houses `--json`
  output-contract tests for `ll-loop` list commands; consider pinning the
  `queue list --json` contract here (array of plain queue-entry dicts, `[]` when
  empty) alongside the existing contracts. [Agent 3 finding]

_FYI (owned by ENH-2620, no edit in this issue):_
- `scripts/tests/test_wiring_cli_registry.py` — `DOC_STRINGS_PRESENT` (line 20) is
  a doc-sync gate; it only needs a `queue` entry once ENH-2620 adds the doc
  sections, so that update travels with the docs, not this feature. [Agent 1 finding]

### Documentation
- Handled downstream by ENH-2620 (docs for the `queue` subcommand family:
  `docs/reference/CLI.md`, `docs/guides/LOOPS_GUIDE.md`, `.claude/CLAUDE.md`). No
  doc edits required in this issue beyond what ENH-2620 covers.

## Proposed Solution

1. Add nested `queue` subparser group in
   `scripts/little_loops/cli/loop/__init__.py` with a `list` verb exposing
   `-j/--json`, plus `"queue"` in `known_subcommands`.
2. Implement `cmd_queue_list(args, loops_dir)`:
   - `queue_dir = loops_dir / ".queue"`.
   - `entries = read_queue_entries(queue_dir)` (prunes dead entries as a
     side effect, returns sorted-by-`enqueuedAt`).
   - JSON mode (`getattr(args, "json", False)`): `print_json(entries)` (entries
     are already plain dicts) — including `print_json([])` when empty — and return 0.
   - Human mode: print a header + one row per entry showing id (short),
     `loopName`, `context.pid`, liveness (see Open Questions), and a truncated
     `enqueuedAt`; friendly "Queue is empty" message when none.
3. Add `TestQueueListCommand` in `scripts/tests/test_cli_loop_queue.py`.
4. Run `python -m pytest scripts/tests/test_cli_loop_queue.py -v`.

## Acceptance Criteria

- `ll-loop queue list` prints pending queue entries (id, loop name, PID,
  liveness, enqueued time) sorted by enqueue time.
- `ll-loop queue list --json` emits a JSON array (empty array `[]` when the queue
  is empty) and no human-readable decoration.
- Empty queue prints a friendly message in human mode and `[]` in JSON mode; exit 0.
- `queue` is registered so `ll-loop queue list` is not misparsed as a loop-name
  shorthand.
- New CLI-level tests in `test_cli_loop_queue.py` cover populated, empty, and
  `--json` cases and pass under `python -m pytest scripts/tests/`.

## Open Questions

- **Liveness column semantics**: `read_queue_entries()` prunes dead-PID entries,
  so its output is always-live. Decide whether (a) the listing is fine showing
  only live entries (liveness column always "alive", simplest, reuses the helper
  as-is) or (b) `list` should raw-read `*.json` to also surface dead/stale entries
  before pruning. Recommendation: **(a)** for v1 — matches the helper's documented
  contract and keeps `list` a thin consumer; a `--stale`/`--all` flag can be added
  later if surfacing orphans proves useful.

## Resolution

Implemented `ll-loop queue list` as a nested subparser group (FEAT-2618):

- New module `scripts/little_loops/cli/loop/queue.py` with
  `cmd_queue_list(args, loops_dir)` — reads `.loops/.queue` via the shared
  `read_queue_entries()` helper (ENH-2617), which prunes dead-PID entries and
  returns them sorted by `enqueuedAt`. Renders id (short), loop name, PID,
  liveness, and truncated enqueue time; `--json`/`-j` emits the plain entry
  dicts (`[]` when empty); friendly "Queue is empty" message in human mode.
- Wired `"queue"` into `known_subcommands` and added the nested `queue list`
  subparser + dispatch branch in `cli/loop/__init__.py`. Bare `ll-loop queue`
  prints help and returns 1.
- Chose Open-Questions option (a): liveness is always "alive" since the helper
  prunes dead entries; a `--stale`/`--all` flag can surface orphans later.
- Tests: `TestQueueListCommand` in `test_cli_loop_queue.py` (empty/populated/
  `--json`/sort) and `TestMainLoopQueueDispatch` in `test_cli_loop_dispatch.py`
  (routing, `--json` forwarding, no-verb help). Full suite green.

## Session Log
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
- `/ll:refine-issue` - 2026-07-13T12:30:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7b7de1d-7aaf-454a-91a3-7ca97b3fba3b.jsonl`
- `/ll:wire-issue` - 2026-07-13T12:30:48 - session JSONL unavailable
- `/ll:manage-issue` - 2026-07-13T18:09:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a57eb810-b1eb-44db-8139-1f8ccc8244b0.jsonl`
