---
id: BUG-1634
title: ll-loop list omits nested runnable loops (oracles/)
type: bug
priority: P3
status: done
completed_at: 2026-05-23T17:48:25Z
labels:
- cli
- loops
- discoverability
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ll-loop list omits nested runnable loops

## Summary

`ll-loop list` enumerates only top-level YAMLs under `scripts/little_loops/loops/`, so runnable loops nested in subdirectories (e.g. `oracles/oracle-capture-issue.yaml`) are invisible from the listing even though `ll-loop validate` and `ll-loop run` accept them. Any loop added under `oracles/` or a future subdirectory is dark until users read the filesystem directly.

## Current Behavior

`ll-loop list` walks only the top level of `scripts/little_loops/loops/`. Nested runnable loops are validatable and runnable but never appear:

```bash
$ ll-loop validate oracles/oracle-capture-issue
oracles/oracle-capture-issue is valid     # runnable

$ ll-loop list | grep -i oracle
# (no output)                              # not discoverable
```

## Expected Behavior

`ll-loop list` recursively enumerates runnable loops under nested subdirectories of `loops/`, while continuing to exclude library fragments under `loops/lib/` (those are not valid FSMs on their own). Nested loops are displayed with their relative path (e.g. `oracles/oracle-capture-issue`) so users can copy/paste the identifier directly into `ll-loop run`. Category grouping in the listing continues to work for nested loops, either by frontmatter `category` field or by subdirectory name.

## Steps to Reproduce

1. Confirm a nested loop exists and is runnable: `ll-loop validate oracles/oracle-capture-issue` → reports `is valid`.
2. Run `ll-loop list | grep -i oracle`.
3. Observe: no output — the nested loop is missing from the listing despite being runnable.

## Root Cause

- **File**: `scripts/little_loops/` (ll-loop CLI listing implementation)
- **Anchor**: loop-enumeration helper backing `ll-loop list`
- **Cause**: Listing is non-recursive — it scans only the top level of `loops/`. Same root cause shape as [[BUG-1633]] (non-recursive enumeration in doc verification), but located in the CLI rather than doc tooling.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Function**: `cmd_list()` in `scripts/little_loops/cli/loop/info.py` (lines 52–236).
- **Bug lines (project loops)**: lines 119–121 — `yaml_files = sorted(loops_dir.glob("*.yaml"))` + `project_names = {p.stem for p in yaml_files}`. Non-recursive single-segment glob.
- **Bug lines (built-in loops)**: lines 124–129 — `builtin_files = [f for f in sorted(builtin_dir.glob("*.yaml")) if f.stem not in project_names]`. Same non-recursive glob.
- **Display-name bug**: line 142 — `"name": path.stem` produces `oracle-capture-issue` for a file at `loops/oracles/oracle-capture-issue.yaml`, losing the `oracles/` prefix that `ll-loop run` requires.
- **Override-suppression bug**: `project_names = {p.stem for p in yaml_files}` keys on bare stem; with recursive enumeration, a project loop at `oracles/foo.yaml` and a built-in at `foo.yaml` would collide. The key needs to be the relative path stem (`str(path.relative_to(base).with_suffix(""))`).
- **Why `loops/lib/` is currently hidden**: not by explicit exclusion — only as a side-effect of the non-recursive glob. Once recursion is added, `lib/` fragments would appear unless filtered.
- **Contrast — `validate`/`run` already work**: `resolve_loop_path()` in `scripts/little_loops/cli/loop/_helpers.py:127–148` constructs the path as `loops_dir / f"{name_or_path}.yaml"`. Subdirectory notation works natively via `Path.__truediv__` — there's no glob, just path construction.
- **Sibling non-recursive glob (out of scope, noted)**: `cmd_install()` in `scripts/little_loops/cli/loop/config_cmds.py:49` also uses `builtin_dir.glob("*.yaml")` for its error-message available-list. Tracked separately.

## Proposed Solution

