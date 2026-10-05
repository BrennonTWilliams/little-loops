---
id: FEAT-3583
type: FEAT
title: Brainstorm mode profiles with automatic mode selection
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:13Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
- FEAT-3667
reconcile_attempted: true
---

# FEAT-3583: Brainstorm mode profiles with automatic mode selection

## Summary

Add automatic mode selection, explicit context-override wiring, and preset tuning to the engine shipped by FEAT-3667 and wired by FEAT-3582. The four JSON presets, Profile/Axis schema, resolver and precedence tests already belong to FEAT-3667. This issue changes the default mode from artifact to auto; it does not enable optional capabilities.

## Current Behavior

The current shipped loop has one generic pipeline. After FEAT-3667/3582 land, four explicit modes exist, but the default is artifact and no classifier chooses between them.

## Expected Behavior

- Init runs `resolve-profile --validate-only` with the explicit mode/knobs before any classifier call; invalid mode, unknown key, bad numeric/bool, or unbuilt capability fails with no LLM dispatch. Reuse the engine validator, without a separate gate state or a second implementation.
- Explicit `mode=artifact|visual|functional|business` skips classification. `mode=auto` runs one prompt state, capturing `MODE_JSON: {"mode": str, "confidence": number, "rationale": str}` for the resolver. `classify_mode` declares `next: resolve_profile` and `on_error: resolve_profile` (plus bounded timeout/rate-limit routing), and the resolver treats a failed classifier call as fallback, rather than accepting partial stdout.
- Confidence must be finite and in [0,1], excluding booleans. A known mode with confidence >= 0.6 is accepted; malformed/unknown/invalid confidence, confidence < 0.6, or classifier host error/timeout falls back to artifact. `profile.json` records requested mode, decision, fallback reason, resolved mode, and overridden keys. The banner and report make the choice visible and explain `mode=` reruns.
- Explicit nonempty context knobs override the selected preset. Empty string inherits; explicit false/none disables. Knobs are reframe, ground, materialize, premortem, min_ideas, min_cells, max_finalists, ideas_per_round. The resolver enforces BUILT_CAPABILITIES. In core v1, reframe=true, ground=codebase, materialize=render and premortem=true fail until their owning implementation enables them (reframe remains v2).
- Prompts consume captured engine blocks with nonce fences; their schema/rubric/lenses are already parameterized by FEAT-3582. Do not rewrite that plumbing again.
- All modes produce canonical portfolio.json; output_shape only changes the report layout. Visual mode uses text judging until FEAT-3585, functional mode has no anchor validation until FEAT-3584, and business mode has no web grounding in v1.

## Use Case

A user supplies a naming, visual, functional, or business brief. The loop visibly chooses a suitable preset; an explicit mode and built-knob override remain available for mixed briefs.

## Motivation

Mode-specific lenses, bins, idea fields and rubric provide useful differentiation even before grounding/rendering/pre-mortem land. Resolving explicit inputs before classification prevents spending a call on an impossible run.

## Proposed Solution

Add classify_mode between init and the existing resolve_profile state, selecting it from init only for auto. Capture classifier stdout and exit status, write a safe raw input file in resolve_profile, and pass --decision-file plus --set values to the engine. Preserve exit status if resolve_profile and prompt-block share an action: failure of either must prevent frame. Fence the brief and captured blocks. Every prompt state has next/on_error or an explicit evaluator.

## Program Design

### Types

- Profile and Axis: import the FEAT-3667 types, including per-bin definitions, duplicate_criterion, lenses, extra_fields, overridden keys and provenance; do not define a second reduced schema.
- ModeDecision: {mode: str, confidence: float, rationale: str}; validate numeric confidence as above.

### Signatures

- parse_mode_decision(raw: str, exit_code: int) -> dict — deterministic classifier-result validation/fallback record in brainstorm_engine; final profile resolution is FEAT-3667's resolve_profile.

### Call Path

init (explicit-input preflight) -> [classify_mode, only for auto] -> resolve_profile -> frame -> frame_apply -> pop_lens -> diverge -> ingest -> dedup -> shortlist -> tournament -> portfolio -> render_report -> validate_portfolio -> route_sink

## Pinned Preset Contents

All four files are created in FEAT-3667; this issue tunes them. Every axis has definitions for its bins and every profile a nonempty duplicate_criterion. Lens catalogs plus task-specific additions must fit frame-apply's maximum nine lenses.

