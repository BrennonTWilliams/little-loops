---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
id: FEAT-1217
priority: P2
parent_issue: FEAT-1215
discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Very Large
confidence_score: 80
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1217: Parallel Loop YAML Fixture and Fixture-Load Test

## Summary

Create the `parallel-loop.yaml` FSM fixture and add `test_load_valid_parallel_yaml` to `TestLoadAndValidate` in `test_fsm_schema.py`. Verifies the fixture round-trips through `load_and_validate` with no validation warnings.

## Parent Issue

Decomposed from FEAT-1215: Parallel State Config Round-Trip Tests and Fixture

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `ParallelStateConfig` is added to `StateConfig` and the JSON schema is updated, this fixture confirms the YAML representation loads cleanly end-to-end.

**Goal**: Create `parallel-loop.yaml` and add one fixture-load test method.

**Outcome**: `python -m pytest scripts/tests/test_fsm_schema.py -x -k "test_load_valid_parallel_yaml"` passes green.

## Proposed Solution

### New fixture: scripts/tests/fixtures/fsm/parallel-loop.yaml

```yaml
name: parallel-loop
initial: fan_out
states:
  fan_out:
    parallel:
      items: "${captured.queue.output}"
      loop: refine-to-ready-issue
      max_workers: 2
      isolation: thread
      fail_mode: collect
      context_passthrough: false
    route:
      on_yes: done
      on_partial: done
      on_no: done
  done:
    terminal: true
```

Note: `name:` and `initial:` are required top-level fields for `FSMLoop`. Terminal state uses `terminal: true` to match the codebase convention in `scripts/tests/fixtures/fsm/valid-loop.yaml:8-9` (`StateConfig.from_dict` at `schema.py:359` reads `data.get("terminal", False)` as a plain boolean).

### test_fsm_schema.py — Add test_load_valid_parallel_yaml

Add to `TestLoadAndValidate` (opens at `test_fsm_schema.py:1541`), modeled after `test_load_valid_yaml` at `test_fsm_schema.py:1544-1551`:

```python
def test_load_valid_parallel_yaml(self, fsm_fixtures: Path) -> None:
    """Load valid parallel-state YAML file."""
    fixture_path = fsm_fixtures / "parallel-loop.yaml"
    fsm, warnings = load_and_validate(fixture_path)
    assert fsm.name == "parallel-loop"
    assert fsm.initial == "fan_out"
    assert len(fsm.states) == 2
    assert warnings == []
```

Imports: no new imports needed — `load_and_validate`, `Path`, and `pytest` are already in scope at the top of `test_fsm_schema.py`.

**Implementation note (wiring pass)**: The test as written does not assert `fsm.states["fan_out"].parallel is not None`. This is intentional — it is a load/smoke test matching the `test_load_valid_yaml` pattern. Deeper `ParallelStateConfig` field assertions belong in the FEAT-1213/FEAT-1215 round-trip tests (both completed). If FEAT-1074 lands and the fixture silently drops `parallel:`, this test would still pass structurally; consider adding `assert fsm.states["fan_out"].parallel is not None` to make the semantic intent enforceable.

## Integration Map

### Files to Create
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture

### Files to Modify
- `scripts/tests/test_fsm_schema.py` — Add `test_load_valid_parallel_yaml` to `TestLoadAndValidate` (after `test_load_valid_yaml:1544`)

### Dependent Files
- `scripts/little_loops/fsm/schema.py` — `StateConfig.parallel` field (FEAT-1074, blocking; currently absent, `StateConfig` fields end at `schema.py:255`)
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig` dataclass (FEAT-1074, blocking; does not yet exist)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `parallel` under `stateConfig.properties` (FEAT-1074, blocking; `stateConfig` definition spans `fsm-loop-schema.json:175-321`, last property is `tools` at `:306`)
- `scripts/tests/conftest.py:30-33` — project-wide `fsm_fixtures` fixture (uses `fixtures_dir / "fsm"`); module-local fixture at `test_fsm_schema.py:33-36` (uses `Path(__file__).parent / "fixtures" / "fsm"`) takes precedence within the file — both resolve to the same directory

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:115` — contains hardcoded `"# FSM YAML fixtures (8 files)"` count; already stale (9 files exist now), becomes 10 once `parallel-loop.yaml` is added. FEAT-1214 is the designated owner of this count update — no change needed here, but listed as a known coupling.

