---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
id: FEAT-1218
priority: P2
parent_issue: FEAT-1215
discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Very Large
confidence_score: 88
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1218: TestParallelStateConfig Test Class

## Summary

Add `TestParallelStateConfig` class to `test_fsm_schema.py`, modeled after `TestSubLoopStateConfig:1817`. Covers round-trip serialization, default values, `StateConfig` integration, alias handling, and a no-spurious-error guard.

## Parent Issue

Decomposed from FEAT-1215: Parallel State Config Round-Trip Tests and Fixture

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `ParallelStateConfig` exists, these unit tests verify the Python class serializes/deserializes correctly and does not cause spurious validation errors on non-parallel loops.

**Goal**: Add `TestParallelStateConfig` class after `TestSubLoopStateConfig:1817` in `test_fsm_schema.py`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_schema.py -x -k "TestParallelStateConfig"` passes green.

## Proposed Solution

### test_fsm_schema.py — Add TestParallelStateConfig class

Add after `TestSubLoopStateConfig` (line 1817), mirroring its 9-method structure:

1. `test_state_config_with_parallel_field` — field setting
2. `test_state_config_context_passthrough` — secondary field (mirrors `test_state_config_context_passthrough` in sub-loop class)
3. `test_state_config_parallel_defaults_to_none` — default value / backward compat
4. `test_to_dict_includes_parallel_when_set` — serialization emits `parallel` key
5. `test_to_dict_excludes_parallel_when_none` — serialization omits key when default
6. `test_from_dict_with_parallel` — deserialization; if FEAT-1074 introduces legacy-name aliases (e.g. `on_success` → `on_yes` analogue), include alias test mirroring `test_fsm_schema.py:1857`
7. `test_from_dict_without_parallel` — deserialization defaults
8. ~~`test_parallel_and_action_mutual_exclusion`~~ — **NOT in scope; FEAT-1216 owns this**
9. `test_parallel_state_no_transition_error` — no-spurious-error guard; mirrors `test_sub_loop_state_no_transition_error:1884` (constructs `FSMLoop` directly, calls `validate_fsm(fsm)`, asserts `not any("no transition" in m.lower() for m in error_messages)`)

**Import**: Add `ParallelStateConfig` to the import block at `test_fsm_schema.py:16-24` (from `little_loops.fsm.schema`). If FEAT-1074 does NOT create a standalone class (instead uses fields directly on `StateConfig`), skip this import and test via `StateConfig` directly. **Precedent**: `TestSubLoopStateConfig` (the template) tests fields on `StateConfig` with NO separate `SubLoopStateConfig` import — this is the more likely outcome for FEAT-1074 too.

### Template — TestSubLoopStateConfig shape (lines 1817–1901)

The sub-loop class is the exact template. Key methods to mirror:

- **Line 1817**: class declaration
- **Line 1857**: alias test (`on_success` → `on_yes`) — apply only if FEAT-1074 introduces analogous aliases on `ParallelStateConfig`
- **Line 1884**: `test_sub_loop_state_no_transition_error` — constructs `FSMLoop` directly, calls `validate_fsm(fsm)`, asserts no "no transition" errors

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` class **after line 1901** (end of `TestSubLoopStateConfig`, before `TestLoopConfigOverrides`); add `ParallelStateConfig` to schema import block at lines 16–24 **only if** FEAT-1074 exposes a standalone class

### Dependent Files
- `scripts/little_loops/fsm/schema.py:229-255` — `StateConfig` field list (27 fields today, no `parallel` field). FEAT-1074 adds `parallel` here and/or introduces `ParallelStateConfig`
- `scripts/little_loops/fsm/validation.py:267-278` — `_validate_state_routing` contains `has_loop` guard at line 271. FEAT-1074 must add analogous `has_parallel` guard for `test_parallel_state_no_transition_error` to pass
- `scripts/little_loops/fsm/validation.py:372-484` — `validate_fsm(fsm: FSMLoop) -> list[ValidationError]` — returns list where each error has `message: str`, `path: str | None`, `severity: ValidationSeverity`

