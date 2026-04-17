---
id: ENH-1139
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-17
parent: ENH-1138
related: [ENH-1138, ENH-1134]
size: Medium
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
testable: false
---

# ENH-1139: 429 Resilience — API.md Reference Updates for Circuit Breaker

## Summary

Update `docs/reference/API.md` with three targeted changes: (1) replace the stale `FSMExecutor.__init__` signature with the full 7-parameter version, (2) add a `### little_loops.fsm.rate_limit_circuit` class section, and (3) add `RateLimitCircuit` to the Quick Import block.

## Parent Issue

Decomposed from ENH-1138: 429 Resilience — Documentation Updates for Circuit Breaker

## Expected Behavior

### 1. `docs/reference/API.md:4003-4011` — `FSMExecutor.__init__` signature

Replace the current 3-parameter signature (currently shown as `fsm: FSMLoop`, `event_callback: Callable[[dict], None] | None`, `action_runner: ActionRunner | None`) with the full 7-parameter version from `scripts/little_loops/fsm/executor.py:115-124`:

```python
def __init__(
    self,
    fsm: FSMLoop,
    event_callback: EventCallback | None = None,
    action_runner: ActionRunner | None = None,
    signal_detector: SignalDetector | None = None,
    handoff_handler: HandoffHandler | None = None,
    loops_dir: Path | None = None,
    circuit: RateLimitCircuit | None = None,
)
```

Notes:
- The first parameter is `FSMLoop` (the dataclass at `scripts/little_loops/fsm/schema.py:524`), not `FSMDefinition`.
- `EventCallback` is the alias defined at `scripts/little_loops/fsm/types.py:75` as `Callable[[dict[str, Any]], None]`; prefer the alias over inlining the Callable type to match the codebase and other class docs.
- The source signature in `executor.py:115-124` has no explicit `-> None` return annotation; don't add one to the docs.

### 2. `docs/reference/API.md` — new `### little_loops.fsm.rate_limit_circuit` section

Insertion point: between the existing `### little_loops.fsm.concurrency` section (starts at `docs/reference/API.md:4402`) and `### little_loops.fsm.signal_detector` (starts at `docs/reference/API.md:4440`). This matches the module-overview-table ordering at `docs/reference/API.md:3671-3673` (concurrency → rate_limit_circuit → signal_detector). The `:3672` row is just the overview-table entry for the module and already exists; the gap is the missing class-reference section below.

Document the public surface exactly as defined in `scripts/little_loops/fsm/rate_limit_circuit.py`:

- `__init__(path: Path)` — constructor at `rate_limit_circuit.py:40`; accepts the absolute path to the shared JSON state file (internally coerced via `Path(path)`, and a sidecar `.lock` file is derived from `path`)
- `record_rate_limit(backoff_seconds: float) -> None` — `rate_limit_circuit.py:44`; writes/updates shared state under an `fcntl.flock` lock, increments `attempts`, and advances `estimated_recovery_at` monotonically (`max(existing, now + backoff_seconds)`) so concurrent observers can't shrink an in-flight backoff window
- `get_estimated_recovery() -> float | None` — `rate_limit_circuit.py:77`; returns the epoch-seconds timestamp of estimated recovery, or `None` if the entry is stale or the file is absent (the signature returns `float`, not `datetime`)
- `is_stale() -> bool` — `rate_limit_circuit.py:87`; returns `True` when `last_seen` is older than `STALE_THRESHOLD_SECONDS = 3600.0` (`rate_limit_circuit.py:27`). Returns `False` if the file is absent entirely
- `clear() -> None` — `rate_limit_circuit.py:97`; removes the state file, no-op if already absent

Add a one-sentence module blurb matching the module docstring (`rate_limit_circuit.py:1-12`): "Shared circuit-breaker state file for cross-worktree 429 coordination."

### 3. `docs/reference/API.md:3677-3695` — Quick Import block

Add `RateLimitCircuit` to the Quick Import block under a `# Rate Limiting` comment group:

```python
# Rate Limiting
from little_loops.fsm import RateLimitCircuit
```

## Integration Map

### Files to Modify

