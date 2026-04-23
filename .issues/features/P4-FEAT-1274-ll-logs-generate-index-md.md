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
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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
  - **Note**: this file does not exist yet; it is created by FEAT-1271. Implement FEAT-1271 → FEAT-1273 → FEAT-1274 in order.

### Similar Patterns
- `scripts/little_loops/issue_history/doc_synthesis.py:301-315` — canonical markdown table pattern (header row → `|---|` separator → f-string data rows → `"\n".join(lines)`)
- `scripts/little_loops/issue_history/formatting.py:565-595` — second markdown table example

### Tests
- `scripts/tests/test_ll_logs.py` — add `TestGenerateIndex` or extend `TestExtract`
  - **Note**: this file does not exist yet; it is created by FEAT-1271.
  - `_write_jsonl` helper pattern: `scripts/tests/test_user_messages.py:109-113` (instance method — define it on `TestExtract`, not as a standalone function)
- Optionally add `TestMainLogsIntegration` to `scripts/tests/test_cli.py:2590+` — use `TestMainHistoryCoverage` (lines 2590-2698 in that file) as the structural template; it's a closer match than `test_issue_history_cli.py:71-137` [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py:77, 192` — `test_readme_tool_count_is_16` asserts `"16 CLI tools"` in `README.md`; will break when `ll-logs` is registered (count becomes 17) — update in FEAT-1271/FEAT-1005 scope [Agent 3 finding]
- `scripts/tests/test_create_extension_wiring.py:198` — `test_configure_areas_count_is_15` asserts `"Authorize all 15"` in `skills/configure/areas.md`; same cascading break — update in FEAT-1006 scope [Agent 3 finding]

### Documentation
(*All tracked in FEAT-1004/FEAT-1005 — not in scope here*)
- `.claude/CLAUDE.md`, `commands/help.md`, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**JSONL reading — stream-parse with error handling** (`scripts/little_loops/user_messages.py:436-454`):
- Outer `try/except OSError: continue` wraps each file; inner `try/except json.JSONDecodeError: continue` inside the line loop
- Call `line.strip()` before the empty-line guard
- Access timestamp via `record.get("timestamp")`; session id via `record.get("sessionId", "")`

**Agent-file exclusion when globbing JSONL** (`scripts/little_loops/session_log.py:78`):
- `[f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]`
- Apply this filter when collecting JSONL files under each project slug subdir

**Directory iteration pattern** (`scripts/little_loops/parallel/orchestrator.py:247-248`):
- `for item in logs_dir.iterdir(): if item.is_dir(): ...`
- Each subdir name is the project slug; no sorted() required unless deterministic output matters

**`setdefault` grouping** (`scripts/little_loops/doc_counts.py:258-261`):
- Only needed if per-session bucketing is required for deduplication; for date-range calculation a simple `min`/`max` over all timestamps in the subdir suffices

**Write output file** (`scripts/little_loops/cli/history.py:272-275`):
- `output_path.parent.mkdir(parents=True, exist_ok=True)` then `output_path.write_text(content, encoding="utf-8")`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. When ll-logs registration is complete (FEAT-1271), update `scripts/tests/test_create_extension_wiring.py` — change `"16 CLI tools"` → `"17 CLI tools"` (lines 77, 192) and `"Authorize all 15"` → `"Authorize all 16"` (line 198)

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-23_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1271 is backlog**: `scripts/little_loops/cli/logs.py` and `scripts/tests/test_ll_logs.py` do not exist yet — both are created by FEAT-1271. This issue cannot be implemented until FEAT-1271 is done.
- **FEAT-1273 is backlog**: The `extract` subcommand dispatch block (where `generate_index()` is called) is implemented by FEAT-1273. FEAT-1274 extends that block — required sequencing: FEAT-1271 → FEAT-1273 → FEAT-1274.

## Session Log
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7bd7f20-2f58-4e9f-b4e6-e50990bfbd10.jsonl`
- `/ll:wire-issue` - 2026-04-23T16:30:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7bd7f20-2f58-4e9f-b4e6-e50990bfbd10.jsonl`
- `/ll:refine-issue` - 2026-04-23T16:26:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1447f80b-a52b-410a-bd33-db465a58f851.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/965334bc-43d3-43d2-add7-d5f59631e49a.jsonl`

---

## Status

**Open** | Created: 2026-04-23 | Priority: P4
