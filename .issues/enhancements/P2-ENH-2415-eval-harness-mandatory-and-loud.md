---
id: ENH-2415
title: Make rn-build eval harness mandatory and loud (no silent skip to done)
type: ENH
priority: P2
status: done
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
completed_at: '2026-07-28T15:43:29Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Medium
relates_to:
- EPIC-2412
- FEAT-2413
- FEAT-2414
labels:
- loops
- verification
- greenfield
- rn-build
- eval-harness
confidence_score: 98
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 21
score_change_surface: 25
---

# ENH-2415: Make rn-build eval harness mandatory and loud (no silent skip to done)

## Summary

`rn-build`'s only real code-execution gate — the eval harness — is optional,
LLM-installed, and **silently degrades to "no verification / done"** on every
absence or error path. Change the routing so a missing or crashed harness routes to a
non-success terminal (`build_failed`), never silently to `done`. The strongest
verification the pipeline has should not be the easiest thing to skip.

## Current Behavior

`eval_harness` is an LLM prompt that installs one of the harness templates. On its
failure or absence:

- `check_harness_name` routes `on_no`/`on_error` → `synthesize_result` (bypasses eval).
- `eval_gate` runs `loop: "${captured.harness_name.output}"`; empty name previously
  crashed (BUG-2013) and now routes `on_error` → `synthesize_result`.
- `resume` without `resume_harness` warns "Eval gate will be SKIPPED" but still
  proceeds to `synthesize_result`.
- `synthesize_result` terminates `done` for all four outcomes.

Net: build results can be reported `done` with zero verification.

## Expected Behavior

- If no harness can be resolved (given `resume_harness` → scan prior
  `.loops/runs/rn-build-*/harness-name.txt` → scan `.loops/*.yaml`), the run
  terminates at a `build_failed` (`success: false`) terminal with a loud reason and a
  `resume_command`, not `done`.
- A harness that crashes routes to `build_failed`, not `synthesize_result`-then-`done`.
- `synthesize_result` reserves `done` for runs where the eval gate (or the FEAT-2414
  acceptance phase) actually passed.
- A deliberate, explicit `--context skip_eval=true` is the ONLY way to bypass, and it
  still terminates non-`done` with `eval_skipped: true` in the JSON.

## Proposed Solution

1. Add a `build_failed` terminal (`success: false`) if not already reachable from all
   verification-bypass paths.
2. Repoint `check_harness_name` `on_no`/`on_error` and `eval_gate` `on_error` to a new
   `harness_missing` state that writes a crash/skip marker and routes to `build_failed`.
