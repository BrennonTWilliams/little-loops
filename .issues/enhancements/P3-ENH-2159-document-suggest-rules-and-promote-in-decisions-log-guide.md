---
id: ENH-2159
title: Document ll-issues decisions suggest-rules and promote in DECISIONS_LOG_GUIDE.md
type: ENH
priority: P3
status: done
created: 2026-06-14
completed_at: 2026-06-15 15:25:13+00:00
affects:
- docs/guides/DECISIONS_LOG_GUIDE.md
relates_to:
- ENH-2125
- ENH-2126
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
testable: false
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

## Integration Map

### Files to Modify
- `docs/guides/DECISIONS_LOG_GUIDE.md` — add new section "Promoting Decisions to Rules" with `suggest-rules` and `promote` coverage; update TOC

### Implementation Source (Reference Only)
- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_suggest_rules()` (line 528) and `_cmd_promote()` (line 875) are the source of truth for flags, output format, and auto-sync behavior
- `scripts/little_loops/decisions_sync.py` — `sync_to_local_md()` explains what `promote --enforcement required` triggers automatically

### CLI Reference (Already Updated)
- `docs/reference/CLI.md` (lines 1370–1455) — fully documents both subcommands; paraphrase, don't duplicate

### Tests (No Changes Needed)
- `scripts/tests/test_cli_decisions.py` — `TestDecisionsCLIPromote` (line 964) and `TestDecisionsCLISuggestRules` (line 1241) cover both subcommands

## Impact

- **Priority**: P3 - Documentation gap; subcommands are functional but undiscoverable via the guide
- **Effort**: Small - Single doc file, two subcommands to cover, CLI.md already has reference content to paraphrase
- **Risk**: Low - Documentation-only change, no code modifications
- **Breaking Change**: No

## Scope Boundaries

- Only `DECISIONS_LOG_GUIDE.md` is updated; `docs/reference/CLI.md` already documents both subcommands and is not modified
- No changes to CLI behavior, flags, or implementation code
- No new tests required (existing `TestDecisionsCLIPromote` and `TestDecisionsCLISuggestRules` cover the subcommands)

## Labels

`documentation`, `decisions-log`, `dx`

## Notes

ENH-2125 and ENH-2126 are both `status: done`. This is a documentation-only gap.

## Status

**Open** | Created: 2026-06-14 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-15T15:23:45 - `8dd28e01-170a-449b-a2f3-7e0c49c95852.jsonl`
- `/ll:refine-issue` - 2026-06-15T15:17:16 - `0513c30d-7b01-426f-995d-70b3df510f7f.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e66a103e-84d8-4335-be07-8b71c6a9ffd7.jsonl`
