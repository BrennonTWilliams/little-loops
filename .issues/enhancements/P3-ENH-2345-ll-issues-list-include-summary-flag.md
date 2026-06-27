---
id: ENH-2345
title: Add --include-summary flag to ll-issues list --json
type: ENH
priority: P3
status: open
captured_at: '2026-06-27T18:58:04Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2345: Add --include-summary flag to ll-issues list --json

## Summary

`ll-issues list --json` currently omits the `## Summary` section body from each issue's JSON output. Skills that need title + summary for similarity scoring (e.g., `/ll:create-epics-from-unparented`, `/ll:link-epics`) must `Read` every issue file individually to extract the summary, which blows the context window when there are many orphans. A `--include-summary` flag would embed the extracted summary text into the JSON payload, eliminating the per-file `Read` calls entirely.

## Current Behavior

`ll-issues list --json` outputs only frontmatter fields (id, title, priority, status, parent) for each issue. The `## Summary` section body is not included in the JSON payload.

Skills that need title + summary for similarity scoring must `Read` every issue file individually to extract the summary text, consuming significant context budget when many issues are present.

## Expected Behavior

When `--include-summary` is passed alongside `--json`, each JSON object includes a `"summary"` key containing the plain text of the issue's `## Summary` section (whitespace-stripped). If the section is absent, the value is an empty string `""`.

Without `--include-summary`, the output is unchanged — no `"summary"` key appears.

## Motivation

`/ll:create-epics-from-unparented` failed in practice when 20 orphaned issues were present: after running 3 `ll-issues list` commands and then reading all 20 files in full, the session hit the context limit before clustering could begin. The clustering algorithm only needs `title + summary` — a small fraction of each file — but the current API forces a full `Read` to get it.

Skills like `/ll:link-epics` have the same pattern. Fixing the data source fixes all consumers.

## Implementation Steps

1. In `scripts/little_loops/cli/issues/list_cmd.py` (where `ll-issues list` is implemented), add `--include-summary` boolean flag (only meaningful with `--json`; silently ignored otherwise).
2. When the flag is set, after loading each issue's frontmatter, also parse the `## Summary` section from the file body using the existing regex pattern `## Summary\n(.+?)(?=\n##|\Z)` with DOTALL.
3. Embed the extracted text as `"summary": "<text>"` in each JSON object (empty string if section absent).
4. Update `docs/reference/CLI.md` (flag table at line 1004) to document the new flag.
5. Add a test asserting the flag populates `summary` and that it is absent (or null) without the flag.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/json-output-contracts.md` — add `summary` as an optional field in the `ll-issues list --json` schema table (only present when `--include-summary` is passed); reference the CLI.md entry

## API / Interface

```bash
# New flag
ll-issues list --status open --type ENH --json --include-summary

# Example output shape (one element)
{
  "id": "ENH-2345",
  "title": "Add --include-summary flag to ll-issues list --json",
  "priority": "P3",
  "status": "open",
  "parent": null,
  "summary": "ll-issues list --json currently omits the ## Summary section..."
}
```

The flag is a no-op when `--json` is absent (plain text listing has no place to embed it).

## Acceptance Criteria

- `ll-issues list --json --include-summary` includes a `"summary"` key in every result object.
- The value is the plain text of the `## Summary` section (leading/trailing whitespace stripped); empty string `""` if the section is absent.
- Without `--include-summary`, the `"summary"` key is absent from the JSON (no regression).
- `/ll:create-epics-from-unparented` Step 2 updated to use `--include-summary` instead of per-file `Read` calls.

## Scope Boundaries

- **In scope**: Adding `--include-summary` flag to `ll-issues list --json`; extracting only the `## Summary` section body; updating `docs/reference/CLI.md`; adding a test.
- **Out of scope**: Including other sections (Motivation, Implementation Steps, etc.) in the JSON output; modifying `--json` output format when `--include-summary` is absent; auto-updating consumer skills beyond `/ll:create-epics-from-unparented`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — add `--include-summary` boolean flag to `ls` subparser
- `scripts/little_loops/cli/issues/search.py` — add `_parse_summary_from_content(content: str) -> str` helper
- `scripts/little_loops/cli/issues/list_cmd.py` — call `_parse_summary_from_content`, extend enriched tuple, emit `"summary"` key in JSON dict

