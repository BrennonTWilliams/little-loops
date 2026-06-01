---
id: ENH-1860
type: ENH
priority: P4
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to: [FEAT-1737]
parent: EPIC-1864
---

# ENH-1860: EPIC cascade lifecycle — propagate close/cancel to children

## Summary

When an EPIC's status is set to `cancelled` or `done`, optionally cascade the status change to its active children. Add `--cascade` and `--cascade-to <status>` flags to `ll-issues set-status` so that closing an EPIC can mark its open children `deferred` (default) or `cancelled` in one call. Default behavior remains non-cascading.

## Current Behavior

Setting `ll-issues set-status EPIC-1622 done` only updates the EPIC's frontmatter. Its active children remain `open` / `in_progress` / `blocked`, even though they are now orphans of a closed initiative. Users either leave them as stale orphans, manually close each one, or run `/ll:link-epics` later to reparent them.

`/ll:capture-issue` flips `status: done → open` when reopening, but there is no equivalent flow for "this EPIC is no longer relevant — defer its children."

## Expected Behavior

```
$ ll-issues set-status EPIC-1622 cancelled --cascade
EPIC-1622: marked cancelled
  Cascading to 4 active children (default: deferred):
    ENH-1311 → deferred
    ENH-1312 → deferred
    BUG-1320 → deferred
    FEAT-1335 → deferred
  (5 children already done/cancelled — unchanged)

$ ll-issues set-status EPIC-1622 done --cascade --cascade-to done
# closes all open children as well
```

Without `--cascade`, behavior is unchanged.

## Motivation

EPICs that get cancelled (priority shift, scope change, deprecated direction) leave a tail of stale orphan issues that pollute `ll-issues list` and confuse scan tools. Today this requires N manual `set-status` calls. The cascade flag makes the cleanup atomic and auditable.

This is a lower-leverage gap (EPICs are rarely cancelled), captured at P4 to track but not prioritize.

## Proposed Solution

1. Add `--cascade` (bool) and `--cascade-to <status>` (default: `deferred`) flags to `ll-issues set-status`.
2. Reject `--cascade` if the target status is not `done` or `cancelled` (cascade only makes sense on closure).
3. Resolve children via FEAT-1737 union path.
4. Filter to active statuses (`open`, `in_progress`, `blocked`).
5. Apply the target cascade status to each, in a transaction-style loop with per-file logging.
6. Print summary; exit non-zero if any individual file update fails (but continue the rest).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/set_status.py` (or wherever `set-status` lives) — add `--cascade` flags and child-resolution path
- `scripts/little_loops/cli/issues/__init__.py` — argparse wiring

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sprint.py` — reuse `SprintManager.load_or_resolve()` union for child resolution
- `skills/capture-issue/SKILL.md` — adjacent reopen-issue flow; pattern reference

### Similar Patterns
- `ll-issues set-status` existing single-file update — model cascade as N independent updates with shared logging
- FEAT-1737 union resolution — exact same children set

### Tests
- `scripts/tests/test_issues_cli.py:TestSetStatus` — extend
  - `--cascade` with no children → no-op, exit 0
  - `--cascade` with mix of active/done children → only active ones change
  - `--cascade --cascade-to done` → closes all open children
  - `--cascade` rejected when target status is not done/cancelled
  - One-file failure does not abort the rest

### Documentation
- `docs/reference/CLI.md` — `ll-issues set-status --cascade` flag row
- `.claude/CLAUDE.md` — Issue File Format section may mention cascade in status enum docs

### Configuration
- `epics.cascade.default_status` (default `deferred`) — overridable

## Implementation Steps

1. **Argparse extension** — `--cascade`, `--cascade-to`.
2. **Validation** — reject cascade for non-closing transitions.
3. **Child resolution** — reuse FEAT-1737 path.
4. **Apply cascade** — per-child update with try/except, accumulate results.
5. **Render summary** — counts + per-child outcomes.
6. **Tests** for each case above.
7. **Docs** update.

## Impact

- **Priority**: P4 — Low frequency (EPIC cancellation is rare); cleanup ergonomics.
- **Effort**: Small — Reuses resolution; adds a flag + loop.
- **Risk**: Low–Medium — Mass status updates, but only when explicitly opted in via flag. Default behavior preserved.
- **Breaking Change**: No

## Success Metrics

- Cancelling an EPIC with N active children completes in 1 command instead of N+1.
- No accidental cascades — flag is required.

## Scope Boundaries

- Cascade only on `done` / `cancelled` (not `open`, `in_progress`, etc.).
- Cascade does not edit child issue body or remove them — only status frontmatter.
- No automatic reparenting of children to a successor EPIC (out of scope).
- No reverse cascade (child status changes do not propagate up).

## API/Interface

```
ll-issues set-status EPIC-NNN done --cascade
ll-issues set-status EPIC-NNN cancelled --cascade --cascade-to cancelled
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `cli`, `lifecycle`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-01T17:45:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac3a8d0e-1e74-47b1-9d58-b8dbb8f453b4.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P4
