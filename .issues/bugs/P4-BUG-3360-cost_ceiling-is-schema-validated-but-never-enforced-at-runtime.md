---
id: BUG-3360
type: BUG
title: cost_ceiling is schema-validated but never enforced at runtime
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-30'
captured_at: '2026-08-30T04:51:19Z'
labels:
- fsm
- loops
- dead-code
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3360: cost_ceiling is schema-validated but never enforced at runtime

## Summary

`StateConfig.cost_ceiling` (ENH-2477) is a fully-plumbed dataclass with
serialization and validation, but **no runtime consumer**. A loop author can
declare a per-state USD spend cap, `ll-loop validate` reports the loop as
valid, and the cap is never checked during the run. The knob is a silent no-op
that reads as spend protection.

Its documented companion — FEAT-2476's global `--max-cost` accumulator, which
`CostCeilingConfig`'s own docstring says it "composes with"
(`fsm/schema.py:401`) — was **cancelled**, so the enforcement half of the
design never landed on either side.

## Current Behavior

`cost_ceiling` exists end-to-end on the config path:

| Site | Role |
|------|------|
| `fsm/schema.py:397-434` | `CostCeilingConfig` dataclass (`cost_ceiling_per_state`, `cost_warn_at`) + `to_dict`/`from_dict` |
| `fsm/schema.py:735` | `StateConfig.cost_ceiling` field |
| `fsm/schema.py:846-847` | serialized in `StateConfig.to_dict` |
| `fsm/schema.py:888-890,960` | deserialized in `StateConfig.from_dict` |
| `fsm/validation/structural_rules.py:755-757` | dispatch when present |
| `fsm/validation/structural_rules.py:762-831` | `_validate_state_cost_ceiling` — rejects negatives, warns on `cost_warn_at >= cost_ceiling_per_state` |
| `scripts/tests/test_fsm_validation_structural.py:702-769` | validation-only test coverage |

And nowhere on the execution path:

```
$ grep -rn "cost_ceiling" scripts/little_loops/fsm/executor.py
(no output)

$ grep -rn "cost_warn_at|\.cost_ceiling" scripts/little_loops/ scripts/tests/ \
    | grep -v "schema.py|structural_rules.py"
scripts/tests/test_fsm_validation_structural.py: ...   # validation tests only
```

Reproduced against a minimal loop declaring both keys on a shell state:

```yaml
states:
  work:
    action: "echo hi"
    action_type: shell
    cost_ceiling:
      cost_ceiling_per_state: 1.0
      cost_warn_at: 0.5
    next: done
```

`ll-loop validate` → `is valid`. No warning that the ceiling is inert.

(The shell state above demonstrates the validation gap. Note it also exposes a
second inertness trap for the enforce path: shell/mcp actions never write
`usage.jsonl` rows — see the writer's guard and comment at
`fsm/persistence.py:1008-1010`, "Shell and mcp_tool invocations produce no
token data and are skipped" — so a ceiling on a non-prompt state can never
trip even once enforcement lands. Covered under Decision Rules.)

Two aggravating details:

1. **`cost_ceiling` is absent from `fsm-loop-schema.json`.** It is not among
   the 45 properties of `/definitions/stateConfig`, which declares
   `additionalProperties: false`. The dataclass path accepts it anyway, so the
   JSON schema and the dataclass schema disagree about whether the key exists
   at all.
2. **The data needed to enforce it is already being written live.**
   `PersistentExecutor._handle_event()` appends a per-`action_complete` row —
   `state`, `iteration`, `input_tokens`, `output_tokens`, cache tokens,
   `model` — to `<run_dir>/usage.jsonl` at `fsm/persistence.py:1008-1036`, and
   `fsm/cost_graph.py` already aggregates those rows into `PerStateCost` with
   `estimate_cost_usd`. Only the in-run comparison and route are missing.

(Note: `cost_graph.py`'s module docstring cites this writer at
`fsm/persistence.py:637-655`; the real site is `:1008-1036`. Worth refreshing
while in the area.)

## Steps to Reproduce

1. Write a loop YAML declaring a per-state ceiling on any state:

   ```yaml
   name: cc-probe
   description: probe whether cost_ceiling is enforced
   initial: work
   states:
     work:
       action: "echo hi"
       action_type: shell
       cost_ceiling:
         cost_ceiling_per_state: 1.0
         cost_warn_at: 0.5
       next: done
     done:
       terminal: true
   ```

2. `ll-loop validate cc-probe.yaml` → `cc-probe.yaml is valid`. No warning that
   the declared ceiling has no effect. (Confirmed 2026-08-30; the only emitted
   warning is the unrelated missing-`scope:` one.)

