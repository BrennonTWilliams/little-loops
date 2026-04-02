---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# ENH-923: Enhance `ll-sprint show` Detail and Output Quality

## Summary

Improve the `ll-sprint show` command with richer detail and better output formatting: add a readiness/confidence table per issue, omit empty descriptions, use human-friendly timestamps, show sprint composition breakdown, surface sprint run state from `.sprint-state.json`, use lighter visual separators, widen title truncation, add a `--json` flag, and display file paths for each issue.

## Current Behavior

`ll-sprint show` displays sprint metadata, an execution plan, and issue lists, but:

- Shows `Description: (none)` for empty descriptions, adding noise.
- Uses microsecond-precision ISO 8601 timestamps (e.g., `2026-04-02T19:49:32.123456`) which are hard to scan.
- Does not show readiness or outcome confidence scores per issue.
- No composition breakdown (type/priority distribution).
- Does not surface previous run state even when `.sprint-state.json` exists.
- Uses heavy full-width `===` banners as section separators.
- Truncates titles at ~45 characters, clipping useful context.
- No `--json` output flag (unlike `ll-sprint list`).
- Does not show the file path for each issue.

## Expected Behavior

1. **Issue table with scores** — Each issue in the execution plan shows readiness and outcome confidence scores, styled consistently with `ll-issues list` output.
2. **Omit empty description** — Only render `Description:` when a value exists.
3. **Human-friendly timestamps** — `Created: 2026-04-02 19:49 UTC (today)` or relative like `2h ago`.
4. **Composition line** — After health summary: `Composition: 4 ENH  |  P3: 2, P4: 2`
5. **Sprint run state** — If `.sprint-state.json` exists, show: `Last run: 2026-04-01 — 3/4 completed, 1 failed (ENH-921)`
6. **Lighter separators** — Replace `===` banners with: `── Execution Plan (4 issues, 1 wave) ──────────────────`
7. **Wider title truncation** — Bump to ~60 chars or calculate dynamically from terminal width minus fixed-width prefix/suffix.
8. **`--json` flag** — Structured JSON output for scripting, matching the pattern from `ll-sprint list --json`.
9. **Issue file paths** — Show file path below each issue entry:
   ```
   ├── ENH-919: Wire EventBus Emission into Issue Lifecycle (P3)
   │   .issues/enhancements/P3-ENH-919-wire-eventbus-issue-lifecycle.md
   ```

## Motivation

`ll-sprint show` is the single entry point for understanding a sprint's full status. Currently it requires users to cross-reference multiple commands to get readiness scores, run history, or file locations. Consolidating this information and aligning the visual style with other `ll-` CLI commands makes sprint review faster and reduces context-switching.

## Proposed Solution

TBD - requires investigation. Key areas to modify:

- `scripts/little_loops/cli/sprint.py` — `_render_execution_plan()` and `show` subcommand handler
- Reuse styled output helpers from `ll-issues list` (color utilities, table formatting)
- Read `.sprint-state.json` for run state display
- Add `--json` argument to the `show` subparser
- Use `shutil.get_terminal_size()` for dynamic title width

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — main rendering logic

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- `scripts/little_loops/cli/issues.py` — `ll-issues list` output styling to match

### Tests
- `scripts/tests/test_sprint.py` — add/update tests for new output features

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Audit current `_render_execution_plan()` and `show` handler in `sprint.py`
2. Refactor separator rendering to use lighter `──` style
3. Add readiness/confidence score display per issue and composition breakdown
4. Implement human-friendly timestamp formatting (reuse or create utility)
5. Add `.sprint-state.json` run state reading and display
6. Implement dynamic title truncation based on terminal width
7. Add `--json` flag with structured output
8. Add issue file path display
9. Update tests for all new output features

## Success Metrics

- All 9 improvements are visible in `ll-sprint show` output
- `--json` flag produces valid JSON matching the displayed information
- Existing `test_sprint.py` tests pass without regression
- New tests cover each added feature

## Scope Boundaries

- Does not change `ll-sprint list` output (already styled)
- Does not modify sprint execution logic or wave planning
- Does not add interactive features to `show`

## Impact

- **Priority**: P3 - Quality-of-life improvement for sprint review workflow
- **Effort**: Medium - 9 discrete changes to rendering logic, but mostly additive
- **Risk**: Low - Output-only changes, no execution logic modified
- **Breaking Change**: No (additive only; `--json` is opt-in)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI module structure and output conventions |
| `docs/reference/API.md` | Sprint manager API and state file format |

## Labels

`enhancement`, `cli`, `sprint`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2d0784e-0b23-40cf-bd8f-79c2a103fa18.jsonl`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P3
