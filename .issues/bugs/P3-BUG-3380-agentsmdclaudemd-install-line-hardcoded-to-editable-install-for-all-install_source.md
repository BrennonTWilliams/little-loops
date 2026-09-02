---
id: BUG-3380
type: BUG
title: AGENTS.md/CLAUDE.md install line hardcoded to editable install for all install_source
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-02'
captured_at: '2026-09-02T22:19:40Z'
---

# BUG-3380: AGENTS.md/CLAUDE.md install line hardcoded to editable install for all install_source

## Summary

`ll-init` generates AGENTS.md (and CLAUDE.md) with a hardcoded `Install:` line
of `pip install -e "./scripts[dev]"` regardless of the consuming project's
`install_source`. This command is only valid for the little-loops source repo
itself (editable dev install with the `scripts/` package dir and `[dev]`
extras present); PyPI-installed and Claude Code plugin-installed consumers
have no `scripts[dev]` to install and the command fails for them.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

`scripts/little_loops/init/writers.py:247`, inside `_render_commands_block()`:

```python
lines.extend(["", 'Install: `pip install -e "./scripts[dev]"`', ""])
```

This runs once at module import time to build module-level constants
`_CLAUDE_MD_COMMANDS_BLOCK` (line 252) and `_AGENTS_MD_COMMANDS_BLOCK` (line
256), which `write_claude_md()` and `write_agents_md()` then append verbatim.
Neither writer function accepts an `install_source` parameter, so the string
never varies per project.

`install_source` is already computed and in scope at every call site that
could pass it through instead:

- `scripts/little_loops/init/cli.py:519-520` (`detect_installation(...)`)
  before the writer calls at `cli.py:706` / `cli.py:711`
- `scripts/little_loops/init/cli.py:918-936` (`_run_yes` path) before the
  writer calls at `cli.py:918` / `cli.py:923`
- `scripts/little_loops/init/tui.py:185-274` before the writer calls at
  `tui.py:895` / `tui.py:900`

Precedent for branching writer/CLI behavior on `install_source` already
exists at `cli.py:247` (`== "project-claude-code"`) and `cli.py:549`
(`== "local-editable"`).

`config-schema.json:2062-2066` defines the `install_source` enum:
`local-editable`, `pypi`, `global-claude-code`, `project-claude-code`,
`global-codex`, `global-pi`, or `null`.

## Steps to Reproduce

1. Run `ll-init` in a project where little-loops was installed via
   `pip install little-loops` (install_source: `pypi`) or as a Claude Code
   plugin (`global-claude-code` / `project-claude-code`).
2. Open the generated `AGENTS.md` (or `CLAUDE.md`).
3. The `Install:` line reads `pip install -e "./scripts[dev]"` — a command
   that assumes a `scripts/` dir and dev extras that don't exist in that
   project.

## Expected vs Actual

- **Expected**: the install line reflects how the project actually installed
  little-loops — e.g. `pip install little-loops` for `pypi`, no bare
  `pip install -e "./scripts[dev]"` for plugin-based installs.
- **Actual**: every generated AGENTS.md/CLAUDE.md gets the same
  source-repo-only editable-dev-install command.

## Suggested Fix

Thread `install_source: str | None` into `_render_commands_block()` and into
`write_claude_md()` / `write_agents_md()`; branch the Install line so
`pip install -e "./scripts[dev]"` renders only when
`install_source == "local-editable"`, otherwise `pip install little-loops`
(or omit the line for plugin-based `install_source` values, where there's no
pip install to run at all). Update the three call sites above to pass the
already-detected `install_source` through instead of leaving it unused.

## Related

`P2-BUG-1071` / `P3-ENH-1020` cover a related but distinct instance of the
same install_source-unaware problem class in `skills/init/SKILL.md` /
`skills/configure/SKILL.md`'s bash `INSTALL_CMD` shim. That shim already
branches correctly (`[ -d "./scripts" ] && ... || INSTALL_CMD="pip install
--upgrade little-loops"`) and is not affected by this bug — this issue is
scoped to the Python-side AGENTS.md/CLAUDE.md generator in `writers.py` only.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-02 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-02T22:19:45 - `64850b61-eea3-464a-8dc5-33dc204c7fce.jsonl`
