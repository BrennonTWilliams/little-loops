---
id: ENH-2406
title: '`rn-implement`: pre-dequeue learning-readiness gate (mirror ENH-2008 blocked_by
  gate)'
type: ENH
priority: P3
status: done
relates_to:
- EPIC-2207
- ENH-2008
- ENH-2319
- ENH-2402
- ENH-2405
labels:
- rn-implement
- learning-tests
- orchestration
- efficiency
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2406: `rn-implement` pre-dequeue learning-readiness gate (mirror ENH-2008 blocked_by gate)

## Summary

The learning gate fires **inside** `ll-auto --only` (ENH-2319's deliberate single
choke-point), so by the time a learning-gate block is detected, the issue has already been
dequeued and consumed an implement slot — and the block surfaces only as a
`LEARNING_GATE_BLOCKED` marker that rn-remediate/autodev classify *after* the failed implement
attempt. ENH-2008 already established the fix-pattern for the structurally-identical
`blocked_by` case: a cheap pre-dequeue gate in `rn-implement`'s router that defers the issue
*before* spending a remediation/implement budget. This issue mirrors that pattern for
learning-readiness: check the dequeued issue's `learning_tests_required` against the registry
(stale-aware) right after dequeue, and route a still-unproven issue to a distinct
learning-blocked outcome before `run_remediation` runs.

## Current Behavior

- `dequeue_next → fifo_pop`/`select_next` pops an issue with **no** learning-readiness check.
- `check_depth → run_remediation` enters `rn-remediate`, which eventually calls
  `ll-auto --only`; the learning gate inside `process_issue_inplace`
  (`issue_manager.py:854-869`) runs `proof-first-task` and, if a target can't be proven,
  prints `LEARNING_GATE_BLOCKED` and exits 1.
- rn-remediate's `check_learning_gate` state then classifies that marker post-hoc (the
  ordering of this classifier vs. `check_impl_auth` was the subject of extended debate — a
  symptom of the gate being discovered late and reverse-engineered from one exit code).
- The implement slot and any preceding remediation passes are already spent.

## Expected Behavior

- After dequeue (both `fifo_pop` and `select_next`), before `check_depth`/`run_remediation`,
  `rn-implement` checks the dequeued issue's `learning_tests_required` via the stale-aware
  gate (`scripts/little_loops/learning_tests/gate.py`).
