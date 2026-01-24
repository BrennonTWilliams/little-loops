# Convert create_sprint Skill to Slash Command

## Summary

The `create_sprint` functionality is currently implemented as a Skill but should be a Slash Command (`/ll:create_sprint`) for consistency with other project commands.

## Current State

- `create_sprint` exists as a skill in `skills/create_sprint.md`
- Invoked via `/create_sprint`

## Desired State

- Create a new slash command at `commands/create_sprint.md`
- Command should be invoked as `/ll:create_sprint`
- Remove or deprecate the skill version

## Acceptance Criteria

- [ ] New command file exists at `commands/create_sprint.md`
- [ ] Command follows the standard command file format
- [ ] Functionality matches the existing skill
- [ ] Skill file is removed or marked as deprecated
- [ ] `/ll:help` output includes the new command

## Notes

Project preference is to use Skills for composable functionality and Slash Commands for user-facing operations. Sprint creation is a user-facing operation and should follow the `/ll:*` naming convention.

---

## Status

**Closed - Already Fixed** | Created: 2026-01-24 | Priority: P3

---

## Resolution

- **Action**: close
- **Completed**: 2026-01-24
- **Status**: Closed - Already Fixed

### Closure Reason

This issue is based on a false premise. The `create_sprint` functionality was **never** implemented as a Skill - it has always been a slash command.

### Evidence

1. The command file exists at `.claude/commands/create_sprint.md` and is invoked as `/ll:create_sprint`
2. No `skills/create_sprint.md` file exists or has ever existed in the repository
3. Git history confirms the command was created directly in the commands directory (commit 0bd5e8f shows rename from `ll_create_sprint.md` to `create_sprint.md` within the commands folder)
4. The command is documented in `docs/COMMANDS.md` under "Sprint Management"

All acceptance criteria are effectively already met since the slash command exists and functions correctly.
