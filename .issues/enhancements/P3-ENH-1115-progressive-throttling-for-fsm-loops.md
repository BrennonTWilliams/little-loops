---
id: ENH-1115
type: ENH
priority: P3
status: done
discovered_date: 2026-04-15
discovered_by: capture-issue
completed_at: 2026-05-11T21:01:49Z
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
size: Very Large
relates_to: []
---

# ENH-1115: Progressive Throttling for FSM Loop Tool Calls

## Summary

Extend the recent 429 / rate-limit detection in FSM loops (commits fa02a18..95b4fed2) with call-count-based progressive degradation: calls 1–3 normal, 4–8 warn + reduced output, 9+ redirect to batch execution or hard-stop.

## Motivation

Recent FSM work added per-state rate-limit config, storm detection, and in-place retry (see `d84e5f11`, `95b4fed2`, `c8ea14e9`, `fa02a186`). That handles the provider side (429s). But we still see runaway loops where the same state fires 20+ similar tool calls before any rate limit trips — burning cache, cost, and user trust without ever hitting a retry-able error.

Context-mode (github.com/mksglu/context-mode) applies "progressive throttling" at the MCP layer: call counts per logical operation escalate restrictions so noisy loops self-throttle before hitting provider limits. Same idea, but applied to FSM state transitions.

## Current Behavior

- FSM rate-limit config handles 429 responses with retry-in-place + count persistence
- No mechanism counts *successful* repeated calls from the same state
- A state that makes 15 successful Read calls in a single tick burns context with no warning

## Expected Behavior

- FSM tracks per-state tool-call count within a single state visit
- New `throttle:` section in FSM state config:
  ```yaml
  throttle:
    normal_max: 3      # calls 1-3 pass through
    warn_max: 8        # calls 4-8 get a warning injected into tool result
    hard_max: 12       # calls 9-12 trigger state transition to a batch/summarize state
    # >hard_max: hard stop, mark loop stuck
  ```
- Defaults live in `templates/` and can be overridden per state
- Warnings and hard-stops appear in loop telemetry / `analyze-loop` output

## Acceptance Criteria

- New config keys validated in FSM config schema
- Counter resets on state exit
- Unit tests cover warn / hard / stop transitions
- At least one built-in loop template uses the new throttle block
- `/ll:analyze-loop` surfaces throttle events
- Docs updated alongside existing rate-limit fields (commit `c8ea14e9` touched these)

## Scope Boundaries

- **In scope**: Per-state tool-call counter within a single state visit; new `throttle:` YAML config block for FSM states; warning injection into tool results at `warn_max`; state transition to batch/summarize state at `hard_max`; hard-stop and "stuck" marking beyond `hard_max`; default throttle values in `templates/`; throttle events in `analyze-loop` telemetry; unit test coverage
- **Out of scope**: Provider-side 429 retry handling (covered by existing FSM rate-limit config); cross-state or global tool-call aggregation; throttling non-tool-call loop operations (state transitions, sleep intervals)

## API/Interface

New `throttle:` block in FSM state YAML config (all fields optional; defaults applied from `templates/`):

```yaml
throttle:
  normal_max: 3    # calls 1–3: pass through
  warn_max: 8      # calls 4–8: inject warning into tool result
  hard_max: 12     # calls 9–12: transition to batch/summarize state
  # calls > hard_max: hard stop, mark loop stuck
```

## Proposed Solution

Implement in three layers:

