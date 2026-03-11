---
type: BUG
id: BUG-656
title: init --interactive does not create .issues directory structure
priority: P3
status: open
discovered_date: 2026-03-08
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
---

# BUG-656: init --interactive does not create .issues directory structure

## Summary

Running `/ll:init` in a project without an existing `.issues/` folder and selecting the issue management option in the interactive wizard does not create the `.issues/` directory with its required subdirectories (`bugs/`, `features/`, `enhancements/`, `completed/`).

## Current Behavior

When running `/ll:init --interactive` in a project that has no `.issues/` folder, selecting the issue management option completes without error but does not create the `.issues/` directory structure. Users must manually create the directories afterward.

## Expected Behavior

When the user selects issue management during `/ll:init --interactive`, the wizard should automatically create:
- `.issues/`
- `.issues/bugs/`
- `.issues/features/`
- `.issues/enhancements/`
- `.issues/completed/`

This was the intent of ENH-453 ("Create issue directories during init"), which was marked completed but appears to have a regression or incomplete implementation.

## Steps to Reproduce

1. Navigate to a project that does not have a `.issues/` directory
2. Run `/ll:init --interactive`
3. Select the option to enable issue management
4. Complete the wizard
5. Observe: `.issues/` directory and subdirectories are not created

## Motivation

This is the first experience new users have with little-loops issue management. Failing to create the directories silently means subsequent commands (`/ll:capture-issue`, `/ll:scan-codebase`, etc.) will fail or behave unexpectedly, creating a poor onboarding experience.

## Root Cause

- **File**: `skills/init/interactive.md`
- **Anchor**: Round 2 "Issues" question (lines 158–174)
- **Cause**: When no `.issues/` directory exists (the new-project scenario), the "Yes, use .issues/" option is **commented out** at lines 168–169. The only options shown are "Yes, custom directory" and "Disable". This means new users have no straightforward default option to enable issue management with the standard `.issues/` path.

Additionally, the `mkdir` instruction in `skills/init/SKILL.md:296–299` (Step 8, sub-step 4) is unconditional — it runs regardless of whether the user enabled or disabled issue management. However, since the init skill is a natural-language prompt executed by the LLM, the LLM may not reliably reach or execute Step 8 sub-step 4, especially if the interactive wizard flow ends ambiguously.

ENH-453 added the `mkdir` to SKILL.md Step 8 but did not uncomment the default option in `interactive.md`, leaving the interactive path broken for new projects.

## Proposed Solution

1. **Uncomment the default "Yes, use .issues/" option** in `interactive.md:168–169` so it appears when no existing issues directory is found
2. **Add a conditional guard** to the `mkdir` in `SKILL.md:296–299` so directories are only created when the user selected issue management (not "Disable")
3. Also add `.issues/deferred/` to the expected behavior list (currently missing from the issue description but present in the mkdir command)

## Integration Map

### Files to Modify
- `skills/init/interactive.md:158–174` — Uncomment the "Yes, use .issues/" option in Round 2 for the no-existing-dir case
- `skills/init/SKILL.md:296–299` — Add conditional guard around `mkdir` so it only runs when issues are enabled

### Dependent Files (Callers/Importers)
- `skills/init/SKILL.md:115–117` — Delegates to `interactive.md` for the wizard flow
- `skills/init/SKILL.md:324–352` — Step 10 completion message unconditionally reports "Created:" for issue dirs (should also be conditional)

### Similar Patterns
- `skills/init/SKILL.md:272–274` — `.claude/` directory creation in the same Step 8 (unconditional, correct model for always-needed dirs)
- `scripts/little_loops/sprint.py:228` — `mkdir(parents=True, exist_ok=True)` pattern for directory creation at runtime
- `scripts/tests/test_issue_lifecycle.py:91–103` — Test fixture creating all 5 issue subdirs

### Tests
- No automated tests exist for the init skill (it's a prompt-based skill, not Python code)
- Manual verification: run `/ll:init --interactive` in a project without `.issues/` and confirm directories are created

### Documentation
- `docs/guides/GETTING_STARTED.md` — References init; no changes needed
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — Documents issue directory structure; no changes needed

### Configuration
- `config-schema.json` — Defines `issues.base_dir` (default `.issues`), `issues.completed_dir`, `issues.deferred_dir`; no changes needed

## Implementation Steps

1. **Uncomment default option in `interactive.md`**: At lines 168–169, uncomment the `"Yes, use .issues/"` label and description so it renders when `EXISTING_ISSUES_DIR` is empty. Also uncomment the alternative question text at line 162.
2. **Add conditional to `SKILL.md` Step 8 sub-step 4**: Wrap the `mkdir -p` at lines 296–299 with a condition: only run if the user's config includes `issues.base_dir` (i.e., they didn't select "Disable").
3. **Add conditional to `SKILL.md` Step 10**: Wrap the "Created:" line at line 333 with the same condition.
4. **Verify**: Run `/ll:init --interactive` in a test project without `.issues/` — confirm the "Yes, use .issues/" option appears and directories are created after completion.

## Impact

- **Priority**: P3 - Functional bug in onboarding flow, workaround exists (manual mkdir)
- **Effort**: Small - Likely a minor fix in the init skill
- **Risk**: Low - Isolated to init wizard, no breaking changes
- **Breaking Change**: No

## Related Key Documentation

- `.issues/completed/P3-ENH-453-create-issue-directories-during-init.md` — Original feature that added `mkdir` to SKILL.md Step 8 (incomplete fix)
- `skills/init/SKILL.md` — Primary init skill definition
- `skills/init/interactive.md` — Interactive wizard flow with the commented-out option

## Labels

`bug`, `init`, `onboarding`, `captured`

## Verification Notes

- **Verdict**: NEEDS_UPDATE
- **Verified**: 2026-03-09
- **Findings**:
  - **Root cause at `interactive.md:168–169` is OUTDATED**: Those lines now contain "Scan Dirs" / "Custom selection", not a commented-out "Yes, use .issues/" option. The issue directory handling was refactored to silent auto-detection at `interactive.md:132–144` — when no `.issues/` dir exists, the wizard silently defaults to `.issues` with no user prompt.
  - **`SKILL.md:296–299` mkdir confirmed unconditional**: Verified accurate.
  - **`SKILL.md:333` completion message confirmed unconditional**: Verified accurate.
  - **Core bug changed in nature**: Since `interactive.md` no longer has a user-facing "enable issue management" question, there is no "Disable" path. The mkdir runs unconditionally for all inits, so directories should always be created. Proposed fix #1 (uncomment option) is no longer applicable.
  - **Fix needed**: Update root cause and proposed solution to reflect current code. The remaining real risk is that LLMs may skip bash steps in SKILL.md, which can still prevent directory creation — but the cause is unreliable LLM step execution, not a commented-out UI option.

## Session Log
- `/ll:capture-issue` - 2026-03-08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c9fbbab-751f-4a81-918e-15e1679ae4ae.jsonl`
- `/ll:refine-issue` - 2026-03-08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/31ac7f57-4c4f-493a-b624-a5dd9cd01e66.jsonl`
- `/ll:ready-issue` - 2026-03-08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:confidence-check` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/130348b7-6f10-4ffb-bc17-cd9244cd1bcb.jsonl`
- `/ll:verify-issues` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Open** | Created: 2026-03-08 | Priority: P3

## Blocks
- FEAT-638
- FEAT-565
- ENH-669
- ENH-665
- ENH-668
- ENH-459
- ENH-494
- ENH-497
- ENH-654
- ENH-493
