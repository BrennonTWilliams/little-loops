---
discovered_date: 2026-04-04
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
---

# FEAT-949: Add `improve-claude-md` skill using `<important if>` block restructuring

## Summary

Add a new `ll:improve-claude-md` skill that rewrites a project's `CLAUDE.md` file using `<important if="condition">` XML blocks, improving LLM instruction adherence by scoping each section to the tasks where it's actually relevant.

## Current Behavior

`ll:audit-claude-config` audits CLAUDE.md quality but does not rewrite the file. Users must manually restructure their CLAUDE.md to use `<important if>` blocks. There is no automated rewrite path in ll.

## Expected Behavior

An `ll:improve-claude-md` skill applies a 9-step rewrite algorithm to the project's CLAUDE.md, wrapping instructions in `<important if="condition">` blocks scoped to when they are relevant, and outputs a diff summary of changes.

## Context

Identified from conversation comparing humanlayer/skills `improve-claude-md` to ll's `audit-claude-config`. The comparison revealed that ll has no equivalent capability: `audit-claude-config` audits CLAUDE.md quality but does not rewrite the file. The core mechanism — `<important if>` XML blocks — exploits the same XML pattern used by Claude Code's own system prompt, cutting through the "may or may not be relevant" system reminder to give Claude precise, conditional instruction attention.

## Motivation

Claude Code injects a system reminder that CLAUDE.md content "may or may not be relevant to your tasks," causing Claude to selectively ignore sections. Wrapping instructions in `<important if="condition">` blocks signals relevance explicitly. Without this skill, users must manually restructure their CLAUDE.md, and ll's audit step has no automated rewrite path.

## Proposed Solution

Create a `skills/improve-claude-md/SKILL.md` that implements the humanlayer 9-step rewrite algorithm:

1. Extract project identity — leave bare (always relevant)
2. Extract directory map — leave bare
3. Extract tech stack — leave bare, condensed
4. Extract commands — wrap together in one `<important if="you need to run commands...">` block; never drop any command
5. Break apart rules — each rule gets its own narrow-condition `<important if>` block
6. Wrap domain sections — testing patterns, API conventions, etc. each get their own block
7. Delete linter-territory — strip style rules already enforced by linter/formatter
8. Delete code snippets — replace with file path references
9. Delete vague instructions — remove non-actionable guidance

**Key design constraints (from humanlayer reference impl)**:
- Foundational context (identity, project map, tech stack) stays bare — relevant to 90%+ of tasks
- Conditions must be narrow and specific (not "you are writing code" but "you are adding imports")
- No file sharding — everything inline, LLM attends by condition match
- Never drop commands — commands table is a hard constraint

**Scope options** (to decide during refinement):
- Option A: Standalone `ll:improve-claude-md` skill (mirrors humanlayer structure)
- Option B: Add `--rewrite` flag to `ll:audit-claude-config` (integrated into existing audit flow)

Option A is preferred for composability and discoverability.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**SKILL.md frontmatter spec** (following `format-issue/SKILL.md:1–19`):
```yaml
---
description: |
  Use when the user asks to improve or rewrite CLAUDE.md, restructure instructions using
  <important if> blocks, or increase LLM instruction adherence. Apply the 9-step rewrite algorithm.

  Trigger keywords: "improve claude md", "rewrite claude md", "important if blocks",
  "instruction adherence", "restructure claude md", "scope instructions"
argument-hint: "[--dry-run] [--file path]"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Bash(git:*)
arguments:
  - name: flags
    description: "Optional flags: --dry-run (preview without writing), --file <path> (target file)"
    required: false
---
```
No `Task` in `allowed-tools` — this is a sequential single-file skill (not parallel like `audit-claude-config`).

**`--file` flag extraction** (no direct precedent; derive from `format-issue/SKILL.md:50–82` pattern):
```bash
FLAGS="${flags:-}"
DRY_RUN=false
FILE_ARG=""

if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
FILE_ARG=$(echo "$FLAGS" | grep -oP '(?<=--file )\S+' || true)

# Default CLAUDE.md resolution
if [[ -z "$FILE_ARG" ]]; then
    if [[ -f ".claude/CLAUDE.md" ]]; then
        FILE_ARG=".claude/CLAUDE.md"
    elif [[ -f "CLAUDE.md" ]]; then
        FILE_ARG="CLAUDE.md"
    else
        echo "Error: no CLAUDE.md found (.claude/CLAUDE.md or ./CLAUDE.md)"
        exit 1
    fi
fi
```

**Diff output format** — use `-/+` line prefix convention from `audit-claude-config/SKILL.md:596–609` (not `->` arrow notation from `configure`). The diff should show before/after for each wrapped block added, and explicitly list every section deleted (steps 7–9 deletions).

**Companion file recommendation** — both `audit-claude-config` and `format-issue` use a sidecar file (`report-template.md` and `templates.md` respectively) for reference tables. The 9-step algorithm detail and condition examples should go in `skills/improve-claude-md/algorithm.md` to keep the main SKILL.md focused on the process flow.

## Implementation Steps

