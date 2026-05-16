---
id: ENH-858
type: ENH
priority: P3
status: active
discovered_date: 2026-03-22
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 78
---

# ENH-858: go-no-go Should Update Issue With Significant Findings

## Summary

When `/ll:go-no-go` produces a verdict with significant findings not already represented in the issue (e.g., hidden complexity, existing coverage gaps, new risk factors, or strong pro arguments clarifying motivation), it should offer to — or in `--auto` mode, automatically — update the issue file with those findings.

## Current Behavior

`/ll:go-no-go` appends only a session log entry (pointer to the JSONL) to the issue file after evaluation. The verdict, rationale, key arguments, and deciding factor are displayed in the conversation but never written back to the issue.

## Expected Behavior

After rendering a verdict, go-no-go examines the judge's findings against the issue's current content. If significant new information is present (e.g., hidden complexity not in the issue, existing coverage discovered by the con agent, clarified motivation from the pro agent), it updates the issue file with the relevant content — either interactively (prompting the user) or automatically in `--auto` mode.

## Motivation

The adversarial debate agents perform real codebase research and often surface accurate, concrete findings — specific files, functions, and risks — that aren't captured in the original issue. Without write-back, this research is ephemeral. Persisting significant findings improves issue quality, reduces re-research during implementation, and keeps the issue file as the authoritative record of what is known about a problem.

## Success Metrics

- After a go-no-go run, if the judge identifies significant findings not in the issue, those findings appear in the issue file (e.g., under a `## Go/No-Go Findings` section)
- In `--auto` mode, findings are written without prompting
- In interactive mode, the user is asked whether to apply findings before writing
- Findings that merely restate existing issue content are not duplicated
- Session log entry is still appended as before

## Scope Boundaries

- **In scope**: Writing verdict rationale + key arguments + deciding factor to the issue file when substantive; interactive vs auto mode gating
- **Out of scope**: Changing the verdict itself; altering the issue's priority, status, or frontmatter based on the verdict; modifying issue title or summary

## Proposed Solution

After Step 3e (format and display verdict), add a new step:

1. Compare judge's KEY ARGUMENTS AGAINST (hidden complexity, risk factors) and KEY ARGUMENTS FOR (implementation feasibility, pattern fit) against the issue's existing content
2. If novel findings exist: collect them into a `## Go/No-Go Findings` section with the verdict, rationale, and deciding factor
3. In `--auto` mode: write directly using the Edit tool
4. In interactive mode: show the proposed section and ask the user to confirm before writing
5. Append below any existing `## Additional Context` or before `## Session Log`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`## Go/No-Go Findings` section template** (modeled after `confidence-check/SKILL.md:419-438`):

  ```markdown
  ## Go/No-Go Findings

  _Added by `/ll:go-no-go` on [YYYY-MM-DD]_ — **[GO | NO-GO]**

  **Deciding Factor**: [single sentence from judge output]

  ### Key Arguments For
  - [bullet from judge KEY ARGUMENTS FOR]

  ### Key Arguments Against
  - [bullet from judge KEY ARGUMENTS AGAINST]

  ### Rationale
  [2-4 sentences from judge RATIONALE]
  ```

- **CHECK_MODE gating**: Add `if CHECK_MODE: skip entire phase` guard at the top of Phase 3f — same guard as `confidence-check/SKILL.md:403` (no writes in `--check` mode)
- **Section anchor**: Phase 3f runs before the session log step (`SKILL.md:356-369`), so `## Session Log` won't exist yet at that point — use "before `## Status`" as the insertion anchor

## Integration Map

### Files to Modify
- `skills/go-no-go/SKILL.md` — two changes required:
  - Add `Edit` and `AskUserQuestion` to `allowed-tools` frontmatter (lines 9-18; both are currently absent)
  - Add Phase 3f after Step 3e (lines 289-313) implementing the `HAS_FINDINGS` gate, interactive/auto mode split, and `## Go/No-Go Findings` section write-back

