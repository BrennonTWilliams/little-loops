---
parent: BUG-1105
priority: P2
type: BUG
size: Large
confidence_score: 95
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# BUG-1108: StateConfig Schema, Validation, Signal Detection, Config, and UI for Rate Limit Handling

## Summary

Decomposed from BUG-1105: FSM Loops Silently Skip All Work on 429 Rate Limit Failures.

This child covers the data model layer and all wiring that surrounds the core executor change: new `StateConfig` fields, paired validation, JSON schema update, `RATE_LIMIT_STORM` signal rule, schema registry entry, diagram edge rendering, user-configurable edge colors, `with_rate_limit_handling` fragment in `common.yaml`, and opt-in wiring in the affected loop YAML configs.

## Scope

### StateConfig Schema (schema.py)

Add `max_rate_limit_retries: int`, `on_rate_limit_exhausted: str`, and `rate_limit_backoff_base_seconds: int` fields using the exact 5-part pattern from `max_retries` / `on_retry_exhausted`:
1. Docstring (`schema.py:187-211`)
2. Field declaration (`schema.py:228-229`) — `rate_limit_backoff_base_seconds` defaults to `30`
3. `to_dict` serialization (`schema.py:270-273`)
4. `from_dict` deserialization + register `on_rate_limit_exhausted` in `_known_on_keys` set (`schema.py:305-338`)
5. `get_referenced_states` (`schema.py:362-363`) — `on_rate_limit_exhausted` only; `rate_limit_backoff_base_seconds` is not a state reference

### Paired Validation (validation.py)

Add validation at `validation.py:280-301` (mirror of `max_retries` / `on_retry_exhausted` paired validation): `max_rate_limit_retries` and `on_rate_limit_exhausted` required together; `max_rate_limit_retries >= 1`. Also validate `rate_limit_backoff_base_seconds >= 1` when present (standalone — does not require the paired fields).

### JSON Schema (fsm-loop-schema.json)

Update JSON Schema for the two new `StateConfig` fields.

### RATE_LIMIT_STORM Detection (executor.py — NOT signal_detector.py)

**Decision (2026-04-14)**: RATE_LIMIT_STORM is an executor-level event, not a `SignalPattern`. `SignalPattern` only does regex matching on a single `action.output`; consecutive-exhaustion detection spans multiple states/actions and is fundamentally stateful cross-invocation telemetry. Implement in `executor.py`:

1. Add `self._consecutive_rate_limit_exhaustions: int = 0` to executor state (alongside existing `self._rate_limit_retries`)
2. On `rate_limit_exhausted` event emission (existing site near `executor.py:487`): increment the counter
3. On any successful non-rate-limited state transition: reset counter to 0
4. When counter reaches threshold (hardcode `3` for this issue; configurability deferred): emit new `RATE_LIMIT_STORM` LLEvent with payload `{"count": N, "state": state_name}` and halt via the existing `on_rate_limit_exhausted` / `on_error` routing path
5. No changes to `signal_detector.py`, `fsm/__init__.py` re-exports, or `test_signal_detector.py`

### Schema Registry (generate_schemas.py)

Add **two** entries to `SCHEMA_DEFINITIONS` at `generate_schemas.py:78-290` (manual registry, not auto-discovered):
1. `rate_limit_exhausted` — existing executor event from BUG-1107 that is missing from the registry
2. `rate_limit_storm` — new executor event added by this issue

Update FSM Executor sub-section comment from `(11 types)` to `(13 types)`. Update count docstring in `cli/schemas.py:15` (19 → 21).

### Config + UI (config/cli.py, config/core.py, layout.py)

