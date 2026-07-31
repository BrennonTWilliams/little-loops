---
id: ENH-2931
title: "`ll-queue list` omits `loop_input` and `timeout`, hiding what an entry will actually do"
type: ENH
status: open
priority: P4
captured_at: '2026-07-30T21:27:49Z'
discovered_date: 2026-07-30
discovered_by: capture-issue
relates_to:
- BUG-2928
- FEAT-2682
- FEAT-2930
labels:
- queue
- cli
- dx
---

# ENH-2931: `ll-queue list` omits `loop_input` and `timeout`

## Summary

`ll-queue list` renders id, priority, status, `runner:target`, and enqueue time
— but not the entry's `args` or `timeout`. Four entries that each carry a
different `--input` are displayed identically, so the listing can't be used to
confirm what was queued.

## Motivation

The omission is actively misleading rather than merely terse. Four `autodev`
entries queued with distinct `--input` values render as four identical
`loop:autodev` rows:

```
173dffa0  P3  pending  loop:autodev  2026-07-30T20:30:10Z
2c537be6  P3  pending  loop:autodev  2026-07-30T20:30:44Z
2103b6ba  P3  pending  loop:autodev  2026-07-30T20:31:08Z
5fabca33  P3  pending  loop:autodev  2026-07-30T20:31:10Z
```

During triage this listing led to an incorrect conclusion that the entries had
been enqueued without input at all; only `ll-queue status <id> --json` revealed
the `args.loop_input` values were present and correct. The same blind spot hides
the `timeout: 120` default that BUG-2928 identifies as fatal for LOOP entries —
both facts an operator needs, and neither visible without per-entry drilldown.

## Current Behavior

`cmd_list` (`cli/queue.py:121`) prints one line per entry containing the short
id, priority tier, status, `runner.value:target`, and `enqueued_at`. The
`ActionSpec`'s `args` dict and `timeout` are stored in the DB and returned by
`ll-queue status --json`, but never surfaced in the listing.

## Expected Behavior

The listing shows enough to distinguish entries from one another:

- A compact rendering of the entry's meaningful `args` — at minimum
  `loop_input` for `LOOP` entries — appended to the `runner:target` column.
- The effective `timeout`, at least when it differs from the runner default (or
  unconditionally, if that reads more cleanly). Post-BUG-2928 the `LOOP` default
  is unbounded, so render that as `timeout=∞` (or `none`) rather than omitting
  it — "no timeout" is the fact an operator most needs to see.
- Elapsed time for entries in `running` status, computed against
  `enqueued_at`'s successor timestamp. This is the same row-rendering change and
  it is the only thing that makes a stuck-forever `LOOP` entry visible at a
  glance now that BUG-2928 removed the `LOOP` subprocess timeout — without it a
  hung entry and a healthy long-running one are indistinguishable in the
  listing. See the note under Program Design about the missing claim timestamp.
- Long values truncated to keep rows single-line; full values remain available
  via `ll-queue status <id> --json`.

## API/Interface

`--wide` disables truncation. No other new flags.

```
ll-queue list [--json] [--wide]
```

## Program Design

### Signatures

- `_ARGS_SUMMARY_WIDTH: int = 40` (module constant)

  Truncation budget for the args suffix. **Deliberately a constant, not
  `shutil.get_terminal_size()`** — terminal detection makes row output
  environment-dependent and the assertions in the new tests would then pass or
  fail based on the harness's TTY width. `--wide` bypasses the constant rather
  than raising it.

- `_format_action_summary(action: ActionSpec, *, wide: bool = False) -> str`

  Renders `runner:target` plus an args/timeout suffix, truncated to
  `_ARGS_SUMMARY_WIDTH` unless *wide*.

- `cmd_list(args: argparse.Namespace) -> int`

  Existing handler; delegates row rendering to the helper.

### Call Path

`cmd_list` -> `list_entries` -> `_format_action_summary` -> stdout

### Note: elapsed time needs a claim timestamp

`queue_entries` (`queue_store.py:106`) stores `enqueued_at` but no
`claimed_at`, so "how long has this been running" is not currently derivable —
`enqueued_at` measures wait time, not run time. FEAT-2930 proposes adding
`claimed_at`/`owner_pid` for its stale-entry reclaim. If FEAT-2930 lands first,
render true elapsed run time from `claimed_at`; if this issue lands first,
render elapsed-since-`enqueued_at` labelled as such (`queued 4m ago`) and
upgrade the label when the column arrives. Do not add the column here — that is
FEAT-2930's schema change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale anchor**: `cmd_list` is currently at `cli/queue.py:165` (the row-print
  loop at `:181-189`), not `:121` as stated under Current Behavior — line
  numbers have drifted since this issue was captured. `cmd_status` is at
  `:225`, `_classify_action` at `:56`, `_default_timeout_for` at `:33`,
  `_run_loop_entry` at `:280`, `cmd_run` at `:318`.
- **Reuse candidate for the elapsed-time column**: `format_relative_time(seconds: float) -> str`
  already exists at `cli/output.py:220` and renders exactly the `"4m ago"`
  shape this issue's Expected Behavior calls for (`"Xs ago"` / `"Xm ago"` /
  `"Xh ago"` / `"Xd ago"` tiers). It's already reused elsewhere via a
  suffix-stripping wrapper (`ctx_stats.py:_time_gained`) rather than
  reimplemented — `_format_action_summary` should import and call it directly
  on `(datetime.now(timezone.utc) - datetime.fromisoformat(entry.enqueued_at)).total_seconds()`
  rather than writing a new "time ago" helper.