### Dependent Files (No Changes Needed)
- `scripts/little_loops/session_log.py` — session log logic unchanged; Phase 3f inserts before `## Session Log`, which the existing session log step (lines 356-369) appends to afterwards
- No Python test changes required (skill behavior is prose)

### Similar Patterns to Follow
- `skills/confidence-check/SKILL.md:397-453` — direct model: `HAS_FINDINGS` boolean gate, `AskUserQuestion` prompt in interactive mode (line 408), `AUTO_MODE` bypass (line 413), `Edit` insertion before `## Session Log` (line 417)
- `skills/map-dependencies/SKILL.md:144-157` — parallel auto vs. interactive write-back pattern

## Implementation Steps

1. Read `skills/go-no-go/SKILL.md` to understand the current Phase 3 flow
2. Define the novelty heuristic: findings are "significant" if they mention specific files/functions not already in the issue body
3. Add Phase 3f after Step 3e in the skill:
   - Build a `## Go/No-Go Findings` block from judge output
   - In `--auto` mode: use Edit to insert it before `## Session Log`
   - In interactive mode: use AskUserQuestion to confirm before writing
4. Update the session log entry format if needed (e.g., note that findings were written)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Key lines to read in `skills/go-no-go/SKILL.md`**:
  - Lines 9-18: `allowed-tools` frontmatter — currently `Read, Glob, Grep, Bash(find:*), Bash(ls:*), Bash(cat:*), Bash(git:*), Agent`; `Edit` and `AskUserQuestion` are absent and must be added
  - Lines 268-286: judge output schema (VERDICT, RATIONALE, KEY ARGUMENTS FOR, KEY ARGUMENTS AGAINST, DECIDING FACTOR) — all fields are available for extraction
  - Lines 289-313: Phase 3e (verdict display) — Phase 3f inserts immediately after line 313
  - Lines 356-369: session log append — runs after Phase 3f; `## Session Log` won't exist yet when Phase 3f runs
- **Step 3 model**: Follow `confidence-check/SKILL.md:397-453` — `HAS_FINDINGS` boolean gate (line 401), `CHECK_MODE` skip guard (line 403), `AskUserQuestion` in interactive mode (line 408), direct write in auto mode (line 413), `Edit` insertion with "before `## Status`" fallback (line 417)
- **Step 4 correction**: Session log format is unchanged; the only new behavior is Phase 3f running before the session log append

## Impact

- **Priority**: P3 - Useful improvement to issue quality and research persistence; not blocking any critical workflows
- **Effort**: Small - Modifies only `skills/go-no-go/SKILL.md` (prose); no Python or test changes required
- **Risk**: Low - Additive new phase; existing session log, check mode, and verdict behavior are unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `go-no-go`, `skill`

## Resolution

Implemented by `/ll:manage-issue` on 2026-03-22.

**Changes made**:
- `skills/go-no-go/SKILL.md`: Added `Edit` and `AskUserQuestion` to `allowed-tools` frontmatter
- `skills/go-no-go/SKILL.md`: Added Phase 3f (Go/No-Go Findings Write-Back) after Step 3e — implements novelty heuristic, interactive/auto mode gating, and `## Go/No-Go Findings` section write-back

## Session Log
- `/ll:ready-issue` - 2026-03-23T02:19:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/54ad326d-246f-4fab-9297-e3498f587df3.jsonl`
- `/ll:refine-issue` - 2026-03-23T01:55:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9359449-731d-43e3-ba00-6082cc3bba84.jsonl`
- `/ll:capture-issue` - 2026-03-22T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b57f667-bbed-4765-ac10-65a94b63e0d9.jsonl`
- `/ll:confidence-check` - 2026-03-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/26736631-f9f6-4a51-9124-5b5503a68625.jsonl`
- `/ll:manage-issue` - 2026-03-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a675b2b4-23de-4f29-88aa-2fb2faf7e761.jsonl`

---

## Status

Completed — 2026-03-22.