- `docs/reference/API.md` — three edits:
  - **Line 4003-4011** (FSMExecutor signature block): expand from 3 to 7 parameters
  - **Between line 4439 and 4440** (after `### little_loops.fsm.concurrency`, before `### little_loops.fsm.signal_detector`): insert new `### little_loops.fsm.rate_limit_circuit` class section
  - **Line 3677-3695** (Quick Import block): add `# Rate Limiting` comment group with `RateLimitCircuit`

### Source-of-Truth References

- **Canonical `FSMExecutor.__init__` signature**: `scripts/little_loops/fsm/executor.py:115-124` (no explicit `-> None` return annotation in source)
- **`FSMLoop` dataclass** (correct name, not `FSMDefinition`): `scripts/little_loops/fsm/schema.py:524`
- **`EventCallback` type alias**: `scripts/little_loops/fsm/types.py:75` — `EventCallback = Callable[[dict[str, Any]], None]`
- **`RateLimitCircuit` module**: `scripts/little_loops/fsm/rate_limit_circuit.py` (134 lines)
  - Module docstring: `rate_limit_circuit.py:1-12` (use as section blurb)
  - `__init__`: `rate_limit_circuit.py:40` — signature is `__init__(self, path: Path) -> None`
  - `record_rate_limit`: `rate_limit_circuit.py:44`
  - `get_estimated_recovery`: `rate_limit_circuit.py:77` — returns `float | None` (epoch seconds), NOT `datetime | None`
  - `is_stale`: `rate_limit_circuit.py:87` — returns `False` when file absent; `True` only when entry exists and `last_seen` is older than threshold
  - `clear`: `rate_limit_circuit.py:97`
  - `STALE_THRESHOLD_SECONDS = 3600.0`: `rate_limit_circuit.py:27`
- **Import path**: `from little_loops.fsm import RateLimitCircuit` — re-exported at `scripts/little_loops/fsm/__init__.py:117` and listed in `__all__` at `scripts/little_loops/fsm/__init__.py:167`

### Anchor Landmarks in API.md (for locating edits)

- Module overview table row already exists: `docs/reference/API.md:3672`
- Existing `### little_loops.fsm.executor` class section header: `docs/reference/API.md:3997`
- Existing `#### FSMExecutor` heading: `docs/reference/API.md:4001`
- Existing `### little_loops.fsm.concurrency` class section header: `docs/reference/API.md:4402`
- Existing `### little_loops.fsm.signal_detector` class section header: `docs/reference/API.md:4440`
- Quick Import opening `from little_loops.fsm import (` at `docs/reference/API.md:3678`; closing `)` at `docs/reference/API.md:3694`

### Dependent / Related Surfaces (context, no direct edits required here)

- Parent issue `ENH-1138` tracks the overall documentation effort
- Sibling `ENH-1140` covers prose doc updates; `ENH-1141` covers the doc-wiring test
- `CHANGELOG.md` entry (if any) is out of scope for this issue — covered by `ENH-1138`'s umbrella

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1138_doc_wiring.py` — new test file to be written by ENH-1141; will verify API.md contains the full 7-param `FSMExecutor.__init__` signature, `RateLimitCircuit` in the Quick Import block, and the `### little_loops.fsm.rate_limit_circuit` section header; follow the pattern in `scripts/tests/test_create_extension_wiring.py:96`
- `scripts/tests/test_create_extension_wiring.py:96` — existing doc-wiring test that reads API.md; asserts unrelated content (`little_loops.testing`) and will not break after this issue's changes

### Similar Patterns in API.md

- **Signature block style** to match for the expanded `FSMExecutor.__init__`: see `#### FSMLoop` at `docs/reference/API.md:3703` (uses fenced `python` block with full dataclass signature)
- **Class section layout** to match for the new `### little_loops.fsm.rate_limit_circuit`: see `### little_loops.fsm.concurrency` at `docs/reference/API.md:4402` — short module blurb, one `####` class heading, fenced signature, then a **Methods** table

## Implementation Steps