- **`ActionSpec`** is defined at `runner_spec.py:78-90` (`args: dict[str, Any]`,
  `timeout: int | None = 120`). The dataclass-level `120` default is never
  actually relied on for LOOP entries — `_classify_action` always resolves
  `timeout` explicitly via `_default_timeout_for` before constructing the
  spec, so a stored `ActionSpec.timeout` of `None` unambiguously means "LOOP,
  no override" rather than an unresolved default.
- **Existing truncation-helper convention**: every other `cli/` list-rendering
  module defines its own local `_truncate*`/`_cell` helper rather than
  importing a shared one (`issues/list_cmd.py:_truncate_title`,
  `loop/layout.py:_truncate_to_width`, `issues/show.py:_truncate_to_width`,
  `issues/refine_status.py:_truncate`, `output.py:table()`'s inline `_cell`).
  `output.py:table()` already defaults `max_col_width=40`, matching this
  issue's proposed `_ARGS_SUMMARY_WIDTH = 40` — a module-local constant in
  `cli/queue.py` (rather than importing one of the above) is consistent with
  how every other list command in this codebase does it.
- **Flag-naming precedent**: two existing list subcommands (`ll-issues list`,
  `ll-loop list`) already use `--no-truncate` for "show untruncated"; `--wide`
  (as specified in API/Interface above) is a new name not used elsewhere in
  the CLI surface. Noting for awareness only — not changing the issue's
  already-decided `--wide` flag name.
- **Test target**: `scripts/tests/test_cli_queue.py:207`,
  `class TestCmdList` — existing tests patch `sys.argv`, call `main_queue()`,
  and read `capsys.readouterr()` (substring match for human output,
  `json.loads(...)` for `--json`); the `_isolate_cwd` autouse fixture
  (`test_cli_queue.py:20`) gives each test its own `.ll/queue.db` via
  `monkeypatch.chdir(tmp_path)`. New tests for `loop_input`/`timeout`/elapsed-time
  rendering and the `--json` no-regression AC should extend this class
  directly rather than adding a parallel test module.

## Acceptance Criteria

- [ ] `ll-queue list` distinguishes two entries that share a target but differ in
      `args.loop_input`.
- [ ] The effective `timeout` is visible in the listing, including an explicit
      rendering for the unbounded `LOOP` default.
- [ ] A `running` entry's row shows elapsed time.
- [ ] Long inputs are truncated rather than wrapping the row; `--wide` emits the
      untruncated value.
- [ ] Truncation width does not vary with terminal size (no
      `get_terminal_size()` call on the listing path).
- [ ] `ll-queue list --json` output is byte-identical to pre-change — this is a
      human-output change only. (`--json` exists today at `cli/queue.py:170`;
      this is a firm no-regression assertion, not a conditional one.)
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: human-readable `ll-queue list` row rendering — args summary, effective
  timeout, elapsed-time column, truncation, `--wide`.
- **Out**: any change to `ll-queue status` output (already complete via
  `--json`); the stored `ActionSpec` schema; the `claimed_at`/`owner_pid`
  columns (FEAT-2930); the timeout *default* itself (BUG-2928); sorting or
  filtering flags for the listing.

## Sequencing

**Implement this before FEAT-2930**, despite the P4-vs-P2 ordering that
`ll-auto` would otherwise apply. Both issues edit row rendering in
`cli/queue.py`, and FEAT-2930's per-entry progress line (`cmd_run`,
`cli/queue.py:~370`) prints the same `runner:target` fragment. Landing this
first means FEAT-2930 calls `_format_action_summary` instead of introducing a
third hand-built copy of the format. This issue is ~30 lines and has no
dependencies.

## Impact

Low severity, real cost: the gap caused a live misdiagnosis of correctly-queued
entries. Small, self-contained display change.

**Effort**: Small. **Risk**: Low — human-readable output only, no schema or
dispatch behavior touched.

## Related

- **BUG-2928** — the timeout defect this listing hides; that issue's Proposed Fix
  originally carried this display gap as a secondary item, now split out here so
  it has a single owner
- **FEAT-2682** — established the listing format

## Session Log
- `/ll:refine-issue` - 2026-07-30T23:58:31 - `9b52783e-0bad-43ac-ab91-23ced0cc7008.jsonl`
- `/ll:capture-issue` - 2026-07-30T21:27:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f37dc1-b451-4197-a82c-a55434adcd06.jsonl`
- Pre-implementation review - 2026-07-30 - confirmed `ll-queue list --json` exists (`cli/queue.py:170`), so the no-regression AC is now unconditional. Pinned truncation to a module constant rather than terminal width (test determinism) and added `--wide`. Added an elapsed-time column for `running` entries — the only visibility into a wedged `LOOP` entry now that BUG-2928 removed its timeout — with a note that true run-time needs FEAT-2930's `claimed_at`. Marked as implement-before-FEAT-2930 despite the P4/P2 ordering.

## Status

**Open** | Created: 2026-07-30 | Priority: P4
