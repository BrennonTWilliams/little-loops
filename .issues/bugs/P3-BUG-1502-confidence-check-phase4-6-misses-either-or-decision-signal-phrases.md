---
id: BUG-1502
type: BUG
priority: P3
status: done
captured_at: '2026-05-16T15:05:57Z'
completed_at: '2026-05-17T05:24:40Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
decision_needed: false
relates_to:
- BUG-1278
- BUG-1294
labels:
- captured
- confidence-check
- decision-needed
- signal-phrases
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1502: `confidence-check` Phase 4.6 misses "either/or" and "resolve before starting" decision signal phrases

## Summary

Phase 4.6 of `/ll:confidence-check` (`skills/confidence-check/SKILL.md:520-534`) scans Outcome Risk Factors for four signal phrases — `"open decision"`, `"unresolved decision"`, `"resolve before implementing"`, `"decision point"` — and sets `decision_needed: true` when any match. The skill itself, however, regularly produces semantically equivalent phrasings that don't match this list (e.g., `"open 'either/or'"`, `"resolve before starting"`, `"open question"`), so unresolved decisions remain undetected in frontmatter even when the prose explicitly flags them.

## Current Behavior

Observed on FEAT-1496 (`.issues/features/P4-FEAT-1496-host-capability-preflight-check.md:286-288`). Phase 4.5 wrote this Outcome Risk Factor:

> `config-schema.json` strategy (step 14) is an open 'either/or' — resolve before starting so AC#1 implementation in `doctor.py` is unambiguous.

This is a textbook unresolved design decision — Phase 4.6's intent — but it uses `"open 'either/or'"` and `"resolve before starting"` rather than `"open decision"` / `"resolve before implementing"`. Phase 4.6's exact-substring scan misses both, leaves `decision_needed: false` (line 24 of the issue file), and the autodev FSM (`scripts/little_loops/loops/autodev.yaml`) routes through `check_decision_after_refine` → `triage_outcome_failure` → `check_decision_before_size_review` — all of which read `decision_needed` — and finds the flag absent at every checkpoint. Result: `/ll:issue-size-review` runs in place of `/ll:decide-issue`, attempting to decompose an issue whose primary outcome blocker is a single unresolved design choice.

## Expected Behavior

Phase 4.6 detects all phrasings the skill naturally emits for unresolved decisions and sets `decision_needed: true` whenever Phase 4.5's risk-factor prose flags a pre-implementation decision — regardless of which equivalent phrasing was chosen.

Signal phrases to add (each observed in skill output or already documented elsewhere in the same skill):

- `"either/or"` / `"either…or"` (Phase 3 already lists `"either...or"` as an ambiguity indicator at `skills/confidence-check/SKILL.md:375`)
- `"resolve before starting"` (semantic equivalent of `"resolve before implementing"`)
- `"open question"` (also already listed at `skills/confidence-check/SKILL.md:375`)
- `"Option A/B"` / `"Option A or"` without resolution (also at `skills/confidence-check/SKILL.md:375`)

## Steps to Reproduce

