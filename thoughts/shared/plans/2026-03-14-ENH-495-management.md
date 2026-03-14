# ENH-495: Structured Handoff with Anchored Iterative Summarization

**Date**: 2026-03-14
**Issue**: P3-ENH-495-structured-handoff-with-anchored-iterative-summarization.md
**Action**: improve

## Summary

Replace the 3-section prose schema in `/ll:handoff` with a 4-section anchored schema + YAML frontmatter. Update `/ll:resume` to surface Intent and Next Steps prominently.

## Research Findings

### Current State
- `commands/handoff.md` default output (lines 124–174): 3 sections
  - `## Conversation Summary` (subsections: Primary Intent, What Happened, User Feedback, Errors and Resolutions, Code Changes)
  - `## Resume Point` (What Was Being Worked On, Direct Quote, Next Step)
  - `## Important Context` (Decisions Made, Gotchas Discovered, User-Specified Constraints, Patterns Being Followed)
  - `--deep` mode adds `## Artifact Validation` appended after
- `commands/resume.md`: displays full continuation prompt as a blob; no structured extraction

### Target State
- `ll-continue-prompt.md` uses YAML frontmatter + 4 anchored sections:
  ```
  ---
  session_date: YYYY-MM-DD
  session_branch: <branch>
  issues_in_progress: [ISSUE-ID, ...]
  ---

  # Session Continuation: [Primary Intent]

  ## Intent
  ## File Modifications
  ## Decisions Made
  ## Next Steps
  ```
- `--deep` mode appends `## Artifact Validation` after `## Next Steps`
- Resume extracts Intent and Next Steps, shows them prominently before full content

## Implementation Plan

### Phase 1: Update `commands/handoff.md`

1. Update the Process section (step 3) to describe gathering info for each new section
2. Replace default mode template (lines 124–174) with:
   - YAML frontmatter block
   - `## Intent` (1–3 sentence summary)
   - `## File Modifications` (bullet list: path — what/why)
   - `## Decisions Made` (bullet list: Decision: X — Rationale: Y)
   - `## Next Steps` (numbered list of concrete actions)
3. Update deep mode (lines 176–203) to append `## Artifact Validation` after `## Next Steps`
4. Update argument/example docs if needed

### Phase 2: Update `commands/resume.md`

1. Update "Display Resume Context" section to detect new vs old format
2. For new format: extract `## Intent` and `## Next Steps`, show them at top before full content
3. Keep backward compatibility: if sections not found, fall back to full blob display

## Success Criteria

- [ ] `commands/handoff.md` emits 4-section anchored schema with YAML frontmatter
- [ ] `--deep` mode still appends Artifact Validation section
- [ ] `commands/resume.md` surfaces Intent and Next Steps prominently on resume
- [ ] Both commands backward-compatible with old format
- [ ] No breaking changes to automation integration