Make `ll-loop list` recursively walk `loops/` and include any YAML whose frontmatter parses as a valid FSM (matching what `ll-loop validate` accepts). Explicitly exclude `loops/lib/` (library fragments). Consider extracting the discovery logic into a shared "discover runnable loops" helper so [[BUG-1633]] can reuse it and the two bugs stay in sync. Display nested loops with their relative path (`oracles/oracle-capture-issue`) so the displayed identifier is the same string users pass to `ll-loop run`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Shared helper already exists** (from [[BUG-1633]], status `done`): `is_runnable_loop(path: Path) -> bool` in `scripts/little_loops/fsm/validation.py:853–872`. Cheap predicate: parses YAML, checks for `name` + `initial` + (`states` or `flow`). Library fragments under `loops/lib/` naturally return `False` because they lack `initial:` — no directory-name check needed.
- **Public import path**: `from little_loops.fsm import is_runnable_loop`. Re-exported via `scripts/little_loops/fsm/__init__.py:151` and listed in `__all__` at line 215. No circular-dependency risk for `cli/loop/info.py`.
- **Precedent in production code**: `doc_counts.py:verify_documentation()` (lines 140–148) already uses the `rglob` + `is_runnable_loop` pattern for the sibling BUG-1633 fix:
  ```python
  actual_counts["loops"] = sum(
      1 for p in loops_dir.rglob("*.yaml") if is_runnable_loop(p)
  )
  ```
  BUG-1634's `cmd_list()` fix should mirror this shape.
- **Display-name fix**: replace `"name": path.stem` with `str(path.relative_to(base_dir).with_suffix(""))` so nested loops render as `oracles/oracle-capture-issue` — the same string `resolve_loop_path()` accepts.
- **Override-suppression fix**: change `project_names = {p.stem for p in yaml_files}` to use the same relative-path key so identically-named loops in different subdirectories don't incorrectly suppress each other.
- **Category grouping**: `cmd_list()` buckets by frontmatter `category` field (lines 184–188), not by subdirectory. Nested loops without an explicit `category` will land in `"uncategorized"` — acceptable, since `oracles/oracle-capture-issue.yaml` already sets `category` in its frontmatter. No additional grouping logic required.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` lines 119–129: switch project-loop and built-in-loop enumeration from `glob("*.yaml")` to `rglob("*.yaml")` + `is_runnable_loop` filter. Change `"name": path.stem` (line 142) to relative-path key. Change `project_names` set (line 121) to use the same relative-path key.
- `scripts/little_loops/cli/loop/info.py` — top imports: add `from little_loops.fsm import is_runnable_loop`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/__init__.py:421` — dispatcher for `cmd_list`. No change required.
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdList` class (lines 164–200+). Existing tests cover only top-level loops; needs new fixtures for nested + lib/ to lock in the fix.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_integration.py:266` — `test_list_multiple_loops` uses bare-YAML fixtures (`"name: a"`) that `is_runnable_loop()` will reject; this test will break once the `is_runnable_loop` filter is applied.
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopList` exercises `cmd_list()` via `main_loop()`; `test_list_shows_builtin_tag` and `test_list_hides_overridden_builtin` remain valid after the fix (top-level loop keys are equal before and after relative-path keying), but should be verified during test run.

### Similar Patterns

- `scripts/little_loops/doc_counts.py:140–148` — `rglob("*.yaml")` + `is_runnable_loop` filter. Direct precedent; mirror this shape in `cmd_list()`.
- `scripts/little_loops/cli/loop/_helpers.py:127–148` — `resolve_loop_path()` shows the name-string contract: `oracles/oracle-capture-issue` resolves via `loops_dir / f"{name_or_path}.yaml"`. The listing's display name must match this exact string format.

### Tests

- `scripts/tests/test_ll_loop_commands.py` — `TestCmdList` needs:
  - A fixture with a nested `oracles/foo.yaml` (runnable) that asserts `foo` appears in listing as `oracles/foo`.
  - A fixture with a `lib/fragment.yaml` (missing `initial:`) that asserts the fragment does NOT appear in listing.
  - A fixture where project and built-in have a same-name loop at different relative paths, asserting override-suppression keys on the relative path, not the stem.
- `scripts/tests/test_doc_counts.py:599–634` — `test_verify_loops_recursive_excludes_fragments` is the regression model to copy. Inline `tmp_path` fixture tree with top-level + `oracles/` + `lib/` is the established pattern.
- Minimal runnable YAML fixture content: `"name: X\ninitial: start\nstates:\n  start:\n    terminal: true\n"`.
- Minimal fragment YAML fixture content: `"name: X\n"`.

_Wiring pass added by `/ll:wire-issue`:_
- **EXISTING TESTS WILL BREAK** — All fixture YAMLs in `TestCmdList`, `TestLoopListCategoryFilter` (lines 379–522), and `TestLoopListFormatting` (lines 525–815) write bare YAML (`"name: x\n"`) with no `initial:` or `states:`. After the fix applies `is_runnable_loop()` as a listing filter, all these loops will be excluded from `cmd_list()` output, causing assertion failures. These fixtures must be updated to valid runnable FSM content (`"name: X\ninitial: start\nstates:\n  start:\n    terminal: true\n"`) before adding the new nested-loop tests.
- `scripts/tests/test_ll_loop_integration.py:266` — `test_list_multiple_loops` has the same bare-YAML issue. Update fixture content (add `initial:` + `states:`) and add assertions for relative-path display names. [exists — update]
- `scripts/tests/test_builtin_loops.py:208,225` — `test_list_shows_builtin_tag` and `test_list_hides_overridden_builtin` are safe after fix: top-level loops' relative-path key equals their stem, so override suppression still matches. Verify these pass without modification. [verify only]

### Configuration

- No config changes needed. `loops_dir` resolution via `Path(config.loops.loops_dir)` and `get_builtin_loops_dir()` are unchanged.

### Documentation

- No documentation changes required for this fix; the `ll-loop list` output is additive. (BUG-1633's doc-count drift will already be addressed by its own fix.)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` (~line 2948, section "Discovery: `lib/` is Hidden") — currently explains that `lib/` is excluded as a side-effect of the non-recursive `glob("*.yaml")`. After the fix, exclusion is deliberate via `is_runnable_loop()`. The causal explanation becomes stale and misleading; update to say exclusion is predicate-based. [update — stale causal explanation]
- `docs/reference/CLI.md` (~line 426, section "`ll-loop list` / `ll-loop l`") — the `--json` output table lists `name` as a field but does not specify its format. After the fix, nested loops have `name` values like `oracles/oracle-capture-issue` (relative path, not bare stem). Document the format change so downstream parsers (skills, scripts) can adapt. [update — `--json` name field format]

