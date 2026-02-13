# Documentation Audit Report

**Date**: 2026-02-12
**Scope**: README.md and linked documentation
**Commit**: 21f1b3d

## Summary
- **Files audited**: 9 (README.md, CONTRIBUTING.md, docs/INDEX.md, docs/COMMANDS.md, docs/ARCHITECTURE.md, docs/API.md, docs/CONFIGURATION.md, docs/TROUBLESHOOTING.md, docs/SESSION_HANDOFF.md)
- **Issues found**: 10
  - Critical: 2
  - Warning: 6
  - Info: 2

---

## Results by File

### README.md

| Check | Status | Details |
|-------|--------|---------|
| File paths/links | PASS | All 10 linked docs exist |
| Agent count (8) | PASS | 8 agent files confirmed |
| Skill count (8) | PASS | 8 skill dirs confirmed |
| CLI tool count (11) | PASS | 11 entry points in pyproject.toml |
| Command count (34) | **FAIL** | 35 command files exist |
| Command tables | **FAIL** | `refine_issue` missing |
| Code examples | PASS | Install/usage examples valid |
| Config examples | PASS | JSON examples match schema |

#### Issues
1. **[CRITICAL]** Line 84: Says "34 slash commands" but there are **35** — `refine_issue` was re-created as a new command (FEAT-380) after the original was renamed to `format_issue` (ENH-379). The count and tables were never updated.
2. **[CRITICAL]** Issue Refinement table (lines 104-113): Missing `/ll:refine_issue` — the codebase-driven research command that fills knowledge gaps in issue files.

### docs/ARCHITECTURE.md

| Check | Status | Details |
|-------|--------|---------|
| Component diagram | **FAIL** | "34 slash commands" wrong |
| Directory structure | **WARN** | Loops listing incomplete |
| Agent listing | PASS | All 8 listed |
| Skill listing | PASS | All 8 listed |
| Mermaid diagrams | PASS | Syntax valid |
| Skill reference | **WARN** | Wrong command syntax |

#### Issues
3. **[WARNING]** Lines 24, 67: Mermaid diagram and directory listing say "34 slash commands" / "34 slash command templates" — should be **35**.
4. **[WARNING]** Lines 98-103: Loops directory shows only 5 files but there are **8**. Missing: `history-reporting.yaml`, `sprint-execution.yaml`, `workflow-analysis.yaml`.
5. **[WARNING]** Line 626: References `/ll:map_dependencies` (underscore) but the skill directory is `map-dependencies` (hyphen), so correct invocation is `/ll:map-dependencies`.

### docs/COMMANDS.md

| Check | Status | Details |
|-------|--------|---------|
| Command coverage | **FAIL** | Missing `refine_issue` |
| Quick reference | **FAIL** | 34/35 commands |
| Descriptions | PASS | Match actual behavior |
| Arguments | PASS | Accurate |

#### Issues
6. **[WARNING]** `refine_issue` is absent from both the detailed command sections and the quick reference table at the bottom. Should be added under Issue Management with its description and arguments.

### CONTRIBUTING.md

| Check | Status | Details |
|-------|--------|---------|
| Install steps | PASS | Accurate |
| Test commands | PASS | All work |
| Project structure | **WARN** | cli.py comment incomplete |
| Links | PASS | All resolve |

#### Issues
7. **[WARNING]** Lines 166-167: The `cli.py` inline comment lists 7 entry points but cli.py actually has **9** (`ll-verify-docs` and `ll-check-links` from `main_verify_docs`/`main_check_links` are missing from the comment).

### docs/API.md

| Check | Status | Details |
|-------|--------|---------|
| Module table | PASS | All modules listed |
| Install command | **WARN** | Missing `-e` and `[dev]` |
| Code examples | PASS | Import paths correct |

#### Issues
8. **[WARNING]** Line 13: Shows `pip install /path/to/little-loops/scripts` without `-e` flag or `[dev]` extras. CONTRIBUTING.md recommends `pip install -e "./scripts[dev]"`. Developers following API.md would get a non-editable install without test dependencies.

### docs/CONFIGURATION.md

| Check | Status | Details |
|-------|--------|---------|
| Config sections | PASS | All major sections documented |
| Variable substitution | PASS | Correct |
| Full example accuracy | **INFO** | `timeout_per_issue` value differs from default |
| context_monitor docs | **INFO** | Missing dedicated table |

#### Issues
9. **[INFO]** Line 55: Full example shows `"timeout_per_issue": 7200` while the `parallel` table (line 199) documents the default as `3600`. While the example isn't claiming to show defaults, users may copy it and get non-default behavior.
10. **[INFO]** `context_monitor` has no table in CONFIGURATION.md (the primary config reference) — users must go to SESSION_HANDOFF.md for defaults. Consider adding a brief table or cross-reference.

### docs/INDEX.md, docs/TROUBLESHOOTING.md, docs/SESSION_HANDOFF.md

| Check | Status | Details |
|-------|--------|---------|
| Links | PASS | All resolve |
| Content accuracy | PASS | Consistent with codebase |
| Config references | PASS | Match schema |

---

## Recommended Fixes

### Critical (Must Fix)
1. **README.md:84** — Change "34 slash commands" to "35 slash commands"
2. **README.md Issue Refinement table** — Add row: `/ll:refine_issue [id]` | Refine issue with codebase-driven research

### Warnings (Should Fix)
3. **ARCHITECTURE.md:24,67** — Update "34" to "35" in diagram and directory listing
4. **ARCHITECTURE.md:98-103** — Add 3 missing loop files to directory listing
5. **ARCHITECTURE.md:626** — Change `/ll:map_dependencies` to `/ll:map-dependencies`
6. **COMMANDS.md** — Add `refine_issue` section and quick reference row
7. **CONTRIBUTING.md:166-167** — Add `ll-verify-docs, ll-check-links` to cli.py comment
8. **API.md:13** — Change to `pip install -e "/path/to/little-loops/scripts[dev]"`

### Suggestions
9. Align CONFIGURATION.md full example's `timeout_per_issue` with default (3600)
10. Add `context_monitor` cross-reference to CONFIGURATION.md
