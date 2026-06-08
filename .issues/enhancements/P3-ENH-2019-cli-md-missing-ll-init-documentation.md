---
id: ENH-2019
title: CLI.md missing documentation section for ll-init
status: done
priority: P3
type: ENH
created: 2026-06-08
testable: false
completed_at: 2026-06-08 16:30:14+00:00
---

## Summary

`ll-init` is a registered CLI entry point (`ll-init = "little_loops.cli:main_init"` in `scripts/pyproject.toml`) but `docs/reference/CLI.md` has no `### ll-init` section. Every other `ll-*` entry point defined in `pyproject.toml` has a corresponding documented section in CLI.md.

## Current Behavior

`docs/reference/CLI.md` documents all other `ll-*` tools (ll-action, ll-harness, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-issues, ll-deps, ll-history, etc.) but has no section for `ll-init`. Running `ll-init --help` shows full usage but there is no reference entry in the docs.

## Expected Behavior

`docs/reference/CLI.md` includes a `### ll-init` section documenting:
- Description and purpose (initialize little-loops for a project)
- Arguments/flags table (`--yes`, `--force`, `--dry-run`, `--plan`, `--hosts`, `--root`, and the `apply` subcommand)
- Usage examples matching the patterns in the argparse epilog

## Scope Boundaries

- Only add the `### ll-init` section to `docs/reference/CLI.md`; do not modify other sections or the CLI implementation
- Follow the same heading level and table/example structure used by adjacent `### ll-*` sections

## Impact

- **Priority**: P3 - Documentation gap only; does not affect functionality
- **Effort**: Small - Single new section following established patterns in CLI.md
- **Risk**: Low - Documentation-only change; no code modified
- **Breaking Change**: No

## Labels

`documentation`, `cli`

## Status

**Open** | Created: 2026-06-08 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-08T16:27:41 - `338b7ae2-70bb-4e80-be06-e62380887c77.jsonl`