| Field | artifact | visual | functional | business |
|---|---|---|---|---|
| Axes | register [literal, evocative, abstract] × tone [playful, neutral, serious] | density [sparse, balanced, dense] × temperament [warm, neutral, cool] | scope [local, module, cross-cutting] × approach [extend, refactor, new-component] (provisional) | customer [existing, adjacent, new] × model [product, service, platform] |
| Core v1 reframe / ground / materialize / premortem | false / none / none / false | false / none / none / false | false / none / none / false | false / none / none / false |
| output_shape | grid (portfolio plus grid map) | portfolio | winner_risks (portfolio; risk section only when annotations exist) | winner_risks (same rule) |
| min_ideas / min_cells / max_finalists / ideas_per_round / reserve | 12 / 4 / 8 / 5 / 0 | 12 / 4 / 8 / 5 / 0 | 12 / 4 / 8 / 5 / 0 | 12 / 4 / 8 / 5 / 0 |
| extra_fields | none | palette, layout_summary | touchpoints, creates | assumptions, target_customer |
| Lenses | universal + task-specific | typography, color, hierarchy, layout, metaphor, constraint | data flow, failure modes, extensibility, migration, testability, operability | customer job, pricing, distribution, incumbents, regulation, unit economics |
| Rubric | breadth, distinctness, memorability | clarity, hierarchy, brief fit | feasibility, implementation cost, blast radius | demand assumptions, differentiation, cost to test |
| Duplicate criterion | same name/coined word | same layout and palette direction | same core mechanism such that implementing one makes the other redundant | same customer and value proposition |

Optional target flips are owned by FEAT-3584 (functional ground=codebase), FEAT-3585 (visual materialize=render), and FEAT-3586 (functional/business premortem=true), in the same change as their states. reframe and ground=web remain deferred; they are not preset targets for this issue.

### Bounded tuning and comparable evaluation

The completed FEAT-3686 spike found functional approach agreement 0.72 (<0.75); visual/business axes are unmeasured. For each of these modes, use a fixed corpus of at least 20 representative ideas and the same three independent blind-tag calls, recording exact-cell and per-axis agreement. Permit at most two tuning iterations (three measured versions including the initial one); acceptance is exact-cell >=0.6 and each axis >=0.75. If it still fails, preserve a provisional explicit-mode preset and leave auto default on artifact until the axis decision is resolved; report the blocker rather than tune indefinitely or silently weaken the threshold.

Freeze the final definitions and corpus/model/version in the run record. If functional bins/definitions change, re-tag **both old and new** pinned-brief ideas with those same final definitions; the historical six-cell figure is not a gate against a changed grid. FEAT-3582's earlier comparison uses FEAT-3667's provisional preset and is preserved as its own evidence.

## Integration Map

### Behavior Parity

