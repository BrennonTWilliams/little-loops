---
id: BUG-3107
type: BUG
title: 'll-loop validate: warn when a loop declares no `scope:`'
priority: P3
status: done
parent: BUG-3088
captured_at: '2026-08-08T00:00:00Z'
completed_at: '2026-08-08T14:06:07Z'
discovered_date: 2026-08-08
discovered_by: issue-size-review
labels:
- fsm-concurrency
- loop-authoring
relates_to:
- BUG-3088
- BUG-3106
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
testable: true
---

# BUG-3107: `ll-loop validate` should warn when a loop declares no `scope:`

## Summary

This is Deliverable 2 of [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md):
the regression guard. `ll-loop validate` emits a WARNING when a loop declares
no `scope:`, so a newly authored loop cannot silently reacquire a repo-root
lock the way the 78 loops audited in [[BUG-3106]] did.

**Depends on [[BUG-3106]] landing first.** Per BUG-3088's "Warning-ratchet
decision": enrolling this rule in `test_builtin_loops.py`'s deterministic
warning-category ratchet before BUG-3106 lands would introduce 78 findings at
once, either tripping the ratchet or requiring a 78-entry allowlist. Land
BUG-3106 first so the finding count is ~0, then add this rule and enroll it
in the ratchet directly.

## Parent Issue

Decomposed from [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md):
Audit unscoped loops and warn at validate time when `scope:` is missing.

## Current Behavior

`ll-loop validate` runs `validate_fsm()` against a loop's YAML but performs
no check on `fsm.scope`. A loop authored without a `scope:` key validates
cleanly (no ERROR, no WARNING) and only reveals the gap at `ll-loop run`
time, when `run.py:373`'s `resolve_scope(fsm.scope or ["."], fsm.context)`
fallback silently locks the repo root and false-conflicts with every other
narrowly-scoped loop running concurrently.

## Expected Behavior

`ll-loop validate` emits a `ValidationSeverity.WARNING` when `fsm.scope` is
empty, naming `scope: ["."]` as the explicit repo-wide opt-in. The warning
surfaces in both plain-text and `--json` output paths of `cmd_validate()`,
the same way other structural WARNINGs (e.g. `_validate_input_key_without_guard`)
already do.

## Steps to Reproduce

1. Author a loop YAML under `scripts/little_loops/loops/` (or point
   `ll-loop validate` at any loop file) that omits the `scope:` key
   entirely.
2. Run `ll-loop validate <loop-name>`.
3. Observe: validation passes with no warning about the missing `scope:`,
   even though the loop will silently acquire a repo-root lock the first
   time it runs (`cli/loop/run.py:373`).

## Root Cause

`FSMLoop.scope: list[str]` defaults to `[]` (`fsm/schema.py:1278`) and
nothing in `validate_fsm()` currently checks it. A loop author who forgets
`scope:` gets no signal until their loop conflicts at runtime with another
unscoped loop, both silently locking the repo root via `run.py`'s
`resolve_scope(fsm.scope or ["."], fsm.context)` fallback.

## Proposed Solution

Follow the shape of `_validate_input_key_without_guard`
(`fsm/validation/structural_rules.py:1195-1217`): a new
`_validate_missing_scope(fsm: FSMLoop) -> list[ValidationError]` function —
single-condition early-return guard (`if fsm.scope: return []`), then one
`ValidationError(severity=ValidationSeverity.WARNING)` whose message names
`scope: ["."]` as the explicit opt-in for repo-wide loops (otherwise the
remedy is undefined and the rule reads as un-silenceable).

Wiring (3 sites, confirmed exhaustive by `/ll:refine-issue` on BUG-3088):
1. `errors.extend(_validate_missing_scope(fsm))` appended into
   `validate_fsm()`'s flat call sequence (`structural_rules.py:1063` area).
2. Function name added to the `from little_loops.fsm.validation.structural_rules
   import (...)` block in `fsm/validation/__init__.py:127-152`, alphabetically
   ordered.
3. Same name added to `__all__` at `__init__.py:154-255`, alphabetically
   ordered.

`cmd_validate()` (`cli/loop/config_cmds.py`) requires no per-rule change — it
iterates whatever `ValidationError`s `validate_fsm()` returns generically;
verify (no code change expected) that the new WARNING surfaces in both the
`--json` `violations` list and the plain-text `⚠` loop.

### Decision Rule

