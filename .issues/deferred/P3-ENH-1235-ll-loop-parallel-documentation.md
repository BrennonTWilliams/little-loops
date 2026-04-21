---
discovered_date: "2026-04-21"
discovered_by: planning-discussion
confidence_score: 90
size: Small
depends_on: FEAT-1232, FEAT-1233
status: deferred
deferred_date: "2026-04-21"
deferred_reason: low-value
---

# ENH-1235: Documentation for `ll-loop parallel`

## Summary

Update `LOOPS_GUIDE.md`, `loops/README.md`, and CLI `--help` text to document the `ll-loop parallel` subcommand introduced in FEAT-1232/FEAT-1233.

## Deferral Notes

Deferred alongside FEAT-1232 and FEAT-1233. Documentation has no standalone value without the feature being implemented.

## Acceptance Criteria

- [ ] `LOOPS_GUIDE.md`: new "Running Loops in Parallel" section with a minimal example (`ll-loop parallel a b`), scope conflict explanation, and note about log file locations
- [ ] `loops/README.md`: add `ll-loop parallel` to the command summary table (alongside `run`, `stop`, `info`, etc.)
- [ ] CLI `--help` (argparse): `ll-loop parallel --help` shows all flags (`--no-status`, `--status-interval`) with meaningful descriptions
- [ ] `create-loop` skill (`skills/create-loop/SKILL.md` or `reference.md`): note that users can run any set of independent loops in parallel without coordination, with a pointer to `ll-loop parallel`

## Implementation Notes

- No new doc files — only additions to existing files
- The "Running Loops in Parallel" section should come after the existing "Background Execution" section in `LOOPS_GUIDE.md`
- Keep the example short: show the command, the pre-flight conflict error UX, and the completion summary — no need to reproduce the full status table in docs
