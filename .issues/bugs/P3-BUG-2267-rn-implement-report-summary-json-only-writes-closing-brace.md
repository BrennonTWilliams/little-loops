---
discovered_commit: 47a94f498645c1e35c50cc98dd4e9465e0053b04
discovered_branch: main
discovered_date: 2026-06-24T00:00:00Z
discovered_by: audit-loop-run
status: done
completed_at: 2026-06-24T00:00:00Z
---

# BUG-2267: `rn-implement` `report` state writes only `}` to `summary.json`

## Summary

The `report` state in `rn-implement.yaml` redirected only the final `printf '}\n'` call to `$RUN_DIR/summary.json`. All preceding `printf` calls (the opening brace and every field) went to stdout. The resulting file contained a single `}` and could not be parsed as JSON.

## Location

- **File**: `scripts/little_loops/loops/rn-implement.yaml`
- **Anchor**: `report` state, `action` block
- **Code (before fix)**:
```bash
printf '{\n'
printf '  "total_processed": %s,\n' "$DEQUEUE_COUNT"
# ... 10 more printf lines ...
printf '  "rate_limited": %s\n' "$RATE_LIMITED"
printf '}\n' > "$RUN_DIR/summary.json"   # only this line redirected
```

## Root Cause

The `>` redirect was attached only to the last `printf` in a sequence of 13. The rest wrote to stdout (captured in `events.jsonl`) but never to the file.

## Impact

- `summary.json` was always `}` — unreadable as JSON.
- No data loss: all values appeared in the `action_output` event stream in `events.jsonl`.
- Downstream tooling or human review relying on `summary.json` would fail to parse it.

## Fix

Wrapped the entire `printf` block in a grouped command redirect so all output goes to `summary.json`:

```bash
{
  printf '{\n'
  printf '  "total_processed": %s,\n' "$DEQUEUE_COUNT"
  # ...
  printf '}\n'
} > "$RUN_DIR/summary.json"
```

Applied in this session; no tests required (shell correctness only).

## Detection

Surfaced by an external `audit-loop-run` audit of a downstream project that forked from little-loops — the same bug was present verbatim in both copies.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-24T21:50:23 - `03694585-2be6-4c43-b1bc-ab818355eb3c.jsonl`
