---
id: BUG-2957
title: Tamper guard vetoes any pyproject.toml edit in projects using [tool.pytest.ini_options]
type: BUG
priority: P2
status: done
captured_at: '2026-08-01T01:25:49Z'
completed_at: '2026-08-01T05:55:38Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- BUG-2954
- ENH-2933
- ENH-2935
- ENH-2854
- BUG-2959
- BUG-2962
confidence_score: 98
outcome_confidence: 80
score_complexity: 17
score_test_coverage: 21
score_ambiguity: 22
score_change_surface: 20
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Canonicalization recipe**: the codebase has no existing dotted-path TOML
  table walker (only the chained `.get("tool", {}).get("pytest", {})` idiom
  already used in `resolved_pytest_config_paths`) and no TOML/dict
  canonicalizer to reuse verbatim, but it does have an established
  deterministic-hashing idiom to follow for `hash_config_target`:
  `json.dumps(payload, sort_keys=True, default=str)` then
  `hashlib.sha256(blob.encode("utf-8")).hexdigest()`, used in
  `scripts/little_loops/prompts/fragment_store.py:26-32` and
  `scripts/little_loops/session_store/writers.py:1928-1934`
  (`_hash_args`, which additionally wraps in `try/except (TypeError,
  ValueError)` with a `repr(value)` fallback — relevant since a `tomllib`-
  parsed table can contain non-JSON-native values like `datetime`/`date`).
  This matches `test_tamper_guard.py`'s own `_sha256_bytes`/`_sha256_file`
  hashing convention (`:59-69`).
