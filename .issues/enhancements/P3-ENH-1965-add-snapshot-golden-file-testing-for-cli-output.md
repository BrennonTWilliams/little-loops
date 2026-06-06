---
id: ENH-1965
type: ENH
priority: P3
status: open
captured_at: '2026-06-05T21:16:36Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
- test-infrastructure
- captured
parent: EPIC-1967
confidence_score: 92
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 25
decision_needed: false
---

# ENH-1965: Add Snapshot/Golden-File Testing for CLI Output

## Summary

The project has no snapshot or golden-file testing for CLI output. Integrate a snapshot testing library (e.g., `syrupy` or `pytest-snapshot`) to enable regression testing of CLI output, TUI rendering, and formatted text. This is a prerequisite for safely testing the TUI rendering engine (`cli/loop/layout.py`, 1,981 lines).

## Context

Identified during a comprehensive test suite audit. The audit found zero snapshot/golden-file tests despite a large CLI surface area with formatted output. This gap makes it impossible to write regression tests for the TUI rendering engine without fragile string-matching assertions.

## Current Behavior

- CLI output testing relies on ad-hoc `assert "substring" in captured.stdout` patterns
- TUI rendering (`layout.py`, 1,981 lines) has zero tests — partially because there's no snapshot infrastructure
- No snapshot testing library is installed or configured
- The single E2E test file (`test_cli_e2e.py`, 533 lines) uses basic dry-run scenarios without output verification

## Expected Behavior

- `syrupy` or `pytest-snapshot` is installed and configured as a dev dependency
- Snapshot tests exist for key CLI output formats: sprint status tables, loop info displays, diagram rendering
- TUI rendering tests can snapshot rendered output for regression detection
- Snapshots are version-controlled and reviewed in PRs like any other test artifact
- Snapshot update workflow is documented in CONTRIBUTING.md

## Motivation

- **Unblocks TUI testing**: ENH-1964 (CLI layer tests) Phase 3 depends on snapshot infrastructure to test `layout.py`
- **Catches formatting regressions**: A refactor that changes CLI table formatting or diagram output will be caught
- **Industry standard**: Snapshot testing is the established pattern for testing rendered output in CLI tools, React components, and API responses
- **Low-effort, high-value tests**: Snapshot tests are quick to write once infrastructure is in place

## Current Pain Point

Without snapshot testing, verifying CLI output correctness requires either (a) fragile substring assertions that break on any formatting change, or (b) manual visual inspection that doesn't scale. This is the primary reason `layout.py` (1,981 lines) has zero tests — there's no practical way to test TUI output without snapshot infrastructure.

## Proposed Solution

**Recommended: `syrupy`**
> **Selected:** syrupy — auto-injected `snapshot` fixture reuses existing `_USE_COLOR`/`terminal_width` patch patterns; tighter pytest assertion integration than pytest-snapshot; supports future binary output if diagram renderer evolves.

- Mature pytest plugin with snapshot file management
- Supports binary snapshots (useful for diagram/image output)
- Built-in snapshot update workflow (`pytest --snapshot-update`)
- Active maintenance and community

**Alternative: `pytest-snapshot`**
- Simpler API, fewer features
- May suffice if only text snapshots are needed

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-05.

**Selected**: syrupy

**Reasoning**: syrupy's auto-provided `snapshot` fixture integrates directly with the existing test patterns — `_USE_COLOR` and `terminal_width` are already patched in tests like `test_ll_loop_display.py`, and `strip_ansi()` from `output.py:46` normalizes colored output before comparison. While pytest-snapshot has a simpler API, syrupy's `assert snapshot == value` pattern requires no conftest ceremony and scores higher on codebase consistency. All current output is text (`str`), but `layout.py`'s FSM renderer may extend to image output, and syrupy handles that path.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| syrupy | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| pytest-snapshot | 2/3 | 3/3 | 2/3 | 3/3 | 10/12 |

**Key evidence**:
- syrupy: `assert snapshot == value` extends pytest assertions naturally; existing `_USE_COLOR` + `terminal_width` monkeypatches (14+ sites in `test_ll_loop_display.py`) map directly to determinism controls; `strip_ansi()` at `output.py:46` available for color-independent golden files; `helpers.py:make_test_state()` provides deterministic FSM inputs.
- pytest-snapshot: `snapshot.assert_match(value, "name")` API requires explicit snapshot names and conftest `snapshot_path` setup; no auto-injection; sufficient for text-only but extra ceremony compared to syrupy.

