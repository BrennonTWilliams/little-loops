# P1-BUG-077: Skills Use Wrong Directory Structure

## Summary

Skills are stored as flat `.md` files directly in the `skills/` directory instead of the required subdirectory structure with `SKILL.md` files.

## Problem

### Current Structure (Wrong)

```
skills/
├── capture-issue.md
├── create-loop.md
└── issue-workflow.md
```

### Expected Structure (Correct)

```
skills/
├── capture-issue/
│   └── SKILL.md
├── create-loop/
│   └── SKILL.md
└── issue-workflow/
    └── SKILL.md
```

## Impact

- Skills may not be auto-discovered by Claude Code's plugin system
- Plugin relies on fallback behavior rather than proper structure
- Cannot include supporting files (scripts, references, examples) per skill
- Inconsistent with Claude Code plugin conventions

## Root Cause

Skills were created using the simpler flat-file pattern instead of the subdirectory pattern required by the Claude Code plugin specification.

## Solution

For each skill file:

1. Create a subdirectory with the skill name (kebab-case)
2. Move the `.md` file into the subdirectory
3. Rename the file to `SKILL.md`

### Migration Steps

```bash
# For each skill:
mkdir -p skills/capture-issue
mv skills/capture-issue.md skills/capture-issue/SKILL.md

mkdir -p skills/create-loop
mv skills/create-loop.md skills/create-loop/SKILL.md

mkdir -p skills/issue-workflow
mv skills/issue-workflow.md skills/issue-workflow/SKILL.md
```

## Acceptance Criteria

- [x] Each skill has its own subdirectory in `skills/`
- [x] Each skill subdirectory contains a `SKILL.md` file
- [x] No flat `.md` files remain directly in `skills/`
- [x] Skill frontmatter (name, description) is preserved
- [x] Skills are discoverable after restructuring

## Files to Modify

| Current Path | New Path |
|--------------|----------|
| `skills/capture-issue.md` | `skills/capture-issue/SKILL.md` |
| `skills/create-loop.md` | `skills/create-loop/SKILL.md` |
| `skills/issue-workflow.md` | `skills/issue-workflow/SKILL.md` |

## Testing

1. After restructuring, start a new Claude Code session
2. Verify skills appear in the Skill tool's available skills list
3. Test invoking each skill to confirm they load correctly
4. Verify skill descriptions and trigger keywords work

## Benefits of Correct Structure

Once restructured, each skill can include supporting files:

```
skills/
├── capture-issue/
│   ├── SKILL.md
│   ├── templates/           # Issue templates
│   └── examples/            # Example issues
├── create-loop/
│   ├── SKILL.md
│   ├── scripts/             # Helper scripts
│   └── loop-templates/      # Loop definition templates
└── issue-workflow/
    ├── SKILL.md
    └── references/          # Workflow documentation
```

## Discovered By

Plugin structure audit using `plugin-dev:plugin-structure` skill

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-16
- **Status**: Completed

### Changes Made
- `skills/capture-issue.md` → `skills/capture-issue/SKILL.md`
- `skills/create-loop.md` → `skills/create-loop/SKILL.md`
- `skills/issue-workflow.md` → `skills/issue-workflow/SKILL.md`

### Verification Results
- Structure: PASS (no flat .md files, all subdirectories have SKILL.md)
- Content: PASS (frontmatter preserved in all files)
- Git: PASS (clean renames tracked)
