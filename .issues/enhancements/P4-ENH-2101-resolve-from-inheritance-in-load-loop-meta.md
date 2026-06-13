---
id: ENH-2101
title: Resolve one level of from: inheritance in _load_loop_meta so inherited metadata shows in ll-loop list
type: ENH
priority: P4
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
parent: EPIC-1811
decision_needed: false
---

# ENH-2101: Resolve `from:` inheritance in `_load_loop_meta`

## Summary

`_load_loop_meta` (`scripts/little_loops/cli/loop/info.py:31-50`) reads raw YAML and never resolves `from: lib/apo-base` inheritance, so metadata defined only in the parent template (e.g. `category:`) is invisible to `ll-loop list` and README tooling. The 2026-06-12 audit worked around this by adding explicit `category:` to `apo-beam`, `apo-textgrad`, and `rn-plan-apo`, but the root cause remains: any future loop relying on inherited metadata will silently show as uncategorized.

## Motivation

This enhancement would:
- **Eliminate silent metadata gaps**: Any future loop relying on inherited metadata currently shows as uncategorized in `ll-loop list` with no error or warning, making the gap invisible until audited manually.
- **Remove duplication burden**: Developers must explicitly repeat parent metadata (e.g., `category:`) in every child loop, creating maintenance debt that compounds with each new loop.
- **Align `_load_loop_meta` with executor behavior**: The FSM executor already resolves `from:` inheritance; the metadata loader should match that behavior to avoid a divergence that surprises users.

## Expected Behavior

`_load_loop_meta` follows one level of `from:` (matching the executor's resolution path for lib templates) and merges parent metadata under child overrides, so `ll-loop list` shows inherited `category`/`labels` without requiring duplication in every child.

## Success Metrics

- `ll-loop list` shows correct `category` for a child loop with `from: lib/apo-base` and no explicit `category:` field
- Zero future child loops require explicit metadata duplication for fields already declared in the parent template

## Scope Boundaries

- **In scope**: One level of `from:` resolution for metadata keys (`category`, `labels`) within `_load_loop_meta`
- **Out of scope**: Chained `from:` resolution (corpus has no chains); full FSM build-time resolution path

## Implementation Steps

1. In `scripts/little_loops/cli/loop/info.py:_load_loop_meta()`, add a call to `resolve_inheritance(spec, path.parent)` immediately after `spec = yaml.safe_load(f) or {}` — mirroring the call at `validation.py:1990`. Import `resolve_inheritance` from `little_loops.fsm.fragments` at the top of `info.py` (already-imported sibling `fragments` module; no circular import issue since `info.py` is in `cli/loop/`).
2. Wrap the `resolve_inheritance` call in a bare `except Exception: pass` guard consistent with the existing exception-swallowing pattern in `_load_loop_meta` (line 49) — a parent-load failure should fall back to the raw dict, not crash the listing.
3. Verify with `ll-loop list` that a child loop with `from: lib/apo-base` and no explicit `category:` shows the parent's category in the output.
4. Add a unit test to `TestLoopListFormatting` in `scripts/tests/test_ll_loop_commands.py` following the pattern at line 826: write a parent YAML and child YAML to `tmp_path`, call `_load_loop_meta(child_path)`, assert `meta["category"]` equals the parent's value. The `resolve_loop_path` call inside `resolve_inheritance` searches `loop_dir` (i.e., `tmp_path`) first, so placing both files there is sufficient.
5. Run `python -m pytest scripts/tests/test_ll_loop_commands.py -v` to confirm.
6. Optionally remove now-redundant explicit `category:` lines from `apo-beam.yaml`, `apo-textgrad.yaml`, and `rn-plan-apo.yaml` — explicit beats implicit, but these are safe to clean up once the loader resolves inheritance.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` (lines 31-50, `_load_loop_meta`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:151` — `cmd_list()` calls `_load_loop_meta(path)` for each project loop
- `scripts/little_loops/cli/loop/info.py:156` — `cmd_list()` calls `_load_loop_meta(path)` for each builtin loop

### Similar Patterns
- `scripts/little_loops/fsm/fragments.py:154` — `resolve_inheritance()`: the existing function to call; accepts `(raw_loop_dict, loop_dir)`, reads `from:`, opens parent via `resolve_loop_path`, deep-merges parent into child (child wins), strips `from:` from result
- `scripts/little_loops/fsm/validation.py:1990` — call site showing the correct insertion point: `data = resolve_inheritance(data, path.parent)` right after `yaml.safe_load`
- `scripts/little_loops/fsm/fragments.py:41` — `_deep_merge()`: utility used internally by `resolve_inheritance`; no need to call it directly

### Tests
- `scripts/tests/test_ll_loop_commands.py:826` — `TestLoopListFormatting.test_multiline_description_gets_ellipsis`: exact test pattern to follow (write YAML to `tmp_path`, call `_load_loop_meta(loop_file)`, assert on returned dict)
- `scripts/tests/test_fsm_inheritance.py` — `TestResolveInheritance` class: reference for `resolve_inheritance` test patterns including cycle detection and deep-merge assertions
- `scripts/tests/test_ll_loop_commands.py:840` — `TestLoopListFormatting.test_singleline_description_no_ellipsis`: second direct `_load_loop_meta` call pattern (same shape as line 826) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — section "Loop Template Inheritance via `from:`" states that children must explicitly repeat `category:` for it to appear in `ll-loop list`; after this fix that claim is no longer accurate — optional update to note that inherited metadata is resolved automatically [Agent 2 finding]

### Configuration
- N/A

## Acceptance Criteria

- [ ] A child loop with `from: lib/apo-base` and no explicit `category:` shows the parent's category in `ll-loop list`
- [ ] Unit test covering metadata inheritance in `scripts/tests/` (cli loop info tests)
- [ ] `python -m pytest scripts/tests/` passes


## Session Log
- `/ll:wire-issue` - 2026-06-13T01:25:39 - `9b9b3ddb-0e48-4bb6-9d26-28def2ae4f2f.jsonl`
- `/ll:refine-issue` - 2026-06-13T01:19:07 - `a4efd312-c1f5-4b77-a845-be41650b1078.jsonl`
- `/ll:format-issue` - 2026-06-13T01:13:54 - `5ecd855a-18b3-4edc-9eb8-01146e79c066.jsonl`
