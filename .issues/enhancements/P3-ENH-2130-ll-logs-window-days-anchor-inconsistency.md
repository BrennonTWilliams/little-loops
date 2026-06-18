---
id: ENH-2130
type: ENH
priority: P3
status: open
title: ll-logs --window-days anchor semantics inconsistent across subcommands
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: "2026-06-14T01:52:17Z"
parent: EPIC-1918
depends_on: [ENH-2134]
---

# ENH-2130: ll-logs --window-days anchor semantics inconsistent across subcommands

## Summary

`--window-days` computes a cutoff date relative to a reference timestamp, but that reference differs by subcommand:

- **`sequences`, `stats`, `dead-skills`**: each project/db is filtered independently using *that project's* latest timestamp as the anchor. When used with `--all`, project A's "last 30 days" and project B's "last 30 days" may refer to entirely different calendar windows.
- **`scan-failures`**: uses `latest_ts_overall`, the single latest timestamp seen across *all* projects scanned — a global anchor.

A user running `ll-logs sequences --all --window-days 30` and `ll-logs scan-failures --all --window-days 30` in the same session gets results anchored to different dates. Neither behavior is documented.

## Current Behavior

`--window-days N` anchors to different reference points depending on the subcommand:

- `sequences`, `stats`, `dead-skills`: anchor = per-project latest event timestamp. With `--all`, each project's window is computed independently against its own data, so two projects with different activity recency yield non-overlapping calendar windows for the "same" N-day filter.
- `scan-failures`: anchor = `latest_ts_overall`, the maximum timestamp across all projects scanned in a single invocation — a single shared anchor.

## Expected Behavior

`--window-days N` should use a consistent wall-clock anchor (`datetime.now(UTC) - timedelta(days=N)`) across all subcommands, so "last 30 days" always means the last 30 calendar days regardless of which subcommand is used or how many projects are scanned.

## Motivation

Predictable UX: `--window-days N` should mean the same thing across all subcommands. A user expecting "the last 30 days" should get consistent results.

## Proposed Solution

**Option A — Global anchor (align to `scan-failures` behavior)**: Use the single latest timestamp across all inputs as the anchor for all subcommands. Most intuitive for `--all` usage; slightly less precise per-project.

**Option B — Wall-clock anchor** (recommended): Anchor all subcommands to `datetime.now(UTC)` rather than data-derived timestamps. Eliminates cross-subcommand inconsistency and aligns with user mental model ("last 30 calendar days"). Requires no cross-project timestamp scan. Reuse the existing `datetime` import in `logs.py`; pass an explicit `cutoff: datetime | None` parameter down through `_extract_ll_event_streams`, `_aggregate_skill_stats`, and `_cmd_dead_skills` rather than deriving the anchor internally.

**Option C — Document the current behavior**: Add a note to the CLI docs and each subcommand's `--help` string explaining the per-project vs. global anchor distinction. Lowest change surface.

## Implementation Steps

1. Decide on the anchor strategy (recommend Option B — wall-clock is unambiguous and deterministic).
2. Update `_extract_ll_event_streams`, `_aggregate_skill_stats`, and `_cmd_dead_skills` to accept an explicit `cutoff: datetime | None` parameter rather than deriving the anchor internally.
3. In each `_cmd_*` handler, compute `cutoff = datetime.now(UTC) - timedelta(days=args.window_days)` once and pass it down.
4. Update `_cmd_scan_failures` to use the same wall-clock cutoff (remove `latest_ts_overall` anchor).
5. Update `--window-days` help strings to say "within the last N calendar days".
6. Update tests to reflect the new semantics.

## Scope Boundaries

- Out of scope: changing any other `ll-logs` flags or adding new ones
- Out of scope: changing behavior when `--window-days` is omitted (no cutoff filtering)
- Out of scope: modifying `ll-logs discover`, `extract`, `tail`, or `diff` subcommands (they do not use `--window-days`)
- Not a breaking change to the public Python API — `_extract_ll_event_streams` and related helpers are internal

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_extract_ll_event_streams`, `_aggregate_skill_stats`, `_cmd_sequences`, `_cmd_stats`, `_cmd_dead_skills`, `_cmd_scan_failures`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` is the sole consumer of its own internal helpers; no external callers use the anchor computation directly

### Similar Patterns
- All `--window-days` consumers live in `logs.py`; the fix must be consistent across all six functions above

### Tests
- `scripts/tests/test_ll_logs.py` — tests for `sequences`, `stats`, `dead-skills`, `scan-failures` subcommands that mock or assert on time-windowed output

### Documentation
- `docs/reference/CLI.md` — `ll-logs` section; `--window-days` help strings in each affected `_cmd_*` handler

### Configuration
- N/A

## Impact

- **Priority**: P3 — Behavioral inconsistency; primarily affects multi-project `--all` usage where different projects have different last-active timestamps. Not blocking.
- **Effort**: Small — Refactor of anchor derivation in ~5 functions within a single file; no new infrastructure required.
- **Risk**: Low — Semantic change to `--window-days` (wall-clock vs. data-derived); help text update documents the new behavior. No external API contracts affected.
- **Breaking Change**: Yes (semantic) — Users relying on the per-project or global-max anchor behavior will see different filter boundaries after this change.

## Labels

`cli`, `ll-logs`, `ux-consistency`

## Verification Notes

2026-06-18 (ACCURATE): Confirmed in `cli/logs.py`. `_extract_ll_event_streams` (line 276-278) and `_aggregate_skill_stats` (lines 701-704) both use per-project latest event timestamp as the `--window-days` anchor. `_cmd_scan_failures` (lines 1046-1049) uses `latest_ts_overall` — the global max across all projects scanned. Option B (wall-clock anchor) not yet implemented.

## Status

**Open** | Created: 2026-06-14 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-14T02:30:10 - `1f6a8dcb-a399-44be-a092-c05f684e7ce2.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:32 - `2a5cb136-c2a6-4327-b4ad-e6deaff58e4f.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
