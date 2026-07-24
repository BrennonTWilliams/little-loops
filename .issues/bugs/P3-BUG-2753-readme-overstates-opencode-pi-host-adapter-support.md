---
id: BUG-2753
title: README overstates OpenCode/Pi host adapter support
type: BUG
priority: P3
status: open
discovered_date: 2026-07-23
discovered_by: audit-docs
testable: false
confidence_score: 98
outcome_confidence: 96
score_complexity: 25
score_test_coverage: 21
score_ambiguity: 25
score_change_surface: 25
---

README.md claims parity across three hosts that don't actually have parity.
`ll-init`'s host dispatch (`scripts/little_loops/init/cli.py:107,109`) prints
`"[OpenCode] Adapter not yet available — opencode orchestration not yet
wired."` and `"[Pi] Adapter not yet available — tracked in EPIC-1622."` for
those two hosts — only Codex has a real, wired adapter. Notably, `EPIC-1622
(Pi adapter — remaining work)` is itself `status: cancelled`, so the Pi claim
isn't just premature, it points at work that will not land.

## Current Behavior

- README.md:37 — "Built for Claude Code, with host adapters for Codex,
  OpenCode, and Pi."
- README.md:77 — "OpenCode and Pi wire up the same way via `ll-init --hosts`."

Both statements read as though OpenCode and Pi are supported today via the
same mechanism as Codex. Running `ll-init --hosts opencode` or `--hosts pi`
instead prints a "not yet available" message and installs nothing.

## Expected Behavior

README should describe adapter support accurately — e.g. distinguish
"Codex: fully wired" from "OpenCode/Pi: planned/not yet available" — so a
reader doesn't attempt an unsupported `--hosts` value expecting it to work.

## Acceptance Criteria

- [ ] README.md:37 no longer implies OpenCode and Pi have working adapters
      equivalent to Codex's.
- [ ] README.md:77 no longer claims "OpenCode and Pi wire up the same way";
      either removed or replaced with accurate status.
- [ ] Wording decision accounts for EPIC-1622 being cancelled (Pi adapter is
      not just "not yet" but currently unplanned).

## Source

Found by `/ll:audit-docs readme` (2026-07-23).

## Session Log
- `/ll:verify-issues` - 2026-07-24T03:31:20 - `830776b6-8e8e-4688-bb99-ecd84751534a.jsonl`
- `/ll:confidence-check` - 2026-07-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d9178da1-6fdf-41d0-81ae-1fb0156b305f.jsonl`
