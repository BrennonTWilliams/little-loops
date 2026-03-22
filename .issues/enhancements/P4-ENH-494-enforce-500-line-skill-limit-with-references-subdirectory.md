---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 86
outcome_confidence: 72
---

# ENH-494: Enforce 500-Line SKILL.md Limit with references/ Subdirectory Pattern

## Summary

Skills should stay under 500 lines to minimize context consumption when loaded. Overflow content belongs in a `skills/<name>/references/` subdirectory that is loaded on demand. This is a direct application of progressive disclosure: skills should be cheap to load, with full reference material available but not forced into context.

## Current Behavior

Some skills (e.g., `manage-issue`, `review-sprint`, `confidence-check`) likely exceed 500 lines. All skill content is loaded into context whenever the skill is active, regardless of whether the full content is needed for the current task.

There is no `references/` subdirectory convention and no enforcement of a line limit.

## Expected Behavior

- All `SKILL.md` files remain at or under 500 lines
- Detailed reference material, examples, and extended documentation live in `skills/<name>/references/*.md`
- The `SKILL.md` links to reference files with clear "see also" pointers
- A linting check (or documentation convention) establishes 500 lines as the limit

## Motivation

Every line in a `SKILL.md` is loaded into the context window when that skill is active. Large skills consume attention budget even when only a fraction of their content is relevant. The 500-line limit is not arbitrary — it's the same progressive disclosure principle the skills themselves teach. Practicing what we preach improves both performance and credibility.

## Proposed Solution

1. Audit all 16 `skills/*/SKILL.md` files for line count: `wc -l skills/*/SKILL.md`
2. For any skill exceeding 500 lines, identify what content is "reference" vs. "operational"
3. Create `skills/<name>/references/` directories for overflow content
4. Add "See also" links in `SKILL.md` pointing to reference files
5. Document the 500-line convention in `CONTRIBUTING.md`
6. Optionally add a `ll-check-links` or similar lint check for skill size

## Scope Boundaries

- **In scope**: Auditing skill sizes, extracting overflow to `references/`, documenting the convention
- **Out of scope**: Changing skill logic or rewriting skill content substantively

## Implementation Steps

1. ~~Run `wc -l skills/*/SKILL.md | sort -n` to identify oversized skills~~ (**Done — see Research Findings below**)
2. For each violating skill, extract reference/example sections to `references/` files
3. Add `## See Also` section in `SKILL.md` with links
4. Update `CONTRIBUTING.md` with the 500-line limit and `references/` pattern
5. Optionally extend `ll-check-links` to also check skill line counts

### Codebase Research Findings

_Added by `/ll:refine-issue` — Skill line count audit:_

**Current line counts (descending):**
```
708  skills/audit-claude-config/SKILL.md  ← EXCEEDS by 208 lines
604  skills/confidence-check/SKILL.md     ← EXCEEDS by 104 lines (was 554)
513  skills/manage-issue/SKILL.md         ← EXCEEDS by 13 lines (was 500 at boundary)
386  skills/init/SKILL.md
371  skills/capture-issue/SKILL.md
356  skills/format-issue/SKILL.md
335  skills/audit-docs/SKILL.md
305  skills/create-loop/SKILL.md
304  skills/configure/SKILL.md
295  skills/workflow-automation-proposer/SKILL.md
280  skills/product-analyzer/SKILL.md
275  skills/issue-size-review/SKILL.md
173  skills/map-dependencies/SKILL.md
168  skills/issue-workflow/SKILL.md
116  skills/analyze-history/SKILL.md
```

**3 skills now exceed 500 lines** (was 2):
- `audit-claude-config/SKILL.md` (708 lines) — extract wave definitions, sub-agent prompt templates, or audit checklists to `references/`
- `confidence-check/SKILL.md` (604 lines, was 533) — extract scoring rubrics or evaluation criteria to `references/`
- `manage-issue/SKILL.md` (513 lines, was 500) — extract phase details or reference patterns to `references/`

