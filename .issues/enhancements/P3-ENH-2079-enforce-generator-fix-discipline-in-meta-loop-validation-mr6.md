---
id: ENH-2079
title: Enforce generator-fix discipline in meta-loop validation (MR-6)
type: ENH
priority: P3
status: done
captured_at: '2026-06-10T18:12:09Z'
completed_at: '2026-06-11T00:38:41Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
parent: EPIC-2087
confidence_score: 98
outcome_confidence: 87
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
decision_needed: false
---

# ENH-2079: Enforce generator-fix discipline in meta-loop validation (MR-6)

## Summary

Add MR-6 to `ll-loop validate`: detect hand-patching anti-patterns where a loop has a `shell`-type state that writes to the same file path as a non-shell (LLM-type) state in the same loop. Emit a WARNING suggesting the patch be moved into the generator action instead. Include a `generator_fix_ok: true` suppression flag for intentional post-processing cases. Document MR-6 in `CLAUDE.md` alongside MR-1 through MR-5.

## Current Behavior

`ll-loop validate` enforces rules MR-1 through MR-5 but does not detect the hand-patching anti-pattern. A loop that generates an artifact via an LLM-type state and then directly patches it via a `shell` state passes validation silently, producing fragile output that diverges from the generator on the next run.

## Expected Behavior

`ll-loop validate` emits a MR-6 WARNING when it detects a `shell`-type state writing to the same file path as a non-shell (LLM-driven) state in the same loop. The WARNING message recommends moving the patch into the generator action. A `generator_fix_ok: true` flag at the loop top-level suppresses the warning for intentional post-processing cases.

## Motivation

Meta-loops that generate YAML, issue files, or FSM states frequently hand-patch the emitted artifact rather than fixing the generation logic. Hand-patching creates fragile output that diverges from the generator on the next run, undermining iterative refinement. The stable approach is to fix the generator — the loop's action/transition rules — so every subsequent run produces correct output automatically.

## Proposed Solution

Add rule MR-6 to `ll-loop validate` as a new `_validate_generator_fix_discipline(fsm: FSMLoop) -> list[ValidationError]` function in `scripts/little_loops/fsm/validation.py`.

**Detection heuristic** (static, at validate time):

There is no `action_type: apply` in the FSM schema — "apply" is a conventional state name, not a distinct action type. The detection operates on action text across all states:

1. Scan all states for file path patterns in `state.action` text (same regex approach as MR-3/MR-5: extract `${context.run_dir}/...`, `${captured.<var>}/...`, and relative paths appearing after `>`, `>>`, `-i`, `tee`).
2. Build two sets:
   - `shell_targets`: paths found in states where `state.action_type == "shell"` or `state.action_type is None` and the action looks like a shell command
   - `generator_targets`: paths found in states where `state.action_type in ("prompt", "slash_command")` AND the action contains `yaml_state_editor`, `captures: [to_file:`, or similar LLM-output write markers
3. Flag the intersection of `shell_targets ∩ generator_targets` — same file path written by both a shell state and an LLM-generator state in the same loop.

**Suppression**: `generator_fix_ok: bool = False` at the FSM top-level, following the same pattern as `meta_self_eval_ok`, `shared_state_ok`, `partial_route_ok`, `artifact_versioning_ok`.

**Wiring**: Add `errors.extend(_validate_generator_fix_discipline(fsm))` at the end of the `validate_fsm()` call chain in `validation.py`, after `_validate_artifact_overwrite`.

Document the rule in `.claude/CLAUDE.md` under Loop Authoring alongside MR-1 through MR-5.

## Implementation Steps

1. **Add `generator_fix_ok` field to `FSMLoop`** in `scripts/little_loops/fsm/schema.py`:
   - Add `generator_fix_ok: bool = False` field to the `FSMLoop` dataclass (alongside `artifact_versioning_ok` at lines ~972–976)
   - Add `if self.generator_fix_ok: result["generator_fix_ok"] = self.generator_fix_ok` to `FSMLoop.to_dict()` (skip-if-default pattern)
   - Add `generator_fix_ok=data.get("generator_fix_ok", False)` to `FSMLoop.from_dict()`