A loop satisfies the rule iff `fsm.scope` is non-empty. `scope: ["."]` is the
explicit repo-wide declaration and passes; omitting `scope:` fails with a
WARNING. There is no separate "repo-wide is allowed" carve-out.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/fsm/validation/structural_rules.py` — add `_validate_missing_scope()` and wire into `validate_fsm()` near `structural_rules.py:1063`
- `scripts/little_loops/fsm/validation/__init__.py` — add `_validate_missing_scope` to the import block (`:127-152`) and `__all__` (`:154-255`); alphabetically it sits between `_validate_meta_loop_evaluation` and `_validate_on_max_iterations` in both lists

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation/structural_rules.py:1632` (`load_and_validate`) — calls `validate_fsm()`; the new rule's output flows through unchanged
- `scripts/little_loops/cli/loop/config_cmds.py:12-76` (`cmd_validate()`) — consumes `validate_fsm()`'s output generically (branches only on `ValidationSeverity`, no per-rule logic); confirmed no code change needed here
- `scripts/little_loops/cli/loop/run.py:373` — `resolve_scope(fsm.scope or ["."], fsm.context)`, the runtime fallback this lint warns loop authors about ahead of time. `resolve_scope()` itself (`fsm/concurrency.py:35-53`) applies no default — an empty input list returns `[]`; the `or ["."]` fallback lives only at this one caller, not inside `resolve_scope`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/scaffold_eval.py:268-280` (`scaffold_eval()`) and `scripts/little_loops/cli/loop/scaffold_verify.py:213-233` (`scaffold_verify()`) — each constructs an `FSMLoop(...)` in-process without a `scope=` kwarg, then calls `validate_fsm(fsm)` directly. `ScaffoldResult.errors = [f"{e.severity.value}: {e.path}: {e.message}" for e in validation_errors]` includes every severity (not just ERROR), so every `ll-loop scaffold-eval`/`ll-loop scaffold-verify` run will gain a new `"warning: scope: ..."` line in its `errors` list / `--json` payload. `ScaffoldResult.validated` (`has_errors`, ERROR-only) is unaffected, and no test in `scripts/tests/test_ll_loop_scaffold_eval.py` / `test_ll_loop_scaffold_verify.py` asserts `result.errors == []`, so nothing breaks — but the emitted payload contents change for a code path not previously named in this issue. [Agent 1/2 finding]

### Conventions in Force
- New structural WARNING rules follow a single early-return-guard shape: return `[]` for the pass case, a one-item `[ValidationError(...)]` for the warning case, with `path` set to the field name the warning concerns — evidence: `_validate_input_key_without_guard` (`structural_rules.py:1195-1217`), the direct template already named in this issue's Proposed Solution.
- `fsm/validation/__init__.py`'s import block and `__all__` list are both alphabetically ordered within their private-function sections — evidence: `__init__.py:127-152`, `:154-255`.

### Tests
- `scripts/tests/test_fsm_validation_structural.py` — add trigger/non-trigger/`..._wired_into_validate_fsm` tests, modeled on the tests near line 1539
- `scripts/tests/test_builtin_loops.py:13464` (`TestValidatorWarningBudget`) — `CATEGORY_PATTERNS` dict at `:13474-13484`; add one `"no-scope": "<substring>"` entry
- `scripts/tests/test_builtin_loops.py` (`TestBuiltinLoopFiles`, sibling of `test_all_have_description_field` at lines 100-118) — add `test_all_have_scope_field`
- `scripts/tests/test_ll_loop_commands.py:205-220` (`TestCmdValidate::test_validate_json_output_valid_loop`) — its inline `valid-loop.yaml` fixture (written at lines 210-212) declares no `scope:` and the test asserts an empty `violations` list; this breaks once the rule ships and needs `scope:` added to the fixture or the assertion updated

### Documentation (informational — BUG-3108 owns doc updates, not this issue)
- `skills/create-loop/reference.md:631` currently reads "**Most users can omit this field**" for `scope:` — directly contradicts the new lint once it ships. Flagged because it's the one doc site whose current wording actively conflicts with this rule's intent.
- `scripts/little_loops/fsm/fsm-loop-schema.json:30-35` — `scope` JSON-schema property description; not mentioned in the issue, no runtime effect.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:786-813` — the `#### ll-loop validate <loop>` section enumerates every named structural/lint rule `validate_fsm()` emits (MR-1…MR-14, Zero-retry counter, etc.) with severity; has no entry for the new "no-scope" WARNING. Same informational status as the two doc sites above — not test-enforced, but the canonical rule-reference doc. [Agent 2 finding]
- `skills/create-loop/loop-types.md:159,274,388,498` — four YAML scaffold snippets each show `# scope: ["src/"]  # Optional: declare paths for ll-parallel concurrency control`; same "optional" framing already flagged for `reference.md:631`, but these four sites are not literally covered by that reference and sit in the same skill directory BUG-3108 is scoped to own. [Agent 2 finding]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
N/A — no new data type. `_validate_missing_scope` reuses the existing `ValidationError`/`ValidationSeverity` types (`fsm/validation/_base.py:15-38`) and the existing `FSMLoop.scope: list[str] = field(default_factory=list)` (`fsm/schema.py:1278`).