**No `references/` subdirectories exist yet** — this PR establishes the convention from scratch

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` — oversized skills only
- `CONTRIBUTING.md` — add convention documentation

### New Files
- `skills/<name>/references/*.md` — one or more per oversized skill

### Tests
- `wc -l skills/*/SKILL.md` should show all files ≤ 500 lines

### Documentation
- `CONTRIBUTING.md` — new section on skill size limits

## Impact

- **Priority**: P4 — Incremental improvement; not blocking
- **Effort**: Low — Audit + text reorganization, no code changes
- **Risk**: Low — Reorganization only, skill behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `CONTRIBUTING.md` | Development conventions — target file for 500-line limit and `references/` pattern documentation |

## Labels

`enhancement`, `skills`, `context-engineering`, `progressive-disclosure`

## Session Log
- `/ll:tradeoff-review-issues` - 2026-03-22T05:05:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a58662a-8ea7-4c74-bb16-c6d77d559e08.jsonl`
- `/ll:verify-issues` - 2026-03-22T02:49:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45cffc78-99fd-4e36-9bcb-32d53f60d9c2.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Completed skill line count audit; 2 skills exceed 500 lines: audit-claude-config (708) and confidence-check (524)
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; still blocked by ENH-493, ENH-491, FEAT-441
- `/ll:verify-issues` - 2026-03-03 - Updated line counts: confidence-check 524→533, manage-issue 447→500 (now AT limit). Removed ENH-491 and FEAT-441 from Blocked By (both completed)
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `CONTRIBUTING.md` to Related Key Documentation
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: audit-claude-config (708 lines) and confidence-check (533 lines) still exceed 500; removed stale Blocks refs ENH-502 and ENH-496 (both completed)
- `/ll:refine-issue` + `/ll:confidence-check` - 2026-03-06 - Re-assessed knowledge gaps: none new. Line counts re-confirmed (708, 533). `references/` pattern is clear; implementation steps fully specified. Raised confidence_score 80→86 (all research done, no open unknowns) and outcome_confidence 68→72 (slight residual uncertainty from ENH-493 blocker — reorganization needs to align with trigger description style before splitting content).
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: audit-claude-config(708L), confidence-check(533L) exceed limit
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: audit-claude-config (708L) and confidence-check (533L) still exceed 500-line limit; no `references/` subdirs exist
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — NEEDS_UPDATE: removed FEAT-638 (missing) and ENH-668 (completed) from Blocked By; updated confidence-check line count 533→554

---

## Verification Notes

- **Date**: 2026-03-21
- **Verdict**: NEEDS_UPDATE
- `audit-claude-config/SKILL.md` = **708 lines** (unchanged), `confidence-check/SKILL.md` = **604 lines** (was 554 — grew 50 lines), `manage-issue/SKILL.md` = **513 lines** (was 500 — now exceeds limit). No `references/` subdirectories exist. Enhancement scope now covers **3 skills** exceeding 500 lines (was 2).

## Status

**Open** | Created: 2026-02-24 | Priority: P4

---

## Tradeoff Review Note

**Reviewed**: 2026-02-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Only 2 skills exceed the 500-line limit (audit-claude-config: 708, confidence-check: 524), making scope smaller than expected. However, the `references/` subdirectory pattern needs to be defined and documented before extracting content. Blocked by ENH-493 (trigger descriptions), ENH-491, and FEAT-441. Implement after those resolve and the pattern convention is established in CONTRIBUTING.md.

## Blocked By
- ENH-493
- FEAT-565

---

## Tradeoff Review Note (2026-03-03 Update)

**Reviewed**: 2026-03-03 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first — Implement ENH-493 (rewrite skill descriptions as trigger documents) first. Only after trigger descriptions are finalized should content be split into `references/` directories, so that reorganized reference material matches the new description style. Scope remains well-bounded (only 2 skills exceed 500 lines). Implementation is straightforward once ENH-493 resolves.

## Tradeoff Review Note (2026-03-22 Update)

**Reviewed**: 2026-03-22 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Blocked by ENH-493 (rewrite skill descriptions as trigger documents). Content must be split into `references/` directories only after the trigger description style is finalized, so reorganized reference material is consistent with the new description style. Scope has grown to 3 violating skills (audit-claude-config: 708L, confidence-check: 604L, manage-issue: 513L). Implementation is straightforward once ENH-493 resolves.

## Blocks