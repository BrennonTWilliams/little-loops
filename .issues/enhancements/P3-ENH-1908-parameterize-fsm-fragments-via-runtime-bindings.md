---
id: ENH-1908
type: ENH
priority: P3
status: open
captured_at: "2026-06-03T20:51:54Z"
discovered_date: "2026-06-03"
discovered_by: capture-issue
labels: [fsm, fragments, loops, dx]
---

# ENH-1908: Parameterize FSM fragments via runtime params/with bindings

## Summary

FSM shared-state fragments (`scripts/little_loops/loops/lib/*.yaml`) have no
parameterization contract. They are pure YAML mixins resolved at parse time by
`resolve_fragments` (`scripts/little_loops/fsm/fragments.py`) via deep-merge,
with values injected only through ad-hoc runtime `${context.X}` interpolation
documented in prose `description:` fields. There is no typed/required/default
parameter declaration and no validation that a caller supplied the values a
fragment needs — so fragments like `retry_counter` silently misbehave when a
context key is unset, and two states using the same fragment collide on shared
context keys (e.g. `counter_key`).

Add a runtime parameterization mechanism for fragments by **reusing the existing
`ParameterSpec` + `with:` model** already used for sub-loops, rather than
inventing a parallel parse-time system.

## Current Behavior

A fragment "parameterizes" only two ways today, neither enforced:

1. **State-level key override (deep-merge).** A state supplies top-level fields
   (`action`, `on_yes`, `on_no`) that win over the fragment's. Works for direct
   fields; no contract.
2. **Runtime `${context.X}` interpolation.** For values spliced into the
   *interior* of a fragment-owned string (e.g. `retry_counter`'s
   `${context.max_retries}` in `evaluate.target`, or `ll_rubric_score`'s
   `${context.run_dir}`). The fragment hardcodes the placeholder and *hopes* the
   loop's `context:` block (or a runtime injection) defines it.

Failure modes:
- **Silent failure (no enforcement).** `retry_counter`'s `description` says
  "State must supply (via context interpolation): context.counter_key,
  context.max_retries" — but nothing checks it. A loop that forgets silently
  produces wrong behavior at runtime.
- **Cross-reference collision (no per-reference scoping).** Two states using
  `retry_counter` in one loop share `context.counter_key` → shared counter-file
  corruption (the same class of bug the MR-3 / `run_dir` isolation rules fight).
- **No defaults / types.** A fragment cannot declare `max_retries` defaults to 3
  or that it must be an integer.

## Expected Behavior

A fragment declares typed inputs and a reference binds them, with the contract
enforced at validation time and resolution deferred to runtime:

```yaml
# fragment def (lib/common.yaml)
retry_counter:
  parameters:
    counter_key: {type: string, required: true}
    max_retries: {type: integer, default: 3}
  action: |
    FILE=".loops/tmp/${param.counter_key}"
    N=$(cat "$FILE" 2>/dev/null || echo 0); N=$((N+1))
    printf '%s' "$N" > "$FILE"; echo "$N"
  action_type: shell
  evaluate: {type: output_numeric, operator: lt, target: "${param.max_retries}"}

# usage — two states, no collision, no loop-global context: pollution
lint_retry:
  fragment: retry_counter
  with: {counter_key: lint_retries, max_retries: 5}
  on_yes: lint
  on_no: give_up
```

- Missing required params → validation ERROR (not silent runtime failure).
- Each reference's `with:` bindings are scoped to that state's `${param.X}`
  namespace, so two references never collide.
- `ParameterSpec.default` supplies optional values; type is checked.
- Deep-merge override stays for plain state fields (`on_yes`, `action`); `with:`
  is only for values spliced into the fragment's interior. Two non-overlapping
  channels, each with one job.

## Motivation

Fragments have limited reuse value without a real parameter contract — the
current prose-only convention pushes the cost of every fragment's implicit
dependencies onto every caller, and the failures are silent. The sub-loop system
already solved this exact problem with `ParameterSpec` (`type`/`required`/
`default`/`enum values`) + `with:` bindings + three-layer validation
(`_validate_parameters`, `_validate_with_bindings`, runtime enforcement in
`_execute_sub_loop`). Extending that one model to fragments gives a single mental
model — *anything reusable declares `parameters:`; any reference binds via
`with:`* — instead of two parallel systems.

## Key design finding: resolution MUST be at runtime, not parse time

An initial design considered resolving fragment params at **parse time** (inside
`resolve_fragments`, substituting a `${param.X}` namespace and expanding it away
before the dataclass exists). An audit of every interpolation reference in every
`lib/*.yaml` fragment **disproves** that this is sufficient:

- `ll_rubric_score` interpolates `${context.run_dir}`. Per `.claude/CLAUDE.md`,
  **the runner injects `run_dir` as `.loops/runs/<loop>-<timestamp>/` at
  execution start** — it is constant for the loop instance but **not knowable
  when `resolve_fragments` runs**. A parse-time substitution would have nothing
  to substitute.
- `playwright_screenshot` (`file_url`, `screenshot_path`, typically derived from
  `run_dir`) and `ll_commit` (`commit_message`, typically generated) follow the
  same "constant-per-loop but runtime-only" pattern.