3. Gate the only silent-pass path behind an explicit `skip_eval` context flag.
4. Keep the existing loud resume warning but make it terminal-affecting.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/guides/LOOPS_REFERENCE.md` — rewrite the `resume_harness`-omitted
   prose (lines 731-733) and add a `skip_eval` row to the context-variables table.
6. Update `docs/reference/API.md` — add the `build_failed` terminal and `skip_eval`
   context var to the `rn-build` Key phases section (lines 9878-9918).
7. Update `scripts/tests/test_builtin_loops.py` — add structural routing assertions
   for the new `harness_missing`/`finalize_harness_missing` states, following the
   existing `check_substrate` assertion pattern.
8. Add a `CHANGELOG.md` entry for this behavior change during release prep (per
   project convention, in a versioned section, not `[Unreleased]`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`build_failed` already exists** — `scripts/little_loops/loops/rn-build.yaml:760-762`
(`terminal: true`, `failure: true`), reached via `finalize_build_failed`
(`rn-build.yaml:733-759`, a `finalize_*` shell state that writes a JSON payload
with `resume_command` then `next: build_failed`). It is currently reachable only
from `check_build_outcome`'s `on_no`/`on_error` (goal-cluster hard-crash,
`rn-build.yaml:600-604`) and from `synthesize_result`'s `on_error`
(`rn-build.yaml:719-720`, added by ENH-2825). **No path from the eval-harness gate
reaches it today** — this issue's change #2 is to add that path, not invent a new
terminal.

**Exact states to repoint** (`scripts/little_loops/loops/rn-build.yaml`):
- `check_harness_name` (lines 611-624): `on_no`/`on_error` currently → `synthesize_result`.
  ```yaml
  check_harness_name:
    action_type: shell
    action: |
      NAME="${captured.harness_name.output:default=}"
      if [ -z "$NAME" ]; then
        echo "no_harness"
        exit 1
      fi
      echo "$NAME"
    evaluate:
      type: exit_code
    on_yes: eval_gate
    on_no: synthesize_result      # ← repoint to harness_missing
    on_error: synthesize_result   # ← repoint to harness_missing
  ```
- `eval_gate` (lines 628-634): `on_error` currently → `synthesize_result` (indistinguishable
  from `on_yes`, a real pass).
  ```yaml
  eval_gate:
    loop: "${captured.harness_name.output}"
    timeout: 7200
    capture: eval_result
    on_yes: synthesize_result
    on_no: check_eval_retry_budget
    on_error: synthesize_result   # ← repoint to harness_missing
  ```
- `check_eval_retry_budget` (lines 636-651): `on_no` (retries exhausted) and `on_error`
  also both → `synthesize_result` today, same silent-done problem; in scope per the
  issue's intent ("A harness that crashes routes to `build_failed`") even though not
  explicitly named in Current Behavior.
- `synthesize_result` (lines 671-720): `on_yes`/`on_no`/`on_partial` all → `done`
  regardless of which upstream condition occurred; `eval_passed`/`eval_retry_count`
  are LLM-authored JSON fields, not read by any FSM `evaluate:`/routing construct, so
  they cannot gate the terminal today.

**`finalize_build_failed`/`build_failed` is the shape to reuse for the new
`harness_missing` path** — a `finalize_*` shell state writes the JSON payload
(`eval_passed: false`, `error`, `resume_command` built from
`$RUN_DIR/epic-id.txt` + `$RUN_DIR/harness-name.txt`), then `next: build_failed`.
The new `harness_missing` state (or a `finalize_harness_missing` following the same
pattern) can call `finalize_build_failed` directly via `next:`, or duplicate its
shape with a harness-specific `error` message — either satisfies "writes a
crash/skip marker and routes to `build_failed`."

**Precedent for the `skip_eval` context-flag gate** — `recursive-refine.yaml:80-81,
287-292` uses the exact idiom to copy:
```yaml
NO_RECURSION="${context.no_recursion:default=false}"
if [ "$NO_RECURSION" = "true" ]; then
  ...
  exit 0
