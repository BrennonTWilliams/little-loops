---
id: FEAT-2259
title: Generic host-parameterized conformance harness
type: feature
status: done
priority: P4
discovered_date: 2026-06-24
captured_at: 2026-06-24 00:00:00+00:00
completed_at: 2026-06-26 18:57:22+00:00
discovered_by: planning-assessment
parent: EPIC-2257
decision_ref: ARCHITECTURE-049
labels:
- host-compat
- portfolio
- conformance
- testing
relates_to:
- FEAT-1721
- FEAT-2192
decision_needed: false
learning_tests_required:
- pytest
confidence_score: 94
outcome_confidence: 83
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 19
score_change_surface: 25
---

# FEAT-2259: Generic host-parameterized conformance harness

## Summary

Build **one** host-parameterized conformance harness that exercises the
`ll-auto` / `ll-sprint` / `ll-loop` / `ll-action` golden paths against a host
passed as an argument (`--host codex|gemini|omp`), instead of a bespoke
conformance suite per host epic.

Per ARCHITECTURE-049, this replaces the independently-specified per-host
conformance children:
- **FEAT-1721** (Codex conformance)
- **FEAT-2192** (Gemini conformance)
- the omp conformance need (now folded here, not re-specified under EPIC-2258)

## Current Behavior

Each host integration requires a bespoke conformance suite. FEAT-1721 specified
Codex-specific tests; FEAT-2192 specified Gemini-specific tests. Every new host
means a new issue and a new test file that re-derives the same four golden-path
scenarios (`ll-auto`, `ll-sprint`, `ll-loop`, `ll-action`). Conformance coverage
scales as O(N) new files per host — there is no shared harness.

## Expected Behavior

One parameterized harness runs all four golden paths against any registered host
via a `--host <host>` argument. Adding a host requires only a host registry
entry, not new test code. The harness outputs per-host pass/fail rows compatible
with `HOST_COMPATIBILITY.md`.

## Motivation

Each per-host epic re-derived the same conformance suite. A single harness that
takes a host arg means a new host's conformance coverage is a config row, not a
new issue + new test file.

## Use Case

A developer enabling OMP conformance runs `ll-harness --host omp` (or
`pytest -k conformance --host omp`) and receives a pass/fail matrix for the four
golden paths, without writing any OMP-specific test code. When Gemini support
lands, `--host gemini` immediately measures Gemini conformance as a side-effect
of the generic harness.

## Acceptance Criteria

- One harness (CLI or pytest-parametrized) runs the four golden paths against
  any registered host via a `--host`/parametrize arg.
- Produces per-host pass/fail rows consumable by `HOST_COMPATIBILITY.md`.
- Codex and Gemini conformance run through this harness (FEAT-1721 / FEAT-2192
  closed as superseded once it lands).
- Adding a host requires no new conformance code — only a host entry.

## Proposed Solution

Build on `ll-harness` (existing one-shot runner evaluation CLI) as the primary
integration point. Parametrize over `resolve_host()` from `host_runner.py`.

**Option A — pytest-parametrized:**
> **Selected:** Option A — pytest-parametrized — exact codebase idiom fit (resolve_host env-injection + parametrize already in 70+ tests); test-only addition, no production code changes.
```python
@pytest.mark.parametrize("host", ["codex", "gemini", "omp"])
def test_conformance_golden_path(host, golden_path):
    invocation = resolve_host(host).build_streaming(...)
    result = run_conformance(invocation, golden_path)
    assert result.exit_code == 0
```

**Option B — CLI wrapper (`ll-harness --suite conformance`):**
```bash
ll-harness --host codex --suite conformance
ll-harness --host gemini --suite conformance
```

