---
id: FEAT-1004
type: FEAT
priority: P4
status: backlog
title: Documentation and wiring updates for ll-logs
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 88
outcome_confidence: 63
testable: false
---

# FEAT-1004: Documentation and wiring updates for ll-logs

## Summary

Update all documentation, skills configuration, and help references to register and describe the new `ll-logs` CLI tool. This is purely additive — no production code changes beyond referencing the tool already implemented in FEAT-1002.

## Current Behavior

`ll-logs` is implemented (FEAT-1002) but invisible to users: it does not appear in `CLAUDE.md`, `README.md`, `commands/help.md`, `docs/reference/CLI.md`, or `docs/reference/API.md`. It is also not wired into `skills/init/SKILL.md` permissions or `skills/configure/areas.md`, so it is not granted during project initialization. The `README.md` still reports 13 CLI tools.

## Expected Behavior

`ll-logs` is documented in all standard locations: `CLAUDE.md` CLI Tools section, `README.md` (count updated to 14, new tool section added), `docs/reference/CLI.md` with full subcommand and flag table, `docs/reference/API.md`, and `commands/help.md` CLI TOOLS block. Skills wiring in `skills/init/SKILL.md` and `skills/configure/areas.md` ensures the tool is authorized during init and enumerated in configure output.

## Motivation

Without documentation and skills wiring, `ll-logs` effectively doesn't exist from a user perspective — discovery requires raw filesystem exploration. Proper documentation maintains consistency with the other 13 CLI tools and makes the tool accessible to users who rely on `/ll:help`, `README.md`, or `docs/reference/CLI.md` to discover available commands.

## Use Case

A developer runs `/ll:help` or browses `README.md` to discover available CLI tools. After FEAT-1002 ships, `ll-logs` is silently absent from all documentation surfaces. This issue ensures that a user who reads `README.md`, runs `ll-logs --help`, or checks `docs/reference/CLI.md` gets complete, accurate information about the tool's `discover`, `extract`, and `tail` subcommands.

## Parent Issue
Decomposed from FEAT-1001: Add log discovery and extraction for ll-loop and ll-commands

## Prerequisites

FEAT-1002 must be implemented first (`ll-logs` must exist to document it accurately).

## Implementation Steps

1. **Update `CLAUDE.md`** — add `ll-logs` to CLI Tools section (after `ll-gitignore` entry)

2. **Update `docs/reference/CLI.md`** — add `### ll-logs` section after `### ll-gitignore` section (~line 881, before `### ll-verify-docs`); include flag table with `discover`, `extract`, and `tail` subcommands and their flags (`--project`, `--all`, `--cmd`, `--loop`)

3. **Update `docs/reference/API.md`** — add `ll-logs` command reference

4. **Update `docs/ARCHITECTURE.md`** — add `├── logs.py` to the `scripts/little_loops/cli/` directory tree (~line 180)

5. **Update `README.md`**:
   - Change `13 CLI tools` → `14 CLI tools` at line 90
   - Add `### ll-logs` section after `ll-gitignore` section (~line 431) following same pattern as other tool sections

6. **Update `commands/help.md:208-221`** — add `ll-logs` to CLI TOOLS block (currently ends at `ll-check-links`)

7. **Update `CONTRIBUTING.md:183-194`** — add `├── logs.py` to the `cli/` directory tree listing (parallel to the `docs/ARCHITECTURE.md` tree update in step 4)

8. **Update skills configuration** (wiring):
   - `skills/init/SKILL.md:428-443` — add `"Bash(ll-logs:*)"` to canonical `permissions.allow` list written to `.claude/settings.local.json` during init
   - `skills/init/SKILL.md:510-522` — add `ll-logs` to CLAUDE.md CLI Tools boilerplate (file-exists case)
   - `skills/init/SKILL.md:539-546` — add `ll-logs` to CLAUDE.md CLI Tools boilerplate (create-new case)
   - `skills/configure/areas.md:793` — update count (`12` → `13`) and enumerated list in the "Authorize all N ll- CLI tools" description string

## Integration Map

### Files to Modify
- `CLAUDE.md` — CLI Tools section
- `docs/reference/CLI.md` — add `### ll-logs` section with flag table
- `docs/reference/API.md` — add command reference
- `docs/ARCHITECTURE.md` — add to cli/ directory tree
- `README.md` — count update + new section
- `commands/help.md:208-221` — add to CLI TOOLS block
- `skills/init/SKILL.md:428-443` — permissions.allow list
- `skills/init/SKILL.md:510-522` — CLAUDE.md boilerplate (file-exists case)
- `skills/init/SKILL.md:539-546` — CLAUDE.md boilerplate (create-new case)
- `skills/configure/areas.md:793` — count and enumerated list
- `CONTRIBUTING.md:183-194` — add `├── logs.py` to cli/ directory tree listing _(Wiring pass added by `/ll:wire-issue`)_

### Dependent Files (Callers/Importers)
- N/A — documentation-only changes; no code imports or calls `ll-logs`

### Similar Patterns
- Other CLI tool sections in `docs/reference/CLI.md` (e.g., `### ll-messages`, `### ll-history`) — follow same heading + flag table format
- Other tool entries in `README.md` (e.g., `### ll-gitignore`) — follow same section pattern
- Other `Bash(ll-*:*)` entries in `skills/init/SKILL.md` permissions block — follow same format

