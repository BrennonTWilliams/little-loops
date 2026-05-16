---
id: FEAT-1181
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
completed_at: 2026-04-18T22:34:16Z
discovered_by: issue-size-review
parent: FEAT-1163
size: Very Large
confidence_score: 98
outcome_confidence: 73
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 18
---

# FEAT-1181: `ll-history` Analytics and `CompletedIssue` Timestamp Support

## Summary

Update `ll-history` to use `captured_at` / `completed_at` frontmatter timestamps at sub-day resolution, add optional fields to the `CompletedIssue` dataclass, fix two WILL-BREAK tests, add missing test coverage for `_parse_discovered_date`, and update API/CLI docs.

## Parent Issue

Decomposed from FEAT-1163: Read `captured_at`/`completed_at` Timestamps in Analytics and Display

## Motivation

The analytics layer (`ll-history`) currently falls back to regex and git-log for dates. Frontmatter timestamps are more precise and should be preferred when available. This is the highest-risk child — it touches the most files and has two tests that will break on implementation.

## Implementation Steps

### parsing.py

- **`scripts/little_loops/issue_history/parsing.py:291-306`** — `_parse_discovered_date(fm)`: check `fm.get("captured_at")` first. Parse via `datetime.fromisoformat(value.rstrip("Z"))` inside `try/except ValueError`; return `None` on failure. Fall through to existing `discovered_date` logic on absence.
- **`scripts/little_loops/issue_history/parsing.py:131-170`** — `_parse_completion_date()`: add first check `fm.get("completed_at")` before the body-regex → git-log fallback chain. Same `fromisoformat` pattern.

### models.py

- **`scripts/little_loops/issue_history/models.py:17-37`** — `CompletedIssue`: add `captured_at: datetime | None = None` and `completed_at: datetime | None = None` fields (use `None` defaults to avoid breaking ~56 importing files).
- Update `to_dict()` (lines 28-38): follow existing `value.isoformat() if value else None` pattern at lines 33-34.
- **Do NOT** promote `discovered_date` / `completed_date` from `date` to `datetime` — this avoids a fan-out of `.date()` coercions in debt.py, summary.py, and history.py. Use separate `captured_at`/`completed_at` datetime fields alongside the existing date fields.

### WILL-BREAK tests (fix these first)

- **`scripts/tests/test_issue_parser.py:521-541`** — `test_parse_file_ignores_captured_at`: currently asserts `captured_at` is ignored. Rewrite to assert the new `captured_at` field is parsed and returned. Fixture `scripts/tests/fixtures/issues/bug-with-frontmatter.md:2` already has `captured_at: 2026-01-20T10:30:00Z`.
- **`scripts/tests/test_issue_history_summary.py:27-57`** — `TestCompletedIssue.test_to_dict`: currently asserts exact `to_dict()` key set. Update to include the new `captured_at` and `completed_at` keys.

### Missing test coverage

- **`scripts/tests/test_issue_history_parsing.py`** — add `TestParseDiscoveredDate` class mirroring `TestParseCompletionDate` (line 105): test `_parse_discovered_date(fm)` with `captured_at` present (should return datetime), absent (should fall back to `discovered_date`), and malformed (should return `None`).

### Documentation

- **`docs/reference/API.md:1560-1568`** — add `captured_at: datetime | None = None` and `completed_at: datetime | None = None` to the `CompletedIssue` dataclass code block.
- **`docs/reference/CLI.md:426-434`** — add `captured_at` and `completed_at` to the `ll-issues show` card contents description.
- **`docs/reference/CLI.md:456-462`** — note that `captured_at` is checked first as higher-resolution alternative before `discovered_date` when resolving `--date-field discovered`.

## Coercion note

`parse_frontmatter(content, coerce_types=True)` returns ISO 8601 strings as `str`. Strip trailing `Z` before `fromisoformat` for Python <3.11 compatibility: `value.rstrip("Z")`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Return-type mismatch to resolve.** `_parse_discovered_date` currently returns `date | None` (uses `date.fromisoformat`, see `parsing.py:300-306`). The issue says to add `datetime.fromisoformat(value.rstrip("Z"))` for `captured_at`. Two viable options:
- Keep return type `date | None` and coerce `.date()` on the parsed datetime (preserves caller signatures across `_utils.py`, `doc_synthesis.py`, `analysis.py`, `summary.py`, `cli/history.py`).
- Promote return type to `datetime | None` (requires auditing all 5 callers — analysis/summary do downstream `.toordinal()`, `(today - d).days`, etc., that work on both `date` and `datetime`).
The sibling FEAT-1163 implementation in `cli/issues/search.py:21-36` chose the second route (returns `datetime`). The Implementation Steps in this issue lean toward the same approach since separate `captured_at` field on `CompletedIssue` is `datetime | None`.

