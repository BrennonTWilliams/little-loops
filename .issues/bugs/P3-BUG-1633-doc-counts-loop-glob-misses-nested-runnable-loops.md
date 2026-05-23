---
id: BUG-1633
title: doc_counts loop glob misses nested runnable loops (oracles/)
type: bug
priority: P3
status: done
completed_at: 2026-05-23T17:20:53Z
labels:
- docs
- verification
- loops
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# doc_counts loop glob misses nested runnable loops

## Summary

`doc_counts.count_files()` enumerates loop YAMLs with a non-recursive `*.yaml` glob, so nested runnable loops (e.g. `loops/oracles/oracle-capture-issue.yaml`) are silently excluded from `ll-verify-docs` counts.

## Current Behavior

`scripts/little_loops/doc_counts.py:28` defines:

```python
COUNT_TARGETS = {
    ...
    "loops": ("scripts/little_loops/loops", "*.yaml"),
}
```

The glob pattern `*.yaml` is non-recursive, so `count_files()` only sees top-level YAML files (51). Runnable nested loops are ignored — currently `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml`, which `ll-loop validate oracles/oracle-capture-issue` confirms is a valid 4-state FSM.

Result: `ll-verify-docs` reports "All counts match" even when README.md says `51 FSM loops` while the runnable count is `52`. This silently degrades the verifier from a guard into a rubber stamp.

## Expected Behavior

`count_files()` (or its caller) enumerates loop YAMLs recursively and filters to runnable FSM definitions only:

- `loops/oracles/oracle-capture-issue.yaml` is counted (runnable FSM)
- `loops/lib/*.yaml` is excluded (library fragments missing required FSM fields)
- Reported count = 52 today, and tracks future additions of nested runnable loops automatically

## Motivation

The whole point of `ll-verify-docs` is to catch documentation drift. A verifier that under-counts the artifacts it's supposed to verify can pass while the docs are wrong — exactly what happened in the audit that surfaced this (README.md:167 said 51, runnable count was 52, verifier said "All counts match"). Fixing the enumeration restores the verifier's role as a guard.

## Steps to Reproduce

```bash
$ ll-loop validate oracles/oracle-capture-issue
oracles/oracle-capture-issue is valid
  States: check_mechanical, route_phase1, score_semantic, done

$ python3 -c "from scripts.little_loops.doc_counts import count_files; \
  print(count_files('scripts/little_loops/loops', '*.yaml'))"
51

$ find scripts/little_loops/loops -name '*.yaml' | wc -l
57
```

