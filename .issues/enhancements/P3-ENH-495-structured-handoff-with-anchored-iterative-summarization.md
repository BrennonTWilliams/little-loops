---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 98
outcome_confidence: 68
---

# ENH-495: Structured Handoff with Anchored Iterative Summarization

## Summary

The `/ll:handoff` skill generates a free-form continuation prompt in `.claude/ll-continue-prompt.md`. Replace this with a structured, machine-readable schema based on the Anchored Iterative Summarization pattern: four dedicated sections (Intent, File Modifications, Decisions Made, Next Steps) that resist context degradation and are easier to parse programmatically.

## Current Behavior

`/ll:handoff` generates a prose continuation prompt. The content is useful but unstructured: sections may appear in different orders, key decisions may be buried in narrative, and file changes are described inconsistently. The output is human-readable but not easily machine-parsed for future tooling.

## Expected Behavior

`ll-continue-prompt.md` follows a canonical four-section schema:

```markdown
## Intent
What this session was trying to accomplish (1-3 sentences)

## File Modifications
- `path/to/file.py` — what changed and why
- `path/to/other.md` — what changed and why

## Decisions Made
- Decision: [what was decided] — Rationale: [why]

## Next Steps
1. [First concrete next action]
2. [Second concrete next action]
```

This structure places the highest-signal information in attention-favored positions (beginning and end), is consistent across sessions, and can be parsed by future automation.

## Motivation

The handoff document is one of the most important pieces of context in a resumed session. Free-form summaries are subject to "context poisoning" — if the generating session was late in its context window, the summary may be incomplete or inconsistent. Anchoring to a fixed schema ensures all four information types are always present and findable.

Additionally, a machine-readable schema enables future `ll-resume` enhancements to extract specific fields programmatically rather than presenting the entire document.

## Proposed Solution

1. Update `skills/handoff/SKILL.md` to require the four-section output schema
2. Update the prompt to generate each section explicitly, not as an emergent outcome
3. Add a YAML frontmatter block to `ll-continue-prompt.md` with: `session_date`, `session_branch`, `issues_in_progress`
4. Update `/ll:resume` to parse and surface the structured fields on resume

## Scope Boundaries

- **In scope**: Output schema for `ll-continue-prompt.md`; prompt changes in `skills/handoff/SKILL.md`; optional YAML frontmatter; `/ll:resume` parsing improvements
- **Out of scope**: Changing when handoff is triggered, storing multiple handoffs, or versioning handoff files

## Implementation Steps

1. Read current `commands/handoff.md` and `commands/resume.md`
2. Define the four-section schema with field descriptions
3. Update handoff skill prompt to emit each section explicitly
4. Add YAML frontmatter spec to the schema
5. Update resume skill to extract and display structured fields on startup
6. Test with a sample session: verify all four sections are populated

## Integration Map

### Files to Modify
- `commands/handoff.md` — updated output schema and prompt (handoff is a command, not a skill)
- `commands/resume.md` — parse structured fields on resume (resume is a command, not a skill)
- `.claude/ll-continue-prompt.md` — output format (generated, not edited directly)

### Similar Patterns
- `thoughts/shared/plans/` — existing structured planning documents

### Codebase Research Findings

_Added by `/ll:refine-issue` — Current handoff and resume schema details:_

**Current `commands/handoff.md` output schema (lines 124-174):**
The existing template has these sections: `## Conversation Summary` (with subsections: Primary Intent, What Happened, User Feedback, Errors and Resolutions, Code Changes), `## Resume Point` (What Was Being Worked On, Direct Quote, Next Step), `## Important Context` (Decisions Made, Gotchas Discovered, User-Specified Constraints, Patterns Being Followed). The `--deep` mode appends `## Artifact Validation`.

**Current `commands/resume.md` behavior:**
- Resume displays the full markdown blob from `ll-continue-prompt.md` verbatim (no structured field extraction)
- A separate `ll-session-state.json` file already carries structured fields: `timestamp`, `active_issue`, `phase`, `plan_file`, `todos`, `context`, `handoff_prompt`
- `commands/resume.md:106-120` — the session state JSON schema

**What ENH-495 proposes vs. current state:**
- Current: 3-section prose template (Conversation Summary, Resume Point, Important Context)
- Proposed: 4-section anchored schema (Intent, File Modifications, Decisions Made, Next Steps)
- Key change: rename and restructure to place Intent first (attention-favored) and reduce free-form prose
- YAML frontmatter addition (`session_date`, `session_branch`, `issues_in_progress`) would complement the existing `ll-session-state.json`

**Resume parsing opportunity:**
- Current resume reads `ll-continue-prompt.md` as a blob; with the new structured schema, it could parse and surface `## Intent` and `## Next Steps` prominently without displaying all sections
- The existing `ll-session-state.json` parsing in `commands/resume.md:47-56` provides the structural pattern to follow

### Tests
- Manual: run `/ll:handoff`, verify four sections appear in output
- Manual: run `/ll:resume`, verify it surfaces Intent and Next Steps prominently

### Documentation
- N/A

## Impact

- **Priority**: P3 — Moderate; improves session continuity quality
- **Effort**: Low — Prompt changes only, no Python code required
- **Risk**: Low — Output format change only; no behavioral change
- **Breaking Change**: No (existing `ll-continue-prompt.md` files remain readable)

## Labels

`enhancement`, `handoff`, `context-engineering`, `session-management`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:verify-issues` - 2026-02-25 - Corrected file paths: `skills/handoff/SKILL.md` → `commands/handoff.md`; `skills/resume/SKILL.md` → `commands/resume.md` (handoff/resume are commands, not skills)
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Documented current handoff schema (3-section prose) and resume behavior; noted existing ll-session-state.json structured fields

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