2. **Register `generator_fix_ok` in `KNOWN_TOP_LEVEL_KEYS`** in `scripts/little_loops/fsm/validation.py` — add the string `"generator_fix_ok"` to the frozenset at lines ~122–159 (alongside existing suppression flag strings)

3. **Implement `_validate_generator_fix_discipline(fsm)`** in `scripts/little_loops/fsm/validation.py`:
   - Gate: `if fsm.generator_fix_ok or not _is_meta_loop(fsm): return []`
   - Scan `state.action` text for file-path patterns across all states; categorize by `action_type` into shell vs. generator sets
   - Flag intersection with `ValidationError(severity=ValidationSeverity.WARNING)` using ENH-2079 in the message

4. **Wire into `validate_fsm()`** — add `errors.extend(_validate_generator_fix_discipline(fsm))` after the `_validate_artifact_overwrite(fsm)` call

5. **Document MR-6** in `.claude/CLAUDE.md` under Loop Authoring (between `artifact_versioning_ok` and the `loop-specialist` rationale paragraph) — add entry with rationale and suppression flag documentation matching MR-3 through MR-5 style

6. **Add test cases** following the test class conventions for existing MR rules:
   - `TestGeneratorFixDiscipline` in `scripts/tests/test_fsm_validation.py` — positive control (detection fires), negative control (no overlap → no warning), suppression test (`generator_fix_ok: true`), and end-to-end via `validate_fsm()`
   - `TestGeneratorFixOk` in `scripts/tests/test_fsm_schema.py` — round-trip serialization: `True` round-trips, `False` is omitted from `to_dict()`, defaults `False` from `from_dict()`
   - `TestMR6BuiltinFalsePositives` in `scripts/tests/test_builtin_loops.py` — load `harness-optimize.yaml` (the only built-in loop with both LLM-generator and shell states writing to the same target) and verify no unexpected MR-6 warnings, or confirm it surfaces correctly and add `generator_fix_ok: true` to that loop YAML if appropriate

## Scope Boundaries

