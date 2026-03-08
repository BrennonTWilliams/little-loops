---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 98
outcome_confidence: 78
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

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/handoff.md` | Current handoff output schema (3-section prose template, lines 124–174) |
| `commands/resume.md` | Resume parsing behavior and `ll-session-state.json` schema (lines 47–56, 106–120) |

## Labels

`enhancement`, `handoff`, `context-engineering`, `session-management`

## Verification Notes

- **2026-03-05** — VALID. `commands/handoff.md` and `commands/resume.md` both exist; current 3-section prose schema (Conversation Summary / Resume Point / Important Context) confirmed at `handoff.md:124–174`; 4-section schema not yet implemented. `ll-session-state.json` structured fields confirmed in `resume.md:47–56`, `106–120`.

## Session Log
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — readiness: 98/100 PROCEED, outcome: 78/100 MODERATE (up from 68 — improved change surface assessment: 2 isolated command files, docs refs not callers)
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:verify-issues` - 2026-02-25 - Corrected file paths: `skills/handoff/SKILL.md` → `commands/handoff.md`; `skills/resume/SKILL.md` → `commands/resume.md` (handoff/resume are commands, not skills)
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Documented current handoff schema (3-section prose) and resume behavior; noted existing ll-session-state.json structured fields
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; research findings from 2026-02-25 remain current
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `commands/handoff.md` (lines 124–174) and `commands/resume.md` (lines 47–56, 106–120)
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: 3-section prose structure still in use
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: 4-section anchored schema not yet implemented; 3-section prose structure still in use

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3

---

## Tradeoff Review Note

**Reviewed**: 2026-03-03 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — Good intent, but the handoff schema becomes part of a session-continuity contract once changed. Before restructuring, validate the proposed four-section schema against 3-5 real session handoff files. Also: document the current 3-section schema (Conversation Summary / Resume Point / Important Context) in `CONTRIBUTING.md` as a baseline, so the diff from current → proposed is explicit. The MEDIUM maintenance overhead comes from `/ll:resume` needing updates to parse and surface structured fields — ensure that change is scoped into this issue before implementation.