- If unproven/refuted targets remain, route directly to a learning-blocked terminal/record
  state (mirroring ENH-2008's `mark_deferred`) with a "prove with /ll:explore-api" reason —
  skipping `run_remediation` entirely. The issue re-surfaces once its deps are proven.
- If all targets are proven (or none registered), proceed as today.
- The in-`ll-auto` gate (ENH-2319) **remains** as defense-in-depth: this is an earlier,
  cheaper, FSM-visible check, not a relocation. With it in place, the post-implement
  `check_learning_gate` classifier becomes a rarely-hit safety net whose internal ordering
  stops mattering.

## Motivation

1. **Wasted budget** — a learning-blocked issue can burn remediation passes before the
   in-`ll-auto` gate stops it; the pre-dequeue check skips that, exactly as ENH-2008 does for
   `blocked_by`.
2. **Visible, routable signal** — today the FSM infers a rich gate verdict from a single exit
   code + grep. A first-class pre-dequeue state lets the loop route learning-blocked issues
   distinctly without the fragile post-failure classifier chain.
3. **Honors the established pattern** — ENH-2008 already routes on `blocked_by` frontmatter
   post-dequeue; `learning_tests_required` is the same shape of first-class readiness
   frontmatter and deserves the same treatment.

## Implementation Steps

1. Add a `check_learning_ready` state in `rn-implement` after dequeue and before
   `check_depth`, reading the dequeued issue's `learning_tests_required` and calling the
   stale-aware gate helper for each target.
2. On any unproven/refuted target → route to a `mark_learning_blocked` record state
   (model on ENH-2008's `mark_deferred`): tag `failures.txt` with
   `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` (distinct from the post-remediation safety-net's
   `LEARNING_GATE_BLOCKED` tag — see Implementation Step 12), surface the `/ll:explore-api`
   remedy, and `next: dequeue_next`.
3. On all-proven / no-targets → `check_depth` as today.
4. Demote rn-remediate/autodev's post-implement `check_learning_gate` to an explicit
   safety-net comment; do **not** change its routing in this issue (that ordering is settled
   separately).
5. Coordinate with ENH-2405 so the pre-dequeue check and the in-`ll-auto` gate prove the same
   registered target list.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. `check_learning_ready` must check `${context.skip_learning_gate}` first and fail open
   (route straight to `check_depth`, skipping the registry check entirely) when it is set —
   mirroring rn-remediate's existing `if [ -n "${context.skip_learning_gate}" ]` bypass
   (`rn-remediate.yaml:441`). `rn-implement.yaml:34-38` already documents this knob as "parity
   with `ll-auto --skip-learning-gate`... threaded down to rn-remediate's inner
   `ll-auto --only`" — without this check, the new pre-dequeue gate has no knowledge of the
   knob and `--skip-learning-gate` silently stops being a full bypass once this state ships.
7. Update `scripts/tests/test_rn_implement.py::TestBlockedByGate::test_route_blocked_by_defers_on_blocked`
   (lines 843-853) — it currently asserts `rbb["on_no"] == "check_depth"` and
   `rbb["on_error"] == "check_depth"`; once `route_blocked_by`'s `on_no`/`on_error` retarget to
   `check_learning_ready`, these two assertions break and must be updated.
8. Update `scripts/tests/test_rn_implement.py::test_state_count_is_orchestrator_sized`
   (lines 587-605) — adding `check_learning_ready` + `mark_learning_blocked` (+2 states) pushes
   the orchestrator past its hardcoded `state_count <= 39` ceiling; bump the bound and append a
   changelog comment line following the file's own convention (FEAT-1991 → 26, ...,
   learning-gate routing → 39).
9. Add an assertion to `scripts/tests/test_builtin_loops.py::TestLearningGateConsistency`
   verifying the resolved tag-collision choice — the distinct `LEARNING_GATE_BLOCKED_PRE_DEQUEUE`
   tag (see Implementation Step 12 and the "Tag-collision consideration" research note below) —
   including that `report`'s generic `LEARNING_GATE_BLOCKED` count does not double-count
   `_PRE_DEQUEUE` lines. Today's `test_rn_implement_report_tallies_separately` only checks
   substring presence, so it would not catch a wrong choice or a double-counting regression.
10. Update `docs/guides/LOOPS_REFERENCE.md` — the `blocked_by` pre-gate (ENH-2008) section's
    prose, Output-artifacts table, and literal FSM-flow diagram all hardcode the
    `check_blocked_by → route_blocked_by → on_no: check_depth` edge being split by this issue.
11. Update `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — the `rn-implement` gate-order bullet list
    needs a new entry for the learning-readiness check, and the outcome-token table currently
    describes `LEARNING_GATE_BLOCKED` as solely an `rn-remediate`-originated, post-implement
    token; it now also originates pre-dequeue.
12. Resolve the tag-collision (added by `/ll:confidence-check`): `mark_learning_blocked` uses
    the distinct `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` tag rather than reusing
    `LEARNING_GATE_BLOCKED`, so `report` can separate free pre-dequeue catches (no remediation
    spent) from remediation-spent safety-net catches in `summary.json` on an ongoing basis —
    not just via a one-off run-trace check for Acceptance Criterion 1. Because
    `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` contains `LEARNING_GATE_BLOCKED` as a substring, update
    `report`'s existing `grep -c "LEARNING_GATE_BLOCKED"` (`rn-implement.yaml:989`) so it
    doesn't double-count: count the `_PRE_DEQUEUE` lines separately first, then exclude them
    when counting the generic tag (e.g. `grep -c "LEARNING_GATE_BLOCKED_PRE_DEQUEUE"` plus
    `grep -c "LEARNING_GATE_BLOCKED" failures.txt | grep -v "_PRE_DEQUEUE"`, or an equivalent
    word-boundary-safe pattern), and surface both counts in `summary.json` (a new
    `learning_gate_blocked_pre_dequeue` key alongside the existing `learning_gate_blocked`).

## Scope Boundaries

- **In scope**: a post-dequeue learning-readiness gate in `rn-implement`'s router; a distinct
  learning-blocked record path; documenting the post-implement classifier as a safety net.
- **Out of scope**: removing the ENH-2319 in-`ll-auto` gate (kept as defense-in-depth);
  changing `blocked_by` handling (ENH-2008); auto-running `/ll:explore-api` from inside
  rn-implement (the in-`ll-auto` gate already does that via `type: learning`); the
  auth-vs-learning-gate classifier ordering (settled separately).

## Acceptance Criteria

1. An issue with an unproven `learning_tests_required` target is routed to the learning-blocked
   path **without** entering `run_remediation` (verified by run trace / no remediation pass
   recorded).
2. An issue with all targets proven proceeds to `check_depth` unchanged.
3. An issue with no `learning_tests_required` field is unaffected.
4. The in-`ll-auto` learning gate still fires for callers that bypass `rn-implement`
   (ll-parallel, ll-sprint) — i.e. the choke point is intact.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — add a `check_learning_ready` state and its
  routing evaluator on the `check_blocked_by`/`route_blocked_by` → `check_depth` edge (mirrors
  `check_blocked_by`/`route_blocked_by`, `rn-implement.yaml:353-461`); add a `mark_learning_blocked`
  record state near `mark_deferred` (`rn-implement.yaml:912`); update `report`'s grep/subtraction
  logic (`rn-implement.yaml:989-1014`) to add a substring-safe `LEARNING_GATE_BLOCKED_PRE_DEQUEUE`
  count alongside the existing `LEARNING_GATE_BLOCKED` count (Implementation Step 12)
- `scripts/little_loops/loops/rn-remediate.yaml` — demote `check_learning_gate`
  (`rn-remediate.yaml:452`) to an explicit safety-net comment; no routing change in this issue

### Dependent Files (Callers/Importers)
- None outside `rn-implement.yaml` — the new state is purely an additional router edge

### Similar Patterns
- `check_blocked_by` / `route_blocked_by` (`rn-implement.yaml:353-461`) — the ENH-2008 pre-dequeue
  gate this issue mirrors, including the fail-open-to-`check_depth` shape
- `mark_deferred` (`rn-implement.yaml:912`) — model for `mark_learning_blocked`'s record-and-requeue
  shape
- the in-`ll-auto` learning gate in `process_issue_inplace`
  (`scripts/little_loops/issue_manager.py:854-869`) — the ENH-2319 choke point this pre-dequeue
  check front-runs but does not replace; calls the same stale-aware gate helper
  (`scripts/little_loops/learning_tests/gate.py`)

### Tests
- `scripts/tests/test_rn_implement.py` — new `TestLearningReadyGate` class (mirrors
  `TestBlockedByGate`, `test_rn_implement.py:804`)
- `scripts/tests/test_rn_remediate.py` — update/annotate `check_learning_gate` coverage to reflect
  its safety-net role (no routing change expected)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_implement.py::TestBlockedByGate::test_route_blocked_by_defers_on_blocked`
  (lines 843-853) — will break: asserts `on_no`/`on_error` == `"check_depth"`, must update to
  `"check_learning_ready"` [Agent 3 finding]
- `scripts/tests/test_rn_implement.py::test_state_count_is_orchestrator_sized` (lines 587-605) —
  will break: hardcoded `state_count <= 39` ceiling, must bump for +2 states and extend the
  changelog comment [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestLearningGateConsistency` — add a new assertion
  verifying the resolved tag-collision choice (distinct `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` tag,
  see Implementation Step 12) and that `report`'s generic count doesn't double-count
  `_PRE_DEQUEUE` lines; existing assertions only check substring presence and would not catch a
  wrong choice or a double-counting regression [Agent 2/3 finding; resolved by
  `/ll:confidence-check`]

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — note the pre-dequeue learning-readiness gate
  alongside the existing `blocked_by` gate note (ENH-2008)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the `blocked_by` pre-gate (ENH-2008) section's prose,
  Output-artifacts table, and literal FSM-flow diagram hardcode the
  `check_blocked_by → route_blocked_by → on_no: check_depth` edge this issue splits
  [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — the `rn-implement` gate-order bullet list and the
  outcome-token table describe `LEARNING_GATE_BLOCKED` as solely a post-implement,
  `rn-remediate`-originated token; needs a new gate-order bullet and an updated token
  description now that it can also originate pre-dequeue [Agent 2 finding]
- `docs/guides/LEARNING_TESTS_GUIDE.md` — the "Using Learning Tests in Issue Lifecycle Gates"
  section's claim that "all three automation runners... resolve targets just-in-time via a
  shared `resolve_learning_targets()` helper" becomes incomplete once `check_learning_ready`
  ships: it is a fourth gate call site that does **not** use that shared Python helper (it
  shells out directly to `ll-learning-tests check <target> --stale-aware` per target, mirroring
  `check_blocked_by`'s frontmatter-parsing pattern instead) [Agent 2 finding, second
  `/ll:wire-issue` pass]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Gate-helper correction**: `scripts/little_loops/learning_tests/gate.py` does **not** expose a
  per-target or list-of-targets "stale-aware" check function — it only has
  `is_record_stale(record, stale_after_days)` (pure date math on an already-fetched record) and
  `run_learning_gate_for_issue(issue_path, ...)` (the active **prover** that shells out to the
  `proof-first-task` sub-loop, not a registry lookup). The actual stale-aware **registry check**
  this issue needs is the CLI `ll-learning-tests check <target> --stale-aware`
  (`scripts/little_loops/cli/learning_tests.py:cmd_check`, lines 13-45), which is single-target
  (positional arg, not a list) and exits 0 only if the target's record is `status == "proven"` and
  not stale per `LearningTestsConfig.stale_after_days`; exits 1 for absent/refuted/not-proven/stale.
  Step 1 should shell out to this CLI once per `learning_tests_required` entry (mirroring how
  `scripts/little_loops/loops/migrate-sdk-version.yaml`'s `reprove_next` state subprocess-calls
  `ll-learning-tests check <target>` per target), not call into `gate.py` directly.
- **Frontmatter parsing**: no existing FSM loop YAML parses `learning_tests_required` today (a grep
  across `scripts/little_loops/loops/` for the field returns no matches) — `check_learning_ready`
  would be the first. Mirror `check_blocked_by`'s approach exactly: an inline-Python heredoc that
  re-resolves the issue file by globbing `.issues/{bugs,features,enhancements,epics}/*.md` and
  reads the raw `---`-delimited frontmatter block via `yaml.safe_load` (regex fallback if `yaml`
  import fails) — do not shell into `ll-issues show --json` (it does expose
  `learning_tests_required`, per `scripts/little_loops/cli/issues/show.py:189,299-301`, unlike
  `blocked_by`, but `check_blocked_by`'s established convention in this file is direct frontmatter
  parsing, and consistency with the adjacent gate outweighs the shortcut). Normalize
  comma-string-or-list the same way `scripts/little_loops/issue_parser.py:490-498` does.
- **Exact routing edges to redirect**: `route_blocked_by`'s `on_no: check_depth` and
  `on_error: check_depth` (`rn-implement.yaml:460-461`) are the literal edges to retarget at the
  new `check_learning_ready` state, so the chain becomes
  `route_blocked_by → check_learning_ready → check_depth`, with `check_learning_ready`'s own
  `on_no`/`on_error` pointing to `check_depth` to preserve the fail-open contract.
- **`mark_deferred` mechanics to mirror for `mark_learning_blocked`**: `mark_deferred`
  (`rn-implement.yaml:912-939`) reads an optional per-run sidecar file
  (`$RUN_DIR/blocked_by_unmet_${ID}.txt`) written by its gate state for a specific reason string,
  falls back to a generic reason if absent, appends `"$ID  $REASON"` (two-space separator) to
  `$RUN_DIR/deferred.txt`, calls `ll-issues set-status "$ID" deferred`, and unconditionally
  `next: dequeue_next`. `mark_learning_blocked` should follow the same shape, reading a sidecar
  (e.g. `learning_unproven_${ID}.txt`) listing the unproven target names.
- **Tag-collision consideration (resolved by `/ll:confidence-check`)**: `record_learning_gate_blocked`
  (`rn-implement.yaml:~890`) already writes the literal tag `LEARNING_GATE_BLOCKED` to `failures.txt`
  for the *post-remediation* safety-net hit, and `report` (`rn-implement.yaml:~961-1016`) already
  subtracts `grep -c "LEARNING_GATE_BLOCKED"` from `FAILURES`. **Decision**: `mark_learning_blocked`
  uses a distinct `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` tag rather than reusing `LEARNING_GATE_BLOCKED`,
  so `report` can separate free pre-dequeue catches from remediation-spent safety-net catches in
  `summary.json` on an ongoing basis — not just via a one-off run-trace check for Acceptance
  Criterion 1. This requires a substring-collision fix in `report`'s grep (see Implementation
  Step 12), since `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` contains `LEARNING_GATE_BLOCKED` as a
  substring.
- **Adjacent but out-of-scope**: `autodev.yaml` has its own parallel `check_learning_gate` /
  `mark_gate_blocked` pair (lines 345-367 — `check_learning_gate:` header at 345, `mark_gate_blocked:`
  header at 356, body through 367 including `on_error: dequeue_next`) consuming the same
  `ll_auto_learning_gate_check` fragment from `scripts/little_loops/loops/lib/common.yaml`. Not
  touched by this issue's Scope Boundaries (rn-implement/rn-remediate only), but worth flagging so
  a future symmetrical change isn't missed.
- **`skip_learning_gate` contract (`/ll:wire-issue` finding)**: `rn-implement.yaml:34-38` already
  defines a `skip_learning_gate` context knob documented as "parity with
  `ll-auto --skip-learning-gate`... threaded down to rn-remediate's inner `ll-auto --only`" (passed
  onward at `rn-implement.yaml:536`), and `rn-remediate.yaml:439-441` already gates its
  post-implement `check_learning_gate` behind `if [ -n "${context.skip_learning_gate}" ]`. The new
  pre-dequeue `check_learning_ready` state must check this same context variable and fail open
  (route straight to `check_depth`) when set — otherwise the existing "skip the whole learning
  gate" contract silently breaks for callers that set this knob, since the pre-dequeue gate would
  fire before ever reaching rn-remediate's bypass check. See Wiring Phase step 6.
- **`re_enqueue_unblocked` ledger ambiguity (`/ll:wire-issue` finding)**: which output file
  `mark_learning_blocked` writes to determines downstream behavior, and the two candidates in this
  codebase have different consumers. `mark_deferred` writes `deferred.txt` (two-space
  `"$ID  $REASON"`), which `re_enqueue_unblocked` re-scans every pass but only re-resolves lines
  whose REASON contains the substring `"blocked_by"` (`grep -q "blocked_by"`) — anything else is
  copied through unchanged and never re-checked for same-run re-enqueue. `record_learning_gate_blocked`
  instead writes `failures.txt` (tag-suffixed line, per this issue's Implementation Step 2), which
  `re_enqueue_unblocked` does not read at all. Implementation Step 2 already specifies `failures.txt`,
  which sidesteps `re_enqueue_unblocked` entirely (no same-run re-enqueue for learning-blocked
  issues) — confirm that's intentional, since it differs from how `mark_deferred`'s `blocked_by`
  case behaves today (same-run re-enqueue once the blocker completes).
- **Test references confirmed**: `check_learning_gate`'s existing routing assertions in
  `rn-remediate.yaml` are at `scripts/tests/test_rn_remediate.py:299-306`
  (`test_implement_failure_routes_to_failed`), with related marker/router/report-subtraction
  assertions at `scripts/tests/test_builtin_loops.py:8662-8784`
  _(refine-issue correction: previously cited as `8379-8494` — that span now contains unrelated
  `TestThing`/`TestInteractiveComponentGeneratorLoop` 3D-print test classes; `TestLearningGateConsistency`
  has moved)_. Within it, the assertions Implementation Step 9 / Wiring Step 9 must extend are
  `test_rn_implement_report_tallies_separately` (`:8753-8759` — today substring-only: asserts
  `"LEARNING_GATE_BLOCKED" in report`, `"- LEARNING_GATE_BLOCKED" in report`,
  `"learning_gate_blocked" in report`) and `test_rn_implement_threads_skip_to_remediate`
  (`:8761-8764`). `TestBlockedByGate` (the class `TestLearningReadyGate` should mirror) is a pure
  static-structure test — loads the YAML via `yaml.safe_load` and asserts on dict keys /
  string-containment in `action` blocks, with no FSM execution or subprocess mocking
  (`scripts/tests/test_rn_implement.py:804-860`).

_Second `/ll:refine-issue` pass — additional verification findings (re-checked against HEAD `1a803fac`;
all prior claims confirmed accurate except the two corrections above):_

- **`ready-to-implement-gate.yaml` exists but must NOT be used as the implementation model
  (considered and rejected)**: `scripts/little_loops/loops/ready-to-implement-gate.yaml` is a
  pre-existing built-in loop using the native FSM `type: learning` action (not `type: shell`) that
  takes `context.targets` (CSV) and **proves** each target via the registry/prover machinery —
  running `/ll:explore-api` when a target is unproven — then routes `on_yes: done` /
  `on_blocked: blocked`. It is not currently invoked from `rn-implement.yaml` or `rn-remediate.yaml`
  (confirmed via grep: no references in either file). At first glance this looks like a more
  "native" alternative to the planned Python-heredoc-per-target shell-out, but it must **not** be
  used for `check_learning_ready`: this issue's Scope Boundaries explicitly excludes "auto-running
  `/ll:explore-api` from inside rn-implement," and `type: learning` actively proves/runs
  `/ll:explore-api` rather than performing a cheap check-only gate. This confirms the plan already
  in Implementation Step 1 (shell to `ll-learning-tests check <target> --stale-aware`, check-only,
  no proving) is correct, not `ready-to-implement-gate`'s proving shape.
- **Per-target shell-loop shape — `reprove_next` is a partial model, not a full one**:
  `migrate-sdk-version.yaml`'s `reprove_next` (cited in the Gate-helper correction note above) calls
  `ll-learning-tests check <target>` **without** `--stale-aware` and pops exactly one target per FSM
  tick off a queue file across multiple loop iterations/recursions — that multi-tick queue-popping
  mechanic doesn't fit `check_learning_ready`'s need to gate *all* of one issue's
  `learning_tests_required` entries within a single state before routing once. The closer model is
  `check_blocked_by`'s own shape (`rn-implement.yaml:353-461`): one Python heredoc, in one state,
  looping over every target in-process and calling
  `subprocess.run(["ll-learning-tests", "check", t, "--stale-aware"])` per entry, aggregating
  unproven results, then routing — not `reprove_next`'s pop-one-per-tick pattern.
- **`re_enqueue_unblocked` exact anchor**: the `grep -q "blocked_by"` substring check referenced in
  the "`re_enqueue_unblocked` ledger ambiguity" note above is at `rn-implement.yaml:585`.

_Third `/ll:refine-issue` pass — re-verified against current HEAD (`9c30803e`); all prior line numbers
and claims confirmed exact (no drift), one precision nuance worth recording:_

- **`skip_learning_gate` bypass mechanism — location precision**: `rn-remediate.yaml:441`'s
  `if [ -n "${context.skip_learning_gate}" ]` lives inside the **`implement`** state (lines 433-450),
  not inside `check_learning_gate` (lines 452-460) itself. It controls whether `--skip-learning-gate`
  is appended to the inner `ll-auto --only` call — `check_learning_gate` always executes on
  `implement`'s `on_no`/`on_error`; it just finds no `LEARNING_GATE_BLOCKED` marker to classify when
  the flag suppressed the gate upstream inside `ll-auto`. This means rn-remediate's bypass is
  indirect (suppress the marker the classifier looks for), not a literal skip of the classifier
  state. Wiring Step 6's design for `check_learning_ready` is **not** identical to this mechanism —
  the new state must short-circuit itself directly (an early `if [ -n "${context.skip_learning_gate}" ];
  then echo READY; exit 0; fi`-style guard before any `ll-learning-tests check` subprocess calls),
  since there is no downstream `ll-auto` call whose marker output it could instead suppress. Both
  approaches achieve the same fail-open contract, but an implementer copying rn-remediate's exact
  shape (gate the flag passed to a subprocess) rather than `check_blocked_by`'s shape (gate the
  state's own routing) would build the wrong thing.

_Second `/ll:wire-issue` pass — re-ran the 3-agent wiring sweep against current HEAD; prior wiring
(Tests/Documentation sections, Implementation Steps 6-12) confirmed still complete, two small
additions:_

- **Adjacent existing gate call site — `worker_pool.py` (in addition to the already-noted
  `autodev.yaml`)**: `scripts/little_loops/parallel/worker_pool.py`'s
  `_run_per_worktree_proof_first_gate()` is a third existing learning-gate call site (alongside the
  in-`ll-auto` gate and `autodev.yaml`'s `check_learning_gate`/`mark_gate_blocked` pair) that resolves
  `learning_tests_required` per worktree for `ll-parallel`. Like `autodev.yaml`, it is untouched by
  this issue's Scope Boundaries (rn-implement/rn-remediate only) and is exactly the kind of caller
  Acceptance Criterion 4 ("the in-`ll-auto` learning gate still fires for callers that bypass
  `rn-implement`") already covers — flagged for symmetry awareness only, no action required
  [Agent 1 finding].
- **`test_builtin_loops.py` line-number drift, found mid-pass**: the prior "Test references
  confirmed" note's `test_builtin_loops.py` citations have drifted since the Third refine-issue
  pass — `TestLearningGateConsistency` now starts at line 8722 (not 8662), and within it
  `test_rn_implement_report_tallies_separately` is now at lines 8813-8819 (not 8753-8759) and
  `test_rn_implement_threads_skip_to_remediate` is now at lines 8821-8824 (not 8761-8764).
  Assertion *content* is unchanged — only line numbers moved. The drift is confined to
  `test_builtin_loops.py`, which `git status` shows as locally modified (uncommitted, unrelated
  edits) at the time of this pass; re-locate by class/function name
  (`TestLearningGateConsistency`, `test_rn_implement_report_tallies_separately`,
  `test_rn_implement_threads_skip_to_remediate`, `test_rn_remediate_threads_skip_flag`) rather
  than trusting any cited line number in this file until that local modification lands or is
  reverted [Agent 3 finding].

## API/Interface

N/A — no public API changes. This adds internal FSM router states (`check_learning_ready`,
`mark_learning_blocked`) to `rn-implement.yaml`, not a function/class signature or CLI argument.

## Impact

- **Priority**: P3 — efficiency + clarity improvement on a working path; not blocking.
- **Effort**: Small–Medium — one router state + one record state in `rn-implement`, modeled
  directly on ENH-2008.
- **Risk**: Low–Medium — additive router state; must not double-block or regress the
  across-runners choke point. Pairs with ENH-2405.
- **Breaking Change**: No.

## Labels

`enhancement`, `rn-implement`, `learning-tests`, `orchestration`, `efficiency`

## Session Log
- `/ll:ready-issue` - 2026-07-01T00:28:59 - `30250bcf-0ca1-43b6-9d9f-6ffb78a57185.jsonl`
- `/ll:confidence-check` - 2026-06-30T23:30:00 - `77eb3749-b914-48c8-a9c1-dcc2bba1ebb0.jsonl`
- `/ll:wire-issue` - 2026-06-30T23:09:39 - `ccc753bc-c18e-4ab5-83d0-331a9ffe1e99.jsonl`
- `/ll:refine-issue` - 2026-06-30T22:58:47 - `ccc753bc-c18e-4ab5-83d0-331a9ffe1e99.jsonl`
- `/ll:refine-issue` - 2026-06-30T22:22:30 - `d9035869-74ff-4583-aea5-9a496a2f8235.jsonl`
- `/ll:confidence-check` - 2026-06-30T21:50:47 - `0efaa89a-2331-4523-aad0-814d20e76a5a.jsonl`
- `/ll:wire-issue` - 2026-06-30T21:43:57 - `7475cb34-e529-45a6-ae0d-48e2395d6a0c.jsonl`
- `/ll:refine-issue` - 2026-06-30T21:32:34 - `f9faf247-a4a4-4477-ba0f-2637b7a0635b.jsonl`
- `/ll:format-issue` - 2026-06-30T21:24:21 - `13874c47-a99b-4643-8187-fc2c7bf0ae42.jsonl`
- `/ll:capture-issue` - 2026-06-30T21:17:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/517f4fde-43d5-44f7-afc7-41dd7c15be45.jsonl`

## Resolution

**Closed - Already Fixed** (2026-06-30, via `/ll:ready-issue`).

Implemented in commit `f60de257` — "feat(loops): add pre-dequeue learning-readiness
gate to rn-implement (ENH-2406)" (on `main`). Verified present and working:

- `check_learning_ready` + `route_learning_ready` states added on the
  `route_blocked_by → check_depth` edge (`rn-implement.yaml:461-581`); `on_yes`
  routes to `mark_learning_blocked` (`rn-implement.yaml:1063`).
- `skip_learning_gate` short-circuit guard present in `check_learning_ready`
  (`rn-implement.yaml:489`) — Wiring Step 6 satisfied.
- Distinct `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` tag written to `failures.txt`; `report`
  counts it separately and subtracts it from the generic `LEARNING_GATE_BLOCKED` total,
  surfacing a `learning_gate_blocked_pre_dequeue` key in `summary.json`
  (`rn-implement.yaml:1136-1161`) — Implementation Step 12 satisfied.
- `rn-remediate.yaml:459-464` demoted `check_learning_gate` to a documented safety-net.
- Docs updated: `LOOPS_REFERENCE.md`, `RECURSIVE_LOOPS_GUIDE.md`, `LEARNING_TESTS_GUIDE.md`.
- Tests green (21 passed): `TestLearningReadyGate`,
  `TestValidation::test_state_count_is_orchestrator_sized` (ceiling bumped to ≤42),
  `test_builtin_loops.py::TestLearningGateConsistency`.
- `ll-loop validate rn-implement` passes (all MR gates).

## Status

**Done** | Created: 2026-06-30 | Closed: 2026-06-30 | Priority: P3
