---
discovered_date: 2026-03-03
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
---

# ENH-524: Add Session Log Steps to Issue-Modifying Commands and Skills

## Summary

Five commands and skills make meaningful changes to issue files (content edits, frontmatter updates, file moves to `completed/`) but do not append a Session Log entry. This leaves gaps in the audit trail for issues processed by `ready-issue`, `verify-issues`, `confidence-check`, `tradeoff-review-issues`, and `issue-size-review`.

## Current Behavior

The following commands/skills write to issue files with no Session Log step:

| Command/Skill | Action on Issue Files |
|---|---|
| `ready-issue` | Auto-corrects content; closes to `completed/` |
| `verify-issues` | Updates verification notes; closes to `completed/` |
| `confidence-check` (skill) | Writes `confidence_score` + `outcome_confidence` to YAML frontmatter |
| `tradeoff-review-issues` | Appends review notes; closes to `completed/` |
| `issue-size-review` (skill) | Creates child issues; closes parent to `completed/` |

These contrast with `format-issue`, `manage-issue`, `capture-issue`, `scan-codebase`, and `refine-issue`, which all append Session Log entries after modifying issues.

## Expected Behavior

Each of the five commands/skills above should append a Session Log entry immediately after modifying the issue file, following the same pattern used by the commands that already implement it:

```markdown
## Session Log
- `/ll:<command>` - [ISO timestamp] - `[path to current session JSONL]`
```

The entry should be added before the `---` / `## Status` footer. If `## Session Log` already exists, the new entry is appended below the header.

## Acceptance Criteria

- [ ] `ready-issue` appends a Session Log entry after auto-correcting issue content
- [ ] `ready-issue` appends a Session Log entry after closing an issue to `completed/`
- [ ] `verify-issues` appends a Session Log entry after updating verification notes
- [ ] `confidence-check` appends a Session Log entry after writing `confidence_score` and `outcome_confidence` to frontmatter
- [ ] `tradeoff-review-issues` appends a Session Log entry after appending review notes
- [ ] `tradeoff-review-issues` appends a Session Log entry after closing an issue to `completed/`
- [ ] `issue-size-review` appends a Session Log entry for each child issue created
- [ ] `issue-size-review` appends a Session Log entry when closing the parent issue to `completed/`
- [ ] All entries follow the standard format: `- /ll:<command> - [ISO timestamp] - [session JSONL path]`

## Motivation

Without Session Log entries, there is no record of which session last touched an issue or what command caused a change. This makes it difficult to trace why an issue was closed, when a confidence score was set, or which session flagged a size decomposition. Consistent Session Log coverage across all issue-writing commands enables complete auditability.

## Success Metrics

- Session Log coverage: 5 of 10 issue-modifying commands → 10 of 10 (100%)
- Zero issue modifications by the 5 affected commands leave the Session Log empty

## Affected Files

- `commands/ready-issue.md` — add Session Log step after autocorrect/close actions
- `commands/verify-issues.md` — add Session Log step after updating verification notes
- `skills/confidence-check/SKILL.md` — add Session Log step after frontmatter write
- `commands/tradeoff-review-issues.md` — add Session Log step after appending review/closing
- `skills/issue-size-review/SKILL.md` — add Session Log step for each created child issue and the closed parent

## Scope Boundaries

- **In scope**: Adding Session Log steps to the 5 commands/skills listed in Affected Files
- **Out of scope**: Changing the Session Log format; modifying `scripts/little_loops/session_log.py`; adding Session Log to commands that don't write issue files

## API/Interface

N/A - No public API changes. The Session Log step writes markdown to existing issue files using the same format already implemented in `commands/refine-issue.md` and `skills/format-issue/SKILL.md`.

## Implementation Steps

1. For each affected file, locate the step that writes/edits the issue file
2. Add a new step immediately after: "Append Session Log Entry"
3. Use the standard Session Log format (same as in `commands/refine-issue.md:384` or `skills/format-issue/SKILL.md:264`)
4. Ensure the step covers all branch paths (e.g., `ready-issue` has both autocorrect and close paths — both need a log entry)
5. For `issue-size-review`, log entries on both the new child issue files and the parent being closed

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Exact insertion points confirmed by codebase analysis:

| File | Insertion: After | Before | Purpose |
|---|---|---|---|
| `commands/ready-issue.md` | Step 5 body ("Save the corrected issue file") ~line 223 | `**IMPORTANT**` caveat ~line 225 | Log after auto-correction |
| `commands/verify-issues.md` | Step 4 body end ~line 118 | `### 5. Output Report` ~line 120 | Log after verification notes update |
| `skills/confidence-check/SKILL.md` | Phase 4 "Update Frontmatter" close ~line 391 | `### Auto Mode Behavior` ~line 393 | Log after frontmatter write |
| `commands/tradeoff-review-issues.md` | `git mv` block in "For Approved Closures" ~line 249 | `#### For Approved Updates` ~line 251 | Log after closing to completed/ |
| `commands/tradeoff-review-issues.md` | Tradeoff Review Note template close ~line 274 | `#### Stage All Changes` ~line 276 | Log after appending review notes |
| `skills/issue-size-review/SKILL.md` | Step 2 "Create child issue files" ~line 126 | Step 3 "Update and move parent" ~line 128 | Log for each child issue created |
| `skills/issue-size-review/SKILL.md` | `git mv` parent block in Step 3 ~line 149 | Step 4 "Stage all changes" ~line 151 | Log for parent issue closure |

