---
id: FEAT-1274
type: FEAT
priority: P4
status: backlog
title: "ll-logs: generate logs/index.md after extraction"
discovered_date: 2026-04-23
discovered_by: issue-size-review
decision_needed: false
parent_issue: FEAT-1272
---

# FEAT-1274: ll-logs: generate logs/index.md after extraction

## Summary

After `ll-logs extract` (FEAT-1273) writes JSONL files to `logs/`, generate a `logs/index.md` markdown table summarising each project: name, JSONL count, and date range derived from `timestamp` fields.

## Parent Issue
Decomposed from FEAT-1272: ll-logs: extract subcommand and logs/index.md generation

## Depends On
- FEAT-1273 — `extract` subcommand must exist and write `logs/<slug>/` directories before index generation is meaningful

## Current Behavior

No `logs/index.md` is generated after extraction.

## Expected Behavior

`ll-logs extract` (any flag variant) produces `logs/index.md`:

```markdown
# Logs Index

| Project | Sessions | Date Range |
|---|---|---|
| little-loops | 5 | 2026-01-01 – 2026-04-23 |
| my-other-project | 2 | 2026-03-10 – 2026-04-20 |
```

## Implementation Steps

1. **Implement `generate_index(logs_dir: Path) -> None`** in `logs.py`:
   - Iterate `logs_dir` subdirs (each is a project slug)
   - For each subdir, collect JSONL files; for each file stream-parse records to extract `timestamp` fields
   - Aggregate: project name, JSONL count, earliest/latest timestamp
   - Write `logs/index.md` using canonical markdown table pattern:
     - Header row, `|---|` separator, f-string data rows (see `issue_history/doc_synthesis.py:301-315`)
     - `"\n".join(lines)` with blank lines surrounding block
   - No existing CLI-layer `index.md` generator — write fresh

2. **Call `generate_index()`** from the `extract` subcommand dispatch block (after JSONL files written)

3. **Tests** — add to `class TestExtract` in `scripts/tests/test_ll_logs.py`:
   - Verify `logs/index.md` is created after extraction
   - Verify markdown table contains expected project name, JSONL count, and date range
   - Test with empty `logs/` dir (edge case)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `generate_index()` and call it from `extract` dispatch

### Similar Patterns
- `scripts/little_loops/issue_history/doc_synthesis.py:301-315` — canonical markdown table pattern (header row → `|---|` separator → f-string data rows → `"\n".join(lines)`)
- `scripts/little_loops/issue_history/formatting.py:565-595` — second markdown table example

### Tests
- `scripts/tests/test_ll_logs.py` — add `TestGenerateIndex` or extend `TestExtract`
- Optionally add `TestMainLogsIntegration` to `scripts/tests/test_cli.py:2590+` following `test_issue_history_cli.py:71-137` pattern

### Documentation
(*All tracked in FEAT-1004/FEAT-1005 — not in scope here*)
- `.claude/CLAUDE.md`, `commands/help.md`, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md`

## Acceptance Criteria

- [ ] `logs/index.md` is created after any `ll-logs extract` invocation
- [ ] Index contains a markdown table with project name, JSONL count, and date range
- [ ] Edge case: empty `logs/` directory produces an empty or stub index
- [ ] Tests pass

## Impact

- **Priority**: P4 - utility tooling
- **Effort**: Small — ~20-30 LOC + tests
- **Risk**: Low — additive; standalone helper function
- **Breaking Change**: No

---

## Session Log
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/965334bc-43d3-43d2-add7-d5f59631e49a.jsonl`

---

## Status

**Open** | Created: 2026-04-23 | Priority: P4