1. Create `skills/improve-claude-md/SKILL.md` with the 9-step rewrite algorithm and frontmatter per spec above
2. Create `skills/improve-claude-md/algorithm.md` sidecar with condition examples and step detail (following `audit-claude-config/report-template.md` and `format-issue/templates.md` pattern)
3. Implement flag parsing: `--dry-run` + `--file` extraction (see `format-issue/SKILL.md:50–82` for the canonical pattern)
4. Resolve target file: check `.claude/CLAUDE.md` then `./CLAUDE.md` (only `.claude/CLAUDE.md` exists in this repo)
5. Apply 9-step algorithm; guard Edit tool call with `if [[ "$DRY_RUN" == false ]]`; use `-/+` diff output format
6. Register in `.claude/CLAUDE.md:57` — Meta-Analysis group (append `improve-claude-md`^); update skill count at line 38: `(21 skills)` → `(22 skills)`
7. Register in `commands/help.md:167` — add entry after `analyze-workflows` block; also update Quick Reference Table at line 242
8. Run `/ll:audit-claude-config` to validate the skill file is discovered correctly

## Integration Map

### Files to Modify
- `CLAUDE.md` — add `improve-claude-md` to skill index
- `commands/*.md` — add to `/ll:help` listing

### New Files
- `skills/improve-claude-md/SKILL.md` — new skill implementing the 9-step algorithm

### Dependent Files (Callers/Importers)
- N/A — new skill, no existing callers

### Similar Patterns
- `skills/audit-claude-config/SKILL.md` — reference for CLAUDE.md-targeting skill structure
- `skills/format-issue/SKILL.md` — reference for multi-step, flagged skill pattern

### Tests
- N/A — skill file only, no Python code

### Documentation
- `CLAUDE.md` — skill index listing update

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact registration locations:**

- `.claude/CLAUDE.md:38` — `skills/` Key Directories count: `# Skill definitions (21 skills)` → update to `(22 skills)`
- `.claude/CLAUDE.md:57` — Meta-Analysis line: append `improve-claude-md`^ to `audit-claude-config`^, `analyze-workflows`, `analyze-history`^
- `commands/help.md:155–167` — META-ANALYSIS section: add new entry after `analyze-workflows` block (line 167)
- `commands/help.md:242` — Quick Reference Table Meta-Analysis entry: append `improve-claude-md`
- `.claude-plugin/plugin.json` — skill manifest uses `"skills": ["./skills"]` glob (auto-discovers new directory — **no manual manifest edit required**)

**help.md entry format** (following `audit-claude-config` at lines 157–160):
```
/ll:improve-claude-md [flags]
    Rewrite CLAUDE.md using <important if="condition"> blocks for scoped instruction attention
    Flags: --dry-run (preview without writing), --file <path> (default: .claude/CLAUDE.md)
```

**Note**: Root-level `CLAUDE.md` does not exist in this repo — only `.claude/CLAUDE.md`.

## Use Case

A developer has a large flat CLAUDE.md with many sections. They run `/ll:improve-claude-md` and the skill rewrites it so that, for example:
- Scratch-pad automation instructions only activate during `ll-auto`/`ll-parallel` runs
- Git/commit guidelines only activate during commit/PR operations
- Code style rules that the linter already enforces are removed

## Acceptance Criteria

- [ ] `skills/improve-claude-md/SKILL.md` exists and implements the 9-step rewrite algorithm
- [ ] `/ll:improve-claude-md` rewrites the target CLAUDE.md in place and displays a diff summary
- [ ] `--dry-run` flag previews changes without writing
- [ ] `--file path/to/CLAUDE.md` targets a specific file (default: `.claude/CLAUDE.md` or `./CLAUDE.md`)
- [ ] Foundational context (project identity, directory map, tech stack) is left bare — not wrapped in `<important if>` blocks
- [ ] Commands table is preserved without omissions (hard constraint)
- [ ] Each rule/convention gets its own `<important if>` block with a narrow, specific condition
- [ ] Skill appears in `/ll:help` output and `CLAUDE.md` skill index

## API/Interface

```bash
# Rewrite CLAUDE.md in place
/ll:improve-claude-md

# Preview changes without writing
/ll:improve-claude-md --dry-run

# Target a specific file (default: .claude/CLAUDE.md or ./CLAUDE.md)
/ll:improve-claude-md --file path/to/CLAUDE.md
```

## Impact

- **Priority**: P3 - Nice-to-have improvement; no existing functionality is blocked
- **Effort**: Medium - New skill file implementing a well-defined 9-step algorithm from a reference implementation
- **Risk**: Low - Creates a new file only; no changes to existing code paths
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | The primary target file this skill rewrites |
| architecture | docs/ARCHITECTURE.md | Skill system design and plugin structure |

## Labels

`feature`, `captured`, `claude-config`, `skill`

---

## Status

**Open** | Created: 2026-04-04 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-04-04T21:33:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbe4ecea-498a-46bf-8529-ec826525bb1b.jsonl`
- `/ll:refine-issue` - 2026-04-04T21:30:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da715ef7-17a9-4847-a68b-48525c65ce91.jsonl`
- `/ll:format-issue` - 2026-04-04T21:26:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a72dd5d-fabc-436e-9d5c-c917cbb88dbd.jsonl`
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5baed11d-a52e-4c14-99da-b2c843eb04ba.jsonl`