The 6-file gap is 5 library fragments under `lib/` (genuinely not runnable — they're missing required FSM fields) plus 1 runnable oracle that should be counted.

## Root Cause

- **File**: `scripts/little_loops/doc_counts.py`
- **Anchor**: `COUNT_TARGETS` constant + `count_files()` helper
- **Cause**: The `*.yaml` glob is non-recursive (uses `Path.glob` with a single-segment pattern), so subdirectories under `loops/` are never traversed. There is also no filter distinguishing runnable FSM YAMLs from library fragments under `lib/`.

## Proposed Solution

Change the loops enumeration to walk recursively and filter to runnable FSM definitions. Two viable approaches:

1. **Directory-based filter** (simpler): use `Path.rglob("*.yaml")` and exclude any path whose parts contain `lib`. Cheap, but couples the verifier to the current `lib/` convention.
2. **Content-based filter** (more robust): use `Path.rglob("*.yaml")` and keep YAMLs whose parsed top-level keys include `name` + `initial` + (`states` or `flow`). This matches `ll-loop validate`'s own notion of "runnable" and survives directory renames.

Recommended: approach 2, with a small helper (e.g. `is_runnable_loop(path) -> bool`) so the same predicate can be reused by `ll-loop list` when [[BUG-1634]] is fixed.

Sketch:

```python
def is_runnable_loop(path: Path) -> bool:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return False
    if not isinstance(data, dict):
        return False
    has_flow = "states" in data or "flow" in data
    return "name" in data and "initial" in data and has_flow

def count_loops(base: Path) -> int:
    return sum(1 for p in base.rglob("*.yaml") if is_runnable_loop(p))
```

`count_files()` either gains a special case for the `loops` target or `COUNT_TARGETS` is extended to allow a callable predicate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **An equivalent required-fields check already exists** in `scripts/little_loops/fsm/validation.py` in `load_and_validate()` (lines 880–894). It checks for `name`, `initial`, and `states` (after `resolve_flow()` from `scripts/little_loops/fsm/fragments.py` has expanded a `flow:` shorthand into `states:`). The new predicate should match this exact contract so "counted by the verifier" == "runnable by `ll-loop validate`".
- **Lightweight YAML reader pattern**: `_load_loop_meta()` in `scripts/little_loops/cli/loop/info.py` (lines 30–49) shows the established style — `yaml.safe_load`, `except Exception` returning a safe default, no schema parsing. The new predicate should follow this shape (fast, no inheritance/fragment resolution).
- **Canonical key set**: `KNOWN_TOP_LEVEL_KEYS` in `scripts/little_loops/fsm/validation.py` (lines 78–107) is the authoritative set of recognized loop YAML keys and explicitly lists `flow` as the alternative to `states`. The predicate's `"states" in data or "flow" in data` clause matches this.
- **`COUNT_TARGETS` shape is uniform `dict[str, tuple[str, str]]`** with no callable slot. Extending it to support a predicate requires either (a) a special-case branch in `verify_documentation()` for `"loops"`, or (b) widening the tuple to `(directory, pattern, predicate | None)` and updating all four entries. Option (a) mirrors the existing skill-budget post-adjustment (`verify_documentation()` lines 139–143), which is also hardcoded for the `"skills"` target.
- **CLI layer is unaffected**: `main_verify_docs()` in `scripts/little_loops/cli/docs.py` (line 12) only calls `verify_documentation(base_dir)` and consumes the `VerificationResult` dataclass. No CLI signature or argparse change is needed.
- **`loops` is the only target with this problem**: `agents/`, `commands/`, and `skills/` have no nested-subdirectory YAMLs/MDs that the current globs miss. The fix can be `loops`-scoped without genericizing all four targets.

## Integration Map

### Files to Modify
- `scripts/little_loops/doc_counts.py` — recursion (`rglob`) + `is_runnable_loop` predicate in `count_files()` / `verify_documentation()` (`COUNT_TARGETS` at line 28, `count_files()` at line 70, `verify_documentation()` at line 118)
- `scripts/little_loops/fsm/validation.py` — add `is_runnable_loop(path: Path) -> bool` predicate alongside `load_and_validate()` so BUG-1634 (`cli/loop/info.py:cmd_list`) can import the same predicate without circular dependencies [wiring pass]
- `scripts/little_loops/fsm/__init__.py` — add `is_runnable_loop` to the re-export block and `__all__` so BUG-1634 can import via `from little_loops.fsm import is_runnable_loop` (same pattern as `load_and_validate` export) [wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/docs.py` — `main_verify_docs()` at line 12, the `ll-verify-docs` entrypoint; calls `verify_documentation(base_dir)` and consumes the `VerificationResult` dataclass. **No CLI change needed** — the recursion fix is fully contained inside `doc_counts.py`.
- Confirmed via grep: no other callers of `count_files` / `COUNT_TARGETS` / `verify_documentation` exist outside `doc_counts.py` and `cli/docs.py`.

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py` in `cmd_list()` (lines 119–129) — same `*.yaml` non-recursive glob; tracked as [[BUG-1634]]. Both bugs should share the same `is_runnable_loop` predicate — put it in a module both can import (suggestion: `scripts/little_loops/fsm/validation.py` alongside `load_and_validate`, or a new `scripts/little_loops/loops_discovery.py` module).
- `scripts/little_loops/cli/loop/config_cmds.py` in `cmd_install()` (line 49) — also uses non-recursive glob; out of scope for this fix but worth noting for future cleanup.
- `scripts/tests/test_builtin_loops.py` `TestBuiltinLoopFiles` (line 22) — fixture also uses `BUILTIN_LOOPS_DIR.glob("*.yaml")`; out of scope, but means nested runnable loops are not currently exercised by builtin-loop validation tests either.
- Existing reusable model: `load_and_validate()` in `scripts/little_loops/fsm/validation.py` (lines 853–933) — the canonical "is this a valid loop?" function; predicate should match its required-fields gate.

### Tests
- `scripts/tests/test_doc_counts.py` `TestCountFiles.test_count_loops_top_level_only()` (line 45) — **must be updated**: this test currently asserts the buggy behavior (subdirectory files are excluded). After the fix, recursive enumeration should count nested *runnable* loops while still excluding `lib/`-style fragments. Rename to `test_count_loops_recursive_excludes_fragments` (or similar) and adjust expectations.
- `scripts/tests/test_doc_counts.py` `TestVerifyDocumentation.test_verify_detects_loops_mismatch()` (line 494) — **will break without fixture content updates**: its inline YAMLs use `write_text(f"name: loop{i}")` — only the `name` key, no `initial` or `states`/`flow`. After the fix, `is_runnable_loop()` returns `False` for all three, making `actual == 0` instead of `3`. Must update fixture YAML content to include `initial` + `states` fields before asserting `actual == 3`. [wiring pass — critical]
- `scripts/tests/test_doc_counts.py` `TestCountFiles.test_count_loops_top_level_only()` (line 45) — same issue: inline YAMLs lack `initial`/`states`; update fixture content when renaming/rewriting this test. [wiring pass]
- `scripts/tests/test_builtin_loops.py` `TestBuiltinLoopFiles.builtin_loops` fixture (line 25) — uses `BUILTIN_LOOPS_DIR.glob("*.yaml")` (top-level only); if `oracles/oracle-capture-issue.yaml` should be validated as a built-in loop, update to `rglob` + `is_runnable_loop` filter. Out of scope for this fix but noted. [wiring pass]
- `scripts/tests/test_builtin_loops.py` `TestBuiltinLoopFiles.test_expected_loops_exist()` (line 120) — uses top-level `*.yaml` glob against a hardcoded 51-name set; does not include `oracle-capture-issue`. Decide whether oracle loops belong in the expected set. Out of scope for this fix. [wiring pass]
- `scripts/tests/test_cli_docs.py` `TestMainVerifyDocs` — mocks `verify_documentation` via `patch("little_loops.doc_counts.verify_documentation", ...)`; fully isolated from the fix. No changes needed.
- `scripts/tests/fixtures/fsm/` — **existing fixtures are reusable** (flat directory, no nested subdir exists):
  - `valid-loop.yaml` — model for the "nested runnable loop" fixture (has `name` + `initial` + `states`)
  - `incomplete-loop.yaml`, `missing-name.yaml`, `missing-states.yaml` — model for the "library fragment is excluded" fixture
  - Fixture path accessed via the `fsm_fixtures` pytest fixture in `scripts/tests/conftest.py` (`Path(__file__).parent / "fixtures" / "fsm"`)
  - A new `oracles/` subdir under `fixtures/fsm/` would be needed for a fixture-based nested integration test; alternatively, build `loops/oracles/` entirely in `tmp_path` inline (existing pattern in `TestCountFiles`)
- New tests to add:
  - Unit test `TestIsRunnableLoop` for `is_runnable_loop(path)` — covers valid `states:` form, `flow:`-only shorthand, missing `name`, missing `initial`, missing both `states` and `flow`, malformed YAML (`yaml.YAMLError`), non-dict root; reuse `fsm_fixtures` for fixture paths
  - Integration test in `TestCountFiles`: place a runnable YAML (with `name`/`initial`/`states`) under `loops/oracles/` in `tmp_path` and a fragment YAML (missing `states`) under `loops/lib/`; assert recursive count includes only the runnable one

### Documentation
- `README.md:167` already manually corrected to 52; no further doc change needed once the verifier counts correctly
- `docs/reference/API.md` section `## little_loops.fsm` — add a function entry for `is_runnable_loop(path: Path) -> bool` if it is to be part of the public FSM API (exported via `fsm/__init__.py`). If kept internal to `validation.py` only, no doc change needed. [wiring pass]

### Configuration
- N/A

## Implementation Steps

1. Add `is_runnable_loop(path: Path) -> bool` predicate in `scripts/little_loops/fsm/validation.py` (alongside `load_and_validate()`) so [[BUG-1634]] (`cli/loop/info.py:cmd_list()` line 120) can import the same predicate without circular dependencies. Follow the lightweight reader style of `_load_loop_meta()` (`cli/loop/info.py:30–49`): `yaml.safe_load` + raw key access + broad `except` returning `False`. The required-key check should mirror `load_and_validate()` lines 880–894: `"name" in data and "initial" in data and ("states" in data or "flow" in data)`. Then re-export `is_runnable_loop` from `scripts/little_loops/fsm/__init__.py` (add to the existing import block and `__all__` alongside `load_and_validate`) so BUG-1634 can import via `from little_loops.fsm import is_runnable_loop`.
2. In `scripts/little_loops/doc_counts.py`, update the `loops` enumeration in `count_files()` (line 70) to use `rglob("*.yaml")` and apply `is_runnable_loop`. Either special-case `"loops"` inside `verify_documentation()` (line 118) — mirroring the existing skill-budget post-adjustment at lines 139–143 — or widen the `COUNT_TARGETS` tuple to allow an optional predicate callable. Recommend the special-case approach: minimal, contained, matches existing precedent.
3. Update tests in `scripts/tests/test_doc_counts.py`:
   - `TestCountFiles.test_count_loops_top_level_only` (line 45): rename and rewrite to assert (a) nested runnable fixtures under `oracles/` are counted, (b) `lib/`-style fragments without `initial:` are excluded. **Also update inline fixture YAML content** — change `write_text("name: loopN")` stubs to include `initial:` and `states:` for runnable cases so `is_runnable_loop()` returns True.
   - `TestVerifyDocumentation.test_verify_detects_loops_mismatch` (line 494): **update the three `write_text(f"name: loop{i}")` fixture YAMLs** to include `initial: start` and `states: {start: {action: ..., transitions: [...]}}`-style content, otherwise `is_runnable_loop()` returns False and `actual` drops to 0, breaking this test.
4. Add a unit test class `TestIsRunnableLoop` covering: valid `states:` form, `flow:`-only shorthand, missing `name`, missing `initial`, missing both `states` and `flow`, malformed YAML (catch `yaml.YAMLError`), non-dict root. Reuse fixtures in `scripts/tests/fixtures/fsm/` (`valid-loop.yaml`, `missing-name.yaml`, `missing-states.yaml`, `incomplete-loop.yaml`) via the `fsm_fixtures` fixture in `scripts/tests/conftest.py`.
5. Run `python -m pytest scripts/tests/test_doc_counts.py -v` and confirm green.
6. Run `ll-verify-docs` from the repo root and confirm it reports `loops: 52` and exits 0; flip `README.md:167` to a wrong number temporarily and confirm it now exits non-zero (regression guard).

## Acceptance Criteria

- [ ] `count_files()` (or its caller in `verify_documentation()`) enumerates loops recursively
- [ ] Library fragments under `lib/` are excluded — either by directory allowlist/denylist, or by filtering to YAMLs whose top-level keys include `name` + `initial` + (`states` or `flow`)
- [ ] `oracles/oracle-capture-issue.yaml` is counted; `lib/*.yaml` are not
- [ ] Total reported count = 52 (today) and tracks future additions of nested runnable loops
- [ ] Existing tests in `scripts/tests/` still pass; new test covers a nested-runnable-loop fixture and a library-fragment fixture

## Impact

- **Priority**: P3 — verifier silently passes on stale counts; correctness regression but no user-visible runtime failure
- **Effort**: Small — single-file change in `doc_counts.py` plus a focused test; predicate is ~10 lines
- **Risk**: Low — additive recursion + filter; existing top-level YAMLs are still counted; well-covered by tests
- **Breaking Change**: No

## Notes

Found during `/ll:audit-docs` (2026-05-23). Manually fixed README.md:167 (51 → 52); this issue prevents the regression from reappearing.

Related: `ll-loop list` also omits nested runnable loops — same root cause but in CLI enumeration, not doc verification. See [[BUG-1634]] (sibling issue).

## Status

**Done** | Created: 2026-05-23 | Completed: 2026-05-23 | Priority: P3

## Resolution

- Added `is_runnable_loop(path: Path) -> bool` in `scripts/little_loops/fsm/validation.py` (mirrors the required-fields gate in `load_and_validate()` lines 885-894; uses the lightweight `yaml.safe_load` + broad-except pattern from `_load_loop_meta()`).
- Re-exported the predicate from `scripts/little_loops/fsm/__init__.py` so BUG-1634 can reuse it without a circular import.
- In `scripts/little_loops/doc_counts.py:verify_documentation()`, added a `loops`-targeted post-adjustment that walks `loops/` recursively via `rglob("*.yaml")` and filters with `is_runnable_loop`. Mirrors the existing skill-budget post-adjustment pattern (lines 139-143) rather than widening `COUNT_TARGETS` tuples — minimal blast radius.
- Updated `test_verify_detects_loops_mismatch` fixture YAMLs to include `initial:` + `states:` so they now satisfy the predicate.
- Renamed `test_count_loops_top_level_only` → `test_count_loops_top_level_glob_non_recursive` to reflect that `count_files()` itself stays a thin non-recursive glob (recursion lives in `verify_documentation()`).
- Added `TestIsRunnableLoop` covering: valid `states:`, `flow:` shorthand, missing `name`/`initial`/both states+flow, non-dict root, malformed YAML, plus integration checks against the real `oracles/oracle-capture-issue.yaml` (runnable) and all `lib/*.yaml` fragments (excluded).
- Added `test_verify_loops_recursive_excludes_fragments` integration test that builds a fixture tree mirroring the real `loops/{,oracles/,lib/}` layout and asserts the runnable count.

**Verification:** `ll-verify-docs` now reports `loops: actual=52` matching README:167; flipping README to `51` produces exit 1 with a `loops: documented=51, actual=52` mismatch (regression guard confirmed). All 508 tests in `scripts/tests/` pass; ruff + mypy clean on changed files.

## Session Log
- `/ll:manage-issue` - 2026-05-23T17:20:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c2d509-42c3-47ff-8eaa-f3b238996a01.jsonl`
- `/ll:ready-issue` - 2026-05-23T17:16:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f14bdb2-9ee0-4a6d-94c4-9d1f93093c71.jsonl`
- `/ll:wire-issue` - 2026-05-23T17:13:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e9ce930-75a4-416e-a121-42fb8b2885f0.jsonl`
- `/ll:refine-issue` - 2026-05-23T17:08:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02f5daa7-b3fb-42d7-bc05-1792527d5a72.jsonl`
- `/ll:format-issue` - 2026-05-23T16:52:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78e7000c-0614-4462-a57a-9dc90750d092.jsonl`