The four golden paths to exercise: `ll-auto`, `ll-sprint`, `ll-loop`, `ll-action`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **API correction — `resolve_host()` takes `env: dict`, not a positional host arg.** Option A's example must use `resolve_host(env={"LL_HOST_CLI": host})`, not `resolve_host(host)`. The env-injection path is already exercised in `scripts/tests/test_host_runner.py:TestResolveHost.test_detect_explicit_override`.
- **Option B requires a new `--host` flag on `ll-harness`.** `scripts/little_loops/cli/harness.py` currently has no `--host` argument; host selection is entirely implicit via `LL_HOST_CLI` env var or binary probe. Option B would add `--host` to `_build_harness_parser()` and inject it as `os.environ["LL_HOST_CLI"] = args.host` before calling `resolve_host()`.
- **`opencode` and `pi` runners are stubs.** In `_HOST_RUNNER_REGISTRY`, `OpenCodeRunner` and `PiRunner` have all `build_*` methods raising `HostNotConfigured`. Conformance tests for those hosts need two skip layers: binary availability (`shutil.which(binary) is None`) and a stub detection check.
- **Pytest `conformance` marker needs registration in `scripts/pyproject.toml`** (lines 132–147 already have pytest marker config). Pattern: `conformance: mark tests as host conformance tests`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-25.

**Selected**: Option A — pytest-parametrized

**Reasoning**: Option A matches the established `pytest.mark.parametrize` idiom used across 70+ test sites and the `resolve_host(env={"LL_HOST_CLI": host})` injection pattern already used in 13 call sites in `test_host_runner.py`. It requires only test-side additions (new directory, marker registration, fixture relocation, skip guards) with zero production code changes. Option B requires non-trivial parser surgery on `harness.py`, introduces `os.environ` mutation diverging from the existing subprocess-env injection pattern, and builds all four golden-path invocations and aggregation from scratch with no existing template.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — pytest-parametrized | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B — CLI wrapper | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |

**Key evidence**:
- **Option A**: `pytest.mark.parametrize` used 70+ times; `resolve_host(env=...)` canonical at 13 test call sites in `test_host_runner.py`; `isolated_env` + conftest fixtures directly reusable; test-only addition
- **Option B**: No `--host`/`--suite` in `_build_harness_parser()`; `subparsers.required = True` requires new `conformance` subparser noun; `os.environ` mutation diverges from subprocess-env pattern in `_run_cross_host_validation()`; all four golden-path invocations and aggregation are net-new inside `ll-harness` with no existing template

## Note — `--host codex` backflow (closes FEAT-1721)

This harness is built during the **Gemini** phase (its first new-host consumer),
but it is host-agnostic by construction, so once it lands, running it
`--host codex` exercises the Codex golden paths and **satisfies FEAT-1721**
(Codex conformance) with no Codex-specific code. This is the deliberate payoff
of sequencing Gemini ahead of EPIC-1463 polish: Codex conformance arrives as a
near-free backflow *from* the Gemini work rather than as separate Codex effort.
After this lands, sweep the Codex column of `HOST_COMPATIBILITY.md` via
`--host codex` and close FEAT-1721 as superseded.

## Implementation Steps

