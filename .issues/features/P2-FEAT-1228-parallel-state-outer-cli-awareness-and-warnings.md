---
discovered_date: "2026-04-21"
discovered_by: issue-size-review
parent_issue: FEAT-1080
size: Very Large
confidence_score: 93
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
---

# FEAT-1228: Parallel State Outer-CLI Awareness and Warnings

## Summary

Add a soft-cap warning to `ll-parallel` and `ll-sprint --parallel` when the loop definition contains any `parallel:` state, an inline comment to `ll-auto` explaining why no warning is needed, and test coverage for all three CLIs.

## Parent Issue

Decomposed from FEAT-1080: Parallel State FSM API Exports and Config Wiring

## Use Case

**Who**: A developer running loops with `parallel:` states under `ll-parallel` or `ll-sprint --parallel`

**Context**: `ll-parallel` runs N issues in N parallel worktrees, each executing the full loop. If the loop contains a `parallel:` state with `max_workers=4`, the system could spawn `N * 4` threads silently. Developers need a visible warning before the fan-out so they can tune `max_workers` down or switch to `ll-auto`.

**Goal**: Emit one clear warning per `ll-parallel` / `ll-sprint --parallel` run when the loop contains any `parallel:` state, naming the computed `N*M` worker budget. No warning under `ll-auto` (sequential by design).

**Outcome**: Silent thread-multiplication is no longer possible; authors are informed of the cumulative budget before execution starts.

## Motivation

The inner `parallel:` state's `max_workers` and the outer CLI's concurrency multiply silently. This issue adds the first line of defense (observability) without imposing a hard limit — that is tracked under ENH-1176.

## Current Behavior

- No warning is emitted when `ll-parallel` or `ll-sprint --parallel` runs a loop containing a `parallel:` state
- The effective thread budget (outer workers × inner `max_workers`) is invisible to the operator
- `ll-auto` is sequential and has no such concern, but the code has no comment explaining this

## Expected Behavior

- `ll-parallel` emits exactly one WARNING to stderr when the loaded loop contains any `parallel:` state:
  ```
  WARNING: loop 'X' contains parallel state(s); ll-parallel concurrency (N) multiplies inner parallel concurrency (M). Cumulative worker budget: N*M=<product>. Consider reducing inner max_workers or running under ll-auto.
  ```
- `ll-sprint --parallel` emits the same warning; no warning under `ll-sprint` without `--parallel`
- `ll-auto` emits no warning; an inline comment in the CLI module explains that the inner parallel state is free to use its full `max_workers` budget (sequential outer execution means no multiplication)
- Tests assert the warning fires exactly once per run and includes the computed `N*M` product

## Proposed Solution

### `scripts/little_loops/cli/ll_auto.py`

- Add an inline comment in the main loop explaining that `parallel:` states inside the loop fan out normally using their own `max_workers`. No composition concern because `ll-auto` runs issues sequentially. **No code change beyond the comment.**

### `scripts/little_loops/cli/ll_parallel.py`

- After the loop definition is loaded (before the fan-out), scan for any state where `state.parallel is not None`
- If any parallel states found, emit once to stderr:
  ```python
  n = len(issue_ids)  # outer worker count
  m = max(s.parallel.max_workers for s in parallel_states)
  warnings.warn(
      f"loop '{loop_name}' contains parallel state(s); ll-parallel concurrency ({n}) "
      f"multiplies inner parallel concurrency ({m}). Cumulative worker budget: {n}*{m}={n*m}. "
      f"Consider reducing inner max_workers or running under ll-auto.",
      stacklevel=2,
  )
  ```
- Emit exactly once, regardless of how many parallel states exist in the loop

### `scripts/little_loops/cli/ll_sprint.py`

- Apply the same scan and warning as `ll-parallel` when `--parallel` is active
- No warning when `--parallel` is not passed

### Modules MUST NOT be touched

- `scripts/little_loops/fsm/executor.py` — parallel dispatch is FEAT-1076's territory
- `scripts/little_loops/fsm/parallel_runner.py` — FEAT-1075's territory
- `scripts/little_loops/parallel/worker_pool.py` — keep the ll-parallel worker pool unaware of FSM parallel states; the warning is at the CLI layer by design

### Tests

- `scripts/tests/test_ll_parallel.py` (new file):
  - Assert warning fires exactly once when loop contains a `parallel:` state
  - Assert warning message includes the computed `N*M` product
  - Assert no warning when loop has no `parallel:` states