- `config/cli.py:86` — add `rate_limit_exhausted: str` color field to `CliColorsEdgeLabelsConfig` (parallel to `retry_exhausted: str`)
- `config/core.py:475-484` — add `"rate_limit_exhausted"` to the `fsm_edge_labels` dict in `BRConfig.to_dict()`
- `layout.py:27-36` — add `"rate_limit_exhausted"` to `_EDGE_LABEL_COLORS` dict
- `layout.py:62-74` — add `"rate_limit_exhausted"` to `_edge_line_color()` priority tuple
- `layout.py:201-202` — add `on_rate_limit_exhausted` diagram edge (mirrors `on_retry_exhausted`)

### Fragment Library (common.yaml)

**Decision (2026-04-14)**: The original interpolation-based fragment design does NOT work. Fragment resolution runs at YAML parse time (`fragments.py:64` → `_deep_merge`) and merges fragment fields into state dicts as literal strings; `StateConfig.from_dict` then type-coerces them into typed fields. Interpolation only runs at execution time on specific string fields (routes, action templates, `evaluate.source`). A fragment setting `max_rate_limit_retries: ${context.rate_limit_retries}` would hand `StateConfig.from_dict` a literal string and crash int coercion.

Add `with_rate_limit_handling` fragment to `scripts/little_loops/loops/lib/common.yaml` with **literal defaults** matching current executor behavior:

```yaml
with_rate_limit_handling:
  description: |
    Applies per-state rate-limit retry handling with 3 retries and 30s base backoff.
    State must supply: on_rate_limit_exhausted (target state name when retries exhausted).
    State may override: max_rate_limit_retries, rate_limit_backoff_base_seconds.
  max_rate_limit_retries: 3
  rate_limit_backoff_base_seconds: 30
```

States opt in with:
```yaml
implement:
  fragment: with_rate_limit_handling
  on_rate_limit_exhausted: halt
  # ... rest of state
```

The literal `3` and `30` match the current `_DEFAULT_RATE_LIMIT_RETRIES` / `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` constants at `executor.py:50,52`, preserving behavior. States that need different counts set `max_rate_limit_retries:` directly — fragment deep-merge lets state-level fields override fragment defaults (`fragments.py:139`). Must include non-empty `description` (or `test_all_common_yaml_fragments_have_description` at `test_fsm_fragments.py:945` will fail).

### Loop YAML Configs

Apply the fragment in `auto-refine-and-implement` and `recursive-refine` where per-state exhaustion routing is needed. Both already import `lib/common.yaml` (`auto-refine-and-implement.yaml:12-13`, `recursive-refine.yaml:23-24`), so only fragment application is required — no new `import:` block needed.

## Files to Modify

