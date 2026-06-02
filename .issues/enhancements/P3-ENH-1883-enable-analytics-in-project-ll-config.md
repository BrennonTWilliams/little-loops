---
id: ENH-1883
type: ENH
priority: P3
status: open
discovered_date: 2026-06-02
captured_at: "2026-06-02T23:39:38Z"
discovered_by: capture-issue
relates_to: [EPIC-1707, ENH-1833, ENH-1835, ENH-1832, ENH-1831, BUG-1881]
labels:
  - enhancement
  - captured
---

# ENH-1883: Enable `analytics.enabled` in project's own `.ll/ll-config.json`

## Summary

The project's `.ll/ll-config.json` has no `analytics` key. The `analytics.enabled` flag defaults to `False`, so `skill_events`, `file_events`, and `user_corrections` writes in `user_prompt_submit.py` and `post_tool_use.py` are gated out. EPIC-1707 consumer features (ENH-1708: corrections wired into refine-issue/ready-issue) read from tables that are never written to. This project is the primary testbed for history.db features and should have analytics enabled.

## Current Behavior

`.ll/ll-config.json` contains no `analytics` key. `feature_enabled(config, "analytics.enabled")` returns `False`. Despite all write-path infrastructure being implemented (ENH-1831–1835 all done), the following tables have 0 rows:
- `skill_events` — `/ll:` skill invocations never recorded
- `user_corrections` — correction detection never fires
- `file_events` — even when BUG-1881 is fixed, gated out here too

## Expected Behavior

`.ll/ll-config.json` includes:
```json
"analytics": {
  "enabled": true,
  "capture": {
    "skills": ["*"],
    "cli_commands": ["*"],
    "corrections": true,
    "file_events": true
  }
}
```

After this change, each `/ll:` invocation creates a `skill_events` row. User correction patterns (e.g. "no, don't do that") are detected and written to `user_corrections`. File touch events flow into `file_events` (once BUG-1881 is also fixed). ENH-1708's reads from `user_corrections` in `refine-issue`/`ready-issue` have actual data.

## Motivation

- The project uses EPIC-1707 consumer features (`ll-history-context`, corrections in confidence-check) but has zero data in the tables those features query.
- `ll-ctx-stats` always falls back to the static `.ll/ll-context-state.json` because `tool_events`/`file_events` are empty — the analytics command is not exercised in the project's own workflow.
- This is a one-line config change that unlocks the entire analytics write path without any code changes.

## Proposed Solution

Add an `analytics` block to `.ll/ll-config.json` with `enabled: true` and default-inclusive capture settings. Additionally, verify `config-schema.json` already has the `analytics` property block (FEAT-1623 was supposed to add it) so config validation doesn't reject the new key.

## Integration Map

### Files to Modify
- `.ll/ll-config.json` — add `analytics` block
- `config-schema.json` — verify `analytics` property exists; add if missing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/user_prompt_submit.py` — reads `analytics.enabled`
- `scripts/little_loops/hooks/post_tool_use.py` — reads `analytics.enabled`
- `scripts/little_loops/session_store.py` — `record_file_event` / `record_correction` / `record_skill_event`

### Tests
- Manual: invoke `/ll:ready-issue` and verify a `skill_events` row appears in `.ll/history.db`

### Configuration
- `.ll/ll-config.json` — project config
- `config-schema.json` — JSON Schema for config validation

## Implementation Steps

1. Check `config-schema.json` for an `analytics` property block; add one if absent (matching the `AnalyticsCaptureConfig` shape)
2. Add `"analytics": { "enabled": true, "capture": { "skills": ["*"], "cli_commands": ["*"], "corrections": true, "file_events": true } }` to `.ll/ll-config.json`
3. Restart session (or run `ll-session` command) to reload config
4. Invoke a skill (e.g. `/ll:help`) and verify:
   ```bash
   python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM skill_events').fetchone())"
   ```
5. Also verify `config-schema.json` validation passes: `python -m little_loops.cli.config validate` (if available)

## Impact

- **Priority**: P3 — activation gap; all infrastructure exists, this is a config flip
- **Effort**: Small — one JSON block addition + schema check
- **Risk**: Low — opt-in flag; enabling it adds write overhead per tool call / prompt submit (negligible)
- **Breaking Change**: No

## Labels

`enhancement`, `history-db`, `analytics`, `config`, `captured`

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log

- `/ll:capture-issue` - 2026-06-02T23:39:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
