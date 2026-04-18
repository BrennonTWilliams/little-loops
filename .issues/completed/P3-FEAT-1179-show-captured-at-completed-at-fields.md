---
id: FEAT-1179
type: FEAT
priority: P3
status: completed
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1163
size: Small
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-04-18T21:39:47Z
---

# FEAT-1179: Display `captured_at` / `completed_at` in `ll-issues show`

## Summary

Update the `ll-issues show` command to extract and render `captured_at` and `completed_at` frontmatter fields when present, enabling sub-day resolution in the issue detail card.

## Parent Issue

Decomposed from FEAT-1163: Read `captured_at`/`completed_at` Timestamps in Analytics and Display

## Motivation

Once upstream writers (FEAT-1161, FEAT-1162) populate these fields they are invisible to users unless the display layer surfaces them. This is the narrowest slice — only the show command and its output styling.

## Implementation Steps

### show.py

- **`scripts/little_loops/cli/issues/show.py:101`** — `_parse_card_fields()`: extract `captured_at` and `completed_at` from the frontmatter dict returned by `parse_frontmatter(content, coerce_types=True)` at line 114. Return them as `str | None` (no datetime coercion needed for display).
- **`scripts/little_loops/cli/issues/show.py:259`** — `_render_card()`: append `captured_at` and `completed_at` rows to `detail_mid_parts` (or equivalent), guarded by `if fields.get(...)`. Follow the conditional-append pattern at lines 283-297 and 333-341.

### Coercion note

`parse_frontmatter(content, coerce_types=True)` returns ISO 8601 strings as plain `str` — no extra parsing needed for display. Just pass the raw string value through.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Optional field read pattern** (`show.py:147-154`): existing optional frontmatter fields are read via `frontmatter.get("key")` without coercion. Follow this exact shape for `captured_at` / `completed_at`.
- **Return dict shape** (`show.py:223-233`): optional fields are stored in the returned dict as `str(value) if value is not None else None`. Add two new keys here.
- **Render target range clarification**: meta-line conditional appends run `show.py:288-296` (the join is line 297); lines 283-287 are upstream variable extractions. The detail-mid block at `show.py:333-341` remains the best model for the new rows since those are also optional detail-card fields.
- **OUTPUT_STYLING.md gap** (`docs/reference/OUTPUT_STYLING.md:128-134`): the current Detail fields table only documents `Source`, `Norm`, `Fmt` — it already omits `Integration`, `Labels`, `History`. Decide whether to (a) add only `Captured at` / `Completed at` rows or (b) backfill the missing rows while editing. Prefer (a) to keep scope small; file a follow-up if (b) is warranted.

### Documentation

- **`docs/reference/OUTPUT_STYLING.md:110-134`** — add `Captured at` / `Completed at` rows to the `_render_card` ASCII layout diagram and Detail fields table (rendered conditionally when present).

## API/Interface

```
Captured at:   2026-04-18T14:32:07Z
Completed at:  2026-05-01T09:15:44Z
```

Both fields are omitted from the card when absent; no error.

## Acceptance Criteria

- [ ] `ll-issues show` displays `captured_at` when present in frontmatter
- [ ] `ll-issues show` displays `completed_at` when present in frontmatter
- [ ] Existing issues without these fields display without errors or blank rows
- [ ] JSON output (`--json`) includes `captured_at` and `completed_at` keys

## Files to Modify

- `scripts/little_loops/cli/issues/show.py` — `_parse_card_fields()` (line 101) and `_render_card()` (line 259)
- `docs/reference/OUTPUT_STYLING.md` — ASCII layout diagram and Detail fields table (lines 110-134)
- `docs/reference/CLI.md:430` — update prose field enumeration sentence for `ll-issues show` to include `captured_at` / `completed_at` [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:430` — dispatches to `cmd_show`; no changes needed (signature unchanged) [Agent 1 finding]

## Tests

- `scripts/tests/test_issues_cli.py` — add `ll-issues show` test cases for `captured_at`/`completed_at` in `TestIssuesCLIShow` (starting line 1051); add JSON output test following pattern of `test_show_json_includes_dim_scores` (line 1735); update `test_show_new_fields_absent_gracefully` (line 1493)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py:1145` — `test_show_completed_issue` uses a no-frontmatter fixture; add companion test with `completed_at:` in frontmatter to cover the "field present in completed issue" render path [Agent 3 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Update `docs/reference/CLI.md:430` — add `captured_at` and `completed_at` to the prose field enumeration sentence describing `ll-issues show` card output

### Implementation Pattern References

- **Rendering optional fields**: `show.py:283-297` (meta line conditional append) and `show.py:333-341` (detail mid-border section)
- **JSON output**: `_parse_card_fields` returns `str | None`; `print_json(fields)` at `show.py:446-447` emits them verbatim

## Resolution

Implemented via TDD:
- `scripts/little_loops/cli/issues/show.py`: `_parse_card_fields` extracts `captured_at`/`completed_at` from frontmatter; `_render_card` appends conditional rows to detail lines.
- `scripts/tests/test_issues_cli.py`: added `test_show_displays_captured_at`, `test_show_displays_completed_at_for_completed_issue`, `test_show_json_includes_timestamps`; updated `test_show_new_fields_absent_gracefully`.
- `docs/reference/OUTPUT_STYLING.md`: added `Captured at` / `Completed at` rows to layout and Detail fields table.
- `docs/reference/CLI.md`: updated `ll-issues show` prose enumeration.

All acceptance criteria met. 4981 tests pass, ruff clean, mypy clean.

## Session Log
- `/ll:manage-issue` - 2026-04-18T21:39:47Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cc24735-d02c-4d53-8d6c-30d9400c65a0.jsonl`
- `/ll:wire-issue` - 2026-04-18T21:33:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5fcc6aa0-2927-43ce-94e3-9ecda4033781.jsonl`
- `/ll:refine-issue` - 2026-04-18T21:29:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c76b539-4f41-4832-b3d8-38ba6b4521bd.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1357a791-c921-47ef-95b7-1d0a7b03979b.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/26e075f3-7d70-4a4c-a57d-abfa22da5d9b.jsonl`