## Implementation Steps

1. **Add import** in `scripts/little_loops/cli/loop/info.py`: `from little_loops.fsm import is_runnable_loop`.
2. **Rewrite project-loop enumeration** at `info.py:119–121`: replace `loops_dir.glob("*.yaml")` with `[p for p in loops_dir.rglob("*.yaml") if is_runnable_loop(p)]`. Compute `project_names` as `{str(p.relative_to(loops_dir).with_suffix("")) for p in yaml_files}`.
3. **Rewrite built-in-loop enumeration** at `info.py:124–129`: replace `builtin_dir.glob("*.yaml")` with `builtin_dir.rglob("*.yaml")` + `is_runnable_loop` filter; suppress built-ins whose relative path stem is already in `project_names`.
4. **Fix display name** at `info.py:142` and the equivalent built-in branch: replace `"name": path.stem` with `"name": str(path.relative_to(base_dir).with_suffix(""))` where `base_dir` is the appropriate `loops_dir` or `builtin_dir`.
5. **Verify category grouping** still works for nested loops with a `category` frontmatter field (it should — `_load_loop_meta()` reads frontmatter regardless of path depth). No change expected.
6. **Add tests** in `scripts/tests/test_ll_loop_commands.py:TestCmdList`:
   - `test_nested_loop_appears_with_relative_path` — assert `oracles/foo` in listing output.
   - `test_lib_fragment_excluded` — assert `lib/fragment` does NOT appear.
   - `test_project_override_keys_on_relative_path` — assert same-stem, different-path loops do not collide.
