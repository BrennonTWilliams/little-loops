---
id: FEAT-1274
type: FEAT
priority: P4
status: done
title: "ll-logs: generate logs/index.md after extraction"
discovered_date: 2026-04-23
discovered_by: issue-size-review
decision_needed: false

confidence_score: 95
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
captured_at: 2026-04-23T00:00:00Z
completed_at: 2026-04-23T22:01:09Z
parent: FEAT-1272
---

# FEAT-1274: ll-logs: generate logs/index.md after extraction

## Summary

After `ll-logs extract` (FEAT-1273) writes JSONL files to `logs/`, generate a `logs/index.md` markdown table summarising each project: name, JSONL count, and date range derived from `timestamp` fields.

## Motivation

After `ll-logs extract`, JSONL files are written to `logs/<slug>/` directories but there is no at-a-glance summary of what was extracted. Users must manually `ls` and inspect files to understand which projects were captured and their activity span. A generated `logs/index.md`:
- Provides immediate visibility into extracted projects, session counts, and date ranges
- Eliminates manual directory inspection after extraction
- Small additive change (~20-30 LOC) with high discoverability value

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

## Use Case

**Who**: Developer running `ll-logs extract` on their Claude Code project

**Context**: After extracting conversation logs into `logs/<slug>/` JSONL files, they want a quick summary of what was captured without manually inspecting directories

**Goal**: See which projects were extracted, how many sessions each has, and the date range of activity

**Outcome**: `logs/index.md` is created automatically — a markdown table with project name, JSONL count, and date range

## Implementation Steps

1. **Implement `generate_index(logs_dir: Path) -> None`** in `logs.py`:
   - Iterate `logs_dir` subdirs (each is a project slug)
   - For each subdir, collect JSONL files; for each file stream-parse records to extract `timestamp` fields
   - Aggregate: project name, JSONL count, earliest/latest timestamp
   - Write `logs/index.md` using canonical markdown table pattern:
     - Header row, `|---|` separator, f-string data rows (see `issue_history/doc_synthesis.py:301-315`)
     - `"\n".join(lines)` with blank lines surrounding block
   - No existing CLI-layer `index.md` generator — write fresh

2. **Call `generate_index()`** from `_cmd_extract()` at `logs.py:207` — insert just before the `return 0`, after the per-project JSONL write loop ends (`logs.py:199-205`); pass `Path.cwd() / "logs"` as `logs_dir` (consistent with `out_base` construction at `logs.py:199`)

3. **Tests** — extend `class TestExtract` in `scripts/tests/test_ll_logs.py` (lines 453-689):
   - Use `_make_project_dir()` helper at lines 456-492 to set up the `logs/<slug>/` fixture
   - Verify `logs/index.md` is created after `extract --all` or `extract --project`
   - Verify markdown table contains expected project name, JSONL count, and date range
   - Test with empty `logs/` dir (edge case — should produce empty or stub index)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `generate_index()` and call it before `return 0` at line 207 in `_cmd_extract()` (lines 151-207)
  - File exists (331 lines); FEAT-1271 and FEAT-1273 are already implemented and registered

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` (extract subcommand dispatch) — calls `generate_index()` after JSONL write; no external callers since this is a new internal helper

### Similar Patterns
- `scripts/little_loops/issue_history/doc_synthesis.py:301-315` — canonical markdown table pattern (header row → `|---|` separator → f-string data rows → `"\n".join(lines)`)
- `scripts/little_loops/issue_history/formatting.py:565-595` — second markdown table example

### Tests
- `scripts/tests/test_ll_logs.py` — extend `TestExtract` (lines 453-689) with generate_index test cases
  - File exists (689 lines); use `_make_project_dir()` helper at lines 456-492 (not `_write_jsonl` — that pattern is in `test_user_messages.py:109-113`, but `TestExtract` already has the right helper for `logs/<slug>/` structure)
- Optionally add `TestMainLogsIntegration` to `scripts/tests/test_cli.py:2590+` — use `TestMainHistoryCoverage` (lines 2590-2698 in that file) as the structural template; it's a closer match than `test_issue_history_cli.py:71-137` [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py:77, 192` — `test_readme_tool_count_is_16` asserts `"16 CLI tools"` in `README.md`; will break when `ll-logs` is registered (count becomes 17) — update in FEAT-1271/FEAT-1005 scope [Agent 3 finding]
- `scripts/tests/test_create_extension_wiring.py:198` — `test_configure_areas_count_is_15` asserts `"Authorize all 15"` in `skills/configure/areas.md`; same cascading break — update in FEAT-1006 scope [Agent 3 finding]

