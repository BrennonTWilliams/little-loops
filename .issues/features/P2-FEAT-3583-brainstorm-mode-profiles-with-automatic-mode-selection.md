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
confidence_score: 75
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3583: Brainstorm mode profiles with automatic mode selection

## Summary

Add **mode profiles as data** to the brainstorm engine plus **automatic mode
selection**: profiles `artifact`, `visual`, `functional`, `business`, selected by
`mode: auto` (default) in the first state after `init`.

## Current Behavior

Brainstorm has a single fixed pipeline with no notion of mode: every brief runs the same lenses, the same ranking prompt, and the same output shape, regardless of whether it is a name, a visual design, a functional design, or a business opportunity.

## Expected Behavior

- Each profile (a small **JSON** preset under `scripts/little_loops/loops/brainstorm-profiles/`, so unfiltered `rglob("*.yaml")` scanners never read it) sets: `reframe` on/off,
  default grid axes, idea schema, `ground` (none|codebase; `web` deferred), `materialize`
  (none|render), tournament rubric, `premortem` on/off, output shape
  (grid | portfolio | winner + risks).
- `classify_mode` state runs right after `init` when `mode=auto`: LLM emits
  `{mode, confidence, rationale}` to the run dir; confidence **below `0.6`** falls
  back to `artifact` (exactly `0.6` is accepted, i.e. `>=`).
- `mode=<x>` skips classification. Individual profile knobs can be overridden via
  context for mixed briefs.
- **Precedence**: the mode (explicit `mode=`, else classifier result, else the
  `artifact` fallback) selects the **base profile**; explicit per-knob context
  values then override that profile's defaults. `mode=business materialize=render`
  therefore renders.
- **Unset vs. explicit**: knob context keys default to `""` (inherit from profile).
  An explicit `none`/`false` is an override that disables the profile's behavior.
- **Overridable knobs** (2026-09-29): `reframe`, `ground`, `materialize`, `premortem`
  **plus** the numeric knobs `min_ideas`, `min_cells`, `max_finalists` (clamped ≤ 8 after
  resolution) and `ideas_per_round`. FEAT-3582 ships these numeric context keys defaulting
  to `""` with their pinned values (`12`/`4`/`8`) in the `artifact` profile; every preset
  here states its own values, and a profile may lower them (never raise `max_finalists`
  above 8). Without this, non-empty context defaults would beat every profile.
- **Per-profile lens catalog** (2026-09-29): each profile carries a `lenses` list (the pinned catalog rows below are starting points, changing one is fine if the schema test stays consistent); `frame` reads `profile.json` `lenses` instead of its hardcoded universal catalog, so mode changes what `diverge` is asked to explore, not only the axes and rubric. Closes the previously open schema gap.
- Each profile axis declares enumerated bins (`axes: [{name, bins}, {name, bins}]`)
  per the FEAT-3582 Data Contract, so cells cannot be invented.
- Every profile produces the canonical `portfolio.json`; `output_shape` changes only
  how `brainstorm.md` is rendered.
- Downstream states read resolved profile values rather than hardcoded behavior;
  gated states route via `classify`-style routing like the current `route_sink`.

## Use Case

**Who**: A little-loops user running `ll-loop run brainstorm "<brief>"` with briefs of very different kinds — a product name, a landing-page look, an API design, a market opportunity.

**Context**: The engine should not treat every brief the same way; visual briefs need rendering, functional briefs need codebase grounding, business briefs need reframing and market evidence.

**Goal**: Have the loop pick the right behavior automatically, while still allowing an explicit `mode=` or per-knob override for mixed briefs.

**Outcome**: The run writes `${context.run_dir}/profile.json` recording the resolved profile, and downstream states behave per that profile.

## Motivation

