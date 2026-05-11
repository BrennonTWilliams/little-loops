---
id: ENH-1428
type: ENH
priority: P2
status: done
completed_at: 2026-05-10T21:36:24Z

confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
size: Very Large
parent: ENH-1422
---

# ENH-1428: Decouple Issue Status — ll-issues CLI Documentation Updates

## Summary

Update `docs/reference/CLI.md` and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` to reflect the new frontmatter-based status vocabulary introduced by ENH-1427. Can be written concurrently with ENH-1427 but must be accurate against the shipped code before merge.

## Parent Issue

Decomposed from ENH-1422: Decouple Issue Status — ll-issues CLI (list/show/count/search)

## Current Behavior

Documentation in `docs/reference/CLI.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/GETTING_STARTED.md`, `docs/reference/API.md`, and `README.md` still references the old directory-based status vocabulary (`active`, `completed`, `deferred`, `active (default)`) that was replaced by frontmatter-based status in ENH-1427. Users following these docs will supply stale `--status` values that produce unexpected results.

## Expected Behavior

All documentation reflects the current frontmatter-based status vocabulary (`open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`) with `open` as the default. No remaining references to `--status active`, `--status completed`, or `active (default)` exist in any `docs/` or `README` file.

## Motivation

After the vocabulary transition from `"active"/"completed"/"deferred"` to `"open"/"in_progress"/"blocked"/"done"/"cancelled"`, the CLI reference and management guide still describe the old directory-based status model and old `--status` choice values. Users following these docs will use stale flag values.

## Proposed Solution

### `docs/reference/CLI.md`

- Lines ~501, ~515, ~546: update `--status` choices tables for `list`, `search`, and `count` subcommands from `active/completed/deferred/all` to `open/in_progress/blocked/deferred/done/cancelled/all`; update default shown from `active` to `open`
- Line ~691: update example `ll-issues count --status completed` to `--status done`

### `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`

- Line ~118: revise "**Directory location determines CLI bucketing.**" to describe frontmatter-based status
- Update vocabulary table entries replacing `active` → `open`/`in_progress`/`blocked` and `completed` → `done`/`cancelled`
- Update any directory-move instructions that describe moving files to `completed/` or `deferred/` as the mechanism for changing status

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional stale locations in `docs/reference/CLI.md` (beyond those in original issue):**
- Line 495: "List active issues with optional filters." — update prose to drop "active" or say "open"
- Line 509: "Count active issues." — same prose fix
- Line 521 (`ll-issues show`): "Searches all active category directories, the completed directory, and the deferred directory." — revise to describe frontmatter-based search
- Line 531 (`ll-issues path`): same directory-enumeration prose
- Line 547: `--include-completed` row — "Include completed issues (alias for `--status all`)" — consider whether this flag still exists post-ENH-1427 or if the row should be removed
- Line 659 (`ll-issues skip` Behavior): "Only works on issues in active directories (`bugs/`, `features/`, `enhancements/`); exits with error for `completed/` or `deferred/`" — update to describe frontmatter status guard

**Additional stale locations in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`:**
- Lines 22–27: directory layout diagram labels `completed/ ← archived issues` and `deferred/ ← parked issues` — these directories are now archival, not the source of truth for status
- Lines 108–116: status vocabulary table lists entirely wrong values (`backlog`, `active`, `completed`, `resolved`, `wont_do`, `superseded`) — replace entirely with: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`
- Lines 125–126: reopen instructions say "Move file from `.issues/completed/` back to the appropriate type directory" — update to say set `status: open` in frontmatter

**Additional files not in original issue:**
- `docs/guides/LOOPS_GUIDE.md:1161`: YAML loop action `ll-issues list --status active` — change to `--status open`; this was explicitly called out in ENH-1427's completed issue as owned by ENH-1428
- `README.md:430`: `ll-issues list  # List all active issues` — update comment to say "open" or "all open"
- `README.md:437`: `ll-issues count --status completed  # Count completed issues` — change to `--status done`

## Implementation Steps

