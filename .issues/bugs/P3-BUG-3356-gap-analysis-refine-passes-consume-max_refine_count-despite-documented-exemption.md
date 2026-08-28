---
id: BUG-3356
type: BUG
title: gap-analysis refine passes consume max_refine_count despite documented exemption
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T23:26:59Z'
---

# BUG-3356: gap-analysis refine passes consume max_refine_count despite documented exemption

## Summary

`--gap-analysis` refine passes consume the `commands.max_refine_count` lifetime budget, contradicting three places that document them as exempt.

## Current Behavior

`refine_count` (read by `ll-issues refine-status --json`, `scripts/little_loops/cli/issues/refine_status.py`) is a raw occurrence count of `/ll:refine-issue` lines in `## Session Log` (`session_log.py` / `issue_parser.py` `session_command_counts`). `ll-issues append-log` (`cli/issues/append_log.py`) takes no mode discriminator, and `commands/refine-issue.md` appends the Session Log entry unconditionally — including on `--gap-analysis` runs (its own text says "Still append the Session Log entry").

Consequence: `refine-to-ready-issue.yaml`'s `refine_followup` state (`--auto --gap-analysis`) silently burns lifetime budget, and `check_lifetime_limit` decomposes issues earlier than the documented contract allows.

## Expected Behavior

Contradicted documentation (all three claim the exemption):
- `scripts/little_loops/config-schema.json` `commands.max_refine_count` description: "Gap-analysis runs (`--gap-analysis` flag) are exempt from this cap"
- `commands/refine-issue.md` (cap discussion)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` `refine_followup` comment (now corrected to note the bug)

Either implement the exemption (e.g. append a mode-discriminated Session Log entry like `/ll:refine-issue --gap-analysis` and have `session_command_counts` / `refine-status` count only non-gap entries toward `refine_count`) or drop the exemption claim from all three documents. Implementing the discriminator is preferred: the gap-analysis pass is additive-only and was deliberately designed not to consume budget (ENH-2247).

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Discovered

2026-08-28 review/refactor of `refine-to-ready-issue.yaml` (loop-side comment updated in the same pass; this issue tracks the CLI/command-side fix).

## Status

**Open** | Created: 2026-08-28 | Priority: P3
