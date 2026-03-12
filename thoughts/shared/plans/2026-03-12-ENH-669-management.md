# ENH-669: Add `--auto` flag to issue prep skills

## Overview
Add `--auto` flag to three skills (`verify-issues`, `map-dependencies`, `issue-size-review`) so they can run non-interactively in FSM loop automation contexts.

## Changes

### 1. `commands/verify-issues.md` (Pattern A)
- Add `flags` argument to frontmatter (lines 10-13)
- Add `### 0. Parse Flags` section before `### 1. Find Issues to Verify` (before line 28)
- Gate `### 3. Request User Approval` (lines 98-107) behind `AUTO_MODE`
- In auto mode: skip confirmation, proceed directly to Phase 4 (update files)
- Add `--auto` to Arguments section and Examples

### 2. `skills/map-dependencies/SKILL.md` (Pattern B)
- Add `## Arguments` section with `$ARGUMENTS` parsing before `## How to Use` (line 29)
- Gate `AskUserQuestion` in `## Applying Proposals` (lines 120-123) behind `AUTO_MODE`
- In auto mode: apply all HIGH-confidence proposals automatically, skip MEDIUM
- Add `--auto` to Examples table

### 3. `skills/issue-size-review/SKILL.md` (Pattern B)
- Add `## Arguments` section with `$ARGUMENTS` parsing before `## Workflow` (line 35)
- Gate `AskUserQuestion` in `### Phase 4: User Approval` (lines 95-111) behind `AUTO_MODE`
- In auto mode: auto-decompose issues scoring ≥8 (Very Large), skip 5-7 (ambiguous)
- Add `--auto` to Examples table

## Auto-Mode Conservative Defaults
- **verify-issues**: Apply all non-destructive updates (verification notes, line number fixes). Skip moving resolved issues (destructive).
- **map-dependencies**: Apply only HIGH-confidence proposals (≥0.7 conflict score). Skip MEDIUM.
- **issue-size-review**: Auto-decompose only Very Large (≥8 score). Skip Large (5-7) as ambiguous.

## Success Criteria
- [x] Plan created
- [ ] verify-issues.md has `--auto` flag with Pattern A parsing
- [ ] map-dependencies/SKILL.md has `--auto` flag with Pattern B parsing
- [ ] issue-size-review/SKILL.md has `--auto` flag with Pattern B parsing
- [ ] All three gate interactive prompts behind AUTO_MODE
- [ ] Loop YAML files (`loops/issue-refinement.yaml`) already pass `--auto` — confirm compatibility