fi
exit 1
```
`rn-build.yaml` itself already uses the sibling `:default=` idiom at line 614
(`NAME="${captured.harness_name.output:default=}"`). Apply the same shape:
`SKIP_EVAL="${context.skip_eval:default=false}"`, string-compared `= "true"`,
gating a still-non-`done` terminal per the Expected Behavior section (`eval_skipped:
true` in the JSON, not a silent pass to `done`).

**Loud-warning precedent already exists for the resume path** —
`resume_read_harness` (`rn-build.yaml:206-263`) already prints a `'=' * 64`-delimited
stderr banner ("WARNING: no eval harness found... Eval gate will be SKIPPED") when
its 4-step fallback scan (current run's `harness-name.txt` → prior
`rn-build-*` run's `harness-name.txt` → installed `.loops/harness-*.yaml` → give up)
finds nothing, then `sys.exit(0)` and continues silently to `done`. This issue's
Expected Behavior ("Keep the existing loud resume warning but make it
terminal-affecting") means: keep the banner text, but route to `harness_missing`/
`build_failed` afterward instead of continuing the pipeline.

**Harness-name resolution logic lives entirely in inline Python inside the YAML**
(`resume_read_harness` lines 206-263, `read_harness_name` lines 506-540 for the
non-resume path) — not in `scripts/little_loops/loops.py` or FSM executor code —
so no Python module changes are needed for the routing fix itself.

### Tests to update (`scripts/tests/test_rn_build.py`)

- `TestCheckHarnessNameGuard.test_check_harness_name_routes_to_synthesize_when_empty`
  (lines 215-222) currently asserts `on_no`/`on_error == "synthesize_result"` — this
  is the test that must be rewritten to assert the new `harness_missing` routing.
- `TestCheckBuildOutcomeGate` (lines 242-295) has the template to copy for asserting
  `build_failed`/`finalize_build_failed` shape (`terminal is True`,
  `"resume_command" in action`).
- `TestRnBuildResumeState` (lines 549-643) already has
  `test_resume_read_harness_emits_loud_warning_when_no_harness` asserting `"WARNING"`
  and `"SKIPPED"` in the action string — extend this class (or add a sibling) to
  assert the warning is now followed by non-`done` routing, satisfying "Existing
  resume tests (ENH-2016) updated to assert the new terminal" in Acceptance Criteria.
- `REQUIRED_STATES` (lines 22-46) needs the new `harness_missing` (and
  `finalize_harness_missing`, if added as a distinct state) state name added.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- No `loop: rn-build` references or Python state-name imports exist anywhere in the
  codebase — `rn-build` is a capstone orchestrator, never called as a sub-loop, and
  its FSM state names are YAML-only (not exported by any Python module). `loop-router.yaml`
  and `lib/composer.yaml` both explicitly `excludes.add('rn-build')` from dispatch
  candidacy, so neither reads its terminal/JSON outcome. No epic-orchestration or
  `ll-parallel`/`ll-sprint`/`ll-auto` code branches on `rn-build`'s `done` vs
  `build_failed` terminal today — the routing change has zero blast radius outside
  this file and its tests. [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — generic FSM validation harness that
  parses/validates every builtin loop including `rn-build.yaml`; already has a
  `check_substrate`-style assertion pattern (state on_yes/on_no/on_partial checks) to
  copy for new `check_harness_name`/`harness_missing`/`finalize_harness_missing`
  routing assertions. [Agent 1 + Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:731-733` — states "If `resume_harness` is omitted,
  `check_harness_name` will route directly to `synthesize_result` (no eval gate
  run)" — describes exactly the soft-skip behavior this issue removes; needs
  rewriting to describe the new `harness_missing`/`build_failed` routing. The
  "Context variables" table for `rn-build` (same file, lists `spec`,
  `max_eval_retries`, `resume_epic`, `resume_harness`) needs a new `skip_eval` row.
  [Agent 2 finding, confirmed by direct grep — `skip_eval` is not currently
  documented anywhere]
- `docs/reference/API.md:9878-9918` — `rn-build` "Key phases" section lists phases
  through `synthesize_result` but does not mention the `build_failed` terminal or
  any `skip_eval` context var; needs the new terminal/flag added. [Agent 2 + Agent 1
  finding, confirmed by direct grep]
- `scripts/little_loops/loops/README.md:140-141` and `docs/guides/LOOPS_GUIDE.md:89,381`
  — one-line `rn-build` descriptions omit failure terminals; lower-priority doc
  touch-up. [Agent 2 finding]
- `CHANGELOG.md` — every prior `rn-build` behavior change (ENH-2016, BUG-2013,
  ENH-2825) has a dedicated versioned bullet (never under `[Unreleased]` per project
  convention); ENH-2415 needs an equivalent bullet added during release prep.
  [Agent 2 finding]