1. **Schema** (`scripts/little_loops/fsm/schema.py`): Add optional `throttle:` block with `normal_max`, `warn_max`, `hard_max` integer fields; load defaults from `templates/`.
2. **Executor** (`scripts/little_loops/fsm/executor.py`): Add per-state call counter initialized on state entry, incremented on each tool call, reset on state exit; check threshold on each increment and take the appropriate action (pass / warn / transition / stop).
3. **Telemetry**: Emit throttle events to loop state so `ll:analyze-loop` can surface them. Update at least one built-in loop template to use a `throttle:` block.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `throttle:` block to state config schema
- `scripts/little_loops/fsm/executor.py` — add per-state call counter and threshold-check logic
- `templates/` — add default throttle config values
- Rate-limit docs (see commit `c8ea14e9`) — update alongside existing rate-limit fields

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/generate_schemas.py:82` — add `throttle_warn`, `throttle_hard`, `throttle_stop` to `SCHEMA_DEFINITIONS` dict; count 23→26; run `ll-generate-schemas` after to regenerate event-type schemas in `docs/reference/schemas/`
- `scripts/little_loops/cli/loop/layout.py:204,30-37` — add `on_throttle_hard` to `_collect_edges()` so FSM diagram includes that transition edge; add `"throttle_hard"` color entry to edge label color dict
- Note: `fsm-loop-schema.json` is **hand-maintained**, NOT auto-generated by `ll-generate-schemas`; the `stateConfig` definition at line 175-321 has `"additionalProperties": false` — add `throttle` nested object property manually alongside schema.py changes

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/__init__.py:90-92` — exports `RATE_LIMIT_*_EVENT` constants; must export new `THROTTLE_*_EVENT` constants alongside them
- `scripts/little_loops/fsm/persistence.py:420-447` — `_handle_event` writes all executor events to `.loops/.running/<name>.events.jsonl`; throttle events are automatically captured if emitted (no changes needed unless counters need persistence across ticks)
- `scripts/little_loops/fsm/validation.py` — FSM config validation; must validate new throttle fields (`normal_max < warn_max < hard_max`)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for FSM loops; needs throttle block added (regenerate with `ll-generate-schemas` after schema.py changes)
- `scripts/little_loops/loops/lib/common.yaml:49-62` — `with_rate_limit_handling` fragment; add parallel `with_throttle` fragment here (NOT in `templates/` — see research note below)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/layout.py:190-215` — `_collect_edges()` iterates `StateConfig` fields to build FSM diagram edges; must include `on_throttle_hard` or diagram silently drops that transition
- `scripts/little_loops/cli/loop/info.py` — imports `StateConfig`/`EvaluateConfig`; surfaces state config details in `ll-loop info` output; will need to display `throttle:` config block alongside evaluate/route

### Similar Patterns
- `scripts/little_loops/fsm/executor.py:181-210` — counter declaration block in `__init__` (`_retry_counts` at 181, `_rate_limit_retries` at 200, `_api_error_retries` at 210); `_throttle_counts: dict[str, int]` slots at line 211 (immediately after `_api_error_retries`)
- `scripts/little_loops/fsm/executor.py:1192-1200` — storm detection increment + threshold check + `_emit()`; direct structural analog for warn/hard/stop thresholds
- `scripts/little_loops/fsm/executor.py:285` — `_retry_counts.pop(_prev_state, None)` on state change; same reset point for `_throttle_counts`
- `scripts/little_loops/fsm/executor.py:307-332` — `max_retries` exhaustion with forced state transition; model for `hard_max` transition logic
- `scripts/little_loops/fsm/schema.py:298-302` — rate-limit flat scalar fields on `StateConfig`; throttle fields would follow this flat-field pattern OR use a nested `ThrottleConfig` dataclass (like `EvaluateConfig`) per the issue's nested YAML spec

### Tests
- `scripts/tests/test_fsm_executor.py:4584` — `TestRateLimitRetries` class; model new `TestThrottling` class after this (factory, event-capture, `patch.multiple` for module constants)
- `scripts/tests/test_fsm_executor.py:4866` — `TestRateLimitStorm` (3-state chained FSM, event assertion pattern); model multi-threshold tests here
- `scripts/tests/test_fsm_schema.py` — add tests for throttle field deserialization (present/absent/invalid)
- `scripts/tests/test_fsm_validation.py` — add tests for `normal_max < warn_max < hard_max` ordering validation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:613-662` — `TestRateLimitHandlingFragment` class exists here; add parallel `TestThrottleFragment` class testing `with_throttle` fragment exists in `common.yaml`, has a description, carries default throttle fields, and resolves correctly through `resolve_fragments`
- `scripts/tests/test_generate_schemas.py:17-19` — count assertion `== 23` must change to `== 26`; add `"throttle_warn"`, `"throttle_hard"`, `"throttle_stop"` to the `expected` set at lines 23-48
- `scripts/tests/test_builtin_loops.py:29-94` — `test_all_validate_as_valid_fsm` enforces correct `ThrottleConfig.from_dict()` wiring once a built-in loop YAML includes `throttle:`; `test_expected_loops_exist` at lines 46-94 must be updated if a new loop YAML is added
- `scripts/tests/test_enh1115_doc_wiring.py` — new file; follow `test_enh1138_doc_wiring.py` / `test_enh1146_doc_wiring.py` pattern; assert `throttle_warn`/`throttle_hard`/`throttle_stop` in `EVENT-SCHEMA.md`, `ThrottleConfig` in `API.md` Quick Import block, throttle fields in `CONFIGURATION.md`

