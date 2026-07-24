---
id: BUG-2753
title: README overstates OpenCode/Pi host adapter support
type: BUG
priority: P3
status: done
discovered_date: 2026-07-23
discovered_by: audit-docs
testable: false
completed_at: '2026-07-24T03:37:25Z'
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

## Steps to Reproduce

1. Read README.md:37 and README.md:77.
2. Run `ll-init --hosts opencode` or `ll-init --hosts pi`.
3. Observe the dispatch in `scripts/little_loops/init/cli.py:107,109` prints
   "Adapter not yet available" for both hosts and installs nothing, contradicting
   the README's parity claim.

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

## Impact

- **Severity**: Low (P3, docs-only — no runtime behavior affected)
- **Effort**: Low (README wording change, two locations)
- Misleads readers into attempting `ll-init --hosts opencode`/`--hosts pi`
  expecting the same result as `--hosts codex`, then hitting a no-op.

## Status

**Open** | Created: 2026-07-23 | Priority: P3

## Source

Found by `/ll:audit-docs readme` (2026-07-23).

## Resolution

Reworded both README.md locations to distinguish adapter support accurately:

- README.md:37 — "Built for Claude Code, with a host adapter for Codex;
  OpenCode and Pi adapters are not yet available."
- README.md:77 — replaced "OpenCode and Pi wire up the same way via
  `ll-init --hosts`" with "OpenCode and Pi adapters aren't wired yet —
  `ll-init --hosts opencode`/`--hosts pi` currently install nothing."

Confirmed via `ll-issues show EPIC-1622 --json` that the Pi-adapter epic is
`status: cancelled`, consistent with treating Pi as unplanned rather than
"not yet". `python -m pytest scripts/tests/` run: 1 pre-existing failure
(`test_string_present_in_doc[README.md-39 typed CLI tools-FEAT-1045]`,
stale CLI-tool-count drift unrelated to this change — reproduced identically
on main via `git stash`) plus 16094 passed / 38 skipped.

## Session Log
- `/ll:ready-issue` - 2026-07-24T03:33:37 - `5a267494-050c-42e9-a453-847716adcf1f.jsonl`
- `/ll:verify-issues` - 2026-07-24T03:31:20 - `830776b6-8e8e-4688-bb99-ecd84751534a.jsonl`
- `/ll:confidence-check` - 2026-07-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d9178da1-6fdf-41d0-81ae-1fb0156b305f.jsonl`
- `/ll:manage-issue` - 2026-07-24T03:36:51 - `c59452f9-24f4-4451-997f-f04c4488102a.jsonl`
