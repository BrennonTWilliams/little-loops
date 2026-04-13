---
id: ENH-1099
type: ENH
priority: P3
discovered_date: 2026-04-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
---

# ENH-1099: ll-issues refine-status show score dimension columns

## Summary

Add four individual Outcome Confidence score dimension columns to `ll-issues refine-status`: **Complexity**, **Test Coverage**, **Ambiguity**, and **Change Surface**, each displaying its integer score (0–25). This requires: (1) `confidence-check` to write the four dimension scores to issue frontmatter after scoring, and (2) `refine-status` to read and render those fields as columns.

## Current Behavior

`ll-issues refine-status` shows `conf` (aggregate `outcome_confidence`, 0–100) and `ready` (`confidence_score`, 0–100) but does not expose the four individual Outcome Confidence criteria that make up the aggregate:

- **A – Complexity** (0–25)
- **B – Test Coverage** (0–25)
- **C – Ambiguity** (0–25)
- **D – Change Surface** (0–25)

`confidence-check` computes these scores during execution but only persists the total (`outcome_confidence`) to frontmatter — the breakdown is lost after the session.

## Expected Behavior

After `/ll:confidence-check` runs on an issue:
- Four new frontmatter fields are written: `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` (integers 0–25 each)

`ll-issues refine-status` reads those fields and renders them as four new columns:

```
ID        Pri  Title                          ready  conf  cmplx  tcov  ambig  chsrf
BUG-123   P2   Fix auth token refresh          85    72     20     18     22     12
ENH-456   P3   Add score columns               —     —      —      —      —      —
```

Each column shows `—` when the field is absent (not yet confidence-checked).

## Motivation

The aggregate `conf` score hides which dimension is pulling the score down. Seeing "conf: 48" gives no actionable signal; seeing "cmplx: 10/25, tcov: 8/25, ambig: 20/25, chsrf: 10/25" immediately shows the issue is complex and touches many files. This per-dimension visibility allows engineers to target refinement effort precisely — e.g., add test scaffolding or reduce change surface — rather than re-running a full confidence check blind.

## Proposed Solution

**Part 1 — confidence-check write-back** (`skills/confidence-check/SKILL.md`):

Extend the Phase 3 frontmatter write step to include the four dimension scores alongside `confidence_score` and `outcome_confidence`:

```yaml
confidence_score: 85
outcome_confidence: 72
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 12
```

**Part 2 — refine-status columns** (`scripts/little_loops/cli/issues/refine_status.py`):

1. Add four new `_WIDTH` constants (e.g., `_DIM_WIDTH = 5` each — fits "25" + header "cmplx").
2. Register four new entries in `_STATIC_COLUMN_SPECS`:
   - `"score_complexity"` → `(_DIM_WIDTH, "cmplx", True)`
   - `"score_test_coverage"` → `(_DIM_WIDTH, "tcov", True)`
   - `"score_ambiguity"` → `(_DIM_WIDTH, "ambig", True)`
   - `"score_change_surface"` → `(_DIM_WIDTH, "chsrf", True)`
3. Add them to `_DEFAULT_STATIC_COLUMNS` after `"confidence"` (or configurable via `ll-config.json`).
4. In `_render_cell()` (or equivalent), read the corresponding frontmatter field from `IssueInfo` and format as integer string or `"—"`.

**Part 3 — issue_parser** (`scripts/little_loops/issue_parser.py`):

Add `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` as optional `int | None` fields to `IssueInfo` (or equivalent parsed model) so the CLI can access them.

## Integration Map