- **In scope**: Static detection at `ll-loop validate` time of shell-then-generator (or generator-then-shell) patterns targeting the same file path
- **Out of scope**: Runtime hand-patch detection during loop execution
- **Out of scope**: Detecting hand-patching across multiple loop runs (single-run analysis only)
- **Out of scope**: Automatic fix rewriting — WARNING with suggestion only
- **Out of scope**: Changes to existing loops that use the pattern (opt-in suppression via flag)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_validate_generator_fix_discipline()` function, add `"generator_fix_ok"` to `KNOWN_TOP_LEVEL_KEYS`, wire into `validate_fsm()` after `_validate_artifact_overwrite(fsm)` call
- `scripts/little_loops/fsm/schema.py` — add `generator_fix_ok: bool = False` to `FSMLoop` dataclass, update `to_dict()` and `from_dict()` (3 separate changes, all at lines ~972–1106)
- `.claude/CLAUDE.md` — Loop Authoring section; add MR-6 entry with rationale and suppression flag

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/config_cmds.py:cmd_validate` — the actual `ll-loop validate` CLI entry point; calls `load_and_validate()` and prints warnings with `⚠` prefix
- `scripts/little_loops/cli/loop/__init__.py:main` — registers the `validate` subparser and dispatches to `cmd_validate`
- `scripts/little_loops/loops/harness-optimize.yaml` — the primary built-in meta-loop that uses both `yaml_state_editor` LLM states and `action_type: shell` states; will surface new MR-6 warnings or need `generator_fix_ok: true`

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:_validate_artifact_isolation` — MR-3: scans `state.action` with `re.compile(r"\.loops/tmp/[\w./-]+")` — same regex-over-action-text approach for MR-6
- `scripts/little_loops/fsm/validation.py:_validate_artifact_overwrite` — MR-5: scans for path patterns in shell/None action_type states; gates on `fsm.artifact_versioning or fsm.artifact_versioning_ok`
- `scripts/little_loops/fsm/schema.py:FSMLoop` — existing suppression flags `meta_self_eval_ok`, `shared_state_ok`, `partial_route_ok`, `artifact_versioning`, `artifact_versioning_ok` — exact pattern for `generator_fix_ok` addition

### Tests
- `scripts/tests/test_fsm_validation.py` — primary test file for MR rule unit tests; contains `TestArtifactIsolation` (MR-3), `TestPartialRouteDeadEnd` (MR-4), `TestArtifactVersioning` (MR-5) — add `TestGeneratorFixDiscipline` (MR-6) following same structure
- `scripts/tests/test_fsm_schema.py` — suppression flag round-trip tests; contains `TestMetaSelfEvalOk`, `TestSharedStateOk`, `TestPartialRouteOk`, `TestFSMLoopArtifactVersioning` — add `TestGeneratorFixOk` following same 3-test structure
- `scripts/tests/test_builtin_loops.py` — builtin loop false-positive regression tests; contains `TestMR4BuiltinFalsePositives` for reference — add `TestMR6BuiltinFalsePositives`

### Documentation
- `.claude/CLAUDE.md` — Loop Authoring section; add MR-6 entry with rationale
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — may need a note on the generator-fix discipline pattern (optional)

### Configuration
- Loop YAML top-level: `generator_fix_ok: true` suppression flag

## Acceptance Criteria

- [ ] `ll-loop validate` emits MR-6 WARNING when hand-patch pattern is detected (shell state + generator state writing same file path)
- [ ] WARNING message suggests moving the fix into the generator action and cites ENH-2079
- [ ] `generator_fix_ok: true` suppresses the warning
- [ ] `generator_fix_ok` field round-trips correctly through `FSMLoop.to_dict()` / `from_dict()` and is omitted when `False`
- [ ] `"generator_fix_ok"` is in `KNOWN_TOP_LEVEL_KEYS` (no spurious "Unknown top-level key" warning when flag is used)
- [ ] `CLAUDE.md` Loop Authoring section documents MR-6 with rationale
- [ ] Tests cover detection, non-detection (no overlap), suppression, round-trip serialization, and builtin false-positive regression

## Impact

- **Priority**: P3 — Low-urgency quality guardrail; hand-patching creates fragility but is not immediately blocking existing work
- **Effort**: Small — New rule added to existing `ll-loop validate` framework; follows established MR-1–5 pattern
- **Risk**: Low — Warning-only; no behavior change to existing loops; suppression flag available for intentional cases
- **Breaking Change**: No

## Labels

`validation`, `meta-loop`, `ll-loop`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-10_

**Readiness Score**: 84/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 77/100 → MODERATE

### Concerns
- Integration Map names `validator.py` (does not exist); correct path is `scripts/little_loops/fsm/validation.py`
- `scripts/little_loops/fsm/schema.py` is missing from Files to Modify; `generator_fix_ok: bool = False` must be added there to match the pattern of all other suppression flags (`meta_self_eval_ok`, `shared_state_ok`, etc.)

## Resolution

Implemented `_validate_generator_fix_discipline()` in `validation.py` (MR-6). Added `generator_fix_ok: bool = False` to `FSMLoop` schema with round-trip serialization. Added `"generator_fix_ok"` to `KNOWN_TOP_LEVEL_KEYS`. Wired into `validate_fsm()`. Documented MR-6 in `CLAUDE.md`. 9 new tests added (5 validation, 3 schema round-trip, 1 builtin regression) — all pass.

## Session Log
- `/ll:refine-issue` - 2026-06-11T00:22:02 - `865e257e-5746-4658-8a3f-6556039a9f0a.jsonl`
- `/ll:format-issue` - 2026-06-10T23:21:55 - `f88b676e-8236-495f-ac95-b57f4e70e306.jsonl`
- `/ll:confidence-check` - 2026-06-10T23:30:00 - `28d844c1-ec8d-49fc-a9f7-c82575d13717.jsonl`
- `/ll:confidence-check` - 2026-06-10T18:49:00 - `43869ed9-0bb9-4101-b58e-1b7cae8cdcc4.jsonl`
- `/ll:manage-issue` - 2026-06-11T00:38:41 - implementation
