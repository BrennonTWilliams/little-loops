---
discovered_date: 2026-04-12
discovered_by: issue-size-review
confidence_score: 85
outcome_confidence: 82
---

# ENH-1057: Documentation updates for rubric externalization system

## Summary

After ENH-1055 and ENH-1056 complete rubric extraction from all four skills, update documentation to reflect the new `.ll/rubrics/` override convention, add `rubric.md` and `audit-criteria.md` entries to the architecture directory trees, and conditionally patch inline threshold/criterion references in guides.

## Parent Issue

Decomposed from ENH-1053: Externalize scoring rubrics in audit/review skills into project-tailorable artifacts

## Dependency

**Depends on ENH-1055 and ENH-1056 being complete.** These docs updates make no sense until the companion files exist and the SKILL.md load directives are in place.

## Scope

**In scope (unconditional):**
- `docs/ARCHITECTURE.md` — add `rubric.md` entries under `confidence-check/`, `go-no-go/`, `issue-size-review/` directory trees (lines 117–118, 133–134, 141–142); add `audit-criteria.md` alongside existing `report-template.md` in `audit-claude-config/` block (lines 105–106)
- `docs/reference/CONFIGURATION.md` — add new section documenting `.ll/rubrics/<skill>.md` project override path, fallback behavior (silently falls back to `skills/<skill>/rubric.md`), and FEAT-948 integration point

**In scope (conditional — update only if defaults changed during extraction):**
- `docs/reference/COMMANDS.md:237-243` — documents `issue-size-review` thresholds; update only if `issue-size-review/rubric.md` changes the "1–10 scale" or "≥8 = Very Large" values
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:336-337` — names `confidence-check` criterion labels verbatim; update only if criterion names are reorganized during ENH-1055 extraction
- `docs/guides/LOOPS_GUIDE.md:332` — hard-codes "Very Large issues (score ≥ 8)"; update only if `issue-size-review/rubric.md` changes the decomposition threshold

## Implementation Steps

### 1. Update ARCHITECTURE.md

Read `docs/ARCHITECTURE.md` around lines 105–145. For each affected skill directory tree:
- Add `rubric.md` entry under `confidence-check/`, `go-no-go/`, `issue-size-review/`
- Add `audit-criteria.md` alongside `report-template.md` under `audit-claude-config/`

Example format (follow existing tree structure):
```
skills/
  confidence-check/
    SKILL.md
    rubric.md          ← new: default readiness + outcome-confidence criteria
  go-no-go/
    SKILL.md
    rubric.md          ← new: pro/con/judge agent prompt templates
  issue-size-review/
    SKILL.md
    rubric.md          ← new: scoring heuristics and size thresholds
  audit-claude-config/
    SKILL.md
    report-template.md
    audit-criteria.md  ← new: CLAUDE.md dimensions, component checklists, key lists
```

### 2. Add configuration section to CONFIGURATION.md

Read `docs/reference/CONFIGURATION.md` to find the appropriate insertion point. Add a new section (suggested title: `## Rubric Overrides`):

```markdown
## Rubric Overrides

Skills that score, audit, or review issues load their scoring criteria from companion `rubric.md` files (or `audit-criteria.md` for `audit-claude-config`). Projects can override these defaults without modifying the plugin:

| Override Path | Default | Affected Skill |
|---|---|---|
| `.ll/rubrics/confidence-check.md` | `skills/confidence-check/rubric.md` | `/ll:confidence-check` |
| `.ll/rubrics/issue-size-review.md` | `skills/issue-size-review/rubric.md` | `/ll:issue-size-review` |
| `.ll/rubrics/go-no-go.md` | `skills/go-no-go/rubric.md` | `/ll:go-no-go` |
| `.ll/rubrics/audit-claude-config.md` | `skills/audit-claude-config/audit-criteria.md` | `/ll:audit-claude-config` |

**Fallback behavior**: If the override file does not exist, the skill silently uses the default companion file. No error is emitted.

**File format**: Override files must be complete replacements of the default (no partial merging). Copy the default and modify as needed.

**FEAT-948 integration**: When the rules-and-decisions log (FEAT-948) is implemented, it will write project-specific rubric updates to `.ll/rubrics/` — not to `skills/` — so shipped defaults remain stable.
```

### 3. Conditional doc patches (check AFTER ENH-1055/ENH-1056 complete)

For each conditional update:
- Read the target file at the specified lines
- Compare the inline values against what was actually written into `rubric.md`/`audit-criteria.md`
- **Only edit if the values differ** — if defaults were preserved verbatim, no change needed

| File | Lines | Check |
|---|---|---|
| `docs/reference/COMMANDS.md` | 237–243 | `issue-size-review` threshold values ("≥8 = Very Large") |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` | 336–337 | `confidence-check` criterion label names |
| `docs/guides/LOOPS_GUIDE.md` | 332 | "Very Large issues (score ≥ 8)" threshold |

## Success Metrics

- `docs/ARCHITECTURE.md` shows `rubric.md` and `audit-criteria.md` in the correct skill directory trees
- `docs/reference/CONFIGURATION.md` has a Rubric Overrides section with override path table
- Conditional files are updated if and only if defaults changed (no spurious edits)
- `ll-verify-docs` passes (if it checks companion file counts)
- `ll-check-links` passes (if it checks link validity in docs)

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (dependency)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (dependency)
- FEAT-948: Rules-and-decisions log (integration target — rubric sync, referenced in new config section)

---

## Impact

- **Priority**: P3
- **Effort**: Small — docs-only; conditional patches likely no-ops if defaults preserved
- **Risk**: Very Low — documentation only; no behavior changes
- **Breaking Change**: No

## Labels

`enhancement`, `docs`, `rubrics`, `project-tailorable`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