1. Define the four golden-path test fixtures and expected exit-code / output criteria
2. Implement `--host` / pytest parametrize interface on the conformance runner
3. Integrate with `resolve_host()` registry from `host_runner.py`
4. Add `HOST_COMPATIBILITY.md` output format (per-host pass/fail rows)
5. Run `--host codex` and `--host gemini`; verify coverage against FEAT-1721 / FEAT-2192 acceptance criteria
6. Close FEAT-1721 and FEAT-2192 as superseded once coverage is confirmed

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Register `conformance` pytest marker in `scripts/pyproject.toml` at `[tool.pytest.ini_options].markers` — do this **first** (before creating any test file) because `--strict-markers` in `addopts` will block `pytest` collection the moment any test uses `@pytest.mark.conformance` without registration
8. Create `scripts/tests/conformance/__init__.py` (empty file) for pytest package-style discovery alongside the existing `scripts/tests/__init__.py`
9. Resolve `isolated_env` fixture scope: either promote it from `scripts/tests/test_host_runner.py` into `scripts/tests/conftest.py`, or create `scripts/tests/conformance/conftest.py` and define it there — the conformance test module cannot see fixtures defined in a sibling test file
10. Update `docs/development/TESTING.md` markers table to add `conformance` row; mention `conformance/` subdirectory in `## Test Suite Organization`
11. Create `docs/development/CONFORMANCE.md` with harness invocation examples (`pytest -m conformance --host <host>`) and a baseline pass/fail board template (absorbed from FEAT-1721 AC)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 2 (pytest option A)**: Use `@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))` from `scripts/little_loops/host_runner.py`. Per-host selection: `monkeypatch.setenv("LL_HOST_CLI", host)` plus the `isolated_env` fixture from `scripts/tests/test_host_runner.py` to clear ambient env vars before each parametrized run.
- **Step 2 (CLI option B)**: Add `--host` to `_build_harness_parser()` in `scripts/little_loops/cli/harness.py`; inject as `os.environ["LL_HOST_CLI"] = args.host` before calling `resolve_host()`, following the precedent in `scripts/little_loops/cli/loop/_helpers.py:_run_cross_host_validation()`.
- **Step 3**: `resolve_host()` signature is `resolve_host(env: dict[str, str] | None = None)` — pass `env={"LL_HOST_CLI": host}` for per-host isolation without requiring `monkeypatch`.
- **Step 5 (skip guard)**: `@pytest.mark.skipif(shutil.which("<binary>") is None, reason="<host> CLI not installed")` — binary name mapping from `_PROBE_ORDER` in `host_runner.py`. Add a second guard for stub runners (`HostNotConfigured` on `build_streaming`).
- **Step 6**: After closing FEAT-1721/FEAT-2192, update "Orchestration CLI" table in `docs/reference/HOST_COMPATIBILITY.md` — table already has the four golden-path tool rows; add a conformance coverage annotation per host column.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `resolve_host()` registry; may need a conformance-mode hook
- New: `scripts/tests/conformance/test_host_conformance.py` — parametrized test suite

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — register `conformance` pytest marker in `[tool.pytest.ini_options].markers`; `--strict-markers` in `addopts` will cause collection failure without it [Agent 2 finding]
- New: `scripts/tests/conformance/__init__.py` — empty package init required for pytest package-style discovery under `scripts/tests/` [Agent 3 finding]

### Dependent Files (Callers/Importers)
- `ll-harness` CLI — existing integration point; extend with `--suite conformance` or similar flag

### Similar Patterns
- `scripts/tests/test_builtin_loops.py` — existing golden-path test patterns to follow

### Tests
- New `scripts/tests/conformance/` directory (or extend existing test suite)
- Per-host parametrized test covering each of the four golden paths

