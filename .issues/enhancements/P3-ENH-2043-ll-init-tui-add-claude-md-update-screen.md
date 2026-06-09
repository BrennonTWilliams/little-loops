---
id: ENH-2043
title: Add CLAUDE.md update step to ll-init TUI (Round 12 parity)
type: enhancement
status: open
priority: P3
discovered_date: 2026-06-09
discovered_by: manual-review
parent: EPIC-1978
relates_to:
- ENH-1982
- FEAT-1980
labels:
- init
- tui
- parity
---

# ENH-2043: Add CLAUDE.md update step to ll-init TUI (Round 12 parity)

## Summary

The `/ll:init` skill's interactive wizard asks (Round 12) whether to append a
`## little-loops CLI Commands` section to the project's `CLAUDE.md`. The
`ll-init` TUI (`tui.py`) has 4 screens and does not include this question.
This is the one interactive-wizard capability that the TUI doesn't cover
before ENH-1982 deletes the prose flow.

## Background

The skill's `--yes` path also skips CLAUDE.md (Step 11 says "skip unless
`--interactive`"), so this gap only affects interactive users who run `ll-init`
without `--yes`. Still, adding it makes the TUI a complete replacement and
removes a reason for anyone to reach for the old skill.

## What to Build

1. Add a 5th screen to the TUI ("5 / 5  CLAUDE.md") after the settings-target
   prompt. Ask:

   ```
   Append ll- CLI commands to CLAUDE.md?
   ▸ Yes, append to existing  /  Yes, create .claude/CLAUDE.md  /  Skip
   ```

   Auto-detect whether `.claude/CLAUDE.md` or `CLAUDE.md` exist and pre-select
   the appropriate option (mirror the skill's Round 12 detection logic).
   If a `## little-loops` section already exists, skip the question and note it.

2. Add a `write_claude_md` writer function to `writers.py` that:
   - Appends the canonical `## little-loops CLI Commands` block (same text as
     the skill's Step 11) if the file exists and the section is absent.
   - Creates `.claude/CLAUDE.md` (with a `# Project Configuration` header) if no
     file exists.
   - Is a no-op if the section is already present (idempotency).

3. Call `write_claude_md` from `_apply_config` (`tui.py`) when the user opts in.

4. Wire the same function for `ll-init --yes`:
   Since `--yes` currently skips CLAUDE.md entirely, decide whether to include
   it as a default-on step or keep it opt-in-only. Recommend: default-on for
   `--yes` (the user expects full setup), matching how `merge_settings` runs
   unconditionally.

## Files to Change

| File | Change |
|------|--------|
| `scripts/little_loops/init/writers.py` | Add `write_claude_md(project_root, dry_run)` |
| `scripts/little_loops/init/tui.py` | Add Screen 5; call `write_claude_md` from `_apply_config` |
| `scripts/little_loops/init/cli.py` | Optionally call `write_claude_md` in `_run_yes` and `_print_dry_run` |

## Acceptance Criteria

- Running `ll-init` (interactive) presents a CLAUDE.md prompt on Screen 5.
- On opt-in, `write_claude_md` appends the canonical block if absent; skips if
  already present.
- `ll-init --yes` writes CLAUDE.md (or decision is explicit about skipping it).
- `ll-init --yes --dry-run` lists `[write/update] .claude/CLAUDE.md` in output.
- `ll-verify-skills` still passes after changes.
- Unit tests cover: file absent (creates), file exists no section (appends),
  file exists with section (no-op).

## Impact

- **Priority**: P3 — nice-to-have TUI completeness; doesn't block ENH-1982.
- **Effort**: Small-medium (one new writer, one new TUI screen, wiring).
- **Risk**: Low — isolated to new writer function and an optional TUI screen.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-09 | Priority: P3