### Signatures
- `_validate_missing_scope(fsm: FSMLoop) -> list[ValidationError]` — new, sited in `fsm/validation/structural_rules.py` near `_validate_input_key_without_guard` (`:1195-1217`)
- `ValidationError(message: str, path: str, severity: ValidationSeverity)` — existing, reused unmodified (`fsm/validation/_base.py:15-38`)
- `scope: list[str]` — existing field on `FSMLoop` being checked, reused unmodified (`fsm/schema.py:1278`)

### Call Path
`validate_fsm()` (`structural_rules.py:908`) → new `errors.extend(_validate_missing_scope(fsm))` call sited in the flat `errors.extend(...)` sequence around `:1063` (confirmed no ordering dependency on neighboring rule calls — each rule takes only `fsm` plus values already computed earlier in `validate_fsm()`) → `load_and_validate()` (`:1632`) merges/splits the result by severity → `cmd_validate()` (`cli/loop/config_cmds.py:12-76`) renders it generically in both `--json` and plain-text output paths, since that function only branches on `ValidationSeverity` and has no per-rule logic.

### Decision Rules
- Gap kind: a loop whose `fsm.scope == []` (the dataclass default). Trigger condition: `if fsm.scope: return []` — the guard passes (no warning) for any non-empty list, including the explicit repo-wide opt-in `scope: ["."]`; it fails (warning fires) only for the empty-list default.
- Severity: `ValidationSeverity.WARNING`, never ERROR — a missing scope doesn't block validation, matching the `_validate_input_key_without_guard` precedent this rule is modeled on.
- Escape hatch: declare `scope: ["."]` explicitly for a loop genuinely intended to run repo-wide. There is no other carve-out.

## Implementation Steps

1. Confirm [[BUG-3106]] has landed and `grep -L "^scope:"
   scripts/little_loops/loops/*.yaml` returns empty.
   > ⚠ Superseded — precondition check is non-recursive, misses loops/oracles/
2. Add `_validate_missing_scope` to `fsm/validation/structural_rules.py`,
   wire into `validate_fsm()`, export from `fsm/validation/__init__.py`'s
   `__all__`.
3. Add tests to `scripts/tests/test_fsm_validation_structural.py`
   (`TestRequiredInputsValidation`-style, line 1539 for pattern): trigger
   case (no `scope:`), non-trigger case (`scope:` present), non-trigger case
   for `scope: ["."]` specifically, and a `..._wired_into_validate_fsm`
   variant.
4. Enroll the new "no-scope" category in `test_builtin_loops.py`'s
   deterministic warning-category ratchet (`TestValidatorWarningBudget`,
   `CATEGORY_PATTERNS` dict) with one new `"no-scope": "<substring>"` entry.
