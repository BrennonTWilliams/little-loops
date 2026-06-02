---
id: ENH-1869
title: "Wave 2b Part 2 \u2014 Convert 5 Harness Loops to Thin Wrappers, Update Tests\
  \ and Docs"
type: ENH
status: done
priority: P3
parent: ENH-1775
relates_to:
- ENH-1868
size: Large
labels:
- loops
- testing
- refactoring
- orchestration
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-06-02 04:16:32+00:00
---

# ENH-1869: Wave 2b Part 2 — Convert 5 Harness Loops to Thin Wrappers, Update Tests and Docs

## Summary

Convert all 5 harness loops from inline generate→evaluate→score cycles to thin wrappers that delegate to the `generator-evaluator` oracle sub-loop. Update the 5 existing test classes, add the migration_targets entry, and update all documentation.

**Prerequisite**: ENH-1868 must be complete (sub-loop and fragment exist and pass `ll-loop validate`).

## Current Behavior

The 5 harness loops (`html-website-generator.yaml`, `svg-image-generator.yaml`, `html-anything.yaml`, `hitl-md.yaml`, `hitl-compare.yaml`) each contain inline `generate` → `evaluate`/`capture` → `score` state cycles, duplicating oracle evaluation logic across all 5 loop definitions.

## Expected Behavior

Each of the 5 harness loops becomes a thin wrapper that replaces its inline evaluation states with a single `loop:` delegation state (`run_gen_eval`) pointing to `oracles/generator-evaluator`. Pre-generate states (plan/segment/identify/prune) are retained. Tests, validation, and documentation are updated to reflect the new delegation architecture.

## Parent Issue

Decomposed from ENH-1775: Wave 2b — Extract `generator-evaluator` Sub-loop and `playwright_screenshot` Fragment

## Motivation

This enhancement would:
- **Code deduplication**: Eliminates duplicated `generate` → `evaluate` → `score` logic spread across 5 loop files; future rubric or evaluation changes only need to be made in the oracle sub-loop
- **Maintainability**: All 5 wrappers share identical evaluation semantics via `oracles/generator-evaluator`, reducing behavioral drift risk
- **Architecture alignment**: Completes the Wave 2b decomposition begun in ENH-1868, fulfilling the thin-wrapper pattern established for harness loops

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

**Failure routing exceptions** — `on_no`/`on_error` from the `run_gen_eval` delegating state are NOT always `failed` directly:
- `html-anything.yaml`: routes `on_no: diagnose, on_error: diagnose` through an intermediate `diagnose` prompt state before `failed`
- `svg-image-generator.yaml`: same pattern — `on_no: diagnose, on_error: diagnose` through intermediate `diagnose` before `failed`
- All other wrappers route `on_no: failed, on_error: failed` directly

### Oracle Sub-Loop Parameters (Confirmed from `oracles/generator-evaluator.yaml:14`)

| Parameter | Required | Default |
|-----------|----------|---------|
| `run_dir` | required | — |
| `generate_prompt` | required | — |
| `rubric` | optional | `""` (empty string) |
| `pass_threshold` | optional | `6` |
| `artifact_path` | optional | `"index.html"` |

`svg-image-generator.yaml` is the **only** wrapper that binds `artifact_path: "image.svg"` to override the oracle default.

`html-website-generator.yaml` is the **only** wrapper that uses `${context.run_dir}` (no `init` shell state to capture the absolute path). All other wrappers use `${captured.run_dir.output}`.

### Current Working Tree State

_Research confirms all 5 loop files are already converted in the working tree (git status shows them as modified-unstaged or staged):_
- `hitl-compare.yaml` — has `run_gen_eval` state with `loop: oracles/generator-evaluator`; no inline `generate`/`evaluate`/`score` states
- `hitl-md.yaml` — converted; `on_yes: finalize` confirmed
- `html-anything.yaml` — converted; failure routes through `diagnose`
- `html-website-generator.yaml` — converted; uses `${context.run_dir}` directly; `on_yes: smoke_test`
- `svg-image-generator.yaml` — converted; binds `artifact_path: "image.svg"`; failure routes through `diagnose`

`test_builtin_loops.py` and `test_fsm_fragments.py` are also modified. Validate, run regression, and complete documentation before closing.

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

Current line numbers (updated from codebase research — working tree):
- `TestHtmlWebsiteGeneratorLoop` at line **2795**
- `TestSvgImageGeneratorLoop` at line **2903** _(was 2888 before conversion work)_
- `TestHtmlAnythingLoop` at line **3791** _(was 3759)_
- `TestHitlCompareLoop` at line **3945** _(was 3931)_
- `TestHitlMdLoop` at line **4105** _(was 4096)_

Follow the delegation-testing pattern from `TestAssumptionFirewallLoop:4599` (`test_run_gate_delegates_to_ready_to_implement_gate`).

