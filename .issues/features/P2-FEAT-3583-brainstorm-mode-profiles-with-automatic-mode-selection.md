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
---

# FEAT-3583: Brainstorm mode profiles with automatic mode selection

## Summary

Add **mode profiles as data** to the brainstorm engine plus **automatic mode
selection**: profiles `artifact`, `visual`, `functional`, `business`, selected by
`mode: auto` (default) in the first state after `init`.

## Current Behavior

Brainstorm has a single fixed pipeline with no notion of mode: every brief runs the same lenses, the same ranking prompt, and the same output shape, regardless of whether it is a name, a visual design, a functional design, or a business opportunity.

## Expected Behavior

- Each profile (a small YAML preset alongside the loop) sets: `reframe` on/off,
  default grid axes, idea schema, `ground` (none|codebase|web), `materialize`
  (none|render), tournament rubric, `premortem` on/off, output shape
  (grid | portfolio | winner + risks).
- `classify_mode` state runs right after `init` when `mode=auto`: LLM emits
  `{mode, confidence, rationale}` to the run dir; confidence below a threshold falls
  back to `artifact`.
- `mode=<x>` skips classification. Individual profile knobs can be overridden via
  context for mixed briefs.
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

Add profiles as data alongside `scripts/little_loops/loops/brainstorm.yaml`, plus two states after `init`:

- Four profile presets (`artifact`, `visual`, `functional`, `business`), each setting `reframe`, grid axes, idea schema, `ground` (none|codebase|web), `materialize` (none|render), tournament rubric, `premortem`, and output shape.
- `classify_mode` (LLM, only when `mode=auto`) emits `{mode, confidence, rationale}`; confidence below a threshold falls back to `artifact`.
- `resolve_profile` (script) merges precedence explicit `mode=` > per-knob context override > profile default > fallback, and writes `${context.run_dir}/profile.json`.

Downstream states read resolved values from `profile.json`, and gated states route the way `route_sink` does today.

## Program Design

### Types

- `Profile`: `{mode: str, reframe: bool, axes: [str, str], ground: "none" | "codebase" | "web", materialize: "none" | "render", rubric: str, premortem: bool, output_shape: str}`
- `ModeDecision`: `{mode: str, confidence: float, rationale: str}`

### Signatures

- `classify_mode(brief: str) -> ModeDecision` — LLM state; result written to the run dir
- `resolve_profile(mode: str, overrides: dict[str, str], decision: ModeDecision | None) -> Profile` — deterministic script

### Call Path

`init` -> `classify_mode` -> `resolve_profile` -> `frame` -> `diverge` -> `route_sink`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add `classify_mode` and `resolve_profile` states; thread resolved values into `frame`/`diverge`/`tournament`/output prompts; add `mode` context key
- New profile files (proposed: `scripts/little_loops/loops/brainstorm-profiles/{artifact,visual,functional,business}.yaml`) — verify loop package-data inclusion in `scripts/pyproject.toml`

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)
- FEAT-3584, FEAT-3585, FEAT-3586 — read `ground`, `materialize`, and `premortem` from the resolved profile

### Similar Patterns
- `route_sink` in `scripts/little_loops/loops/brainstorm.yaml` — existing gated-routing pattern for the profile-gated states

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: profile schema validation, resolution precedence (explicit > override > profile > fallback), stubbed-classifier routing for one reference brief per mode

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context keys: add `mode` (default `auto`) and per-knob overrides (`ground`, `materialize`, `premortem`, `reframe`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Package data: `scripts/pyproject.toml:203` includes `little_loops/**` wholesale, so a new profile directory under `scripts/little_loops/loops/` ships without a pyproject edit; `ll-verify-package-data` is the check.
- Constraint: `scripts/little_loops/loops/` subdirectories are scanned for loops (`loops/oracles/` is runnable, only `loops/lib/` is fragments). Profile YAMLs placed in a new sibling dir may be picked up by loop discovery and `test_builtin_loops.py` validation as if they were loops (no `initial`/`states`) — placement must be verified against discovery, or profiles stored as non-loop data (e.g. `.json`, or under `loops/lib/`).
- Current shape: `brainstorm.yaml` states are `init -> frame -> pop_lens -> diverge -> dedup_novelty -> (loop) -> cluster -> rank -> converge -> route_sink`; the `context:` block (`brainstorm.yaml:23-32`) holds string-valued knobs, so profile knobs must be string-encoded (`"true"`/`"false"`) there. `init` (`:36-52`) captures `run_dir` and `next: frame`, so `classify_mode`/`resolve_profile` insert between `init` and `frame`.
- Hardcoded behavior the profile must replace: universal lens catalog in `frame` (`:77-83`), `diverge` idea schema `{text, rationale}` (`:132-137`), `rank`/`converge` output shape and rubric (`:280-328`). `dedup_novelty` parses IDEAS_JSON with `text`/`rationale` keys, so any per-profile idea schema must keep `text` (dedup key) intact.
- Call-path correction: the issue's Call Path `frame -> diverge` omits `pop_lens`, which sits between them.
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
- `resolve_profile` and stubbed-classifier routing: use the `_bash` helper pattern in `test_brainstorm.py` (`TestPopLensEmptyQueue` shape) [Agent 3]

**Configuration**
- Validator: `classify_mode`/gated routes using `evaluate: classify` need `default:`/`_:` (`_validate_classify_route_default`); an `llm_structured` classifier needs `on_error`/`cannot_judge` (`_validate_abstention_route`) [Agent 2]
- Adds 2 fixed steps (`classify_mode`, `resolve_profile`) to the `max_steps: 60` budget tracked in FEAT-3582 [Agent 2]

## Implementation Steps

1. Define profile schema and the four presets.
2. Add `classify_mode` + `resolve_profile` states.
3. Thread resolved values into reframe/diverge/tournament/output prompts.
4. Tests for resolution precedence (explicit > override > profile > fallback).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Choose profile storage (prefer `.json`, or a YAML dir verified against the unfiltered rglob scanners and `test_builtin_loop_hardcode_gate.py`)
- Register profile files in `package_data.py` `PACKAGE_DATA_ASSETS` if read via `importlib.resources`; run `ll-verify-package-data`
- Add `classify_mode` to `fence.py` `FENCE_ROLES`
- Add profile schema test modeled on `test_enh1768_profile_system.py`; add `resolve_profile` precedence tests via `_bash`

## Impact

- **Priority**: P2 - unblocks the gated states in FEAT-3584/3585/3586 but adds no value until FEAT-3582 lands
- **Effort**: Medium - new profile schema and two states; mostly data plus one deterministic resolver script
- **Risk**: Low - additive and gated behind `mode`; `mode=artifact` preserves generic behavior
- **Breaking Change**: No

## Acceptance Criteria

- Four profile files exist and are validated by a schema/test.
- One reference brief per mode is classified to the expected profile (test with a
  stubbed classifier output plus a documented manual reference run).
- Explicit `mode=` bypasses `classify_mode`; per-knob override beats profile default.
- Profile resolution is deterministic (script), and the resolved profile is written
  to `${context.run_dir}/profile.json`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-25T02:07:45 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:34 - `ce904479-7e73-4d58-aa48-892e2cdb88b3.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:40 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