- `scripts/little_loops/fsm/schema.py`
- `scripts/little_loops/fsm/validation.py`
- `scripts/little_loops/fsm/fsm-loop-schema.json`
- `scripts/little_loops/generate_schemas.py` — add both `rate_limit_exhausted` and `rate_limit_storm` entries
- `scripts/little_loops/cli/schemas.py`
- `scripts/little_loops/config/cli.py`
- `scripts/little_loops/config/core.py`
- `scripts/little_loops/cli/loop/layout.py`
- `scripts/little_loops/loops/lib/common.yaml`
- Affected loop YAML configs (`auto-refine-and-implement.yaml`, `recursive-refine.yaml`)
- `scripts/little_loops/fsm/executor.py` — (a) replace `_DEFAULT_RATE_LIMIT_RETRIES = 3` (`executor.py:50`) and `_DEFAULT_RATE_LIMIT_BACKOFF_BASE = 30` (`executor.py:52`) with reads from `route_ctx.state.max_rate_limit_retries` / `route_ctx.state.rate_limit_backoff_base_seconds`. Current call sites to update: `executor.py:483` (retry cap check), `executor.py:491` (event payload `retries` field), `executor.py:500-501` (backoff sleep computation). `RATE_LIMIT_EXHAUSTED_EVENT` at `executor.py:54` — reuse it. (b) Add `RATE_LIMIT_STORM_EVENT = "rate_limit_storm"` constant. (c) Add `self._consecutive_rate_limit_exhaustions: int = 0` to executor state; increment on `rate_limit_exhausted` emission, reset on successful non-rate-limited transition, emit `RATE_LIMIT_STORM` event when count reaches 3. (d) Update routing lookup at `executor.py:486` from `state.extra_routes.get("rate_limit_exhausted") or state.on_error` to `state.on_rate_limit_exhausted or state.on_error`.
- `config-schema.json` — add `"rate_limit_exhausted"` property to `fsm_edge_labels` object (`config-schema.json:892-894`); the object has `additionalProperties: false` so this key must be explicitly declared alongside `retry_exhausted` at line 892. [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — imports `_EDGE_LABEL_COLORS` from `layout.py`; adding `rate_limit_exhausted` to the dict is backward-compatible and no additional change is required here
- `scripts/little_loops/fsm/__init__.py` — no changes required under Option A (RATE_LIMIT_STORM lives in `executor.py` as an event constant, not a signal_detector export)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:594` — `cli.colors.fsm_edge_labels` table lists `retry_exhausted`; add `rate_limit_exhausted` row (mirrors `retry_exhausted` with orange color `38;5;214` or similar)
- `docs/reference/OUTPUT_STYLING.md:59` — edge color table lists `retry_exhausted`; add `rate_limit_exhausted` row
- `docs/reference/OUTPUT_STYLING.md:203` — `_collect_edges()` description mentions `on_retry_exhausted ("retry_exhausted")`; add `on_rate_limit_exhausted ("rate_limit_exhausted")` 
- `docs/reference/OUTPUT_STYLING.md:214` — second edge color table; add `rate_limit_exhausted` row
- `docs/reference/EVENT-SCHEMA.md:207-220` — `retry_exhausted` event section with field table and JSON example; add parallel `rate_limit_exhausted` section (fields: `event`, `ts`, `state`, `retries`, `next`) AND `rate_limit_storm` section (fields: `event`, `ts`, `state`, `count`)
- `docs/reference/EVENT-SCHEMA.md:520` — schema file tree lists `retry_exhausted.json`; add `rate_limit_exhausted.json` and `rate_limit_storm.json`
- `docs/reference/EVENT-SCHEMA.md:603` — event source table lists `retry_exhausted`; add `rate_limit_exhausted` and `rate_limit_storm` rows
- `docs/guides/LOOPS_GUIDE.md:993-994` — StateConfig field reference table documents `max_retries` and `on_retry_exhausted`; add `max_rate_limit_retries`, `on_rate_limit_exhausted`, `rate_limit_backoff_base_seconds` entries
- `docs/reference/API.md:3786-3806` — `StateConfig` dataclass stub; add `max_rate_limit_retries`, `on_rate_limit_exhausted`, `rate_limit_backoff_base_seconds` fields (note: `max_retries`/`on_retry_exhausted` are absent from the stub here too — verify whether this doc lists all fields or a curated subset before deciding scope)
- `docs/generalized-fsm-loop.md:393-447` — documents `on_blocked` and routing shorthand fields; add `on_rate_limit_exhausted` alongside `on_blocked` in the routing fields section
- `skills/create-loop/reference.md:891-934` — has a dedicated `max_retries and on_retry_exhausted` reference section; add parallel `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds` section

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_generate_schemas.py:18,22-44,50,57,165` — **MAY_BREAK** (5 assertions): `assert len(SCHEMA_DEFINITIONS) == 19` (line 18); expected key set at lines 23-44 missing `"rate_limit_exhausted"` and `"rate_limit_storm"`; three file-count assertions all assert `== 19` (lines 50, 57, 165); update all counts to **21** and add **both** keys to expected set
- `scripts/tests/test_fsm_executor.py:4341,4359,4376,4395,4411,4441` — **MAY_BREAK**: `TestRateLimitRetries` class patches `little_loops.fsm.executor._DEFAULT_RATE_LIMIT_RETRIES` and `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` as module-level constants; once BUG-1108 replaces executor reads with `state.max_rate_limit_retries` / `state.rate_limit_backoff_base_seconds`, all six tests must construct `StateConfig` with the new fields instead of patching the module; also `executor.py:486` routing lookup changes from `state.extra_routes.get("rate_limit_exhausted")` to `state.on_rate_limit_exhausted` — `test_rate_limit_exhausted_routes_to_on_rate_limit_exhausted` (line 4395) uses `extra_routes={"rate_limit_exhausted": "exhausted"}` and will need updating
- `scripts/tests/test_fsm_schema.py:238-524` — **EXISTS/NEW_NEEDED**: follow the 6-test-per-field pattern used for `on_partial` (lines 284-340) and `on_blocked` (lines 342-398); add 18 new tests for the three new fields; also `test_extra_routes_in_from_dict` (line 408) **MAY_BREAK** — once `on_rate_limit_exhausted` is in `_known_on_keys`, it must NOT go to `extra_routes`; add an assertion confirming the new field is NOT captured there
- `scripts/tests/test_fsm_validation.py:1-67` — **NEW_NEEDED**: no paired-field validation tests exist for any field; add tests for both-or-neither (`max_rate_limit_retries` ↔ `on_rate_limit_exhausted`), `max_rate_limit_retries >= 1`, and `rate_limit_backoff_base_seconds >= 1` standalone
- `scripts/tests/test_signal_detector.py` — **NO CHANGE**: under Option A, RATE_LIMIT_STORM is an executor-level event, not a SignalPattern. The existing `test_default_patterns` assertion (`len == 3`, names == `{"handoff", "error", "stop"}`) remains valid.
- `scripts/tests/test_fsm_executor.py` — **NEW_NEEDED**: add `TestRateLimitStorm` class with tests for: (a) `_consecutive_rate_limit_exhaustions` increments on each `rate_limit_exhausted` emission, (b) counter resets on any successful non-rate-limited transition, (c) `RATE_LIMIT_STORM` event fires when counter reaches 3, (d) event payload contains `count` and `state` fields
- `scripts/tests/test_ll_loop_display.py:2378-2387` — **NEW_NEEDED**: mirror `test_collect_edges_includes_on_retry_exhausted` (line 2378) for `on_rate_limit_exhausted`; add `rate_limit_exhausted` edge color test
- `scripts/tests/test_config.py:1315-1325` — **NEW_NEEDED**: add assertion for `config.rate_limit_exhausted` default ANSI code in `test_defaults`; add to `to_dict` assertion block
- `scripts/tests/test_builtin_loops.py:843-846` — **NEW_NEEDED**: mirror `test_execute_has_max_retries` for `max_rate_limit_retries` once the fragment is applied to `auto-refine-and-implement` and `recursive-refine`
- `scripts/tests/test_fsm_fragments.py` — **NEW_NEEDED**: dedicated tests for `with_rate_limit_handling` fragment (mirroring `TestRealCommonYamlFragments`): fragment is defined, has `max_rate_limit_retries` and `on_rate_limit_exhausted` fields; `test_all_common_yaml_fragments_have_description` (line 945) will also run against the new fragment automatically
- `scripts/tests/test_fsm_executor.py` — **NOTE on MAY_BREAK scope**: existing `TestRateLimitRetries` tests (lines 4341-4467) will only break if stub constants (`_DEFAULT_RATE_LIMIT_RETRIES`, `_DEFAULT_RATE_LIMIT_BACKOFF_BASE`) are removed from the module namespace; if constants are kept as exported fallbacks, existing tests continue to pass but new **NEW_NEEDED** tests should verify that `StateConfig.max_rate_limit_retries` / `rate_limit_backoff_base_seconds` field values override the defaults when explicitly set

## Key Reference Points

- `schema.py:180-211` — `StateConfig` docstring; add `max_rate_limit_retries`, `on_rate_limit_exhausted`, `rate_limit_backoff_base_seconds` entries alongside `max_retries`/`on_retry_exhausted` (lines 203-207)
- `schema.py:228-229` — `max_retries`/`on_retry_exhausted` field declarations to mirror
- `schema.py:270-273` — `to_dict` serialization pattern for retry fields
- `schema.py:298-308` — `_known_on_keys` set; must add `"on_rate_limit_exhausted"`
- `schema.py:315-338` — `from_dict` constructor kwargs; add the three new fields
- `schema.py:362-363` — `get_referenced_states` pattern for `on_retry_exhausted`
- `validation.py:280-301` — paired validation pattern (max_retries ↔ on_retry_exhausted, both-or-neither, >= 1)
- `layout.py:201-202` — `on_retry_exhausted` edge to mirror in `_collect_edges()`
- `layout.py:35` — `"retry_exhausted"` entry in `_EDGE_LABEL_COLORS`
- `layout.py:66` — `"retry_exhausted"` in `_edge_line_color()` early-return tuple
- `signal_detector.py` — **OUT OF SCOPE** under Option A; RATE_LIMIT_STORM is implemented in `executor.py` as a stateful counter + LLEvent, not a SignalPattern
- `generate_schemas.py:78` — `SCHEMA_DEFINITIONS` dict start; add both `"rate_limit_exhausted"` and `"rate_limit_storm"` entries using the `_schema()` helper (brings FSM Executor entries from 11 to 13)
- `cli/schemas.py:15` — docstring count `"all 19 LLEvent types"` → `"all 21 LLEvent types"`
- `fragments.py:64,139` — fragment resolution runs at parse time via `_deep_merge`; state-level fields override fragment defaults, so `max_rate_limit_retries: 3` in the fragment can still be overridden by a state that sets its own value
- `scripts/tests/test_fsm_fragments.py:945` — `test_all_common_yaml_fragments_have_description` enforces the `description` field requirement for new `with_rate_limit_handling` fragment

## Acceptance Criteria

- [ ] `StateConfig` accepts `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds` (all 5-part pattern steps)
- [ ] Paired validation rejects either of `max_rate_limit_retries` / `on_rate_limit_exhausted` without the other; `max_rate_limit_retries >= 1`; `rate_limit_backoff_base_seconds >= 1` when present
- [ ] `rate_limit_backoff_base_seconds` defaults to `30`; `executor.py` stub constants replaced with reads from `StateConfig`
- [ ] `fsm-loop-schema.json` updated for new fields
- [ ] Executor tracks `_consecutive_rate_limit_exhaustions` counter; emits `RATE_LIMIT_STORM` LLEvent when counter reaches 3; resets on successful non-rate-limited transition
- [ ] `rate_limit_exhausted` and `rate_limit_storm` entries added to schema registry; count updated to 21; `cli/schemas.py:15` docstring updated
- [ ] `rate_limit_exhausted` edge color configurable via `CliColorsEdgeLabelsConfig`
- [ ] Diagram edges render `on_rate_limit_exhausted` with color
- [ ] `with_rate_limit_handling` fragment in `common.yaml` (with `description` field)
- [ ] `auto-refine-and-implement` and `recursive-refine` opt in via fragment

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. **`config-schema.json`** — add `"rate_limit_exhausted"` property to `fsm_edge_labels` block (line 892-894); `additionalProperties: false` means this is a hard blocker for any user who sets this config key
2. **`executor.py:486`** — update routing lookup from `state.extra_routes.get("rate_limit_exhausted") or state.on_error` to `state.on_rate_limit_exhausted or state.on_error`; this is required after `on_rate_limit_exhausted` is added to `_known_on_keys` (otherwise the key no longer lands in `extra_routes` and the current lookup silently always falls back to `on_error`)
3. **`scripts/little_loops/fsm/__init__.py`** — no change required under Option A (RATE_LIMIT_STORM is an executor event constant, not a signal_detector export)
4. **Update `test_generate_schemas.py`** — all 5 count assertions (`lines 18, 22-44, 50, 57, 165`) must change from 19→**21** and the expected key set must include both `"rate_limit_exhausted"` and `"rate_limit_storm"`
5. **Update `test_fsm_executor.py:TestRateLimitRetries`** — 6 tests that patch module-level constants must be rewritten to use `StateConfig` with the new fields; `test_rate_limit_exhausted_routes_to_on_rate_limit_exhausted` (line 4395) must use `on_rate_limit_exhausted=` field instead of `extra_routes={"rate_limit_exhausted": ...}`
6. **Add `TestRateLimitStorm` to `test_fsm_executor.py`** — new test class for the consecutive-exhaustion counter and `RATE_LIMIT_STORM` event emission (see Tests section for cases)
7. **`test_signal_detector.py`** — no change (Option A keeps signal_detector.py out of scope)
8. **Documentation updates** — add `rate_limit_exhausted` AND `rate_limit_storm` entries to EVENT-SCHEMA.md; add `rate_limit_exhausted` entries to CONFIGURATION.md, OUTPUT_STYLING.md, LOOPS_GUIDE.md, generalized-fsm-loop.md, skills/create-loop/reference.md, and API.md (StateConfig field listing)

## Dependencies

- BUG-1107 implements the executor's 429 detection and retry logic, using a hardcoded `_DEFAULT_RATE_LIMIT_RETRIES = 3` stub. This issue (BUG-1108) is responsible for: (a) adding `max_rate_limit_retries` to `StateConfig`, and (b) updating `executor.py` to replace the stub constant with `route_ctx.state.max_rate_limit_retries`. Implement in parallel or after BUG-1107.
- **Note (2026-04-14)**: BUG-1107's executor work appears to have landed (commit `8dba4536 fix(fsm): detect 429 rate limits, retry in-place, persist retry counts`). The stub constants and `RATE_LIMIT_EXHAUSTED_EVENT` symbol are already present in `executor.py:50-54`, so BUG-1108 can proceed — no blocker remains. Verify BUG-1107 issue status before starting.

## Codebase Research Findings

_Added by `/ll:refine-issue` on 2026-04-14 — verified file:line references against current `main` (HEAD: 8dba4536)._

### Fragment Template for `with_rate_limit_handling` (RESOLVED 2026-04-14)

**Finding**: Fragment resolution at `fragments.py:64` runs at YAML parse time via `_deep_merge` — fragment fields are merged into state dicts as literals, then `StateConfig.from_dict` type-coerces them. Interpolation (`${context.*}`) runs only at execution time on specific string fields (routes, action templates, `evaluate.source`). A fragment setting `max_rate_limit_retries: ${context.rate_limit_retries}` would hand `from_dict` a literal string for an `int` field and crash.

**Resolved design** — fragment ships with literal defaults matching current executor constants; state supplies the routing target:

```yaml
with_rate_limit_handling:
  description: |
    Applies per-state rate-limit retry handling with 3 retries and 30s base backoff.
    State must supply: on_rate_limit_exhausted (target state name when retries exhausted).
    State may override: max_rate_limit_retries, rate_limit_backoff_base_seconds.
  max_rate_limit_retries: 3
  rate_limit_backoff_base_seconds: 30
```

State-level fields win via `_deep_merge` (`fragments.py:139`), so any state can override the defaults while still opting into the fragment.

### RATE_LIMIT_STORM Detection (RESOLVED 2026-04-14 — Option A)

**Finding**: `SignalPattern` (`signal_detector.py:31-70`) only does regex-on-`action.output`. Consecutive-exhaustion detection spans multiple actions across multiple states; it's stateful cross-invocation telemetry, not output parsing.

**Resolved design (Option A)**: Implement as an executor-level counter + LLEvent, not a SignalPattern.
- Add `self._consecutive_rate_limit_exhaustions: int = 0` to executor state alongside existing `self._rate_limit_retries` dict
- Increment on `rate_limit_exhausted` emission (near `executor.py:487`)
- Reset to 0 on any successful non-rate-limited state transition
- When counter reaches 3 (hardcoded for this issue; config deferred), emit `RATE_LIMIT_STORM` LLEvent with `{"count": N, "state": state_name}`
- No changes to `signal_detector.py`, `fsm/__init__.py`, or `test_signal_detector.py` — dropped from scope entirely

### Event Count Audit (UPDATED 2026-04-14)

`generate_schemas.py:78` defines `SCHEMA_DEFINITIONS` with sub-section comment `# FSM Executor (11 types)`. This issue adds **two** new events (`rate_limit_exhausted` — previously missing from registry despite being emitted by BUG-1107; and new `rate_limit_storm`), making it **13** FSM Executor types. Update the sub-section comment and the `cli/schemas.py:15` docstring to **21** total events.

### Verified References vs. Issue Claims

| Issue claim | Verified | Notes |
|---|---|---|
| `schema.py:228-229` field declaration | ✓ | Exact match |
| `schema.py:270-273` to_dict | ✓ | Exact match |
| `schema.py:305-338` from_dict + `_known_on_keys` | Drift | `_known_on_keys` set is at 298-308, `from_dict` constructor at 315-338 |
| `schema.py:362-363` get_referenced_states | ✓ | Exact match |
| `validation.py:280-301` paired validation | ✓ | Exact match |
| `signal_detector.py:73-76` SignalPattern | ✓ | Exact match |
| `generate_schemas.py:78-290` SCHEMA_DEFINITIONS | ✓ | Dict starts at 78 |
| `cli/schemas.py:15` count "19" | ✓ | Confirmed in docstring |
| `config/cli.py:86` `retry_exhausted` | ✓ | Exact match |
| `config/core.py:475-484` fsm_edge_labels | ✓ | Exact match |
| `layout.py:27-36` `_EDGE_LABEL_COLORS` | ✓ | `retry_exhausted` at line 35 |
| `layout.py:62-74` `_edge_line_color()` | ✓ | `retry_exhausted` in tuple at line 66 |
| `layout.py:201` `on_retry_exhausted` edge | ✓ | Edge appended at 201-202 |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-14_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 45/100 → LOW

### Outcome Risk Factors
- **Complexity (0/25)**: ~31 files touched across FSM schema, executor, config, layout, CLI, fragment library, loop YAMLs, 8 doc files, and 9 test files. Expect integration friction and a long diff to review.
- **RATE_LIMIT_STORM mechanism unresolved (Ambiguity)**: The issue explicitly says "decide the approach before coding" — the existing `SignalPattern` regex model doesn't fit; a new non-regex rule type or executor-side synthetic output string must be chosen first. Skipping this decision will cause a mid-implementation stall.
- **Fragment interpolation unverified (Ambiguity)**: `with_rate_limit_handling` uses `${context.*}` interpolation at the top-level StateConfig field level — the issue notes this is "a novel pattern" and advises confirming that fragment merge supports it before coding. If interpolation isn't supported, the fragment design changes significantly.
- **Wide change surface (Change Surface 10/25)**: `schema.py` has 13 non-test importers; `signal_detector.py` has 19. Changes are additive, but regressions are possible across a broad surface.

## Session Log
- `/ll:confidence-check` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:wire-issue` - 2026-04-14T17:45:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9622453-ef85-41be-ba58-37fdc2a25853.jsonl`
- `/ll:refine-issue` - 2026-04-14T17:28:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a46c6016-f36a-4046-8296-d7eefba32350.jsonl`
- `/ll:issue-size-review` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4abdbd46-1b62-4801-9d00-a2569583afde.jsonl`

---

## Status

**Open** | Created: 2026-04-14 | Priority: P2