3. `grep -n "cost_ceiling" scripts/little_loops/fsm/executor.py` → no matches.
   The run never reads the value.

**Expected at step 2 or 3:** either the ceiling is enforced during the run, or
validation rejects/warns on a key nothing consumes.

## Expected Behavior

**Decision (2026-08-30 pre-implementation review): enforce, abort-only.**

- **Enforce it (chosen).** After each state visit, sum that state's cost from
  the rows already being appended to `usage.jsonl` and compare against
  `cost_ceiling_per_state`; emit a warning at `cost_warn_at`; **abort the run
  on breach** (`terminated_by="cost_ceiling_exceeded"`), mirroring the abort
  branch of the host-budget handling at `fsm/executor.py:795-800`. This also
  requires adding `cost_ceiling` to `/definitions/stateConfig` in
  `fsm-loop-schema.json` so the two schemas agree.

Rationale for enforce over remove: `README.md:144`, `scripts/README.md:144`,
and `docs/guides/LOOPS_GUIDE.md:202-224` already advertise the feature, and
the enforcement half is small given `cost_graph.py` reuse; removal deletes an
advertised capability. Rationale for abort-only over routing: it is the only
option consistent with "no new field" on `CostCeilingConfig`, it is the
minimal fix for the inert-knob lie, and it adds **no new route-target
convention** — sidestepping the EPIC-3041 collision (FEAT-3038/FEAT-3039
independently add a second "route on running out of X" shape to the same FSM
layer) entirely. If routing is ever wanted, add the
`on_ceiling_exceeded`/`ceiling_state` pair shape (mirroring
`on_budget_exceeded`/`budget_state`) as a follow-up issue, settling the
collision then.

The rejected alternative, for the record: **remove it** — drop
`CostCeilingConfig`, the `StateConfig` field, the validation branch, and the
validation tests. The removal-path line items below are retained in the
Integration Map for context but are not the plan.

## Program Design

Designed for the **enforce (abort-only)** path — the committed decision, see
Expected Behavior.

### Types

- `CostCeilingConfig` (`fsm/schema.py:397-434`) — no new field. The existing
  `cost_ceiling_per_state: float | None` and `cost_warn_at: float | None` are
  the whole declarative surface; this issue adds only readers. "No new field"
  is consistent because enforcement is **abort-only** (no route target to
  name). The docstring must be corrected in the same change: it currently
  says a breach "routes to a ceiling-exhausted target" and "composes with
  FEAT-2476's global `--max-cost`" (`fsm/schema.py:400-405`) — rewrite to
  "aborts the run" and drop the reference to the cancelled FEAT-2476.
- `PerStateCost` (`fsm/cost_graph.py:42-71`) — no new field. Its `cost_usd` is
  the quantity compared against the ceiling, and its `has_unknown_model` flag
  is the documented "cost is 0 because the model could not be priced" signal
  the check must treat as *unknown*, never as *under budget*.

### Signatures

- `FSMExecutor._check_cost_ceiling(self, state: StateConfig) -> bool` — new; returns `True` when the ceiling is breached (caller then finishes the run via `self._finish("cost_ceiling_exceeded", error=...)`, mirroring the abort branch of the host-budget handling at `fsm/executor.py:795-800`), `False` otherwise — including all "unknown" cases (see Decision Rules). Takes `StateConfig` like the adjacent `_check_host_guard` (`fsm/executor.py:3506`), but abort-only means no next-state return.
- `CostReport.from_usage_jsonl(cls, path: Path) -> CostReport` — existing classmethod (`fsm/cost_graph.py:185`); the check reuses it to read the live `<run_dir>/usage.jsonl` rather than adding a second accumulator.
- `estimate_cost_usd(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_creation_tokens: int = 0, is_batch: bool = False)` — existing (`little_loops/pricing.py:113-119`); already the pricing primitive behind `PerStateCost.cost_usd`, unchanged here.

### Call Path

`FSMExecutor._execute_state` (`fsm/executor.py:1795`) → `_run_action_or_route`
(`fsm/executor.py:3323`) → [action completes; the `action_complete` `_emit` at
`fsm/executor.py:2407` synchronously invokes `PersistentExecutor._handle_event`
(`fsm/persistence.py:998`), which appends the row to `<run_dir>/usage.jsonl`
at `:1008-1036`] → new `_check_cost_ceiling` → `CostReport.from_usage_jsonl`
→ compare this state's `PerStateCost.cost_usd` against
`state.cost_ceiling.cost_ceiling_per_state` → on breach, abort via
`_finish("cost_ceiling_exceeded", ...)`, mirroring the abort branch of the
host-budget handling at `fsm/executor.py:795-800`.