1. Create or locate an issue whose outcome confidence is below threshold with the dominant blocker being a single design decision.
2. Run `/ll:confidence-check <ID>` and observe Phase 4.5 emits an Outcome Risk Factor using `"open 'either/or'"` or `"resolve before starting"` (the skill's natural vocabulary).
3. Read the issue's frontmatter — `decision_needed` is still `false`.
4. Run `ll-loop run autodev "<ID>"` — observe the loop routes to `run_size_review`, not `run_decide`.

Real-world reproduction: FEAT-1496 on 2026-05-16 — autodev ran `/ll:issue-size-review` instead of `/ll:decide-issue` despite the risk-factor prose flagging an unresolved config-schema decision.

## Root Cause

**File**: `skills/confidence-check/SKILL.md`
**Phase**: 4.6 (`Decision-Needed Flag`), lines 520-534

The signal-phrase list at lines 522-526 was scoped to four exact substrings when BUG-1278 introduced Phase 4.6. The list does not cover the full vocabulary the skill emits — Phase 3's own ambiguity-indicator list at line 375 (`"either...or"`, `"open question"`, `"Option A/B"`) and natural variants like `"resolve before starting"` were not propagated forward. Exact-substring matching plus a narrow vocabulary creates false-negative escapes whenever the LLM picks an equivalent phrasing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing wider vocabulary in same skill**: `skills/confidence-check/SKILL.md:375` already documents `"TBD"`, `"TODO"`, `"open question"`, `"decide"`, `"either...or"`, `"Option A/B"` as ambiguity indicators for Phase 3 (input scan). Phase 4.6 (output scan) should reuse this list — the asymmetry is the bug.
- **Phase 4.6 mechanism is sound** — see BUG-1278 (`P3-BUG-1278-confidence-check-does-not-set-decision-needed-flag.md`, status: done) for the design rationale of the post-prose scan, idempotency guard, and CHECK_MODE guard. This bug only extends the signal-phrase set; no architectural change.
- **Exact signal phrase block confirmed at lines 522–526**: `skills/confidence-check/SKILL.md:522-526` — four bullet literals under `**Signal phrases** (any match triggers the flag):`; format is `- "quoted phrase"`, one per line. New phrases slot in as additional bullets.
- **Criterion C vocabulary confirmed at line 375**: `skills/confidence-check/SKILL.md:375` — `"TBD"`, `"TODO"`, `"open question"`, `"decide"`, `"either...or"`, `"Option A/B"` are listed as a single comma-separated detection-method sentence; no de-duplication work needed between sections.
- **Partial bypass in `triage_outcome_failure`**: `scripts/little_loops/loops/autodev.yaml` (lines ~415–429) also gates on `score_ambiguity <= 10` as a numeric proxy — so that one autodev path can still route to `run_decide` even if `decision_needed` is `false`. However, `check_decision_after_refine` (lines ~122–130) and `check_decision_before_size_review` (lines ~406–413) rely **solely** on the frontmatter flag with no numeric fallback — meaning those two gate states always misroute when the signal phrases are missed.
- **`decision_needed` serialization path**: `scripts/little_loops/cli/issues/show.py:248-250` serializes the YAML boolean `true` to JSON string `"true"` for `ll-issues show --json` output; autodev compares against the string `'true'`. No changes needed here — the fix only affects what Phase 4.6 writes.

## Proposed Solution

Extend the Phase 4.6 signal-phrase list at `skills/confidence-check/SKILL.md:522-526` to include the broader vocabulary already documented at line 375:

- `"either/or"` (covers `"open 'either/or'"`, `"an either/or"`)
- `"either...or"` / `"either…or"`
- `"resolve before starting"` (covers natural synonym of `"resolve before implementing"`)
- `"open question"`
- `"Option A or Option B"` / `"Option A/B"` without resolution

Apply the same matching rules: case-insensitive substring match against Phase 4.5's just-written Outcome Risk Factors content. Preserve existing guards (idempotency, CHECK_MODE skip).

Optionally consolidate by extracting the ambiguity-indicator list into a single bulleted block that Phase 3 (input scan) and Phase 4.6 (output scan) both reference — eliminating future drift.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md:522-526` — extend signal-phrase bullets

### Dependent Files (Consumers of `decision_needed`)
- `scripts/little_loops/loops/autodev.yaml` — `check_decision_after_refine`, `triage_outcome_failure`, `check_decision_before_size_review`, `decide_current` all gate on `decision_needed == 'true'`
- `skills/manage-issue/SKILL.md` — Phase 2.3 Decision Gate
- `skills/wire-issue/SKILL.md` — advisory warning
- `scripts/little_loops/issue_parser.py` — parses `decision_needed` from frontmatter (no changes needed)
- `scripts/little_loops/cli/issues/show.py:248-250` — serializes YAML boolean `true` → JSON string `"true"` for `ll-issues show --json` (no changes needed; autodev reads this output)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_decision_needed` state (line ~265) gates via `ll-issues check-flag`; routes to `done` when true to preserve signal for outer loop (no changes needed)
- `scripts/little_loops/loops/recursive-refine.yaml` — `check_decision_needed` state (line ~448) reads frontmatter directly; skips size-review when flag is true (no changes needed)
- `scripts/little_loops/issue_manager.py:719-723` — Decision gate invokes `/ll:decide-issue` when `issue.decision_needed is True` (no changes needed)
- `scripts/little_loops/parallel/worker_pool.py:378` — Decision gate invokes decide command when `issue.decision_needed is True` (no changes needed)
- `skills/decide-issue/SKILL.md` — Phases 3b and 7b read `decision_needed` and set it to `false` after deciding (no changes needed)
- `scripts/little_loops/cli/issues/check_flag.py` — `ll-issues check-flag <ID> decision_needed` CLI; used by FSM loops to read the boolean (no changes needed)
- `skills/issue-workflow/SKILL.md` — references decide-issue invocation when `decision_needed: true` (no changes needed)

_No changes needed in dependents — only the detection set widens._

### Tests
- `scripts/tests/test_confidence_check_skill.py` — extend the existing Phase 4.6 structural test (added in BUG-1278) to assert each new signal phrase is present in the phase text

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:255` — The `### /ll:confidence-check` section's `**decision_needed` write-back**` paragraph contains a hard-coded parenthetical: `("open decision", "unresolved decision", "resolve before implementing", "decision point")`. After this fix the parenthetical will be a stale subset; update it to include the new phrases or rewrite as representative examples. This is the only doc file that enumerates the exact phrase list verbatim.
- If the optional consolidation (referencing Phase 3 vocabulary from Phase 4.6) is chosen, update the Phase 3 cross-reference at `skills/confidence-check/SKILL.md:375`.

## Acceptance Criteria

- [ ] Phase 4.6 sets `decision_needed: true` when Outcome Risk Factors contain `"either/or"`, `"either...or"`, `"resolve before starting"`, `"open question"`, or `"Option A/B"` (in addition to the four existing phrases)
- [ ] Retrospective test: re-running `/ll:confidence-check` on FEAT-1496 sets `decision_needed: true`
- [ ] Phase 4.6 idempotency and CHECK_MODE guards are preserved
- [ ] Structural test in `test_confidence_check_skill.py` asserts each new signal phrase is documented in Phase 4.6 text

## Motivation

Detection-set coverage gaps in Phase 4.6 cause silent FSM mis-routing in autodev: when a single unresolved decision is the outcome blocker but the skill's own prose chose synonym phrasing, the FSM runs size-review (which can't resolve the decision) instead of decide-issue (which can). The issue's outcome confidence stays below threshold across iterations, decomposition runs unnecessarily, or the issue is skipped — all because of vocabulary asymmetry inside one skill.

