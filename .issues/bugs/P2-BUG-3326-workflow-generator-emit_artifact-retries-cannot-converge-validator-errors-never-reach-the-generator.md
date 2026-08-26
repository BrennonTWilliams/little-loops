---
id: BUG-3326
type: BUG
title: 'workflow-generator emit_artifact retries cannot converge: validator errors
  never reach the generator'
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T17:33:29Z'
completed_at: '2026-08-26T22:04:16Z'
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3326: workflow-generator emit_artifact retries cannot converge: validator errors never reach the generator

## Summary

`workflow-generator`'s `emit_artifact` retry loop cannot converge on deterministic
faults. `validate_artifact` runs `ll-loop validate` and discards its stderr, and
`emit_artifact`'s prompt reads only `intent.yaml` and `graph-routed.yaml` — so the
validator's error text never reaches the generator. All three retries re-read
identical unchanged inputs and produce byte-identical output.

Observed in run `2026-08-26T171218-workflow-generator`: iterations 14 and 17 failed
with the same 12 errors, ~$0.15 and ~4 minutes spent on draws from an unchanged
distribution. `max_emit_retries` only buys anything for *nondeterministic* emission
errors.

## Current Behavior

```yaml
validate_artifact:
  action: |
    ll-loop validate "${captured.run_dir.output}/workflow.yaml"
```

stderr goes to the runner log; nothing is persisted for the next `emit_artifact`
pass to read.

## Steps to Reproduce

1. Run `workflow-generator` on a brief that causes `emit_artifact` to produce a
   `workflow.yaml` with a deterministic structural fault (e.g. a state missing a
   required `evaluate` companion field).
2. `validate_artifact` runs `ll-loop validate` against the emitted artifact; it
   fails and discards stderr.
3. `count_emit_retry` routes back to `emit_artifact` under `max_emit_retries`.
4. Observe: `emit_artifact`'s prompt re-reads only `intent.yaml` and
   `graph-routed.yaml` (unchanged), so each retry regenerates the same fault and
   the loop exhausts its retry budget without converging.

## Expected Behavior

1. `validate_artifact` tees `ll-loop validate` output to
   `${captured.run_dir.output}/.emit_errors.txt` while preserving its exit status
   (the `exit_code` evaluator depends on it) **and** leaving the error text visible
   in the runner log, then truncates that file on a zero exit status so
   "non-empty" means "the previous attempt failed" (the validator prints a
   success block to stdout, so `tee` alone does not clear it).
2. `emit_artifact`'s prompt instructs: if `.emit_errors.txt` exists and is
   non-empty, read it first and fix every listed error specifically.
3. `validate_evaluators` is extended to check evaluator field *values*, not just
   field *presence* — importing `VALID_OPERATORS` alongside the tables it already
   imports — so that every `.evaluate:`-pathed fault is caught at the state that
   owns it, and the residual `.evaluate:` faults reaching `validate_artifact` are
   emitter-owned by construction. The check must fire **wherever an `operator`
   value is non-`None`**, not only where `EVALUATOR_REQUIRED_FIELDS` requires
   one and not merely wherever the key exists — see Operator-check scope below.
   `count_emit_retry` keeps its flat
   `on_yes: emit_artifact` edge.

Point (3) is the substantive design work. See the Rejected Alternative below for
why fault-class routing from `count_emit_retry` to `attach_evaluators` — the
original proposal — is the wrong shape now that `validate_evaluators` is fixed.

## Motivation

`max_emit_retries` is spent budget: on a deterministic fault it burns real
time and API cost (~$0.15 / ~4 min per unproductive retry pair observed in the
source run) while never converging, and the run still fails at the end —
strictly worse than failing fast on the first attempt. Fixing this makes the
retry mechanism actually do what its name promises.

## Proposed Solution