### Regression Surfaces
- `scripts/tests/test_fsm_schema.py:780` (`TestFSMValidation`) — `len(error_list) == 0` assertions; `ParallelStateConfig` must not emit errors for non-parallel loops
- `scripts/tests/test_fsm_schema_fuzz.py` — `StateConfig.from_dict()` fuzz coverage; new `parallel` field must not break fuzz generator
- `scripts/tests/test_review_loop.py`, `test_outer_loop_eval.py`, `test_builtin_loops.py` — parametrized validation over built-in loops; must stay green
- `scripts/tests/test_fsm_validation.py` — direct `StateConfig` + `validate_fsm` usage (lines 9–10); exercises the same `_validate_state_routing` guard path that FEAT-1074 must modify; regression surface if the `has_parallel` guard is incomplete
- `scripts/tests/test_cli.py:1950,2003,2059,2101,2153,2228,2307` — seven test methods build `StateConfig` objects inline; none use a `parallel` field today; will stay green as long as a bare `StateConfig` with no `parallel` field emits no new errors

### Export / Re-export Surface

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:120-127,179` — re-exports `StateConfig`, `ValidationError`, `validate_fsm` from `schema.py`/`validation.py`; `ParallelStateConfig` is **deliberately NOT exported** through `__init__.py` (per FEAT-1074 decision). This confirms the test import should import directly from `little_loops.fsm.schema` if a standalone class exists, or simply test via `StateConfig` fields — NOT via the public `little_loops.fsm` package surface.

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1817-1901` — `TestSubLoopStateConfig` — exact template (9 methods; no fixtures, all state built inline)
- `scripts/tests/test_fsm_schema.py:1884-1901` — `test_sub_loop_state_no_transition_error` — no-spurious-error guard: builds minimal `FSMLoop` with the candidate state + two `terminal=True` states, calls `validate_fsm()`, then `error_messages = [str(e) for e in errors]` and `assert not any("no transition" in m.lower() for m in error_messages)`
- `scripts/tests/test_fsm_schema.py:1851-1858` — alias test: passes `"on_success"` in raw dict, asserts `state.on_yes == "done"` with inline `# on_success alias` comment (embedded in `test_from_dict_with_loop`, NOT a standalone method)
- `scripts/tests/test_fsm_schema.py:1866-1882` — `test_loop_and_action_mutual_exclusion` — positive-assert pattern; **NOT duplicated here (owned by FEAT-1216)**
- `scripts/tests/test_fsm_schema.py:895-907` — `test_on_partial_only_shorthand_is_valid` — alternative no-spurious-error idiom using `e.message` directly (not `str(e)`); either style is acceptable

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis 2026-04-21:_

**Critical — template shape surprise**: `SubLoopStateConfig` does NOT exist as a standalone class. `TestSubLoopStateConfig` tests the `loop` and `context_passthrough` fields that live directly on `StateConfig` (schema.py:229-255). This foreshadows that FEAT-1074 may likewise add parallel config fields directly on `StateConfig` rather than introducing a `ParallelStateConfig` class. Implementer must inspect FEAT-1074's final schema.py shape before deciding the `ParallelStateConfig` import in test_fsm_schema.py lines 16–24.

**Current schema state**: Zero occurrences of `"parallel"` exist in `scripts/little_loops/fsm/schema.py` or `scripts/tests/test_fsm_schema.py`. FEAT-1074 is a true hard blocker.

**Existing dataclasses in schema.py**: `EvaluateConfig` (line 25), `RouteConfig` (144), `StateConfig` (180), `LLMConfig` (415), `LoopConfigOverrides` (459). FEAT-1074 will slot `ParallelStateConfig` alongside these if standalone.

**Serialization idioms** (to mirror in tests):
- `to_dict`: optional fields added only when they differ from default (None-defaulted fields added only if not None; bool fields added only if True — see schema.py:282-283 for `terminal`, 307-308 for `context_passthrough`)
- `from_dict`: `.get()` with explicit defaults; `on_success`/`on_failure` aliases handled at schema.py:353-354 (`on_yes=data.get("on_yes") or data.get("on_success")`); unknown `on_*` keys flow to `extra_routes` via `_known_on_keys` set at schema.py:329-340

