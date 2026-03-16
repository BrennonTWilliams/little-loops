---
id: ENH-779
priority: P3
status: backlog
discovered_date: 2026-03-16
discovered_by: capture-issue
---

# ENH-779: confidence-check offer to update issue with findings

## Summary

At the end of `/ll:confidence-check`, after presenting its findings section (Concerns, Items of Note, etc.), the skill should ask the user if it should update the issue file to address or at least document those findings. In `--auto` mode, if there are findings/concerns, it should update the issue automatically.

## Motivation

Currently, confidence-check surfaces useful findings — concerns about implementation approach, items worth noting, missing context — but they exist only in the conversation. The issue file itself remains unaware of these insights. This creates a gap: the next person (or agent) implementing the issue won't see the concerns raised during the confidence check. Capturing findings back into the issue closes the feedback loop and makes confidence-check output durable.

## Acceptance Criteria

- [ ] After presenting findings, confidence-check asks: "Should I update the issue to address or include these findings?" (interactive mode)
- [ ] If user confirms, the issue file is updated to incorporate findings (e.g., appended under a "## Confidence Check Notes" section, or by patching relevant sections like Acceptance Criteria, Implementation Notes, or Risks)
- [ ] In `--auto` mode: if there are any findings/concerns, the issue is updated automatically without prompting
- [ ] In `--auto` mode with no findings: no update is made (clean bill of health)
- [ ] The update is staged with `git add`

## Implementation Steps

1. Locate the findings/concerns section in the confidence-check output flow (the final summary block)
2. After rendering findings, add an interactive prompt (using `AskUserQuestion`) asking whether to update the issue
3. If confirmed (or `--auto` with findings), append a `## Confidence Check Notes` section to the issue file with:
   - Date of check
   - Readiness score and outcome confidence score
   - Concerns (bulleted)
   - Gaps to Address (bulleted, if any)
   - Outcome Risk Factors (bulleted, if any)
4. Run `git add` on the updated issue file
5. For `--auto` mode: check if findings list is non-empty before updating; skip if clean

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 location**: Findings are rendered at `skills/confidence-check/SKILL.md:461-474`. The three findings subsections are: Concerns (line 463, present when PROCEED WITH CAUTION), Gaps to Address (line 466-469, rendered when readiness < 70), Outcome Risk Factors (line 470-473, rendered when outcome confidence < 60). The issue's "Items of Note" terminology doesn't appear in the skill — the actual sections are these three. Track `HAS_FINDINGS=false` before the output block; set to `true` if any of the three subsections has content.
- **Step 2 interactive pattern**: Follow `skills/format-issue/SKILL.md:319-337` for the `AskUserQuestion` yes/no prompt. Immediately before the prompt, add auto-mode bypass: "When `AUTO_MODE` is true and `HAS_FINDINGS` is true: skip the AskUserQuestion prompt and proceed automatically" (pattern from `skills/map-dependencies/SKILL.md:144`).
- **Step 3 append pattern**: Use `Edit` tool (already in allowed-tools) to append `## Confidence Check Notes` before the `## Session Log` entry written in Phase 4 (`SKILL.md:396-403`). Place the new Phase 5 block between the Phase 4 frontmatter write and the session log append so the log covers the full write.
- **Step 4 git add**: Current allowed-tools (`SKILL.md:11-16`) only permits `Bash(find:*)`. Must expand frontmatter to add `Bash(git:*)` or `Bash` to enable `git add "[issue-file-path]"`. Specific-file staging pattern: `git add "[issue-file-path]"` (see `skills/capture-issue/SKILL.md:257` and `skills/format-issue/SKILL.md:335`).
- **New phase placement**: Insert as **Phase 4.5** between existing Phase 4 (frontmatter update, `SKILL.md:360-403`) and the session log append. This keeps the session log as the final write, consistent with all other skills.
- **Check mode skip**: `CHECK_MODE` skips all writes (`SKILL.md:418-428`). The new Phase 4.5 must also be skipped when `CHECK_MODE` is true (same guard as Phase 4 frontmatter skip).
- **Batch mode behavior**: When `ALL_MODE` is true, `AUTO_MODE` is also true (`SKILL.md:66-68`). Issue update logic runs per-issue inside the batch loop, with the same `HAS_FINDINGS` gate.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — add Phase 4.5 (findings write-back); expand `allowed-tools` to add `Bash(git:*)` or `Bash` for `git add`

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md` — calls `/ll:confidence-check` in Phase 2.5; reads `confidence_score` from frontmatter as gate; behavior unchanged by this enhancement
- `loops/issue-refinement.yaml` — invokes confidence-check with `--auto`; the `HAS_FINDINGS` auto-update will run automatically
- `loops/sprint-build-and-validate.yaml` — invokes confidence-check with `--auto`; same as above

### Similar Patterns (Reference Implementations)
- `skills/format-issue/SKILL.md:319-337` — `AskUserQuestion` yes/no prompt after presenting findings; models the interactive offer UX
- `skills/capture-issue/SKILL.md:272-294` — `cat >>` heredoc for appending named sections to issue files with immediate `git add`
- `skills/map-dependencies/SKILL.md:144-166` — auto-mode bypass text pattern + `git add {{config.issues.base_dir}}/`
- `skills/review-loop/SKILL.md:299-313` — `AskUserQuestion` single yes/no confirmation after proposals

### Tests
- `scripts/tests/test_refine_status.py` — references `confidence_check` in refine status context
- `scripts/tests/test_issue_workflow_integration.py` — integration tests for issue workflow pipeline

## Related Issues

- ENH-753: rename confidence-check skill (touches same skill file)

## Session Log
- `/ll:refine-issue` - 2026-03-16T17:32:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8de8f7f-036d-410c-b49a-697d879afa38.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7b97881-4db4-44f5-a2fe-58abb7c61bc4.jsonl`