7. **Run tests**: `python -m pytest scripts/tests/test_ll_loop_commands.py scripts/tests/test_doc_counts.py -v`.
8. **Smoke test**: `ll-loop list | grep oracle` should now show `oracles/oracle-capture-issue`. `ll-loop run "$(ll-loop list | grep oracle | awk '{print $1}')"` should resolve correctly.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Update all existing bare-YAML fixtures** in `scripts/tests/test_ll_loop_commands.py` (`TestCmdList`, `TestLoopListCategoryFilter`, `TestLoopListFormatting`) — replace `"name: x\n"` fixture content with valid runnable FSM content (`"name: X\ninitial: start\nstates:\n  start:\n    terminal: true\n"`). This is a precondition for the new nested-loop tests; without it, all existing listing tests break when `is_runnable_loop()` is applied.
10. **Update `test_list_multiple_loops`** in `scripts/tests/test_ll_loop_integration.py:266` — update fixture YAML to valid runnable FSM content; optionally add assertion for relative-path display name.
11. **Verify `test_builtin_loops.py`** — run `python -m pytest scripts/tests/test_builtin_loops.py -v -k "TestBuiltinLoopList"` to confirm `test_list_shows_builtin_tag` and `test_list_hides_overridden_builtin` pass without modification.
12. **Update `docs/guides/LOOPS_GUIDE.md`** (~line 2948, "Discovery: `lib/` is Hidden") — rewrite the causal explanation to say lib/ exclusion is predicate-based (`is_runnable_loop()`) rather than a side-effect of a non-recursive glob.
13. **Update `docs/reference/CLI.md`** (~line 426, "`ll-loop list` / `ll-loop l`") — document that the `--json` `name` field for nested loops is a relative path (`oracles/oracle-capture-issue`), not a bare stem.

## Acceptance Criteria

- [ ] `ll-loop list` includes runnable loops under nested subdirectories of `loops/`
- [ ] Library fragments under `loops/lib/` remain excluded (they're not valid FSMs)
- [ ] Nested loops display with their relative path (`oracles/oracle-capture-issue`) so users can copy/paste into `ll-loop run`
- [ ] Category grouping in the listing still works for nested loops (assign by frontmatter category or by subdirectory)
- [ ] Test coverage: a nested-runnable-loop fixture appears in `ll-loop list` output; a library-fragment fixture does not

## Impact

- **Priority**: P3 — Discoverability gap; users can still run nested loops if they know the path, but the listing CLI silently hides them.
- **Effort**: Small — Localized change in the loop-enumeration helper plus a couple of fixture-based tests.
- **Risk**: Low — Pure read-side change; no effect on `ll-loop run` semantics, and `loops/lib/` exclusion preserves the existing "fragments aren't FSMs" contract.
- **Breaking Change**: No — Output is additive (more rows listed). Identifiers stay copy-pasteable into `ll-loop run`.

## Notes

Found during `/ll:audit-docs` (2026-05-23). Shares a root cause with [[BUG-1633]] (non-recursive enumeration), but lives in CLI listing rather than doc verification. Fix the two together if convenient — they may share a "discover runnable loops" helper.

## Labels

`cli`, `loops`, `discoverability`

---

**Open** | Created: 2026-05-23 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-05-23T17:48:25 - `001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
- `/ll:wire-issue` - 2026-05-23T17:31:06 - `11747bce-3ff7-459a-9a11-9fe37cce5bed.jsonl`
- `/ll:refine-issue` - 2026-05-23T17:25:55 - `7788c8e9-e2d4-4246-9d3a-02ad822b537a.jsonl`
- `/ll:format-issue` - 2026-05-23T16:52:06 - `c0c0653a-6b0f-4270-aa05-e54a6f8925dd.jsonl`
- `/ll:confidence-check` - 2026-05-23T18:00:00 - `184bfdae-1f41-4d76-88a3-4daa06dddea2.jsonl`
