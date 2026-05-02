---
captured_at: "2026-05-01T18:15:00Z"
discovered_date: "2026-05-01"
discovered_by: capture-issue
---

# FEAT-1311: Typed Parameter Contract for Sub-Loop Calls

## Summary

Add a top-level `parameters:` block to loop YAML (declares the loop's public contract) and a per-call `with:` block on states that invoke sub-loops via `loop:` (binds parent values to declared parameters). Replaces today's all-or-nothing `context_passthrough` with explicit, validated, named bindings.

## Current Behavior

A state invokes a sub-loop with `loop: <name>` plus an optional `context_passthrough: true`. When passthrough is on, the parent's entire context dict (plus extracted capture outputs) is merged into the child's context (`scripts/little_loops/fsm/executor.py:417-425`). When passthrough is off, the child runs with no parent context at all. There is no per-call named-parameter binding, no declaration of what context keys a child loop expects, and no validation that callers actually supply them. A child silently sees whatever keys happen to exist in the parent — or nothing.

## Expected Behavior

Loop YAML accepts an optional top-level `parameters:` block declaring typed inputs (name, type, required/default, description). States that set `loop:` accept an optional `with:` block that binds parent expressions to declared parameter names. The loader and validator (`scripts/little_loops/fsm/schema.py`, `scripts/little_loops/fsm/validation.py`) check that:

- All `required: true` parameters are bound in `with:` (or supplied via `--context` at the top level).
- No `with:` keys reference parameters not declared by the child.
- Bound values pass type validation at load time when statically known, and at runtime after interpolation when not.

At runtime, `_execute_sub_loop` populates the child context with only the resolved `with:` values (plus declared defaults), instead of bulk-copying the parent context. `context_passthrough: true` remains as a legacy escape hatch but is mutually exclusive with `with:` on the same state.

## Motivation

`context_passthrough` is a real ergonomics wart in the current loop catalog: many sub-loops only need one or two values from the parent, but the only way to share them is to leak the entire context. That couples child loops to the parent's variable names, makes refactors silently dangerous (rename a context key in the parent → child stops working with no error), and prevents `/ll:review-loop` and `ll-loop validate` from ever flagging missing or extra inputs.

Loop-viz FEAT-553 (typed parameter form on `SubLoopRefNode`) is also blocked on this. Their issue assumes a `with:` block already exists in loop YAML; it does not. Without a runtime contract here, loop-viz cannot ship a typed form — any UI it builds would write YAML the runtime ignores. Shipping the contract in little-loops unblocks loop-viz and improves CLI ergonomics independently.

## Use Case

A user writes a reusable `analyze-pr-review` loop that needs a PR number and a base branch. They declare its contract once at the top:

```yaml
name: analyze-pr-review
parameters:
  pr_number:
    type: integer
    required: true
    description: GitHub PR number to review
  branch:
    type: string
    default: main
    description: Base branch for diff
  strict_mode:
    type: boolean
    default: false
    description: Fail loop if any reviewer requests changes
states:
  fetch:
    ...
```

A parent loop calls it with explicit bindings:

```yaml
- name: review_pr
  loop: analyze-pr-review
  with:
    pr_number: ${context.target_pr}
    branch: main
    # strict_mode omitted → uses declared default
  on_yes: done
  on_no: failed
```

`ll-loop validate` flags a missing `pr_number` binding or a typo like `with: { pr_numbr: 7 }` at load time, not at runtime.

## Proposed Solution

Add `parameters:` to the top-level loop YAML schema and `with:` to the state schema (the latter only valid when `loop:` is set). At load time, `load_and_validate` parses the parameter contract and verifies every state's `with:` block against the referenced child loop's schema. At runtime, `_execute_sub_loop` populates `child_fsm.context` with only the resolved `with:` values plus declared defaults, instead of bulk-copying the parent context.

`context_passthrough: true` remains a legacy escape hatch with unchanged semantics, but is mutually exclusive with `with:` on the same state (load-time error). See **API/Interface** below for the schema model and field semantics, and **Implementation Steps** for the staged rollout.

## API/Interface

**New top-level YAML field:**

- `parameters: { <name>: { type, required?, default?, description?, values? } }` — declares the loop's public input contract. Supported `type` values (v1): `string`, `integer`, `number`, `boolean`, `enum` (with `values: [...]`), `path`. Flat schema only — no nested objects in v1.

**New state field (only valid when `loop:` is set):**

- `with: { <param-name>: <expression> }` — binds parent expressions (interpolation strings, literals) to the child's declared parameter names. Mutually exclusive with `context_passthrough` on the same state.

**Schema model (`scripts/little_loops/fsm/schema.py`):**

- New `ParameterSpec` dataclass: `name`, `type`, `required: bool`, `default: Any | None`, `description: str | None`, `values: list[Any] | None` (for `enum`). Model after existing `EvaluateConfig` (`schema.py:24-141`) or `RouteConfig` (`schema.py:144-178`) — both demonstrate the codebase's `to_dict`/`from_dict` round-trip convention.
- The top-level loop dataclass is `FSMLoop` (`schema.py:524-641`, NOT "FSMConfig"). Add `parameters: dict[str, ParameterSpec] = field(default_factory=dict)` alongside the existing `context: dict[str, Any]` field at line 548. Wire into both `to_dict` (omit when empty, like the existing `if self.context:` guard at 572-573) and `from_dict` (parse via `{name: ParameterSpec.from_dict(spec) for name, spec in data.get("parameters", {}).items()}`).
- `StateConfig` (`schema.py:180-376`) grows `with: dict[str, Any] = field(default_factory=dict)` next to `context_passthrough` (line 253). Serialize at 306-309 alongside `loop`/`context_passthrough`. Deserialize at 371-372. **Note**: `with` is a Python reserved word — the dataclass field will need a safe attribute name (e.g., `with_`, then alias on the dict round-trip), or use `__annotations__` patching.

**Runtime (`scripts/little_loops/fsm/executor.py:_execute_sub_loop`, lines 400-473):**

- The bulk-copy lives at lines 417-425 (the `if state.context_passthrough:` block that builds `captured_as_context` and merges into `child_fsm.context`). Add a sibling `elif state.with:` branch immediately before it.
- Use `interpolate_dict(state.with, ctx)` from `scripts/little_loops/fsm/interpolation.py:209` to resolve `${context.foo}`-style values against the parent's `InterpolationContext`. The `ctx` parameter is already passed to `_execute_sub_loop` (line 400 signature).
- Validate the resolved dict against the child's `parameters` schema (apply defaults for unbound optional params, type-check each value), then assign `child_fsm.context = resolved` (no merge with parent — only declared keys reach the child).
- Note the captures merge-back at lines 456-457 (`if state.context_passthrough and child_executor.captured:`) — decide whether `with`-bound calls also merge child captures back into the parent (recommend yes, mirror existing behavior).
- Setting both `with` and `context_passthrough: true` on the same state raises a load-time error in `validation.py`, not at runtime.

**JSON Schema (`scripts/little_loops/fsm/fsm-loop-schema.json`):**

- Add `parameters` to top-level loop schema.
- Add `with` to state schema, conditionally allowed when `loop` is present.

## Implementation Steps

1. Extend `schema.py`: add `ParameterSpec` dataclass (model after `EvaluateConfig` at `schema.py:24-141`); add `parameters: dict[str, ParameterSpec]` to `FSMLoop` (`schema.py:524-641`); add `with` to `StateConfig` (`schema.py:180-376`) — see API/Interface for the Python-keyword aliasing concern; round-trip via `from_dict`/`to_dict`.
2. Extend `validation.py`: add `_validate_parameters` and `_validate_state_with` helpers that follow the `_validate_state_action` (`validation.py:196`) and `_validate_state_routing` (`validation.py:231`) patterns — return `list[ValidationError]`, call from `validate_fsm` (`validation.py:373-485`) inside the per-state loop at lines 412-434. Validate parameter type names, duplicate names, default-vs-required conflicts; for each state with `loop:` set, resolve the child via `resolve_loop_path` + `load_and_validate` and check `with:` keys exist + statically-checkable types match.
3. Update `_execute_sub_loop` (`executor.py:400-473`): add `elif state.with:` branch before the existing `if state.context_passthrough:` block at lines 417-425; call `interpolate_dict(state.with, ctx)` (`fsm/interpolation.py:209`), validate against child's `parameters`, assign `child_fsm.context = resolved` (no merge). Cross-check the captures merge-back at lines 456-457 for consistency.
4. Update `fsm-loop-schema.json`: add top-level `parameters` property; add `with` to the state schema next to the existing `context_passthrough` entry at `fsm-loop-schema.json:293-297` (model after how `loop` and `context_passthrough` are declared inline in `properties`).
5. Surface validation in `/ll:review-loop` (`skills/review-loop/SKILL.md`) and `ll-loop validate` — the CLI handler is `cmd_validate` in `scripts/little_loops/cli/loop/config_cmds.py:11`, registered at `scripts/little_loops/cli/loop/__init__.py:178,376` (NOT `ll_loop.py` — that path does not exist). Errors must include the offending state name and parameter; the existing `ValidationError(message=..., path=f"states.{state_name}")` convention (`validation.py:419-424`) is the model.
6. Pick 1–2 existing loops in `scripts/little_loops/loops/` and migrate as proof-of-value (recommended: `auto-refine-and-implement.yaml:43`, `autodev.yaml:100`). Defer the full sweep — there are 11 active passthrough sites (see Integration Map → Similar Patterns for the complete list).
7. Update docs: `docs/generalized-fsm-loop.md:202-218` (replace bulk passthrough description), `docs/reference/API.md:3845`, `scripts/little_loops/loops/README.md:160-165`, `skills/create-loop/reference.md:692,707`, and `docs/guides/EXAMPLES_MINING_GUIDE.md` (multiple references — see Integration Map for line numbers).
8. Tests in `scripts/tests/` (flat layout — there is NO `scripts/tests/fsm/` directory): extend `test_fsm_schema.py` (parameters/with parse/round-trip — model after the `context_passthrough` test cluster at lines 1837-1877), `test_fsm_validation.py` (missing-required, unknown-key, type-mismatch, `with` + `context_passthrough` rejected), `test_fsm_executor.py` (with-binding at runtime, defaults applied, no-parent-leak — extend the sub-loop test cluster at lines 3756-3909+ which already includes `test_sub_loop_context_passthrough` at line 3875 as the model).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `ParameterSpec` dataclass; extend the top-level loop dataclass with `parameters: dict[str, ParameterSpec]`; extend `StateConfig` with `with: dict[str, Any]`; ensure `from_dict`/`to_dict` round-trip cleanly
- `scripts/little_loops/fsm/validation.py` — `load_and_validate`: parse the `parameters:` block (unknown types, duplicate names, default-vs-required conflicts); for each state with `loop:` set, resolve the child loop's schema and validate `with:` keys + statically-checkable types
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop` (around lines 400–425): when `state.with` is set, interpolate each value and seed `child_fsm.context` with declared parameters + defaults; raise on `with` + `context_passthrough` together
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `parameters` to top-level loop schema; add `with` to state schema, conditionally allowed when `loop` is present
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — migrate from `context_passthrough: true` to explicit `parameters:` + `with:` (proof-of-value)
- `scripts/little_loops/loops/autodev.yaml` — migrate from `context_passthrough: true` to explicit `parameters:` + `with:` (proof-of-value)

### Dependent Files (Callers/Importers)
- `skills/review-loop/SKILL.md` — surface new validation errors (required-but-unbound, unknown-with-key, type mismatch) with state name + parameter
- `scripts/little_loops/cli/loop/config_cmds.py:11` (`cmd_validate`) — CLI handler that runs `load_and_validate` and prints errors; new validation errors flow through here automatically
- `scripts/little_loops/cli/loop/__init__.py:178,376` — `validate` subcommand parser registration and dispatch (the `ll-loop validate` entry point)

### Similar Patterns
- All other loops in `scripts/little_loops/loops/` currently using `context_passthrough: true` — survey for follow-up migrations once the contract ships
- FEAT-1308 (Loop YAML template inheritance via `from:`) — adjacent loader/schema work; both touch top-level loop YAML structure and must agree on the canonical states form

### Tests
- `scripts/tests/test_fsm_schema.py` — extend the `context_passthrough` test cluster at lines 1837-1877 with parallel cases for `parameters:` parse/validate (all v1 types + `enum` + `path`), `with:` parse/round-trip, and `to_dict`/`from_dict` symmetry
- `scripts/tests/test_fsm_validation.py` — new tests: missing-required failure, unknown-with-key failure, statically-detectable type mismatch, `with` + `context_passthrough` rejected at load time
- `scripts/tests/test_fsm_executor.py` — extend the sub-loop test cluster at lines 3756-3909+ (model after `test_sub_loop_context_passthrough` at line 3875): `with:` runtime binding + interpolation, declared defaults applied, child sees only declared keys (no parent leak)
- **Note**: the issue originally referenced `scripts/tests/fsm/` — that directory does not exist. The repo uses a flat `scripts/tests/test_fsm_*.py` layout
- Existing FSM executor and validation tests must still pass — verify graceful degradation: loops without `parameters:`/`with:` behave identically; legacy `context_passthrough` path unchanged

### Documentation
- `docs/ARCHITECTURE.md` — sub-loop execution model: replace bulk passthrough description with the typed contract
- `docs/reference/API.md:3845` — schema reference; the existing `context_passthrough=True` example needs to be paired with a `with:` example
- `docs/generalized-fsm-loop.md:202-218` — the loops guide; currently has the canonical `context_passthrough` description (lines 215-218); rewrite to lead with the typed contract and demote bulk passthrough to a legacy escape hatch
- `docs/guides/EXAMPLES_MINING_GUIDE.md` — references `context_passthrough: true` at lines 81, 241, 249, 516, 599 — update the example walkthrough to use `parameters:` + `with:` and re-explain how the inner-loop inputs are bound
- `scripts/little_loops/loops/README.md:160-165` — sub-loop schema snippet shows `context_passthrough` and points to `skills/create-loop/reference.md` for full docs; update both
- `skills/create-loop/reference.md:692,707` — the documented sub-loop example uses `context_passthrough: true`; needs the typed-contract version and a deprecation note

### Configuration
- N/A — `parameters:` and `with:` are additive, opt-in YAML fields with no settings, env vars, or runtime config knobs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Top-level loop dataclass is `FSMLoop`, not "FSMConfig"** (`scripts/little_loops/fsm/schema.py:524-641`). The original draft of this issue used a placeholder name; the actual dataclass already owns `context: dict[str, Any]` (line 548) and is the right place for `parameters: dict[str, ParameterSpec]`.

**Existing dataclass round-trip patterns to model `ParameterSpec` after**:
- `EvaluateConfig` (`schema.py:24-141`) — biggest precedent for a sub-component dataclass with `to_dict`/`from_dict`, optional fields, and field-presence guards in serialization
- `RouteConfig` (`schema.py:144-178`) — simpler example, closer in shape to `ParameterSpec` (small, all-optional fields)
- Neither maps a Python keyword to a YAML key, so the `with:` field on `StateConfig` is the only place needing keyword aliasing — store as `with_` (or use a `__getattr__` shim) and translate on `to_dict`/`from_dict`

**Validation pattern to model new helpers after**: `_validate_state_action` (`validation.py:196-228`) and `_validate_state_routing` (`validation.py:231-370`) are both pure helpers returning `list[ValidationError]`, called from inside the per-state loop in `validate_fsm` at `validation.py:412-434`. New `_validate_state_with(state_name, state, child_loop)` follows the same shape. `ValidationError` carries `message`, `path` (`f"states.{state_name}.with.{param}"` is the natural extension), and `severity`.

**Interpolation API is already importable**: `_execute_sub_loop` already has `ctx: InterpolationContext` (`executor.py:400`); `interpolate(template, ctx)` and `interpolate_dict(obj, ctx)` from `fsm/interpolation.py:169,209` are used throughout the executor (e.g., `executor.py:615` for `params`). Drop-in for resolving `with:` values.

**No pre-existing `ParameterSpec`-like infrastructure** — searched `fsm/`, `cli/`, and the broader package. Greenfield addition; no risk of name collision or pattern divergence.

**Full inventory of loops using `context_passthrough: true`** (11 active sites — issue listed 2):
- `eval-driven-development.yaml:86`
- `sprint-refine-and-implement.yaml:52`
- `autodev.yaml:100`
- `issue-refinement.yaml:30`
- `recursive-refine.yaml:97`
- `greenfield-builder.yaml:163,180` (two states)
- `sprint-build-and-validate.yaml:118`
- `examples-miner.yaml:138`
- `prompt-regression-test.yaml:91`
- `auto-refine-and-implement.yaml:43`
- `oracles/oracle-capture-issue.yaml:13`

The sweep is bigger than the issue suggested but doesn't change the implementation plan — only a follow-up scope decision (full migration vs. leave as legacy).

**Existing sub-loop test coverage to extend** (not write fresh):
- `scripts/tests/test_fsm_executor.py:3756-3909+` — 7+ existing `test_sub_loop_*` cases including `test_sub_loop_context_passthrough` at line 3875 and `test_sub_loop_context_passthrough_captured_values` at line 3909. Mirror the fixture/assertion shape for new `with:`-binding tests.
- `scripts/tests/test_fsm_schema.py:1837-1877` — `context_passthrough` parse/serialize/round-trip cluster. Add parallel cases for `parameters:` and `with:` here.

**JSON Schema slot-in location**: `fsm-loop-schema.json:289-297` shows `loop` and `context_passthrough` declared inline in the state `properties`; add `with` immediately after `context_passthrough` (line 297). Top-level `parameters` slots into the loop-level `properties` block (separate top-level object — needs locating in the file but the pattern is the same as existing top-level fields like `context`, `scope`).

## Acceptance Criteria

- [ ] Loop YAML accepts a top-level `parameters:` block; types `string`, `integer`, `number`, `boolean`, `enum`, `path` parse correctly.
- [ ] States with `loop:` set accept a `with:` block; values are interpolated and bound to declared parameter names at runtime.
- [ ] `ll-loop validate` reports required-but-unbound, unknown-with-key, and statically-detectable type mismatches with the state name and parameter in the error message.
- [ ] At runtime, a child loop invoked with `with:` sees only declared parameters + defaults in its context — no bulk copy of the parent.
- [ ] `with:` and `context_passthrough: true` on the same state produce a load-time validation error.
- [ ] Existing loops without `parameters:` or `with:` behave identically (graceful degradation; `context_passthrough` legacy path unchanged).
- [ ] `fsm-loop-schema.json` reflects the new fields so external consumers (loop-viz) can read the contract.
- [ ] At least one existing loop is migrated to `parameters:` + `with:` and passes existing tests.

## Impact

- **Priority**: P3 — Quality-of-life + unblocks loop-viz FEAT-553. No current loop is broken without it; `context_passthrough` keeps working.
- **Effort**: Medium — Schema + validation + runtime + JSON Schema + docs + 1 migration.
- **Risk**: Medium — Touches the sub-loop execution path. Mitigated by keeping `context_passthrough` legacy behavior intact and adding `with` as an additive opt-in.
- **Breaking Change**: No — `parameters:` and `with:` are opt-in. `context_passthrough` semantics unchanged.

## Open Questions

- Should top-level `--context KEY=VALUE` CLI args validate against `parameters:` when the entry-point loop declares one? (Probably yes, but worth deciding before shipping.)
- Should `path` type resolve relative to the loop file, the cwd, or be left as a raw string? Suggest raw string in v1 with documentation.
- When a child loop declares `parameters:` and a parent uses `context_passthrough: true` (no `with:`), should we (a) silently filter the passed context to declared keys, (b) pass everything as today, or (c) emit a deprecation warning? Suggest (c) for one release, then (a).
- Do we want a `parameters.<name>.examples` field for documentation/UX (loop-viz form placeholder hints), or defer to v2?

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM loop architecture — sub-loop execution model |
| `docs/reference/API.md` | Schema reference — `parameters` and `with` need to be documented here |
| `scripts/little_loops/fsm/fsm-loop-schema.json` | JSON Schema consumed by external editors (loop-viz) |

## Related Issues

- loop-viz FEAT-553 (Typed Parameter Schema for Sub-Loop References) — depends on this issue. Their UI cannot ship until the runtime contract exists.
- FEAT-1308 (Loop YAML template inheritance via `from:`) — adjacent loader/schema work; both touch loop YAML structure and should agree on the canonical states form.

## Labels

feature, loops, fsm, yaml, schema, validation, sub-loops, captured

## Session Log
- `/ll:refine-issue` - 2026-05-01T21:01:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a85844e-e09f-4359-8f57-686145624246.jsonl`
- `/ll:format-issue` - 2026-05-01T19:35:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0346db4-b5ff-485c-99bb-b9d802871bf0.jsonl`
- `/ll:capture-issue` - 2026-05-01T18:15:00Z - captured during review of loop-viz FEAT-553; runtime gap identified (no `with:` block exists today; `context_passthrough` is all-or-nothing)

---

## Status

**Open** | Created: 2026-05-01 | Priority: P3
