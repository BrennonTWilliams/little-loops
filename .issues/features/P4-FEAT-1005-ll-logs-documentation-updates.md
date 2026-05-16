---
id: FEAT-1005
type: FEAT
priority: P4
status: done
title: Documentation file updates for ll-logs
discovered_date: 2026-04-08
discovered_by: issue-size-review
completed_at: 2026-04-23T23:56:40Z
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
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

1. **Update `docs/reference/CLI.md`** — add `### ll-logs` section after `### ll-gitignore` section (~line 881, before `### ll-verify-docs`); include flag table with `discover`, `extract`, and `tail` subcommands and their flags (`--project`, `--all`, `--cmd`, `--loop`)

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

### Wiring Phase (added by `/ll:wire-issue`)

_Corrections identified by wiring analysis:_

- **Step 2b: DO NOT execute** — `_build_parser()` in `scripts/little_loops/cli/logs.py:297-347` registers no `--dry-run`, `--quiet`, or `--config` flags on the root parser or any subparser. Adding `ll-logs` to the Common Flags table would document flags that do not exist in the as-built implementation.
- **Step 3 is a REPLACEMENT, not an addition** — `docs/reference/API.md:3277-3292` already has `### main_logs`; the `**CLI Arguments:**` block at lines 3287-3291 lists four non-existent global flags. Replace those four bullet lines with the subcommands format from Codebase Research Findings (see below).
- **Optional test** — `scripts/tests/test_ll_logs_wiring.py` does not test `docs/reference/API.md` content. Follow the `test_enh1138_doc_wiring.py` pattern to add a `TestApiReferenceWiring` class that pins the corrected subcommand docs.

## Integration Map

### Files to Modify
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs_wiring.py` — existing wiring tests cover `commands/help.md`, `skills/init/SKILL.md`, and `skills/configure/areas.md` but do **not** test `docs/reference/API.md` content. Optional: add `TestApiReferenceWiring` class (following `test_enh1138_doc_wiring.py` pattern) to pin the corrected subcommand docs after the API.md fix.

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

### Codebase Research Findings (2026-04-23 refinement pass)

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CONTRIBUTING.md: already done**
- `CONTRIBUTING.md:192` — `├── logs.py` is ALREADY PRESENT between `history.py` and `messages.py`. Implementation step 6 is complete; no edit needed.

**docs/reference/API.md: exists but content is inaccurate**
- `docs/reference/API.md:3277-3292` — `### main_logs` section EXISTS, but it lists four top-level CLI arguments (`-v/--verbose`, `--config`, `-n/--dry-run`, `-q/--quiet`) that are NOT registered in the actual `_build_parser()` at `scripts/little_loops/cli/logs.py:297-347`. The real implementation has only the three subcommands below with no shared global flags.
- The entry must be **replaced** (not a new insertion). Correct replacement content:

```markdown
### main_logs

```python
def main_logs() -> int
```

Entry point for `ll-logs` command. Discover, extract, and tail Claude Code session logs for ll-loop and ll-commands.

**Returns:** 0 on success, 1 when no subcommand given or on error

**Subcommands:**
- `discover` — List all Claude projects with ll activity (no flags)
- `extract` — Extract ll-relevant JSONL records to `logs/<slug>/<session-id>.jsonl`; requires `--project DIR` or `--all`; optional `--cmd TOOL` to filter by CLI tool
- `tail` — Stream live events from an active loop session; requires `--loop NAME`

---
```

**Verification notes correction**
The Verification Notes section (lines 211-225) states "Still missing ✗" for both API.md and CONTRIBUTING.md, but both are present in the codebase as of the `fdf2c2f4` commit. The notes were written after that commit and are inaccurate. Actual remaining work is solely the API.md content fix described above.

## Acceptance Criteria

- [x] `ll-logs` appears in `CLAUDE.md` CLI Tools section
- [x] `docs/reference/CLI.md` has a complete `### ll-logs` section with subcommand and flag table
- [x] `README.md` count updated to 14 CLI tools and new section added
- [x] `docs/reference/API.md` includes `ll-logs` command reference
- [x] `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` cli/ trees include `├── logs.py`

## Impact

