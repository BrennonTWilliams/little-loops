---
id: ENH-2159
title: Document ll-issues decisions suggest-rules and promote in DECISIONS_LOG_GUIDE.md
type: ENH
priority: P3
status: open
created: 2026-06-14
affects:
  - docs/guides/DECISIONS_LOG_GUIDE.md
relates_to:
  - ENH-2125
  - ENH-2126
---

## Problem

`docs/guides/DECISIONS_LOG_GUIDE.md` has no documentation for two `ll-issues decisions` subcommands that shipped as done (ENH-2125, ENH-2126):

- **`ll-issues decisions suggest-rules`** — surfaces decision history entries that are candidates for promotion to standing rules
- **`ll-issues decisions promote`** — converts a decision entry into a standing rule with configurable enforcement level (`--enforcement required|advisory`)

Both are listed in CHANGELOG v1.124.0 under Added, but the guide was not updated when the feature landed.

## Acceptance Criteria

- [ ] Add a new section "Promoting Decisions to Rules" (or similar) to DECISIONS_LOG_GUIDE.md covering:
  - When to promote a decision to a rule (becomes recurring guidance, not a one-off)
  - `ll-issues decisions suggest-rules` — what it outputs, how to interpret candidates
  - `ll-issues decisions promote <id> --enforcement required|advisory` — flags, effect on `.ll/decisions.yaml`, sync behavior
- [ ] Cross-link to `ll-issues decisions sync` (already documented) since promote writes rules that sync also pushes
- [ ] Verify subcommand flags against `ll-issues decisions promote --help` and `suggest-rules --help`

## Notes

ENH-2125 and ENH-2126 are both `status: done`. This is a documentation-only gap.
