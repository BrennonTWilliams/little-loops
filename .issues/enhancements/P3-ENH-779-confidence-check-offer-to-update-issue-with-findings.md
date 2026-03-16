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
   - Items of Note (bulleted)
4. Run `git add` on the updated issue file
5. For `--auto` mode: check if findings list is non-empty before updating; skip if clean

## Related Issues

- ENH-753: rename confidence-check skill (touches same skill file)

## Session Log
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7b97881-4db4-44f5-a2fe-58abb7c61bc4.jsonl`
