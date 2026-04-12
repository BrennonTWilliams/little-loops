---
discovered_date: 2026-04-12
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 80
---

# ENH-1055: Extract rubrics for confidence-check and issue-size-review skills

## Summary

Extract inline scoring rubrics from `confidence-check` and `issue-size-review` into companion `rubric.md` files, update each SKILL.md to load the rubric, and add test files that verify the rubric files exist with the expected content.

## Parent Issue

Decomposed from ENH-1053: Externalize scoring rubrics in audit/review skills into project-tailorable artifacts

## Motivation

Both skills embed scoring criteria directly in SKILL.md. Projects cannot adjust thresholds or heuristics without forking the plugin. Extracting into companion files enables project-level overrides via `.ll/rubrics/<skill>.md`.

## Expected Behavior

```
skills/confidence-check/SKILL.md    ← logic only; loads rubric
skills/confidence-check/rubric.md   ← default criteria (checked in)
.ll/rubrics/confidence-check.md     ← project override (gitignored or committed per project)
```

Load idiom (from `skills/review-loop/SKILL.md:67-69`):
```
Read `rubric.md` (this companion file) now. You will need the criterion definitions and scoring tables.
If `.ll/rubrics/confidence-check.md` exists, read that instead — it takes precedence over the default.
```

## Scope

**In scope:**
- `skills/confidence-check/SKILL.md` — remove inline rubric (lines 181–373 and 380–394), add load-rubric directive
- `skills/confidence-check/rubric.md` — new file: readiness criteria (5 × 0–20 pts) + outcome-confidence criteria (4 × 0–25 pts) + both threshold tables
- `skills/issue-size-review/SKILL.md` — remove inline scoring heuristic table (lines 112–124) and threshold section (lines 326–332), add load-rubric directive
- `skills/issue-size-review/rubric.md` — new file: 11-point scoring heuristic table + 4-tier size threshold table
- `scripts/tests/test_confidence_check_skill.py` — verify SKILL.md references `rubric.md`, `rubric.md` exists, contains readiness + outcome-confidence headings; follow pattern in `scripts/tests/test_improve_claude_md_skill.py`
- `scripts/tests/test_issue_size_review_skill.py` — same pattern; assert `rubric.md` exists and contains scoring heuristic table and threshold section

**Out of scope:** go-no-go, audit-claude-config (ENH-1056); documentation updates (ENH-1057)

## Implementation Steps

### 1. Extract `confidence-check` rubric

- Read `skills/confidence-check/SKILL.md` lines 181–394 to identify exact rubric content
- Create `skills/confidence-check/rubric.md` with:
  - Section: `## Readiness Criteria` — 5 criteria blocks (0–20 pts each)
  - Section: `## Outcome-Confidence Criteria` — 4 criteria blocks (0–25 pts each)
  - Section: `## Scoring Thresholds` — both threshold tables
- In SKILL.md, replace extracted content with load directive at the insertion point (line 180):
  ```
  Read `rubric.md` (this companion file) now — or `.ll/rubrics/confidence-check.md` if it exists (project override takes precedence). You will need all criterion definitions and scoring tables.
  ```

### 2. Extract `issue-size-review` rubric

- Read `skills/issue-size-review/SKILL.md` lines 112–124 and 326–332 to identify exact rubric content
- Create `skills/issue-size-review/rubric.md` with:
  - Section: `## Scoring Heuristics` — 5-row table (criterion / points / detection)
  - Section: `## Size Thresholds` — 4-tier table (score / assessment / recommendation)
- In SKILL.md, replace scoring table at line 112 with load directive; also replace threshold section at line 326

### 3. Create test files

Follow pattern in `scripts/tests/test_improve_claude_md_skill.py`:

- `scripts/tests/test_confidence_check_skill.py`:
  - Assert `skills/confidence-check/rubric.md` exists
  - Assert SKILL.md contains `rubric.md` reference
  - Assert rubric contains `## Readiness Criteria` and `## Outcome-Confidence Criteria` headings

- `scripts/tests/test_issue_size_review_skill.py`:
  - Assert `skills/issue-size-review/rubric.md` exists
  - Assert SKILL.md contains `rubric.md` reference
  - Assert rubric contains scoring heuristic table and `## Size Thresholds` section

## Codebase Research Findings

**Exact line ranges:**

| Skill | Content | Lines |
|---|---|---|
| `confidence-check/SKILL.md` | 9 criteria blocks + 2 threshold tables | 181–373 (criteria), 380–394 (thresholds) |
| `issue-size-review/SKILL.md` | 5-row scoring table + 4-tier threshold table | 112–124 (scoring), 326–332 (thresholds) |

**Load idiom from** `skills/review-loop/SKILL.md:67-69`: explicit imperative with stated purpose — follow this pattern exactly.

**Test pattern from** `scripts/tests/test_improve_claude_md_skill.py`.

## Success Metrics

- `/ll:confidence-check` produces identical scores on a known issue after rubric extraction
- `/ll:issue-size-review` reads scoring heuristics from `rubric.md`
- Creating `.ll/rubrics/issue-size-review.md` with custom threshold (e.g., `≥4 = Large`) causes `issue-size-review` to use the override
- Removing `.ll/rubrics/confidence-check.md` falls back to default with no error
- Both new test files pass `python -m pytest`

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after extraction complete)
- FEAT-948: Rules-and-decisions log (integration target — rubric sync)

---

## Impact

- **Priority**: P3
- **Effort**: Small-Medium — 2 new files, 2 SKILL.md edits, 2 test files
- **Risk**: Low — content-only extraction; no Python changes; fallback keeps behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