The check must sit **after** the event is appended, not before, since the row
carrying this visit's tokens is written by the event handler. This ordering is
sound because `_emit` (`fsm/executor.py:3397`) calls the event callback
synchronously.

Citation note: `_check_host_guard` (`fsm/executor.py:3506`) is *called* at
`fsm/executor.py:736`; `:795-800` is the separate pending-flag budget branch
inside `run()`. They are two mechanisms — the new check mirrors the shape of
the former and the abort semantics of the latter.

### Decision Rules

- **Warn vs. breach.** `cost_warn_at` logs only (no abort) — it is documented
  as "a warning-only threshold for visible spend, not a hard cap"
  (`fsm/schema.py:404-405`). Only `cost_ceiling_per_state` aborts. Warn **once
  per state**, not on every visit past the threshold (track warned states on
  the executor).
- **Unpriceable models.** When `PerStateCost.has_unknown_model` is true,
  `cost_usd` is left at 0 by design. Treat this as *unknown*, not *under
  budget*: do not abort, and log that the ceiling could not be evaluated.
  Silently reading 0 would make the ceiling inert for exactly the unpriced
  models most likely to be new and expensive.
- **Missing/empty `usage.jsonl` is *unknown*, not zero.** The file exists only
  when running under `PersistentExecutor` with `run_dir` in context
  (`fsm/persistence.py:1011-1012`); a bare `FSMExecutor.run()` never writes
  it. Mirror the unpriceable-model rule: log once that the ceiling could not
  be evaluated, do not abort. (Added 2026-08-30 review.)
- **Shell/mcp states cannot trip the ceiling.** Only `action_complete` events
  carrying `input_tokens` produce `usage.jsonl` rows
  (`fsm/persistence.py:1008-1010`) — shell and mcp_tool actions never do. Add
  a validation **warning** in `_validate_state_cost_ceiling` when
  `cost_ceiling` is declared on a state whose `action_type` can never produce
  token usage, so the config isn't silently inert under the new enforcement.
  (Added 2026-08-30 review.)
- **Grain.** The ceiling is per *state*, matching `cost_ceiling_per_state`'s
  name and `PerStateCost`'s existing aggregation grain (which sums across a
  state's visits). Per-visit grain would need a new aggregation and is out of
  scope.
- **Breach action: abort-only.** No route target — see the committed decision
  under Expected Behavior. Finish with
  `terminated_by="cost_ceiling_exceeded"` and emit a breach event carrying
  `state` and the computed `cost_usd` vs. ceiling, following the
  `HOST_BUDGET_EXCEEDED_EVENT` payload shape (`fsm/executor.py:795-800`). Do
  **not** add `on_ceiling_exceeded`/`ceiling_state` fields in this issue.
- **Re-read cost is accepted.** `CostReport.from_usage_jsonl` re-parses the
  whole file on each checked visit — O(n²) over a long run, fine at JSONL
  scale. Do not add a second in-memory accumulator to "fix" this; the single
  source of truth is the file.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- **Contested convention: how "route on breach" targets are declared.** This
  codebase has two established, mutually inconsistent shapes for "declare a
  threshold, then route to a state when it's breached":
  - **Pair shape** — an `on_X` action switch (`"route"` / `"abort"` / other)
    plus a companion `X_state` field carrying the target state name, both
    declared on the *same* config object as the threshold itself:
    `HostGuardConfig.on_pressure` / `pressure_state`
    (`fsm/host_guard.py:77-78`, JSON schema
    `fsm-loop-schema.json:308,314`) and
    `HostGuardConfig.on_budget_exceeded` / `budget_state`
    (`fsm/host_guard.py:81-82`, JSON schema
    `fsm-loop-schema.json:328,334`) both follow it.
  - **Direct shape** — a single field holding the target state name with no
    separate action switch: `StateConfig.on_retry_exhausted: str | None`
    (`fsm/schema.py:712`, JSON schema `fsm-loop-schema.json:524`).
  - `CostCeilingConfig` (`fsm/schema.py:397-434`) declares neither shape
    today — only `cost_ceiling_per_state` and `cost_warn_at`. Its own
    docstring already asserts a breach "routes to a ceiling-exhausted
    target" (`fsm/schema.py:401-402`), but no field on the dataclass carries
    that target's name under either convention.
  - This is in tension with this issue's own Program Design → Types claim
    that `CostCeilingConfig` needs "no new field": under either established
    shape, a route target needs a field somewhere (a new `ceiling_state`-like
    field mirroring the pair shape, or a `StateConfig`-level field mirroring
    `on_retry_exhausted`'s direct shape). Only an abort-only enforcement (no
    route capability, ceiling breach always ends the run) needs no new
    field — narrower than "reuse `host_guard.py`'s existing
    `on_budget_exceeded`/`budget_state` naming" as currently phrased under
    Decision Rules → Route target, which implies routing is in scope.