_Wiring pass added by `/ll:wire-issue`:_
- `isolated_env` fixture — currently defined only in `scripts/tests/test_host_runner.py`, **not** in `scripts/tests/conftest.py`; conformance tests in `scripts/tests/conformance/` cannot see it unless it is promoted to `conftest.py` or redefined in a new `scripts/tests/conformance/conftest.py` [Agent 3 finding]
- New: `scripts/tests/conformance/conftest.py` — alternative scoping location for `isolated_env` if promotion to top-level `conftest.py` is undesirable [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — update with per-host conformance pass/fail rows
- FEAT-1721 and FEAT-2192 issue files — close as superseded after harness lands (both already `cancelled`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` — markers table (~line 1026) lists only `integration` and `slow`; add `conformance` row; also add mention of `conformance/` subdirectory in `## Test Suite Organization` section [Agent 2 finding]
- New: `docs/development/CONFORMANCE.md` — harness run instructions and baseline pass/fail board; absorbed from FEAT-1721 acceptance criteria which FEAT-2259 supersedes [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` at `[tool.pytest.ini_options].markers` — add `"conformance: mark tests as host conformance tests (deselect with '-m \"not conformance\"')"` following the `integration` and `slow` entries; `--strict-markers` causes collection failure without registration [Agent 2/3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional test files to inform implementation:**
- `scripts/tests/test_cli_harness.py` — `FakeRunner` test double, `_make_namespace()`, `_make_completed()` helpers; exit-code assertion patterns for `cmd_skill`/`cmd_cmd`
- `scripts/tests/test_host_runner.py` — `isolated_env` fixture (clears `LL_HOST_CLI`/`LL_HOOK_HOST`); `resolve_host(env={"LL_HOST_CLI": ...})` direct-injection patterns; `_HOST_RUNNER_REGISTRY` membership assertions
- `scripts/tests/test_cross_host_baseline.py` — `_make_probe_env()` helper; `LL_HOST_CLI` env capture from `subprocess.run` kwargs; multi-host subprocess invocation pattern
- `scripts/tests/test_cli_e2e.py:TestSequentialExecutionWorkflow.test_ll_auto_dry_run` — closest existing end-to-end `ll-auto` golden-path test via `sys.argv` injection + `monkeypatch.chdir`
- `scripts/tests/conftest.py` — `temp_project_dir`, `config_file`, `issues_dir`, `_isolate_history_db` (autouse) fixtures reusable by conformance tests

**Authoritative host list for parametrize:**
- `scripts/little_loops/host_runner.py:_HOST_RUNNER_REGISTRY` — current keys: `"claude-code"`, `"codex"`, `"opencode"`, `"pi"`. Use `list(_HOST_RUNNER_REGISTRY.keys())` as the parametrize iterable so new hosts are automatically included.

## Impact

- **Effort**: Medium.
- **Risk**: Low — test-only; no runtime behavior change.
- **Breaking Change**: No.

## Resolution

Implemented 2026-06-26 via `/ll:manage-issue`.

- `scripts/pyproject.toml`: registered `conformance` pytest marker
- `scripts/tests/conformance/__init__.py`: empty package init
- `scripts/tests/conformance/conftest.py`: `isolated_env` fixture + `--conformance-host` option
- `scripts/tests/conformance/test_host_conformance.py`: 16 parametrized tests (4 golden paths × 4 hosts); 8 PASS (claude-code, codex), 8 SKIP (opencode, pi stubs)
- `docs/development/CONFORMANCE.md`: harness run docs + baseline board
- `docs/development/TESTING.md`: added `conformance/` to directory structure + marker table
- `docs/reference/HOST_COMPATIBILITY.md`: added Conformance harness row + `[^conf]` footnote

Codex conformance confirmed via `--conformance-host codex` (all 4 golden paths PASS).
FEAT-1721 can be closed as superseded. FEAT-2192 pending GeminiRunner landing.

## Status

**Done** | Created: 2026-06-24 | Completed: 2026-06-26 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-06-26T18:57:22Z - implementation complete
- `/ll:ready-issue` - 2026-06-26T18:46:59 - `f4c1b96c-6eb1-4b0d-9a01-f9a61ebd45f2.jsonl`
- `/ll:confidence-check` - 2026-06-26T00:00:00 - `36fe0b13-b39e-4a8f-99e9-b13deb64e7b8.jsonl`
- `/ll:confidence-check` - 2026-06-25T00:00:00 - `4bf59de2-23a4-414b-a149-93b27c0b197d.jsonl`
- `/ll:wire-issue` - 2026-06-25T18:48:08 - `0eaae7ef-edbe-497f-bc91-15b8fc518594.jsonl`
- `/ll:decide-issue` - 2026-06-25T18:38:10 - `70f59565-7e94-410d-bf6c-c34dd59cbf9f.jsonl`
- `/ll:refine-issue` - 2026-06-25T18:29:32 - `9285574b-00e2-4b27-85e4-574f9b9140d0.jsonl`
- `/ll:format-issue` - 2026-06-25T18:19:48 - `e27f501c-1ebe-4d74-afe6-614f2df00059.jsonl`
