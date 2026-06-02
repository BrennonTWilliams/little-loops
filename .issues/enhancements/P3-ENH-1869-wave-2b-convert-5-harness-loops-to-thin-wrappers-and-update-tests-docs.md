---
id: ENH-1869
title: "Wave 2b Part 2 — Convert 5 Harness Loops to Thin Wrappers, Update Tests and Docs"
type: ENH
priority: P3
parent: ENH-1775
relates_to:
- ENH-1868
size: Large
---

# ENH-1869: Wave 2b Part 2 — Convert 5 Harness Loops to Thin Wrappers, Update Tests and Docs

## Summary

Convert all 5 harness loops from inline generate→evaluate→score cycles to thin wrappers that delegate to the `generator-evaluator` oracle sub-loop. Update the 5 existing test classes, add the migration_targets entry, and update all documentation.

**Prerequisite**: ENH-1868 must be complete (sub-loop and fragment exist and pass `ll-loop validate`).

## Parent Issue

Decomposed from ENH-1775: Wave 2b — Extract `generator-evaluator` Sub-loop and `playwright_screenshot` Fragment

## Proposed Solution

### Step 4: Convert 5 harness loops to thin wrappers

Each wrapper keeps its pre-generate states (plan/segment/identify/prune) and replaces the inline `generate`, `evaluate`/`capture`, `score` states with a single `loop:` state delegating to `oracles/generator-evaluator` with `with:` bindings.

Model after `loop-router.yaml:334` (`dispatch` state) and `outer-loop-eval.yaml:55` (`run_sub_loop` state).

**Loop-specific notes**:

| Loop | Pre-generate states | Screenshot state name to remove | Score `on_yes` target | Run dir source |
|------|---------------------|--------------------------------|-----------------------|----------------|
| `html-website-generator.yaml` | `plan` | `capture` (not `evaluate`) | `smoke_test` | `${context.run_dir}` |
| `svg-image-generator.yaml` | `init`→`plan` | `evaluate` | `done` | `${captured.run_dir.output}` |
| `html-anything.yaml` | `init`→`plan` | `evaluate` | `done` | `${captured.run_dir.output}` |
| `hitl-md.yaml` | `init`→`segment` | `evaluate` | `finalize` | `${captured.run_dir.output}` |
| `hitl-compare.yaml` | `init`→`identify`→`prune` | `evaluate` | `done` | `${captured.run_dir.output}` |

Key constraints:
- `html-website-generator.yaml` post-generate routes `score.on_yes → smoke_test`; `hitl-md.yaml` routes `score.on_yes → finalize`. These states are retained in the parent wrappers. The thin wrapper's delegating `loop:` state sets `on_yes: smoke_test` or `on_yes: finalize` respectively.
- The sub-loop's `done` terminal maps to the parent's `on_yes`.
- `hitl-md.yaml` has **13 criteria** (not 6 as previously noted): document_readability, inline_highlighting, affordance_overlay, keyboard_reachability, inline_constraint, markdown_reconstruction, staged_highlighting, density_control, multi_channel_saliency, schema_switching, minimap_state_rail, trust_calibration, design_token_consistency.
- `on_handoff: spawn` is only in `html-website-generator.yaml` (line 21); remove it there since the sub-loop manages its own `on_handoff`.
- `with:` bindings must pass: rubric criteria/weights/thresholds, pass_threshold, run_dir source, max_iterations, timeout.
- `_validate_with_bindings()` (`validation.py:326`) cross-validates `with:` keys against the child loop's declared `parameters:`. Required-but-unbound parameters are flagged as ERROR.

