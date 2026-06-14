---
id: ENH-2070
title: Wire scan-failures --capture as automated bug intake
type: ENH
priority: P3
status: open
discovered_date: "2026-06-10"
discovered_by: capture-issue
captured_at: "2026-06-10T15:59:33Z"
labels: [ll-logs, automation, scan-failures, bug-intake, telemetry]
parent: EPIC-1918
relates_to: [EPIC-1918]
---

# ENH-2070: Wire scan-failures --capture as automated bug intake

## Summary

`ll-logs scan-failures` already mines failure clusters from session logs but nothing converts them into issue files automatically. Over the past 30 days, 146+ failure events across multiple clusters produced zero bug issues. Wiring `scan-failures --capture` into a cron job or pre-session hook would auto-create bug issues from observed failure patterns with no manual intervention required.

## Motivation

The gap between "failure happens" and "bug issue exists" is currently infinite unless someone manually runs `ll-logs scan-failures`. Automating this closes the feedback loop and surfaces real regressions (like BUG-2069) the same session they accumulate enough signal.

## Implementation Steps

1. **Evaluate hook vs. cron placement**: session_start hook runs per-session (high frequency, low latency); a `/schedule` cron runs independently (better for batch). Recommend session_start with a recency guard (skip if last run < 24h ago via a sentinel file in `.ll/`).
2. **Add `scan-failures` step to session_start hook** (or a new `daily-intake` cron loop):
   - Run `ll-logs scan-failures --project . --window-days 7 --capture -j`
   - The `--capture` flag writes one issue file per new cluster; skip clusters already in `.issues/`
   - Log how many new issues were created to session_start output
3. **Dedup guard in `--capture`**: verify the flag checks existing issue IDs or titles before writing, to avoid re-creating already-captured failures across sessions
4. **Surfacing in session_start output**: include a one-line summary ("3 new failure clusters captured as bug issues") in the `project_context` block

## API/Interface

```bash
# Session_start hook addition (pseudo-code):
SENTINEL=".ll/.scan-failures-last-run"
if [ ! -f "$SENTINEL" ] || [ "$(find "$SENTINEL" -mtime +1)" ]; then
    ll-logs scan-failures --project . --window-days 7 --capture 2>/dev/null || true
    touch "$SENTINEL"
fi
```

## Acceptance Criteria

- Running a session the day after new failure clusters accumulate automatically produces `P2-BUG-*` issue files
- Existing issues are not duplicated across sessions
- Session_start output includes count of newly captured issues (or is silent when count = 0)

## Success Metrics

- **Auto-capture rate**: 0 auto-created bug issues/month → failure clusters captured within one session cycle (≤24h lag)
- **Duplicate suppression**: 0 duplicate issues created across repeated sessions (dedup guard verified)
- **Session start latency**: Sentinel guard keeps added latency < 1s when last run < 24h ago

## Scope Boundaries

- **In scope**: session_start hook integration with recency sentinel, `ll-logs scan-failures --capture` dedup logic, count reporting in `project_context` block
- **Out of scope**: changes to the manual scan-failures workflow, historical backfill of pre-existing failures, modifying failure-cluster detection heuristics

## Integration Map

### Files to Modify
- `hooks/adapters/claude-code/session-start.sh` — add sentinel-guarded `ll-logs scan-failures --capture` call
- `scripts/little_loops/hooks/session_start.py` — wire scan count into `project_context` output

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "scan.failures\|scan_failures" scripts/`

### Similar Patterns
- TBD - search for existing sentinel patterns: `grep -r "last-run\|sentinel" hooks/`

### Tests
- TBD - identify test files to update (likely `scripts/tests/test_builtin_loops.py` or session_start tests)

### Documentation
- TBD - docs that may need updates

### Configuration
- `.ll/.scan-failures-last-run` sentinel file (created at runtime, gitignored)

## Verification Notes

2026-06-13: Integration Map path corrected. `hooks/prompts/session_start.md` does not exist; correct targets are `scripts/little_loops/hooks/session_start.py` and `hooks/adapters/claude-code/session-start.sh`. `ll-logs scan-failures` confirmed present in logs.py.

## Session Log
- `/ll:verify-issues` - 2026-06-14T00:12:40 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:58 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:format-issue` - 2026-06-10T16:05:08 - `6facc3ad-9141-4c37-9e24-3adbe7fc2e43.jsonl`

- `/ll:capture-issue` - 2026-06-10T15:59:33Z - surfaced via conversation analysis of `ll-logs scan-failures` output