- `retry_counter` (`counter_key`, `max_retries`) and `ll_loop_run` (`loop_name`)
  are the only genuine parse-time constants.

So fragment params must resolve at **runtime** (when `run_dir`, `captured.*`,
etc. are all available). This one decision also means a naive parse-time
`requires:` validator would **false-positive on `run_dir`** (flag it "missing"
because it is runner-injected, not authored) — any validation must be
runtime-injection-aware or whitelist runner-injected vars.

Audit detail: no fragment *executable body* references `prev`/`result`/`state`/
`loop`/`env`/`messages`; only `context.*`. `captured.*` appears only in
`parse_tagged_json`'s prose (it deliberately ships no default `action`).

## Proposed Solution

Extend the runtime `parameters:` / `with:` model to fragment references:

1. Fragments may declare a top-level `parameters:` block per fragment, reusing
   the existing `ParameterSpec` dataclass (`schema.py`) verbatim.
2. A state's `fragment:` reference may carry a `with:` map binding those params
   (same keyword as sub-loop calls).
3. `resolve_fragments` merges the fragment body into the state (as today) and
   carries the `with:` bindings onto the resulting `StateConfig` (new field —
   **not** the existing `params:` field, which holds MCP tool args; use a
   distinct name e.g. `fragment_bindings`).
4. The executor exposes bindings as a `${param.X}` namespace in the per-state
   `InterpolationContext`, applying `ParameterSpec` defaults / required-checks /
   type validation at runtime (mirror `_execute_sub_loop` logic).
5. Add cross-validation (analogous to `_validate_with_bindings`) so unknown
   bindings and missing required params are caught at `load_and_validate`.

### Rejected alternatives

- **Parse-time-only `${param}` substitution** — rejected: cannot serve the
  `run_dir`/`file_url` class of runtime-injected per-loop constants (see finding
  above).
- **Validation-only `requires:` list** — rejected as insufficient: closes the
  silent-failure gap but delivers no actual parameterization (no per-reference
  scoping, no defaults), and false-positives on runner-injected vars.
- **Promote parameterized fragments to sub-loops** — rejected for single-state
  shapes: sub-loops are runtime black-box calls with their own executor frame /
  lifecycle / timeout, far too heavy for "a state with a hole," and cannot
  splice a single state inline into the parent's graph.

## Integration Map

- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments`: carry `with:`
  bindings onto state; keep deep-merge for plain fields.
- `scripts/little_loops/fsm/schema.py` — reuse `ParameterSpec`; add fragment
  `parameters:` parsing; add a `fragment_bindings` field to `StateConfig`
  (avoid collision with existing MCP `params`).
- `scripts/little_loops/fsm/interpolation.py` — add a `param` namespace to
  `InterpolationContext.resolve`.
- `scripts/little_loops/fsm/executor.py` — populate the `param` namespace per
  state in `_build_context`; apply defaults/required/type (mirror
  `_execute_sub_loop`, executor.py ~506-612).
- `scripts/little_loops/fsm/validation.py` — fragment-binding cross-validation
  analogous to `_validate_with_bindings`; teach it about runner-injected vars so
  it does not false-positive on `run_dir`.
- Migrate `retry_counter` and `ll_rubric_score` off bare `${context.X}` onto
  `${param.X}` as the proof cases; keep genuine runtime refs as runtime interp.

## Implementation Steps

1. Add fragment `parameters:` parsing (reuse `ParameterSpec`) and a
   `StateConfig.fragment_bindings` field.
2. Carry `with:` bindings through `resolve_fragments` onto the merged state.
3. Add the runtime `param` namespace to `InterpolationContext` + `_build_context`.
4. Apply defaults/required/type at runtime per state.
5. Add `load_and_validate` cross-validation for fragment bindings (runner-var
   aware).
6. Migrate `retry_counter` + `ll_rubric_score`; add tests covering: missing
   required → ERROR, default applied, two references no-collision, `run_dir`
   still resolves at runtime.

## Backwards Compatibility

Additive. Existing fragments using `${context.X}` keep working (context
interpolation is unchanged); `parameters:`/`with:` on fragments is opt-in.
Migrate fragments opportunistically.

## Success Metrics

- A fragment with a `required` param errors at validation when unbound (no
  silent runtime failure).
- Two states using `retry_counter` with distinct `counter_key` bindings do not
  share a counter file.
- `ll_rubric_score` migrated to `${param.run_dir}` still resolves at runtime.

## Scope Boundaries

- In: fragment `parameters:`/`with:`, runtime `param` namespace, validation,
  migration of `retry_counter` + `ll_rubric_score`.
- Out: changing the sub-loop param system; mutating the deep-merge override
  channel for plain fields; auto-migrating all fragments.

## Impact

Medium. Touches `fragments.py`, `schema.py`, `interpolation.py`, `executor.py`,
`validation.py` and the `lib/` fragment defs, but reuses existing dataclasses and
the interpolation engine, so net new surface is small.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Loop Authoring | Meta-loop / `run_dir` isolation rules; run_dir injection |
| `docs/reference/API.md` | `little_loops.fsm.*` module reference |

## Labels

fsm, fragments, loops, dx

## Session Log
- `/ll:capture-issue` - 2026-06-03T20:51:54Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1cd9a64-5656-4d3a-9168-942bbb1958da.jsonl`

## Status

open