- **Test convention for this class of check**: executor-level route/abort
  checks are tested end-to-end via `FSMExecutor.run()` against a real event
  stream, not by unit-testing the check method in isolation — see
  `TestExecutorRssBudget` (`scripts/tests/test_host_guard.py:509-573`), which
  builds a minimal FSM, drives a full `run()`, and asserts on
  `result.final_state` / `result.terminated_by` plus the emitted
  `host_budget_exceeded` event payload's `action` key
  (`"route:<state>"` vs `"abort"`). A cost-ceiling enforcement test would
  follow the same shape rather than calling `_check_cost_ceiling` directly.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — per-state-visit cost check + abort on breach
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `cost_ceiling` to `/definitions/stateConfig`
- `scripts/little_loops/fsm/schema.py:397-434` — fix `CostCeilingConfig` docstring: "routes to a ceiling-exhausted target" → "aborts the run"; drop the cancelled-FEAT-2476 "composes with" claim (2026-08-30 review)
- `scripts/little_loops/fsm/validation/structural_rules.py:762-831` — extend `_validate_state_cost_ceiling` with the inert-on-shell/mcp-state warning (2026-08-30 review)
- `scripts/little_loops/fsm/cost_graph.py` — refresh the stale `persistence.py:637-655` docstring citation → `:1008-1036`