EPIC-3581 identifies a mode mismatch: visual designs need rendered candidates judged visually, functional designs need codebase grounding, business opportunities need market grounding and reframing, and artifacts need breadth more than a single winner. Encoding this as data profiles avoids forking the loop into four copies and lets FEAT-3584/3585/3586 stay gated behind profile knobs.

## Proposed Solution

FEAT-3667 already ships `resolve-profile`, the `profile.json` schema, and the `artifact` profile (FEAT-3582 wires the state). This issue **extends** them (it does not introduce them): three more presets, `classify_mode`, per-knob overrides in `resolve_profile`, and flipping the `mode` default to `auto`. Profiles live as `.json` data under `scripts/little_loops/loops/brainstorm-profiles/`:

- Four profile presets (`artifact`, `visual`, `functional`, `business`), each setting `reframe`, grid axes with enumerated bins, profile-specific idea fields (under the core `extra` object), `ground` (none|codebase; `web` deferred), `materialize` (none|render), tournament rubric, `premortem`, and output shape (rendering only). **Presets ship every not-yet-built knob at its off value** (§ Pinned Preset Contents → Shipped vs target): `resolve-profile` rejects values outside FEAT-3667's `BUILT_CAPABILITIES`, so a preset can never route into a state that does not exist yet.
- `classify_mode` (LLM, only when `mode=auto`) emits `{mode, confidence, rationale}`; confidence below `0.6` falls back to `artifact`. Malformed or unknown-mode output also falls back to `artifact` and is recorded as such. LLM self-reported confidence is poorly calibrated, so the run **makes the choice visible**: the loop prints `Mode: <x> (auto, confidence <c>) — rerun with mode=<y> to override` at start, and the report header repeats it. The four reference briefs in FEAT-3596 are the calibration data for the `0.6` threshold.
- `resolve_profile` (engine-module command `resolve-profile`, extended from FEAT-3667; `little_loops.brainstorm_engine`): (1) base profile = explicit `mode=` if set, else classifier mode, else `artifact`; (2) each knob whose context value is non-empty overrides the base profile's value; (3) writes `${context.run_dir}/profile.json` including which knobs were overridden. An invalid explicit `mode=` or knob value fails the run (exit 1 → `finalize_failed`) rather than silently falling back.

Downstream states read resolved values from `profile.json`, and gated states route the way `route_sink` does today.

## Program Design

### Types

- `Axis`: `{name: str, bins: [str]}` — cell values must be members of `bins`
- `Profile` (`extra` idea fields per mode are listed in § Pinned Preset Contents and stored as `extra_fields: [str]` — FEAT-3667's `Profile` type; the schema test asserts them): `{mode: str, lenses: [str], extra_fields: [str], reframe: bool, min_ideas: int, min_cells: int, max_finalists: int, ideas_per_round: int, reserve: int, axes: [Axis, Axis], ground: "none" | "codebase" (`web` deferred), materialize: "none" | "render", rubric: str, premortem: bool, output_shape: "grid" | "portfolio" | "winner_risks", overridden: [str]}`
- `ModeDecision`: `{mode: str, confidence: float, rationale: str}`

### Signatures

- `classify_mode(brief: str) -> ModeDecision` — LLM state; result written to the run dir
- `resolve_profile(mode: str, overrides: dict[str, str], decision: ModeDecision | None) -> Profile` — deterministic engine function behind `resolve-profile` (FEAT-3667 CLI contract); empty-string override = inherit

### Call Path

`init` -> `classify_mode` -> `resolve_profile` -> `frame` -> `reframe` -> `pop_lens` -> `diverge` -> `dedup` -> `shortlist` -> `tournament` -> `portfolio` -> `validate_portfolio` -> `route_sink`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add `classify_mode`; extend the FEAT-3582 `resolve_profile` state with overrides (engine side: FEAT-3667); thread resolved values into `frame`/`diverge`/`tournament`/output prompts; add `mode` context key
- New profile files (`.json`, decided 2026-09-28, e.g. `scripts/little_loops/loops/brainstorm-profiles/{artifact,visual,functional,business}.json`, so unfiltered `rglob("*.yaml")` loop scanners never read them — Wiring Phase finding) — no `scripts/pyproject.toml` edit needed (`little_loops/**` is included wholesale, `pyproject.toml:203`); confirm with `ll-verify-package-data`

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)
- FEAT-3584, FEAT-3585, FEAT-3586 — read `ground`, `materialize`, and `premortem` from the resolved profile

