---
id: BUG-2957
title: Tamper guard vetoes any pyproject.toml edit in projects using [tool.pytest.ini_options]
type: BUG
priority: P2
status: open
captured_at: '2026-08-01T01:25:49Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- BUG-2954
- ENH-2933
- ENH-2935
- ENH-2854
---

# BUG-2957: Tamper guard vetoes any pyproject.toml edit in projects using [tool.pytest.ini_options]

## Summary

In any project whose pytest config lives in `pyproject.toml`
(`[tool.pytest.ini_options]`), the tamper guard treats **every** modification
to `pyproject.toml` as a tamper finding — including version bumps, dependency
changes, and ruff/mypy config edits that have nothing to do with test
selection. Under the default `tamper_guard.policy: fail` this vetoes issue
completion for routine, entirely legitimate work.

This repo is masked from the bug because it uses `pytest.ini`, so
`pyproject.toml` never enters its candidate set. It bites consumer projects,
which is most of the pip-package install base.

## Current Behavior

`resolved_pytest_config_paths` (`scripts/little_loops/test_tamper_guard.py:163-187`)
resolves pytest's config file in pytest's own discovery order. When
`pytest.ini` is absent and `pyproject.toml` contains
`[tool.pytest.ini_options]`, it returns `['pyproject.toml']`.

`tamper_guard_candidate_paths` (`test_tamper_guard.py:86-106`) unions those
config paths into the snapshot set unconditionally, and `run_tamper_guard`
(`test_tamper_guard.py:270-279`) re-unions them into `after_paths`. The
comparison is whole-file sha256 (`compare_snapshots`, `test_tamper_guard.py:127-146`),
so any byte change anywhere in `pyproject.toml` produces a
`TamperFinding(kind="modified", is_config=True)`, and `apply_tamper_policy`
under `fail` returns `passed=False`.

Reproduced on a synthetic repo (no test file touched at all — a bare version
bump):

```
candidates : ['pyproject.toml']
findings   : [('pyproject.toml', 'modified', True)]
passed     : False
```

## Expected Behavior

Only changes to the portion of the config that governs **which tests run**
should count as tamper findings. A version bump, a dependency addition, or a
`[tool.ruff]` edit in the same file must not veto completion.

Concretely: for a multi-purpose config file, compare the resolved pytest
section (`[tool.pytest.ini_options]`) rather than the whole file. Single-
purpose config files (`pytest.ini`, `tox.ini`'s `[pytest]`, `setup.cfg`'s
`[tool:pytest]`) keep whole-file comparison where the whole file — or the
relevant section — is already pytest-scoped.

## Motivation

`pyproject.toml` with `[tool.pytest.ini_options]` is the mainstream modern
Python layout, and editing it is routine implementation work. For those
projects the tamper guard fires on ordinary changes with no test tampering
involved, producing exactly the failure mode BUG-2954 describes: a full
implement cycle burned, then a misleading rejection at the finalize step.

BUG-2954 fixes the test-file half of this false-positive class and
deliberately leaves the config half content-agnostic, because a config edit
changes which tests run and is not measurable by source-strength metrics.
That reasoning is correct for `pytest.ini`; it is wrong for a file where the
pytest table is one section among many. Without this fix, BUG-2954 ships a
guard that is safe for this repo and still broken for its consumers.

## Proposed Solution

Make config-file comparison section-scoped when the resolved config file is
multi-purpose:

- Return enough information from config resolution to identify *what to
  compare*, not just which file — a path plus an optional section selector
  (e.g. the TOML table path `tool.pytest.ini_options`, or an INI section
  name). `pytest.ini` gets no selector (whole file).
- When a selector is present, hash the canonicalized serialization of that
  section only, so edits elsewhere in the file are invisible to the guard.
- Preserve the current fail-closed behavior for unparseable config: if the
  section cannot be extracted (TOML parse error), fall back to whole-file
  comparison rather than silently passing.

This composes with BUG-2954's `finding_filter` rather than competing with it:
BUG-2954 filters *test-file* findings by weakening; this narrows what
produces a *config-file* finding in the first place.

### Alternatives considered

- *Drop config files from the candidate set entirely*: removes a real
  attack surface — editing `testpaths`/`addopts` (`-p no:randomly`,
  `--ignore=...`) is a genuine way to make a failing suite "pass".
- *Treat config findings as warnings only*: same loss of enforcement, and
  inconsistent with `pytest.ini` projects where the current strictness is
  correct.

## Integration Map