5. Add `test_all_have_scope_field` to
   `test_builtin_loops.py::TestBuiltinLoopFiles`, modeled on
   `test_all_have_description_field` (lines 100-118): iterate the
   `builtin_loops` fixture, call `load_and_validate`, assert both
   `fsm.scope` truthy and no matching WARNING.
   > ⚠ Superseded — builtin_loops fixture is recursive, hits 12 unscoped loops/oracles/*.yaml
6. Update `scripts/tests/test_ll_loop_commands.py::TestCmdValidate::test_validate_json_output_valid_loop` —
   its `valid-loop.yaml` fixture (lives in a tmp dir, not
   `scripts/little_loops/loops/`) has no `scope:` and asserts `violations ==
   []`; this breaks once the rule ships. Add `scope:` to the fixture or
   update the assertion.
7. Verify `cmd_validate()` surfaces the WARNING in both plain-text and
   `--json` output (no code change expected, confirm by running
   `ll-loop validate` against an unscoped test fixture).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Widen Implementation Step 1's precondition check to be recursive
  (`grep -rL "^scope:" scripts/little_loops/loops/` or equivalent) — the
  non-recursive glob misses `scripts/little_loops/loops/oracles/`.
- Resolve `scripts/little_loops/loops/oracles/*.yaml` (12 files, all
  `visibility: internal`, all runnable, none declare `scope:`; not touched
  by [[BUG-3106]]): either backfill `scope:` on each (BUG-3106-style), or
  have `_validate_missing_scope` exempt `visibility: internal` loops, or add
  12 `ALLOWLIST[(stem, "no-scope")]` entries in
  `test_builtin_loops.py::TestValidatorWarningBudget` mirroring the existing
  `("generator-evaluator-cli", "unreachable")` pattern (lines ~13504-13510).
  Whichever approach is chosen must keep `test_all_have_scope_field` (Step
  5) and the `"no-scope"` `CATEGORY_PATTERNS` ratchet entry (Step 4)
  passing without the finding count starting at 12 instead of ~0.
- Add a "no-scope (WARNING)" bullet to `docs/reference/CLI.md:786-813`'s
  enumerated `ll-loop validate` rule list.

## Impact

- **Severity**: without this, a newly authored loop can silently regrow the
  problem BUG-3106 just fixed.
- **Blast radius**: ~25-line lint rule plus tests. No runtime code paths
  change — `ll-loop validate` never gates `ll-loop run`.

## Status

open


## Session Log
- `/ll:manage-issue` - 2026-08-08T14:05:05 - `445807af-0feb-40fb-a339-375eea670ef7.jsonl`
- `/ll:ready-issue` - 2026-08-08T13:44:59 - `011c7f56-09ff-4657-b333-6da1d8cd6def.jsonl`
- `/ll:confidence-check` - 2026-08-08T13:40:57 - `9c830d31-3eaf-456d-9ca9-ef100573c66b.jsonl`
- `/ll:verify-issues` - 2026-08-08T13:38:38 - `40362678-df6a-4882-8c0f-055e1ceb99bf.jsonl`
- `/ll:wire-issue` - 2026-08-08T13:36:17 - `04be62d9-6adb-4a6b-94b0-f3940dc14295.jsonl`
- `/ll:refine-issue` - 2026-08-08T13:25:07 - `20d858e8-c130-4bb0-ab5d-7e9fedf6de5f.jsonl`
- `/ll:issue-size-review` - 2026-08-08T12:31:14 - `252cabd4-42b7-43f3-becc-2330b53bf3d0.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-08-08
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/validation/structural_rules.py`: added `_validate_missing_scope()`, wired into `validate_fsm()`
- `scripts/little_loops/fsm/validation/__init__.py`: exported `_validate_missing_scope` (import block + `__all__`)
- `scripts/tests/test_fsm_validation_structural.py`: added `TestMissingScopeValidation` (trigger, non-trigger, `scope: ["."]` non-trigger, wired-into-validate_fsm x2)
- `scripts/tests/test_builtin_loops.py`: added `"no-scope"` to `CATEGORY_PATTERNS`; allowlisted the 12 `loops/oracles/*.yaml` sub-loops (internal, predate BUG-3106's scope backfill) in both the ratchet `ALLOWLIST` and the new `test_all_have_scope_field`
- `scripts/tests/test_ll_loop_commands.py`: added `scope: ["."]` to `test_validate_json_output_valid_loop`'s inline fixture
- `scripts/tests/fixtures/fsm/valid-loop.yaml`: added `scope: ["."]` (fixed `test_fsm_schema.py::test_load_valid_yaml`'s `warnings == []` assertion)
- `docs/reference/CLI.md`: documented the new "No-scope (WARNING)" rule in the `ll-loop validate` rule list

### Deferred (not in scope for this issue)
- The 12 `loops/oracles/*.yaml` sub-loops still lack a real per-file `scope:`; they're allowlisted rather than backfilled, since assigning an accurate scope to each requires the same per-loop audit BUG-3106 did for the other 78 loops. Follow-up left open.
- `skills/create-loop/reference.md:631` and `skills/create-loop/loop-types.md` scaffold snippets still describe `scope:` as optional — owned by BUG-3108.

### Verification Results
- Tests: PASS (18660 passed, 42 skipped)
- Lint: PASS (no new findings on touched files; pre-existing `test_builtin_loops.py` import-sort drift predates this change)
- Types: not run (not part of configured verification for this change)
