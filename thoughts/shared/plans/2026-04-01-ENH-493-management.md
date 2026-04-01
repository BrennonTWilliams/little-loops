# ENH-493: Rewrite Skill Descriptions as Trigger Documents

**Created**: 2026-04-01
**Issue**: `.issues/enhancements/P3-ENH-493-rewrite-skill-descriptions-as-trigger-documents.md`
**Action**: improve

## Research Findings

- All 21 SKILL.md files confirmed. 8 have summary-only descriptions, 13 have trigger keywords but lead with summary text.
- The `description` field is consumed directly by Claude Code runtime for auto-activation — no propagation automation exists.
- CONTRIBUTING.md (lines 440-455) has a template that already shows the `Trigger keywords:` pattern but doesn't explain the convention.
- `.claude/CLAUDE.md` has hand-authored parenthetical notes independent of SKILL.md descriptions.
- Target format: Lead with trigger conditions ("Use when..."), followed by brief context, then `Trigger keywords:` line.

## Implementation Plan

### Phase 1: Rewrite 8 summary-only skills
Add trigger-condition-first descriptions with `Trigger keywords:` to:
1. `skills/audit-claude-config/SKILL.md`
2. `skills/audit-docs/SKILL.md`
3. `skills/configure/SKILL.md`
4. `skills/create-loop/SKILL.md`
5. `skills/format-issue/SKILL.md`
6. `skills/init/SKILL.md`
7. `skills/manage-issue/SKILL.md`
8. `skills/review-loop/SKILL.md`

### Phase 2: Restructure 13 skills with existing keywords
Rewrite descriptions to lead with trigger conditions instead of summary:
1. `skills/analyze-history/SKILL.md`
2. `skills/analyze-loop/SKILL.md`
3. `skills/capture-issue/SKILL.md`
4. `skills/cleanup-loops/SKILL.md`
5. `skills/confidence-check/SKILL.md`
6. `skills/go-no-go/SKILL.md`
7. `skills/issue-size-review/SKILL.md`
8. `skills/issue-workflow/SKILL.md`
9. `skills/map-dependencies/SKILL.md`
10. `skills/product-analyzer/SKILL.md`
11. `skills/update/SKILL.md`
12. `skills/update-docs/SKILL.md`
13. `skills/workflow-automation-proposer/SKILL.md`

### Phase 3: Update CONTRIBUTING.md
Update the skill template (lines 440-455) to document the trigger-phrase-first convention with explanation.

### Phase 4: Verify
- `ruff check scripts/` (no Python changes expected, but sanity check)
- Manual review of all 21 descriptions for consistency

## TDD Note
TDD Phase 3a skipped: This is a YAML frontmatter text-editing task with no testable Python code changes. The issue's own test plan calls for manual testing ("does Claude activate the right skill when using trigger phrases?").

## Success Criteria
- [ ] All 21 SKILL.md descriptions lead with trigger conditions
- [ ] All 21 SKILL.md descriptions include `Trigger keywords:` line
- [ ] CONTRIBUTING.md documents the trigger-phrase convention
- [ ] No other file content (body, tools, model) changed