| Component | File | Change |
|---|---|---|
| confidence-check skill | `skills/confidence-check/SKILL.md` | Write 4 dimension scores to frontmatter in Phase 3 |
| issue_parser | `scripts/little_loops/issue_parser.py` | Add 4 optional `int \| None` fields to parsed model |
| refine_status CLI | `scripts/little_loops/cli/issues/refine_status.py` | Add 4 column specs, width constants, cell rendering |
| tests | `scripts/tests/test_refine_status.py` | Add fixtures with dimension score frontmatter, verify column output |
| config schema | `config-schema.json` | Update `columns` description string (line 681) to list new column names |
| RefineStatusConfig | `scripts/little_loops/config/cli.py` | Verify default `columns` list includes the 4 new keys (if configured here) |
| docs (API) | `docs/reference/API.md` | Add 4 new `IssueInfo` fields to dataclass listing (lines 522–542) |
| docs (CLI) | `docs/reference/CLI.md` | Add column names to refine-status column enumeration (lines 486, 499) |
| docs (Config) | `docs/reference/CONFIGURATION.md` | Add 4 new names to valid `columns` enumeration (lines 489–490) |
| docs (Template) | `docs/reference/ISSUE_TEMPLATE.md` | Add 4 new frontmatter fields alongside `confidence_score`/`outcome_confidence` |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction**: The write-back in `confidence-check` is **Phase 4** (not Phase 3 as noted above). Phase 3 is "Score and Recommend"; Phase 4 (`SKILL.md:398–432`) is the Edit-tool frontmatter update step.

**`skills/confidence-check/SKILL.md`**
- Phase 2b scores 4 criteria at lines 300–373 (A: Complexity, B: Test Coverage, C: Ambiguity, D: Change Surface — each 0–25)
- Phase 4 frontmatter write-back at lines 398–432 — extend the `confidence_score` / `outcome_confidence` block to also write `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`

**`scripts/little_loops/issue_parser.py`**
- `IssueInfo` dataclass: lines 201–240; `confidence_score` and `outcome_confidence` at lines 235–236 are the exact pattern to replicate
- Integer coercion pattern in `parse_file`: lines 347–356 — `raw = frontmatter.get("key")` → `int(raw) if raw is not None and str(raw).isdigit() else None`
- Add 4 new `raw` + coercion blocks after line 356 (after `outcome_raw` block, before `testable_raw`)
- Pass into `IssueInfo(...)` constructor at lines 378–396
- `to_dict` at lines 265–266 and `from_dict` at lines 288–289 — add 4 entries alongside `confidence_score` / `outcome_confidence`

**`scripts/little_loops/cli/issues/refine_status.py`**
- `_STATIC_COLUMN_SPECS` dict: lines 63–74 — add 4 entries; reuse `_SCORE_WIDTH` (= 5, same as `"ready"`)
- `_DEFAULT_STATIC_COLUMNS` list: lines 77–88 — insert 4 new keys after `"confidence"`, before `"total"`
- `_POST_CMD_STATIC` frozenset: line 91 — add all 4 keys (they render after the command block like `"ready"` and `"confidence"`)
- `_DEFAULT_ELIDE_ORDER` list: line 99 — insert 4 new keys before `"confidence"` (dropped first when terminal is narrow)
- `_cell_value` function: lines 393–416 — add 4 branches following the `"confidence"` pattern at lines 410–413; `"\u2014"` fallthrough for `None` is already the default
- `_print_key` legend: lines 475–489 — add 4 entries after the `"conf"` line (488) describing each sub-dimension

**JSON output** — `refine_status.py:292–329`
- The `--json` array block (lines 292–309) and `--format json` NDJSON block (lines 312–329) each build explicit field dicts — add all 4 new fields to both blocks alongside `"confidence_score"` / `"outcome_confidence"`

