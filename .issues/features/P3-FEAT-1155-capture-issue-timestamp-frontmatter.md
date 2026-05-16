---
id: FEAT-1155
type: FEAT
priority: P3
status: completed
discovered_date: 2026-04-18
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 53
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
---

# FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Summary

Record a `captured_at` ISO timestamp in issue frontmatter when `/ll:capture-issue` creates a new issue, and record a `completed_at` ISO timestamp when an issue is moved to `.issues/completed/`.

## Motivation

Issues currently have `discovered_date` (date-only), but no machine-readable record of the exact moment capture happened or when the issue was completed. Without precise timestamps, velocity metrics from `ll-history` and other analysis tools can only resolve to day granularity. Capture and completion times are the two most analytically useful moments in an issue's lifecycle — both should be persisted where they're discovered, not reconstructed from git blame.

## Implementation Steps

1. **`/ll:capture-issue` skill** (`skills/capture-issue/SKILL.md`): After writing the issue file, add `captured_at: <ISO 8601 datetime>` to its YAML frontmatter (alongside existing `discovered_date`).

2. **Issue completion paths** — all places that move a file into `completed/` must append `completed_at: <ISO 8601 datetime>` to the frontmatter before or immediately after the move:
   - `/ll:manage-issue` skill (`skills/manage-issue/`)
   - `ll-auto` CLI (`scripts/little_loops/auto.py` or equivalent)
   - `ll-parallel` CLI (`scripts/little_loops/parallel.py` or equivalent)
   - `ll-sprint` CLI
   - Any `git mv` wrapper that targets the completed dir

3. **Schema**: Add both fields to `config-schema.json` issue frontmatter documentation; update `ll-issues show` to display them.

4. **`ll-history` / analytics**: Use `captured_at` and `completed_at` where available for sub-day resolution; fall back to `discovered_date` / file mtime when absent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — `captured_at` in capture-issue skill:**
- The exact location for adding `captured_at` is `skills/capture-issue/SKILL.md` near line 235 (the instruction that mandates `discovered_date` and `discovered_by: capture-issue`), and `skills/capture-issue/templates.md:134-139` (the heredoc template that must gain the new field).
- Shell format to use: `date -u +"%Y-%m-%dT%H:%M:%SZ"` (consistent with the format already used in `issue_lifecycle.py:730`).

**Step 2 — Completion code paths (CLI entry points are NOT the right targets):**
The issue mentions `auto.py`, `parallel.py`, `sprint.py` as the targets, but the actual completion logic routes through a single layer:
- `scripts/little_loops/issue_lifecycle.py:648` — `complete_issue_lifecycle()` — primary sequential path; calls `_move_issue_to_completed()` at `issue_lifecycle.py:294`. Write `completed_at` to frontmatter here, before calling `git mv`.
- `scripts/little_loops/issue_lifecycle.py:545` — `close_issue()` — automated closure via ready-issue verdict; calls the same `_move_issue_to_completed()` helper.
- `scripts/little_loops/parallel/orchestrator.py:1121` — `_complete_issue_lifecycle_if_needed()` — parallel path; performs its own inline `git mv` at `orchestrator.py:1182-1196`.
- `skills/manage-issue/SKILL.md:408-418` — interactive path; LLM runs `git mv` directly (no Python). The skill must be updated to also write `completed_at` via the Edit tool on the frontmatter before executing the move.

**Reusable frontmatter update utility:**
`sync.py:160-182` contains `_update_issue_frontmatter(content, updates)` — a YAML round-trip function using `yaml.safe_load` / `yaml.dump`. This pattern should be extracted to `frontmatter.py` (or replicated inline) for use in `issue_lifecycle.py` and `orchestrator.py` to inject `completed_at`.

**Timestamp helper:** `_iso_now()` already exists in `issue_lifecycle.py:26-28` returning `datetime.now(UTC).isoformat()`. Use this directly rather than introducing a new helper.

**Step 3 — `ll-issues show`:**
`scripts/little_loops/cli/issues/show.py:101` — `_parse_card_fields()` reads frontmatter via `parse_frontmatter(content, coerce_types=True)` at `show.py:114`. Add `captured_at` and `completed_at` extraction here, then render them in `_render_card()` at `show.py:259`.

**Step 4 — `ll-history` / analytics:**
- `scripts/little_loops/issue_history/parsing.py:291-306` — `_parse_discovered_date(fm)` reads `fm.get("discovered_date")`. Update to also check `fm.get("captured_at")` as a higher-resolution fallback for `discovered_date`.
- `scripts/little_loops/issue_history/parsing.py:131-170` — `_parse_completion_date()` currently uses body-regex → git-log fallback chain. Add a first check: `fm.get("completed_at")` before the regex, so frontmatter wins when present.
- `scripts/little_loops/issue_history/models.py:17-37` — `CompletedIssue` dataclass. Consider adding `captured_at: datetime | None` and `completed_at: datetime | None` fields (or reuse existing `discovered_date`/`completed_date` with higher precision).

