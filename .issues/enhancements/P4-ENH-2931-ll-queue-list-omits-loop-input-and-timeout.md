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
  unconditionally, if that reads more cleanly).
- Long values truncated to keep rows single-line; full values remain available
  via `ll-queue status <id> --json`.

## API/Interface

No new flags required. If truncation proves contentious, a `--wide` flag is the
natural escape hatch, but the default should already be informative.

## Program Design

### Signatures

- `_format_action_summary(action: ActionSpec, width: int) -> str`

  Renders `runner:target` plus a truncated args/timeout suffix.

- `cmd_list(args: argparse.Namespace) -> int`

  Existing handler; delegates row rendering to the helper.

### Call Path

`cmd_list` -> `list_entries` -> `_format_action_summary` -> stdout

## Acceptance Criteria

- [ ] `ll-queue list` distinguishes two entries that share a target but differ in
      `args.loop_input`.
- [ ] The effective `timeout` is visible in the listing.
- [ ] Long inputs are truncated rather than wrapping the row.
- [ ] `ll-queue list --json` (if present) is unchanged — this is a human-output
      change only.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: human-readable `ll-queue list` row rendering — args summary, effective
  timeout, truncation.
- **Out**: any change to `ll-queue status` output (already complete via
  `--json`); the stored `ActionSpec` schema; the timeout *default* itself
  (BUG-2928); sorting or filtering flags for the listing.

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
- `/ll:capture-issue` - 2026-07-30T21:27:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f37dc1-b451-4197-a82c-a55434adcd06.jsonl`

## Status

**Open** | Created: 2026-07-30 | Priority: P4