### Documentation
- `docs/reference/CONFIGURATION.md:81-85,342-345` — existing rate-limit config reference; add throttle block alongside
- `docs/reference/EVENT-SCHEMA.md:247-298` — existing rate-limit event schema section; add `throttle_warn`, `throttle_hard`, `throttle_stop` events
- `docs/guides/LOOPS_GUIDE.md` — loop usage guide; add throttle configuration section
- `docs/generalized-fsm-loop.md` — FSM design doc; update with throttle block spec
- `skills/analyze-loop/SKILL.md:115-177` — Signal Rules step; add throttle event classification rules

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3749-3751` — Quick Import block lists exported symbols from `little_loops.fsm`; add `ThrottleConfig`, `THROTTLE_WARN_EVENT`, `THROTTLE_HARD_EVENT`, `THROTTLE_STOP_EVENT`
- `docs/reference/API.md:3854-3881` — `StateConfig` dataclass field documentation; add `throttle: ThrottleConfig | None` field entry
- `skills/create-loop/reference.md:939-981` — dedicated rate-limit state fields subsection; add peer `throttle:` block subsection covering `normal_max`, `warn_max`, `hard_max`, `on_throttle_hard`
- `skills/create-loop/loop-types.md:789-798` — harness-loop YAML example with inline rate-limit comments; add `throttle:` block alongside as an optional field
- `docs/reference/CLI.md:1205` — states "22 LLEvent types"; update count after adding 3 throttle event schemas
- `docs/reference/OUTPUT_STYLING.md:57-61` — edge color mappings for `rate_limit_exhausted`, `rate_limit_waiting`; add `on_throttle_hard` entry to `_collect_edges()` edge label color dict
- `docs/reference/COMMANDS.md:537` — analyze-loop heuristics list `rate_limit_exhausted` and `rate_limit_waiting`; add throttle event classification bullet

### Configuration
- `scripts/little_loops/fsm/executor.py:51-60` — module-level `_DEFAULT_*` constants are where FSM rate-limit defaults live (NOT `templates/`); add `_DEFAULT_THROTTLE_NORMAL_MAX`, `_DEFAULT_THROTTLE_WARN_MAX`, `_DEFAULT_THROTTLE_HARD_MAX` here
- `scripts/little_loops/loops/lib/common.yaml:49-62` — `with_rate_limit_handling` fragment; add parallel `with_throttle` fragment with explicit default values for states that opt in

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py:378-412` (`get_referenced_states`) — must include `on_throttle_hard` if it becomes a state-reference field on `StateConfig`; without this, the FSM reachability validator at `validation.py:415` emits false "unreachable state" warnings for states targeted only by `on_throttle_hard`
- `scripts/little_loops/fsm/persistence.py:449-474` (`_save_state`) — **PERSISTENCE DECISION RESOLVED**: `_throttle_counts` is NOT serialized to `LoopState`; throttle counters reset on loop resume. Rationale: throttle counts measure "calls within a single continuous state visit" — resuming starts a fresh visit. Unlike `_retry_counts`/`_rate_limit_retries` (which track cumulative across interruptions and are restored at `resume:539-545`), throttle counts are instantaneous visit-level state. No changes to `persistence.py` or `LoopState` are needed.
- `scripts/little_loops/fsm/fsm-loop-schema.json:175-321` — stateConfig definition; `"additionalProperties": false` at line 320 means any YAML with a `throttle:` block fails schema validation until `throttle` is added as a nested object property — this file is hand-maintained, not regenerated by `ll-generate-schemas`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Schema design choice**: Existing rate-limit config uses flat scalar fields on `StateConfig` (`schema.py:245-251`). The issue specifies a nested `throttle:` YAML block. This is a deliberate design departure toward a nested `ThrottleConfig` dataclass (like `EvaluateConfig`) rather than flat fields like `throttle_normal_max`. Either works; the nested approach matches the issue spec and is more readable in YAML.
- **Templates/ clarification**: The issue says "defaults live in `templates/`" — this is incorrect. The `templates/` directory holds ll-config project-type templates (e.g. `generic.json`), not FSM loop defaults. FSM defaults use module constants in `executor.py` + reusable fragments in `loops/lib/common.yaml`.
- **Event export**: New throttle event constants (e.g. `THROTTLE_WARN_EVENT`, `THROTTLE_HARD_EVENT`, `THROTTLE_STOP_EVENT`) must be exported from `fsm/__init__.py:90-92` alongside existing rate-limit event exports.
- **Counter increment location**: `executor.py:533` and `executor.py:557` — the call sites of `_run_action_or_route` inside `_execute_state` — are the natural increment points (after each action call for the current state).
- **Validation rule**: `validation.py` should enforce `normal_max < warn_max < hard_max` and that all three are positive integers when `throttle:` is present.