**Test files to update/add:**
- `scripts/tests/test_issue_lifecycle.py:125-167` — add assertions that `completed_at` appears in frontmatter after `_build_completion_resolution()` / `_move_issue_to_completed()`.
- `scripts/tests/test_issue_history_parsing.py` — add fixture with `completed_at: "2026-05-01T09:15:44Z"` in frontmatter and assert it is preferred over body regex.
- `scripts/tests/test_issues_cli.py` — add test case for `ll-issues show` displaying both new fields.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/little_loops/cli/issues/search.py:21-34` — update the **independent** `_parse_discovered_date` regex implementation to also check `captured_at` frontmatter (mirrors the change in `parsing.py`; `list_cmd.py` inherits automatically since it imports from `search.py`)
6. Update `scripts/little_loops/issue_history/models.py:28-38` — if `captured_at`/`completed_at` are added as `datetime | None` fields to `CompletedIssue`, update `to_dict()` to serialize them; use `None` defaults to avoid breaking the ~30+ existing construction sites in tests
7. Update `scripts/tests/test_orchestrator.py` — add `completed_at` assertions to tests in `TestCompleteIssueLifecycle` that exercise the parallel `git mv` path
8. Update `docs/reference/ISSUE_TEMPLATE.md:875` — add `captured_at` and `completed_at` rows to the canonical frontmatter field table

## API/Interface

New frontmatter fields:

```yaml
captured_at: "2026-04-18T14:32:07Z"   # set by capture-issue
completed_at: "2026-05-01T09:15:44Z"  # set when moved to completed/
```

Format: ISO 8601 UTC (`datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")` in Python, or `date -u +"%Y-%m-%dT%H:%M:%SZ"` in shell).

## Acceptance Criteria

- [ ] New issues created by `/ll:capture-issue` contain `captured_at` in frontmatter
- [ ] Issues moved to `completed/` via any path contain `completed_at` in frontmatter
- [ ] `captured_at` and `completed_at` are valid ISO 8601 UTC strings
- [ ] `ll-issues show` displays both fields when present
- [ ] Existing issues without these fields continue to work without errors

## Integration Map

### Files to Modify
- `skills/capture-issue/SKILL.md` — add `captured_at` field instruction near line 235 alongside `discovered_date`
- `skills/capture-issue/templates.md` — add `captured_at: [ISO timestamp]` to heredoc template at line 134-139
- `skills/manage-issue/SKILL.md` — add Edit-tool step to write `completed_at` to frontmatter before `git mv` (phase 5, near line 408)
- `scripts/little_loops/issue_lifecycle.py` — inject `completed_at` in `_move_issue_to_completed()` (line 294) before the git mv call; reuse `_iso_now()` from line 26
- `scripts/little_loops/parallel/orchestrator.py` — inject `completed_at` in `_complete_issue_lifecycle_if_needed()` before the inline `git mv` at line 1182-1196
- `scripts/little_loops/issue_history/parsing.py` — update `_parse_discovered_date()` (line 291) to check `captured_at`; update `_parse_completion_date()` (line 131) to check `completed_at` frontmatter field first
- `scripts/little_loops/cli/issues/show.py` — extract and display `captured_at`/`completed_at` in `_parse_card_fields()` (line 101) and `_render_card()` (line 259)
- `scripts/little_loops/cli/issues/search.py` — contains a **separate, independent `_parse_discovered_date` implementation** (lines 21-34, regex-only, no frontmatter fallback); must be updated in parallel with `parsing.py` to check `captured_at` — otherwise `ll-issues search` and `ll-issues list` will remain at day granularity even after `parsing.py` is updated
- `scripts/little_loops/issue_history/models.py` — if `captured_at`/`completed_at` are added as fields to `CompletedIssue`, update `to_dict()` (lines 28-38) to serialize them; use `datetime | None` with `None` defaults so existing construction sites don't break

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:683,693` — calls `complete_issue_lifecycle()`; no changes needed if logic is in `issue_lifecycle.py`
- `scripts/little_loops/cli/sprint/run.py` — references `completed/` directory; routes through `issue_lifecycle.py`, likely no direct changes
- `scripts/little_loops/issue_history/models.py:17-37` — `CompletedIssue` dataclass; may need `captured_at`/`completed_at` as `datetime | None` fields for sub-day analytics

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/list_cmd.py:28,64` — imports `_parse_discovered_date` from `search.py` (not from `parsing.py`); will inherit `captured_at` support automatically once `search.py` is updated
- `scripts/little_loops/__init__.py` — re-exports `close_issue` and `complete_issue_lifecycle` in `__all__`; no changes needed but confirms the public API surface for these symbols
- `scripts/little_loops/issue_history/__init__.py` — re-exports `CompletedIssue`; if the dataclass gains new fields, downstream consumers importing from here will see them automatically
- `scripts/little_loops/issue_history/debt.py:255-256,408-413` — computes `delta = issue.completed_date - issue.discovered_date` (day-level); if `CompletedIssue` fields stay as `date`, no change needed; if upgraded to `datetime`, type alignment required before subtraction
- `scripts/little_loops/issue_history/summary.py:47,104,110` — groups issues by `issue.completed_date` as `date`; same type-alignment concern as `debt.py`
- `scripts/little_loops/cli/history.py:225-227` — `--since/--until` filter compares `i.completed_date >= since_date` where both are `date` objects; needs `.date()` coercion if `completed_date` becomes a `datetime`

