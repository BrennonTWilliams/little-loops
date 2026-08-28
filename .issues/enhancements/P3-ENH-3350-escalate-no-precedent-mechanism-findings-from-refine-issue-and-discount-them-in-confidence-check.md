---
id: ENH-3350
type: ENH
title: Escalate no-precedent mechanism findings from refine-issue and discount them
  in confidence-check
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T01:42:06Z'
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3350: Escalate no-precedent mechanism findings from refine-issue and discount them in confidence-check

## Summary

Refine-issue findings that state a proposed remedy relies on a mechanism with no confirming precedent in the codebase are currently deposited silently and nothing downstream acts on them. On BUG-3349, the refine pass recorded exactly the warning sign ("no existing site applies :shell to a captured.* reference — no direct precedent confirming the combination works"), yet the flawed remedy survived format-issue, refine-issue, and confidence-check (outcome_confidence 84) even though its core primitive — a bare :shell binding on a capture that is always missing on one of two mutually exclusive branches — would have raised InterpolationError on every run. No skill in the chain is tasked with falsifying a proposed mechanism: refine-issue only annotates contradictions (the directive line had pre-emptively acknowledged the mutual-exclusivity fact, so no Superseded marker fired), and confidence-check takes the issue's internal reasoning at face value.

Three changes:

1. /ll:refine-issue: when a codebase research finding this pass is depositing states that a proposed mechanism has no confirming precedent (no existing usage site exercises the combination the remedy depends on), emit an explicit escalation — deposit a canonical `⚠ Unproven mechanism` inline marker next to the finding, set `unproven_mechanism: true` in frontmatter, and recommend /ll:spike in the completion report, analogous to the existing superseded-marker -> /ll:reconcile-issue recommendation path (ENH-2992 pattern).

2. /ll:confidence-check: cap outcome_confidence at `outcome_threshold − 1` when the issue carries an unsuppressed `unproven_mechanism: true` flag (suppressed by `spike_attempted`/`spike_completed`). A hard cap, not a fixed penalty: only a cap guarantees the discounted score lands below the outcome gate at any starting score, which is what makes Phase 4.5 write Outcome Risk Factors and Phase 4.6 have notes to act on at all.

3. ll-issues set-flags: when frontmatter carries `unproven_mechanism: true`, the `spike_needed` rule fires without its `score_test_coverage <= 10` numeric gate and without a phrase re-match — the flag is direct evidence, stronger than the phrase heuristic. Without this, the enforcement chain stays broken on the motivating case: BUG-3349 has `score_test_coverage: 15` (fails the numeric gate) and its finding text "no direct precedent confirming" does not substring-match any `_SPIKE_NEEDED_PHRASES` entry, so the discount alone would never light up `spike_needed` or the `check_spike_needed` loop gates.


## Current Behavior