_Updated by `/ll:refine-issue` 2026-05-11 — implementation status sweep:_

**Core implementation is already complete.** The following acceptance criteria are met:
- `ThrottleConfig` dataclass in `schema.py:228` with `from_dict`/`to_dict`, `throttle` + `on_throttle_hard` fields on `StateConfig:353-354`, `get_referenced_states` updated at `schema.py:519-520`
- Default constants `_DEFAULT_THROTTLE_NORMAL_MAX/WARN_MAX/HARD_MAX` in `executor.py:73-75`; `THROTTLE_WARN/HARD/STOP_EVENT` constants at `executor.py:77-79` and exported from `__init__.py:94-96`
- `_throttle_counts: dict[str, int]` at `executor.py:224`; reset at `executor.py:305`; `_check_throttle()` method at `executor.py:548` with warn/hard/stop logic and learning-state exemption at `executor.py:591-593`
- Called at `executor.py:645` and `executor.py:674` (formerly 533/557 — shifted by implementation)
- `validation.py:539-571` enforces `normal_max < warn_max < hard_max` ordering and positive-integer checks
- `fsm-loop-schema.json:347-373` — `throttle` block and `on_throttle_hard` field added (hand-maintained file updated)
- `generate_schemas.py` has throttle event schemas; `test_generate_schemas.py` count updated to 26
- `layout.py:214-215` — `on_throttle_hard` edge added to `_collect_edges()`
- `with_throttle` fragment in `common.yaml:64-75`
- `TestThrottling` class in `test_fsm_executor.py:5976` covering warn, hard, stop, fallback, counter-reset, per-state override, and learning-state exemption (`test_learning_state_exempt_from_hard_max:6188`)
- `TestThrottleFragment` implied by fragment existence; `test_fsm_validation.py:486` covers throttle validation
- `test_enh1115_doc_wiring.py` exists; `CONFIGURATION.md:482-492`, `API.md:3965-3977` updated

**Two acceptance criteria REMAIN UNMET** (these are the only implementation gaps):

1. **No built-in loop template uses `throttle:` block** — `autodev.yaml` and `recursive-refine.yaml` confirmed to have no `throttle:` entry. Step 6 of the implementation plan targets these files.