| Artifact | Behavior | Disposition |
|---|---|---|
| brainstorm.yaml | Explicit artifact default | Changed to auto only when classifier and preset tuning gates pass |
| brainstorm.yaml | Explicit modes, engine data blocks, sink contract | Preserved |
| brainstorm-profiles/*.json | Preset schema and unbuilt knobs off | Preserved; tune bins/definitions/lenses only |

### Files to Modify
- scripts/little_loops/loops/brainstorm.yaml — init preflight/auto route, classifier, existing resolver's override plumbing, mode default.
- scripts/little_loops/brainstorm_engine.py — parse_mode_decision and decision/fallback provenance; reuse resolver validation.
- scripts/little_loops/loops/brainstorm-profiles/{artifact,visual,functional,business}.json — tuning of existing files.
- scripts/little_loops/fsm/fence.py — classify_mode brief registration.
- scripts/tests/test_brainstorm.py and scripts/tests/test_brainstorm_engine.py — routing and direct-import decision fixtures; existing precedence tests remain owned by FEAT-3667.
- scripts/tests/test_builtin_loops.py and scripts/tests/data/loop_interpolation_baseline.json — relevant fence/capture/warning checks.

### Dependent Files
- FEAT-3584/3585/3586 read resolved knobs; FEAT-3596 reads final preset definitions for comparison.
- package_data.py registrations are made in FEAT-3667 and verified here by ll-verify-package-data.

### Documentation
- scripts/little_loops/loops/README.md, docs/guides/LOOPS_GUIDE.md, docs/guides/LOOPS_REFERENCE.md — automatic choice, overrides, fallback, and capability availability.

## Implementation Steps

1. Tune and measure the existing presets within the bounded process; keep final axis definitions comparable across baselines.
2. Wire explicit-input preflight, auto-only classify_mode, safe capture/file delivery and the existing resolver.
3. Add malformed/finite-confidence/boundary/error/explicit-mode fixtures and capability-token wiring tests.
4. Verify preset packaging, fence/capture rules, exact state count (classifier adds one successful-path state), both loop validation and the local suite.

## Impact

- **Priority**: P2 — makes the four core modes automatically usable.
- **Effort**: Medium — one classifier, existing resolver plumbing, bounded preset measurement.
- **Risk**: Low — explicit modes and visible artifact fallback remain available.
- **Breaking Change**: No.

## Acceptance Criteria

- Four existing presets satisfy FEAT-3667's schema; functional/visual/business tuning meets the bounded measurement gate before the default flips to auto.
- One reference brief per mode is routed using stubbed classifier output plus documented real calibration runs; stubbed success alone is not evidence of classifier accuracy.
- Explicit mode skips classification; invalid explicit inputs cause zero LLM dispatches even with mode=auto, including ideas_per_round outside FEAT-3667's 1–10 cap or min_ideas above nine-lens capacity. Reuse engine validation; do not add a second bound implementation.
- Confidence 0.6 is accepted; lower, nonfinite/out-of-range, boolean, malformed, unknown mode and classifier host failure/timeout all fall back visibly to artifact.
- A **built** numeric override (e.g. mode=business ideas_per_round=3) wins over the preset. Empty inherits; false/none disables. Unbuilt optional overrides fail preflight rather than requiring materialize to exist.
- Every successful capability token reaches its explicitly mapped state; fail and _ routes remain failures. No route pre-wires an unbuilt state.
- No reframe state, web grounding, or optional preset enablement is implemented here; no hidden evaluator call is added.
- Changed definitions trigger comparable old/new re-tagging; reference records include import origin and actual resource usage.

## Review History

Historical rationale only; the reconciled directive sections above define current scope (2026-10-05).

_Added 2026-09-30 (FEAT-3686 spike results):_ every preset axis needs a one-line **definition per bin** (agreement 0.51–0.67 without, 0.62–0.83 with) and a `duplicate_criterion` (artifact: same name or coined word; functional: same core mechanism such that implementing one makes the other redundant; visual: same layout and palette direction; business: same target customer and value proposition). The `functional` `approach` axis (`extend`/`refactor`/`new-component`) scored 0.72 per-axis agreement (< 0.75): sharpen its bins/definitions and re-run the spike's 3-call blind tagger check (`postmortems/brainstorm-spike/spike.py tag`) until ≥ 0.75 before pinning the preset; `visual` and `business` axes have not been measured and get the same check. Add the definitions and criteria to the schema test.

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus, structural/process pass; nothing measured):_ all four preset JSONs are now created by **FEAT-3667** (unbuilt knobs off); this issue adds `classify_mode`, the per-knob override plumbing, the `mode` default flip to `auto`, and tuning of the presets (axes/bins are provisional until FEAT-3686 reports). `reframe` is deferred to v2 (`BUILT_CAPABILITIES["reframe"] = {False}`): `functional`/`business` ship `reframe: false`, and the "target" `reframe: true` cells in § Pinned Preset Contents are the follow-up's, not v1's. Blocked-by also includes FEAT-3686 transitively via FEAT-3582.

_Added 2026-09-29 (EPIC-3581 third review, `/ll:advise` with Opus; nothing measured):_ profiles gain `lenses` (per-mode lens catalog read by `frame`); `business` defaults to `ground: none` and `reserve: 0` because `ground=web` is out of v1; profile data reaches prompts through engine `prompt-block` stdout blocks captured by the states (FEAT-3667), not by prompt-side file reads; `classify_mode` is a prompt state and must declare `next:` + `on_error:` (no hidden evaluator call) and route via an explicit classify with `_: finalize_failed` where it gates.

_Added 2026-09-30 (EPIC-3581 fourth review, `/ll:advise` with Opus; nothing measured):_ presets ship unbuilt knobs off and each optional child flips its own (§ Pinned Preset Contents → Shipped vs target); `resolve-profile` enforces `BUILT_CAPABILITIES` (FEAT-3667); `ground` type text reconciled to `none|codebase`; tests are direct-import, not `_bash`.

## Confidence Check Notes

Historical score; not re-run after this review. Re-score after the revised contracts and prerequisites are implemented.

_Added by `/ll:confidence-check` on 2026-09-28; re-verified unchanged 2026-09-29 (FEAT-3582 still open, `Profile` type still lacks `extra`)_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (dependency hard override)
**Outcome Confidence**: 75/100 → MODERATE

### Gaps to Address
- Unresolved dependency (hard override): `blocked_by` FEAT-3582 is `Open`. Implement FEAT-3582 first, or remove the dependency if it no longer applies. The rest of the issue is otherwise ready (preset contents, threshold, and `.json` profile storage are now pinned).

### Concerns
- `artifact` is pinned to `output_shape: grid`, while FEAT-3582's Acceptance Criteria say `brainstorm.md` presents "a portfolio + the grid map" for the core engine. Reconcile: state that `grid` renders the grid map in addition to the portfolio section.
- The `Profile` type in § Program Design omits the profile-specific idea fields (`extra`) that § Pinned Preset Contents pins per mode; add them so the schema test has one source of truth.
- Line anchors in the Codebase Research Findings describe the pre-FEAT-3582 file and will shift once it lands.


## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Session Log
- Follow-up pre-implementation review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.72; no new live measurements) - 2026-10-05
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:28 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:26 - `813546cd-0058-4cf8-a1bc-da17040cac6b.jsonl`
- `/ll:confidence-check` - 2026-09-29T06:02:09 - `1e4b6b11-acbb-4e78-b169-131d9cd93116.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:00:47 - `c90c2478-f308-49d4-930c-8be0a9590776.jsonl`
- `/ll:confidence-check` - 2026-09-25T17:21:39 - `823eec8e-b4aa-4134-9728-fb6281ade224.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:27 - `284cb1d7-e993-4a6e-afc1-6ece8366d2db.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:45 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:34 - `ce904479-7e73-4d58-aa48-892e2cdb88b3.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:40 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