`/ll:refine-issue` deposits codebase-research findings (including "no existing
usage site confirms this mechanism works") silently into the issue body with
no escalation. `/ll:confidence-check` takes the issue's own reasoning at face
value and computes `outcome_confidence` without checking for an unresolved
no-precedent finding. On BUG-3349 this let a remedy whose core primitive (a
bare `:shell` binding on a capture that is always missing on one of two
mutually exclusive branches) reach `outcome_confidence: 84` and survive
format-issue, refine-issue, and confidence-check, even though it would raise
`InterpolationError` on every run.

## Expected Behavior

`/ll:refine-issue` escalates a no-precedent finding explicitly: it sets
`unproven_mechanism: true` in frontmatter, deposits a canonical inline marker
(`⚠ Unproven mechanism`) next to the finding, and recommends `/ll:spike` in
its completion report, mirroring the existing superseded-marker →
`/ll:reconcile-issue` recommendation path (ENH-2992). `/ll:confidence-check`
checks that flag before scoring and caps `outcome_confidence` at
`outcome_threshold − 1` while the flag is set and unsuppressed. The cap is
suppressed when `spike_attempted` or `spike_completed` is true in frontmatter
(mirroring `_spike_not_already_flagged`, `set_flags.py:130-135`) — `/ll:spike`
already sets `spike_completed: true` on success and its SKILL.md promises that
re-running confidence-check recovers the discounted points; that frontmatter
signal, not session-log parsing, is the resolution check. `/ll:reconcile-issue`
may additionally set `unproven_mechanism: false` when it rewrites the flagged
section.

## Motivation

Without this, the confidence gate is blind to an entire class of
implementation-blocking failure: a proposed mechanism can be self-flagged as
unproven by refine-issue's own research and still clear confidence-check at a
score above the outcome threshold (BUG-3349: 84, above this project's 65
outcome gate). That lets `/ll:manage-issue` burn a full implementation cycle
on a remedy that fails on first run.

## Proposed Solution

1. Add an `unproven_mechanism: bool | None` field to `IssueInfo`
   (`issue_parser.py`), mirroring the existing `decision_needed` field's
   dataclass entry, `to_dict`/`from_dict` wiring, and frontmatter coercion.
2. Update the `/ll:refine-issue` skill: when a codebase-research finding this
   pass is depositing states that a proposed mechanism has no confirming
   precedent, deposit a `⚠ Unproven mechanism` inline marker next to the
   finding, set `unproven_mechanism: true`, and recommend `/ll:spike` in the
   completion report — the same shape as the existing
   `superseded_marker_count` (`issue_parser.py:1781`) → `/ll:reconcile-issue`
   escalation. The fixed marker makes the Step 8 gate row and skill-prose
   tests assertable (the `⚠ Superseded` precedent works because it is a
   greppable literal) and leaves room for a future `format-check` read-back
   key.
3. Update the `/ll:confidence-check` skill: read `unproven_mechanism` before
   computing `outcome_confidence`; when the flag is true and neither
   `spike_attempted` nor `spike_completed` is set, cap the score at
   `outcome_threshold − 1` (hard cap, not a fixed penalty — a penalty is
   fragile across scores/thresholds, and only a below-threshold result makes
   Phase 4.5 write Outcome Risk Factors at all).
4. Update `ll-issues set-flags` (`set_flags.py`): the `spike_needed`
   `FlagRule` fires on `unproven_mechanism: true` in frontmatter directly,
   bypassing the `score_test_coverage <= 10` numeric gate and the
   `_SPIKE_NEEDED_PHRASES` match (both of which BUG-3349's shape fails). The
   existing `_spike_not_already_flagged` suppression still applies.
5. Clearing: suppression via `spike_attempted`/`spike_completed` frontmatter
   (set by `/ll:spike`) is the primary resolution path; `/ll:reconcile-issue`
   may set `unproven_mechanism: false` when it rewrites the flagged section.
   No session-log parsing.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add `unproven_mechanism` field to `IssueInfo`
- `commands/refine-issue.md` — emit the escalation at Step 6.7 (detection bullet, lines 983-1052), Step 8 (`## PROSE/PROGRAM DESIGN GATE` row, lines 1087-1154), and the pipeline-diagram footnote (lines 1179-1197); `skills/ll-refine-issue/SKILL.md` is a 22-line bridge stub with no step numbering or gate logic and is not the real target
- `skills/confidence-check/SKILL.md` — add a Phase 1.6/1.8-style pre-fetch gate that reads the flag
- `skills/confidence-check/rubric.md` — add the outcome_confidence cap/override rows for Criteria A-D; no existing cap targets `outcome_confidence` today, only the readiness-side `Parity/Claim/Structure Cap` (rubric.md:241-259) and `Decision Cap` (rubric.md:310-327) exist as a shape to adapt
- `scripts/little_loops/cli/issues/set_flags.py` — `spike_needed` `FlagRule` gains an `unproven_mechanism: true` frontmatter trigger that bypasses the `score_test_coverage <= 10` numeric gate and the phrase match (see Proposed Solution part 4); without it the discount never reaches the loop gates on BUG-3349-shaped issues

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/show.py` — displays frontmatter fields like `decision_needed`; extend for `unproven_mechanism` for parity
- `scripts/little_loops/cli/help.py` — no change expected, verify it doesn't enumerate frontmatter fields that would need updating

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:1167` — `if info.decision_needed is True and not dry_run:` auto-invokes `/ll:decide-issue`; the direct execution-time analog of `decision_needed`'s gate. **Not to be mirrored** for `unproven_mechanism` — this issue's own Scope Boundaries state it "does not... attempt to automatically prove or disprove the flagged mechanism," so no auto-invoke-`/ll:spike` gate belongs here. Confirmed deliberately out of scope, not a missing touchpoint. [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py:593` — same "Decision gate: invoke decide-issue" pattern inside the parallel worker's pre-implementation sequence. Same out-of-scope conclusion as above. [Agent 1 finding]
- `scripts/little_loops/loops/autodev.yaml:1319` (`check_spike_needed` state, ENH-2640) — the default automation loop's gate, reading `spike_needed`/`spike_attempted` from frontmatter to route to `/ll:spike` before implementation. This is the actual enforcement mechanism this issue's Motivation section is trying to engage — but it fires only if the Part 3 discount lands in `outcome_confidence` before `set-flags` computes `spike_needed` from it (see Wiring Phase below). [gate_consumers finding, Agent 1]
- `scripts/little_loops/loops/spike-gate.yaml` (`check_spike_needed` state) — same `spike_needed`-driven gate, packaged as an opt-in wrapper loop (not on the default `autodev.yaml` path). Its enforcement is conditional on being used to wrap the impl loop. [gate_consumers finding, Agent 1]

### Similar Patterns
- Superseded-marker escalation: `superseded_marker_count()` (`issue_parser.py:1781-1807`) and the `⚠ Superseded` → `/ll:reconcile-issue` recommendation path (ENH-2992) — mirror its exact three-surface shape: a Step 6.7 detection bullet, a fixed-format Step 8 gate-table row, and a conditional `## NEXT STEPS` bullet naming the remedy command, plus the pipeline-diagram footnote
- `decision_needed` field wiring in `IssueInfo` (`issue_parser.py:3433`, `3480`, `3520`, frontmatter coercion at `3588` and `3714` via the shared `IssueParser._coerce_tristate_bool` helper at `4024-4038`) — template for adding `unproven_mechanism`
- `spike_needed` (`scripts/little_loops/cli/issues/set_flags.py`) is a near-identical existing mechanism that phrase-detects no-precedent language (`_SPIKE_NEEDED_PHRASES`, lines 67-76) but its `FlagRule` precondition (`_spike_precondition_factory`, lines 138-144) requires `outcome_confidence` to already be below the outcome threshold — structurally unable to catch BUG-3349's case (`outcome_confidence: 84`, above the 65 threshold). `unproven_mechanism` must be set during `/ll:refine-issue`'s research pass, before `outcome_confidence` is computed, not as a post-hoc low-score trigger

### Tests
- `scripts/tests/test_issue_parser.py` — round-trip test for the new `unproven_mechanism` field (dataclass, to_dict/from_dict, frontmatter coercion)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_reference_docs.py` — data-driven `(doc_path, string, issue_id)` parametrized fixture (e.g. line 28's `("docs/reference/ISSUE_TEMPLATE.md", "spike_needed", "ENH-2569")` row); add a row asserting `docs/reference/CLI.md` documents `unproven_mechanism`'s indirect gate-consumption note. [Agent 3 finding]
- `scripts/tests/test_confidence_check_skill.py` — `TestPhase45OutcomeThreshold`-style class (lines 196-230, e.g. `test_phase_4_6_guard_uses_outcome_threshold`) asserting SKILL.md prose references specific phases/thresholds; add an analogous class asserting Phase 2b computes the `unproven_mechanism` discount and Phase 4 persists it before Phase 4.6's `set-flags` call. [Agent 3 finding]
- `scripts/tests/test_set_flags_cli.py` — existing `FlagRule`/`spike_needed` precondition tests; add a case confirming `spike_needed` fires on a **faithful** BUG-3349-shaped fixture: `unproven_mechanism: true`, discounted `outcome_confidence` below threshold, `score_test_coverage: 15` (above the numeric gate), and notes text ("no direct precedent confirming...") that matches no `_SPIKE_NEEDED_PHRASES` entry — proving the new frontmatter trigger, not the old gate/phrase path, closes the loop the Motivation describes. Also a suppression case: same fixture plus `spike_completed: true` does not fire. [Agent 3 finding; revised after gate-chain review]

### Documentation
- `docs/reference/API.md` — document the new `IssueInfo.unproven_mechanism` field

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (~lines 1975-1979, "Which gate states consume which flag" table) — clarify that `unproven_mechanism` is not itself read by any loop gate state; it affects gating only indirectly, via the `outcome_confidence` discount feeding the existing `spike_needed` computation that `check_spike_needed` (`autodev.yaml`, `spike-gate.yaml`) already consumes. [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Location correction**: `skills/ll-refine-issue/SKILL.md` (named in this issue's own Files to Modify) is a 22-line bridge stub — "Bridged from `commands/refine-issue.md` for Codex Skills API discovery." It has no step numbering and no gate logic of its own. The actual prose that owns the `superseded_marker_count` → `/ll:reconcile-issue` escalation this issue's Part 2 should mirror lives in `commands/refine-issue.md` Step 6.7 (lines 983–1052) and Step 8 (lines 1087–1154) — that is the real target file for Part 2, not the skill stub.
- **`superseded_marker_count` is a real production call site, not markdown-only**: computed at `issue_parser.py:1781-1807`, then invoked from `scripts/little_loops/cli/issues/format_check.py:694` inside `cmd_format_check()`'s `--format json` branch, which merges it into the JSON payload as a side-channel key deliberately excluded from `FormatGaps`/`has_gaps` (comment at `format_check.py:684-692`, so it never affects `format-check`'s exit code). `commands/refine-issue.md` Step 6.7 and `scripts/little_loops/loops/autodev.yaml`'s `check_reconcile_needed` state (~line 1636) both read this same JSON key independently.
- **Exact three-surface escalation shape to mirror** (the `superseded_marker_count` precedent): (1) a Step 6.7 bullet naming the detection key and the boundary ("annotate, don't rewrite" / "surface, don't resolve") — `commands/refine-issue.md:1012-1020`; (2) a fixed-format Step 8 `## PROSE/PROGRAM DESIGN GATE` table row — `commands/refine-issue.md:1135`; (3) a conditional `## NEXT STEPS` bullet naming the exact remedy command — `commands/refine-issue.md:1145`. All three surfaces are required for the existing precedent; a new `unproven_mechanism` row for Part 2 would need the same three, plus the pipeline-diagram footnote at `commands/refine-issue.md:1179-1197`.
- **Existing near-identical mechanism this issue must reconcile with**: `spike_needed` (`scripts/little_loops/cli/issues/set_flags.py`) already phrase-detects no-precedent language via `_SPIKE_NEEDED_PHRASES` (lines 67-76: "no precedent", "zero precedent", "unprecedented", "no existing test exercises", "untested mechanism", "novel mechanism", "unproven approach", "no test coverage of the") and routes to `/ll:spike` through `autodev.yaml`. Its `FlagRule` (`set_flags.py:210-215`) has a precondition (`_spike_precondition_factory`, `set_flags.py:138-144`) requiring `outcome_confidence` to already be below the outcome threshold. **BUG-3349's actual failure case (`outcome_confidence: 84`, above this project's 65 threshold) would never satisfy that precondition** — confirming the existing `spike_needed` mechanism structurally cannot catch the class of bug this issue targets, since it only fires after the score is already low, and the whole problem is that the score was inflated. This validates ENH-3350's premise that detection must happen earlier (during `/ll:refine-issue`'s research pass, before `outcome_confidence` is computed), not merely that a new field is needed.
- `spike_needed`/`spike_attempted`/`spike_completed` are **not** `IssueInfo` dataclass fields — they are read/written directly against raw frontmatter via `parse_frontmatter()`/`update_frontmatter()` (`set_flags.py:262,280,323`), a lighter-weight pattern distinct from `decision_needed`'s full dataclass round-trip. `program_design_not_applicable` and `behavior_parity_not_applicable` follow the same raw-frontmatter-only pattern (`program_design.py:530`). This issue's own Proposed Solution correctly targets the `decision_needed`-style full dataclass round-trip for `unproven_mechanism` (since it needs `to_dict`/`from_dict` for the `IssueInfo` API surface, matching how `decision_needed` itself is consumed) rather than the raw-frontmatter-only pattern — flagging the two competing patterns exist in the codebase so this choice is made knowingly, not by accident.
- **Corrected line numbers** for the `decision_needed` template (Proposed Solution and Program Design cite slightly different numbers): dataclass field `issue_parser.py:3433`, `to_dict` entry `issue_parser.py:3480`, `from_dict` entry `issue_parser.py:3520`, frontmatter coercion `issue_parser.py:3588` and `issue_parser.py:3714`, shared coercion helper `IssueParser._coerce_tristate_bool` at `issue_parser.py:4024-4038`. Doc-comment template: `docs/reference/API.md:721` (one-line inline comment stating setter/clearer, matching the block at lines 705-729).
- **Additional file to modify not currently listed**: `skills/confidence-check/rubric.md` — the actual cap/override rows for readiness criteria (`Parity/Claim/Structure Cap` at rubric.md:241-259, `Decision Cap` at rubric.md:310-327) live here, not in SKILL.md alone. **No existing cap of this shape targets `outcome_confidence` or its Criteria A-D today** — `rubric.md:371` states "the outcome confidence is informational context for planning," so this issue's Part 3 would be the first override of this kind on that dimension, with no existing outcome-confidence-cap precedent to copy verbatim (only the readiness-side shape to adapt).
- **Testing template locations** (sibling `IssueInfo` tristate-bool test classes, 6-8 tests each: default-None, explicit True/False, `to_dict` presence, `from_dict` missing/False, `parse_file` integration true/absent): `TestIssueInfoTestable` at `test_issue_parser.py:2470`, `TestIssueInfoDecisionNeeded` at `test_issue_parser.py:2647`, `TestIssueInfoMissingArtifacts` at `test_issue_parser.py:2943`, `TestIssueInfoImplementationOrderRisk` at `test_issue_parser.py:3074`.
- **`show.py` extension points confirmed**: `decision_needed_raw = frontmatter.get("decision_needed")` at `show.py:129`, rendered as lowercased string at `show.py:317-318`; `spike_needed_raw`/`spike_attempted_raw`/`spike_completed_raw` follow the identical raw-frontmatter pattern at `show.py:131-137` with an inline comment "mirroring the `decision_needed` pattern" — either wiring shape is available as precedent for `unproven_mechanism`.

## Program Design

### Types

- `IssueInfo.unproven_mechanism: bool | None` (new field, mirrors `decision_needed`)

### Signatures

- `IssueInfo.to_dict(self) -> dict` — extend to serialize `unproven_mechanism`, mirroring the existing `decision_needed` entry
- `IssueInfo.from_dict(data: dict) -> IssueInfo` — extend to deserialize `unproven_mechanism` via `_coerce_tristate_bool`, mirroring `decision_needed`'s coercion

### Call Path

`/ll:refine-issue` (frontmatter write) -> `IssueInfo.from_dict` (`issue_parser.py:3513`) -> `IssueInfo.to_dict` (`issue_parser.py:3473`) -> `/ll:confidence-check` (reads `unproven_mechanism`, discounts `outcome_confidence`)

- Corrected anchors (analyzer-verified): dataclass field `issue_parser.py:3433`, `to_dict` entry `issue_parser.py:3480`, `from_dict` entry `issue_parser.py:3520`, frontmatter coercion `issue_parser.py:3588`/`:3714` via `IssueParser._coerce_tristate_bool` (`issue_parser.py:4024-4038`).
- Detection leg (Part 2) differs from the `superseded_marker_count` template it mirrors: that key is read back out of `ll-issues format-check --format json` (`format_check.py:694`) by the consuming command. `unproven_mechanism` has no equivalent read-back — `/ll:refine-issue` (real target `commands/refine-issue.md`, not the `skills/ll-refine-issue/SKILL.md` stub) would set the frontmatter flag directly during its own research pass, with no intermediate `format-check` round trip.
- Discount leg (Part 3): `/ll:confidence-check` (`skills/confidence-check/SKILL.md`) would need a new pre-fetch gate in the shape of the existing Phase 1.6/1.8 pattern (read `unproven_mechanism` via `ll-issues show {{issue_id}} --json` or a `format-check` key) feeding a new cap consumed in `skills/confidence-check/rubric.md`'s Criteria A-D. No such outcome-confidence cap exists today — the two existing caps (`Parity/Claim/Structure Cap`, `Decision Cap`, `rubric.md:241-259`,`:310-327`) both target the readiness score only (`rubric.md:371`).

## Implementation Steps

1. Add `unproven_mechanism` frontmatter field to `IssueInfo`, mirroring `decision_needed`'s wiring (dataclass field, `to_dict`/`from_dict`, and frontmatter coercion via `IssueParser._coerce_tristate_bool`).
2. Update `commands/refine-issue.md` (not `skills/ll-refine-issue/SKILL.md`, a bridge stub with no step logic) to deposit the `⚠ Unproven mechanism` inline marker, set `unproven_mechanism: true`, and recommend `/ll:spike` when a no-precedent finding is deposited, mirroring `superseded_marker_count`'s three-surface shape (Step 6.7 detection bullet, Step 8 gate-table row, `## NEXT STEPS` bullet). Detection must happen during this research pass, before `outcome_confidence` is computed — the existing `spike_needed` mechanism (`set_flags.py`) only fires once the score is already below threshold, which structurally can't catch an inflated-score case like BUG-3349's.
3. Update `skills/confidence-check/SKILL.md` with a new Phase 1.6/1.8-style pre-fetch gate that reads `unproven_mechanism` (plus `spike_attempted`/`spike_completed` for suppression), and `skills/confidence-check/rubric.md` with the `outcome_threshold − 1` cap rows for Criteria A-D — no existing cap targets `outcome_confidence` today, only the readiness-side `Parity/Claim/Structure Cap` and `Decision Cap` shapes exist as precedent to adapt.
4. Update `set_flags.py`: add the `unproven_mechanism: true` frontmatter trigger to the `spike_needed` `FlagRule`, bypassing the numeric gate and phrase match; keep `_spike_not_already_flagged` suppression.
5. Add round-trip tests for the new field; verify the cap and the `spike_needed` chain against a faithful BUG-3349-shaped fixture (`score_test_coverage: 15`, non-matching phrase text) plus a `spike_completed` suppression case.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Compute the `unproven_mechanism` cap at confidence-check `Phase 2b: Outcome Confidence Assessment` (`skills/confidence-check/SKILL.md:309`) and persist the capped value at `Phase 4: Update Frontmatter` (`SKILL.md:387`) — **before** `Phase 4.5` writes Outcome Risk Factors and `Phase 4.6: Flag Write-Back` (`SKILL.md:454`) runs `ll-issues set-flags`. Phase 4.5 only writes risk notes when `outcome_confidence` is below threshold, and Phase 4.6 no-ops on an empty notes section — so the cap must land before both. This ordering constraint is load-bearing for the issue's stated goal.
- **The ordering fix alone is insufficient** (gate-chain review, 2026-08-27): `spike_needed`'s `FlagRule` has two further preconditions the original wiring analysis missed — the `score_test_coverage <= 10` numeric gate (`set_flags.py:147-148, 214`; BUG-3349 has 15) and a `_SPIKE_NEEDED_PHRASES` substring match ("no direct precedent confirming" matches nothing in that list). Proposed Solution part 4's frontmatter trigger in `set_flags.py` is what actually completes the chain to `autodev.yaml`'s `check_spike_needed` (ENH-2640) and `spike-gate.yaml`.
- Update `docs/reference/CLI.md`'s gate-state/flag-consumption table (~lines 1975-1979) to note `unproven_mechanism` is consumed indirectly (via the `outcome_confidence` → `spike_needed` chain), not directly by any gate state.
- Add the three test touchpoints listed under Tests above (`test_wiring_reference_docs.py`, `test_confidence_check_skill.py`, `test_set_flags_cli.py`).

## Impact

- **Priority**: P3 - process/tooling correctness fix, not user-facing; prevents false-confidence approvals but isn't blocking active work
- **Effort**: Medium - one dataclass field, one `FlagRule` trigger in `set_flags.py`, plus two skill markdown files; no complex control flow
- **Risk**: Low - additive, opt-in field; only discounts scoring when the new flag is explicitly set, so existing issues are unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-28 | Priority: P3

## Success Metrics

A BUG-3349-shaped issue (unproven mechanism flagged by refine's own research,
undiscounted `outcome_confidence` above the gate, `score_test_coverage` above
the numeric gate, finding text matching no `_SPIKE_NEEDED_PHRASES` entry) ends
its refine → confidence-check → set-flags pipeline with `outcome_confidence ≤
outcome_threshold − 1` and `spike_needed: true`, so `check_spike_needed`
routes to `/ll:spike` before `/ll:manage-issue` runs. After a completed spike
(`spike_completed: true`), re-running confidence-check restores an uncapped
score.

## Scope Boundaries

Does not change `/ll:confidence-check`'s other scoring inputs
(`readiness_threshold`, `tdd_mode` gating) or attempt to automatically prove
or disprove the flagged mechanism — proving it is `/ll:spike`'s job. This
issue only wires the escalation and the discount, not resolution.

## Backwards Compatibility

Fully additive: issues without `unproven_mechanism` in frontmatter score
exactly as before, the new `set_flags.py` trigger only widens when
`spike_needed` can fire (never narrows), and `_coerce_tristate_bool` treats
the absent field as `None`.

## API/Interface

```yaml
# New frontmatter field, opt-in
unproven_mechanism: true
```


## Session Log
- `/ll:confidence-check` - 2026-08-28T02:28:28 - `59dee31a-c0af-4de1-b7d6-0e9cd9b1bbc6.jsonl`
- `/ll:confidence-check` - 2026-08-28T02:18:50 - `7dc575d8-a564-4ee8-873a-56d4554d4bd4.jsonl`
- `/ll:wire-issue` - 2026-08-28T02:15:58 - `da7096ea-4b62-4c96-b0a5-607df47afec2.jsonl`
- `/ll:reconcile-issue` - 2026-08-28T02:09:56 - `944f35f9-d220-44e9-ae5d-f1b677d300f9.jsonl`
- `/ll:refine-issue` - 2026-08-28T02:02:24 - `c7449015-080a-4efe-a7a0-c43d4513085b.jsonl`
- `/ll:format-issue` - 2026-08-28T01:53:13 - `881412bb-ad90-435b-b1d5-be56284588b6.jsonl`
- `/ll:format-issue` - 2026-08-28T01:52:50 - `70aa94f1-e630-42c3-805a-03afcbda0b82.jsonl`
- `/ll:capture-issue` - 2026-08-28T01:42:14 - `ba0fc777-8ec0-4b16-9e56-2a5dee8b5dea.jsonl`