1. `validate_artifact` tees `ll-loop validate` output to
   `${captured.run_dir.output}/.emit_errors.txt` while preserving its exit
   status, using the established `pipefail` + `tee` idiom (idiom (a) in the
   Convention check below):
   ```yaml
   validate_artifact:
     action: |
       set -o pipefail
       ll-loop validate "${captured.run_dir.output}/workflow.yaml" 2>&1 \
         | tee "${captured.run_dir.output}/.emit_errors.txt"
       RC=$?
       [ "$RC" -eq 0 ] && : > "${captured.run_dir.output}/.emit_errors.txt"
       exit "$RC"
   ```
   `set -o pipefail` makes the pipeline's exit status that of `ll-loop
   validate`, so `RC` — and therefore the `exit_code` evaluator — still sees
   the real result. A bare `cmd 2>file` also preserves the exit code but
   *removes the error text from the runner log*, which is where a run is
   triaged post-mortem — prefer the pipeline. **Verified:** `ll-loop validate`
   writes its error block to **stderr** via `Logger.error`
   (`scripts/little_loops/logger.py:97`), so `2>&1` is required — the failure
   path prints nothing on stdout.

   Do **not** wrap the validator as `if ll-loop validate ...; then` — that
   shape discards the real exit code, and it is the same construct that
   silently disables 429/rate-limit detection elsewhere in this codebase.

   **The explicit truncate-on-success line is load-bearing — `tee` alone does
   not self-clear.** An earlier draft of this issue asserted that a successful
   validation leaves `.emit_errors.txt` empty. That is **false**: `ll-loop
   validate` prints a multi-line success block to **stdout** on the happy path
   (verified against the current tree):

   ```
   [16:33:57] scripts/little_loops/loops/workflow-generator.yaml is valid
     States: init, capture_intent, ...
     Initial: init
     Max steps: 30
   ```

   Under `2>&1 | tee` that block lands in `.emit_errors.txt`, leaving it
   non-empty on success. Hence the `[ "$RC" -eq 0 ] && : > ...` branch, which
   makes "non-empty ⇒ the immediately preceding attempt failed" true by
   construction. Do **not** add an `rm` step; do **not** remove the truncate
   branch as a "simplification".

   **Staleness caveat.** Self-clearing only holds on paths that actually reach
   `validate_artifact`. `emit_artifact` is also entered from `validate_routing`
   on the first pass, and a run that re-enters `emit_artifact` without an
   intervening `validate_artifact` would read a `.emit_errors.txt` describing a
   prior artifact. Apply **both** mitigations — they cover different paths and
   neither subsumes the other:
   - **(a)** truncate the file in `init` (`: > "$DIR/.emit_errors.txt"`). One
     line; covers the first-pass `validate_routing -> emit_artifact` entry, and
     covers a reused `run_dir` carrying a file from a prior *run*.
     **Verified:** `emit_artifact` has exactly two inbound edges —
     `validate_routing.on_yes` (line 277) and `count_emit_retry.on_yes`
     (line 344) — so (a) plus the truncate-on-success branch between them
     cover every path into the state. (b) remains as defense in depth.
   - **(a′) Reset `.emit_retry_count` in the same `init` line group**
     (`rm -f "$DIR/.emit_retry_count"`). `count_emit_retry` persists its
     counter to the same `run_dir` and nothing ever clears it, so the reused-
     `run_dir` argument that justifies (a) applies identically here — and the
     consequence is worse: a stale count at or above `max_emit_retries` sends
     the *first* failure straight to `diagnose` with zero retries, which is
     strictly worse than the non-convergence this issue fixes. One line,
     same state, same staleness class.
   - **(b)** phrase `emit_artifact`'s prompt so the file is advisory ("if it
     exists and is non-empty, treat it as the errors from your previous
     attempt") rather than authoritative — the only protection against a path
     neither (a) nor the truncate branch enumerates.
2. `emit_artifact`'s prompt instructs: if `.emit_errors.txt` exists and is
   non-empty, read it first and fix every listed error specifically before
   re-emitting.
3. `validate_evaluators`
   (`scripts/little_loops/loops/workflow-generator.yaml:202`) is extended to
   validate evaluator field *values*, not just presence: import
   `VALID_OPERATORS` (already exported from
   `scripts/little_loops/fsm/validation/__init__.py:51`, defined at
   `_base.py:74` as `{"eq", "ne", "lt", "le", "gt", "ge"}`) alongside the
   `EVALUATOR_REQUIRED_FIELDS` / `NON_LLM_EVALUATOR_TYPES` it already imports,
   and assert membership wherever `ev.get("operator") is not None` (see
   Operator-check scope below).
   Its terminal skip is left **unchanged** — see Terminal skip below.
   `count_emit_retry` (line 329) is left unchanged.

### Operator-check scope — present, not required

The intermediate gate must mirror the terminal gate's predicate exactly, or this
issue reintroduces the very laundering topology it exists to close.

`_validate_evaluate` in
`scripts/little_loops/fsm/validation/structural_rules.py:115` reads:

```python
if evaluate.operator is not None and evaluate.operator not in VALID_OPERATORS:
```

— i.e. it validates the operator whenever one is **present**, regardless of the
evaluator type. Restricting the intermediate check to types whose
`EVALUATOR_REQUIRED_FIELDS` entry *lists* `operator` (only `output_numeric` and
`output_json`) makes it a proper subset of the terminal gate: an
`output_contains` or `exit_code` evaluator carrying a stray
`operator: "greater"` passes `validate_evaluators`, propagates through
`resolve_routing` and `emit_artifact`, and first surfaces at
`validate_artifact` — where `count_emit_retry` routes back to `emit_artifact`, a
state structurally incapable of repairing an `attach_evaluators` defect. That is
the exact failure shape described in FEAT-3328's Summary, relocated one field
over.

Implement as: for every evaluator, check the operator whenever an `operator`
value is present. Presence, not requiredness, is the trigger.

**Mirror the terminal predicate exactly: `is not None`, not `in`.** The
terminal gate's test is `evaluate.operator is not None`. An intermediate gate
written as `if 'operator' in ev:` is *stricter* than the terminal gate: an
`output_contains` evaluator carrying an explicit `operator: null` has the key
present, so the intermediate gate rejects an artifact `ll-loop validate` would
accept. That routes to `attach_evaluators` on a non-defect — and
`validate_evaluators`'s `on_no` edge carries no retry counter, so the loop
oscillates until `max_steps`. This is the laundering failure inverted, and it
is just as unreachable-by-retry. Use `ev.get('operator') is not None`.

**Quoting — the gate body is inside a double-quoted shell string.**
`validate_evaluators`'s Python runs as `python3 -c "` … `"`
(`workflow-generator.yaml:209`), so every Python string literal in it must use
single quotes, and any f-string quote must be escaped `\"` — the existing lines
in that gate all do. A naive `if "operator" in ev: assert ev["operator"] in
VALID_OPERATORS` terminates the shell string and is a syntax error. Write it as:

```python
op = ev.get('operator')
if op is not None:
    assert op in VALID_OPERATORS, f\"state {s.get('name')!r} has invalid operator {op!r}\"
```

### Terminal skip — leave the name-keyed skip alone

`validate_evaluators` skips terminals **by name**:

```python
if s.get('name') in ('done', 'failed'):
    continue
```

An earlier draft of this issue read that as a mismatch against `ll-loop
validate` (which keys on `terminal: true`) and proposed widening the skip to
`s.get('terminal') is True or s.get('name') in ('done', 'failed')`. **Do not
do that.** Verified against the current tree, the widening is a dead branch
that opens a new laundering hole:

- **The key does not exist at that stage.** `graph-evaluators.yaml`'s schema
  is set by `attach_evaluators`'s prompt (`workflow-generator.yaml:184-198`),
  which emits `name` / `purpose` / `kind` / `evaluate` only. `terminal: true`
  is introduced four states later, at `emit_artifact`'s SHAPE FLIP. So
  `s.get('terminal') is True` can never fire in this gate.
- **The failure it claims to prevent is unreachable.** `validate_sketch`
  (`workflow-generator.yaml:128`) hard-asserts `'done' in names` and
  `'failed' in names`. A sketch whose terminals are named `aborted` /
  `succeeded` is rejected two states earlier and routed back to
  `sketch_state_graph`; it cannot reach `validate_evaluators` at all. The
  name-keyed skip is therefore *consistent with the pipeline's own upstream
  invariant*, not a drift from it.
- **It would be actively harmful if the key ever did appear.** An emitter that
  stamps `terminal: true` onto a work state would have that state's evaluator
  skipped entirely and laundered downstream to `validate_artifact` — where
  `count_emit_retry` routes back to `emit_artifact`, a state structurally
  incapable of repairing an `attach_evaluators` defect. That is precisely the
  topology this issue exists to close.

The new `VALID_OPERATORS` assertion inherits the existing name-keyed skip
unchanged. No skip change is part of this issue.

### Rejected Alternative — fault-class routing to `attach_evaluators`

The original proposal had `count_emit_retry` grep `.emit_errors.txt` for
`\.evaluate:` and route those faults back to `attach_evaluators`, reusing
`validate_evaluators`'s existing `on_no` edge (line 231). That was drafted
against the pre-fix world and is now the wrong shape:

- **The class it targets no longer reaches `validate_artifact`.**
  `validate_evaluators` already imports `EVALUATOR_REQUIRED_FIELDS` and
  `NON_LLM_EVALUATOR_TYPES` and checks *both* type membership and companion-
  field completeness (the gate-completeness fix referenced in Notes). A
  missing-companion-field defect — the source incident's actual fault — is
  caught at `attach_evaluators` and cannot surface downstream any more.
- **The residual `.evaluate:` faults are emitter-owned.** What can still reach
  `validate_artifact` on that path is `emit_artifact` dropping or mangling
  evaluator fields during the documented `states:` list→mapping SHAPE FLIP.
  Routing those to `attach_evaluators` blames the wrong state.
- **It discards two passes of work.** `attach_evaluators` re-reads
  `graph-sketch.yaml` and rewrites `graph-evaluators.yaml`, so
  `resolve_routing`'s `graph-routed.yaml` is regenerated too — the routing
  pass re-runs for a transcription bug.
- **It reintroduces this very bug one state over.** `attach_evaluators`'s
  prompt reads only `graph-sketch.yaml`. Routed there without also being told
  to read `.emit_errors.txt`, it regenerates byte-identical evaluators — the
  exact non-convergence this issue exists to fix, relocated.

The one genuine `attach_evaluators`-owned class that *does* survive the
current gate is **invalid field values**: `validate_evaluators` checks that
`operator` is present, not that it is a legal operator, so
`operator: "greater"` passes the gate and fails at `ll-loop validate` with an
`.evaluate:`-pathed error. Fixing that upstream (Proposed Solution step 3) is
strictly smaller than a classification state, keeps the fix at the state that
owns the fault, and applies the same import-don't-restate principle FEAT-3328
proposes to lint for.

Fault-class retry routing for `count_emit_retry` is therefore an explicit
**non-goal** of this issue.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — `validate_artifact`
  (line 315), `emit_artifact` (line 280), `validate_evaluators` (line 202),
  and `init` (lines 43-56, the two-line `.emit_errors.txt` truncation and
  `.emit_retry_count` removal per the Staleness caveat, mitigations (a) and
  (a′)). Placement inside `init` is constrained on both sides: the two lines
  must come **after** `mkdir -p "$DIR"` — `init` creates the run dir in the
  same action, so a truncate above it writes into a nonexistent directory —
  and **before** the `case`/`echo` block, which must stay last because
  `init`'s stdout is the `capture: run_dir` contract. Neither line emits
  stdout, so the contract is otherwise undisturbed.
  `count_emit_retry` (line 329) is **not** modified — see Rejected Alternative.
  Also `max_steps` (line 31) — set to `40`, see Step-budget interaction.

### Dependent Files (Callers/Importers)
- N/A — loop is invoked by ID via the FSM runner, not imported

### Similar Patterns
- `validate_evaluators` (line 202) already fixed its own gate-gap by
  *importing* the terminal validator's tables rather than restating them —
  that import-don't-restate move is the pattern step 3 extends to
  `VALID_OPERATORS`.
  ~~its fault-class routing to `attach_evaluators` (line 231) is the pattern
  `count_emit_retry` should reuse~~ — **superseded**; see Rejected Alternative.
  `count_emit_retry` keeps its flat edges.
- `capture_intent`/`validate_intent` (lines 58, 82) have an analogous
  unfenced-input issue tracked separately in BUG-3327

