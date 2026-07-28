---
id: ENH-2774
status: done
priority: P2
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
focus_area: large-files
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
confidence_score: 96
outcome_confidence: 81
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
completed_at: '2026-07-28T11:58:10Z'
---

# ENH-2774: Split fsm/validation.py by rule family

## Summary

Architectural issue found by `/ll:audit-architecture`. All loop-validation
lint rules — MR-1 through MR-11 plus the specialty gates (policy-table,
static-loop-ref, haiku-gen, capture-reachability, session-mode-eval) — live in
one 3,126-line module.

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 1-3126 (entire file)
- **Module**: `little_loops.fsm.validation`

## Current Behavior

All loop-validation lint rules — MR-1 through MR-13 plus the specialty gates
(policy-table, static-loop-ref, haiku-gen, capture-reachability,
session-mode-eval) — live in one 3,444-line `scripts/little_loops/fsm/validation.py`
module, with no structural boundary matching the documented rule taxonomy.

## Expected Behavior

`fsm/validation.py` is a `fsm/validation/` package split by rule family (per
the Suggested Approach below), with a thin aggregator (`_base.py` +
`__init__.py`) preserving the current public/private API surface so every
existing importer keeps resolving names off `little_loops.fsm.validation`
unchanged.

## Impact

- **Development velocity**: adding a rule means navigating a 3k-line file;
  rule-local helpers are hard to distinguish from shared infrastructure.
- **Maintainability**: no structural boundary matches the documented rule
  taxonomy, so the docs and code drift apart.
- **Risk**: medium — cross-rule helper reuse is untracked; a tweak for one rule
  can shift another's behavior.

## Scope Boundaries

In scope: splitting `fsm/validation.py` into a `fsm/validation/` subpackage
and triaging its test file, per the ENH-2772 precedent. Out of scope: changing
any rule's validation logic/behavior, adding new lint rules, or altering the
public `ll-loop validate` CLI surface.

## Finding

### Current State

- 3,126 lines, 59 top-level defs/classes.
- Second-largest file in the codebase.
- Each new lint rule (the table in `.claude/CLAUDE.md` § Loop Authoring keeps
  growing) is appended to the same file; rules with unrelated concerns
  (evaluator pairing, shell-escape safety, capture dominance analysis,
  session-mode checks) share one namespace.

### Impact

- **Development velocity**: adding a rule means navigating a 3k-line file;
  rule-local helpers are hard to distinguish from shared infrastructure.
- **Maintainability**: no structural boundary matches the documented rule
  taxonomy, so the docs and code drift apart.
- **Risk**: medium — cross-rule helper reuse is untracked; a tweak for one rule
  can shift another's behavior.

## Proposed Solution

Convert to a `fsm/validation/` package split by rule family, with a thin
aggregator preserving the current public API (`ll-loop validate` entry points
and suppress-flag registry).

### Suggested Approach

1. Create `fsm/validation/` with modules along the existing families, e.g.
   `meta_rules.py` (MR-1..MR-6), `shell_safety.py` (MR-7, MR-9, MR-11),
   `evaluator_rules.py` (MR-8, MR-10, session-mode-eval, haiku-gen),
   `reachability.py` (capture-reachability, static loop refs, policy-table).
2. Keep shared context (loaded loop model, suppress-flag handling) in a
   `_base.py`; re-export everything from `__init__.py` so importers (including
   `cli/loop/_helpers`) are unchanged.
3. Run the full suite plus `ll-loop validate` against the bundled loops to
   confirm identical findings before/after.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current size**: `scripts/little_loops/fsm/validation.py` is now 3,445
  lines / ~57 top-level defs (2 classes: `ValidationSeverity`,
  `ValidationError`) — grown from the 3,126 lines noted at filing time.
  Roughly 60% the size of `session_store.py` (5,154 lines) before its ENH-2772
  split, so the same subpackage pattern applies but at a smaller scale.