- **Priority**: P4 - documentation
- **Effort**: Small - prose updates only, no logic changes
- **Risk**: Very low - additive docs changes
- **Breaking Change**: No

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `.claude/CLAUDE.md` CLI Tools update belongs exclusively to **FEAT-1006** (wiring/permissions scope), not this issue. FEAT-1005 owns only user-facing documentation under `docs/` and root-level docs (`README.md`, `CONTRIBUTING.md`). This avoids two issues both writing the same CLAUDE.md entry.

## Labels

`feature`, `documentation`, `cli`

## Verification Notes

**Verdict**: NEEDS_UPDATE — FEAT-1002 shipped; most doc updates are done but two items remain:

**Done ✓**
- `docs/reference/CLI.md:995` — `### ll-logs` section with subcommand and flag table ✓
- `README.md:358` — `### ll-logs` section added ✓; count now reads "16 CLI tools" (includes ll-logs) ✓
- `docs/ARCHITECTURE.md:217` — `├── logs.py` in cli/ tree ✓
- `.claude/CLAUDE.md:109` — `ll-logs` in CLI Tools section ✓ (FEAT-1006 scope, but already done)

**Still missing ✗**
- `docs/reference/API.md` — NO `### main_logs` entry (still absent; add after `### main_check_links`)
- `CONTRIBUTING.md` — NO `├── logs.py` in cli/ directory tree (~lines 182-194)

**Action needed**: Implement the two missing items above.

— Verified 2026-04-23

_Wiring pass correction (2026-04-23):_
The "Still missing ✗" claims above are **inaccurate** as of commit `fdf2c2f4`:
- `CONTRIBUTING.md:192` — `├── logs.py` IS present (between `history.py` and `messages.py`) ✓
- `docs/reference/API.md:3277` — `### main_logs` IS present, but `**CLI Arguments:**` block (lines 3287-3291) lists four global flags (`-v/--verbose`, `--config`, `-n/--dry-run`, `-q/--quiet`) that do not exist in the actual parser. **Action needed**: Replace those four bullet lines with subcommands format — do not add a new section.

## Session Log
- `/ll:ready-issue` - 2026-04-23T23:55:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/505de9cd-4ca7-4d18-8750-a5c6542f39e5.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab8d94a1-ea7c-4a30-9041-a8059b1d8041.jsonl`
- `/ll:wire-issue` - 2026-04-23T23:52:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a730208-4b84-4f23-9d7c-2df0dba38a12.jsonl`
- `/ll:refine-issue` - 2026-04-23T23:48:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb0ab28e-5acd-4a08-a244-c1cea97bb0c2.jsonl`
- `/ll:verify-issues` - 2026-04-23T23:33:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3de88f83-60a8-4b24-a159-032238ca23ed.jsonl`
- `/ll:verify-issues` - 2026-04-23T23:07:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3de88f83-60a8-4b24-a159-032238ca23ed.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-22T20:04:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82d256a6-9a99-40f5-8866-377a208de262.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:wire-issue` - 2026-04-08T22:15:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7442f9bc-9ee0-4418-bdc5-0a1d97abfe36.jsonl`
- `/ll:refine-issue` - 2026-04-08T22:11:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/af0c751e-6fe7-46aa-9bdf-a9083eb40d63.jsonl`
- `/ll:format-issue` - 2026-04-08T22:07:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7d2deea6-cb0f-420c-b650-c96b5bb4036d.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7158b6b3-d465-4658-9645-8a41be41765d.jsonl`

---

## Resolution

**Completed**: 2026-04-23T23:56:40Z

The only remaining work was fixing `docs/reference/API.md:3277-3292` — the `### main_logs` section existed but listed four non-existent global flags (`-v/--verbose`, `--config`, `-n/--dry-run`, `-q/--quiet`). Replaced the inaccurate `**CLI Arguments:**` block with an accurate `**Subcommands:**` block (`discover`, `extract`, `tail`) matching the actual `_build_parser()` implementation in `scripts/little_loops/cli/logs.py`.

All other documentation items were already completed by commit `fdf2c2f4`.

## Status

**Completed** | Created: 2026-04-08 | Completed: 2026-04-23 | Priority: P4