Also check `svg-textgrad.yaml` — may use generator-evaluator pattern; evaluate for conversion (out of scope if it doesn't cleanly fit).

### Step 6: Validate all modified loops

```bash
ll-loop validate scripts/little_loops/loops/html-website-generator.yaml
ll-loop validate scripts/little_loops/loops/svg-image-generator.yaml
ll-loop validate scripts/little_loops/loops/html-anything.yaml
ll-loop validate scripts/little_loops/loops/hitl-md.yaml
ll-loop validate scripts/little_loops/loops/hitl-compare.yaml
```

Fix any ERROR-severity issues (especially `with:` binding mismatches and unreachable state warnings).

### Step 11: Update `test_builtin_loops.py` harness loop tests (TDD)

Tests in these classes assert on `generate`, `evaluate`/`capture`, `score` state existence, action content, evaluator types, and routing. They will break when those states are replaced by `loop:` delegation. Restructure each to assert:
- Pre-generate states retained
- Correct `loop:` target (`oracles/generator-evaluator`)
- Correct `with:` bindings for rubric/threshold/run_dir
- Correct routing from the delegating state (`on_yes` → `done`/`finalize`/`smoke_test`, `on_no` → retry/`failed`)

Current line numbers (may drift before implementation):
- `TestHtmlWebsiteGeneratorLoop` at line **2795**
- `TestSvgImageGeneratorLoop` at line **2888**
- `TestHtmlAnythingLoop` at line **3759**
- `TestHitlCompareLoop` at line **3931**
- `TestHitlMdLoop` at line **4096**

Follow the delegation-testing pattern from `TestAssumptionFirewallLoop:4611` (`test_run_gate_delegates_to_ready_to_implement_gate`).

### Step 12d: Add migration_targets entry

In `scripts/tests/test_fsm_fragments.py:987` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` — add the 5 thin-wrapper loops to the `migration_targets` list: `html-website-generator.yaml`, `svg-image-generator.yaml`, `html-anything.yaml`, `hitl-compare.yaml`, `hitl-md.yaml`.

### Step 7: Run regression suite

```bash
python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_validation.py -v --tb=short
```

Verify all 5 modified loops' test classes pass, fragment resolution tests pass, and executor sub-loop tests pass.

### Step 13: Update documentation

**(a) `docs/guides/LOOPS_GUIDE.md`**:
- Add `playwright_screenshot` to fragment tables
- Add `generator-evaluator` to oracle sub-loop listing
- Bump "Five libraries" prose at line 3151 to "Six libraries"

**(b) `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:743-744`**:
- Update references from inline harness loops to thin-wrapper + sub-loop architecture

**(c) `skills/create-loop/reference.md`**:
- Add `lib/harness.yaml` to the `## Fragment Catalog` library list
- Add `### lib/harness.yaml fragments` table section with `playwright_screenshot` row

**(d) `docs/reference/loops.md`**:
- Update fragment and sub-loop tables

**(e) `docs/generalized-fsm-loop.md:1658`**:
- Verify evaluate routing rule still applies after sub-loop extraction

**(f) `README.md:163`**:
- Increment `**65 FSM loops**` count to **66** (new oracle adds one; thin wrappers replace existing, not new)

**(g) `scripts/little_loops/loops/README.md:160-166`**:
- Add `lib/harness.yaml` row to `### Fragment Libraries` table

### Step 14: Extended validation

```bash
ll-loop fragments  # verify playwright_screenshot is listed
ll-loop show oracles/generator-evaluator --resolved  # verify internal states visible
```

Verify sub-loop resolution: `resolve_loop_path("oracles/generator-evaluator", ...)` resolves to `scripts/little_loops/loops/oracles/generator-evaluator.yaml`.

### Step 15: Full regression

```bash
python -m pytest scripts/tests/ -v --tb=short
```

Pay special attention to:
- `test_ll_loop_commands.py:400-485` (subdirectory listing must include new oracle)
- `test_doc_counts.py` (runnable loop count may need updating if `verify_documentation()` checks it)
- `ll-verify-docs` exit code (stale loop count causes exit 1)

## Integration Map

### Files to Modify
- `loops/html-website-generator.yaml` — convert to thin wrapper
- `loops/svg-image-generator.yaml` — convert to thin wrapper
- `loops/html-anything.yaml` — convert to thin wrapper
- `loops/hitl-md.yaml` — convert to thin wrapper
- `loops/hitl-compare.yaml` — convert to thin wrapper
- `scripts/tests/test_builtin_loops.py` — restructure 5 test classes, add migration_targets
- `scripts/tests/test_fsm_fragments.py:987` — add 5 loops to `migration_targets`
- `docs/guides/LOOPS_GUIDE.md` — fragment tables, library count
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:743-744` — architecture reference
- `skills/create-loop/reference.md` — Fragment Catalog
- `docs/reference/loops.md` — fragment and sub-loop tables
- `docs/generalized-fsm-loop.md:1658` — verify routing rule
- `README.md:163` — loop count
- `scripts/little_loops/loops/README.md:160-166` — library table

### Files Unchanged (but awareness required)
- `scripts/little_loops/cli/loop/_helpers.py:811` — `resolve_loop_path()` resolves `oracles/generator-evaluator` via built-in path; no changes needed
- `scripts/little_loops/cli/loop/lifecycle.py:440,586` — path-agnostic; no changes needed
- `scripts/tests/test_fsm_flow.py:324` — `test_all_builtin_loops_still_load` non-recursive `glob("*.yaml")` silently misses `oracles/generator-evaluator.yaml`; awareness only, no change required

## Scope Boundaries

- Does NOT include creating `oracles/generator-evaluator.yaml` or `lib/harness.yaml` (ENH-1868)
- Does NOT include `parse_tagged_json` or `ll_commit` fragments (ENH-1854, already done)
- `svg-textgrad.yaml` conversion is out of scope for this wave
- The 6 loops that inline `/ll:commit` but are NOT converted here remain for ENH-1777 or later

## Success Metrics

- All 5 harness loops pass `ll-loop validate` after conversion
- All 5 harness loop test classes pass in restructured delegation-testing form
- `TestBuiltinLoopMigration.migration_targets` includes all 5 thin-wrapper loops
- Documentation updated: library count, fragment catalog, architecture references
- `python -m pytest scripts/tests/ -v --tb=short` passes with no regressions
- `ll-verify-docs` exits 0 (loop count updated)

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ecf075d8-f165-4bd9-ad2a-2a2a8e1ddeea.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