### Tests
- `scripts/tests/test_builtin_loops.py` — add/extend cases asserting
  `workflow-generator.yaml` validates, that `validate_artifact` persists
  validator output to `.emit_errors.txt` while preserving its exit code, and
  that `validate_evaluators` rejects an invalid `operator` value

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestWorkflowGeneratorLoop`
  (class starts line 17684) currently has no test pinning
  `count_emit_retry`'s `on_yes`/`on_no` targets or `validate_artifact`'s
  `on_no` target — a genuine gap since the class otherwise asserts routing
  edges for every other gated state. Add a dict-lookup test following
  `test_shrink_gated_by_context_flag`/`test_promotion_gated_by_auto_promote_flag`
  (lines 17759-17772) pinning `count_emit_retry`'s edges as
  `on_yes: emit_artifact` / `on_no: diagnose` — a *regression guard against
  the Rejected Alternative*, so a future author re-adds fault-class routing
  deliberately rather than by drift.
- Extend `test_validate_evaluators_enforces_required_companion_fields` (lines
  17837-17864) — or add a sibling in the same behavioral subprocess shape —
  covering the new `VALID_OPERATORS` value check. **Two cases, not one**, per
  Operator-check scope:
  (i) an `output_json` evaluator (type *requires* `operator`) carrying
  `operator: "greater"` must exit non-zero;
  (ii) an `output_contains` evaluator (type does **not** require `operator`)
  carrying a stray `operator: "greater"` must **also** exit non-zero. Case (ii)
  is the regression guard against the required-only subset formulation — it is
  the case `structural_rules.py:115` catches and a requiredness-keyed
  intermediate gate would launder.
  (iii) an `output_contains` evaluator carrying an explicit `operator: null`
  must exit **zero**. This is the over-strictness guard: `structural_rules.py:115`
  tests `is not None`, so a `'operator' in ev` formulation would reject an
  artifact the terminal validator accepts and wedge the unbounded
  `validate_evaluators -> attach_evaluators` edge. Cases (ii) and (iii) are a
  couple — neither alone pins the predicate.
- Add a behavioral test for `validate_artifact`'s capture: run the extracted
  action against a `tmp_path` run dir containing a deliberately invalid
  `workflow.yaml`, assert `returncode != 0` **and** that
  `.emit_errors.txt` is non-empty and contains the validator's error text;
  then against a valid one, assert `returncode == 0` and the file is empty.
  **Label the second case as pinning the truncate-on-success branch, not
  `tee` behavior** — `ll-loop validate` prints a success block to stdout, so
  `tee` alone leaves the file non-empty (see Proposed Solution step 1). Without
  that label the test reads as an accident and a future author deletes the
  `[ "$RC" -eq 0 ] && : > ...` line as redundant.
- Add a behavioral test for `init`'s reset lines (mitigations (a)/(a′)): seed
  a `tmp_path` run dir with a non-empty `.emit_errors.txt` and a
  `.emit_retry_count` of `9`, run the extracted `init` action, and assert both
  are cleared **and** that the action's stdout is still exactly the run-dir
  path — the `capture: run_dir` contract is what constrains where those lines
  may go.
- `scripts/tests/test_builtin_loops.py::test_pipeline_states_exist` (line
  17725, `required` set includes `count_emit_retry` at 17738) — no change
  needed; no new state is introduced by this issue.

### Documentation
- N/A — `count_emit_retry`'s topology is unchanged, so the existing docs stay
  accurate.

_Wiring pass added by `/ll:wire-issue` — superseded:_
- ~~`docs/guides/LOOPS_REFERENCE.md` (~line 2659) and `docs/reference/loops.md`
  (~line 152) need a clause for a new fault-class exit to
  `attach_evaluators`.~~ Both descriptions (`count_emit_retry` falls back to
  `diagnose`; `max_emit_retries` bounds `emit_artifact` retries) remain
  correct under the revised solution — no doc change needed. Re-check these
  two spots only if the Rejected Alternative is ever revived.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- Confirmed current line numbers match the issue exactly: `validate_artifact` (315), `emit_artifact` (280), `count_emit_retry` (329), `validate_evaluators` (202) with its `on_no: attach_evaluators` edge at line 231 (the `attach_evaluators` state header itself is at line 145 — the issue's "line 231" citation refers to the routing edge, not the state header).
- Full state pipeline order (all under `${captured.run_dir.output}`, set in `init` via `capture: run_dir`): `init → capture_intent → validate_intent → sketch_state_graph → validate_sketch → attach_evaluators → validate_evaluators → resolve_routing → validate_routing → emit_artifact → validate_artifact → count_emit_retry`.
- `count_emit_retry`'s current shell action is a pure retry-budget counter (persists `.emit_retry_count`, compares against `${context.max_emit_retries}`, default `3` — defaulted twice: once in `context:` at line 39, once again inline in the shell script). It performs no branching on *why* validation failed — `on_yes: emit_artifact`, `on_no: diagnose`. `diagnose` is a `prompt` state with `next: failed` and no `on_error` handling (contrast: `finalize_await_confirmation` does declare `on_error: failed`).
- `validate_evaluators`'s fault-class routing works because its shell action is a `python3 -c` snippet that imports `NON_LLM_EVALUATOR_TYPES`/`EVALUATOR_REQUIRED_FIELDS` directly from `little_loops.fsm.validation` (not restated), asserts membership/field-completeness, and its single `on_no: attach_evaluators` edge routes straight back to the one state that owns that one fault class — there is no separate "count" state interposed. ~~Reusing this edge for `count_emit_retry` means inserting a classification step between `validate_artifact` and `count_emit_retry` (or inside `count_emit_retry` itself) that greps the captured error text for a fault-class signature before deciding `emit_artifact` vs `attach_evaluators`.~~ **Superseded** — that classification step is the Rejected Alternative and is an explicit non-goal. The research above is retained only as the reason the *upstream* fix (step 3) is the right shape: `validate_evaluators` already owns this fault class, so it should be made complete rather than have downstream states route back to it.
  Note also that `validate_evaluators`'s `on_no: attach_evaluators` edge is itself **unbounded** — no retry counter guards it. Step 3 must therefore not make that gate stricter than the terminal validator (see "Mirror the terminal predicate exactly" above), or a non-defect wedges the loop.

### Convention check — stderr capture and fault-class routing
- No loop YAML in `scripts/little_loops/loops/` uses the literal `cmd 2>file; exit $?` one-liner the issue proposes. Two established idioms exist instead: (a) `cmd 2>&1 | tee file` combined with `set -o pipefail` (e.g. `fix-quality-and-tests.yaml:62-64`, `test-coverage-improvement.yaml`, `dead-code-cleanup.yaml`, `autodev.yaml`, `rn-remediate.yaml`), or (b) stderr-only redirect to a file plus explicit `$?` capture into a shell variable, used when the state needs to branch on the result rather than just log it (e.g. `vega-viz.yaml:298-320`, `cli-anything-bootstrap.yaml:271-279,324-325`). Idiom (b) is the closer structural match to what `validate_artifact` needs (preserve exit code for the `exit_code` evaluator while also persisting stderr for the next state to read).
  **Decision:** use idiom (a) (`set -o pipefail` + `2>&1 | tee`) anyway. Idiom (b)'s bare `2>file` redirect satisfies the next state but strips the validator's error text out of the runner log, which is where a failed run is actually triaged. `pipefail` makes the pipeline's status that of `ll-loop validate`, so the "a pipeline swallows the exit code" concern in the original Expected Behavior does not apply — it is only true *without* `pipefail`. Idiom (a) is used here **augmented** with an explicit truncate-on-success branch, because `ll-loop validate` prints a success block to stdout and a bare `tee` would leave the capture file non-empty on the happy path (see Proposed Solution step 1).
  **`pipefail` availability verified:** the FSM executes every `action_type:
  shell` body via `["bash", "-c", action]` (`scripts/little_loops/fsm/runners.py:297`),
  not `sh`, so `set -o pipefail` is guaranteed available. No POSIX-sh fallback
  is needed.

### Step-budget interaction — `max_steps: 30`

`workflow-generator` declares `max_steps: 30` (line 31) across 24 states. The
happy path with `enable_shrink` already consumes ~20 steps, and the shrink loop
(`shrink_select_candidate -> shrink_try_remove -> shrink_probe_candidate ->
shrink_apply -> shrink_select_candidate`) iterates once per candidate.

This issue changes the economics of that budget. Today a full retry cycle
(`emit_artifact -> validate_artifact -> count_emit_retry`, 3 steps x
`max_emit_retries: 3` = 9 steps) is pure waste, because the retries are
byte-identical draws. After this fix the retries become *productive* — which
means real runs will now actually spend those 9 steps making progress instead
of failing identically on the first pass.

Consequence: a run that previously died at `diagnose` with 12 identical errors
can now die at `max_steps` instead, which reads the same in a run log.

**Decision — set `max_steps: 40`** (20 happy-path + 9 retry cycle + shrink
headroom). This is no longer conditional and is not deferred to sequencing:
an earlier draft had this issue and BUG-3327 each say "whichever lands second
owns the final number", which is a coordination bug that yields either two
conflicting edits or none. The numbers are now assigned per-issue:

| Issue | `max_steps` | Why |
|---|---|---|
| BUG-3326 (this) | `40` | +9 productive retry steps |
| BUG-3327 | `45` | headroom over `40` for its `count_intent_retry` counter state and for FEAT-3332's gate |

Land in issue order. If BUG-3327 lands first for any reason, it sets `45`
directly and this issue's step 4 becomes a no-op verification that the value
is at least 40 — not a downgrade to 40.

_BUG-3327's `45` was originally justified as "+1 state per pass from
FEAT-3332's gate, plus a bounded retry edge". FEAT-3332 was split out and is
not landing with it, so that row is re-stated above as plain headroom. The
number is unchanged; only its rationale moved._

**Note (out of scope for this issue, do not fix here):** `max_steps` remains
under-budgeted for the shrink pass at `40` *or* `45`.
`shrink_select_candidate -> shrink_try_remove -> shrink_probe_candidate ->
shrink_apply` costs 4 steps per candidate, once per state of the **generated**
loop, so a 10-state artifact needs ~40 steps for shrink alone on top of the
~20-step happy path. Latent today (`enable_shrink` defaults `false`). Recorded
so the next `max_steps` bump is not re-derived from scratch; a real fix means a
shrink-specific budget or a candidate cap, not a larger constant.
_The two bullets below surveyed fault-class routing precedent for the **Rejected
Alternative**. Retained for the record only — this issue adds no fault-class
routing. Consult them only if that alternative is ever revived._
- ~~Fault-class routing on a retry edge (grep prior output for a discriminator, route on `output_contains`) is an established, repeated pattern elsewhere: `lib/common.yaml:332-354` (`ll_auto_auth_check`), `lib/common.yaml:355-386` (`ll_auto_learning_gate_check`, three-way classification via sequential grep), and `cua-agent-desktop.yaml:344-391` (a full `_check_*`/`_route_*` chain, with an explicit comment noting this exists specifically because a flat retry edge would otherwise mask a distinct fault class).~~
- ~~Contrast case: `cli-anything-bootstrap.yaml:490-506` (`count-refine-cycle`) is structurally identical to `workflow-generator.yaml`'s current `count_emit_retry` — a flat, fault-agnostic counter with no discrimination. This confirms fault-class discrimination is consistently implemented as an *additional* layer on top of the counter shape, not folded into the counter state itself, in every codebase example that has it.~~ The `cli-anything-bootstrap` contrast case is still the correct model: `count_emit_retry` stays a flat, fault-agnostic counter.

### Prompt convention — reading a prior error file
- The "if `<path>` exists and is non-empty, read it first" phrasing is an established, near-identical convention repeated verbatim across generator-family loops (`svg-image-generator.yaml:75-76`, `hitl-md.yaml:170`, `openscad-model-generator.yaml:97`, `pixi-data-viz.yaml:133`, `canvas-sketch-generator.yaml:126`, `pixi-generative-art.yaml:101`, `html-website-generator.yaml:70`, `generative-art.yaml:98`) and `rn-refine.yaml:438-441`/`general-task.yaml:987-989` for triage-style reads. `emit_artifact`'s prompt should follow this exact phrasing convention rather than inventing new wording.

### Test shape conventions
- `scripts/tests/test_builtin_loops.py` has two established shapes for this kind of assertion: a static dict-lookup shape for routing-target assertions (`test_shrink_gated_by_context_flag`, `test_promotion_gated_by_auto_promote_flag` — `data["states"][name].get("on_yes"/"on_no")` equality checks), and a behavioral subprocess-execution shape for proving a shell gate's logic actually discriminates (`test_validate_evaluators_enforces_required_companion_fields` — extracts the action string, substitutes a `tmp_path` fixture, runs it via `subprocess.run(["bash", "-c", action], ...)`, asserts on `returncode`/`stderr`). ~~A new test for `count_emit_retry`'s fault-class routing should follow the behavioral shape since the point is proving the grep-based discrimination works, not just that a YAML key has a given value.~~ **Superseded** — there is no fault-class routing to test. Use the two shapes as follows: the *static dict-lookup* shape for pinning `count_emit_retry`'s unchanged edges (a regression guard against the Rejected Alternative), and the *behavioral subprocess* shape for the two gates whose logic actually changes (`validate_artifact`'s tee/exit-code capture and `validate_evaluators`'s operator check).

## Program Design

### Signatures

- `validate_artifact() -> int` — shell action, tees `ll-loop validate`'s
  merged output to `${captured.run_dir.output}/.emit_errors.txt` under
  `set -o pipefail`, truncates that file when the captured exit code is zero,
  and re-raises the validator's exit code
- `validate_evaluators() -> int` — shell action, gains a
  `VALID_OPERATORS`-membership assertion for every evaluator whose `operator`
  is not `None`, whether or not that type requires one — exactly mirroring
  `structural_rules.py:115`'s `operator is not None` predicate, neither
  narrower (requiredness-keyed) nor wider (`'operator' in ev`); its
  name-keyed terminal skip is unchanged
- `count_emit_retry() -> int` — **unchanged**; edges stay
  `on_yes: emit_artifact` / `on_no: diagnose`

### Call Path

`attach_evaluators` -> `validate_evaluators` (now also rejects invalid
`operator` values, so evaluator-owned faults never escape this gate) ->
... -> `emit_artifact` (reads `.emit_errors.txt` when non-empty) ->
`validate_artifact` (writes `.emit_errors.txt`) -> `count_emit_retry` ->
`emit_artifact` under the budget, `diagnose` once exhausted

## Implementation Steps

1. Add output capture to `validate_artifact` (`set -o pipefail` + `2>&1 |
   tee`, then `RC=$?`, the truncate-on-success branch, and `exit "$RC"`),
   plus the `init` lines — mitigations (a) and (a′) — from the Staleness
   caveat: `: > "$DIR/.emit_errors.txt"` and `rm -f "$DIR/.emit_retry_count"`,
   placed after `mkdir -p "$DIR"` and before the `case`/`echo` block.
2. Update `emit_artifact`'s prompt to read and address `.emit_errors.txt`,
   using the established "if `<path>` exists and is non-empty, read it first"
   phrasing (see Prompt convention below), worded advisorily per mitigation
   (b) ("treat it as the errors from your previous attempt").
3. Extend `validate_evaluators` to import `VALID_OPERATORS` and assert
   operator-value membership for every evaluator where `operator` is
   **non-None** (see Operator-check scope — including both the `is not None`
   predicate and the single-quote requirement, since the gate body sits inside
   a double-quoted `python3 -c "…"` string). Leave that gate's name-keyed
   terminal skip **exactly as it is** — see Terminal skip.
4. Set `max_steps: 40` (see Step-budget interaction below).
5. Verify with `ll-loop validate scripts/little_loops/loops/workflow-generator.yaml`
   and a re-run of the source scenario (or an equivalent fixture) to confirm
   retries now converge or fail fast on genuinely emitter-owned faults.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/loops/workflow-generator.yaml`'s `diagnose`
  prompt (lines 582-595) — its "read whichever of these exist" file list
  (`intent.yaml, graph-sketch.yaml, graph-evaluators.yaml, graph-routed.yaml,
  workflow.yaml, .emit_retry_count`) does not include `.emit_errors.txt`; add
  it so the terminal diagnostic path sees the new artifact.
