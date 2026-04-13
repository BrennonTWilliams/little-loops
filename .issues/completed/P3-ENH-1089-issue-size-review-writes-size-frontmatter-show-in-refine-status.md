---
id: ENH-1089
type: ENH
priority: P3
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 64
---

# ENH-1089: issue-size-review writes size frontmatter, show in refine-status

## Summary

Two related improvements to surface issue size data across the toolchain: (1) `/ll:issue-size-review` should persist its size assessment by writing a `size` field to each issue's YAML frontmatter after review, and (2) `ll-issues refine-status` should display a `Size` column in its tabular CLI output using that frontmatter field.

## Current Behavior

- `/ll:issue-size-review` analyzes issue complexity and outputs a size recommendation (XS/S/M/L/XL) to the conversation, but does not write the result back to the issue file's frontmatter.
- `ll-issues refine-status` renders a table of issues with refinement status but has no `Size` column, so the size data is invisible in CLI workflows.

## Expected Behavior

- After `/ll:issue-size-review` assesses an issue, it writes `size: <XS|S|M|L|XL>` to the YAML frontmatter of the issue file.
- `ll-issues refine-status` reads the `size` frontmatter field and renders it as a `Size` column in the table (empty/`-` when not yet reviewed).

## Motivation

Size data is only useful if it persists and is visible. Right now the assessment is ephemeral — it disappears when the conversation ends. Persisting it to frontmatter makes it available to sprint planning, dependency analysis, and CLI reporting. Showing it in `refine-status` closes the feedback loop for users doing issue triage.

## Proposed Solution

**Part 1 — `issue-size-review` skill writes frontmatter:**

After computing the size label, use a frontmatter update pattern consistent with how other skills write back to issue files (e.g., how `confidence-check` writes `confidence` or `concerns`). The `size` field should be added/updated under the YAML `---` block.

```yaml
# Expected frontmatter after review (using skill's actual labels)
size: Medium   # one of: Small, Medium, Large, Very Large
```

**Part 2 — `ll-issues refine-status` column:**

In `scripts/little_loops/cli/issues/refine_status.py` (the actual file — not `issues.py`), read `size` from `IssueInfo.size` (populated from parsed frontmatter by `IssueParser`) and include it as a static column. When the field is absent, display `—`.

Example output:
```
 ID       | Priority | Size | Confidence | Status
----------+----------+------+------------+--------
 ENH-1089 | P3       | M    | -          | active
 BUG-1079 | P3       | S    | high       | active
```

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md:6-9` — add `Edit` to `allowed-tools` (currently only `Read`, `Glob`, `Bash`); add Phase 4 frontmatter write-back after Phase 2 size determination (lines 111-126)
- `scripts/little_loops/cli/issues/refine_status.py:18-22` — add `_SIZE_WIDTH = 4` width constant alongside `_SCORE_WIDTH`, `_CONF_WIDTH`, `_TOTAL_WIDTH`
- `scripts/little_loops/cli/issues/refine_status.py:60-72` — add `"size": (_SIZE_WIDTH, "size", False)` entry in `_STATIC_COLUMN_SPECS`
- `scripts/little_loops/cli/issues/refine_status.py:75-85` — insert `"size"` in `_DEFAULT_STATIC_COLUMNS` (after `"priority"`, before `"title"`)
- `scripts/little_loops/cli/issues/refine_status.py:88` — `size` should NOT be added to `_POST_CMD_STATIC`
- `scripts/little_loops/cli/issues/refine_status.py:96` — add `"size"` to `_DEFAULT_ELIDE_ORDER` (low priority, drops before `confidence`)
- `scripts/little_loops/cli/issues/refine_status.py:288-323` — add `"size": issue.size` to JSON output records in both `--json` array and `--format json` NDJSON paths
- `scripts/little_loops/cli/issues/refine_status.py:388-409` — add `if col == "size": return issue.size if issue.size else "—"` branch in `_cell_value`
- `scripts/little_loops/issue_parser.py:236` — add `size: str | None = None` field to `IssueInfo` dataclass (after `outcome_confidence`)
- `scripts/little_loops/issue_parser.py:264-265` — add `"size": self.size` in `to_dict`
- `scripts/little_loops/issue_parser.py:286-287` — add `size=data.get("size")` in `from_dict`
- `scripts/little_loops/issue_parser.py:336-352` — add `size = frontmatter.get("size")` in `IssueParser.parse_file` (simple string `.get()`, no coercion needed — same pattern as `discovered_by` at line 337)
- `config-schema.json:674-692` — add `"size"` to valid `refine_status.columns` names (currently documents only `id, priority, title, source, norm, fmt, ready, confidence, total`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/frontmatter.py` — read-only utilities (`parse_frontmatter`, `strip_frontmatter`); no changes needed, `parse_frontmatter` already returns arbitrary fields via `.get()`
- `scripts/little_loops/cli/issues/show.py` — reads frontmatter directly; no changes needed for this issue

