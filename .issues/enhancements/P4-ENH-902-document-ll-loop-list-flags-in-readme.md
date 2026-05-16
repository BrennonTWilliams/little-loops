---
discovered_commit: 65034c7349f19502348b3416c93c743ce77f63e4
discovered_branch: main
discovered_date: 2026-03-31
discovered_by: audit-docs
doc_file: README.md
testable: false
---

# ENH-902: Document `ll-loop list` flags in README

## Summary

Documentation issue found by `/ll:audit-docs`.

## Location

- **File**: `README.md`
- **Line(s)**: 282–283
- **Section**: CLI Tools → ll-loop

## Current Behavior

```markdown
ll-loop list                     # List all available loops
ll-loop list --json              # JSON array of available loops
```

## Problem

The README only shows `--json` for `ll-loop list`, but three additional flags exist and are useful:

- `--running` — show only actively running loops
- `--builtin` — show only built-in loops (ships with little-loops)
- `--status <status>` — filter running loops by status (e.g., `interrupted`, `awaiting_continuation`)

These flags are documented in `docs/guides/LOOPS_GUIDE.md` (line 1020) but absent from the README's CLI quick-reference section. Users consulting only the README won't know `--running` exists, which is the primary way to check what loops are active.

## Expected Behavior

```markdown
ll-loop list                     # List all available loops
ll-loop list --running           # List only running loops
ll-loop list --builtin           # List only built-in loops
ll-loop list --json              # JSON array of available loops
```

Optionally also add `--status` with a note about valid values.

## Scope Boundaries

- Add `--running` and `--builtin` lines to the README's ll-loop quick-reference block
- Optionally add `--status` with a note about valid values (e.g., `interrupted`, `awaiting_continuation`)
- Out of scope: comprehensive flag documentation (that lives in `docs/guides/LOOPS_GUIDE.md`); changes to LOOPS_GUIDE.md itself; adding flags for other `ll-loop` subcommands

## Impact

- **Severity**: Low (workaround: `--help` and LOOPS_GUIDE.md both cover it)
- **Effort**: Small (add 1–2 lines to README)
- **Risk**: None

## Labels

`enhancement`, `documentation`, `auto-generated`

## Session Log
- `/ll:ready-issue` - 2026-04-01T00:14:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/449aebc1-b302-4e74-a376-4bf455aa3aae.jsonl`

---

## Resolution

Added `--running`, `--builtin`, and `--status` lines to the `ll-loop list` block in README.md (lines 282–286). All three flags were verified present in `scripts/little_loops/cli/loop/__init__.py`.

## Status

**Completed** | Created: 2026-03-31 | Resolved: 2026-03-31 | Priority: P4