_Removal-path line items (rejected alternative, retained for context only):_
- `scripts/little_loops/fsm/schema.py:397-434,735,846-847,888-890,960` — `CostCeilingConfig` (removal path)
- `scripts/little_loops/fsm/validation/structural_rules.py:755-831` — validation branch (removal path)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:139,176` — package-level export of `CostCeilingConfig`; removal path must drop this export alongside the `schema.py` field [Agent 1 finding]
- `scripts/little_loops/fsm/validation/__init__.py:154,268` — package-level export of `_validate_state_cost_ceiling`; removal path must drop this export alongside the `structural_rules.py` branch [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/fsm/host_guard.py:68-82` + `fsm/executor.py:795-800` — the host-budget breach handling; the new check mirrors its **abort** branch (event payload + `_finish`), not the route branch
- `scripts/little_loops/fsm/cost_graph.py` — existing `usage.jsonl` → `PerStateCost` aggregation to reuse

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py:2013` (`_print_usage_summary`) — existing production caller of `CostReport.from_usage_jsonl`, the same classmethod the enforce path's `_check_cost_ceiling` reuses; confirms the primitive already has a live consumer, so its read contract (return shape, missing-file/malformed-row handling) must stay compatible with this caller [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:144` — the "Bounded by design" pull-quote asserts "Cost ceilings (per-state `cost_ceiling:`) ... keep spend ... honest" — this is the exact overclaim the bug reports; enforce path needs this to become true, removal path must delete the clause [Agent 2 finding]
- `scripts/README.md:144` — duplicate of the same claim, kept in sync with the root README [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:202-224` — full "Per-State Cost Ceiling (`cost_ceiling:`)" reference section, including "hard cap; routes/aborts when exceeded"; rewrite for abort-only semantics and document the two inertness caveats (shell/mcp states, non-persistent runs) [Agent 2 finding; updated 2026-08-30 review]
- `docs/reference/API.md:5755` — one-line `StateConfig.cost_ceiling` field reference ("routes on cost ceiling trip"); under abort-only this is **not** accurate — reword to "aborts on cost ceiling trip" [Agent 2 finding; updated 2026-08-30 review]

### Tests
- `scripts/tests/test_fsm_validation_structural.py:702-769` — extend with the new inert-on-shell/mcp-state warning case
- **New enforcement test caveat (2026-08-30 review):** the cited
  `TestExecutorRssBudget` pattern drives a bare `FSMExecutor.run()`, which
  never writes `usage.jsonl` — copying it verbatim would exercise nothing.
  The new test must either run under `PersistentExecutor` with a real
  `run_dir` in context, or pre-seed `<run_dir>/usage.jsonl` with rows priced
  above the ceiling before driving `run()`. Use a **prompt** state (or a
  stubbed host action emitting `input_tokens`), never a shell state. Also
  cover: missing `usage.jsonl` → no abort + logged "could not evaluate", and
  `has_unknown_model` → no abort.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py:3410-3464` — existing `CostCeilingConfig`/`StateConfig.cost_ceiling` serialization round-trip tests; removal path deletes these, enforce path keeps them as regression coverage alongside the new runtime-enforcement test [Agent 3 finding]
- `scripts/tests/test_cli_loop_layout.py:144` — layout test asserting a `"cost_ceiling": None` key in loop-summary output; verify against whichever path lands [Agent 3 finding]
- `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_cli_cost_table.py` — existing full coverage of `CostReport.from_usage_jsonl`, the classmethod the enforce path's `_check_cost_ceiling` reuses; no gap, but the new enforcement test should follow `TestExecutorRssBudget`'s end-to-end `run()` pattern (already cited under Codebase Research Findings) rather than duplicate this file's unit-level coverage [Agent 3 finding]

## Impact

- **Priority**: P4 — no crash or data loss, but a safety knob that reports
  valid and does nothing is worse than an absent one: an author who sets
  `cost_ceiling_per_state: 5.0` on an expensive state reasonably believes spend
  is bounded, and it is not.
- **Effort**: Small either way. Removal is mechanical. Enforcement is one
  executor check plus a JSON-schema entry, reusing `cost_graph.py`'s existing
  aggregation and `host_guard.py`'s existing route shape.
- **Risk**: Low. No loop in this repo declares `cost_ceiling` today, so neither
  path changes existing behavior.
- **Breaking Change**: Removal breaks any out-of-repo loop that declares the
  key — but only by rejecting a key that never did anything.

## Root Cause

ENH-2477 ("F6 (finishes) — Per-state cost attribution: stable JSON + per-state
ceilings", done 2026-07-07) delivered the attribution half — `usage.jsonl`,
`cost_graph.py`, the stable JSON shape — and landed the ceiling **schema** as
the declarative surface for FEAT-2476 to enforce. FEAT-2476 ("F2 — `--max-cost`
accumulator + 80%/100% guard") was subsequently cancelled, orphaning the
schema. Nothing failed loudly because a config key with no reader raises no
error, and the validation tests pass regardless.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-30_

> **Resolution (2026-08-30 pre-implementation review):** both Concerns below
> are settled — the fork is committed to **enforce**, and the route-target
> contradiction is resolved as **abort-only** (no new field, no new route
> convention). See Expected Behavior. The notes below are retained as the
> historical record.

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- Contested route-target convention is unresolved: the Codebase Research
  Findings section itself flags that `CostCeilingConfig` declares no field
  for a route target, yet Decision Rules → "Route target" calls for reusing
  `host_guard.py`'s `on_budget_exceeded`/`budget_state` pair shape, which
  needs one. This directly contradicts Program Design → Types' "no new
  field" claim; only an abort-only enforcement needs no new field. Resolve
  which shape (pair-field vs. abort-only vs. `on_retry_exhausted`-style
  direct field) before implementing routing.
- The issue leaves a fundamental fork open by design ("Either is
  acceptable"): enforce `cost_ceiling` at runtime, or remove it entirely.
  Whichever path is picked should be committed to before implementation
  starts, since the two paths touch almost entirely different files.

### Outcome Risk Factors
- Ambiguity: the unresolved route-target field decision (see Concerns)
  could force mid-implementation rework if the field-free "abort-only"
  scope proves too narrow once routing is attempted.
- Test coverage: no test yet exercises the new `_check_cost_ceiling` path
  end-to-end; the issue points at `TestExecutorRssBudget`
  (`scripts/tests/test_host_guard.py:509-573`) as the pattern to follow,
  but that test still needs to be authored from scratch.

## Status

**Open** | Created: 2026-08-30 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-08-30T20:21:21 - `2728ce43-8a34-4c85-a85c-d62c320e9372.jsonl`
- `/ll:confidence-check` - 2026-08-30T20:12:02 - `0689d759-b3b6-42ca-983c-618fccd6cc96.jsonl`
- `/ll:verify-issues` - 2026-08-30T20:06:44 - `a1ad8a57-f920-432c-8aa4-c8eaf847f8b7.jsonl`
- `/ll:wire-issue` - 2026-08-30T20:01:49 - `a1ad8a57-f920-432c-8aa4-c8eaf847f8b7.jsonl`
- `/ll:refine-issue` - 2026-08-30T19:56:19 - `a1ad8a57-f920-432c-8aa4-c8eaf847f8b7.jsonl`
