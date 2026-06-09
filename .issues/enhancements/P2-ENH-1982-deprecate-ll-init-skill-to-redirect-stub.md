---
id: ENH-1982
title: Deprecate /ll:init skill to a redirect stub
type: enhancement
status: open
priority: P2
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1978
blocked_by:
- BUG-2042
relates_to:
- EPIC-1978
- FEAT-1979
- FEAT-1980
- FEAT-1981
- ENH-2043
labels:
- init
- cleanup
- skill
confidence_score: 92
outcome_confidence: 68
score_complexity: 17
score_test_coverage: 15
score_ambiguity: 16
score_change_surface: 20
decision_needed: false
---

# ENH-1982: Deprecate /ll:init skill to a redirect stub

## Summary

Once `ll-init` (FEAT-1979/1980/1981) reaches parity, collapse the ~1,250-line
`/ll:init` skill into a thin redirect stub and delete the prose wizard. This
removes the parallel implementation so there is one source of truth for init.

## Motivation

EPIC-1978's whole point is that init logic should live once, in Python.
Leaving the prose skill in place would guarantee drift between it and
`ll-init`. The user's decision (2026-06-05) is to **deprecate the skill
entirely** rather than convert it to a `--plan`/`apply` wrapper — the
in-session interactive path needs a real PTY the host `!`-prefix can't reliably
provide, and first-run almost always happens in a terminal where `ll-init` runs
natively.

## What to Build

Replace `skills/init/SKILL.md` body with a short stub that, when invoked
in-session as `/ll:init`:

1. Detects whether stdin is interactive. It generally is not (the skill runs
   inside the host), so:
2. **Decision resolved**: the stub will auto-run `ll-init --yes` (non-interactive
   defaults). Rationale: the config it produces is safe to write unprompted
   (same output as `--yes` always was), and auto-run is friendlier than forcing
   the user to switch terminals. The stub should print a one-line banner before
   running: "Guided init moved to CLI — running `ll-init --yes` with detected
   defaults…" so the handoff is visible.
3. Passes through recognized flags (`--force`, `--dry-run`, `--codex`/`--hosts`)
   to `ll-init` so existing muscle-memory invocations keep working.

Cleanup:
- Delete `skills/init/interactive.md` (925 lines).
- Reduce `skills/init/templates.md` to only what the stub still needs (or
  remove if fully owned by the Python core).
- Update the skill description/frontmatter to reflect the redirect role.

## Acceptance Criteria

- `skills/init/SKILL.md` is a short stub (target < 60 lines) with no
  duplicated procedure.
- `interactive.md` removed; `ll-verify-skills` (≤ 500 lines) trivially passes.
- `/ll:init` in-session still does something correct and non-confusing
  (either writes a default config or cleanly redirects).
- Recognized flags pass through to `ll-init`.
- README / `.claude/CLAUDE.md` / HOST_COMPATIBILITY reflect `ll-init` as the
  canonical init path.
- No remaining doc points users at the old multi-round wizard.

## Dependencies

- **Blocked by** BUG-2042 — three parity gaps in `ll-init` (`deploy_design_tokens`
  not called, `history.session_digest` missing from generated config,
  `Skill(ll:explore-api)` permission not wired for learning-tests). Fix BUG-2042
  before deleting the prose wizard.
- FEAT-1979, FEAT-1980, FEAT-1981 are all `done` — dependency unblocked.
- ENH-2043 (TUI CLAUDE.md screen) is P3 and can follow in a separate PR;
  it does not block this stub.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — collapse to stub.
- `.claude/CLAUDE.md`, `README.md`, `docs/reference/HOST_COMPATIBILITY.md` —
  point at `ll-init`.

### Files to Delete
- `skills/init/interactive.md`.
- `skills/init/templates.md` (if fully absorbed by the Python core).

## Impact

- **Priority**: P2 — completes the epic; without it the drift risk remains.
- **Effort**: Small.
- **Risk**: Low — gated behind parity; pure deletion + redirect.
- **Breaking Change**: Soft — `/ll:init` no longer runs the in-session wizard;
  produced config is unchanged.

## Labels

`init`, `cleanup`, `skill`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-08_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **Open decision requires resolution before starting**: Whether `/ll:init` should auto-invoke `ll-init --yes` or print a redirect message is left for implementation time. This is a user-facing behavior choice — resolve before implementing the stub body to avoid rewriting it mid-PR.
- **Wiring tests will regress on doc updates**: `scripts/tests/test_wiring_reference_docs.py` (lines 101–102) asserts `/ll:init` appears in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` and `docs/reference/CONFIGURATION.md`. When those references are updated to `ll-init`, the test fixture list must be updated in the same commit or the test suite will fail.
- **No direct unit tests for skill file content**: The stub in `skills/init/SKILL.md` has no automated tests — correctness relies entirely on the acceptance criteria (manual verification that flags pass through, redirect is non-confusing).

## Verification Notes

**Verdict: BLOCKED** — 2026-06-09. FEAT-1979/1980/1981 are all `done`; `ll-init`
is functional. Three parity gaps remain (BUG-2042): `deploy_design_tokens` not
called, `history.session_digest` absent from generated config, and
`Skill(ll:explore-api)` permission not wired for learning-tests. The redirect
behavior decision (auto-invoke vs. message only) is now resolved: auto-run
`ll-init --yes` with a one-line handoff banner. Ready to implement once BUG-2042
is fixed.

## Session Log
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f4b8008-562a-49e0-b070-2b75fe480d05.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