**Test files**
- `scripts/tests/test_refine_status.py:18–55` — `_make_issue()` helper sets frontmatter by keyword arg; extend its signature with the 4 new optional int params (model after `confidence_score` / `outcome_confidence`)
- `scripts/tests/test_refine_status.py:251–283` — `test_ready_and_outconf_columns` is the model for "value present → shows integer string"; `test_size_absent_shows_dash` (lines 318–347) is the model for "value absent → shows em-dash"
- `scripts/tests/test_issue_parser.py` — model new `int | None` field tests after existing `confidence_score` tests

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:522–542` — `IssueInfo` dataclass field listing; add 4 new fields after `outcome_confidence` entries [Agent 2]
- `docs/reference/CLI.md:486` — column enumeration in refine-status description; add `cmplx`, `tcov`, `ambig`, `chsrf` [Agent 2]
- `docs/reference/CLI.md:499` — narrow-terminal elide order description; update if new columns are added to `_DEFAULT_ELIDE_ORDER` [Agent 2]
- `docs/reference/CONFIGURATION.md:489` — valid column names list for `refine_status.columns`; add 4 new names [Agent 2]
- `docs/reference/ISSUE_TEMPLATE.md` — frontmatter field reference; add `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` alongside `confidence_score`/`outcome_confidence` [Agent 1]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py:1455–1595` — add new `TestIssueInfoScoreDimensions` class modeled after `TestIssueInfoSize`; write tests for default-None, value, `to_dict`, `from_dict`, `parse_file` present/absent for all four fields [Agent 3 — no existing coverage found]
- `scripts/tests/test_refine_status.py:819–827` — JSON record assertions; add 4 new field checks alongside `confidence_score`/`outcome_confidence` [Agent 2/3]
- `scripts/tests/test_refine_status.py:855–858` — JSON missing scores assertions; add 4 new fields (expected `None` when absent) [Agent 2/3]
- `scripts/tests/test_refine_status.py:1372–1374` — JSON flag test assertions; add 4 new fields [Agent 2/3]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:681` — `columns` array description string enumerates valid names; add `cmplx`/`tcov`/`ambig`/`chsrf` [Agent 2]
- `scripts/little_loops/config/cli.py` — `RefineStatusConfig` dataclass; verify whether default `columns` list is configured here and add the 4 new keys if so [Agent 1]

## Implementation Steps

1. **`SKILL.md:398–432` (Phase 4 write-back)**: Extend the frontmatter Edit block to add `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` using the Phase 2b per-criterion values (criteria A, B, C, D respectively).
2. **`issue_parser.py:235–236` (`IssueInfo`)**: Add 4 new `int | None = None` fields after `outcome_confidence`.
3. **`issue_parser.py:347–356` (`parse_file`)**: Add 4 raw → coercion blocks after the `outcome_raw` block (before `testable_raw` at line 357). Add each field to `to_dict` (lines 265–266) and `from_dict` (lines 288–289). Pass into the `IssueInfo(...)` constructor at lines 378–396.
4. **`refine_status.py:63–99`**: Add 4 entries to `_STATIC_COLUMN_SPECS` (reuse `_SCORE_WIDTH`), `_DEFAULT_STATIC_COLUMNS`, `_POST_CMD_STATIC`, and `_DEFAULT_ELIDE_ORDER`.
5. **`refine_status.py:406–416` (`_cell_value`)**: Add 4 branches following the `"confidence"` pattern (lines 410–413).
6. **`refine_status.py:292–329` (JSON blocks)**: Add all 4 fields to both the `--json` array dict (lines 292–309) and the `--format json` NDJSON dict (lines 312–329).
7. **`refine_status.py:487–489` (`_print_key`)**: Add 4 legend lines.
8. **`scripts/tests/test_refine_status.py`**: Extend `_make_issue()` (lines 18–55) with 4 new keyword params; add tests for value-present and value-absent cases modeled after `test_ready_and_outconf_columns` (lines 251–283) and `test_size_absent_shows_dash` (lines 318–347).
8. Run `python -m pytest scripts/tests/test_refine_status.py scripts/tests/test_issue_parser.py -v` to confirm.
5. Update `scripts/tests/test_refine_status.py`: add test cases with issues that have / do not have dimension score frontmatter and assert column output.
6. Run `python -m pytest scripts/tests/test_refine_status.py -v` to confirm.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `config-schema.json:681` — append `cmplx`, `tcov`, `ambig`, `chsrf` to the `columns` description string
10. Check `scripts/little_loops/config/cli.py` (`RefineStatusConfig`) — if a default `columns` list exists, add the 4 new keys after `"confidence"`
11. Update `docs/reference/API.md:536–537` — add 4 new `int | None = None` field entries to the `IssueInfo` listing after `outcome_confidence`
12. Update `docs/reference/CLI.md:486,499` — add new column names to the refine-status column enumeration and elide order description
13. Update `docs/reference/CONFIGURATION.md:489–490` — add 4 new names to the valid `refine_status.columns` enumeration
14. Update `docs/reference/ISSUE_TEMPLATE.md` — add `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` as optional frontmatter fields
15. In `test_issue_parser.py`, add `TestIssueInfoScoreDimensions` class (modeled after `TestIssueInfoSize`, lines 1455–1595) covering default-None, value, `to_dict`, `from_dict`, `parse_file` present/absent for all four fields
16. Extend JSON record assertions in `test_refine_status.py` at lines 819–827, 855–858, and 1372–1374 to include all 4 new dimension score fields

## Scope Boundaries

- **Not in scope**: Changes to the confidence-check scoring algorithm, criteria weights, or thresholds — this enhancement only exposes already-computed values
- **Not in scope**: Adding new scoring criteria beyond the existing four (Complexity, Test Coverage, Ambiguity, Change Surface)
- **Not in scope**: Making dimension score fields required frontmatter — issues without scores display `—` (backward-compatible additive change)
- **Not in scope**: Filtering or sorting by individual dimension scores in `refine-status` — display-only columns
- **Not in scope**: Changes to existing `ready` or `conf` column behavior

## Impact

- **Files changed**: ~3–4 (SKILL.md, issue_parser.py, refine_status.py, test_refine_status.py)
- **Risk**: Low — additive only; existing columns and rendering logic are unchanged
- **Backwards compat**: Issues without dimension scores show `—` in new columns — no breakage

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/confidence-check/SKILL.md` | Defines the 4 Outcome Confidence criteria and current write-back |
| `scripts/little_loops/cli/issues/refine_status.py` | Current column registration pattern to follow |
| `scripts/tests/test_refine_status.py` | Existing test patterns for column assertions |

