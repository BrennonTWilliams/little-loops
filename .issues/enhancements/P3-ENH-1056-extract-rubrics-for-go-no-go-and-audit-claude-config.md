---
discovered_date: 2026-04-12
discovered_by: issue-size-review
confidence_score: 88
outcome_confidence: 78
---

# ENH-1056: Extract rubrics for go-no-go and audit-claude-config skills

## Summary

Extract inline agent prompt templates from `go-no-go` and inline audit criteria from `audit-claude-config` into companion artifact files, update each SKILL.md to load the companion file, and add test files that verify the files exist with expected content.

## Parent Issue

Decomposed from ENH-1053: Externalize scoring rubrics in audit/review skills into project-tailorable artifacts

## Motivation

`go-no-go` embeds verbatim Pro/Con/Judge agent prompt templates directly in SKILL.md (lines 148–290). `audit-claude-config` distributes its audit dimensions, component checklists, and validation lists across three Task prompts (lines 126–186, 195–229, 262–330). Projects cannot customize these without forking the plugin. Extracting into companion files enables project-level overrides via `.ll/rubrics/<skill>.md`.

## Expected Behavior

```
skills/go-no-go/SKILL.md            ← logic only; loads agent-prompts/rubric
skills/go-no-go/rubric.md           ← Pro, Con, Judge prompt templates + verdict taxonomy
.ll/rubrics/go-no-go.md             ← project override (gitignored or committed per project)

skills/audit-claude-config/SKILL.md ← logic only; loads criteria
skills/audit-claude-config/audit-criteria.md  ← audit dimensions, checklists, key lists
.ll/rubrics/audit-claude-config.md  ← project override
```

**Naming note:** `audit-claude-config` already has a `report-template.md` companion. Use `audit-criteria.md` (not `rubric.md`) to distinguish criteria from report format.

**Naming note for go-no-go:** The "rubric" is three verbatim agent prompt templates with a verdict taxonomy (`CLOSE`/`REFINE`/`SKIP`). Keep `rubric.md` for consistency with other skills (or use `agent-prompts.md` — either is acceptable; `rubric.md` preferred for consistency).

## Scope

**In scope:**
- `skills/go-no-go/SKILL.md` — remove agent prompt templates (lines 148–290), add load-rubric directive after line 143 (`**IMPORTANT**` note)
- `skills/go-no-go/rubric.md` — new file: Pro agent prompt (6 directives + 5 output sections), Con agent prompt (6 directives + 5 output sections), Judge prompt (4 dimensions + CLOSE/REFINE/SKIP verdict taxonomy)
- `skills/audit-claude-config/SKILL.md` — remove distributed criteria from 3 Task prompts (lines 126–186, 195–229, 262–330), add load-criteria directive inside each Task prompt
- `skills/audit-claude-config/audit-criteria.md` — new file: CLAUDE.md audit dimensions, plugin component checklists, settings key validation list + deprecated/managed-only keys
- `scripts/tests/test_go_no_go_skill.py` — verify SKILL.md references `rubric.md`, file exists, contains judge verdict taxonomy (CLOSE/REFINE/SKIP); follow pattern in `scripts/tests/test_improve_claude_md_skill.py`
- `scripts/tests/test_audit_claude_config_skill.py` — verify SKILL.md references `audit-criteria.md`, file exists; also assert `report-template.md` is still referenced after refactor

**Out of scope:** confidence-check, issue-size-review (ENH-1055); documentation updates (ENH-1057)

## Implementation Steps

### 1. Extract `go-no-go` rubric

- Read `skills/go-no-go/SKILL.md` lines 143–290 to identify exact prompt template content
- Create `skills/go-no-go/rubric.md` with:
  - Section: `## Pro Agent Prompt` — 6 directives + 5 output sections
  - Section: `## Con Agent Prompt` — 6 directives + 5 output sections
  - Section: `## Judge Prompt` — 4 dimensions + CLOSE/REFINE/SKIP verdict taxonomy
- In SKILL.md, replace lines 148–290 with load directive after the `**IMPORTANT**` note at line 143:
  ```
  Read `rubric.md` (this companion file) now — or `.ll/rubrics/go-no-go.md` if it exists (project override takes precedence). You will need the pro, con, and judge agent prompt templates.
  ```

### 2. Extract `audit-claude-config` criteria

- Read `skills/audit-claude-config/SKILL.md` lines 126–186, 195–229, and 262–330 to identify exact criteria content
- Create `skills/audit-claude-config/audit-criteria.md` with:
  - Section: `## CLAUDE.md Audit Dimensions` — from lines 126–186
  - Section: `## Plugin Component Checklists` — from lines 195–229
  - Section: `## Settings Key Validation` — key validation list + deprecated/managed-only keys from lines 262–330
- In SKILL.md, replace extracted content inside each Task prompt with load-criteria directive referencing `audit-criteria.md` (and `.ll/rubrics/audit-claude-config.md` as override)
- Verify `report-template.md` reference is untouched

### 3. Create test files

Follow pattern in `scripts/tests/test_improve_claude_md_skill.py`:

- `scripts/tests/test_go_no_go_skill.py`:
  - Assert `skills/go-no-go/rubric.md` exists
  - Assert SKILL.md contains `rubric.md` reference
  - Assert rubric contains CLOSE/REFINE/SKIP verdict taxonomy text

- `scripts/tests/test_audit_claude_config_skill.py`:
  - Assert `skills/audit-claude-config/audit-criteria.md` exists
  - Assert SKILL.md references `audit-criteria.md`
  - Assert SKILL.md still references `report-template.md` (regression check)

## Codebase Research Findings

**Exact line ranges:**

| Skill | Content | Lines |
|---|---|---|
| `go-no-go/SKILL.md` | Pro/Con/Judge agent prompt templates + verdict taxonomy | 148–290 |
| `audit-claude-config/SKILL.md` | CLAUDE.md audit dimensions | 126–186 |
| `audit-claude-config/SKILL.md` | Plugin component checklists | 195–229 |
| `audit-claude-config/SKILL.md` | Settings key validation + deprecated keys | 262–330 |

**Load idiom from** `skills/review-loop/SKILL.md:67-69`: explicit imperative with stated purpose — follow this pattern exactly.

**Existing companion** `skills/audit-claude-config/report-template.md` confirms this pattern already works for audit-config; `audit-criteria.md` follows the same convention.

**Test pattern from** `scripts/tests/test_improve_claude_md_skill.py`.

## Success Metrics

- `/ll:go-no-go` produces identical verdicts using prompt templates loaded from `rubric.md`
- `/ll:audit-claude-config` produces identical audit output using criteria loaded from `audit-criteria.md`
- `report-template.md` is still referenced in `audit-claude-config/SKILL.md` after refactor
- Both new test files pass `python -m pytest`
- Deleting `.ll/rubrics/go-no-go.md` falls back to default `rubric.md` with no error

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after extraction complete)
- FEAT-948: Rules-and-decisions log (integration target — rubric sync)

---

## Impact

- **Priority**: P3
- **Effort**: Small-Medium — 2 new companion files, 2 SKILL.md refactors, 2 test files; audit-claude-config has non-contiguous extraction
- **Risk**: Low-Medium — audit-claude-config has distributed criteria across 3 Task prompts (non-contiguous extraction is trickier)
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