**Reference pattern — already merged FEAT-1163 sibling code:**
- `scripts/little_loops/cli/issues/search.py:21-36` — exact pattern: `fm.get("captured_at")` → `isinstance(captured, str) and captured` guard → `datetime.fromisoformat(captured.rstrip("Z"))` → fall through to `discovered_date` regex on `ValueError`.
- `scripts/little_loops/cli/issues/show.py:155-156, 244-246` — display path: `frontmatter.get("captured_at")` then `str(captured_at) if captured_at is not None else None`.
- `scripts/tests/test_issues_search.py:1023-1136` — `TestParseDiscoveredDate` reference tests; `test_sort_by_created_prefers_captured_at` at line 2424 — model the new `TestParseDiscoveredDate` class in `test_issue_history_parsing.py` after this.

**Confirmed CompletedIssue fan-out (not "~56" — actual count is small):**
- `scripts/little_loops/issue_history/_utils.py` — imports CompletedIssue
- `scripts/little_loops/issue_history/doc_synthesis.py` — imports & constructs
- `scripts/little_loops/issue_history/analysis.py` — analytics consumer
- `scripts/little_loops/issue_history/summary.py` — summary stats consumer
- `scripts/little_loops/issue_history/formatting.py` — renderer
- `scripts/little_loops/issue_history/__init__.py` — public re-export
- `scripts/little_loops/cli/history.py` — `ll-history` CLI entry point
All construct `CompletedIssue` with kwargs and omit optional fields, so `None` defaults on new fields are safe.

**Confirmed fixture state:**
- `scripts/tests/fixtures/issues/bug-with-frontmatter.md:2` — already has `captured_at: 2026-01-20T10:30:00Z`. No fixture additions required for the WILL-BREAK rewrite.

**Fixture form for new tests** — model new `TestParseDiscoveredDate` fixtures on `test_issues_search.py:1087-1107` (inline `"---\ncaptured_at: 2026-01-01T09:00:00Z\n---\n"` strings).

### Codebase Research Findings — Pass 2 Corrections

_Added by second `/ll:refine-issue` pass — verified against current source:_

**"WILL-BREAK tests" label is inaccurate — neither test mechanically breaks.** Both tests named under "WILL-BREAK tests (fix these first)" are semantically stale but their current assertions still pass after the change:

1. `scripts/tests/test_issue_parser.py:521-541` — `test_parse_file_ignores_captured_at` exercises `IssueParser.parse_file()` returning `IssueInfo` (module: `scripts/little_loops/issue_parser.py:313,334`), which is a **different parser** from the `parse_completed_issue` / `CompletedIssue` code path being changed in this issue. `IssueInfo` (`issue_parser.py:200-239`) has no `captured_at` field and this issue does not add one. The test's only assertion is `info.discovered_by == "capture-issue"` — the `captured_at` key in the fixture is not asserted on. The test name is stale (it documents an assumption no longer accurate elsewhere in the system), but the test itself will continue to pass unchanged. **Recommendation**: either (a) leave this test as-is and drop it from the scope of FEAT-1181, or (b) rename-only for accuracy (no assertion change needed, no WILL-BREAK). Do not list it as a required fix.

2. `scripts/tests/test_issue_history_summary.py:27-44` — `TestCompletedIssue.test_to_dict` (actual line range is 27-44, not 27-57; 46-57 is the sibling `test_to_dict_none_values`). Assertions use the per-key pattern `assert result["path"] == ...`, `assert result["issue_type"] == ...`, etc. — **not** strict dict equality. Adding `captured_at` / `completed_at` keys to `to_dict()` output will not break these assertions. **Recommendation**: still update this test (and `test_to_dict_none_values` at 46-57) to add positive assertions for the new keys, but treat it as coverage expansion, not a blocker/WILL-BREAK.

**Net effect on plan**: the "fix these first to establish green baseline" framing is unnecessary. Both test updates are coverage improvements and can happen in any order relative to the core changes. The real baseline risk is instead the `_parse_completion_date` two-arg callers flagged in the Wiring Phase (list_cmd.py, search.py) — those are the integration decisions that gate implementation.

**`rstrip("Z")` vs `replace("Z", "+00:00")` convention.** The issue plan uses `rstrip("Z")`. The codebase has both forms:
- `cli/issues/search.py:35` — `datetime.fromisoformat(captured.rstrip("Z"))` (the sibling FEAT-1163 code this issue models after)
- `user_messages.py:560,654`, `workflow_sequence/analysis.py:226`, `cli/loop/info.py:494` — `.replace("Z", "+00:00")` then `fromisoformat` (preserves timezone)