### Documentation
(*All tracked in FEAT-1004/FEAT-1005 — not in scope here*)
- `.claude/CLAUDE.md`, `commands/help.md`, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md`

### Configuration
- N/A — no configuration files affected

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

### Codebase Research Findings (pass 2)

_Added by `/ll:refine-issue` pass 2 — based on codebase analysis of the now-implemented `logs.py`:_

**Exact call site**: `_cmd_extract()` ends at `logs.py:207` (`return 0`) after writing all JSONL output at lines 199-205. `generate_index()` goes between those — receive `logs_dir = Path.cwd() / "logs"` (matches `out_base = Path.cwd() / "logs" / slug` at line 199).

**`slug` derivation** (`logs.py:170`): `slug = cwd_path.resolve().name` — the last component of the decoded project path. Each `logs/<slug>/` subdir name is this value.

**Agent-file exclusion confirmed in `logs.py` itself** — two sites mirror `session_log.py:78`:
- `logs.py:76` — inside `_has_ll_activity()`
- `logs.py:173` — inside `_cmd_extract()` when collecting per-project JSONL files

Use the same filter when `generate_index()` collects JSONL under each slug subdir.

**`TestExtract._make_project_dir()` at lines 456-492** — builds the full `~/.claude/projects/<encoded>/session.jsonl` fixture *and* patches both `pathlib.Path.home` and `little_loops.cli.logs.Path.cwd`. Tests for `generate_index()` should extend `TestExtract` and reuse this helper directly; the helper writes records with `sessionId` and any fields you inject (including `timestamp`).

**Registration confirmed**: `cli/__init__.py:31` imports `main_logs`; `pyproject.toml:64` registers `ll-logs = "little_loops.cli:main_logs"`. The wiring note about registration being pending is stale.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. When ll-logs registration is complete (FEAT-1271), update `scripts/tests/test_create_extension_wiring.py` — change `"16 CLI tools"` → `"17 CLI tools"` (lines 77, 192) and `"Authorize all 15"` → `"Authorize all 16"` (line 198)

## Acceptance Criteria

- [ ] `logs/index.md` is created after any `ll-logs extract` invocation
- [ ] Index contains a markdown table with project name, JSONL count, and date range
- [ ] Edge case: empty `logs/` directory produces an empty or stub index
- [ ] Tests pass

## API/Interface

```python
def generate_index(logs_dir: Path) -> None:
    """Generate logs/index.md summarising extracted projects."""
```

Internal helper function called from the `extract` subcommand dispatch — no public API changes.

## Impact

- **Priority**: P4 - utility tooling
- **Effort**: Small — ~20-30 LOC + tests
- **Risk**: Low — additive; standalone helper function
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-logs`, `captured`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-23_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1271 is backlog**: `scripts/little_loops/cli/logs.py` and `scripts/tests/test_ll_logs.py` do not exist yet — both are created by FEAT-1271. This issue cannot be implemented until FEAT-1271 is done.
- **FEAT-1273 is backlog**: The `extract` subcommand dispatch block (where `generate_index()` is called) is implemented by FEAT-1273. FEAT-1274 extends that block — required sequencing: FEAT-1271 → FEAT-1273 → FEAT-1274.

_Updated 2026-04-23 (`/ll:refine-issue` pass 2)_: Both concerns are resolved. `logs.py` exists (331 lines), `test_ll_logs.py` exists (689 lines), and `ll-logs` is registered in `cli/__init__.py:31` and `pyproject.toml:64`. This issue is unblocked and ready for implementation.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-23T22:01:25 - `ce3fdce1-b748-424c-9a92-653033dd133f.jsonl`
- `/ll:ready-issue` - 2026-04-23T21:56:30 - `816bb8d3-6bdf-4745-a786-f7fbcc55fb91.jsonl`
- `/ll:refine-issue` - 2026-04-23T21:46:11 - `e46e8afa-f342-484a-a4ee-c3ede25dc01f.jsonl`
- `/ll:format-issue` - 2026-04-23T21:04:34 - `30650d70-0663-4ee5-a9e8-3cd0089e06c9.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `f7bd7f20-2f58-4e9f-b4e6-e50990bfbd10.jsonl`
- `/ll:wire-issue` - 2026-04-23T16:30:47 - `f7bd7f20-2f58-4e9f-b4e6-e50990bfbd10.jsonl`
- `/ll:refine-issue` - 2026-04-23T16:26:21 - `1447f80b-a52b-410a-bd33-db465a58f851.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `965334bc-43d3-43d2-add7-d5f59631e49a.jsonl`

---

## Resolution

**Completed** 2026-04-23

Added `generate_index(logs_dir: Path) -> None` to `scripts/little_loops/cli/logs.py`:
- Iterates sorted subdirs of `logs_dir`, collects non-agent-prefixed JSONL files
- Stream-parses records with error handling to extract `timestamp` fields
- Writes `logs/index.md` with a markdown table (project, sessions, date range)
- Edge case: empty or non-existent `logs_dir` produces a stub index with "No projects extracted yet."
- Called from `_cmd_extract()` before `return 0` with `Path.cwd() / "logs"`

Three new tests added to `TestExtract` in `scripts/tests/test_ll_logs.py` — all 29 tests pass.

## Status

**Completed** | Created: 2026-04-23 | Completed: 2026-04-23 | Priority: P4
