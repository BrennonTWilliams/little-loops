---
id: ENH-2348
title: Add ll-loop validate lint for unescaped ${ns.path:-default} bash-default interpolation
type: ENH
status: open
priority: P2
captured_at: '2026-06-27T21:16:24Z'
discovered_date: '2026-06-27'
discovered_by: capture-issue
labels:
- loops
- fsm
- validation
- linting
relates_to:
- BUG-2346
confidence_score: 100
outcome_confidence: 84
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2348: Add validation lint for unescaped ${ns.path:-default} interpolation

## Summary

Add a static validation rule (surfaced by `ll-loop validate`, implemented in
`scripts/little_loops/fsm/validation.py`) that flags FSM action strings containing an
unescaped `${namespace.path:-...}` — bash parameter-expansion default syntax that the FSM
interpolator does not support. The message should point authors at the two supported forms:
`${namespace.path:default=...}` (engine-native default) or `$${VAR:-...}` (escaped, handled
by the shell).

## Motivation

BUG-2346 shipped 7 instances of this exact pattern across two builtin loops, one of which
(`recursive-refine.yaml:50`) made the loop dead-on-arrival for ~2 weeks. The interpolation
engine already special-cases `:default=` (`validation.py:128`) and the test suite documents
the trap (`test_fsm_interpolation.py:221,364`), yet `ll-loop validate` had no gate to catch
authors mixing bash `:-` into an interpolated `${context.X}` token. This is the
"shift the gate left" pattern already used for the meta-loop rules (MR-1..MR-6) in
`.claude/CLAUDE.md`.

## Current Behavior

`ll-loop validate` validates `:default=` defaults but has no rule for the unsupported
`${ns.path:-...}` form. A loop author can write `${context.order:-queue}`, pass validation,
and only discover the crash at runtime as `Path 'order:-queue' not found in context`.

## Expected Behavior

`ll-loop validate <loop>` reports a finding (WARNING or ERROR) on any unescaped
`${namespace.path:-...}` occurrence, e.g.:

```
[ERROR] interpolation: ${context.order:-queue} uses unsupported bash ':-' default.
Use ${context.order:default=queue} (engine default) or $${ORDER:-queue} (shell, escaped).
  at recursive-refine.yaml:50 (state: parse_input)
```

## API / Interface

- New rule in `scripts/little_loops/fsm/validation.py`. Detect `${` + namespace.path + `:-`
  where the leading `$` is not doubled (`$${` is the legitimate escaped form and must be
  exempted). Reuse the existing `${...}` extraction the `:default=` check already uses.
- Choose severity: ERROR is defensible (the pattern always crashes at runtime), but WARNING
  is acceptable if there is concern about edge cases; recommend ERROR.

## Scope Boundaries