**Session Log step template** (copy verbatim from `commands/refine-issue.md:384`, adapting command name):

```markdown
### N. Append Session Log

After updating the issue, append a session log entry:

```markdown
## Session Log
- `/ll:<command-name>` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). If `## Session Log` already exists, append below the header. If not, add before `---` / `## Status` footer.
```

Additional reference implementations to consult for placement conventions:
- `commands/scan-codebase.md:314` — `### 5.5. Append Session Log Entries` (multi-file loop context)
- `skills/capture-issue/SKILL.md:246` — inline numbered sub-item (simplest pattern)
- `skills/manage-issue/SKILL.md:385` + `templates.md:331` — delegates format to templates.md

## Related Key Documentation

| Document | Relevance |
|---|---|
| `commands/refine-issue.md:384` | Reference implementation of Session Log step |
| `skills/format-issue/SKILL.md:264` | Reference implementation in skill context |
| `skills/manage-issue/templates.md:331` | Canonical Session Log entry format template |
| `scripts/little_loops/session_log.py` | Python module for session log operations |

## Integration Map

### Files to Modify

- `commands/ready-issue.md` — add Session Log step after Step 5 auto-correction body (~line 223) and after close verdict execution
- `commands/verify-issues.md` — add Session Log step after Step 4 "Update Issue Files" body (~line 118); renumber Output Report to Step 6
- `skills/confidence-check/SKILL.md` — add Session Log step after Phase 4 "Update Frontmatter" close (~line 391)
- `commands/tradeoff-review-issues.md` — add Session Log step in two locations within Phase 5: after closure `git mv` (~line 249) and after review notes template (~line 274)
- `skills/issue-size-review/SKILL.md` — add Session Log step in two locations within Phase 5: after child issue creation (~line 126) and after parent `git mv` (~line 149)

### Similar Patterns (Reference Implementations)

- `commands/refine-issue.md:384` — standalone `### 7. Append Session Log` step; **canonical template for commands**
- `skills/format-issue/SKILL.md:264` — merged step heading `### 5. Update Issue File and Append Session Log`; canonical for skills
- `commands/scan-codebase.md:314` — `### 5.5. Append Session Log Entries`; model for multi-file loop contexts
- `skills/capture-issue/SKILL.md:246` — inline numbered sub-item; simplest pattern
- `skills/manage-issue/SKILL.md:385` + `templates.md:331` — step references external template file

### Supporting Modules

- `scripts/little_loops/session_log.py` (85 lines) — exports `get_current_session_jsonl(cwd)` and `append_session_log_entry(issue_path, command, session_jsonl=None)`; **not called by command/skill markdown** — the markdown files include inline LLM instructions that reproduce the same logic
- `scripts/tests/test_session_log.py` — covers the Python module; no changes needed for this ENH

### Tests

No automated tests for command/skill markdown behavior (LLM-instruction-based). The Python module is tested separately; it is unchanged by this ENH.

## Impact

- **Priority**: P3 - Low; fills an audit trail gap but does not affect functionality or correctness
- **Effort**: Small - markdown-only additions to 5 command/skill files; no Python code changes
- **Risk**: Low - changes are LLM instruction text only; no behavioral regressions possible for existing commands
- **Breaking Change**: No

## Labels

`enhancement`, `audit-trail`, `session-log`, `commands`, `skills`

## Session Log
- `/ll:capture-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3f89019-8d96-425f-80aa-cd975bd7521c.jsonl`
- `/ll:format-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d89e72fb-8a73-4022-8536-d2864de87a77.jsonl`
- `/ll:refine-issue` - 2026-03-03T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b5cd253-19da-4e4f-813e-cf37aab9832b.jsonl`
- `/ll:ready-issue` - 2026-03-03T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa7608ed-9d5f-447a-9ef6-600644b1d11f.jsonl`
- `/ll:manage-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ca133f6-3509-4ee0-a78a-2b75838b643d.jsonl`

---

## Resolution

- **Status**: Completed
- **Completed**: 2026-03-03
- **Fix Commit**: (pending commit)
- **Files Changed**:
  - `commands/ready-issue.md` — added Session Log sub-step (item 7) in Step 5 Auto-Correction
  - `commands/verify-issues.md` — added `### 4.5 Append Session Log Entries` between Step 4 and Step 5
  - `skills/confidence-check/SKILL.md` — added Session Log step after frontmatter write block, before `### Auto Mode Behavior`
  - `commands/tradeoff-review-issues.md` — added Session Log step after closure `git mv` and after review notes template
  - `skills/issue-size-review/SKILL.md` — added Session Log step after child issue creation and after parent `git mv`

---

## Status

**Completed** | Created: 2026-03-03 | Priority: P3