- `scripts/tests/test_ll_sprint.py` (extend):
  - Assert warning fires when `--parallel` is active and loop contains a `parallel:` state
  - Assert no warning when `--parallel` is absent, even if loop has `parallel:` states
- `scripts/tests/test_ll_auto.py` (new file):
  - Assert no warning is emitted when a loop containing a `parallel:` state runs under `ll-auto`
  - Use `capsys` pattern from `test_ll_loop_state.py:332`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Import `load_loop` from `little_loops.cli.loop._helpers` into `parallel.py` and `sprint/run.py` (required to obtain `FSMLoop` for the parallel-state scan before orchestrator construction)
2. Resolve `loops_dir` via `config.get_loops_dir()` (`scripts/little_loops/config/core.py:238`) — already available via the `config` object in both CLI paths
3. Decide warning mechanism before writing any code: `print("⚠ ...", file=sys.stderr)` (matches `config_cmds.py:27` codebase convention; testable via `capsys.readouterr().err`) vs. `warnings.warn(..., stacklevel=2)` (as originally proposed; requires `pytest.warns()` — currently absent from the entire test suite)
4. In `parallel.py`: insert warning call after `create_parallel_config` (line 195); compute `N = parallel_config.max_workers` (resolved) and `M = max(s.parallel.max_workers for s in parallel_states)`
5. In `sprint/run.py`: insert warning call at the `else` branch entry (~line 376) before `create_parallel_config` (~line 389); there is no `--parallel` flag — the condition is "multi-issue wave dispatched to orchestrator"
6. Update `scripts/tests/test_cli.py:495–568` and `:1601–1724` to mock `"little_loops.cli.parallel.load_loop"` (prevents FileNotFoundError in tests that call `main_parallel()` directly)
7. Update `scripts/tests/test_sprint_integration.py` parallel dispatch tests to mock `"little_loops.cli.sprint.run.load_loop"` or supply a loop YAML fixture in `tmp_path`

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/auto.py` — inline comment only (file is `auto.py`, not `ll_auto.py`; `main_auto()` at line 21, `AutoManager` constructed at line 90)
- `scripts/little_loops/cli/parallel.py` — scan + emit warning before fan-out (file is `parallel.py`, not `ll_parallel.py`; `main_parallel()` at line 31, orchestrator constructed at lines 229–235 and `orchestrator.run()` at line 237)
- `scripts/little_loops/cli/sprint/run.py` — sprint is a package (`cli/sprint/`), not a single file; parallel dispatch decision at `run.py:332` (sequential when `len(wave) == 1 or is_contention_subwave`) and orchestrator creation at `run.py:389–410`

### New Test Files

- `scripts/tests/test_ll_parallel.py` — new test file for ll-parallel warning behavior (confirmed absent; existing `test_parallel_types.py` covers schema types, not CLI)
- `scripts/tests/test_ll_auto.py` — new test file asserting no warning under ll-auto (confirmed absent)

### Files to Extend

- `scripts/tests/test_sprint.py` **and/or** `scripts/tests/test_sprint_integration.py` — these are the real sprint test files; `test_ll_sprint.py` does NOT exist in the tree. Pick the file whose structure matches a CLI-entry-point test (likely `test_sprint_integration.py`).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py:117` — provides `load_loop()`; must be imported into `parallel.py` and `sprint/run.py` to obtain the `FSMLoop` before orchestrator construction
- `scripts/little_loops/config/core.py:238` — `BRConfig.get_loops_dir()` provides the `loops_dir` argument required by `load_loop()`; already accessible via the `config` object in both CLI paths
- `scripts/little_loops/parallel/types.py:282–340` — `ParallelConfig.max_workers` is the resolved N (outer concurrency); read from `parallel_config.max_workers` after `create_parallel_config`, not from `args.workers`
- `scripts/little_loops/cli/__init__.py:21,30,32–37` — re-exports `main_auto`, `main_parallel`, `main_sprint`; no changes expected
- `scripts/little_loops/cli/sprint/__init__.py:115–134` — confirms no `--parallel` flag is registered on the `run` subparser; sprint parallelism is determined automatically by wave size / contention, not a CLI flag

### Tests (Existing — At Risk of Breaking)