### Similar Patterns
- `route_sink` in `scripts/little_loops/loops/brainstorm.yaml` — existing gated-routing pattern for the profile-gated states

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: profile schema validation (incl. axis bins), resolution precedence (mode selects base profile, explicit knob overrides it), stubbed-classifier routing for one reference brief per mode, invalid explicit mode, malformed classifier output, confidence exactly at the threshold, explicit `false`/`none` override vs. empty-string inherit

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context keys: add `mode` (default `auto`) and per-knob overrides (`ground`, `materialize`, `premortem`, `reframe`, and — 2026-09-29 — `min_ideas`, `min_cells`, `max_finalists`, `ideas_per_round`), each defaulting to `""` (inherit). This supersedes any child issue's standalone `none`/`false` default for these keys. The `Profile` type also gains `reserve` (shortlist reserve size, read by FEAT-3582 `shortlist`; `2` when `ground=web`, else `0`). `lenses` is added to the `Profile` type (2026-09-29 third review). Remaining schema gaps — `output_shape` fallbacks, `judge_mode` — stay open.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Package data: `scripts/pyproject.toml:203` includes `little_loops/**` wholesale, so a new profile directory under `scripts/little_loops/loops/` ships without a pyproject edit; `ll-verify-package-data` is the check.
- Constraint: `scripts/little_loops/loops/` subdirectories are scanned for loops (`loops/oracles/` is runnable, only `loops/lib/` is fragments). Profile YAMLs placed in a new sibling dir may be picked up by loop discovery and `test_builtin_loops.py` validation as if they were loops (no `initial`/`states`) — placement must be verified against discovery, or profiles stored as non-loop data (e.g. `.json`, or under `loops/lib/`).
- Current shape: `brainstorm.yaml` states are `init -> frame -> pop_lens -> diverge -> dedup_novelty -> (loop) -> cluster -> rank -> converge -> route_sink`; the `context:` block (`brainstorm.yaml:23-32`) holds string-valued knobs, so profile knobs must be string-encoded (`"true"`/`"false"`) there. `init` (`:36-52`) captures `run_dir` and `next: frame`, so `classify_mode`/`resolve_profile` insert between `init` and `frame`.
- Hardcoded behavior the profile must replace: universal lens catalog in `frame` (`:77-83`), `diverge` idea schema `{text, rationale}` (`:132-137`), `rank`/`converge` output shape and rubric (`:280-328`). `dedup_novelty` parses IDEAS_JSON with `text`/`rationale` keys, so any per-profile idea schema must keep `text` (dedup key) intact.
- Call-path correction: `pop_lens` sits between `frame` and `diverge` (Call Path updated).
- Downstream ordering: `blocked_by: FEAT-3582` — the engine core rewrite changes these states; line anchors above describe the pre-3582 file and will shift.
- Sink routing precedent for gated states: `route_sink` (`:332-344`) uses `evaluate: type: classify` over an echoed token with `_:` default route; a `mode=auto` gate reads the same way. Interpolated `${context.*:shell}` form is used for the shell echo.
- Test conventions: `scripts/tests/test_brainstorm.py` loads `LOOP_FILE` via `load_and_validate`/`validate_fsm` and exercises shell states by extracting `action` and running `bash -c` in `tmp_path` (`_bash` helper) — a deterministic `resolve_profile` shell/python state is testable the same way, and stubbed-classifier routing can be tested by pre-writing the classifier output file.
- Bash-brace rule: any `${...}` shell expansion inside FSM actions must be escaped `$${...}` (interpolated before bash).

