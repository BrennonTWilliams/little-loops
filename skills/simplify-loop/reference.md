# Simplify Loop — Reference

Detection algorithms, mapping tables, the behavior-preservation checklist, the
scope-resolution table, and the artifact schema for `/ll:simplify-loop`.

The two transforms map onto engine features that already exist:

- **`flow:`** — Linear Flow Shorthand expanded by
  `resolve_flow()` (`scripts/little_loops/fsm/fragments.py`). See
  `docs/guides/LOOPS_GUIDE.md` §"Linear Flow Shorthand via `flow:`".
- **Sub-loops** — `loop:` states executed by `_execute_sub_loop()`
  (`scripts/little_loops/fsm/executor.py`). See `loops/oracles/*.yaml` for
  callee shape and `rn-plan.yaml` / `deep-research.yaml` for caller shape.

You never reimplement expansion or execution — you only emit YAML that the
existing parser accepts.

---

## Detection

Work from the **resolved** graph (`ll-loop show <name> --resolved --json`). Model
it as nodes (states) and directed edges. An edge is any routing target: `next`,
`on_yes`, `on_no`, `on_error`, every entry of a `route:` table, and (for `loop:`
states) `on_success` / `on_failure` / `on_error`. A state is **terminal** if it
sets `terminal: true` (or is a `done`/`failed` leaf with no outbound edges).

Compute, per state:

- `in_edges(s)` — states with an edge to `s` (plus `initial` has an implicit
  inbound).
- `out_edges(s)` — `s`'s routing targets.

### 2a. Linear-chain eligibility

A run `s1 → s2 → ... → sk` (k ≥ 2) is a **collapsible linear chain** when, for
every state:

| Check | Requirement |
|-------|-------------|
| Single forward edge | each `s1..s(k-1)` routes onward **only** via `next:` (an unconditional transition), OR via a single `on_yes`/`on_no` pair whose targets are expressible as a ternary (see below) |
| No fan-in mid-chain | each `s2..sk` has exactly one inbound edge, and it comes from its predecessor in the run (no other state routes into it) |
| No fan-out mid-chain | no interior state has extra edges (no stray `on_error` to outside the chain — unless preserved per the error-handling note below) |
| Not a self-loop | no state routes to itself (retry counters are **not** linear) |
| `initial` placement | if the chain includes `initial`, it must be `s1` (a `flow:` loop sets `initial:` to the first entry) |

**Maximal** means: extend the run in both directions until a check fails. Prefer
the longest eligible chain.

A loop is **fully collapsible** when its entire reachable state set is one
linear chain — only then can you replace `states:` with `flow:` (they are
mutually exclusive; you cannot leave residual `states:` beside a `flow:` block).
A partially-linear loop is a candidate for **extracting** the linear part as a
child (2b) whose body is then expressed with `flow:`.

### Worked transform: verbose `states:` → `flow:` + `state_defs:`

Input:

```yaml
name: lint-and-test
initial: run_lint
states:
  run_lint:
    action: "ruff check scripts/"
    action_type: shell
    evaluate: { type: exit_code }
    next: run_tests
  run_tests:
    action: "python -m pytest scripts/tests/"
    action_type: shell
    evaluate: { type: exit_code }
    terminal: true
```

Output (behaviorally identical after `resolve_flow()`):

```yaml
name: lint-and-test
initial: run_lint
flow:
  - run_lint
  - run_tests

state_defs:
  run_lint:
    action: "ruff check scripts/"
    action_type: shell
    evaluate: { type: exit_code }
  run_tests:
    action: "python -m pytest scripts/tests/"
    action_type: shell
    evaluate: { type: exit_code }
```

Note what the generator strips and what it keeps:

- Drop each interior state's `next:` — the `flow:` ordering regenerates it.
- Drop the last state's `terminal: true` — the last `flow:` entry is implicitly
  terminal.
- Keep `action`, `action_type`, `evaluate`, `capture`, `timeout`, `fragment`,
  and any `on_error:` override (see below) in `state_defs:`.
- `initial:` stays explicit (it is **not** inferred from `flow:`).

### Ternary mapping table

| Source state shape | `flow:` entry | Generated skeleton |
|--------------------|---------------|--------------------|
| `next: B` (last in run) | `A` (last entry) | `terminal: true` |
| `next: B` (interior) | `A` | `next: B` (from ordering) |
| `on_yes: B`, `on_no: C` | `A?B:C` | `on_yes: B`, `on_no: C` |
| `next: B` + `on_error: E` | `A` + keep `on_error` in `state_defs` | `next: B`, `on_error: E` |

Only a single yes/no branch per state is expressible inline. A state with a full
`route:` table or three-way verdict routing is **not** flow-collapsible — leave
it in `states:`.

### Error-handling caveat

In a `flow:` chain, a non-branching state uses `next:`, which routes **all**
outcomes (including non-zero exit) forward unless you add `on_error:` to its
`state_defs:` entry. Before collapsing, confirm each source state's error
behavior already matches "advance on error" — or carry its explicit `on_error:`
into `state_defs:`. Never silently change error routing; that breaks the
behavior-preservation invariant.

### 2b. Cohesion rules (sub-loop extraction)

A set of states `R` is an **extractable cohesive region** when:

1. **Single entry.** Exactly one state `e ∈ R` is targeted by edges from outside
   `R` (or is `initial`). All external inbound edges point at `e`.
2. **No interior leakage in.** No state outside `R` routes to any state in
   `R \ {e}`.