_Wiring pass added by `/ll:wire-issue`:_
If `load_loop(...)` is called in `main_parallel()` or `sprint/run.py` to scan for `parallel:` states, the following existing tests will fail with `FileNotFoundError` (their `tmp_path` has no `.loops` directory) and must be updated to mock `load_loop`:
- `scripts/tests/test_cli.py:495–568` (`TestMainParallelIntegration`) — 3 tests call `main_parallel()` directly; mock target: `"little_loops.cli.parallel.load_loop"`
- `scripts/tests/test_cli.py:1601–1724` (`TestMainParallelAdditionalCoverage`) — 6 more `main_parallel()` tests; same mock target
- `scripts/tests/test_cli_e2e.py:321` — `main_parallel()` e2e test; same risk
- `scripts/tests/test_sprint_integration.py:267–480, 553–1803` — sprint parallel dispatch tests; mock target: `"little_loops.cli.sprint.run.load_loop"`
- `scripts/tests/test_sprint.py:2227–2278` — patches `create_parallel_config`; may also need `load_loop` mock if added upstream in the same call path

Mock pattern reference: `scripts/tests/test_cli_loop_lifecycle.py:281–284` — `patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm)`

### Similar Patterns

- **Warning-assertion template**: `scripts/tests/test_ll_loop_commands.py:75-107` (`test_validate_with_unreachable_state_prints_warning`) — the established pattern asserts `"⚠" in captured.out` via `capsys.readouterr()`. The reference at `test_ll_loop_state.py:332` is only a `capsys` fixture parameter, not a warning assertion.
- **CLI entry-point test pattern**: `scripts/tests/test_cli.py:1561-1566` (main_auto), `:1694` (main_parallel), `:2436` (main_sprint) — all use `patch.object(sys, "argv", [...])` + direct function call; no `CliRunner`, no subprocess.
- **Loop-fixture construction**: `scripts/tests/test_ll_loop_state.py:213-224` — tests write inline YAML to a temp file rather than instantiating `FSMLoop`/`StateConfig` directly. New tests must follow this pattern once `parallel:` is a recognized YAML key (blocker below).
- **Warning-emission precedent**: there is **no existing `warnings.warn(` or `import warnings`** anywhere in `scripts/little_loops/`. FEAT-1228 will introduce the first usage. Implementer must decide whether to follow the existing `print("⚠ ...")`-to-stdout convention (matches `cmd_validate`) or introduce a new `warnings.warn(..., stacklevel=2)`-to-stderr convention as this issue's body proposes. **Recommend revisiting this design choice during implementation** — the current issue body specifies `warnings.warn` but the codebase convention is `print("⚠ ...")`. Canonical reference: `scripts/little_loops/cli/loop/config_cmds.py:27` (`print(f"  ⚠ {w}")` to stdout).

### Dependencies

- FEAT-1227 (core API exports) — the `LoopsGlyphsConfig.parallel` field added there is referenced by this issue's verification that config wiring works end-to-end. Note: `LoopsGlyphsConfig.parallel` at `scripts/little_loops/config/features.py:266` is a **display glyph** (`"∥"` = ∥), not a parallel-execution type — do not conflate with `StateConfig.parallel`.
- FEAT-1074 **hard blocker**: `StateConfig` at `scripts/little_loops/fsm/schema.py:180-316` has **no `.parallel` attribute today** (verified in `from_dict` at lines 319–375). The scan `state.parallel is not None` cannot compile until FEAT-1074 lands the field on `StateConfig` with a `ParallelStateConfig` value exposing `.max_workers`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Architectural gap the issue body does not address.** The proposed scan — `for s in fsm.states.values() if s.parallel is not None` — requires access to the loaded `FSMLoop`. At the CLI layer:

- `parallel.py` (`main_parallel`, lines 31–237) does **not** load a loop definition. It builds `parallel_config` (line 195), constructs a `ParallelOrchestrator` (line 229), and calls `orchestrator.run()` (line 237). Loop YAMLs are resolved per-issue **inside worker processes** by the orchestrator; the CLI never holds an `FSMLoop` instance and has no `loop_name` variable. The issue's proposed code `loop_name`, `len(issue_ids)`, and `max(s.parallel.max_workers for s in parallel_states)` reference values that do not exist at the proposed warning site.

- `sprint/run.py` similarly delegates to `ParallelOrchestrator` (lines 389–410). The same loop-loading gap applies.