Implementation:
1. Add chosen library to `pyproject.toml` dev dependencies
2. Create a `conftest.py` fixture for snapshot testing
3. Write initial snapshot tests for 3-5 high-value CLI outputs
4. Document the snapshot workflow in CONTRIBUTING.md

## Success Metrics

- **Infrastructure**: Snapshot library installed and configured
- **Initial coverage**: ≥5 CLI commands have snapshot tests
- **Workflow documented**: Snapshot update process in CONTRIBUTING.md
- **Adoption**: Used by at least one subsequent issue (ENH-1964 Phase 3) within 30 days

## Scope Boundaries

- **In scope**: Library selection, installation, configuration, documentation
- **In scope**: Initial snapshot tests for 3-5 CLI outputs (sprint status, loop info, diagram preview)
- **Out of scope**: Comprehensive snapshot coverage of all CLI commands (follow-up work)
- **Out of scope**: Snapshot testing for non-CLI output (API responses, file output — deferred)

## API/Interface

New test fixtures and conventions:
```python
# Proposed fixture pattern
def test_sprint_status_output(snapshot):
    """Snapshot test for ll-sprint show output."""
    result = runner.invoke(sprint_cli, ["show", "my-sprint"])
    assert result.exit_code == 0
    assert snapshot == result.stdout

# Snapshot update workflow
# $ pytest --snapshot-update
```

## Integration Map

### Files to Modify
- `pyproject.toml` — add snapshot library to dev dependencies
- `scripts/tests/conftest.py` — add snapshot fixture if needed
- `scripts/tests/` — new snapshot test files

### Dependent Files (Callers/Importers)
- ENH-1964 Phase 3 — TUI rendering tests will use snapshot infrastructure
- Future CLI tests — all will benefit from snapshot capability

### Similar Patterns
- `test_cli_e2e.py` — existing CLI test patterns to extend with snapshots

### Tests
- New snapshot test files are the deliverable

### Documentation
- `CONTRIBUTING.md` — add "Snapshot Testing" section with update workflow
- `.claude/CLAUDE.md` — note snapshot testing convention

### Configuration
- `pyproject.toml` — dev dependency + pytest configuration

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Primary snapshot targets (pure `str`-returning functions — no stdout capture needed):**
- `scripts/little_loops/cli/loop/layout.py` — `_render_fsm_diagram()` at line ~1581; the main Sugiyama-layout dispatcher. Already imported and called directly in `test_ll_loop_display.py`; returns the full diagram string. Zero snapshot coverage today.
- `scripts/little_loops/cli/sprint/show.py` — `_render_execution_plan()`, `_render_dependency_graph()`, `_render_health_summary()` — pure str-returning renderers currently tested only with substring assertions in `test_cli_sprint_show.py`.
- `scripts/little_loops/cli/sprint/_helpers.py` — `_render_execution_plan()`, `_score_suffix()` — tabular sprint output.
- `scripts/little_loops/cli/output.py` — `table()`, `status_block()`, `progress()`, `sparkline()` — shared output primitives.

**Determinism control points (must pin for stable snapshots):**
- `scripts/little_loops/cli/output.py:68` — `_USE_COLOR: bool` — patch to `False` via `monkeypatch.setattr("little_loops.cli.output._USE_COLOR", False)` to strip ANSI from snapshots; patch `True` for color-inclusive snapshots.
- `scripts/little_loops/cli/output.py` — `terminal_width()` — already patched in existing tests (e.g., `test_terminal_width_no_overflow` patches `output_mod.terminal_width` to return `80`); must be pinned for deterministic diagram widths.
- `scripts/little_loops/cli/loop/layout.py` — `_USE_COLOR` module-level flag at layout.py — also patchable via `monkeypatch.setattr("little_loops.cli.loop.layout._USE_COLOR", False)`.

**Normalization utility:**
- `scripts/little_loops/cli/output.py:46` — `strip_ansi(text: str) -> str` — strips ANSI escape sequences; use in snapshot fixtures to produce color-independent golden files: `assert snapshot == strip_ansi(result)`.