- **Precedent to follow directly**: `scripts/little_loops/session_store/__init__.py`
  and `scripts/little_loops/fsm/__init__.py` (the very package this split
  extends) already use the exact aggregator shape this issue proposes: a
  package-docstring "layout" manifest, one `from little_loops.<pkg>.<submodule>
  import (...)` block per submodule, then a single alphabetized `__all__`
  that explicitly re-exports private (`_`-prefixed) names "for test access"
  (`session_store/__init__.py:151-239`, `issue_history/__init__.py:203-207`
  is the origin of that private-re-export convention).
- **Load-bearing public/private API surface that must resolve off
  `fsm.validation` (or the new `fsm/validation/__init__.py`) after the
  split**:
  - Re-exported today via `fsm/__init__.py:163-168`: `ValidationError`,
    `is_runnable_loop`, `load_and_validate`, `validate_fsm`.
    `ValidationSeverity` is used across rule functions but is **not**
    currently re-exported at the `fsm` package level — worth re-exporting
    explicitly in the new `__init__.py` since it's part of every
    `ValidationError` construction.
  - Reached directly off `fsm.validation` (bypassing `fsm/__init__.py`) by
    other modules, including private names:
    - `scripts/little_loops/fsm/executor.py:65` — `_SKILL_INVOKE_RE`
      (module-level regex constant, `validation.py:2271`) and
      `_effective_session_mode` (`validation.py:2480`); `executor.py:824` —
      deferred `load_and_validate`.
    - `scripts/little_loops/fsm/persistence.py:41` — `_is_meta_loop`
      (`validation.py:1420`).
    - `scripts/little_loops/fsm/route_table.py:596` — `_find_reachable_states`
      (`validation.py:3264`, deferred import).
    - `scripts/little_loops/doc_counts.py:14` — `is_runnable_loop`.
    - `scripts/little_loops/cli/loop/_helpers.py:1410,1430`,
      `cli/loop/edit_routes.py:37`, `cli/loop/info.py:49`,
      `cli/loop/config_cmds.py:20`, `cli/loop/run.py:106` — `load_and_validate`
      (the `ll-loop validate` / `ll-loop run` entry-point chain).
    - `scripts/little_loops/cli/doctor.py:398` — block import from
      `validation`.
    - `scripts/tests/test_fsm_validation.py` (~150 lines of imports) and
      ~20 other test files import private `_validate_*` rule functions
      directly for unit testing.
  - Any split must keep all of the above resolvable as attributes of
    `little_loops.fsm.validation` (module → package with the same import
    path), following the private-re-export pattern already established in
    `session_store/__init__.py`.
- **Suppress-flag mechanism is simpler than "registry" implies — no
  decorator or dict-based registry exists today**:
  1. `KNOWN_TOP_LEVEL_KEYS` (`validation.py:215-270`, a `frozenset[str]`)
     enumerates every valid top-level YAML key including all `*_ok` suppress
     flags; it is consulted only by `load_and_validate`'s unknown-top-level-key
     check (`validation.py:3391-3399`).
  2. Each rule function reads its own flag directly off the `FSMLoop`
     dataclass instance, e.g. `_validate_terminal_action_ok`:
     `if fsm.terminal_action_ok: return []` (line 1183-1184). The flag
     fields themselves are declared on `FSMLoop` in `fsm/schema.py`, not in
     `validation.py`.
  - "Preserving the suppress-flag registry" therefore means: (a)
    `KNOWN_TOP_LEVEL_KEYS` must remain a single set assembled from all split
    submodules (own by `_base.py` or the aggregator), and (b) each rule
    module keeps its own direct `fsm.<flag>_ok` read — there's no
    indirection layer to preserve beyond that set.