- Update `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop` —
  add the `count_emit_retry` edge-pinning guard, the `VALID_OPERATORS`
  behavioral case, and the `validate_artifact` capture test, per the Tests
  subsection above.
- No documentation changes — see the Documentation subsection.

## Impact

- **Priority**: P2 — retries silently waste cost/time on every workflow-generator
  run that hits a deterministic validator fault, and never actually recovers
- **Effort**: Small — four localized changes to one loop YAML (`init`,
  `emit_artifact`, `validate_artifact`, `validate_evaluators`), no new
  primitives, no new states, no routing changes
- **Risk**: Low — changes are confined to two shell actions and one prompt;
  the control-flow graph is untouched, and the new `VALID_OPERATORS` check
  imports an already-exported table rather than restating one
- **Breaking Change**: No

## Notes

Companion to the gate-completeness fix already landed on `validate_evaluators`,
which moves *evaluator* faults upstream so they never reach this retry. This issue
covers the residual fault classes that legitimately belong to `emit_artifact`,
and finishes the upstream move by closing the one evaluator-owned gap that fix
left open (field *values*, not just field presence).

Implementation ordering: land this issue before FEAT-3328. Its
`VALID_OPERATORS` change is the same import-don't-restate move FEAT-3328 lints
for, and FEAT-3328's AC #3 ("zero violations against the current built-in loop
set") assumes a clean tree.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §2.5, §5 R3.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-26T22:04:05 - `3839dbf2-bb80-4473-88ee-4f1947f0d277.jsonl`
- `/ll:confidence-check` - 2026-08-26T20:09:17 - `fdfe1063-50b8-41a2-aae7-c524a32eadad.jsonl`
- `/ll:wire-issue` - 2026-08-26T19:21:20 - `3b6a461b-67ff-4f6b-9949-d834388d9cff.jsonl`
- `/ll:refine-issue` - 2026-08-26T19:14:21 - `0809cdb6-a88f-42a7-9e51-e57ee8a63f3a.jsonl`
- `/ll:format-issue` - 2026-08-26T19:09:04 - `8c47cf34-66af-4a75-8c4b-c7a8efe5d7ec.jsonl`