1. Update `docs/reference/CLI.md` — change `--status` choices in all three subcommand tables (list, search, count) at lines ~501, ~515, ~546 from `active/completed/deferred/all` to `open/in_progress/blocked/deferred/done/cancelled/all`; update default from `active` to `open`; fix example at line ~691 (`--status completed` → `--status done`)
2. Update `docs/reference/CLI.md` prose — fix lines ~495, ~509, ~521, ~531 (remove/replace "active directories" / "completed directory" language); update `ll-issues skip` behavior at line ~659
3. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — line 116 header **already reads** "Frontmatter `status` determines CLI bucketing" (no change needed there); remaining work: replace stale vocab table rows at lines ~110–111 (`active`, `completed`) entirely with the six shipped values (`open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`); update reopen instructions (lines ~125–126) to say set `status: open` in frontmatter rather than move the file; update directory layout diagram (lines ~22–27) labels
4. Update `docs/guides/LOOPS_GUIDE.md:1161` — change `ll-issues list --status active` to `ll-issues list --status open` in the YAML loop action
5. Update `README.md:437` — change `ll-issues count --status completed` to `--status done`; update line ~430 comment
6. Run `ll-verify-docs` to confirm no broken references remain

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/API.md` — fix `#### search` section: update `--status` choices to `open/in_progress/blocked/deferred/done/cancelled/all` with default `open`, revise or remove `--include-completed` row, update code example at line ~3123, fix prose at line ~3096 ("active, completed, and/or deferred" → frontmatter-based); also fix `ll-issues show` section at line ~3141 ("Searches all active category directories and the completed directory" → "Searches all type directories")
8. Update `docs/guides/GETTING_STARTED.md` — replace stale status enum at line ~179 with the six shipped values (`open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`); update prose at line ~192 that references "not active, not completed"
9. Create `scripts/tests/test_enh1428_doc_wiring.py` — new doc-wiring test file following `test_enh1130_doc_wiring.py` pattern; positive assertions (new vocab present in each modified file) and negative assertions (`--status active`, `--status completed`, `active (default)`, `"Directory location determines CLI bucketing"`, `"active category directories and the completed directory"` absent)

## Integration Map

### Files to Modify
- `docs/reference/CLI.md` — `--status` choices for list/count/search subcommands, prose descriptions, examples, `--include-completed` note, `ll-issues skip` behavior
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — directory bucketing statement, full status vocabulary table, directory layout description, reopen instructions
- `docs/guides/LOOPS_GUIDE.md` — YAML loop action at line 1161 uses `ll-issues list --status active` (invalid post-ENH-1427; explicitly owned by this issue per ENH-1427 resolution notes)
- `README.md` — `ll-issues list` and `ll-issues count --status completed` examples at lines 430 and 437

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### search` section has stale vocabulary independent of line 584: line ~3096 prose "active, completed, and/or deferred"; line ~3104 `--status` choices show `{active,completed,deferred,all}` with default `active`; line ~3105 `--include-completed` row; line ~3123 code example `ll-issues search "caching" --include-completed`
- `docs/guides/GETTING_STARTED.md` — line ~179 status enum lists old values (`active`, `completed`, `resolved`, `wont_do`, `superseded`) alongside new; line ~192 prose uses "not active, not completed" (directory-model phrasing)

_Added by `/ll:refine-issue` — additional stale location:_
- `docs/reference/API.md:3141` — `ll-issues show` CLI section says "Searches all active category directories and the completed directory"; should say "Searches all type directories" (after ENH-1425, all issues live in type directories regardless of status — no separate completed/ or deferred/ search path)

### Reference (Already Correct)
- `docs/reference/API.md:584` — `IssueInfo.status` doc already updated: `open | in_progress | blocked | deferred | done | cancelled` (note: `#### search` section ~lines 3096–3123 is NOT correct — see Files to Modify above)
- `scripts/little_loops/cli/issues/__init__.py` — argparse choices already updated by ENH-1427