2. **`/ll:analyze-loop` does not surface throttle events** — The skill referenced as `analyze-loop` in this issue no longer exists; it was replaced by `skills/audit-loop-run/` and `skills/debug-loop-run/`. Neither skill's `SKILL.md` references throttle events. Step 8 should target `skills/audit-loop-run/SKILL.md` instead of `skills/analyze-loop/SKILL.md`.

## Implementation Steps

1. **Schema** (`scripts/little_loops/fsm/schema.py:245-251`): Add optional `ThrottleConfig` dataclass with `normal_max`, `warn_max`, `hard_max: int | None = None` fields; add `throttle: ThrottleConfig | None = None` to `StateConfig`; add `from_dict`/`to_dict` handling following the `EvaluateConfig` nested pattern; add validation rule `normal_max < warn_max < hard_max` in `scripts/little_loops/fsm/validation.py`
2. **Executor defaults** (`scripts/little_loops/fsm/executor.py:51-60`): Add `_DEFAULT_THROTTLE_NORMAL_MAX = 3`, `_DEFAULT_THROTTLE_WARN_MAX = 8`, `_DEFAULT_THROTTLE_HARD_MAX = 12` alongside existing `_DEFAULT_RATE_LIMIT_*` constants
3. **Executor counter** (`scripts/little_loops/fsm/executor.py:211`): Add `self._throttle_counts: dict[str, int] = {}` in `__init__` (after `_api_error_retries` at line 210); reset at `executor.py:285` (same block as `_retry_counts.pop`) when state changes; increment at `executor.py:533` / `executor.py:557` after each `_run_action_or_route` call; **do NOT serialize to `LoopState`** — reset on resume (see persistence decision below)
4. **Threshold logic**: Resolve thresholds from `state.throttle` (if set) else `_DEFAULT_THROTTLE_*`; after increment: if `count == warn_threshold` emit `THROTTLE_WARN_EVENT`; if `count == hard_threshold` emit `THROTTLE_HARD_EVENT` and transition to `state.on_throttle_hard` (or `on_error`); if `count > hard_threshold` call `_finish("error", ...)` and emit `THROTTLE_STOP_EVENT`, mark as stuck
5. **Event exports** (`scripts/little_loops/fsm/__init__.py:90-92`): Export `THROTTLE_WARN_EVENT`, `THROTTLE_HARD_EVENT`, `THROTTLE_STOP_EVENT`; regenerate `fsm-loop-schema.json` via `ll-generate-schemas`
6. **Fragment** (`scripts/little_loops/loops/lib/common.yaml:49-62`): Add `with_throttle` fragment with explicit `throttle:` defaults; add `throttle:` block to `autodev.yaml` or `recursive-refine.yaml` as the required built-in example
7. **Tests** (`scripts/tests/test_fsm_executor.py:4584`): Add `TestThrottling` class modeled on `TestRateLimitRetries`; use `patch.multiple("little_loops.fsm.executor", _DEFAULT_THROTTLE_*)` for instant runs; cover warn-only, hard-transition, and stop-beyond-hard cases; add schema tests in `test_fsm_schema.py` and validation tests in `test_fsm_validation.py`
8. **Telemetry** (`skills/audit-loop-run/SKILL.md`): Add throttle event classification rules (the `skills/analyze-loop/` path no longer exists — replaced by `audit-loop-run` and `debug-loop-run`); update `docs/reference/EVENT-SCHEMA.md:247-298`, `docs/reference/CONFIGURATION.md:81-85`, and `docs/guides/LOOPS_GUIDE.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `schema.py:378-412` (`get_referenced_states`) to include `on_throttle_hard` — required so FSM reachability validator does not emit false "unreachable state" warnings for states targeted only by `on_throttle_hard`
10. Update `fsm-loop-schema.json:175-321` manually — add `throttle` as a nested object property to the `stateConfig` definition; `"additionalProperties": false` at line 320 blocks any YAML with a `throttle:` block until this is done; this file is hand-maintained, NOT regenerated by `ll-generate-schemas`
11. Update `generate_schemas.py:82` — add `throttle_warn`, `throttle_hard`, `throttle_stop` event schema definitions; count 23→26; run `ll-generate-schemas` to regenerate event-type schemas in `docs/reference/schemas/`
12. Update `layout.py:204,30-37` — add `on_throttle_hard` to `_collect_edges()` and add `"throttle_hard"` color entry to edge label color dict; otherwise FSM diagram silently drops the `on_throttle_hard` transition edge
13. Update `test_generate_schemas.py:17-19` — count assertion 23→26; add `"throttle_warn"`, `"throttle_hard"`, `"throttle_stop"` to the `expected` set
14. Add `TestThrottleFragment` class to `test_fsm_fragments.py:613-662` — parallel to `TestRateLimitHandlingFragment`; assert fragment exists in `common.yaml`, has a description, carries default throttle field values, resolves through `resolve_fragments`
15. Create `test_enh1115_doc_wiring.py` — follow `test_enh1138_doc_wiring.py` / `test_enh1146_doc_wiring.py` pattern; assert `throttle_warn`/`throttle_hard`/`throttle_stop` in `EVENT-SCHEMA.md`, `ThrottleConfig` in `API.md` Quick Import block, throttle fields in `CONFIGURATION.md`
16. Update `docs/reference/API.md:3749-3751,3854-3881` — add `ThrottleConfig` + new constants to Quick Import block; add `throttle: ThrottleConfig | None` to `StateConfig` field documentation
17. Update `skills/create-loop/reference.md:939-981` — add `throttle:` block peer subsection alongside existing rate-limit fields subsection
18. Update `skills/create-loop/loop-types.md:789-798` — add `throttle:` to harness-loop YAML example alongside rate-limit inline comments
19. Update `docs/reference/CLI.md:1205` (event type count), `docs/reference/COMMANDS.md:537` (analyze-loop heuristics), `docs/reference/OUTPUT_STYLING.md:57-61` (edge color for `on_throttle_hard`)

## Impact

- **Priority**: P3 — Quality-of-life improvement for runaway loop prevention; non-blocking
- **Effort**: Medium — Schema changes, executor counter logic, threshold-check wiring, and test coverage; builds on existing rate-limit infrastructure
- **Risk**: Low — New optional config section with safe defaults; omitting `throttle:` leaves existing loop behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `loops`, `throttling`, `captured`

## Status

**Open** | Created: 2026-04-15 | Priority: P3

## References

- Inspiration: context-mode progressive throttling on search calls
- Builds on: recent FSM rate-limit work (`fa02a186`, `95b4fed2`, `c8ea14e9`, `8dba4536`)

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23; re-verified 2026-05-03; line numbers corrected 2026-05-06

- No `throttle:` section in FSM state config schema (`scripts/little_loops/fsm/schema.py`) ✓
- No per-state tool-call counter in FSM executor ✓
- Feature not yet implemented ✓
- **Line numbers corrected** (2026-05-06): All executor.py references updated to current state. Key current lines: counter block 181-210 (slot at 211), storm detection 1192-1200, retry pop at 285, max_retries exhaustion 307-332, `_run_action_or_route` call sites at 533/557. Schema rate-limit fields now at 298-302. Persistence decision resolved (no `LoopState` changes needed).
- **Persistence decision resolved** (2026-05-06): `_throttle_counts` resets on resume — not serialized to `LoopState`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-06 (updated from 2026-04-24)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- **File breadth (29+ touchpoints)**: `fsm-loop-schema.json:175-321` is hand-maintained with `"additionalProperties": false` at line 320 — any `throttle:` YAML silently fails schema validation until manually updated; doc-count assertions (`test_generate_schemas.py:17-19` count 23→26, `docs/reference/CLI.md:1205` event-type count) are easy to miss.
- **Silent diagram regression**: `layout.py:204` `_collect_edges()` must include `on_throttle_hard` — omitting it drops the FSM diagram transition with no error or test failure to catch it.
- **Learning-state exemption gap**: The `type == "learning"` hard-stop exemption (scope boundary added 2026-05-04) has no dedicated behavioral test yet — `test_enh1115_doc_wiring.py` is doc-focused; a test for learning-state throttle bypass needs to be added to `TestThrottling`.

## Tradeoff Review Note

**Reviewed**: 2026-04-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | HIGH |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — Resolve the persistence decision at `persistence.py:457-460` before starting implementation: should `_throttle_counts` survive loop resume/handoff across ticks, or reset on resume? This determines whether step 3 (`__init__` counter) and `LoopState` serialization need changes. Without a decision, step 3 has an open implementation branch that could cause silent behavioral differences between resumed and fresh loops. Decide and document in the issue before coding.

---

## Resolution

**Completed**: 2026-05-11

The two remaining acceptance criteria were addressed:

1. **Built-in loop template with `throttle:` block** — Added `fragment: with_throttle` and `on_throttle_hard: enqueue_or_skip` to the `run_size_review` state in `scripts/little_loops/loops/recursive-refine.yaml`. This provides a defensive throttle guard on the slash-command state that runs `/ll:issue-size-review`.

2. **`/ll:analyze-loop` surfaces throttle events** — Updated both loop analysis skills (the successors to `analyze-loop`):
   - `skills/debug-loop-run/SKILL.md`: Added `throttle_warn`, `throttle_hard`, `throttle_stop` to the Step 2 event table; added `BUG — Throttle hard stop`, `ENH — Throttle hard transition`, and `NOTE — Throttle warnings` signal classification rules after the rate-limit exhaustion rule.
   - `skills/audit-loop-run/SKILL.md`: Added throttle hard stop/transition to the Phase 1 fault signals list (Step 5).

All 318 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-05-11T21:01:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-11T20:55:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04014a8f-cb78-4e0c-a7dd-92bb73605fc6.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d387013f-4383-4764-82e2-3c331dc1a687.jsonl`
- `/ll:refine-issue` - 2026-05-11T20:40:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e0e03e2a-39f4-49de-8637-407748f778a5.jsonl`
- `/ll:ready-issue` - 2026-05-06T19:27:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1022c87-10c1-48b8-b1ff-f52294d8bdcb.jsonl`
- `/ll:confidence-check` - 2026-05-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1898cad7-7a7c-462d-9a8e-633b83916b6e.jsonl`
- `/ll:refine-issue` - 2026-05-06T19:13:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df8da1ea-1180-4953-9482-243f9d2b5acf.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-05T02:27:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d743dae1-3278-4abd-a763-b23632abd3cb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:tradeoff-review-issues` - 2026-04-27T02:55:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d048a1c-d492-434e-87b2-d34bc1ea2f6c.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:confidence-check` - 2026-04-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/baf6354e-f895-4724-a14b-8b08bc94c4ee.jsonl`
- `/ll:wire-issue` - 2026-04-24T21:07:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e9e8880-2acc-4d17-bd55-40513e4f3106.jsonl`
- `/ll:refine-issue` - 2026-04-24T20:57:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/393f5547-5641-4053-b11e-6e1d77f12ffc.jsonl`
- `/ll:format-issue` - 2026-04-24T20:51:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/952d3167-9cab-4483-a9fb-ad8fd963a3fa.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The new per-state tool-call counter MUST follow the existing `_retry_counts` dict pattern already in `FSMExecutor.__init__` (not a separate parallel dict). The counter must be reset in the same location where state-exit resets are performed (~line 285 of `scripts/little_loops/fsm/executor.py`). Reference `_retry_counts` and `_rate_limit_retries` as the implementation template to avoid a divergent counter with different reset semantics.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `type: learning` states (FEAT-1283) are exempt from the `hard_max` hard-stop. A learning state executes one `ll:explore-api` call per unproven target in sequence — with N targets, it legitimately makes N calls per state visit, which easily exceeds the default `hard_max` of 9. The throttle counter MUST check `state_config.type` before firing: if `type == "learning"`, skip the `hard_max` check entirely (the learning state has its own `max_retries` gate). The `warn_max` warning injection still applies at its threshold so users know the state is doing significant work. Document the learning-state exemption in the `ThrottleConfig` docstring and in the `with_throttle` fragment description in `scripts/little_loops/loops/lib/common.yaml`.