Each class now asserts on:
- `run_gen_eval.loop == "oracles/generator-evaluator"`
- `with:` contains `run_dir`, `generate_prompt`, `rubric`, `pass_threshold` (plus `artifact_path` for `TestSvgImageGeneratorLoop`)
- Correct `on_yes` routing per loop (`smoke_test`, `finalize`, or `done`)
- Absence of old inline `generate`, `evaluate`/`capture`, `score` states

### Step 12d: Add migration_targets entry

In `scripts/tests/test_fsm_fragments.py:987` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` — add the 5 thin-wrapper loops to the `migration_targets` list: `html-website-generator.yaml`, `svg-image-generator.yaml`, `html-anything.yaml`, `hitl-compare.yaml`, `hitl-md.yaml`.

_Research confirms all 5 loops are already present in `migration_targets` in the current working tree (test_fsm_fragments.py is modified). Verify with `grep -n "migration_targets" scripts/tests/test_fsm_fragments.py` before re-adding._

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
- `prompts/hitl-md-generate.md` — referenced by `hitl-md.yaml` generate prompt via `Read`; content unchanged by the conversion

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:903-904` — `## See Also` descriptions of `hitl-compare` and `hitl-md` use "GAN-style generate/evaluate/score pipeline" language implying inline states; update to reflect oracle delegation (note: issue Step 13(b) references lines 743-744 — verify both zones; the `## See Also` section at ~line 903 is the confirmed stale location)
- `docs/guides/LOOPS_GUIDE.md:1031` — "Design rule: Playwright failure routing" blockquote describes `evaluate`/`score` states as if they live in the calling loop; after conversion those states live inside `oracles/generator-evaluator`; update note to clarify the rule applies to the oracle's internal states

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- All 5 loop YAMLs confirmed converted in working tree; the delegating state is named `run_gen_eval` in every wrapper
- `lib/harness.yaml` fragment confirmed exists (ENH-1868 prerequisite complete)
- `oracles/generator-evaluator.yaml:14` `parameters:` block confirms 5 params: `run_dir` (required), `generate_prompt` (required), `rubric` (optional), `pass_threshold` (optional, default 6), `artifact_path` (optional, default "index.html")
- `_validate_with_bindings()` lives at `scripts/little_loops/fsm/validation.py:326`
- `resolve_loop_path()` lives at `scripts/little_loops/cli/loop/_helpers.py:809-811`
- `TestAssumptionFirewallLoop` delegation test pattern is at line 4599 (not 4611)
- `migration_targets` in `test_fsm_fragments.py` already includes all 5 loops
- `TestHtmlAnythingLoop` and `TestSvgImageGeneratorLoop` now have `test_diagnose_routes_to_failed` / `test_diagnose_is_not_terminal` tests (no equivalent in other 3 classes)

## Impact

- **Priority**: P3 - Decomposed sub-task; unblocked once ENH-1868 prerequisite is complete
- **Effort**: Large - 5 loop YAML files + 2 test files + 5+ documentation files
- **Risk**: Low - All 5 loops already converted in working tree; main task is validation, test restructuring, and documentation
- **Breaking Change**: No - Internal refactor; loop parameters and outputs are unchanged

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

## Resolution

All 5 harness loops converted to thin wrappers delegating to `oracles/generator-evaluator` via a `run_gen_eval` state. All 5 loops pass `ll-loop validate`. All 5 test classes restructured to assert delegation pattern (107 targeted tests pass, 1069 total regression passes). Documentation updated: `docs/reference/loops.md` (added oracle sub-loop section), `skills/create-loop/reference.md` (added `lib/harness.yaml` fragment catalog entry), `scripts/little_loops/loops/README.md` (added `lib/harness.yaml` row), `AUTOMATIC_HARNESSING_GUIDE.md` (updated hitl-compare/hitl-md See Also descriptions), `LOOPS_GUIDE.md` (updated Playwright failure routing blockquote to clarify it applies to oracle's internal states).

## Session Log
- `/ll:ready-issue` - 2026-06-02T04:08:32 - `0a24b413-6e18-4285-b34f-33227dbca56d.jsonl`
- `/ll:confidence-check` - 2026-06-02T23:04:50 - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:wire-issue` - 2026-06-02T04:03:44 - `dda81d25-0cb7-4915-9b75-8db71b58f63b.jsonl`
- `/ll:format-issue` - 2026-06-02T03:57:18 - `c9f63592-ca60-4e14-82aa-eaa7bf672b2a.jsonl`
- `/ll:refine-issue` - 2026-06-02T03:53:32 - `188a3bd6-1a9f-4df1-ba54-6d7895aa319d.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ecf075d8-f165-4bd9-ad2a-2a2a8e1ddeea.jsonl`
- `/ll:manage-issue` - 2026-06-02T04:16:32Z - `c69d95aa-ca7b-4968-852b-d44517330591.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
