---
id: ENH-1275
title: Document ll-logs CLI tool in README and CLI reference
type: ENH
priority: P3
status: open
testable: false
discovered_commit: cd924da7
discovered_branch: main
discovered_date: 2026-04-23
completed_at: 2026-04-23T22:57:16Z
discovered_by: audit-docs
doc_file: README.md, docs/reference/CLI.md
---

# ENH-1275: Document ll-logs CLI tool in README and CLI reference

## Summary

`ll-logs` is one of the 16 user-facing CLI tools but has no documentation section in either `README.md` or `docs/reference/CLI.md`. It was implemented in `FEAT-1002` and partially documented (CLAUDE.md + ARCHITECTURE.md were updated in `8098bd95`) but the two primary public-facing references were missed.

## Location

- **File 1**: `README.md` — CLI Tools section (after `ll-messages` section, ~line 356)
- **File 2**: `docs/reference/CLI.md` — Missing `### ll-logs` section

## Problem

The README says "16 CLI tools" and lists `ll-logs` in CLAUDE.md but provides no usage examples or flag documentation in the README body or the CLI reference. Users discovering the tool have no reference for its subcommands.

## Expected Content

Both files need a `### ll-logs` section. The tool has three subcommands:

```bash
ll-logs discover              # List all projects with ll activity (one path per line)
ll-logs tail --loop <name>   # Stream live events from an active loop session
ll-logs extract --all             # Extract all projects to logs/
ll-logs extract --project /path  # Extract one project to logs/<slug>/
ll-logs extract --all --cmd ll-history  # Filter to ll-history invocations
```

Reference: `ll-logs --help` and `docs/ARCHITECTURE.md` (logs.py section).

## Impact

- **Severity**: Warning (tool is undiscoverable without source code)
- **Effort**: Small (copy from `ll-logs --help` + CLAUDE.md description)
- **Risk**: Low

## Scope Boundaries

- Only update `README.md` and `docs/reference/CLI.md` — no changes to CLAUDE.md or ARCHITECTURE.md (already updated in commit `8098bd95`)
- Do not add integration tests or unit tests (documentation-only change)
- Do not refactor existing CLI documentation sections; only add the missing `### ll-logs` entry

## Labels

`enhancement`, `documentation`, `auto-generated`

## Session Log
- `/ll:ready-issue` - 2026-04-23T22:54:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d270dc34-50a0-47b1-95d9-d6f518f16644.jsonl`

---

## Resolution

Added `### ll-logs` sections to both `README.md` (after `### ll-messages`) and `docs/reference/CLI.md` (after `### ll-messages`, before `### ll-gitignore`). Both sections document the three subcommands (`discover`, `tail`, `extract`) with flags and examples matching the tool's argparse help text.

## Status

**Completed** | Created: 2026-04-23 | Completed: 2026-04-23 | Priority: P3
