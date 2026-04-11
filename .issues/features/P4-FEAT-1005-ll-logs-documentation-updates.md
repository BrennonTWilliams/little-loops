---
id: FEAT-1005
type: FEAT
priority: P4
status: backlog
title: Documentation file updates for ll-logs
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 84
outcome_confidence: 86
testable: false
blocked_by: [FEAT-1002]
---

# FEAT-1005: Documentation file updates for ll-logs

## Summary

Update all user-facing documentation files to register and describe the new `ll-logs` CLI tool: `CLAUDE.md`, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, and `CONTRIBUTING.md`.

## Current Behavior

`ll-logs` does not appear in any documentation files (`CLAUDE.md`, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`). The CLI Tools count in `README.md` reads "13 CLI tools".

## Expected Behavior

`ll-logs` is documented in all user-facing documentation files with accurate subcommand descriptions and flag tables. The CLI tool count in `README.md` is updated to "14 CLI tools".

## Motivation

This feature completes the `ll-logs` implementation (FEAT-1002) by making it visible to users through standard documentation. Without these updates, users cannot discover or understand the tool, and the CLI tool count remains inconsistent.

## Use Case

**Who**: Developer or automation user working with little-loops

**Context**: After `ll-logs` is shipped (FEAT-1002), they browse `CLAUDE.md` or `docs/reference/CLI.md` to learn how to use the tool

**Goal**: Find accurate documentation covering `discover`, `extract`, and `tail` subcommands with flag references

**Outcome**: `ll-logs` is discoverable alongside other CLI tools in all standard documentation locations

## Parent Issue
Decomposed from FEAT-1004: Documentation and wiring updates for ll-logs

## Prerequisites

FEAT-1002 must be implemented first (`ll-logs` must exist to document it accurately).

## Implementation Steps

1. **Update `CLAUDE.md`** — add `ll-logs` to CLI Tools section (after `ll-gitignore` entry)

2. **Update `docs/reference/CLI.md`** — add `### ll-logs` section after `### ll-gitignore` section (~line 881, before `### ll-verify-docs`); include flag table with `discover`, `extract`, and `tail` subcommands and their flags (`--project`, `--all`, `--cmd`, `--loop`)

2b. **Update `docs/reference/CLI.md` Common Flags table** (lines 15-28) — add `ll-logs` to the "Used by" column for three existing flag rows:
   - `--dry-run` row: append `, ll-logs`
   - `--quiet` row: append `, ll-logs`
   - `--config` row: append `, ll-logs`

   `ll-logs` uses all three flags via `add_dry_run_arg()`, `add_quiet_arg()`, and `add_config_arg()` (per FEAT-1002 spec), making it consistent with tools like `ll-sync` that appear in all three columns.

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

3. **Update `docs/reference/API.md`** — add `ll-logs` command reference

4. **Update `docs/ARCHITECTURE.md`** — add `├── logs.py` to the `scripts/little_loops/cli/` directory tree (~line 180)

5. **Update `README.md`**:
   - Change `13 CLI tools` → `14 CLI tools` at line 90
   - Add `### ll-logs` section after `### ll-gitignore` section (~line 431) following same pattern as other tool sections

6. **Update `CONTRIBUTING.md:183-194`** — add `├── logs.py` to the `cli/` directory tree listing (parallel to the `docs/ARCHITECTURE.md` tree update in step 4)

## Integration Map

### Files to Modify
- `CLAUDE.md` — CLI Tools section
- `docs/reference/CLI.md` — add `### ll-logs` section with flag table (after line 881); also update Common Flags table (lines 15-28) "Used by" column for `--dry-run`, `--quiet`, `--config`
- `docs/reference/API.md` — add command reference
- `docs/ARCHITECTURE.md` — add `├── logs.py` to cli/ directory tree (~line 180)
- `README.md` — count update (line 90: 13→14) + new section (after line 431)
- `CONTRIBUTING.md:183-194` — add `├── logs.py` to cli/ directory tree listing

### Similar Patterns
- Other CLI tool sections in `docs/reference/CLI.md` (e.g., `### ll-messages`, `### ll-history`) — follow same heading + flag table format
- Other tool entries in `README.md` (e.g., `### ll-gitignore`) — follow same section pattern

### Dependent Files (Callers/Importers)
- N/A — documentation files have no importers

### Tests
- N/A — documentation-only changes require no test file updates

### Documentation
- These ARE the documentation files being changed (see Files to Modify above)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Prerequisite state (as of 2026-04-08):**
- `scripts/little_loops/cli/logs.py` — does NOT exist; FEAT-1002 is not yet implemented
- `ll-logs` is not registered in `scripts/pyproject.toml` `[project.scripts]` (currently 13 entries, `ll-logs` absent)
- `scripts/little_loops/cli/__init__.py:20-36` has no `main_logs` import or `__all__` entry
- **All documentation edits in this issue must be done AFTER FEAT-1002 ships** so the flags/subcommands can be verified against the actual implementation

**Verified insertion points:**
- `docs/reference/CLI.md`: `### ll-gitignore` section ends at line 879; `### ll-logs` goes after the `---` separator at line 881
- `README.md`: `ll-gitignore` section ends at line 431; `ll-logs` section goes between line 431 and `### ll-verify-docs / ll-check-links` at line 433
- `docs/reference/API.md`: `main_gitignore` is NOT documented in API.md; `### main_logs` goes after `### main_check_links` (ends at line 3207), before `## little_loops.workflow_sequence` at line 3209
- `docs/ARCHITECTURE.md`: cli/ flat files listed at lines 175-204; add `├── logs.py` near other flat CLI files (after `history.py` alphabetically)
- `CONTRIBUTING.md`: cli/ tree at lines 182-194; add `├── logs.py` near flat files (after `history.py`)

**Complete flag set per FEAT-1002 spec** (the Implementation Steps flag table is incomplete):
- Top-level parser (all subcommands): `--verbose`/`-v`, `--config` (via `add_config_arg()`), `--dry-run`/`-n` (via `add_dry_run_arg()`), `--quiet`/`-q` (via `add_quiet_arg()`)
- `discover`: no subcommand-specific flags
- `extract`: `--project`, `--all`, `--cmd`
- `tail`: `--loop`

The CLI.md `#### ll-logs extract` and `#### ll-logs tail` sections in step 2 should add a note or table row indicating these global flags apply to all subcommands (follow the `### ll-history` pattern at `docs/reference/CLI.md:663-717`).

**API.md entry format** (follow `### main_messages` at `docs/reference/API.md:3117-3134`):
```markdown
### main_logs

```python
def main_logs() -> int
```

Entry point for `ll-logs` command. Discover, extract, and tail Claude Code session logs for ll-loop and ll-commands.

**Returns:** Exit code

**CLI Arguments:**
- `-v, --verbose` - Verbose progress output
- `--config` - Path to project root (default: current directory)
- `-n, --dry-run` - Preview without modifying files
- `-q, --quiet` - Suppress non-essential output
```

### One-line description (use consistently across all files)
`ll-logs` — Discover, extract, and tail Claude Code session logs for ll-loop and ll-commands

## Acceptance Criteria

- [ ] `ll-logs` appears in `CLAUDE.md` CLI Tools section
- [ ] `docs/reference/CLI.md` has a complete `### ll-logs` section with subcommand and flag table
- [ ] `README.md` count updated to 14 CLI tools and new section added
- [ ] `docs/reference/API.md` includes `ll-logs` command reference
- [ ] `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` cli/ trees include `├── logs.py`

## Impact

- **Priority**: P4 - documentation
- **Effort**: Small - prose updates only, no logic changes
- **Risk**: Very low - additive docs changes
- **Breaking Change**: No

## Labels

`feature`, `documentation`, `cli`

## Verification Notes

**Verdict**: VALID — Blocked by FEAT-1002 (not yet implemented). All prerequisite conditions confirmed:

- `scripts/little_loops/cli/logs.py` does not exist ✓
- `README.md:90` still reads "13 CLI tools" ✓ (note: `ll-generate-schemas` was added to pyproject.toml but not yet to README or help.md, so count remains 13 from a docs perspective)
- `docs/reference/CLI.md` still has no `### ll-logs` section ✓
- Insertion point reference (`### ll-gitignore` ending at line 879) may have shifted slightly — verify before implementing

— Verified 2026-04-11

## Session Log
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:wire-issue` - 2026-04-08T22:15:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7442f9bc-9ee0-4418-bdc5-0a1d97abfe36.jsonl`
- `/ll:refine-issue` - 2026-04-08T22:11:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/af0c751e-6fe7-46aa-9bdf-a9083eb40d63.jsonl`
- `/ll:format-issue` - 2026-04-08T22:07:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7d2deea6-cb0f-420c-b650-c96b5bb4036d.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7158b6b3-d465-4658-9645-8a41be41765d.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