### Tests
- `scripts/tests/test_issues_cli.py` — core CLI tests for status filtering
- `scripts/tests/test_issues_search.py` — `TestSearchStatusFilter` class
- `scripts/tests/test_issue_parser_properties.py:82` — canonical valid status list: `["open","in_progress","blocked","deferred","done","cancelled"]`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1428_doc_wiring.py` — new test file to create following project pattern (see `test_enh1130_doc_wiring.py`); positive assertions: new vocab present in each modified doc file; negative assertions: `--status active`, `--status completed`, `active (default)`, `"Directory location determines CLI bucketing"` absent from target files

## Files to Modify

- `docs/reference/CLI.md`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`
- `docs/guides/LOOPS_GUIDE.md`
- `README.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### search` section (~lines 3096–3123) has stale status vocab separate from the already-correct `IssueInfo.status` docs at line 584; `ll-issues show` CLI section at line ~3141 says "Searches all active category directories and the completed directory" (stale directory-model prose)
- `docs/guides/GETTING_STARTED.md` — stale status enum (line ~179) and directory-model prose (line ~192)

## Acceptance Criteria

- `docs/reference/CLI.md` `--status` choices for list/search/count match the new vocab (`open/in_progress/blocked/deferred/done/cancelled/all`) with default `open`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` no longer states directory location determines status; vocabulary table shows the six shipped values
- `docs/guides/LOOPS_GUIDE.md` YAML loop action uses `--status open` (not `--status active`)
- `README.md` examples use `--status done` (not `--status completed`)
- No remaining references to `--status active`, `--status completed`, or `active (default)` in any docs/ or README file
- `ll-verify-docs` passes after changes

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` `#### search` section uses new `--status` choices with `open` default; no `--include-completed` row referencing old vocabulary; no "active, completed, and/or deferred" prose
- `docs/reference/API.md` `ll-issues show` section at line ~3141 no longer says "Searches all active category directories and the completed directory"
- `docs/guides/GETTING_STARTED.md` status enum lists only the six shipped values; no "not active, not completed" directory-model phrasing
- `scripts/tests/test_enh1428_doc_wiring.py` exists and passes

## Impact

- **Priority**: P2 — Without this, users following the docs will supply stale `--status` values; the mismatch between docs and shipped CLI creates confusion and failed commands.
- **Effort**: Medium — Multiple doc files to update (7 files), but all changes are text substitutions with no runtime code changes.
- **Risk**: Low — Documentation-only changes; no runtime behavior is affected.
- **Breaking Change**: No

## Labels

`documentation`, `enhancement`, `ll-issues`, `status`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- No pre-existing tests cover the documentation files being modified — `scripts/tests/test_enh1428_doc_wiring.py` is itself part of the deliverable (step 9), so early implementation errors won't be caught by an existing safety net. Mitigate by creating the test file first or running `ll-verify-docs` after each file update.
- 7 files touched across distinct doc directories; each requires slightly different vocabulary updates (table rows, prose rewrites, inline examples) rather than a single uniform substitution. Risk of missing a location — use the negative assertions in the wiring test as the completeness check.
- Minor open question resolved during research: `--include-completed` flag (CLI.md:547) still exists in code (`scripts/little_loops/cli/issues/__init__.py:198`) — keep the row but update its description to use new status vocabulary instead of `active/completed`.

## Resolution

Updated 7 documentation files to reflect frontmatter-based status vocabulary (`open/in_progress/blocked/deferred/done/cancelled`) introduced by ENH-1427. All stale `--status active`, `--status completed`, and directory-model prose removed. Created `scripts/tests/test_enh1428_doc_wiring.py` with 31 wiring tests (all pass). `ll-verify-docs` passes.

## Session Log
- `/ll:manage-issue` - 2026-05-10T21:36:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be39e338-241c-4325-ba20-779c072a84de.jsonl`
- `/ll:ready-issue` - 2026-05-10T21:32:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be39e338-241c-4325-ba20-779c072a84de.jsonl`
- `/ll:confidence-check` - 2026-05-10T21:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/073e9f7f-9842-49ed-99f5-f42a29385746.jsonl`
- `/ll:refine-issue` - 2026-05-10T21:19:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f597c5b-71d2-4636-a269-729638a87833.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f1fbcc4-921a-4867-adfe-8fef6dd9af14.jsonl`
- `/ll:wire-issue` - 2026-05-10T17:31:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd82a9f5-907d-4fb1-9121-455f3a13ef6b.jsonl`
- `/ll:refine-issue` - 2026-05-10T17:26:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3eed4435-21f6-476e-9d6f-a0e9d4bf5fd3.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de4dc0e-8a1e-41f5-94a2-7daaa289459e.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