- `auto.py` (`main_auto`) instantiates `AutoManager` (line 90) and calls `manager.run()` (line 104); loop loading is inside `AutoManager`, not the CLI. The comment-only change still fits, but the comment must live near the `AutoManager` construction (lines 90–104).

**Implementation implication**: implementer must either (a) extend the CLI to load & introspect the loop definition before constructing the orchestrator, (b) surface a helper on `ParallelOrchestrator` / `AutoManager` that returns parallel-state metadata, or (c) move the scan into the orchestrator itself (contradicts the issue's "CLI-layer-by-design" directive at line 79). Option (a) is most faithful to the issue intent but adds a `load_loop(...)` call (at `scripts/little_loops/cli/loop/_helpers.py:117`) to each CLI path.

**`ll-sprint --parallel` does not exist.** The `run` subparser in `sprint/__init__.py:115-134` does **not** register a `--parallel` flag. Sprint parallelism is automatic: `run.py:332` runs sequentially when `len(wave) == 1 or is_contention_subwave`, and enters the orchestrator path otherwise. The warning condition must therefore be "wave will dispatch to orchestrator" (i.e., at `run.py:389` before `create_parallel_config`), not "if `--parallel` is passed."

**`ll-parallel` worker count (N).** `args.workers` (line 196) may be `None` at the CLI layer; the resolved N is computed inside `create_parallel_config` and stored on the returned `parallel_config` object. To compute `N*M` at the warning site, read `parallel_config.max_workers` (resolved) rather than `args.workers`.

**Test file renames.** Rename the new-file targets in the issue:
- `scripts/tests/test_ll_parallel.py` → keep name (no conflict)
- `scripts/tests/test_ll_auto.py` → keep name (no conflict)
- `scripts/tests/test_ll_sprint.py` (to extend) → does not exist; extend `scripts/tests/test_sprint_integration.py` instead

## Acceptance Criteria

- Loading a loop with any `parallel:` state under `ll-parallel` emits exactly one WARNING to stderr naming the cumulative worker budget
- Same under `ll-sprint --parallel`; no warning under `ll-sprint` without `--parallel`
- No warning under `ll-auto`; comment present in the CLI module explaining why
- Tests assert warning fires exactly once per run and includes computed `N*M` product

## Impact

- **Priority**: P2
- **Effort**: Small — 3 CLI file changes (1 comment-only) + 2 new test files + 1 test extension
- **Risk**: Low — Warning is observability-only; no behavior change to loop execution
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `cli`, `observability`

---

**Open** | Created: 2026-04-21 | Priority: P2

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 93/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Outcome Risk Factors
- **Test blast radius**: Adding `load_loop_with_spec` to `main_parallel()` and sprint dispatch will break 10+ tests across `test_cli.py:495–568`, `:1601–1724` and `test_sprint_integration.py:267–480`, `:553–1803` with `FileNotFoundError`. Plan mock scaffolding as the first commit before warning logic.
- **Raw YAML fragility**: The FEAT-1074 workaround reads `s.get("parallel").get("max_workers", 1)` from raw spec — silent drift risk if FEAT-1074 later changes the YAML key shape. Low risk for now; revisit when FEAT-1074 lands.
- **Sprint dispatch condition**: No `--parallel` flag exists; the warning condition is "wave dispatched to orchestrator" (before `create_parallel_config` at run.py:397). Getting this condition inverted (`len(wave) == 1 or is_contention_subwave` = skip) is a subtle correctness risk worth double-checking.

## Design Decisions (Resolved by `/ll:refine-issue`)

_These open questions from prior passes are resolved based on codebase research:_

### 1. Warning mechanism: `print("⚠ ...", file=sys.stderr)` recommended

The existing codebase convention (`config_cmds.py:27`) uses `print(f"  ⚠ {w}")` to **stdout** with no `file=` argument. `warnings.warn` is completely absent from `scripts/little_loops/`.

**Recommendation**: use `print(f"⚠ ...", file=sys.stderr)` (explicit stderr) to distinguish runtime warnings from normal CLI output. Tests assert via `capsys.readouterr().err`. If stdout consistency is preferred, use `print(f"⚠ ...")` and assert via `.out` (matches `test_ll_loop_commands.py:75–107`). **Pick one approach and apply it consistently across `parallel.py` and `sprint/run.py`.**

### 2. FEAT-1074 workaround: scan raw YAML spec via `load_loop_with_spec`

`StateConfig` (confirmed at `fsm/schema.py:180–316`) has **no `.parallel` attribute today**.

Use `load_loop_with_spec` (`_helpers.py:131`) which returns `(FSMLoop, dict[str, Any])`. Scan the raw spec dict:

```python
from little_loops.cli.loop._helpers import load_loop_with_spec

_fsm, spec = load_loop_with_spec(args.loop, config.get_loops_dir(), logger)
parallel_states = [
    s for s in spec.get("states", {}).values()
    if s.get("parallel") is not None
]
if parallel_states:
    m = max(s["parallel"].get("max_workers", 1) for s in parallel_states)
    n = parallel_config.max_workers  # resolved int, never None
    print(
        f"⚠ loop '{args.loop}' contains parallel state(s); ll-parallel concurrency ({n}) "
        f"multiplies inner parallel concurrency ({m}). "
        f"Cumulative worker budget: {n}*{m}={n*m}. "
        f"Consider reducing inner max_workers or running under ll-auto.",
        file=sys.stderr,
    )
```

`parallel_config.max_workers` is **always a resolved int** after `create_parallel_config` (`config/core.py:302–303`: `max_workers or self._parallel.base.max_workers`). Never read `args.workers` directly — it may be `None`.

### 3. Exact insertion points (confirmed)

- **`parallel.py`**: insert warning block after line 213 (close of `create_parallel_config`), before line 229 (`ParallelOrchestrator` construction).
- **`sprint/run.py`**: insert warning block after line 397 (close of `create_parallel_config`), before line 404 (`ParallelOrchestrator` construction).
- **`auto.py`**: insert inline comment before line 90 (before `manager = AutoManager(...)`):
  ```python
  # ll-auto processes issues sequentially — inner parallel: states use their own
  # max_workers budget without multiplying outer concurrency.
  ```

### 4. `load_loop_with_spec` signature (confirmed at `_helpers.py:131`)

```python
def load_loop_with_spec(
    name_or_path: str, loops_dir: Path, logger: Logger
) -> tuple[FSMLoop, dict[str, Any]]:
```

Mock pattern for updated existing tests:

```python
# Suppress warning in pre-existing parallel tests — empty spec = no parallel states
patch("little_loops.cli.parallel.load_loop_with_spec", return_value=(MagicMock(), {}))

# Sprint equivalent (monkeypatch style used in test_sprint_integration.py)
monkeypatch.setattr("little_loops.cli.sprint.run.load_loop_with_spec", lambda *a, **k: (MagicMock(), {}))
```

For new warning-assertion tests, use a spec with a parallel state:
```python
mock_spec = {"states": {"scan_issues": {"parallel": {"max_workers": 4}}}}
patch("little_loops.cli.parallel.load_loop_with_spec", return_value=(MagicMock(), mock_spec))
```

### 5. Test patterns to follow

- **Loop YAML fixture**: write to `tmp_path / ".loops" / "test-loop.yaml"` via triple-quoted string (pattern: `test_ll_loop_state.py:212–224`)
- **Warning assertion**: `capsys.readouterr().err` and assert `"⚠" in captured.err` and the `"N*M="` product string
- **`TestMainParallelIntegration` mock update** (`test_cli.py:495–568`, `1601–1724`): add `patch("little_loops.cli.parallel.load_loop_with_spec", return_value=(MagicMock(), {}))` to the existing `with (...)` block in each test
- **Sprint mock update** (`test_sprint_integration.py:267–480`, `553–1803`): add `monkeypatch.setattr("little_loops.cli.sprint.run.load_loop_with_spec", lambda *a, **k: (MagicMock(), {}))` alongside the existing `ParallelOrchestrator` setattr

## Session Log
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644812c0-533a-4e26-96b6-038b38467391.jsonl`
- `/ll:refine-issue` - 2026-04-21T16:26:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/444f6307-f957-4298-afd7-8110637a61ba.jsonl`
- `/ll:wire-issue` - 2026-04-21T16:19:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5e62948-0099-497f-bfc8-c00efc10983d.jsonl`
- `/ll:refine-issue` - 2026-04-21T16:11:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7a2ae01-e999-4e1d-b35a-80cc743b6a7d.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c25b41ad-2e86-4d04-bea4-6daf251405e7.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5e62948-0099-497f-bfc8-c00efc10983d.jsonl`
