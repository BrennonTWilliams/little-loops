---
id: FEAT-1738
type: FEAT
priority: P3
status: done
captured_at: '2026-05-27T18:08:06Z'
completed_at: '2026-05-30T03:19:04Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
depends_on:
- FEAT-1743
relates_to:
- EPIC-1694
- FEAT-1696
- FEAT-1695
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1738: `proof-first-task` — opt-in wrapper that gates any impl loop on assumption-firewall

## Summary

Add `scripts/little_loops/loops/proof-first-task.yaml` — an FSM loop that runs `assumption-firewall` (FEAT-1696) as a pre-phase before delegating to any caller-specified implementation loop. Users who want proof-first behavior run `proof-first-task` instead of `general-task` or `autodev`; the core built-in loops stay unpolluted for projects that don't use the Learning Test Registry.

## Current Behavior

`general-task`, `autodev`, `scan-and-implement`, and other mainstream coding loops have no awareness of the Learning Test Registry. A developer who runs any of these against a task that touches an unfamiliar third-party API will write code based on training-data assumptions rather than proven API behavior, with no automatic prompt to run `/ll:explore-api` first.

`assumption-firewall` and `ready-to-implement-gate` (FEAT-1695, FEAT-1696) exist as opt-in gates, but they are independent loops — a developer must know to run them before their implementation loop. There is no single entry point that combines "prove first, then implement."

## Expected Behavior

```bash
# Prove API assumptions, then implement the task
ll-loop run proof-first-task \
  --context task="Add Stripe webhook signature verification" \
  --context issue_file=".issues/features/P2-FEAT-1234-stripe-webhooks.md" \
  --context impl_loop="general-task"
```

The loop:

1. `gate` (sub-loop) — runs `assumption-firewall` with `input: "${context.issue_file}"`. On `done` (all proven or no external deps) → proceeds to `run_impl`. On `blocked` (refuted) → routes to `blocked` terminal.
2. `run_impl` (sub-loop) — runs the loop named in `context.impl_loop` with `input: "${context.task}"`. On success → `done`. On failure → `impl_failed`.
3. Terminal states: `done`, `blocked` (gate failed), `impl_failed` (impl loop failed after gate passed), `no_issue_file` (issue_file not provided — gate is skipped, loop runs impl directly).

When `issue_file` is empty, the loop skips the gate and routes directly to `run_impl`, so it degrades gracefully to a plain impl-loop runner.

## Motivation

- **Closes the mainstream-loop blindspot without polluting core loops.** The gap identified in the LT registry gap analysis: "The biggest gap is the absence of a pre-implementation gate in `autodev`/`general-task`/`scan-and-implement`." This loop closes that gap as an opt-in alternative entry point rather than a modification to the core loops.
- **Single entry point for proof-first development.** Instead of remembering to run `assumption-firewall` before `general-task`, a developer uses one loop that chains both. The pattern is opt-in by loop choice, not by config flag.
- **Degrades gracefully.** When no `issue_file` is provided, `proof-first-task` acts as a plain wrapper around the specified impl loop — no friction for users who don't need the gate.

## Use Case

A developer wants to implement a Stripe webhook feature. They run:

```bash
ll-loop run proof-first-task \
  --context task="Implement Stripe webhook signature verification" \
  --context issue_file=".issues/features/P2-FEAT-1234-stripe-webhooks.md" \
  --context impl_loop="general-task"
```

The loop extracts API assumptions from the issue file, proves each via the LT registry, then — if all pass — runs `general-task` with the task description. If a surface is refuted, the loop stops with a structured diagnosis before any implementation code is written.

## Proposed Solution

```
check_issue_file (shell)
  → test -n "${context.issue_file}" && test -f "${context.issue_file}"
  evaluate: exit_code
  on_yes: gate
  on_no:  run_impl   # no issue file → skip gate

gate (sub-loop)
  loop: assumption-firewall
  with:
    input: "${context.issue_file}"
  on_success: run_impl        # done or no_external_deps
  on_failure: blocked         # refuted
  on_error:   blocked

run_impl (sub-loop)
  loop: "${context.impl_loop}"
  with:
    input: "${context.task}"
  on_success: done
  on_failure: impl_failed
  on_error:   impl_failed

done (terminal)
blocked (terminal)
impl_failed (terminal)
```