### Reusable Utilities
- `scripts/little_loops/sync.py:160-182` — `_update_issue_frontmatter(content, updates)` — YAML round-trip frontmatter updater (the pattern to extract/reuse for injecting `completed_at`)
- `scripts/little_loops/issue_lifecycle.py:26-28` — `_iso_now()` helper returning `datetime.now(UTC).isoformat()` — use directly

### Tests
- `scripts/tests/test_issue_lifecycle.py` — add assertions for `completed_at` in frontmatter after completion; update `TestMoveIssueToCompleted` class (6 tests at lines 271-465) and `TestCompleteIssueLifecycle.test_full_complete_flow` (line 1114)
- `scripts/tests/test_issue_history_parsing.py` — add fixture with `completed_at` in frontmatter; assert it takes priority over body regex (`TestParseCompletionDate` at lines 94-165); add tests for `_parse_discovered_date` preferring `captured_at` (currently not tested at all)
- `scripts/tests/test_issues_cli.py` — add `ll-issues show` test cases for `captured_at`/`completed_at` to the existing `TestIssuesCLIShow` class (19 tests, starting line 1051); also add JSON output test following pattern of `test_show_json_includes_dim_scores` (line 1735); update `test_show_new_fields_absent_gracefully` (line 1493) to assert absence of new fields
- `scripts/tests/test_frontmatter.py` or `test_sync.py` — add test for `_update_issue_frontmatter` with ISO datetime values

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py` — has `TestCompleteIssueLifecycle` class with `test_appends_session_log_after_successful_git_mv` (line 1674) and sibling tests that exercise the parallel `git mv` path; update to assert `completed_at` is written to frontmatter before the move
- `scripts/tests/test_issues_search.py` — writes frontmatter strings with `discovered_date` at lines 35, 40, 47, 52, 59, 551, 559, 568; asserts `"discovered_date" in item` at line 762; not broken by the change but add a test case asserting `captured_at` is surfaced when present
- `scripts/tests/test_sync.py:748` — asserts `"discovered_date:" in content`; not broken; add ISO datetime round-trip test for `_update_issue_frontmatter` with a `captured_at` value
- `scripts/tests/test_issue_history_advanced_analytics.py` — ~30+ `CompletedIssue` construction sites; **only break if new fields are non-optional**; use `datetime | None` defaults to keep these green
- `scripts/tests/test_issue_history_summary.py` — constructs `CompletedIssue` with `completed_date` at ~7 sites; same concern as above
- `scripts/tests/test_doc_synthesis.py` — constructs `CompletedIssue`; same concern

### Documentation
- `config-schema.json` — add `captured_at` and `completed_at` to issue frontmatter documentation section (note: this file currently has no frontmatter section — a new section must be created, not an existing one updated)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md:875` — canonical frontmatter field table; add rows for `captured_at` (set by capture-issue, ISO 8601 UTC) and `completed_at` (set on completion, ISO 8601 UTC)
- `docs/reference/API.md:1560-1568` — `CompletedIssue` dataclass documentation; update if `captured_at`/`completed_at` fields are added to the dataclass
- `docs/reference/API.md:3092` — `ll-issues search --json` field list; verify after implementation that the serialized key name and documentation match

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-18_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 53/100 → LOW

### Outcome Risk Factors
- **Path fragmentation**: 12 source files across 5 subsystems — the parallel orchestrator's inline `git mv` (L1182-1196) is the highest-risk path to miss; it has no shared helper with the sequential path.
- **Timestamp format mismatch**: `_iso_now()` returns `+00:00` suffix; issue API shows `Z`. Decide format early and apply consistently across Python and shell paths.
- **`CompletedIssue` type alignment**: `debt.py`, `summary.py`, `history.py` do arithmetic on `completed_date` as `date`. If fields stay `date`, no risk. If promoted to `datetime`, add `.date()` coercion at all subtraction/grouping sites before touching `models.py`.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-18
- **Reason**: Issue too large for single session (score 9/11)

### Decomposed Into
- FEAT-1161: captured_at — Write timestamp in capture-issue skill
- FEAT-1162: completed_at — Write timestamp in all completion paths
- FEAT-1163: Analytics & Display — Read timestamps in show, search, and history

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-18T19:38:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19fa4cfd-169f-4f79-9261-a8cecb509292.jsonl`
- `/ll:wire-issue` - 2026-04-18T19:23:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8883fc0-edee-48bf-ae7c-015e4f8b3dfc.jsonl`
- `/ll:refine-issue` - 2026-04-18T19:16:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d435ac64-5de4-4a7e-9c83-24b048229468.jsonl`
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a073fd14-d01d-4031-914c-a939a2a2d07d.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6ae308f-90dc-4b4e-8527-5207880ea6dd.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`