- **Cross-rule helper reuse — candidates for `_base.py`** (used by more than
  one rule family, so cannot move into a single family module):
  - `_check_param_type` (line 465) — used by `_validate_with_bindings` and
    `_validate_fragment_bindings` (structural, not MR-numbered).
  - `_is_llm_judged` (line 1701) — used by structural `_validate_state_action`
    and by MR-1/haiku-gen/session-mode-eval rule logic.
  - `_find_reachable_states` (line 3264) — used internally by `validate_fsm`
    and externally by `fsm/route_table.py`.
  - `_strip_interpolation_prefix` (line 2920) — shared between
    capture-reachability and progress-paths-isolation checks.
  - `_effective_session_mode` (line 2480) — session-mode-eval's helper, also
    imported externally by `fsm/executor.py`.
  - `_SKILL_INVOKE_RE` (line 2271) — module constant used by MR-12's
    pruning-profile logic and imported directly by `fsm/executor.py`.
  - `ValidationError`/`ValidationSeverity` — constructed by every rule
    function; must live in the shared base regardless of split shape.
- **Rules not in the numbered MR-1..MR-13 table but present in the file** —
  the suggested 4-module split needs a fifth bucket (or these fold into
  "structural"): `_validate_zero_retry_counter` (1513, +`_is_counter_action`
  1565, `_suggested_target` 1570), `_validate_harness_multimodal_evaluator_blind_spot`
  (1582), `_validate_input_key_without_guard` (1643), `_validate_classify_route_default`
  (2540), `_validate_on_max_steps`/`_validate_on_max_iterations` (2679/2700),
  `_validate_circuit` (2867), `_validate_host_guard` (2721),
  `_validate_prompt_size_guard` (2847), `_validate_progress_paths_isolation`
  (2925, MR-3's actual detector — paired with `_find_shared_tmp_writes` 1627).
  Also structural/entry-point functions not gated by any suppress flag:
  `_validate_evaluator` (282), `_validate_parameters` (421),
  `_validate_with_bindings` (480), `_validate_loop_references` (555, the
  "static `loop:` ref" ERROR rule), `_validate_fragment_bindings` (592),
  `_validate_state_action` (664), `_validate_state_routing` (812),
  `_validate_state_cost_ceiling` (1018), `_validate_targets` (1096),
  `_validate_failure_terminal_action` (1114), `validate_fsm` (1215, the
  dispatcher), `is_runnable_loop` (3307), `load_and_validate` (3336).
- **`terminal-action-ok` and `abandonment-verdict-ok` (MR-13) aren't listed
  in the issue's original 4-family split** — `_validate_terminal_action_ok`
  (1167) and `_validate_abandonment_verdict` (2182) need a home; both fit
  `evaluator_rules.py` or a fifth module by the issue's own naming scheme.
- **Test-split convention** (from the ENH-2772 precedent, commit `f72922c5`):
  this repo has **no mirror-directory convention** for split-package
  tests — both `fsm/` (16 submodules) and `issue_history/` (13 submodules)
  keep tests as flat, module-name-prefixed files under `scripts/tests/`
  (e.g. `test_fsm_schema.py`), not `scripts/tests/fsm/test_schema.py`.
  Splitting `test_session_store.py` (~75 `class Test*` groups) required
  **manual per-class triage**, not a mechanical move, because the original
  file was organized by feature/schema-version rather than by target module.
  `scripts/tests/test_fsm_validation.py` will likely need the same manual
  triage into files like `test_fsm_validation_meta_rules.py`,
  `test_fsm_validation_shell_safety.py`,
  `test_fsm_validation_evaluator_rules.py`,
  `test_fsm_validation_reachability.py` (naming to match whichever final
  module names are chosen) — confirm the current file's internal
  organization before committing to a 1:1 mapping.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/validation.py` — split into
  `scripts/little_loops/fsm/validation/` (`__init__.py`, `_base.py`,
  `meta_rules.py`, `shell_safety.py`, `evaluator_rules.py`,
  `reachability.py`, plus a bucket for the un-numbered rules listed above).
- `scripts/little_loops/fsm/__init__.py:163-168` — import block stays
  syntactically unchanged (`from little_loops.fsm.validation import (...)`);
  verify it still resolves once `validation` becomes a package.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/executor.py:65,824` — `_SKILL_INVOKE_RE`,
  `_effective_session_mode`, deferred `load_and_validate`
- `scripts/little_loops/fsm/persistence.py:41` — `_is_meta_loop`
- `scripts/little_loops/fsm/route_table.py:596` — `_find_reachable_states`
- `scripts/little_loops/doc_counts.py:14` — `is_runnable_loop`
- `scripts/little_loops/cli/loop/_helpers.py:1410,1430`,
  `cli/loop/edit_routes.py:37`, `cli/loop/info.py:49`,
  `cli/loop/config_cmds.py:20`, `cli/loop/run.py:106` — `load_and_validate`
- `scripts/little_loops/cli/doctor.py:398` — block import from `validation`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_open_question_stall.py:217,218,225,236,244` — imports
  `EVALUATOR_REQUIRED_FIELDS`, `NON_LLM_EVALUATOR_TYPES`, and the private
  `_validate_evaluator` directly off `little_loops.fsm.validation`; not
  previously in the re-export checklist. These three names must be added to
  the new `fsm/validation/__init__.py`'s re-export list alongside the
  already-enumerated private names, or this test breaks on the split.

### Similar Patterns

- `scripts/little_loops/session_store/__init__.py` — aggregator docstring +
  per-submodule import blocks + alphabetized `__all__` with a "Private
  functions re-exported for test access" section; also re-exports `sqlite3`/
  `subprocess` as live package attributes because `conftest.py` monkeypatches
  `session_store.sqlite3.connect`.
- `scripts/little_loops/fsm/__init__.py:1-250` — same shape, grouped by
  concern heading in the docstring; this is the package `fsm/validation/`
  will live inside.
- `scripts/little_loops/issue_history/__init__.py:120-127,203-207` — origin
  of the "private names re-exported for test access" convention.

### Tests

- `scripts/tests/test_fsm_validation.py` — main suite; imports ~26+ private
  `_validate_*` functions directly. Needs manual per-class/per-function
  triage into module-prefixed files (no mirror-directory convention exists
  in this repo — see Codebase Research Findings above).
- ~20 other test files reference `fsm.validation` indirectly (via
  `load_and_validate`/`validate_fsm`) including `test_builtin_loops.py`,
  `test_fsm_executor.py`, `test_fsm_schema.py`, `test_fsm_fragments.py`,
  `test_fsm_flow.py`, `test_fsm_inheritance.py`, `test_verify_issue_loop.py`,
  `test_create_loop.py`, `test_loop_composer.py`,
  `test_loop_composer_adaptive.py`, `test_rn_*.py`,
  `test_ll_loop_commands.py`, `test_ll_loop_edit_routes.py` — these should
  need no changes if the package's import path stays `little_loops.fsm.validation`.

### Documentation

- `.claude/CLAUDE.md` § Loop Authoring — the MR-1..MR-13 rule table; update
  if module ownership becomes part of the documented rule reference.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (lines ~85-110) — full rule
  taxonomy and suppress-flag documentation.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4872` (module index table row for
  `little_loops.fsm.validation`) and `:5623` (the `### little_loops.fsm.validation`
  API section, through the `validate_fsm` "Checks performed" block) — should
  note the module is now a package with named submodules.
- `docs/guides/LOOPS_GUIDE.md:220` — stale anchor
  `` fsm/validation.py:_validate_state_cost_ceiling `` needs retargeting to
  whichever new submodule houses that rule.
- `skills/create-loop/loop-types.md:1918` — stale anchor
  `` scripts/little_loops/fsm/validation.py:76-94 `` (citing
  `NON_LLM_EVALUATOR_TYPES`) needs retargeting.
- `scripts/little_loops/fsm/schema.py:348` — docstring cross-reference to
  `` fsm/validation.py:_validate_state_cost_ceiling `` needs retargeting.
- Stale `fsm/validation.py` path/line comments in test files (non-executable,
  won't break CI but become misleading after the split — update opportunistically):
  `scripts/tests/test_builtin_loops.py:10043,10114,11810`,
  `scripts/tests/test_ll_loop_commands.py:6716,6863`,
  `scripts/tests/test_rn_remediate.py:2062`,
  `scripts/tests/test_fsm_open_question_stall.py:232`,
  `scripts/tests/test_fsm_signal_integration.py:50`.

## Implementation Steps

1. Create `scripts/little_loops/fsm/validation/` package. Move
   `ValidationSeverity`, `ValidationError`, `KNOWN_TOP_LEVEL_KEYS`, and the
   cross-rule helpers (`_check_param_type`, `_is_llm_judged`,
   `_find_reachable_states`, `_strip_interpolation_prefix`,
   `_effective_session_mode`, `_SKILL_INVOKE_RE`) into `_base.py`.
2. Split rule functions into family modules per the Suggested Approach
   above, adding a home for the un-numbered rules (zero-retry-counter,
   multimodal-blind-spot, input-key-guard, classify-route-default,
   on-max-steps/iterations, circuit, host-guard, prompt-size-guard,
   progress-paths-isolation) and for `terminal-action-ok`/MR-13
   (`_validate_terminal_action_ok`, `_validate_abandonment_verdict`), which
   the original 4-family split didn't allocate.
3. Write `fsm/validation/__init__.py` following the
   `session_store/__init__.py` / `fsm/__init__.py` aggregator shape: package
   docstring listing the layout, one import block per submodule, and a
   single alphabetized `__all__` that re-exports the private names listed
   under Dependent Files above (so `executor.py`, `persistence.py`,
   `route_table.py`, and test files keep resolving them off
   `little_loops.fsm.validation`).
4. Triage `scripts/tests/test_fsm_validation.py` into module-prefixed test
   files (e.g. `test_fsm_validation_meta_rules.py`) matching the final
   module boundaries — manual triage, not a mechanical split (per the
   session_store precedent).
5. Run `python -m pytest scripts/tests/` and `ll-loop validate` against the
   bundled loops to confirm identical findings before/after.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `EVALUATOR_REQUIRED_FIELDS`, `NON_LLM_EVALUATOR_TYPES`, and
   `_validate_evaluator` to the new `fsm/validation/__init__.py` re-export
   list — `scripts/tests/test_fsm_open_question_stall.py` imports all three
   directly off `little_loops.fsm.validation` and isn't covered by the
   originally-enumerated re-export set.
7. Retarget the stale `fsm/validation.py:<line>` anchors in
   `docs/guides/LOOPS_GUIDE.md:220`, `skills/create-loop/loop-types.md:1918`,
   and `scripts/little_loops/fsm/schema.py:348` to point at the new
   submodule housing each referenced rule/constant; update
   `docs/reference/API.md:4872,5623` to describe `fsm.validation` as a
   package.
8. Follow the `ENH-2891` test-split template (companion issue that split
   `test_session_store.py`, commit range around `f72922c5`) when triaging
   `test_fsm_validation.py`'s 44 `Test*` classes: flat
   `test_fsm_validation_<family>.py` files directly under `scripts/tests/`
   (no mirror directory, no `conftest.py` promotion), duplicating any
   file-local fixtures/helpers into each new file rather than centralizing
   them.

## Impact Assessment

- **Severity**: High
- **Effort**: Medium
- **Risk**: Medium
- **Breaking Change**: No

## Session Log
- `ll-auto` - 2026-07-28T11:58:10 - `657e0000-3628-4718-aac6-1fec4806a863.jsonl`
- `/ll:ready-issue` - 2026-07-28T11:38:10 - `456a88a8-c02d-4bd2-b8c8-1c8626901228.jsonl`
- `/ll:wire-issue` - 2026-07-28T11:35:39 - `37f16d94-3daa-43c7-8a09-4d69095b7fb5.jsonl`
- `/ll:refine-issue` - 2026-07-28T11:31:27 - `aac8b81c-7c1b-41f1-bdb4-f1d5e15bf5c0.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-28
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