## Implementation Steps

1. Open `skills/confidence-check/SKILL.md` and locate the Phase 4.6 signal-phrase bullet list (lines 522-526).
2. Add the five new phrases as additional bullets, preserving the existing four.
3. (Optional) Add a brief inline note referencing Phase 3's ambiguity indicators at line 375 for traceability.
4. Update `scripts/tests/test_confidence_check_skill.py` — extend `TestDecisionNeededFlagWriteBack.test_signal_phrases_documented` (line 109) to assert new phrases. Current assertion is `"open decision" in text or "unresolved decision" in text`; extend the `or`-chain to include `"either/or"` and `"resolve before starting"` following the same pattern used for Phases 4.7–4.9 (lines 152–153, 202–203).
5. Run `python -m pytest scripts/tests/test_confidence_check_skill.py -v` and `ruff check scripts/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/COMMANDS.md:255` — revise the `**decision_needed` write-back**` parenthetical in the `### /ll:confidence-check` section to include the new signal phrases (or replace with representative examples). The current text `("open decision", "unresolved decision", "resolve before implementing", "decision point")` will be a stale subset after step 2.

## Impact

- **Priority**: P3 — silent mis-routing in autodev; manual workaround (user re-runs after manually setting `decision_needed: true` or running `/ll:decide-issue` directly).
- **Effort**: Trivial — bullet-list extension in a single file plus one test update.
- **Risk**: Low — broadens an existing detection set; preserves all guards; no architectural change.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `skills/confidence-check/SKILL.md` | Phase 4.6 lives here; Phase 3 already documents the wider vocabulary |
| `scripts/little_loops/loops/autodev.yaml` | Downstream consumer of `decision_needed` flag — three gate states |

## Labels

`bug`, `confidence-check`, `decision-needed`, `signal-phrases`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-17T05:23:47 - `e3739429-a254-4809-8c56-81eb569dba7a.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `5bd0252f-eb36-4d40-844f-1ba82253318b.jsonl`
- `/ll:wire-issue` - 2026-05-17T05:19:48 - `0aea8500-1a0e-469e-8b08-e2ac6cbc305c.jsonl`
- `/ll:refine-issue` - 2026-05-17T05:15:07 - `0f7f83fc-e3c9-4852-a03a-c2b11669e9bc.jsonl`
- `/ll:format-issue` - 2026-05-16T15:12:33 - `5c24f73c-ba02-48c1-b2ce-dc8f94ab89b0.jsonl`
- `/ll:format-issue` - 2026-05-16T15:07:44 - `5c24f73c-ba02-48c1-b2ce-dc8f94ab89b0.jsonl`
- `/ll:capture-issue` - 2026-05-16T15:05:57Z