- Does not fix the BUG-2346 crash sites — those are BUG-2346's responsibility.
- Does not add bash `:-` default syntax support to the FSM interpolation engine.
- Does not validate other unsupported bash expansion forms (e.g. `${ns.path:+alt}`, `${ns.path:?err}`) — only the `:-` form is in scope.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_validate_bash_default_interpolation` function; register in `validate_fsm`
- `scripts/little_loops/fsm/schema.py` — add `bash_default_ok: bool = False` to `FSMLoop` suppress-flag block (lines 1002–1007); register in `from_dict` / serialization (lines 1077–1088, 1158–1163)
- `.claude/CLAUDE.md` — add `bash_default_ok: true` suppress-flag entry to the Loop Authoring section after the MR-6 block, following the exact format of existing MR-* entries
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — add new rule to the error taxonomy table; update heading range from `MR-1…MR-6` to `MR-1…MR-7` (or next assigned number)
- `docs/reference/CLI.md` — `#### ll-loop validate` section: add new bullet for the bash-default rule; extend the prose summary sentence that enumerates suppress flags
- `docs/reference/API.md` — `FSMLoop` dataclass block: add `bash_default_ok: bool = False` field with inline comment; `validate_fsm` bullet list: add new MR bullet
- `skills/review-loop/reference.md` — `## First-Pass Checks` table: add new MR row for the bash-default rule

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py` already called by `ll-loop validate` CLI entry point
- `scripts/little_loops/cli/loop/config_cmds.py:cmd_validate()` — actual CLI caller; calls `load_and_validate()` → `validate_fsm()`; no changes needed here

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — calls `load_and_validate()` at line 613; the new lint will also fire at `ll-loop run` time, not just `ll-loop validate`
- `scripts/little_loops/cli/loop/run.py` — calls `load_and_validate()` at line 99 (same; no changes needed)
- `scripts/little_loops/cli/loop/edit_routes.py` — calls `load_and_validate()` at lines 37, 51 (no changes needed)
- `scripts/little_loops/cli/loop/_helpers.py` — calls `load_and_validate()` at lines 883, 903 (no changes needed)
- `scripts/little_loops/fsm/__init__.py` — re-exports `ValidationError`, `ValidationSeverity`, `validate_fsm`, `load_and_validate` (no changes needed; confirming the export surface is stable)

### Similar Patterns
- `_validate_meta_loop_evaluation`, `_validate_artifact_isolation`, `_validate_partial_route_dead_end` in `validation.py` — follow the same add-function-register-in-validate_fsm pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_validate_artifact_isolation` (`validation.py:1346`) and its scanner helper `_find_shared_tmp_writes` (`validation.py:1305`) — canonical two-part pattern: decouple the `re.finditer` scanner from the rule function; follow this split for `_find_bash_default_tokens` + `_validate_bash_default_interpolation`
- `_validate_partial_route_dead_end` (`validation.py:1398`) — iterates `fsm.states.items()`, emits `ValidationError(message=..., path=f"states.{state_name}.action", severity=ValidationSeverity.ERROR)`
- `_unguarded_captured_refs` (`validation.py:120`) — covers only `${captured.*}` tokens via `_CAPTURED_REF_FULL_RE`; does NOT catch `${context.*:-...}` or other namespaces; the new rule fills this gap
- `validate_fsm()` (`validation.py:923`) insertion point: add `errors.extend(_validate_bash_default_interpolation(fsm))` after the `_validate_generator_fix_discipline(fsm)` call (last current MR-* rule)
- `KNOWN_TOP_LEVEL_KEYS` frozenset (`validation.py:149`) — `"bash_default_ok"` must be added here to prevent the "Unknown top-level key" warning when authors set it
- Module-level regex model: `_SHARED_TMP_PATH_RE = re.compile(...)` at `validation.py:106`; new rule should define `_BASH_DEFAULT_RE = re.compile(r"(?<!\$)\$\{[^}]*:-[^}]*\}")` analogously to match unescaped `${...:- ...}` tokens while the negative lookbehind exempts `$${`

