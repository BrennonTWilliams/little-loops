---
id: ENH-1099
type: ENH
priority: P3
discovered_date: 2026-04-13
discovered_by: capture-issue
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

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md` Phase 3 write-back section and add the four dimension score fields to the frontmatter update block.
2. Read `scripts/little_loops/issue_parser.py`, find the `IssueInfo` model, add four optional int fields.
3. Confirm the parser reads YAML frontmatter and maps field names — verify `score_complexity` etc. will be parsed from the YAML key of the same name.
4. In `refine_status.py`: add width constants, column specs, extend `_DEFAULT_STATIC_COLUMNS`, and wire cell rendering.
5. Update `scripts/tests/test_refine_status.py`: add test cases with issues that have / do not have dimension score frontmatter and assert column output.
6. Run `python -m pytest scripts/tests/test_refine_status.py -v` to confirm.

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

## Status

**State**: Open
**Assignee**: —
**Milestone**: —

## Session Log
- `/ll:capture-issue` - 2026-04-13T14:24:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac88abde-52c1-42fa-afd6-ba7adbf884d8.jsonl`