- **No `configparser` precedent**: `tox.ini`'s `[pytest]` and `setup.cfg`'s
  `[tool:pytest]` are currently detected by plain substring check on file
  text (`test_tamper_guard.py:314,318`), not real section parsing —
  `configparser` is not used anywhere else in `scripts/little_loops/`. If a
  future iteration extends section-scoping to those formats (out of scope
  per this issue's "Single-purpose config files ... keep whole-file
  comparison" decision), it would be a new stdlib usage with no in-repo
  extraction helper to copy from.
- **Test convention to extend**: `scripts/tests/test_test_tamper_guard.py`
  already has a `TestResolvedPytestConfigPaths` class (`:130-157`) with one
  `tmp_path`-based method per config-file-kind branch (e.g.
  `test_pyproject_ini_options_detected`), and imports every public symbol
  under test from `little_loops.test_tamper_guard` in one alphabetically
  ordered `from ... import (...)` block (`:22-41`) — new symbols
  (`ConfigTarget`, `hash_config_target`, `resolved_pytest_config_targets`)
  slot in alphabetically there. None of these new test cases need the
  git-repo fixture (`_init_repo`/`copy_git_template`) that
  `TestSnapshotTestPathsAtRef` uses — plain `tmp_path` suffices unless a
  case also exercises `run_tamper_guard`'s full snapshot-diff flow.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — `TestTamperGuardExecutorHook`
  (~L10702) is the FSM-adapter-side integration suite for `run_tamper_guard`,
  parallel to `TestRunTamperGuard` in `test_test_tamper_guard.py`, but has no
  `pyproject.toml`/`[tool.pytest.ini_options]` case today. `fsm/executor.py`
  is already listed above as a caller of the changed resolution path; per
  this issue's own Root Cause note, a fix that only reaches
  `work_verification.py`'s `finding_filter` "would leave that adapter's
  `pyproject.toml` false positive completely unaddressed" — the same logic
  means the FSM adapter's *test* coverage needs the same new case, not just
  its production code path. [Agent 1/3 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — add a `TestTamperGuardExecutorHook`
  case mirroring the new `pyproject.toml`-with-`[tool.pytest.ini_options]`
  version-bump-does-not-trip scenario, confirming `fsm/executor.py::_check_tamper_guard`
  benefits from section-scoped comparison the same way the non-FSM path does
  [Agent 3 finding].

_Confirmed no gap (checked, not added):_ `scripts/tests/test_work_verification.py`
and `scripts/tests/test_worker_pool.py` were traced for any assertion on
`resolved_pytest_config_paths`'s return shape, `tamper_guard_candidate_paths`
output, or `TamperFinding.is_config` — both only exercise black-box
policy/pass-fail behavior on test files, never config files, so the
`ConfigTarget`-based return-shape change (kept as a `list[str]` compat
wrapper per Program Design) needs no edits there [Agent 2/3 finding].

_Confirmed no gap (checked, not added):_ no `docs/*.md`, `commands/*.md`, or
`skills/*/SKILL.md` file documents `resolved_pytest_config_paths`'s return
shape or `pyproject.toml` config-comparison scope in a way this change
invalidates, and `config-schema.json`'s `tamper_guard.policy` entry is
unaffected (no new config key) [Agent 2 finding].

### Configuration
- N/A — no new config key; `tamper_guard.policy` semantics unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Breaking-change surface of the `list[ConfigTarget]` return shape**:
  every downstream consumer of `resolved_pytest_config_paths` currently
  assumes plain `list[str]` path union-compatible with other string sets —
  `tamper_guard_candidate_paths`'s `set(filter_test_files(...)) |
  set(config_paths)` (`:127-129`), `run_tamper_guard`'s
  `set(before) | set(filter_test_files(...)) | set(config_paths)` and
  `finding.path in config_path_set` (`:412-419`), and both
  `snapshot_test_paths(paths: list[str], ...)` /
  `snapshot_test_paths_at_ref(..., paths: list[str])` iterating `path` as a
  dict key and `repo_root / path`. The Program Design section's plan to keep
  `resolved_pytest_config_paths` as a thin compatibility wrapper (returning
  `[t.path for t in targets]`) is confirmed as the right shape to avoid
  touching these four call sites' string-set semantics; only the *hashing*
  step (`snapshot_test_paths`/`snapshot_test_paths_at_ref`) needs to switch
  from `_sha256_file`/`_sha256_bytes` to `hash_config_target` for paths that
  have a non-`None` selector.
- Two more open issues touch this same file/function family and should be
  sequenced against this one: `BUG-2959` (worker pool drops baseline SHA
  from tamper guard call) and `BUG-2962` (tamper-guard fail policy inert on
  convergent routing) — both in `.issues/bugs/`, not yet linked via
  `relates_to`.

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
5. Add the FSM-adapter test case to `TestTamperGuardExecutorHook`
   (`scripts/tests/test_fsm_executor.py`) so `fsm/executor.py`'s
   `_check_tamper_guard` path gets the same `pyproject.toml` coverage as the
   non-FSM path (added by `/ll:wire-issue`).
6. Run the full suite; confirm no regression in ENH-2933/2934/2935 coverage
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The anchors above have shifted on-disk because BUG-2954's fix (uncommitted,
  same file) inserted ~110 new lines ahead of them. Current line numbers:
  `resolved_pytest_config_paths` at `test_tamper_guard.py:297-321`,
  `tamper_guard_candidate_paths` at `:109-129`, `compare_snapshots` at
  `:150-169`, `run_tamper_guard` at `:386-422`. Re-check before starting
  implementation in case BUG-2954 lands first and shifts them again.
- Confirmed the fix cannot ride on BUG-2954's `finding_filter` mechanism:
  in `run_tamper_guard` (`:386-422`), `finding_filter` runs *after* the
  `is_config` tagging loop (`:417-419`), and the concrete filter passed by
  `work_verification._run_non_fsm_tamper_guard`
  (`filter_weakening_findings`, `:253-280`) unconditionally keeps every
  `is_config` finding (`if finding.is_config or finding.kind == "deleted":
  kept.append(finding)`) without inspecting its content. It never had a
  chance to rescue a spurious `pyproject.toml` finding. This validates the
  Proposed Solution's direction: the fix must narrow what produces a
  config-file finding in `compare_snapshots`/`resolved_pytest_config_paths`/
  `snapshot_test_paths` itself, not in a `finding_filter`.
- Independently confirms the FSM adapter angle already noted under
  Integration Map: `fsm.executor._check_tamper_guard` calls
  `run_tamper_guard` with no `finding_filter` argument at all, so a
  `finding_filter`-only fix would leave that adapter's `pyproject.toml`
  false positive completely unaddressed.

## Resolution

Implemented per the Program Design: added `ConfigTarget` (`path`, `section`)
and `resolved_pytest_config_targets(repo_root) -> list[ConfigTarget]` in
`scripts/little_loops/test_tamper_guard.py`, with `resolved_pytest_config_paths`
kept as a thin compatibility wrapper. Added `hash_config_target(source,
target)`, which hashes the canonicalized `[tool.pytest.ini_options]` table
(`json.dumps(..., sort_keys=True, default=str)` then sha256, matching the
repo's existing deterministic-hashing idiom) when `section` is set, and falls
back to whole-source hashing when `section` is `None` or the TOML is
unparseable (fail-closed). `snapshot_test_paths` and `snapshot_test_paths_at_ref`
now resolve section-scoped config targets internally and hash them via
`hash_config_target` instead of whole-file sha256, while every other path
(including single-purpose `pytest.ini`/`tox.ini`/`setup.cfg`) is unaffected.

Verified against the issue's own reproduction: a bare `pyproject.toml` version
bump with `[tool.pytest.ini_options]` present now produces zero findings and
`passed: True`, while an edit inside `[tool.pytest.ini_options]` (e.g. adding
`addopts`) still produces a finding and fails the guard. Added test coverage
in `scripts/tests/test_test_tamper_guard.py` (`TestResolvedPytestConfigTargets`,
`TestHashConfigTarget`, and new `TestRunTamperGuard` end-to-end cases for
version-bump/section-edit/pytest.ini-unchanged/unparseable-TOML-fallback) and
a matching FSM-adapter case in
`scripts/tests/test_fsm_executor.py::TestTamperGuardExecutorHook` per Step 5.
Full suite passes (17495 passed, 42 skipped; the one pre-existing
`test_prose_dep_sweep_gate.py` failure is unrelated — reproduces identically
on a clean stash, tracked separately).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` - 2026-08-01T05:55:00 - `a82b7e57-b74c-443b-a6e0-9664da5c0d57.jsonl`
- `/ll:ready-issue` - 2026-08-01T05:42:48 - `1005a6ba-30e9-4585-9611-59070df89764.jsonl`
- `/ll:confidence-check` - 2026-08-01T05:40:57 - `13ba386f-07e2-456c-8607-bff9b358abb7.jsonl`
- `/ll:wire-issue` - 2026-08-01T05:39:09 - `04e69208-2d93-4eeb-840f-ab990bf2bf20.jsonl`
- `/ll:refine-issue` - 2026-08-01T05:31:30 - `8fd33d39-a3ca-4768-a4cf-93afa8f7a799.jsonl`
- `/ll:capture-issue` - 2026-08-01T01:25:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e6bb49e-330c-449c-8327-ffed663d51ae.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
