---
discovered_date: 2026-02-22
discovered_by: capture-issue
---

# ENH-448: Convert /ll:ready-issue from a command to a skill

## Summary

`/ll:ready-issue` is currently implemented as `commands/ready-issue.md` but would benefit from being migrated to `skills/ready-issue/SKILL.md`. This is a housekeeping/consistency improvement — no functional gap exists since the command is already accessible to AI agents via the Skill tool. The migration would add explicit model selection, trigger keywords for auto-activation, and structural consistency with other major workflow components.

## Current Behavior

`/ll:ready-issue` lives in `commands/ready-issue.md`. It is already surfaced in the Claude Code runtime's skill invocation system (appears in the system-reminder skills list) and can be invoked via the `Skill` tool by AI agents. It has its own `allowed-tools` frontmatter but lacks:
- `model:` field for explicit model selection
- Trigger keywords for auto-activation
- The `skills/*/SKILL.md` directory structure used by other major workflow components

## Expected Behavior

`/ll:ready-issue` should live at `skills/ready-issue/SKILL.md` with:
- `model: sonnet` (or appropriate model selection)
- Trigger keywords (e.g., "validate issue", "is this issue ready", "check issue accuracy")
- All existing logic and `allowed-tools` preserved

## Motivation

- **Structural consistency**: `ready-issue` is a substantial, complex workflow (369 lines) more akin to skills like `manage-issue` and `confidence-check` than simple commands
- **Model selection**: Explicit `model:` field allows intentional choice of model for validation quality
- **Trigger keywords**: Enables auto-activation when users phrase requests naturally (e.g., "is this issue ready to implement?")
- **CLAUDE.md alignment**: Project preference is "Prefer Skills over Agents" and composable components should be skills

## Proposed Solution

1. Create `skills/ready-issue/SKILL.md` with the full content of `commands/ready-issue.md`
2. Add `model: sonnet` to the SKILL.md frontmatter
3. Expand the `description:` frontmatter to include trigger keywords
4. Delete `commands/ready-issue.md`
5. Update any documentation that explicitly references the `commands/` path

## Integration Map

### Files to Modify
- `commands/ready-issue.md` — delete (content moves to skill)
- `skills/ready-issue/SKILL.md` — create (migration target)

### Dependent Files (Callers/Importers)
- `CLAUDE.md` — lists `ready-issue` without `^` marker; needs `^` added to mark it as a skill
- `.claude-plugin/plugin.json` — no change needed (`"commands": ["./commands"]` and `"skills": ["./skills"]` already handle the respective directories)
- `docs/ARCHITECTURE.md` — may reference commands/ structure; verify no hard-coded path
- `README.md` — verify no reference to `commands/ready-issue.md`

### Similar Patterns
- `skills/confidence-check/SKILL.md` — model/frontmatter structure to follow
- `skills/manage-issue/SKILL.md` — example of a complex workflow skill

### Tests
- No direct unit tests for skills/commands; integration tested via usage

### Documentation
- `CLAUDE.md` skill description line for ready-issue (add `^` marker)

### Configuration
- N/A — `plugin.json` already registers `./skills` directory

## Implementation Steps

1. Create `skills/ready-issue/` directory
2. Copy `commands/ready-issue.md` content into `skills/ready-issue/SKILL.md`
3. Update SKILL.md frontmatter: add `model: sonnet`, expand description with trigger keywords
4. Delete `commands/ready-issue.md`
5. Update `CLAUDE.md` to add `^` marker to `ready-issue` in the skill listing
6. Verify `docs/ARCHITECTURE.md` and `README.md` have no hard-coded `commands/ready-issue.md` path references

## Scope Boundaries

- **In scope**: File migration, frontmatter additions, documentation marker update
- **Out of scope**: Any behavioral changes to validation logic, changes to `allowed-tools`, changes to automation scripts (`ll-auto`, `ll-parallel`) — they invoke via `/ll:ready-issue` which works identically regardless of command vs. skill

## Impact

- **Priority**: P5 — No functional gap; purely housekeeping/consistency
- **Effort**: Low — Mechanical migration; no logic changes
- **Risk**: Low — Additive rename; `/ll:ready-issue` invocation syntax unchanged
- **Breaking Change**: No — invocation syntax, output format, and automation integration are unaffected

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Defines skill vs command conventions and `^` marker usage |
| `docs/ARCHITECTURE.md` | System design context for commands vs skills structure |

## Labels

`enhancement`, `captured`, `skills`, `ready-issue`, `housekeeping`

## Session Log

- `/ll:capture-issue` - 2026-02-22T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36760d80-f75d-44ae-b2e2-021d60598e74.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocked By

- ENH-446

---

## Status

**Open** | Created: 2026-02-22 | Priority: P5
