---
id: ENH-1115
type: ENH
priority: P3
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
related: []
decision_needed: false
confidence_score: 100
outcome_confidence: 53
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
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
- `scripts/little_loops/fsm/persistence.py:407-434` — `_handle_event` writes all executor events to `.loops/.running/<name>.events.jsonl`; throttle events are automatically captured if emitted (no changes needed unless counters need persistence across ticks)
- `scripts/little_loops/fsm/validation.py` — FSM config validation; must validate new throttle fields (`normal_max < warn_max < hard_max`)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for FSM loops; needs throttle block added (regenerate with `ll-generate-schemas` after schema.py changes)
- `scripts/little_loops/loops/lib/common.yaml:49-62` — `with_rate_limit_handling` fragment; add parallel `with_throttle` fragment here (NOT in `templates/` — see research note below)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/layout.py:190-215` — `_collect_edges()` iterates `StateConfig` fields to build FSM diagram edges; must include `on_throttle_hard` or diagram silently drops that transition
- `scripts/little_loops/cli/loop/info.py` — imports `StateConfig`/`EvaluateConfig`; surfaces state config details in `ll-loop info` output; will need to display `throttle:` config block alongside evaluate/route

### Similar Patterns
- `scripts/little_loops/fsm/executor.py:197-201` — `_consecutive_rate_limit_exhaustions` counter declaration in `__init__`; same pattern for per-state tool-call counter (`_throttle_counts: dict[str, int]`)
- `scripts/little_loops/fsm/executor.py:1136-1144` — storm detection increment + threshold check + `_emit()`; direct structural analog for warn/hard/stop thresholds
- `scripts/little_loops/fsm/executor.py:276` — `_retry_counts.pop(_prev_state, None)` on state change; same reset point for `_throttle_counts`
- `scripts/little_loops/fsm/executor.py:300-323` — `max_retries` exhaustion with forced state transition; model for `hard_max` transition logic
- `scripts/little_loops/fsm/schema.py:245-251` — rate-limit flat scalar fields on `StateConfig`; throttle fields would follow this flat-field pattern OR use a nested `ThrottleConfig` dataclass (like `EvaluateConfig`) per the issue's nested YAML spec

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
- `scripts/little_loops/fsm/persistence.py:457-460` (`_save_state`) — decision point: currently saves `retry_counts` and `rate_limit_retries`; if `_throttle_counts` must survive resume/handoff across ticks, add to `LoopState` serialization here; if counters reset on resume, no change needed
- `scripts/little_loops/fsm/fsm-loop-schema.json:175-321` — stateConfig definition; `"additionalProperties": false` at line 320 means any YAML with a `throttle:` block fails schema validation until `throttle` is added as a nested object property — this file is hand-maintained, not regenerated by `ll-generate-schemas`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Schema design choice**: Existing rate-limit config uses flat scalar fields on `StateConfig` (`schema.py:245-251`). The issue specifies a nested `throttle:` YAML block. This is a deliberate design departure toward a nested `ThrottleConfig` dataclass (like `EvaluateConfig`) rather than flat fields like `throttle_normal_max`. Either works; the nested approach matches the issue spec and is more readable in YAML.
- **Templates/ clarification**: The issue says "defaults live in `templates/`" — this is incorrect. The `templates/` directory holds ll-config project-type templates (e.g. `generic.json`), not FSM loop defaults. FSM defaults use module constants in `executor.py` + reusable fragments in `loops/lib/common.yaml`.
- **Event export**: New throttle event constants (e.g. `THROTTLE_WARN_EVENT`, `THROTTLE_HARD_EVENT`, `THROTTLE_STOP_EVENT`) must be exported from `fsm/__init__.py:90-92` alongside existing rate-limit event exports.
- **Counter increment location**: `executor.py:481` and `executor.py:504` — the call sites of `_run_action_or_route` inside `_execute_state` — are the natural increment points (after each action call for the current state).
- **Validation rule**: `validation.py` should enforce `normal_max < warn_max < hard_max` and that all three are positive integers when `throttle:` is present.

## Implementation Steps

1. **Schema** (`scripts/little_loops/fsm/schema.py:245-251`): Add optional `ThrottleConfig` dataclass with `normal_max`, `warn_max`, `hard_max: int | None = None` fields; add `throttle: ThrottleConfig | None = None` to `StateConfig`; add `from_dict`/`to_dict` handling following the `EvaluateConfig` nested pattern; add validation rule `normal_max < warn_max < hard_max` in `scripts/little_loops/fsm/validation.py`
2. **Executor defaults** (`scripts/little_loops/fsm/executor.py:51-60`): Add `_DEFAULT_THROTTLE_NORMAL_MAX = 3`, `_DEFAULT_THROTTLE_WARN_MAX = 8`, `_DEFAULT_THROTTLE_HARD_MAX = 12` alongside existing `_DEFAULT_RATE_LIMIT_*` constants
3. **Executor counter** (`scripts/little_loops/fsm/executor.py:197-201`): Add `self._throttle_counts: dict[str, int] = {}` in `__init__`; reset at `executor.py:276` (same block as `_retry_counts.pop`) when state changes; increment at `executor.py:481` / `executor.py:504` after each `_run_action_or_route` call
4. **Threshold logic**: Resolve thresholds from `state.throttle` (if set) else `_DEFAULT_THROTTLE_*`; after increment: if `count == warn_threshold` emit `THROTTLE_WARN_EVENT`; if `count == hard_threshold` emit `THROTTLE_HARD_EVENT` and transition to `state.on_throttle_hard` (or `on_error`); if `count > hard_threshold` call `_finish("error", ...)` and emit `THROTTLE_STOP_EVENT`, mark as stuck
5. **Event exports** (`scripts/little_loops/fsm/__init__.py:90-92`): Export `THROTTLE_WARN_EVENT`, `THROTTLE_HARD_EVENT`, `THROTTLE_STOP_EVENT`; regenerate `fsm-loop-schema.json` via `ll-generate-schemas`
6. **Fragment** (`scripts/little_loops/loops/lib/common.yaml:49-62`): Add `with_throttle` fragment with explicit `throttle:` defaults; add `throttle:` block to `autodev.yaml` or `recursive-refine.yaml` as the required built-in example
7. **Tests** (`scripts/tests/test_fsm_executor.py:4584`): Add `TestThrottling` class modeled on `TestRateLimitRetries`; use `patch.multiple("little_loops.fsm.executor", _DEFAULT_THROTTLE_*)` for instant runs; cover warn-only, hard-transition, and stop-beyond-hard cases; add schema tests in `test_fsm_schema.py` and validation tests in `test_fsm_validation.py`
8. **Telemetry** (`skills/analyze-loop/SKILL.md:115-177`): Add throttle event classification rules; update `docs/reference/EVENT-SCHEMA.md:247-298`, `docs/reference/CONFIGURATION.md:81-85`, and `docs/guides/LOOPS_GUIDE.md`

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

**Verdict**: VALID — Verified 2026-04-23; re-verified 2026-05-03

- No `throttle:` section in FSM state config schema (`scripts/little_loops/fsm/schema.py`) ✓
- No per-state tool-call counter in FSM executor ✓
- Feature not yet implemented ✓
- **Line number drift** (2026-05-03): `executor.py:197-201` reference is stale — `_consecutive_rate_limit_exhaustions` counter declaration is now at line **205**; storm detection cited as `1136-1144` is now at **1180-1186**. Update Implementation Steps 2–3 accordingly before starting.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-24_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 53/100 → LOW

### Outcome Risk Factors
- **File count breadth**: 20+ touchpoints (mostly additive), but `fsm-loop-schema.json` hand-maintenance (line 320 `"additionalProperties": false`) and doc-count assertions (`test_generate_schemas.py:17-19`, `docs/reference/CLI.md:1205`) are high-miss-risk items not auto-updated.
- **Persistence decision unresolved**: Whether `_throttle_counts` survives loop resume (persistence.py:457-460) is flagged as an open decision — resolve before implementing step 3.
- **Silent diagram regression**: `layout.py:204` must include `on_throttle_hard` in `_collect_edges()` — omitting it drops the transition from FSM diagrams without any error or failing test.

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

## Session Log
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:tradeoff-review-issues` - 2026-04-27T02:55:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d048a1c-d492-434e-87b2-d34bc1ea2f6c.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:confidence-check` - 2026-04-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/baf6354e-f895-4724-a14b-8b08bc94c4ee.jsonl`
- `/ll:wire-issue` - 2026-04-24T21:07:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e9e8880-2acc-4d17-bd55-40513e4f3106.jsonl`
- `/ll:refine-issue` - 2026-04-24T20:57:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/393f5547-5641-4053-b11e-6e1d77f12ffc.jsonl`
- `/ll:format-issue` - 2026-04-24T20:51:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/952d3167-9cab-4483-a9fb-ad8fd963a3fa.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