## Labels

`enhancement`, `ll-issues`, `refine-status`, `confidence-check`, `cli`

---

## Resolution

**State**: Completed  
**Completed**: 2026-04-13

### Changes Made

- `skills/confidence-check/SKILL.md` — Extended Phase 4 frontmatter write-back to include `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` (0–25 each) alongside the existing aggregate scores
- `scripts/little_loops/issue_parser.py` — Added 4 new `int | None = None` fields to `IssueInfo`; added parse blocks, `to_dict`, `from_dict` entries, and constructor args
- `scripts/little_loops/cli/issues/refine_status.py` — Added 4 column specs (`cmplx`, `tcov`, `ambig`, `chsrf`) to `_STATIC_COLUMN_SPECS`, `_DEFAULT_STATIC_COLUMNS`, `_POST_CMD_STATIC`, `_DEFAULT_ELIDE_ORDER`; added `_cell_value` branches; updated both JSON output blocks; added legend entries to `_print_key`
- `scripts/tests/test_refine_status.py` — Extended `_make_issue` with 4 new params; added `test_dimension_score_columns_present` and `test_dimension_score_columns_absent`; updated JSON assertion tests; added terminal width mocks to 5 tests that needed wide-terminal rendering
- `scripts/tests/test_issue_parser.py` — Added `TestIssueInfoScoreDimensions` class (8 tests covering default-None, values, `to_dict`, `from_dict`, `parse_file` present/absent)
- `config-schema.json` — Updated `columns` description to list new column names
- `docs/reference/API.md` — Added 4 new `IssueInfo` fields to dataclass listing
- `docs/reference/CLI.md` — Added column names to refine-status description and updated elide order description
- `docs/reference/CONFIGURATION.md` — Updated valid `columns` enumeration and default `elide_order`
- `docs/reference/ISSUE_TEMPLATE.md` — Added 4 new optional frontmatter fields

### Verification

All 4757 tests pass.

---

## Status

**State**: Completed
**Assignee**: —
**Milestone**: —

## Session Log
- `/ll:ready-issue` - 2026-04-13T20:15:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4119b7f-c66e-4356-ba44-626aab115633.jsonl`
- `/ll:confidence-check` - 2026-04-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c3151a7-1ff6-4fbf-9704-43e5cc5e1606.jsonl`
- `/ll:wire-issue` - 2026-04-13T20:09:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53122ea2-9d1d-40fb-96e4-bb9f54c45744.jsonl`
- `/ll:refine-issue` - 2026-04-13T19:29:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9695aacf-403b-43f3-b1c5-452f7a1b7656.jsonl`
- `/ll:capture-issue` - 2026-04-13T14:24:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac88abde-52c1-42fa-afd6-ba7adbf884d8.jsonl`
- `/ll:manage-issue` - 2026-04-13T00:00:00 - implemented