### Dependent Files (Callers/Importers)
- `skills/create-epics-from-unparented/SKILL.md` — Step 2 updated to use `ll-issues list --json --include-summary` instead of per-file `Read` calls
- `skills/link-epics/SKILL.md` — same pattern; benefits from same update (noted in Motivation)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-epic/SKILL.md` — calls `ll-issues list --json` at lines 48, 57, 65; out-of-scope per Scope Boundaries but is a live consumer of the command output
- `scripts/tests/test_cli_output.py` — imports `cmd_list` from `list_cmd` directly; awareness-level dependency

### Similar Patterns
- Existing `--json` flag implementation in `scripts/little_loops/cli/issues/list_cmd.py`

### Tests
- `scripts/tests/test_issues_cli.py` — `TestIssuesCLIList` class: add `test_list_json_include_summary_flag()` (model after `test_list_json_output_contains_labels_key` at line 679) and `test_list_json_no_summary_without_flag()` asserting key is absent without the flag

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_json_output_contracts.py` — `TestIssuesListJsonContract.REQUIRED_FIELDS` does not include `summary`; file header explicitly permits additive fields; no update needed but review before submitting
- `scripts/tests/test_cli_output.py` — imports `cmd_list` directly from `list_cmd`; no changes needed (additive only)

### Documentation
- `docs/reference/CLI.md` — `ll-issues list` flag table (line 1004)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/json-output-contracts.md` — line 102+ section documents the JSON field schema for `ll-issues list --json`; add `summary` as an optional field (only present when `--include-summary` is passed)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected/extended `Files to Modify`:** Flag registration and logic are in separate files:
- `scripts/little_loops/cli/issues/__init__.py` — `main_issues()` / `ls` subparser block; add `ls.add_argument("--include-summary", action="store_true", help="Include ## Summary body in JSON output (no-op without --json)")` alongside the existing `--json` arg
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` function; read `want_summary = getattr(args, "include_summary", False)`, extract from already-read `content`, extend enriched tuple, add `"summary"` key to JSON dict
- `scripts/little_loops/cli/issues/search.py` — **Decision**: add `_parse_summary_from_content(content: str) -> str` here, alongside `_parse_labels_from_content()` (the direct analogue); call it from `list_cmd.py` rather than inlining the regex

**Existing summary regex (from `show.py:_parse_card_fields()` — follow this, not the pattern in Step 2):**
```python
re.search(r"^## Summary\s*\n+(.*?)(?:\n\n|\n##|\Z)", content, re.MULTILINE | re.DOTALL)
```
Return `.group(1).strip()` or `""` if no match. The `^` anchor and `\s*` handle whitespace variations the Step 2 pattern misses.

**No extra disk I/O:** `content = issue.path.read_text()` is already called when `want_json=True` in `cmd_list()`. Extract summary from the already-read string.

**Enriched tuple extension:** Current shape `(issue, stat, disc_date, comp_date, labels)` — add `summary` as 6th element so the JSON dict comprehension can reference it.

**Corrected docs target:** `docs/reference/CLI.md` flag table at line 1004, not `docs/reference/API.md`.

**Specific test references in `scripts/tests/test_issues_cli.py`:**
- Model `test_list_json_include_summary_flag()` after `test_list_json_output_contains_labels_key()` (line 679) — asserts key present on every item
- Add `test_list_json_no_summary_without_flag()` — asserts `"summary"` key absent when flag is omitted (no regression)

## Impact

- **Priority**: P3 — Unblocks context-window failures in `/ll:create-epics-from-unparented` and `/ll:link-epics`; not urgent since workarounds exist but a recurring friction point.
- **Effort**: Small — Adds a boolean flag to an existing command with a regex parse; no new abstractions needed.
- **Risk**: Low — Additive-only change; flag defaults to off, so existing `--json` output is unchanged.
- **Breaking Change**: No

## Labels

`enhancement`, `cli-tool`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-06-27T19:22:23 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:refine-issue` - 2026-06-27T19:09:27 - `62c82d91-b927-47f1-9a31-b33885804e70.jsonl`
- `/ll:verify-issues` - 2026-06-27T19:07:11 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:format-issue` - 2026-06-27T19:01:06 - `c8d05460-64f1-4df3-9ea1-6efc28791f9a.jsonl`
- `/ll:capture-issue` - 2026-06-27T18:58:04Z - captured from conversation about create-epics-from-unparented context-limit failure