### Tests
- `scripts/tests/test_fsm_validation.py` — primary: add coverage for flagged form, `:default=` exempt, `$${VAR:-x}` exempt; also update the import block (lines 24–42) to add `_validate_bash_default_interpolation`
- `scripts/tests/test_fsm_interpolation.py` — secondary: already documents the trap at lines 221, 364; may serve as fixture source

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — add `TestBashDefaultOk` class (3 tests: `true` round-trips, `False` omitted from dict, defaults-false) after `TestGeneratorFixOk` at line 3467; follows the exact same three-test pattern as `TestSharedStateOk`, `TestPartialRouteOk`, `TestMetaSelfEvalOk`, `TestGeneratorFixOk`
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdValidate` class (line 32): optionally add an integration test for the new rule following the `test_validate_with_unreachable_state_prints_warning` pattern (line 88)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `test_fsm_validation.py:TestMetaLoopValidation` (line 938) — test class + `_simple_fsm()` builder helper pattern to follow
- MR-3 block in `test_fsm_validation.py` (~line 1204) — four-test pattern per rule: fires, safe-form-exempt, suppressed-by-flag, end-to-end via `validate_fsm()`; also test `bash_default_ok` key recognized in `KNOWN_TOP_LEVEL_KEYS` via `load_and_validate()`
- `test_fsm_interpolation.py:test_nested_variable_syntax_raises_interpolation_error` (line 230) — runtime crash fixture (`${MAX_TOTAL:-${context.max_refine_count}}`); confirms what the lint rule prevents
- `test_fsm_interpolation.py:test_escape_bash_default_value` (line 363) — `$${DEPTH:-0}` safe form; must NOT be flagged
- Loop YAML end-to-end targets: `recursive-refine.yaml` (lines 50, 70, 71, 106, 275, 291) and `rl-coding-agent.yaml` (line 26) — 7 sites total; lint rule should fire before BUG-2346 fixes land and be clean after

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — **critical**: Loop Authoring section documents each MR-* rule with suppress flag; `bash_default_ok` entry is missing (see Files to Modify above)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — add to error taxonomy table (see Files to Modify above)
- `docs/reference/CLI.md` — `ll-loop validate` section needs new bullet (see Files to Modify above)
- `docs/reference/API.md` — `FSMLoop` field list and `validate_fsm` bullet list (see Files to Modify above)
- `skills/review-loop/reference.md` — First-Pass Checks table (see Files to Modify above)

### Configuration
- N/A

## Implementation Steps

1. Add a detector that scans every interpolated string field (actions, captures, etc.) for
   unescaped `${<ns>.<path>:-`.
2. Exempt `$${...}` (escaped) and `:default=` forms.
3. Emit a finding with file/line/state and the corrective hint.
4. Add tests covering: crashing form flagged, `:default=` not flagged, `$${VAR:-x}` not
   flagged.
5. Confirm it fires on the BUG-2346 sites before they are fixed, and is clean after.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete 5-step expansion:**

1. **Detector** — define `_BASH_DEFAULT_RE = re.compile(r"(?<!\$)\$\{[^}]*:-[^}]*\}")` at module level in `validation.py`. Primary field to scan: `state.action` (covers all 7 BUG-2346 crash sites). Also scan `state.evaluate.source` for completeness (pattern from `_validate_capture_reachability`).

2. **Exempt forms** — the negative lookbehind `(?<!\$)` in the regex handles `$${VAR:-x}` at regex-match time. The `:default=` form (`${context.X:default=Y}`) never contains `:-` so it is automatically exempt.

3. **Emit finding** — use `ValidationError(message=f"[state: {state_name}] ...", path=f"states.{state_name}.action", severity=ValidationSeverity.ERROR)`. Message must name the matched token and give both corrective forms: `${ns.path:default=Y}` (engine) and `$${VAR:-Y}` (shell escape).

4. **Register suppress flag in 3 locations:**
   - `KNOWN_TOP_LEVEL_KEYS` frozenset in `validation.py` (line 149): add `"bash_default_ok"`
   - `FSMLoop` dataclass in `schema.py` (lines 1002–1007): add `bash_default_ok: bool = False`
   - `FSMLoop.from_dict` / serialization in `schema.py` (lines 1077–1088, 1158–1163): include `bash_default_ok`
   - Add `errors.extend(_validate_bash_default_interpolation(fsm))` to `validate_fsm()` after `_validate_generator_fix_discipline(fsm)` call

5. **Test targets** — use `recursive-refine.yaml` lines 50, 70, 71, 106, 275, 291 and `rl-coding-agent.yaml` line 26 for the end-to-end "fires before BUG-2346 fix / clean after" test

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `TestBashDefaultOk` to `scripts/tests/test_fsm_schema.py` after `TestGeneratorFixOk` (line 3467) — 3 tests: `true` round-trips, `False` omitted from `to_dict()`, defaults-false via `from_dict()`
7. Update `.claude/CLAUDE.md` — add `bash_default_ok: true` paragraph to the Loop Authoring section after the MR-6 block, following the format of existing MR-* entries (e.g. `ll-loop validate enforces rule N as ERROR severity. ... Set bash_default_ok: true to suppress. See ENH-2348.`)
8. Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — extend the design rules heading (`MR-1…MR-6` → `MR-1…MR-7`) and add a new table row for the bash-default rule
9. Update `docs/reference/CLI.md` — `#### ll-loop validate` section: add new bullet; extend suppress-flag summary sentence
10. Update `docs/reference/API.md` — `FSMLoop` dataclass block: add `bash_default_ok: bool = False # Suppress MR-7 bash-default interpolation lint rule (ENH-2348)`; `validate_fsm` bullet list: add new MR entry
11. Update `skills/review-loop/reference.md` — `## First-Pass Checks` table: add new MR row after MR-5

## Acceptance Criteria

- [ ] `ll-loop validate` flags `${context.X:-default}` with a corrective message.
- [ ] `$${VAR:-default}` and `${context.X:default=Y}` are not flagged.
- [ ] Tests cover flagged and exempt forms.
- [ ] Rule documented alongside the existing validation rules.

## Impact

- **Priority**: P2 — prevents a class of runtime crash; not P1 because BUG-2346 fixes the immediate live instances
- **Effort**: Small — reuses existing `${...}` extraction in `validation.py`; ~30–50 lines following established MR-* rule pattern
- **Risk**: Low — additive lint rule only; no changes to FSM runtime behavior
- **Breaking Change**: No

## Session Log
- `/ll:confidence-check` - 2026-06-27T22:00:00 - `5f815bfb-e7ec-4c41-8d88-81417a5bf1fe.jsonl`
- `/ll:wire-issue` - 2026-06-27T21:45:57 - `0aa50755-d2cd-4dbe-a456-f77a9a6fedf8.jsonl`
- `/ll:refine-issue` - 2026-06-27T21:31:57 - `a4e8f246-4b58-4fda-8b36-7c2676ca8027.jsonl`
- `/ll:format-issue` - 2026-06-27T21:21:46 - `fb662259-f1c0-459f-aa52-a7924d973eb2.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md

---

## Status

**Open** | Created: 2026-06-27 | Priority: P2