`rstrip("Z")` discards timezone info (produces naive datetime); `.replace("Z", "+00:00")` preserves it (produces tz-aware datetime). For consistency with the sibling FEAT-1163 pattern already used by `ll-issues search/show/list`, keep `rstrip("Z")` — but note this means `ll-history` will continue comparing naive datetimes against `date` objects throughout `analysis.py` / `summary.py`, which is the pragmatic choice here.

**Existing `TestParseCompletedIssue` tests in `test_issue_history_parsing.py:20-103`** already exercise `_parse_discovered_date` indirectly via `parse_completed_issue` (tests `test_parse_with_frontmatter` lines 23-65 and `test_parse_without_frontmatter`). The new `TestParseDiscoveredDate` class should test the function directly for the `captured_at` preference / fallback / malformed-value cases. Model after `test_issues_search.py:1023-1070` (three standalone functions: `test_parse_discovered_date_prefers_captured_at`, `test_parse_discovered_date_falls_back_to_discovered_date`, `test_parse_discovered_date_falls_back_on_invalid_captured_at`).

**Reference pattern confirmed — `cli/issues/search.py:21-50` (exact source for the new logic):**
```python
def _parse_discovered_date(content: str) -> datetime | None:
    fm = parse_frontmatter(content)
    captured = fm.get("captured_at")
    if isinstance(captured, str) and captured:
        try:
            return datetime.fromisoformat(captured.rstrip("Z"))
        except ValueError:
            pass
    # ... existing fallback chain
```
Note: the `issue_history/parsing.py` version takes `fm: dict` directly (not `content: str`), so adapt the signature — skip the `parse_frontmatter(content)` call, use the `fm` parameter directly.

## Acceptance Criteria

- [ ] `ll-history` uses `captured_at` for capture time at sub-day resolution when present
- [ ] `ll-history` uses `completed_at` for completion time at sub-day resolution when present
- [ ] `CompletedIssue` has `captured_at: datetime | None` and `completed_at: datetime | None` fields
- [ ] `to_dict()` serializes new fields as ISO strings or `None`
- [ ] All existing tests pass (including the two rewritten WILL-BREAK tests)
- [ ] `TestParseDiscoveredDate` class added with `captured_at`-preference coverage
- [ ] API.md and CLI.md updated

## Files to Modify

- `scripts/little_loops/issue_history/parsing.py` — `_parse_discovered_date()` (line 291) and `_parse_completion_date()` (line 131)
- `scripts/little_loops/issue_history/models.py` — `CompletedIssue` dataclass (lines 17-37) and `to_dict()` (lines 28-38)
- `scripts/tests/test_issue_parser.py` — rewrite `test_parse_file_ignores_captured_at` (lines 521-541)
- `scripts/tests/test_issue_history_summary.py` — update `TestCompletedIssue.test_to_dict` (lines 27-57)
- `scripts/tests/test_issue_history_parsing.py` — add `TestParseDiscoveredDate` class
- `docs/reference/API.md` — add fields to `CompletedIssue` block (lines 1560-1568)
- `docs/reference/CLI.md` — update show card description (lines 426-434, 456-462)

## Tests

Run `python -m pytest scripts/tests/ -x` after each subsystem to catch regressions early. Fix the two WILL-BREAK tests before any other changes to establish a green baseline.

### Safe callers (no code change needed)

- `scripts/tests/test_issue_history_advanced_analytics.py` — ~30+ `CompletedIssue` constructions; keyword-arg form, safe with `None` defaults
- `scripts/tests/test_issue_history_analysis.py` — constructions at lines 69, 76, 94, 119; keyword-arg form, safe
- `scripts/tests/test_doc_synthesis.py:97` — `CompletedIssue` in `_make_issue()`; safe with `None` defaults

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

**Additional issue_history callers (safe — keyword-arg construction, None defaults):**
- `scripts/little_loops/issue_history/quality.py` — imports `CompletedIssue`; safe with `None` defaults
- `scripts/little_loops/issue_history/debt.py` — imports `CompletedIssue`; safe with `None` defaults
- `scripts/little_loops/issue_history/coupling.py` — imports `CompletedIssue`; safe with `None` defaults
- `scripts/little_loops/issue_history/regressions.py` — imports `CompletedIssue`; safe with `None` defaults
- `scripts/little_loops/issue_history/hotspots.py` — imports `CompletedIssue`; safe with `None` defaults