- The `resume_read_harness` loud-warning banner text ("WARNING: no eval harness
  found... Eval gate will be SKIPPED", `rn-build.yaml` heredoc under the "Step 4: no
  harness found" comment) currently claims the gate "will be SKIPPED" — once
  `skip_eval` is gated and the default becomes a loud failure instead, this banner
  text itself must be updated to match the new semantics (in-file change, not a
  separate doc, since no external doc or test string-matches this exact banner
  text today). [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `TestRnBuildEvalGate.test_retry_budget_on_no_routes_to_synthesize`
  (`test_rn_build.py:358-362`) will break — it asserts
  `check_eval_retry_budget.on_no == "synthesize_result"`, which this issue
  explicitly repoints. [Agent 3 finding]
- `eval_gate.on_error` and `check_eval_retry_budget.on_error` currently have **no**
  dedicated routing assertion in `test_rn_build.py` (both are silently
  `synthesize_result` in the YAML with nothing pinning that value) — new tests are
  needed once these are repointed to `harness_missing`, not just updates to
  existing ones. [Agent 3 finding]
- `synthesize_result`'s `on_yes`/`on_no`/`on_partial` routing keys have **no**
  existing test asserting they equal `"done"` — making `done` conditional on
  `eval_passed` content is new test territory, modeled on
  `TestCheckBuildOutcomeGate`'s content-based-gate pattern (reads JSON content, not
  just the evaluator verdict, to pick `on_yes`/`on_no`). [Agent 3 finding]
- `skip_eval` context-flag gating has no existing analog in `test_rn_build.py`; model
  the new test on `test_resume_context_knobs_exist` (lines 552-561) for asserting
  the context default, plus a `check_harness_name`-style shell-guard test asserting
  the action references `${context.skip_eval:default=false}`. [Agent 3 finding]
- New terminal-shape tests for `harness_missing`/`finalize_harness_missing`,
  copying `TestCheckBuildOutcomeGate`'s four-test template exactly (routes-to-finalize,
  terminal-is-true, not-named-done, finalize-emits-resume_command). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` needs new structural assertions for the new
  state names, following its existing `check_substrate` on_yes/on_no/on_partial
  assertion pattern. [Agent 1 + Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- There is no central context-variable schema (`scripts/little_loops/config-schema.json`
  has no `context`/`--context` keys) — `skip_eval` only needs an entry in
  `rn-build.yaml`'s own `context:` block (mirroring the existing `resume_epic`/
  `resume_harness` inline-comment convention, lines 34-43) plus the corresponding
  `docs/guides/LOOPS_REFERENCE.md` context-variables table row called out above. No
  `ll-loop` CLI help text or JSON Schema references individual loops' context keys.
  [Agent 2 finding]

## Acceptance Criteria

- A run with no installable harness terminates `build_failed`, surfaced as failed
  (not green), with a resume command.
- `ll-loop run rn-build` on a spec whose harness install fails does not report `done`.
- Existing resume tests (ENH-2016) updated to assert the new terminal.

## Scope Boundaries

- Complementary to FEAT-2414: once the acceptance phase exists, it becomes the primary
  gate and the harness a secondary one; this issue ensures neither can be silently null.

## Impact

- **Priority**: P2 - The pipeline's strongest verification is currently the easiest to
  skip; runs can report `done` with zero verification, which is a correctness hazard.
- **Effort**: Medium - Adds a `build_failed` terminal and repoints existing
  `on_no`/`on_error` routes in `rn-build.yaml`; reuses existing terminals and evaluators.
- **Risk**: Medium - Changes which runs report `done`; existing resume tests (ENH-2016)
  must be updated to assert the new terminal.
- **Breaking Change**: No - Behavior tightens; an explicit `--context skip_eval=true`
  preserves the bypass path (still non-`done`).

## Status

**Open** | Created: 2026-06-30 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-07-28T15:43:16 - `91fb749f-272a-4718-9d77-25a82d1bc968.jsonl`
- `/ll:wire-issue` - 2026-07-28T15:30:51 - `c84d4dc2-03e3-48ca-8561-3c817c499569.jsonl`
- `/ll:refine-issue` - 2026-07-28T15:21:56 - `d14c3625-d8e6-423c-b3dd-6acc4c09b36f.jsonl`
