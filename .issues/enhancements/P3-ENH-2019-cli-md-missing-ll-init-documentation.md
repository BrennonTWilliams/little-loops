---
id: ENH-2019
title: "CLI.md missing documentation section for ll-init"
status: open
priority: P3
type: ENH
created: 2026-06-08
---

## Problem

`ll-init` is a registered entry point in `scripts/pyproject.toml` (`ll-init = "little_loops.cli:main_init"`) and is listed in `CLAUDE.md` as a CLI tool, but `docs/reference/CLI.md` has no documentation section for it. Every other `ll-*` entry point defined in `pyproject.toml` has a corresponding section in CLI.md.

## Location

- File: `docs/reference/CLI.md`
- Missing: An `#### ll-init` section (equivalent in structure to other `ll-*` tool sections)

## Expected Outcome

`docs/reference/CLI.md` includes a section for `ll-init` documenting:
- Description and purpose
- Arguments/flags table
- Usage examples

## Source

Discovered during `/ll:audit-docs docs/reference` on 2026-06-08.