### Files to Modify
- `scripts/little_loops/test_tamper_guard.py` — `resolved_pytest_config_paths`
  (carry the section selector), `snapshot_test_paths` /
  `snapshot_test_paths_at_ref` (section-aware hashing for selected paths),
  `tamper_guard_candidate_paths`, `run_tamper_guard`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/work_verification.py` (`_run_non_fsm_tamper_guard`)
  and `scripts/little_loops/fsm/executor.py` (~L1407-1474) both consume
  `tamper_guard_candidate_paths` / `snapshot_test_paths`; a return-shape
  change to config resolution reaches both adapters.

### Tests
- `scripts/tests/test_test_tamper_guard.py` — section-scoped comparison
  cases: pyproject version bump does not trip; `[tool.pytest.ini_options]`
  `addopts`/`testpaths` edit does trip; `pytest.ini` whole-file behavior
  unchanged; unparseable TOML falls back to whole-file.

### Configuration
- N/A — no new config key; `tamper_guard.policy` semantics unchanged.

## Program Design

### Types

New dataclass `ConfigTarget`, naming a config file plus the sub-document that
actually governs test selection:

- `path: str`
- `section: tuple[str, ...] | None`

`section` is `("tool", "pytest", "ini_options")` for `pyproject.toml` and
`None` for `pytest.ini` (whole-file comparison).

### Signatures

In `scripts/little_loops/test_tamper_guard.py`:

- `resolved_pytest_config_targets(repo_root: Path) -> list[ConfigTarget]`
- `hash_config_target(source: str, target: ConfigTarget) -> str`

`resolved_pytest_config_targets` is the section-aware successor to
`resolved_pytest_config_paths`; keep the existing path-only function as a
thin wrapper so current callers and tests keep working.
`hash_config_target` hashes the canonicalized selected section, or the whole
source when `section is None` or extraction fails.

### Call Path

`work_verification._run_non_fsm_tamper_guard` / `fsm.executor._run_state`
→ `tamper_guard_candidate_paths` → `resolved_pytest_config_targets`
→ `snapshot_test_paths` / `snapshot_test_paths_at_ref` → `hash_config_target`
→ `compare_snapshots` → `apply_tamper_policy`

## Implementation Steps

1. Add `ConfigTarget` and `resolved_pytest_config_targets`, keeping
   `resolved_pytest_config_paths` as a compatibility wrapper.
2. Add `hash_config_target` with canonical TOML/INI section serialization and
   whole-file fallback on parse failure.
3. Thread targets through `tamper_guard_candidate_paths`, both snapshot
   functions, and `run_tamper_guard`'s `after_paths` construction.
4. Add the test cases listed under Integration Map → Tests.
5. Run the full suite; confirm no regression in ENH-2933/2934/2935 coverage
   and that `pytest.ini`-based behavior (this repo) is byte-for-byte
   unchanged.

## Impact

- **Priority**: P2 — silently blocks issue completion on routine edits for
  every consumer project using `[tool.pytest.ini_options]` with the default
  `tamper_guard.policy: fail`. Same severity and shape as BUG-2954; masked in
  this repo only because it uses `pytest.ini`.
- **Effort**: Small-Medium — contained to `test_tamper_guard.py` plus a
  return-shape change that both adapters consume.
- **Risk**: Medium — must not weaken detection of genuine `addopts`/
  `testpaths` tampering while removing the false positive.
- **Breaking Change**: No

## Steps to Reproduce

1. Create a project with no `pytest.ini` whose `pyproject.toml` contains a
   `[tool.pytest.ini_options]` table. Commit it.
2. Make any edit elsewhere in `pyproject.toml` — e.g. bump `version` — and
   leave it uncommitted. Touch no test file.
3. Run the tamper guard against the pre-edit commit as its "before" ref
   under `fail` policy (equivalently: run an `ll-auto` issue whose work
   includes a version bump).
4. Observe a `('pyproject.toml', 'modified', is_config=True)` finding and
   `passed: False`, vetoing completion.

## Root Cause

- **File**: `scripts/little_loops/test_tamper_guard.py`
- **Anchor**: `resolved_pytest_config_paths()` → `tamper_guard_candidate_paths()`
  → `compare_snapshots()`
- **Cause**: Config files enter the guard's candidate set as whole-file
  paths and are compared by whole-file sha256. That is sound when the file is
  pytest-scoped end to end (`pytest.ini`), but `pyproject.toml` co-hosts
  project metadata, dependencies, and other tools' config, so the guard
  cannot distinguish a test-selection change from any other edit to the file.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-01T01:25:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e6bb49e-330c-449c-8327-ffed663d51ae.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
