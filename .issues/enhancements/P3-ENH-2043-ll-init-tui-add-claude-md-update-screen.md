---
id: ENH-2043
title: Add CLAUDE.md update step to ll-init TUI (Round 12 parity)
type: enhancement
status: done
priority: P3
discovered_date: 2026-06-09
completed_at: 2026-06-09 20:05:40+00:00
discovered_by: manual-review
parent: EPIC-1978
relates_to:
- ENH-1982
- FEAT-1980
labels:
- init
- tui
- parity
confidence_score: 92
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2043: Add CLAUDE.md update step to ll-init TUI (Round 12 parity)

## Summary

The `/ll:init` skill's interactive wizard asks (Round 12) whether to append a
`## little-loops CLI Commands` section to the project's `CLAUDE.md`. The
`ll-init` TUI (`tui.py`) has 4 screens and does not include this question.
This is the one interactive-wizard capability that the TUI doesn't cover
before ENH-1982 deletes the prose flow.

## Current Behavior

`ll-init` (interactive TUI) presents 4 screens and has no CLAUDE.md update
step. Running it skips the option to append `## little-loops CLI Commands` to
`CLAUDE.md`. The `ll-init --yes` path also skips CLAUDE.md entirely (Step 11
of the skill spec says "skip unless `--interactive`").

## Expected Behavior

`ll-init` (interactive TUI) presents a 5th screen ("5 / 5  CLAUDE.md") that
prompts whether to append the canonical `## little-loops CLI Commands` block.
`ll-init --yes` writes CLAUDE.md by default (or the decision to skip is
explicit in the code). The TUI is a complete replacement for the prose flow
before ENH-1982 deletes it.

## Motivation

The TUI was built to replace the prose-flow wizard, but it is missing one
question: the CLAUDE.md append prompt (Round 12 of the skill). This gap means
interactive users who choose `ll-init` over `ll-init --yes` cannot update
CLAUDE.md without reaching for the old skill. Adding Screen 5 makes the TUI
a complete drop-in replacement and removes the last reason to run the prose
flow before ENH-1982 deletes it.

## Proposed Solution

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

## Scope Boundaries

- **In scope**: New TUI Screen 5 for CLAUDE.md prompt; `write_claude_md`
  writer function in `writers.py`; wiring for `--yes` and `--dry-run` paths
- **Out of scope**: Modifying the `/ll:init` skill's prose-flow content or
  scheduling its deletion (owned by ENH-1982); changing the format or content
  of the `## little-loops CLI Commands` block itself

## Integration Map

### Files to Modify
- `scripts/little_loops/init/writers.py` — Add `write_claude_md(project_root, dry_run)`
- `scripts/little_loops/init/tui.py` — Add Screen 5; call `write_claude_md` from `_apply_config`
- `scripts/little_loops/init/cli.py` — Call `write_claude_md` in `_run_yes` and `_print_dry_run`

### Dependent Files (Callers/Importers)
- TBD — `grep -r "write_claude_md\|_apply_config\|_run_yes" scripts/little_loops/init/`

### Similar Patterns
- Other `write_*` functions in `writers.py` (e.g., `write_settings`) for consistency

### Tests
- `scripts/tests/` — add unit tests for `write_claude_md`: file absent (creates),
  file exists no section (appends), file exists with section (no-op)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `write_claude_md(project_root, dry_run)` to `writers.py`, matching the
   canonical block from the skill's Step 11
2. Add Screen 5 ("5 / 5  CLAUDE.md") to the TUI flow in `tui.py` with
   auto-detection of existing CLAUDE.md paths
3. Wire `write_claude_md` in `_apply_config` (TUI opt-in path)
4. Wire `write_claude_md` in `_run_yes` (default-on) and add output line in
   `_print_dry_run`
5. Write unit tests covering all three `write_claude_md` branches
6. Verify `ll-verify-skills` passes after changes

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


## Session Log
- `/ll:ready-issue` - 2026-06-09T19:50:54 - `48248cbc-4a18-4bf9-b5c3-747e24978a02.jsonl`
- `/ll:format-issue` - 2026-06-09T19:44:52 - `394f5a09-9b07-4821-bb8f-532bb814b3f9.jsonl`
- `/ll:confidence-check` - 2026-06-09T20:00:00 - `a6084b08-a511-44a0-a8ab-7018e86ad977.jsonl`