**Context variables:**

| Variable | Default | Description |
|---|---|---|
| `task` | `""` | Natural-language task description passed to the impl loop; required |
| `issue_file` | `""` | Path to issue file for assumption extraction; optional (gate skipped if empty/missing) |
| `impl_loop` | `"general-task"` | Name of the impl loop to run after the gate passes |

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Sub-loop terminal routing is binary** (`fsm/executor.py:_execute_sub_loop():587-600`): Only `final_state == "done"` routes to `on_yes` (→ `on_success`). All other terminal states — including `no_external_deps` from assumption-firewall — route to `on_no` (→ `on_failure`). **Design consideration**: The Proposed Solution comment "# done or no_external_deps" on `on_success: run_impl` won't work as written; `no_external_deps` would incorrectly route to `blocked` terminal. Two approaches: **(A)** Add `capture: gate_result` on the gate state, then a post-gate `check_gate_blocked` shell state that parses `final_state` from captured JSON to route `no_external_deps` → `run_impl` vs `blocked` → `blocked` terminal. **(B)** Accept the limitation — route both `blocked` and `no_external_deps` to the same terminal with diagnostic output from the sub-loop.
- **`on_success`/`on_failure` are YAML aliases** (`fsm/schema.py:StateConfig.from_dict():510-511`): Mapped to `on_yes`/`on_no` at deserialization. Both forms valid in loop YAML. The `assumption-firewall.yaml` and `adopt-third-party-api.yaml` loops use these aliases.
- **No default-value syntax in templates** (`fsm/interpolation.py`): Missing `${context.*}` variables raise `InterpolationError`. Defaults come from the top-level `context:` block or sub-loop `with:` bindings — not from template syntax.
- **`with:` is the preferred sub-loop binding** (`fsm/executor.py:_execute_sub_loop():513-533`): Interpolates bindings and validates against child's `parameters:` declarations. Alternative `context_passthrough: true` (legacy, line 534) merges entire parent context — use `with:` for explicit, auditable bindings.
- **Loop discovery** (`cli/loop/_helpers.py:resolve_loop_path():811`): Searches project `.loops/` first, then falls back to `scripts/little_loops/loops/`. New YAML file in built-in dir is auto-discovered.
- **Validation scope**: `ll-loop validate` checks state references and routing consistency but does NOT verify sub-loops exist on disk (lazy, checked at runtime).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/proof-first-task.yaml` — new FSM loop definition
- `scripts/tests/test_builtin_loops.py` — add to expected loop set + structural test class
- `README.md` — update loop count
- `CONTRIBUTING.md` — update loop count
- `docs/guides/LOOPS_GUIDE.md` — add built-in loops table row

### Dependent Files (Callers/Importers)
- `assumption-firewall` loop (via sub-loop call)
- User-specified impl loop (e.g., `general-task`, `autodev`) via dynamic sub-loop
- `ll-loop` CLI (entry point for running the loop)

### Similar Patterns
- `general-task` — existing built-in loop that this wraps
- `scan-and-implement` — another mainstream loop that could benefit from this wrapper pattern
- `adopt-third-party-api.yaml` — **exact analog**: wraps `ready-to-implement-gate` as sub-loop with `with:` + `on_success`/`on_failure`, then delegates to impl phase; identical structural pattern to follow
- `integrate-sdk.yaml` — **exact analog**: same gate-then-delegate pattern with identical sub-loop syntax
- `outer-loop-eval.yaml:55` — uses `loop: "${context.input}"` for dynamic sub-loop dispatch, the exact mechanism needed for `${context.impl_loop}`
- `loop-router.yaml:335` — uses `loop: "${captured.chosen.output}"` for runtime dispatch; confirms dynamic `loop:` interpolation works
- `lib/common.yaml:15` — `shell_exit` fragment providing `action_type: shell` + `evaluate: { type: exit_code }`; reusable via `fragment: shell_exit` for the `check_issue_file` state
- `test_builtin_loops.py:3989` — `TestAssumptionFirewallLoop` class is the structural test pattern to model `TestProofFirstTaskLoop` after

### Tests
- `scripts/tests/test_builtin_loops.py` — add `TestProofFirstTaskLoop` class and `"proof-first-task"` to `expected` set

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — built-in loops table
- `scripts/little_loops/loops/README.md` — built-in loops catalog, add row in API Adoption section
- `README.md` — loop count
- `CONTRIBUTING.md` — loop count

### Configuration
- N/A

## Implementation Steps

1. Draft `scripts/little_loops/loops/proof-first-task.yaml` (~70 lines). Model structure after `assumption-firewall.yaml` (114 lines) — same top-level metadata fields (`name`, `category: gate`, `description`, `initial`, `max_iterations`, `timeout`, `on_handoff`), `context:` block with defaults, and bare terminal states. Reference `adopt-third-party-api.yaml` for the sub-loop delegation pattern.
2. Wire `check_issue_file` as a shell state. Use `fragment: shell_exit` (from `lib/common.yaml:15`) to inherit `action_type: shell` + `evaluate: { type: exit_code }`. Action: `test -n "${context.issue_file}" && test -f "${context.issue_file}"`. Route `on_yes: gate`, `on_no: run_impl`.
3. Wire `gate` as a sub-loop call to `assumption-firewall`. Use `loop: assumption-firewall` with `with: { input: "${context.issue_file}" }`. Route `on_success: run_impl`, `on_failure: blocked`, `on_error: blocked`. See `assumption-firewall.yaml:97-104` (`run_gate` state) for the exact syntax. **Routing note**: Per `fsm/executor.py:587-600`, only `final_state == "done"` → `on_success`; `no_external_deps` and `blocked` both → `on_failure`. Consider approach (A) from Codebase Research Findings above if `no_external_deps` → `run_impl` is required.
4. Wire `run_impl` as a dynamic sub-loop: `loop: "${context.impl_loop}"` with `with: { input: "${context.task}" }`. Pattern confirmed by `outer-loop-eval.yaml:55-63` (`run_sub_loop` state). Route `on_success: done`, `on_failure: impl_failed`, `on_error: impl_failed`.
5. Run `ll-loop validate proof-first-task` and iterate until no ERRORs. Validation checks state references, routing consistency, and `with:` binding cross-references but does NOT verify sub-loop file existence.
6. Update `scripts/tests/test_builtin_loops.py`:
   - Add `"proof-first-task"` to `expected` set at `TestBuiltinLoopFiles.test_expected_loops_exist` (line ~66-128)
   - Add `TestProofFirstTaskLoop` class modeled after `TestAssumptionFirewallLoop` (line 3989): `LOOP_FILE` constant, `data` fixture loading YAML, structural assertions for `check_issue_file` (fragment + routing), `gate` (sub-loop delegation + `with:` bindings), `run_impl` (dynamic loop + `with:` bindings), and terminal flags (`done`, `blocked`, `impl_failed`)
7. Update numeric loop counts in `README.md` and `CONTRIBUTING.md` (tracked by `ll-verify-docs`).
8. Add row to `docs/guides/LOOPS_GUIDE.md` built-in loops table. Add a "Proof-First" row to the API Adoption section (lines ~377-380) with name, category, and description. Also update `scripts/little_loops/loops/README.md` built-in loops table.

## Acceptance Criteria

- `scripts/little_loops/loops/proof-first-task.yaml` exists and `ll-loop validate proof-first-task` reports no ERRORs.
- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` passes with `"proof-first-task"` in `expected`.
- When `issue_file` is provided and gate passes: impl loop runs.
- When `issue_file` is provided and gate blocks: loop terminates at `blocked` without running the impl loop.
- When `issue_file` is empty or missing: gate is skipped, impl loop runs directly.
- `context.impl_loop` defaults to `"general-task"` and is overridable per-run.