### Wiring Additions

_Wiring pass added by `/ll:wire-issue`:_

**Files to Modify**
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` entry for `classify_mode` (interpolates `${context.brief}`) [Agent 3]
- `scripts/little_loops/package_data.py` `PACKAGE_DATA_ASSETS` — add explicit tuples per profile file if profiles are read at runtime via `importlib.resources` (manifest is tuple-by-tuple; omissions are false-green); check with `ll-verify-package-data` [Agent 1, Agent 3]

**Dependent Files (Callers/Importers)**
- Profile-directory discovery hazard: `is_runnable_loop` (`fsm/validation/structural_rules.py`) skips YAML lacking `name`/`initial`/`states`, so `doc_counts.py`, `cli/loop/info.py`, `cli/doctor.py`, `test_builtin_loops.py:66` ignore it — but unfiltered `rglob("*.yaml")` scanners will still read it: `fsm/interp_sweep.py:~250`, `fsm/validation/reachability.py:~131`, `cli/loop/rename.py:~83`, and `scripts/tests/test_builtin_loop_hardcode_gate.py::_all_loop_files` (`**/*.yaml`, skips only dot-dirs). Storing profiles as `.json` avoids all of these [Agent 1, Agent 3]

**Tests**
- Profile schema validation: model on `scripts/tests/test_enh1768_profile_system.py` (required-layer-file assertions) and `test_package_data_manifest.py` [Agent 3]
- `scripts/tests/test_builtin_loop_hardcode_gate.py` and `test_builtin_loop_interpolation.py` (rglob) — run against any YAML profile files [Agent 3]
- `resolve_profile` precedence tests are **direct-import tests of `little_loops.brainstorm_engine`** (`test_brainstorm_engine.py`, superseding the earlier `_bash` note); stubbed-classifier routing is a wiring test that pre-writes the classifier output file [Agent 3]

**Configuration**
- Validator: `classify_mode`/gated routes using `evaluate: classify` need `default:`/`_:` (`_validate_classify_route_default`); an `llm_structured` classifier needs `on_error`/`cannot_judge` (`_validate_abstention_route`) [Agent 2]
- Adds 1 fixed step (`classify_mode`; `resolve_profile` is already in FEAT-3582's count) to the `max_steps: 60` budget tracked in FEAT-3582 [Agent 2]

## Implementation Steps

1. Define profile schema and the four presets.
2. Add `classify_mode` + `resolve_profile` states.
3. Thread resolved values into reframe/diverge/tournament/output prompts.
4. Tests for resolution precedence (mode selects base profile; explicit knob overrides it; empty string inherits) and the invalid/malformed/boundary cases.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Choose profile storage (prefer `.json`, or a YAML dir verified against the unfiltered rglob scanners and `test_builtin_loop_hardcode_gate.py`)
- Register profile files in `package_data.py` `PACKAGE_DATA_ASSETS` if read via `importlib.resources`; run `ll-verify-package-data`
- Add `classify_mode` to `fence.py` `FENCE_ROLES`
- Add profile schema test modeled on `test_enh1768_profile_system.py`; add `resolve_profile` precedence tests by direct import of `little_loops.brainstorm_engine` (not `_bash`; matches the Tests section)
- Add the capability wiring test: for every shipped profile, every routing token the engine can emit (`check-floors`, `collapse`, `portfolio`, `frame-apply`) routes to a state other than `finalize_failed`, and `resolve-profile` exits 1 for any knob value outside `BUILT_CAPABILITIES` (including explicit overrides such as `materialize=render`)

## Pinned Preset Contents

_Added 2026-09-28 (EPIC-3581 sub-issue review); the schema test must assert these shapes. Bins are a starting point; changing one is fine if the test and profile stay consistent._

| Field | `artifact` (FEAT-3582) | `visual` | `functional` | `business` |
|-------|-----------|----------|--------------|------------|
| axes | register `[literal, evocative, abstract]` × tone `[playful, neutral, serious]` | density `[sparse, balanced, dense]` × temperament `[warm, neutral, cool]` | scope `[local, module, cross-cutting]` × approach `[extend, refactor, new-component]` | customer `[existing, adjacent, new]` × model `[product, service, platform]` |
| `reframe` | false | false | true | true |
| `ground` | none | none | codebase | none (was `web`; deferred, EPIC-3581 third review) |
| `materialize` | none | render | none | none |
| `premortem` | false | false | true | true |
| `output_shape` | grid | portfolio | winner_risks | winner_risks |
| `min_ideas` / `min_cells` / `max_finalists` / `ideas_per_round` | 12 / 4 / 8 / 5 | 12 / 4 / 8 / 5 | 12 / 4 / 8 / 5 | 12 / 4 / 8 / 5 |
| `reserve` (shortlist) | 0 | 0 | 0 | 0 (`ground=web` is deferred out of v1; the field stays in the schema for the follow-up) |
| `extra` idea fields | — | `palette`, `layout_summary` | `touchpoints`, `creates` (FEAT-3584) | `assumptions`, `target_customer` |
| `lenses` | universal catalog (today's `frame` list) | visual-craft lenses (e.g. typography, color, layout density, motion, metaphor, constraint) | system lenses (e.g. data flow, failure modes, extensibility, migration, testability, operability) | market lenses (e.g. customer job, pricing, distribution, incumbents, regulation, unit economics) |
| rubric focus | breadth, distinctness, memorability | visual clarity, hierarchy, fit to brief | feasibility in this codebase, leverage, blast radius | demand evidence, differentiation, cost to test |

**Shipped vs target (2026-09-30 fourth review).** The table above is the **target** end state. What ships in this issue is the same table with `ground`, `materialize` and `premortem` at their off values (`none` / `none` / `false`) for every mode, because the states arrive in FEAT-3584/3585/3586 and a token routed to a missing state fails the run (a `visual` run after ~13 calls; `functional`/`business` after the full tournament). Each optional child, **in the change that lands its states**: (1) widens `BUILT_CAPABILITIES` in the engine, (2) flips its knob in the target profile(s) (`ground=codebase` for `functional`; `materialize=render` for `visual`; `premortem=true` for `functional`/`business`), (3) adds that flip to its acceptance criteria and the wiring test. Until then `mode=visual` still selects the visual axes, lenses and rubric, and an explicit `materialize=render` fails fast at `resolve-profile` instead of mid-run.

- `output_shape: grid` renders the **grid map in addition to** the portfolio section (FEAT-3582 Acceptance Criteria: `brainstorm.md` presents a portfolio + the grid map); `portfolio` and `winner_risks` render the portfolio without the full grid map. `portfolio.json` is identical for all shapes.
- Classifier confidence threshold: `0.6` (`>=` accepts). The classifier prompt lists the four modes with the one-line profile description; malformed/unknown output → `artifact`, recorded in `profile.json`.
- `visual` keeps `premortem` off and `business` keeps `materialize` off; mixed briefs use per-knob overrides.

## Review Decisions

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus, structural/process pass; nothing measured):_ all four preset JSONs are now created by **FEAT-3667** (unbuilt knobs off); this issue adds `classify_mode`, the per-knob override plumbing, the `mode` default flip to `auto`, and tuning of the presets (axes/bins are provisional until FEAT-3686 reports). `reframe` is deferred to v2 (`BUILT_CAPABILITIES["reframe"] = {False}`): `functional`/`business` ship `reframe: false`, and the "target" `reframe: true` cells in § Pinned Preset Contents are the follow-up's, not v1's. Blocked-by also includes FEAT-3686 transitively via FEAT-3582.

_Added 2026-09-29 (EPIC-3581 third review, `/ll:advise` with Opus; nothing measured):_ profiles gain `lenses` (per-mode lens catalog read by `frame`); `business` defaults to `ground: none` and `reserve: 0` because `ground=web` is out of v1; profile data reaches prompts through engine `prompt-block` stdout blocks captured by the states (FEAT-3667), not by prompt-side file reads; `classify_mode` is a prompt state and must declare `next:` + `on_error:` (no hidden evaluator call) and route via an explicit classify with `_: finalize_failed` where it gates.

_Added 2026-09-30 (EPIC-3581 fourth review, `/ll:advise` with Opus; nothing measured):_ presets ship unbuilt knobs off and each optional child flips its own (§ Pinned Preset Contents → Shipped vs target); `resolve-profile` enforces `BUILT_CAPABILITIES` (FEAT-3667); `ground` type text reconciled to `none|codebase`; tests are direct-import, not `_bash`.

## Impact

- **Priority**: P2 - unblocks the gated states in FEAT-3584/3585/3586 but adds no value until FEAT-3582 lands
- **Effort**: Medium - new profile schema and two states; mostly data plus one deterministic resolver script
- **Risk**: Low - additive and gated behind `mode`; `mode=artifact` preserves generic behavior
- **Breaking Change**: No

## Acceptance Criteria

- Four profile files exist and are validated by a schema/test.
- One reference brief per mode is classified to the expected profile (test with a
  stubbed classifier output plus a documented manual reference run).
- Explicit `mode=` bypasses `classify_mode`; per-knob override beats profile default
  (e.g. `mode=business materialize=render` resolves `materialize: render`).
- Empty-string knob values inherit the profile default; explicit `none`/`false`
  disables it.
- Invalid explicit `mode=` fails the run; malformed classifier output falls back to
  `artifact` and is recorded in `profile.json`.
- Every profile axis has enumerated bins, validated by the schema test.
- Profile resolution is deterministic (script), and the resolved profile is written
  to `${context.run_dir}/profile.json`.
- No shipped profile turns on a capability outside `BUILT_CAPABILITIES`; an explicit override naming one exits 1 at `resolve-profile` before any LLM call; a wiring test proves every token the engine can emit for every shipped profile routes somewhere other than `finalize_failed`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-28; re-verified unchanged 2026-09-29 (FEAT-3582 still open, `Profile` type still lacks `extra`)_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (dependency hard override)
**Outcome Confidence**: 75/100 → MODERATE

### Gaps to Address
- Unresolved dependency (hard override): `blocked_by` FEAT-3582 is `Open`. Implement FEAT-3582 first, or remove the dependency if it no longer applies. The rest of the issue is otherwise ready (preset contents, threshold, and `.json` profile storage are now pinned).

### Concerns
- `artifact` is pinned to `output_shape: grid`, while FEAT-3582's Acceptance Criteria say `brainstorm.md` presents "a portfolio + the grid map" for the core engine. Reconcile: state that `grid` renders the grid map in addition to the portfolio section.
- The `Profile` type in § Program Design omits the profile-specific idea fields (`extra`) that § Pinned Preset Contents pins per mode; add them so the schema test has one source of truth.
- Line anchors in the Codebase Research Findings describe the pre-FEAT-3582 file and will shift once it lands.


## Session Log
- `/ll:confidence-check` - 2026-09-29T06:02:09 - `1e4b6b11-acbb-4e78-b169-131d9cd93116.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:00:47 - `c90c2478-f308-49d4-930c-8be0a9590776.jsonl`
- `/ll:confidence-check` - 2026-09-25T17:21:39 - `823eec8e-b4aa-4134-9728-fb6281ade224.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:27 - `284cb1d7-e993-4a6e-afc1-6ece8366d2db.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:45 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:34 - `ce904479-7e73-4d58-aa48-892e2cdb88b3.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:40 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