### Validation Entry Points
- `load_and_validate(path: Path) -> tuple[FSMLoop, list[ValidationError]]` at `scripts/little_loops/fsm/validation.py:517` — warnings list contains `ValidationError` objects (each with a `.severity` attribute, see `test_warnings_logged_not_raised:1589` for the pattern); `warnings == []` means no errors and no warnings emitted

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1544-1551` — `test_load_valid_yaml` — exact pattern to mirror (docstring + path + `load_and_validate` + asserts on `name`/`initial`/`len(states)`/`warnings`)
- `scripts/tests/test_fsm_schema.py:33-36` — module-local `fsm_fixtures` pytest fixture
- `scripts/tests/fixtures/fsm/valid-loop.yaml` — style reference (9 lines total, `terminal: true` for the end state)
- No existing fixture in `scripts/tests/fixtures/fsm/` uses `parallel:` under a state — `parallel-loop.yaml` will be the first

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-21):_

- FEAT-1074 is confirmed **not yet implemented**: `ParallelStateConfig` does not exist in `schema.py`, `StateConfig.parallel` field is absent (fields end at `schema.py:255`), and `fsm-loop-schema.json` has no `parallel` property under `stateConfig.properties`. This test will hard-fail until FEAT-1074 lands.
- `StateConfig.from_dict` silently ignores unknown state-level keys (uses `data.get(...)` per FEAT-1074 Implementation Notes). Pre-FEAT-1074, loading `parallel-loop.yaml` would not emit an "unknown key" warning for `parallel:`, but the `fan_out` state would then fail `_validate_state_routing`'s no-transition guard at `validation.py:271` (no `action`, no `loop`, no `next`, no `terminal`) unless `route:` alone satisfies it. FEAT-1074 also adds a `has_parallel` exemption to that guard — see FEAT-1074 Blockers section.
- `TestLoadAndValidate` opens at `test_fsm_schema.py:1541` and currently contains 9 test methods (`:1544-:1612`). The new test goes directly after `test_load_valid_yaml` at `:1552`, before `test_file_not_found` at `:1553`.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` schema, `StateConfig.parallel` field, JSON schema update)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_schema.py -x -k "test_load_valid_parallel_yaml"` passes green
- `parallel-loop.yaml` loads with `warnings == []`
- Existing `TestLoadAndValidate` tests stay green (no regressions)

## Labels

`fsm`, `parallel`, `tests`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 is a hard blocker**: `ParallelStateConfig` does not exist in `schema.py`, `StateConfig.parallel` field is absent, and `fsm-loop-schema.json` has no `parallel` property. `test_load_valid_parallel_yaml` will hard-fail until FEAT-1074 lands — the `fan_out` state has no `action`, `loop`, `next`, or `terminal`, which triggers the `_validate_state_routing` no-transition guard.
- **Sequencing risk**: Implementing before FEAT-1074 will break CI. Sequence this immediately after FEAT-1074 completes, or gate the test with a skip marker if the fixture lands first.

## Session Log
- `/ll:refine-issue` - 2026-04-21T06:59:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eda02963-6c6b-479d-ab2b-3b2d62d72735.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f9d86b0-0210-42c0-889d-92931450b358.jsonl`
- `/ll:wire-issue` - 2026-04-21T06:57:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c74aa34-f5c7-4be6-bd84-4508b58e30f5.jsonl`
- `/ll:refine-issue` - 2026-04-21T06:50:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52f66d52-c3d2-4b51-99ce-f54524e6a62b.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59852d6e-fcd5-41f5-b554-577001c3b013.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6ca6793-6b9a-4436-a076-3620e7354261.jsonl`