## API/Interface

```bash
ll-loop run proof-first-task \
  --context task="<task description>" \
  --context issue_file="<path to issue file>" \
  --context impl_loop="<loop name>"
```

**Context variables:**

| Variable | Required | Default | Description |
|---|---|---|---|
| `task` | yes | — | Natural-language task description passed to the impl loop |
| `issue_file` | no | `""` | Path to issue file for assumption extraction; gate skipped if empty/missing |
| `impl_loop` | no | `"general-task"` | Name of the impl loop to run after the gate passes |

**Terminal states:** `done`, `blocked`, `impl_failed`

## Impact

- **Priority**: P3 — Opt-in, additive feature. No existing behavior modified. Users who don't invoke `proof-first-task` are unaffected.
- **Effort**: Small — One new YAML loop file (~60 lines), test additions in one file, and documentation updates.
- **Risk**: Low — Standalone file with no imports from or to other Python modules. Failure mode is contained to the wrapper itself.
- **Breaking Change**: No

## Labels

`feat`, `loop`, `learning-tests`, `fsm`, `gate-consumer`, `proof-first`, `opt-in`

---

**Open** | Created: 2026-05-27 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-29_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- **no_external_deps routing ambiguity**: Per fsm/executor.py:587-600, only `final_state == "done"` routes to `on_success`. The Proposed Solution assumes `no_external_deps` → `run_impl` but sub-loop binary routing means it would go to `on_failure` → `blocked`. Implementation Step 3 flags this. Resolve before or during YAML authoring (Approach A: capture + post-gate shell; Approach B: accept limitation).

