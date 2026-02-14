# ENH-277: Add Pre-Implementation Confidence Check - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-277-add-pre-implementation-confidence-check.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### Key Discoveries
- 6 existing skills in `skills/` follow consistent pattern: directory with single `SKILL.md`
- Skills use YAML frontmatter with `description` field and trigger keywords
- `commands/manage_issue.md` Phase 1.5 gathers research, Phase 2 creates plan — confidence check fits between them
- `/ll:ready-issue` validates issue file format/content but not implementation readiness
- No existing confidence or readiness check exists

### Patterns to Follow
- `skills/issue-size-review/SKILL.md` — closest pattern (scoring heuristics, phased workflow)
- `skills/map-dependencies/SKILL.md` — multi-phase analysis with structured output
- Frontmatter: `description: |` with trigger keywords
- Integration via reference in `commands/manage_issue.md`

## Desired End State

A `skills/confidence-check/SKILL.md` that performs a 5-point pre-implementation assessment with concrete detection methods. Integrated as a recommended step in manage_issue Phase 2 (between research and plan creation).

### How to Verify
- Skill file exists at `skills/confidence-check/SKILL.md` with valid frontmatter
- manage_issue.md references the skill in Phase 2
- Detection methods are concrete and actionable (addressing tradeoff review concerns)

## What We're NOT Doing

- Not making the check mandatory/blocking in manage_issue
- Not changing `/ll:ready-issue` behavior
- Not adding Python code or tests (skill is pure markdown)
- Not adding configuration options

## Solution Approach

Create the skill with concrete detection methods for each of the 5 criteria (addressing the tradeoff review's concern about specificity). Use the research findings from Phase 1.5 as input — the confidence check evaluates whether research adequately covers each criterion rather than re-doing research.

### Scoring Design Decision
Each criterion scored 0-20 points (total 100). Thresholds: >=90 proceed, 70-89 present concerns, <70 stop.

## Implementation Phases

### Phase 1: Create confidence-check skill

**File**: `skills/confidence-check/SKILL.md`

Create skill with:
- Frontmatter matching project pattern
- 5-point assessment with concrete detection methods per criterion
- Scoring rubric with clear point allocation
- Structured output format
- Integration notes for manage_issue

### Phase 2: Integrate into manage_issue

**File**: `commands/manage_issue.md`

Add a recommended confidence-check step between Phase 1.5 (research) and Phase 2 (plan creation). Non-blocking — advisory only.

### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Skill file has valid frontmatter and follows project patterns
- [ ] Detection methods are concrete (not vague)
- [ ] manage_issue references skill appropriately