### Tests
- N/A — documentation and wiring changes; no logic to unit test

### Configuration
- `skills/init/SKILL.md` — permissions.allow list and CLAUDE.md boilerplate blocks
- `skills/configure/areas.md` — CLI tools count and enumerated list

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Confirmed insertion points (verified by reading files)

| File | Confirmed Location | Action |
|------|--------------------|--------|
| `docs/reference/CLI.md:881` | After `### ll-gitignore` `---` separator; before `### ll-verify-docs` at line 883 | Insert new `### ll-logs` section |
| `README.md:431` | After `### ll-gitignore` section (lines 422–431) | Insert new `### ll-logs` section |
| `commands/help.md:221` | After `ll-check-links` entry (last entry, line 221) | Append `ll-logs` line |
| `skills/init/SKILL.md:441` | After `"Bash(ll-check-links:*)"` in permissions.allow block | Insert `"Bash(ll-logs:*)"` |
| `skills/init/SKILL.md:522` | End of CLAUDE.md boilerplate, file-exists case | Append `ll-logs` bullet |
| `skills/init/SKILL.md:546` | End of CLAUDE.md boilerplate, create-new case | Append `ll-logs` bullet |
| `skills/configure/areas.md:793` | `"Authorize all 12 ll- CLI tools …"` label description | Count 12→13, append `ll-logs` to list |
| `docs/ARCHITECTURE.md:~180` | `cli/` directory tree listing | Add `├── logs.py` |

#### One-line description (use consistently across all files)

`ll-logs` — Discover, extract, and tail Claude Code session logs for ll-loop and ll-commands

#### CLI.md flag table content (to write in step 2)

```markdown
### ll-logs

Discover, extract, and tail Claude Code session logs for ll-loop and ll-commands.

**Subcommands:**

#### `ll-logs discover`

List all Claude projects on the machine that contain ll activity.

_(No flags)_

#### `ll-logs extract`

Extract session logs for a project or all projects to the `logs/` directory.

| Flag | Short | Description |
|------|-------|-------------|
| `--project` | | Extract logs for one project by slug |
| `--all` | | Extract all projects to `logs/` |
| `--cmd` | | Filter by specific ll- CLI tool (e.g., `ll-history`) |

#### `ll-logs tail`

Tail active session logs for a named loop.

| Flag | Short | Description |
|------|-------|-------------|
| `--loop` | | Name of the loop to tail active sessions for |

**Examples:**
```bash
ll-logs discover                          # List all projects with ll activity
ll-logs extract --project myproject       # Extract logs for one project
ll-logs extract --all                     # Extract all projects to logs/
ll-logs extract --cmd ll-loop            # Filter to ll-loop sessions only
ll-logs tail --loop my-loop              # Tail active sessions for a loop
```

---
```

#### Note: pre-existing gap in commands/help.md and skills/configure/areas.md

`ll-gitignore` is also missing from `commands/help.md` CLI TOOLS block (12 entries, ends at `ll-check-links`) and from the `skills/configure/areas.md` enumerated list (12 tools named, `ll-gitignore` absent). This is a pre-existing inconsistency outside FEAT-1004's scope. When implementing step 7, only add `ll-logs`; do not fix the `ll-gitignore` gap (that warrants a separate issue). The count `12→13` in `skills/configure/areas.md` is correct for FEAT-1004's scope.

#### FEAT-1002 prerequisite status

As of research date 2026-04-08, `scripts/little_loops/cli/logs.py` does not exist — FEAT-1002 is not yet implemented. Verify actual flag names and signatures match the spec before writing final documentation. Entry point `ll-logs = "little_loops.cli:main_logs"` is absent from `scripts/pyproject.toml:48-63` and `main_logs` is absent from `scripts/little_loops/cli/__init__.py:20-56`.

## Acceptance Criteria

- [ ] `ll-logs` appears in `CLAUDE.md` CLI Tools section
- [ ] `docs/reference/CLI.md` has a complete `### ll-logs` section with subcommand and flag table
- [ ] `README.md` count updated to 14 CLI tools and new section added
- [ ] `commands/help.md` includes `ll-logs` in CLI TOOLS block
- [ ] `skills/init/SKILL.md` includes `ll-logs` in permissions and both CLAUDE.md boilerplate blocks
- [ ] `skills/configure/areas.md` count incremented and `ll-logs` added to enumerated list

## Impact

- **Priority**: P4 - documentation
- **Effort**: Small - prose updates only, no logic changes
- **Risk**: Very low - additive docs/config changes
- **Breaking Change**: No

## Labels

`feature`, `documentation`, `wiring`, `cli`

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-08T22:06:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7158b6b3-d465-4658-9645-8a41be41765d.jsonl`
- `/ll:wire-issue` - 2026-04-08T22:00:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c104ad9-d5a6-4341-a4a8-d735256fe8c9.jsonl`
- `/ll:refine-issue` - 2026-04-08T21:55:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a846d80e-b641-4b2d-aaa9-45449ffd3f8e.jsonl`
- `/ll:format-issue` - 2026-04-08T21:51:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6059f5bf-463b-4ab0-b91d-c3afce5630fa.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4567c5b-d32d-41b7-b9a6-b02cb4590a4e.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7158b6b3-d465-4658-9645-8a41be41765d.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-08
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-1005: Documentation file updates for ll-logs
- FEAT-1006: Skills and commands wiring for ll-logs

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
