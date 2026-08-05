---
id: ENH-3047
title: 'confidence-check: consume unverified-claim and missing-parity gaps as Criterion 4 deductions'
type: ENH
priority: P3
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: "2026-08-04T20:47:11Z"
blocked_by:
- FEAT-3048
relates_to:
- ENH-3045
- ENH-2946
- FEAT-2942
labels:
- skills
- issues
- gates
---

# ENH-3047: Feed claim/parity gaps into confidence-check scoring

## Summary

`/ll:confidence-check` scored FEAT-2942 at **93 readiness / 76 outcome** while the issue
contained a false claim about its own core write path, a silent behavior regression, two
internal contradictions, and three undefined terms. Wire the FEAT-3048 claim gaps and the
ENH-3045 parity gap into the existing Phase 1.6 pre-fetch as explicit Criterion 4 deductions, so
the score reflects what the new gates find.

## Current Behavior

Criterion 4 ("Issue Well-Specified") checks for the **presence** of sections — acceptance
criteria, specific files to modify, scope boundaries, actionable steps
(`skills/confidence-check/SKILL.md` Phase 2). FEAT-2942 has all four, so it scores well
regardless of whether those sections are *correct*, *consistent*, or *sufficient*.

Criterion 3's detection bullet 5 is the one instruction that reaches correctness — *"Verify
claims in the issue against actual code"* — but it is the last sub-bullet of a type-specific
criterion with no CLI behind it, and it is the only prose-only gate in a skill where every other
check has one. Phase 1.6 already pre-fetches the Program Design gate, so the mechanism and the
slot both exist; there is simply nothing to fetch for claims or parity yet.

## Expected Behavior

Phase 1.6 additionally pre-fetches, via `ll-issues format-check --format json`:

- unverified-claim count (`stale_symbol_ref` + `stale_cli_flag` from FEAT-3048)
- missing behavior parity (`missing_behavior_parity` from ENH-3045, if that gap kind lands)

`skills/confidence-check/rubric.md` gains explicit Criterion 4 deductions keyed to those counts,
and the Phase 3 recommendation treats a nonzero unverified-claim count as a readiness blocker
rather than a soft signal — a false claim about the implementation surface is not a "well
specified" issue at any score.

## Motivation

Without this, FEAT-3048 and ENH-3045 improve the *gates* while the *score* stays uncalibrated —
and the score is what `/ll:go-no-go`, `ll-auto`, and sprint selection actually consume. An issue
that fails a claim check should not read as 93% ready.

## Proposed Solution

Follow the existing Phase 1.6 pattern: one `format-check --format json` call, parsed into
counts, referenced by the rubric tables. `ENH-2946` already established that confidence-check
reads `format-check` output, so this is an extension of a live integration rather than a new
coupling.

Keep the deduction table in `rubric.md` (the skill already delegates all scoring tables there),
not in `SKILL.md` — that file is 405 lines against the 500-line cap.

**Dependency:** hard-blocked on FEAT-3048, which produces the gap kinds this issue consumes;
without it there is nothing to read. Soft on ENH-3045 — the parity deduction is additive and
this can ship with claim deductions alone if parity detection lands later or not at all.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 1.6 pre-fetch, Phase 3 recommendation
- `skills/confidence-check/rubric.md` — Criterion 4 deduction table
- `scripts/tests/` — scoring assertions for the deduction path

### Similar Patterns
- `ENH-2852` / `ENH-2967` — Program Design gate pre-fetch and its `check-design` CLI owner;
  the exact shape to copy
- `ENH-2946` — confidence-check already consuming `format-check` output

## Implementation Steps

1. Extend Phase 1.6 pre-fetch to parse the new gap kinds.
2. Add Criterion 4 deduction rows to `rubric.md`.
3. Make a nonzero unverified-claim count a Phase 3 readiness blocker.
4. Validate against FEAT-2942: score drops materially from 93.

## Impact

- **Priority**: P3 — depends on FEAT-3048; without it, no signal to consume
- **Effort**: Low — prompt/rubric wiring on an existing pre-fetch
- **Risk**: Low — scoring change only; may re-score existing issues downward (intended)

## Related Key Documentation

- `.claude/CLAUDE.md` — confidence gate thresholds in `.ll/ll-config.json`
  (`commands.confidence_gate`: readiness 85, outcome 65)
- `docs/reference/COMMANDS.md` — `/ll:confidence-check`

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:09 - `b9710cb8-1d2b-4d04-8cf1-ad93d3cfccb7.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:28 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