3. **Clean exits.** Edges leaving `R` (to states outside it) fall into at most
   two classes that map to child terminals: a **success exit** (→ child `done`)
   and a **failure exit** (→ child `failed`). An execution-error exit also maps
   to `failed` / `on_error`. If `R` has three or more distinct external targets
   that are *not* unifiable into success/failure, it is **not** cleanly
   extractable.
4. **Min size.** `|R|` ≥ 3 (default). Extracting one or two states adds a file
   and a `loop:` indirection without net simplification.
5. **Self-contained state.** `R` reads only `${context.*}` the parent can
   supply; it does not depend on `${captured.*}` produced by states outside `R`
   unless that capture is also passed in via `with:`.

**Interface inference.** For each `${context.KEY}` or `${captured.X}` read inside
`R` but produced outside it, add a child `parameters: { KEY: {type, required} }`
and a parent `with: { KEY: "${context.KEY}" }` binding. Always carry `run_dir`
when the parent has it (the runner injects it regardless, but declare it for
clarity).

**Verdict-laundering guard.** The parent's replacement `loop:` state must set
`on_success` and `on_failure` to **different** targets. If the region's success
and failure both flowed to the same next state, that is legitimate — but flag it,
because it means the child's done/failed distinction is intentionally discarded
(same check as `audit-loop-run` Step 8).

**Oracle reuse.** Before minting a child, compare `R`'s shape (entry action
kind, number of states, parameter set) against
`scripts/little_loops/loops/oracles/*.yaml`. If one matches, propose a `loop:`
call to the existing oracle instead of a new file — fewer files is simpler.

### Child loop skeleton

```yaml
name: <child-name>
description: |
  <one line: extracted from <parent>, what this region does>
initial: <region-entry>
parameters:
  run_dir:
    type: string
    required: true
  # ...inferred params
context:
  run_dir: ""
states:        # or flow: + state_defs: if the region is itself linear
  <region states, verbatim, with exits repointed to done/failed>
  done:
    terminal: true
  failed:
    terminal: true
```

### Parent replacement state

```yaml
<region-entry>:
  loop: <child-name>
  with:
    run_dir: "${context.run_dir}"
    # ...inferred bindings
  on_success: <region-success-target>
  on_failure: <region-failure-target>
  on_error: <region-failure-target>
```

---

## Behavior-preservation checklist

Run every item before declaring success. Any failure ⇒ restore the backup.

- [ ] `initial:` is unchanged.
- [ ] The set of **reachable terminal states** is unchanged (compare sorted lists
      from the baseline vs. post-rewrite resolved graph). Extracted regions'
      internal terminals become the **child's** `done`/`failed`; the parent's
      terminal set must still match the baseline minus any states moved into a
      child, plus none added.
- [ ] Every original transition has a corresponding path post-rewrite: a
      collapsed chain reproduces the same `next:` edges after `resolve_flow()`; an
      extracted region's success path = entry→…→done→`on_success`, failure path =
      entry→…→failed→`on_failure`.
- [ ] No orphaned (unreachable) states introduced in parent or child.
- [ ] `flow:` and `states:` never coexist in one file.
- [ ] Error routing semantics are unchanged (see error-handling caveat).
- [ ] Pure flow-collapse ⇒ the resolved `states:` graph is **byte-equivalent** to
      the baseline. (This is the strongest possible equivalence; demand it when
      no extraction occurred.)
- [ ] `ll-loop validate <name>` passes for parent and every child.
- [ ] `ll-loop simulate <name>` shows no new stall/premature/overrun signal.
- [ ] (builtin) `pytest scripts/tests/test_builtin_loops.py` passes, or failures
      are surfaced (not silently patched).

---

## Scope-resolution table

| Parent scope | Parent source | Extracted child target | Git |
|--------------|---------------|------------------------|-----|
| `project` | `.loops/<name>.yaml` | `.loops/<child>.yaml` | git-ignored (no `git add`) |
| `builtin` | `scripts/little_loops/loops/<name>.yaml` | `<loops-dir>/oracles/<child>.yaml` | git-tracked (`git add` each) |

`<loops-dir>` is the directory the parent resolved from (the built-in package
loops dir). A parent already under `oracles/` keeps its children as siblings in
`oracles/`.

---

## Artifact schema

Write to `.loops/simplifications/<name>-<YYYYMMDD-HHMMSS>.md`:

```markdown
---
loop: <name>
timestamp: <ISO-8601 UTC>
scope: builtin|project
states_before: <N>
states_after: <N'>
flows_collapsed: <K>
subloops_extracted: <C>
---

# Simplification: <name>

## Flows collapsed
- <s1> → <s2> → ... (<k> states) → flow: block

## Sub-loops extracted
- <child-name> (<dir>/<child>.yaml) — region <entry>..<exit>, <m> states
  - parameters: <list>
  - parent routing: on_success → <s>, on_failure → <s>

## Oracle reuse
- <region> matched existing oracle <oracle>; called directly (no new file)

## Equivalence checks
- resolved-graph: <equivalent | byte-equivalent>
- simulate: <no new signals | ...>
- builtin tests: <pass | n/a | failing assertions: ...>
```

---

## Anti-patterns (do not do these)

- **Collapsing a branching graph into `flow:`** by dropping branches — that
  changes behavior. `flow:` is for linear chains and single ternaries only.
- **Extracting a region with leaky inbound edges** (an outside state jumps into
  the region's middle) — the child would be entered at the wrong state.
- **Letting `on_success == on_failure`** silently — flag it as verdict laundering.
- **Editing tests to make them pass** after a builtin rewrite — surface the
  failure; the user decides.
- **Partial application on validation failure** — restore the backup; never
  leave the parent in a broken intermediate state.