**Test helpers in test_fsm_schema.py** (lines 33-60): `fsm_fixtures` fixture, `make_state()` helper, `make_fsm()` helper — `TestSubLoopStateConfig` uses **none of these**; all state is constructed inline. `TestParallelStateConfig` should follow the same inline-construction style.

**Error stringification idiom** (for no-spurious-error guard): two variants exist — prefer the sub-loop style for consistency:
```python
errors = validate_fsm(fsm)
error_messages = [str(e) for e in errors]
assert not any("no transition" in m.lower() for m in error_messages)
```
`ValidationError.__str__` produces `"[ERROR] path: message"` or `"[WARNING] message"` (validation.py:53-58).

**Follow-up research 2026-04-21 (second refine pass)**:

- **FEAT-1074 shape clarified** — FEAT-1074's own refined content specifies `ParallelStateConfig` as a **standalone `@dataclass`** (sibling to `EvaluateConfig`/`RouteConfig`/`LLMConfig` in `schema.py`) with 9 fields: `items`, `loop`, `max_workers`, `isolation`, `fail_mode`, `context_passthrough`, `timeout_seconds`, `max_items`, `max_total_seconds`. `StateConfig` gains `parallel: ParallelStateConfig | None = None` after the `loop` field (around schema.py:251). This partially resolves the "import fork" in the existing Concerns: the standalone-class path is the planned design — so the `ParallelStateConfig` import at `test_fsm_schema.py:16-24` is likely NEEDED (unlike the sub-loop precedent). Verify against FEAT-1074's final merge before writing imports.
- **Field-setting test — concrete targets**: `test_state_config_with_parallel_field` should construct a minimal `ParallelStateConfig(items="{{ list }}", loop="inner")` (required-ish fields) and assert the `parallel` attribute on the resulting `StateConfig` is non-None with expected field values. Defaults to assert in `test_state_config_parallel_defaults_to_none`: `max_workers` default, `isolation` default, `fail_mode` default, `context_passthrough=False`, timeouts `None`, `max_items=None`.
- **Current file sizes confirmed**: `test_fsm_schema.py` is ~2,104 lines; `TestLoopConfigOverrides` begins at line 1904 (insertion point for new class is still between 1901 and 1904). All previously-cited line numbers in this issue remain accurate as of 2026-04-21.
- **No active worktree / branch work** on the FEAT-1074/1216/1217/1218 family — safe to sequence behind FEAT-1074 without collision risk.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` class, `StateConfig.parallel` field)
- **FEAT-1217** is independent (fixture + fixture-load test can be done in either order)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_schema.py -x -k "TestParallelStateConfig"` passes green
- `TestParallelStateConfig` includes no-spurious-error guard mirroring `test_sub_loop_state_no_transition_error:1884`
- Existing `TestFSMValidation` error-count assertions stay green (no regressions)

## Labels

`fsm`, `parallel`, `tests`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 is an unresolved hard blocker.** `ParallelStateConfig` and `StateConfig.parallel` do not yet exist in `schema.py` (confirmed: zero grep hits). Tests can be pre-written (template is clear, insertion point confirmed at line 1901/1904), but will fail at import/construction time until FEAT-1074 merges. Treat as intentional pre-write.
- **Import fork still conditional.** Whether to import `ParallelStateConfig` at lines 16–24 depends on FEAT-1074's final shape. FEAT-1074's refined spec plans a standalone class — but must verify against the actual merged code before writing the import line.

## Session Log
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1554da04-572b-4bf9-a121-be07971caad4.jsonl`
- `/ll:refine-issue` - 2026-04-21T07:15:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/64eaa783-714e-4a4f-b22f-bcde3ef44812.jsonl`
- `/ll:refine-issue` - 2026-04-21T07:06:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a31fb29-38a6-4223-a9a1-03c3b65527be.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59852d6e-fcd5-41f5-b554-577001c3b013.jsonl`
- `/ll:wire-issue` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c60073c-f9ca-498b-a623-c06b69297269.jsonl`