**Existing conftest and helper patterns to extend:**
- `scripts/tests/conftest.py` — add a `snapshot_config` fixture that pins `_USE_COLOR=False` and `terminal_width=80` for all snapshot test classes; no syrupy-specific fixture needed (syrupy auto-provides `snapshot`).
- `scripts/tests/helpers.py` — `make_test_fsm(name, initial, states)` and `make_test_state()` already provide deterministic FSM objects for layout snapshot inputs.

**`pyproject.toml` insertion point** — dev dependencies follow `[project.optional-dependencies]` format (not `[dependency-groups]`); add `"syrupy>=4.0"` (or `"pytest-snapshot>=0.9"`) to the `dev` list around line 90–99.

**Additional documentation target:**
- `docs/development/TESTING.md` — comprehensive testing guide that also needs a "Snapshot Testing" section (not just `CONTRIBUTING.md`).

**No `__snapshots__` directory exists yet** — syrupy creates it automatically on first `pytest --snapshot-update` run under `scripts/tests/__snapshots__/`.

## Implementation Steps

1. Evaluate `syrupy` vs `pytest-snapshot` — check compatibility with existing pytest stack
2. Install chosen library and configure in `pyproject.toml`
3. Create conftest fixture and document snapshot directory structure
4. Write 3-5 initial snapshot tests for high-value CLI outputs
5. Document snapshot workflow in CONTRIBUTING.md (how to create, update, review snapshots)
6. Verify snapshot tests pass in CI

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Decide library** (`/ll:decide-issue ENH-1965` first) — then add to `scripts/pyproject.toml` `[project.optional-dependencies]` `dev` list (lines ~90–99): `"syrupy>=4.0"` or `"pytest-snapshot>=0.9"`. Install with `pip install -e "./scripts[dev]"`.

2. **No conftest fixture required for syrupy** — `snapshot` fixture is auto-provided. Add a `snapshot_config` autouse fixture (or `conftest.py` fixture) that pins determinism:
   ```python
   @pytest.fixture(autouse=True)
   def _stable_snapshot_env(monkeypatch):
       monkeypatch.setattr("little_loops.cli.output._USE_COLOR", False)
       monkeypatch.setattr("little_loops.cli.loop.layout._USE_COLOR", False)
       monkeypatch.setattr("little_loops.cli.output.terminal_width", lambda: 80)
   ```

3. **Write initial snapshots** — three high-value starting points (pure str functions, no capsys needed):
   - `scripts/little_loops/cli/loop/layout.py:_render_fsm_diagram()` — use `make_test_fsm()` from `scripts/tests/helpers.py` to build a 3–5 state FSM and snapshot the rendered string.
   - `scripts/little_loops/cli/sprint/show.py:_render_execution_plan()` — snapshot tabular sprint output.
   - `scripts/little_loops/cli/output.py:table()` — snapshot the shared table formatter.

4. **Use `strip_ansi()` from `scripts/little_loops/cli/output.py:46`** to normalize colored outputs before comparison when snapshots need to be color-independent.

5. **Run first pass** with `pytest --snapshot-update scripts/tests/test_snapshot_*.py` to generate `scripts/tests/__snapshots__/` golden files; commit alongside tests.

6. **Document** in both `CONTRIBUTING.md` (user-facing) and `docs/development/TESTING.md` (developer-facing): how to create new snapshots, update with `--snapshot-update`, and review diffs in PRs.

## Backwards Compatibility

- No breaking changes — purely additive (new dev dependency + new tests)
- Existing assertion-based CLI tests continue to work unchanged

## Impact

- **Priority**: P3 — Important infrastructure, unblocks other work, but not blocking current development
- **Effort**: Medium — Library evaluation, configuration, initial tests, documentation
- **Risk**: Low — Dev-only dependency; no production impact
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Development practices and testing guidelines |

## Labels

`test-infrastructure`, `captured`

## Session Log
- `/ll:decide-issue` - 2026-06-06T01:19:09 - `60252756-dfe4-4839-a040-9e695b6bbda9.jsonl`
- `/ll:refine-issue` - 2026-06-06T01:15:28 - `29abb545-c9b4-44b9-a8c6-120d2bc97de8.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/347e9484-c3e2-47a8-9a1c-7cc7a84bb3da.jsonl`
- `/ll:format-issue` - 2026-06-05T22:11:41 - `f7a66d88-a8bc-4214-b6ed-218118867b50.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P3