### Similar Patterns
- `skills/confidence-check/SKILL.md:398-428` — exact Phase 4 pattern to mirror: use Edit tool to add/update field in frontmatter block, preserve all existing fields; follow with `git add <issue-path>` (`SKILL.md:468`)
- `scripts/little_loops/issue_parser.py:337` — `discovered_by = frontmatter.get("discovered_by")` is the string field read pattern to use for `size`
- `scripts/little_loops/cli/issues/refine_status.py:404` — existing `"confidence"` column branch in `_cell_value` shows the em-dash fallback pattern

### Tests
- `scripts/tests/test_refine_status.py:19-53` — `_make_issue` helper needs `size: str | None = None` kwarg and frontmatter append; follow `confidence_score` parameter pattern
- `scripts/tests/test_refine_status.py:248-280` — `test_ready_and_outconf_columns` is the direct test pattern to model the new `size` column test after
- `scripts/tests/test_issue_parser.py` — add test for `size` frontmatter field parsing (present and absent)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_status.py:722-728` — existing JSON output test asserts specific field names; add `assert record["size"] == ...` once `size` is in JSON output records [Agent 3 finding]
- `scripts/tests/test_issue_size_review_skill.py` — **new test file** (none currently exists); follow structural SKILL.md text-assertion pattern from `scripts/tests/test_confidence_check_skill.py:11-55`; assert write-back phase does not use `AskUserQuestion`, preserves a `CHECK_MODE` skip guard, and names `size` as the frontmatter key [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — add `size` as a documented frontmatter field with valid values
- `config-schema.json:674-692` — add `"size"` to the `refine_status.columns` enum

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:489` — valid column names list reads `id, priority, title, source, norm, fmt, ready, confidence, total`; add `size` [Agent 2 finding]
- `docs/reference/CLI.md:486` — `refine-status` column list description omits `size`; add it [Agent 2 finding]
- `docs/reference/CLI.md:499` — elide sequence description (`source → norm → fmt → confidence → ready → total`) will be stale once `size` is in `_DEFAULT_ELIDE_ORDER`; update [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `allowed-tools` must be updated.** `skills/issue-size-review/SKILL.md:6-9` currently lists `Read`, `Glob`, `Bash(ll-issues:*, git:*)` — the Edit tool is absent. Without adding `Edit`, the skill cannot write back to issue files at all.

**Size label discrepancy.** The issue proposes `<XS|S|M|L|XL>` but the skill's actual size labels (defined at `SKILL.md:327-333`) are `Small`, `Medium`, `Large`, `Very Large`. The frontmatter field should store one of these four values, not a T-shirt size code. Update the expected frontmatter example accordingly:

```yaml
# Correct — matches skill's actual output
size: Medium
# Not:
size: M
```

**`issues.py` is the wrong path.** The actual file is `scripts/little_loops/cli/issues/refine_status.py`, not `scripts/little_loops/issues.py`.

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md:398-428` (Phase 4) to internalize the frontmatter write-back pattern before editing the size-review skill.
2. Edit `skills/issue-size-review/SKILL.md:6-9` — add `Edit` to `allowed-tools`.
3. Edit `skills/issue-size-review/SKILL.md` — insert a Phase 4 after the existing Phase 2 size determination (lines 111-126): use Edit tool to add/update `size: <label>` in the issue's YAML frontmatter, then `git add <path>`. Skip when `CHECK_MODE=true`. Use actual size labels: `Small`, `Medium`, `Large`, `Very Large`.
4. Edit `scripts/little_loops/issue_parser.py:236` — add `size: str | None = None` field to `IssueInfo` dataclass; update `to_dict` (line 264) and `from_dict` (line 286) accordingly.
5. Edit `scripts/little_loops/issue_parser.py:336-352` — add `size = frontmatter.get("size")` in `IssueParser.parse_file` and pass `size=size` to `IssueInfo(...)`.
6. Edit `scripts/little_loops/cli/issues/refine_status.py:18-22` — add `_SIZE_WIDTH = 4` constant.
7. Edit `scripts/little_loops/cli/issues/refine_status.py:60-72` — add `"size"` entry to `_STATIC_COLUMN_SPECS`.
8. Edit `scripts/little_loops/cli/issues/refine_status.py:75-96` — insert `"size"` in `_DEFAULT_STATIC_COLUMNS` (after `"priority"`) and `_DEFAULT_ELIDE_ORDER`.
9. Edit `scripts/little_loops/cli/issues/refine_status.py:388-409` — add `if col == "size":` branch in `_cell_value` returning `issue.size or "—"`.
10. Edit `scripts/little_loops/cli/issues/refine_status.py:288-323` — add `"size": issue.size` to both JSON output record dicts.
11. Edit `config-schema.json:674-692` — add `"size"` to the `refine_status.columns` enum.
12. Add tests in `scripts/tests/test_refine_status.py` following `test_ready_and_outconf_columns` (lines 248-280): add `size` kwarg to `_make_issue` and assert column renders `Small`/`Medium`/`Large`/`Very Large` or `—` when absent.
13. Add test in `scripts/tests/test_issue_parser.py` for `size` frontmatter parsing.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. Update `docs/reference/CONFIGURATION.md:489` — add `size` to the valid column names list (currently reads `id, priority, title, source, norm, fmt, ready, confidence, total`)
15. Update `docs/reference/CLI.md:486` — add `size` to the `refine-status` column list description; update line `:499` elide sequence sentence to include `size`
16. Create `scripts/tests/test_issue_size_review_skill.py` — structural SKILL.md assertion tests; follow the pattern in `scripts/tests/test_confidence_check_skill.py:11-55`; assert: write-back phase exists, does not use `AskUserQuestion`, includes a `CHECK_MODE` skip guard, and writes the `size` frontmatter key

## Impact

- **Scope**: Small — two files modified (SKILL.md + issues.py), additive changes only
- **Risk**: Low — purely additive; missing `size` field gracefully shows `-`
- **Users**: Anyone using `ll-issues refine-status` for issue triage or sprint prep

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/confidence-check/SKILL.md` | Reference pattern for frontmatter write-back |
| `scripts/little_loops/issues.py` | Target file for CLI column change |
| `docs/reference/API.md` | Frontmatter field documentation |

## Labels

`enhancement`, `issue-size-review`, `ll-issues`, `refine-status`, `frontmatter`

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1b3029d-1f24-48d8-a235-4f55d666b8c3.jsonl`
- `/ll:wire-issue` - 2026-04-13T01:23:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d29a22e2-892b-425b-89d3-e05a57c3e9b0.jsonl`
- `/ll:refine-issue` - 2026-04-13T01:14:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b19e73-9a31-4405-88d4-1165503fb996.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46a03127-ab0d-49ea-90a5-3516db3882e6.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24bfa590-00d2-4387-9ba6-799d36510a45.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-12
- **Reason**: Issue too large for single session (score 9/11 — Very Large)

### Decomposed Into
- ENH-1090: issue-size-review skill writes `size` frontmatter after assessment
- ENH-1091: ll-issues refine-status shows Size column

## Status

**State**: completed