1. **Edit `docs/reference/API.md:4003-4011`** — replace the 3-parameter `FSMExecutor.__init__` block with the 7-parameter version; keep `fsm: FSMLoop` (not `FSMDefinition`), use the `EventCallback | None` alias, omit the explicit `-> None` return annotation to match source (`scripts/little_loops/fsm/executor.py:115-124`)
2. **Edit `docs/reference/API.md`** — insert a new `### little_loops.fsm.rate_limit_circuit` section between the end of `### little_loops.fsm.concurrency` (starting at line `4402`) and `### little_loops.fsm.signal_detector` (line `4440`); include a one-sentence module blurb from `rate_limit_circuit.py:1-12`, a `#### RateLimitCircuit` heading, the constructor signature (`__init__(self, path: Path) -> None`), and a Methods table for `record_rate_limit`, `get_estimated_recovery` (returns `float | None`, not `datetime`), `is_stale`, `clear` — match the section layout of `### little_loops.fsm.concurrency`
3. **Edit `docs/reference/API.md:3678-3694`** — inside the existing `from little_loops.fsm import (...)` block, append a `# Rate Limiting` comment group with `RateLimitCircuit` before the closing `)`
4. **Verify** with `rg -n "FSMDefinition|datetime \| None" docs/reference/API.md` to confirm neither of the incorrect type names from earlier drafts of this issue ended up in the file
5. **Run** `python scripts/ll_verify_docs.py` (or `ll-verify-docs`) if the project provides a doc verifier; otherwise skim the rendered markdown for layout consistency with neighboring class sections

## Acceptance Criteria

- `FSMExecutor.__init__` docs at `docs/reference/API.md` include all 7 parameters in source order: `fsm: FSMLoop`, `event_callback: EventCallback | None = None`, `action_runner: ActionRunner | None = None`, `signal_detector: SignalDetector | None = None`, `handoff_handler: HandoffHandler | None = None`, `loops_dir: Path | None = None`, `circuit: RateLimitCircuit | None = None`
- The docs use `FSMLoop` (not `FSMDefinition`) and `EventCallback` (not an inlined `Callable[[dict], None]`)
- A new `### little_loops.fsm.rate_limit_circuit` section exists between the `concurrency` and `signal_detector` sections, documenting `__init__(path: Path)`, `record_rate_limit(backoff_seconds: float) -> None`, `get_estimated_recovery() -> float | None`, `is_stale() -> bool`, and `clear() -> None`
- `get_estimated_recovery` is documented as returning `float | None` (epoch-seconds timestamp), NOT `datetime | None`
- The Quick Import block at `docs/reference/API.md:3677-3695` includes a `# Rate Limiting` comment group with `RateLimitCircuit`
- `rg -n "FSMDefinition" docs/reference/API.md` returns no matches
- `rg -n "datetime \| None" docs/reference/API.md` does not match on the `get_estimated_recovery` line (unrelated matches elsewhere are fine)

## Resolution

Implemented 2026-04-17. Three edits applied to `docs/reference/API.md`:

1. `FSMExecutor.__init__` signature block expanded from 3 to 7 parameters (`fsm: FSMLoop`, `event_callback: EventCallback | None`, `action_runner`, `signal_detector`, `handoff_handler`, `loops_dir`, `circuit: RateLimitCircuit | None`).
2. New `### little_loops.fsm.rate_limit_circuit` class section inserted between `concurrency` and `signal_detector`, documenting `__init__(path)`, `record_rate_limit`, `get_estimated_recovery` (returns `float | None`), `is_stale`, and `clear`.
3. `RateLimitCircuit` added to the Quick Import block under a `# Rate Limiting` comment group.

Verification:
- `rg -n "FSMDefinition" docs/reference/API.md` → no matches.
- `rg -n "datetime \| None" docs/reference/API.md` → only the unrelated `since:` param on line 2367.
- `python -m pytest scripts/tests/` → 4902 passed, 5 skipped.
- `ruff check scripts/` → all checks passed.

## Session Log
- `/ll:manage-issue` - 2026-04-17T00:00:00Z - session (implementation)
- `/ll:ready-issue` - 2026-04-17T06:07:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fe5c4b4-75df-4e51-9e44-81cd29c0be70.jsonl`
- `/ll:wire-issue` - 2026-04-17T06:04:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9816ce6-e660-410f-bfa1-a25f885f5285.jsonl`
- `/ll:refine-issue` - 2026-04-17T05:58:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5f06fdb-7855-4c08-a77a-8dc172328774.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e6682d5-cb79-4c33-9ce6-ede83cb84a43.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6002e31c-2ca3-41bb-9d7e-84f299897bc1.jsonl`

---

## Status
- [x] Completed 2026-04-17