**External callers of `_parse_completion_date` (implementation decision required):**
- `scripts/little_loops/cli/issues/list_cmd.py:66-68` — calls `_parse_completion_date(content, issue.path)` with the existing two-arg signature; will NOT benefit from `completed_at` frontmatter unless the function parses frontmatter internally from `content`. If an optional `fm` param is added, these callers must be updated or they silently miss the improvement.
- `scripts/little_loops/cli/issues/search.py:368-370` — same two-arg call pattern; same decision applies.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_issue_history_parsing.py:93-102` — `TestParseCompletedIssue.test_parse_ignores_captured_at`: this test is in the same file already listed for `TestParseDiscoveredDate`, but its own name/semantics become stale after the change. Post-change `captured_at` is no longer ignored — it is parsed into `issue.captured_at`. The test doesn't assert `issue.captured_at is None` so it won't mechanically break, but rename and add a positive assertion to match the rewrite in `test_issue_parser.py:521-541`.
- `scripts/tests/test_issue_history_cli.py` — integration tests that drive `main_history()` end-to-end (e.g., `TestMainHistoryAnalyze`). Fixture files currently contain only `**Completed**: YYYY-MM-DD` body text, not `completed_at` frontmatter, so the new code path is not triggered. Monitor for regressions; no changes needed unless fixtures are updated.

### Implementation Pattern References

- **Reading datetime from frontmatter**: `parsing.py:291-306` — `fm.get("captured_at")`, manual `datetime.fromisoformat(value.rstrip("Z"))` inside `try/except ValueError`, return `None` on failure
- **`to_dict` serialization**: `models.py:33-34` — `value.isoformat() if value else None`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. **`parsing.py:64-72` — `CompletedIssue(...)` constructor call**: after updating `_parse_discovered_date` and `_parse_completion_date`, the `CompletedIssue(...)` construction in `parse_completed_issue()` must explicitly pass `captured_at=<value>` and `completed_at=<value>` kwargs. Neither field is populated automatically — the parsed `datetime` values must be unpacked here. This step is NOT called out in the existing Implementation Steps but is required for the new fields to reach any consumer.

2. **Decide `_parse_completion_date` frontmatter strategy**: `cli/issues/list_cmd.py:66-68` and `cli/issues/search.py:368-370` call `_parse_completion_date(content, path)` with no `fm` dict. Two options:
   - Parse frontmatter internally inside `_parse_completion_date` from `content` — these callers benefit transparently, no signature change.
   - Add optional `fm: dict | None = None` parameter — callers outside `issue_history` must pass `fm` explicitly or they skip the `completed_at` check silently.
   The sibling `_parse_discovered_date` in `cli/issues/search.py:21-36` already parses its own frontmatter internally — prefer the same approach here for consistency.

3. **`test_issue_history_parsing.py:93-102`** — rename and add assertion for `test_parse_ignores_captured_at` in `TestParseCompletedIssue` (semantically stale; rename and add positive `issue.captured_at` assertion, matching the rewrite in `test_issue_parser.py:521-541`).

## Resolution

- **Action**: implement
- **Completed**: 2026-04-18
- **Changes**:
  - `scripts/little_loops/issue_history/parsing.py`: `_parse_discovered_date` prefers `captured_at` (coerced to date); `_parse_completion_date` prefers `completed_at` and now parses frontmatter from `content` when `fm` is not passed, so external callers (`cli/issues/list_cmd.py`, `cli/issues/search.py`) benefit transparently. Added `_parse_iso_datetime`, `_parse_captured_at`, `_parse_completed_at` helpers.
  - `scripts/little_loops/issue_history/models.py`: `CompletedIssue` gained `captured_at: datetime | None` and `completed_at: datetime | None` fields plus `to_dict()` serialization.
  - `scripts/tests/test_issue_history_parsing.py`: added `TestParseDiscoveredDate` (6 cases); added `test_prefers_completed_at_frontmatter`; renamed `test_parse_ignores_captured_at` → `test_parse_captures_captured_at` with positive assertions; added `test_parse_captures_completed_at`.
  - `scripts/tests/test_issue_history_summary.py`: `TestCompletedIssue.test_to_dict` / `test_to_dict_none_values` assert new keys.
  - `docs/reference/API.md`: `CompletedIssue` dataclass block lists the new fields.
  - `docs/reference/CLI.md`: `ll-history` section notes `captured_at` / `completed_at` preference.

## Session Log
- `/ll:manage-issue` - 2026-04-18T22:34:16Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7af998df-c21c-4688-a42d-351d3cbb9b5b.jsonl`
- `/ll:ready-issue` - 2026-04-18T22:29:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/693f620a-9592-40ea-9092-1faa4ef5a9a4.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e58df0f-c3c0-4e98-b115-f2aecae2688f.jsonl`
- `/ll:refine-issue` - 2026-04-18T22:11:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2fd4193-ac00-45c4-9296-d01de4f293d7.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15c98b83-3ad9-479c-a58c-76eec31c24c2.jsonl`
- `/ll:wire-issue` - 2026-04-18T22:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/memory/`
- `/ll:refine-issue` - 2026-04-18T21:59:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cab24eb-3ef5-48d3-8e04-94d390a03882.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1357a791-c921-47ef-95b7-1d0a7b03979b.jsonl`