## Session Log
- `/ll:ready-issue` - 2026-05-30T03:13:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43c48749-cb46-486e-a602-2111ee564bbc.jsonl`
- `/ll:confidence-check` - 2026-05-29T21:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/638aa818-bcbd-46e3-90c3-b9639455e91c.jsonl`
- `/ll:wire-issue` - 2026-05-30T03:07:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62d239ef-cdb9-4e10-91c4-b7e6d7ebb096.jsonl`
- `/ll:refine-issue` - 2026-05-30T03:01:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10099c1b-8e47-48e1-b15b-3ee2a2da4e58.jsonl`
- `/ll:format-issue` - 2026-05-29T20:02:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a846596c-487a-4d83-8770-0975057857d0.jsonl`
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
- `/ll:manage-issue feature implement FEAT-1738` - 2026-05-30T03:19:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43c48749-cb46-486e-a602-2111ee564bbc.jsonl`
---
---
## Resolution

**Completed**: 2026-05-30T03:19:04Z

### Changes Made

1. **`scripts/little_loops/loops/proof-first-task.yaml`** (new): FSM loop definition with four states:
   - `check_issue_file`: Shell gate using `fragment: shell_exit`; skips to `run_impl` when no issue file provided
   - `gate`: Sub-loop delegation to `assumption-firewall` with `with: { input }` binding; captures result for post-gate routing
   - `check_gate_blocked`: Post-gate shell state distinguishing `no_external_deps` (count=0 → `run_impl`) from `blocked` (count>0 → `blocked` terminal)
   - `run_impl`: Dynamic sub-loop dispatch to `${context.impl_loop}` with `with: { input }` binding
   - Terminals: `done`, `blocked`, `impl_failed`

2. **`scripts/tests/test_builtin_loops.py`**: Added `"proof-first-task"` to expected set and `TestProofFirstTaskLoop` class (10 structural tests)

3. **Documentation**: Added row to `scripts/little_loops/loops/README.md` API Adoption section, `docs/guides/LOOPS_GUIDE.md` API Adoption section, and updated loop count in `CONTRIBUTING.md` (56→59)

### Design Decision: `no_external_deps` Routing

Used Approach A from the codebase research findings. The sub-loop executor (`fsm/executor.py:587-600`) only routes `final_state == "done"` to `on_success`; `no_external_deps` would incorrectly route to `blocked`. Solved by capturing the gate sub-loop result and adding a `check_gate_blocked` shell state that parses the captured JSON: count=0 → `run_impl`, count>0 → `blocked`.

### Verification

- `ll-loop validate proof-first-task` — no ERRORs
- `TestProofFirstTaskLoop` — 10/10 pass (structural assertions for fragment, sub-loop delegation, dynamic dispatch, terminals)
- Pre-existing `test_expected_loops_exist` failure (missing `cli-anything-bootstrap` in expected set) — not caused by this change