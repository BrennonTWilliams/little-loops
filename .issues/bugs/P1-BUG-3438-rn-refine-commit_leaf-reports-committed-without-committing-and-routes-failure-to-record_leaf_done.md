---
id: BUG-3438
type: BUG
title: rn-refine commit_leaf reports COMMITTED without committing and routes failure
  to record_leaf_done
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
decision_needed: false
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3438: rn-refine commit_leaf reports COMMITTED without committing and routes failure to record_leaf_done

## Summary

commit_leaf (rn-refine.yaml ~602-616) has no `set -e` and ends in `|| true`, so a failed `git commit` (no identity, pre-commit reject, index lock) still echoes COMMITTED, exits 0, and writes the pre-leaf HEAD to leaf-baseline-commit.txt. Worse, its on_error already routes to record_leaf_done, which marks the leaf `verified`, so bare `set -e` alone is insufficient: the error path must go to a new `record_leaf_commit_failed` state that **reverts the dirty tree** (a plain `record_failure` reroute would leave the staged changes to be misattributed to the next leaf's commit), records `<nid> COMMIT_FAILED`, and writes no `leaf_impl_` marker so resume re-enqueues the leaf. Audit sibling actions (`reset_leaf_repair`, `snapshot_leaf_diff`) for the same `echo SUCCESS; ... || true` shape. Test: give the ephemeral repo a repo-local git identity (hermetic) and add a failing-commit case (`user.useConfigOnly=true`, no identity) asserting non-zero exit, no COMMITTED marker, and a reverted tree.

## Current Behavior

`commit_leaf` (`scripts/little_loops/loops/rn-refine.yaml`, state `commit_leaf`, action ~lines 602-619) runs its shell action without `set -e` and its only failure guard is `|| true` on the baseline write. When `git commit` fails (no git identity configured, pre-commit hook rejection, `.git/index.lock` contention), execution falls through:

1. `echo "COMMITTED <nid>"` runs unconditionally after the commit attempt → false success marker in run logs.
2. `git rev-parse HEAD` still succeeds (HEAD exists — it's the pre-leaf commit), so `leaf-baseline-commit.txt` is advanced to the **pre-leaf** HEAD with the changes still uncommitted.
3. The action's last command succeeds → exit 0 → FSM routes via `next: record_leaf_done`, which writes `leaf_impl_<nid>.txt` = `verified` and echoes `[LEAF_IMPL] <nid> verified`.
4. The next leaf's `commit_leaf` does `git add -A` and commits the failed leaf's still-staged changes under the **next** leaf's commit message — silent misattribution and a corrupted per-leaf commit history.

Additionally, `commit_leaf`'s `on_error: record_leaf_done` routes infra failures into the state that marks the leaf verified, so adding `set -euo pipefail` alone would convert the silent pass into a loud-but-still-wrong "verified" marking.

## Expected Behavior

- A failed `git commit` makes `commit_leaf` exit non-zero and emit **no** `COMMITTED` marker (an explicit `COMMIT_FAILED` diagnostic is acceptable/desirable).
- `leaf-baseline-commit.txt` is advanced **only** after a successful commit (or `NO_CHANGES`), so retry/verify scoping stays correct.
- `commit_leaf`'s error path routes to a new `record_leaf_commit_failed` state — never to `record_leaf_done`, and not to `record_failure` either (it does not revert). The new state: hard-resets the tree to `leaf-baseline-commit.txt` (so the chain's "each prior leaf either committed or reverted" invariant holds and the next leaf's `git add -A` cannot misattribute this leaf's changes), appends `<nid> COMMIT_FAILED` to `failed_nodes.txt`, echoes `[COMMIT_FAILED] <nid>`, writes **no** `leaf_impl_<nid>.txt` marker (so `check_resume`/`resume_reconcile` re-enqueue the leaf on resume — a commit failure is usually transient/environmental and the work should be retried), and ends `next: dequeue_next`.
- Sibling states with the same swallow shape (`reset_leaf_repair`'s `|| : > file` producing an empty baseline; `snapshot_leaf_diff`'s `|| true` producing an empty touched-files list, which its comment frames as deliberate) are audited and either fixed or filed as follow-ups.

## Steps to Reproduce

1. Create an ephemeral repo: `git init` + one committed file (the baseline), then modify/add a file so `git add -A` stages a change.
2. Make the commit deterministically fail: `git config user.useConfigOnly true` in the ephemeral repo with no repo-local `user.name`/`user.email` → `git commit` exits 128 with "fatal: no email was given and auto-detection is disabled" (verified 2026-09-10). Hiding the global config alone (`GIT_CONFIG_GLOBAL=/dev/null`) is **not** deterministic — git auto-derives an identity from gecos+hostname and only fails when it judges that bogus. A pre-commit hook is fragile if the machine sets a global `core.hooksPath`.
3. Run the rendered `commit_leaf` action (the `_render`/`_bash` pattern from `scripts/tests/test_rn_refine.py::TestFinalizeSafety`) with `captured.run_dir.output` pointing at a run dir and `captured.input.output` = a node id.
4. Observe: exit code 0; stdout contains `COMMITTED <nid>`; `leaf-baseline-commit.txt` holds the pre-leaf HEAD; downstream `record_leaf_done` writes `leaf_impl_<nid>.txt` = `verified` with the changes still uncommitted.

## Root Cause

- **File**: `scripts/little_loops/loops/rn-refine.yaml`
- **Anchor**: `states.commit_leaf.action` (and its `on_error` routing edge)
- **Cause**: The shell action has no `set -e`/`pipefail`; `echo "COMMITTED"` is not conditioned on commit success; the trailing `git rev-parse HEAD ... || true` both swallows its own failure and guarantees an exit-0 tail; and `on_error: record_leaf_done` maps any surfaced failure onto the verified-marker state.

## Proposed Solution

Rewrite the `commit_leaf` action with an explicit failure surface:

```bash
set -e
RUN_DIR="${captured.run_dir.output}"
git add -A
if git diff --cached --quiet; then
  echo "NO_CHANGES ${captured.input.output}"
else
  git commit -m "rn-stepwise: implement leaf ${captured.input.output}"
  echo "COMMITTED ${captured.input.output}"
fi
git rev-parse HEAD > "$RUN_DIR/leaf-baseline-commit.txt"
```

- Drop the `|| true` (and `2>/dev/null`) on the baseline write so a rev-parse failure surfaces too.
- Reroute `on_error: record_leaf_done` → `on_error: record_failure`. Prefer reusing `record_failure` over a new state unless a distinct `COMMIT_FAILED` marker is needed for diagnosability — if added, `record_leaf_commit_failed` should append to `failed_nodes.txt` and echo `[COMMIT_FAILED] <nid>`, mirroring `record_failure`'s `next: dequeue_next`.
- Audit sibling swallow shapes in the same YAML: `capture_baseline` (~line 428, `|| : > "$RUN_DIR/leaf-baseline-commit.txt"` yields an empty baseline that downstream `git diff --name-only ""` mishandles) and `verify_leaf` (~line 475, `|| true` yields an empty touched-files list). Fix or file follow-ups.
- FSM interpolation note: `${captured.*}` refs are FSM-interpolated; any bash runtime `$VAR`/`${NID}` must stay `$${...}`-escaped (existing `record_leaf_done` already follows this).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Sibling-state name corrections (this issue's text): no state named `capture_baseline` exists — the `git rev-parse ... || : > leaf-baseline-commit.txt` write at ~line 428 lives in state `reset_leaf_repair` (`scripts/little_loops/loops/rn-refine.yaml:417-431`), and the `verify_leaf`-attributed `git diff --name-only ... || true` at ~line 475 sits in state `snapshot_leaf_diff`, whose surrounding comment frames never-fail-the-leaf as deliberate (`:463-468`). Any audit or follow-up must target those states by their real names.
- If a dedicated state is chosen over reusing `record_failure`, the precedent shape is: an in-tree issue-ID rationale comment, append `<nid> COMMIT_FAILED` to `failed_nodes.txt` (class token per the ledger rule), a `[COMMIT_FAILED] <nid>` echo, and `next: dequeue_next`.
- Decision point on the action-header form (corpus convention vs as-written):

**Option A**: Keep `set -euo pipefail` as written above. Zero loop-action-body precedent for the combined form (standalone scripts only: `hooks/scripts/check-private-refs.sh`, `.github/scripts/ci-history.sh`), but it is inert-safe here — the action has no pipeline for pipefail to guard and no unset var for `-u` to catch once FSM refs are interpolated.

**Option B**: Follow the corpus forms — bare `set -e` (the only in-loop precedent, `fleet-loop-improve.yaml` state `commit`, paired there with `evaluate: {type: exit_code}` + `on_no`/`on_error: revert`), reserving `set -o pipefail` for commented pipeline sites (12 sites, e.g. `rn-remediate.yaml:484-486`). Functionally equivalent for this action.

> **Selected:** Option B — bare `set -e` matches the only errfail precedent in any loop action body (`fleet-loop-improve.yaml` `commit`); `set -euo pipefail` has zero loop-action-body precedent (0 of 16 corpus `set -` headers).

**Recommended**: Option B — corpus consistency; per-site commented guards are the in-tree rule and the loop corpus contains no `set -euo pipefail` action body. Either option satisfies the AC (non-zero exit, no `COMMITTED` marker on failure).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-10.

**Selected**: Option B — bare `set -e` action header

**Reasoning**: Bare `set -e` is the only errfail form in any loop action body — 3 sites, all in `fleet-loop-improve.yaml` (states `preflight`/`harvest`/`commit`), including its `commit` state with the same failure semantics this fix needs; the combined `set -euo pipefail` appears in 0 of 16 corpus `set -` headers (standalone `.sh` scripts only). The engine contract (plain `bash -c` at `fsm/runners.py:348`; non-zero exit → `on_error` at `fsm/executor.py:2120-2122`) makes the two forms functionally identical for this pipeline-free body, so corpus consistency is the tiebreaker.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (`set -euo pipefail`) | 1/3 | 3/3 | 3/3 | 2/3 | 9/12 |
| Option B (bare `set -e`) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- Combined form: functionally sound and inert-safe (no pipeline for pipefail to guard, no unset var post-interpolation), no validator or test forbids it — but it introduces a first-of-its-kind action-body form.
- Bare `set -e`: matches the verified corpus exactly — it ships in `fleet-loop-improve.yaml`'s `commit` state (paired with `evaluate: {type: exit_code}` + `on_no`/`on_error: revert`); `set -o pipefail` is uniformly reserved for 12 commented per-pipeline sites, all guarding actual pipelines.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml` — `commit_leaf` action body + `on_error` edge; possible sibling touch-ups (`capture_baseline`, `verify_leaf`).

### Dependent Files (Callers/Importers)
- FSM executor consumes the YAML (`scripts/little_loops/fsm/executor.py`); `ll-loop validate` (`scripts/little_loops/fsm/validation/`) re-validates on change — keep the `ll-lint: mr11-ok(...)` comments intact.
- Package data: the YAML ships inside `scripts/little_loops/loops/` — no mirror/host-adapted copy exists for loops.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-stepwise.yaml` — the only runtime composer (`loop: rn-refine` at :37); its description (:11-16) repeats the leaf-chain state enumeration — update only if `record_leaf_commit_failed` is added [Agent 1 finding, grep-confirmed]
- `scripts/little_loops/fsm/validation/shell_safety.py` — the MR-11 adjacency contract behind the "keep mr11-ok intact" note above: every `${captured.*}` line needs its marker adjacent (same-line trailing or stacked-preceding, `_find_adjacent_marker` :261 / `_scan_state_for_mr11` :286); restructuring the action body must move markers with their refs [Agent 2 finding, grep-confirmed]
- Informational (no change required): `scripts/little_loops/loops/oracles/plan-node-refine.yaml`, `oracles/integrate-node.yaml`, `oracles/plan-research-iteration.yaml`, and `scripts/little_loops/rn_synth_queue.py` reference rn-refine at comment/docstring level only; `scripts/little_loops/loops/README.md` (:62, :192) documents artifacts only — no edit needed [Agent 1 finding, grep-confirmed]
- Resume-path coupling inside the changed YAML: a leaf routed to `record_failure` gets no `leaf_impl_<nid>.txt`, so `check_resume`/`resume_reconcile` classify it INCOMPLETE and re-enqueue it on resume — new intended behavior from the reroute [Agent 2 finding]

_Inferred, unconfirmed (held out of the confirmed lists by the evidence gate):_ `scripts/tests/test_fsm_validation.py`, `scripts/little_loops/cli/loop/info.py` — no direct grep hit for rn-refine or the traced symbols; plausible future MR-rule positive-control homes only.

### Similar Patterns
- `record_deviation` / `record_leaf_done` / `record_failure` states for marker-file conventions; `TestFinalizeSafety` in the test file for the render-and-run action-testing pattern.

### Tests
- `scripts/tests/test_rn_refine.py` — new test class (e.g. `TestCommitLeafSafety`) using `_render`/`_bash`: hermetic identity-failure case (assert non-zero exit, no `COMMITTED`, baseline not advanced), happy path with an explicit repo-local git identity (`git config user.email/user.name` so it doesn't depend on the machine's global identity), and routing assertions (`fsm.states["commit_leaf"].on_error == "record_failure"`).
- `scripts/tests/test_builtin_loops.py` references rn-refine — confirm no assumptions about the old routing.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_refine.py` — the existing happy-path pin `test_commit_leaf_commits_pending_changes` (:1816-1847) currently depends on the machine's ambient global git identity (the rendered action's bare `git commit` runs without one); make it hermetic with repo-local `git config` (BUG-3251 fixture pattern, `scripts/tests/test_recursive_finalize.py:14-19`) [Agent 3 finding, grep-confirmed]
- `scripts/tests/test_rn_refine.py` — `NO_CHANGES` passthrough has zero coverage repo-wide; `_bash()` (:36) takes no `env=` — failure injection uses the `env = dict(os.environ)` + direct `subprocess.run` form (:169-173) with `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null`, or a rejecting pre-commit hook (fixture precedent `scripts/tests/test_issue_lifecycle.py:684-686`) [Agent 3 finding, grep-confirmed]
- `scripts/tests/test_rn_refine.py` — routing-assertion precedent is `test_implement_leaf_errors_do_not_reuse_record_leaf_dequeue_habit` (:1632-1640): assert `on_error == "record_failure"` AND `!= "record_leaf_done"`; nothing pins `commit_leaf.on_error` today, so the reroute breaks zero existing assertions [Agent 3 finding, grep-confirmed]
- `scripts/tests/test_rn_refine.py` — pin the reroute's resume semantics: commit-failed leaf carries no `leaf_impl_` marker → `check_resume`/`resume_reconcile` re-enqueue it (retryable-on-resume is intended) [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py` — `MR11_MARKER_ALLOWLIST` tuples key on (file, var, first issue-ID in the marker reason; rn-refine entries :20745-20756): keeping the existing ENH-3358 reasons collapses into existing tuples; citing BUG-3438 in any marker adds a tuple that must land in lockstep [Agent 2 finding, grep-confirmed]
- `scripts/tests/test_builtin_loops.py` — `TestValidatorWarningBudget` (:16928+) has zero rn-refine entries: an orphaned `mr11-ok` marker (ref removed during restructuring) or a new unsafe interpolation fails the warning budget outright [Agent 2 finding, grep-confirmed]

### Documentation
- N/A (loop-internal behavior; `docs/` doesn't document commit_leaf semantics).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` (:637-649, rn-stepwise section) — enumerates the leaf chain (`record_leaf`/`implement_leaf`/`verify_leaf`/`record_deviation`/`record_leaf_done`); `commit_leaf` is not named, so the `on_error` reroute alone needs no edit — update only if `record_leaf_commit_failed` is added [Agent 2 finding, grep-confirmed]

### Configuration
- N/A.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Engine contract: shell actions run under plain `bash -c` with no engine-side `set -e` (`scripts/little_loops/fsm/runners.py:348`, stated verbatim at `scripts/little_loops/loops/general-task.yaml:934`); a non-zero exit routes to `on_error` only when defined (`scripts/little_loops/fsm/executor.py:2120-2122`). A failure surface is exactly two parts: the action exits non-zero on failure, and `on_error` points at a state with the right recording semantics — an `on_error` aimed at a success-marking state is itself the bug shape.
- Rule: `set -o pipefail` is a targeted, commented addition per pipeline site that would otherwise mask the tested command's exit (12 sites, e.g. `rn-remediate.yaml:484-486`, `autodev.yaml:913-915`); bare `set -e` exists in exactly one builtin loop — `fleet-loop-improve.yaml` states `preflight`/`harvest`/`commit` (lines 52, 76, 253-275) — paired there with `evaluate: {type: exit_code}` + `on_no`/`on_error: revert`. The combined form `set -euo pipefail` appears in zero loop action bodies repo-wide (standalone scripts only: `hooks/scripts/check-private-refs.sh`, `.github/scripts/ci-history.sh`).
- Contested convention — commit-state failure surfaces are split across the corpus: guarded (`fleet-loop-improve.yaml` state `commit`), unguarded swallow (`harness-optimize.yaml` state `commit_and_log` ~206-213; `mechanize-skills.yaml` state `commit_change` ~565-598), and `/ll:commit` prompt-fragment delegation (`recursive-refine.yaml:344-349`, `dead-code-cleanup.yaml:173-175` via `scripts/little_loops/loops/lib/prompt-fragments.yaml:18-22`). The guarded variant is the minority; this fix sets precedent rather than follows it.
- Marker-writer rules shared by rn-refine's six recorders: `failed_nodes.txt` is an append-only run-wide ledger — node id first, failure-class token appended only when the class needs distinguishing (`record_failure` → bare `<nid>`, `record_node_crash` → `<nid> CRASH`, `revert_leaf_failed` → `<nid> IMPLEMENT_FAILED`); `leaf_impl_<nid>.txt` holds a single token written with `printf '%s'`; every recorder echoes a bracketed tag line (`[FAILED]`, `[LEAF_IMPL]`, …); all end `next: dequeue_next`.
- Dedicated failure-class states are the established precedent when the class must stay distinguishable, each with an in-tree issue-ID rationale comment (`record_node_crash`, `record_leaf_failed`, rn-remediate's `record_gate_error` — "Distinct from record_gate_failure", `record_sub_loop_crash` — "crash ≠ implementation failure"). No loop defines a commit-failure state today (repo-wide search: only hits are this issue's own text and the unrelated `session_store.record_commit_event` Python API).
- `record_failure` is the generic sink every generic error edge in rn-refine already uses (`route_decomposed`, `route_leaf`, `route_capped` at `rn-refine.yaml:374, 383, 391-392`); the chain documents its own error-routing rule at `rn-refine.yaml:411-415` ("Deliberately does NOT reuse record_leaf's on_error: dequeue_next habit"), enforced by negative-assertion test at `scripts/tests/test_rn_refine.py:1632-1640`.
- MR-11 marker corpus is enumerated and test-frozen: `TestMr11MarkerSet` (`scripts/tests/test_builtin_loops.py:20792-20821`) asserts discovered markers equal `MR11_MARKER_ALLOWLIST` exactly (rn-refine's entries at 20745-20756). A rewritten `commit_leaf` action must keep its `mr11-ok(captured.input.output)` / `mr11-ok(captured.run_dir.output)` markers valid or update the allowlist in lockstep.
- Interpolation: only the brace form `$${...}` is rewritten to bash's `${...}` (`scripts/little_loops/fsm/interpolation.py:345-348`); doubling `$$(` or `$$VAR` is an MR-9 ERROR (`scripts/little_loops/fsm/validation/shell_safety.py:195-245`). In-chain style is contested: `record_leaf_failed` interpolates the FSM ref directly into the path (`rn-refine.yaml:546`) while `record_leaf_done`/`record_deviation` assign once to a shell var then use `$${NID}` (assign-once rationale citing BUG-3390 at `autodev.yaml:931`).
- No MR lint rule covers this bug class: MR-10 (`scripts/little_loops/fsm/validation/evaluator_rules.py:80-126`) flags only inline-Python `json.loads` swallows ending in `exit(0)` with no `on_error`; `on_error` checks in `structural_rules.py:653-731` are pairing/coexistence rules only. No validator change is implied by this fix.
- Hazard if the error route ever passes through a revert-style state: `git reset --hard` can delete `$RUN_DIR` itself when the run dir is tracked; `revert_leaf_failed` (`rn-refine.yaml:530-537`) recreates it with `mkdir -p` before appending. `record_failure` does not revert, so this is informational for the chosen route.
- Test recipe (render-and-run): `_bash` (`scripts/tests/test_rn_refine.py:36`) + `_render` (`:40`) + `_load_rn_refine` (`:46`, which `load_and_validate`s — every render-and-run test re-validates the YAML); assert `returncode` with `stderr` in the message, stdout tokens, and on-disk marker files.
- Hermetic-git rule in test fixtures: ephemeral repos seed with per-command identity flags — `git -c user.email=a@b.c -c user.name=a commit --allow-empty -q -m seed` — never `git config` (machine-global identity must not be a dependency) (`TestStepwiseChainPlumbing`, `test_rn_refine.py:1682-1847`). For the failing-commit case, `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null` in the env makes identity absence deterministic.
- Existing coverage that constrains the fix: `test_commit_leaf_commits_pending_changes` (`test_rn_refine.py:1816-1847`) pins the happy path only (asserts `COMMITTED` in stdout, commit-log subject, non-empty `leaf-baseline-commit.txt`) and must keep passing; `test_commit_leaf_then_record_leaf_done_then_dequeue_next` (`:1666-1669`) pins `commit_leaf.next == "record_leaf_done"`; the `leaf_impl_`-vs-`node_outcome_` namespace separation is pinned at `:1671-1676`; `TestLoadsClean` (`:56-76`) requires `ll-loop validate` to report zero ERRORs for rn-refine.

## Program Design

### Types

- No new Python types. Marker-file contract unchanged: `leaf_impl_<nid>.txt` ∈ {`verified`, `deviated`} written only by `record_leaf_done`; `leaf-baseline-commit.txt` holds the HEAD after the most recent successful leaf commit.

### Signatures

- `commit_leaf(exit_code: int) -> next_state: str` — exit 0 routes to `record_leaf_done` (unchanged); nonzero routes to `record_failure` (changed from `record_leaf_done`)
- `record_leaf_commit_failed(node_id: str) -> None` — optional new state: appends `"<nid> COMMIT_FAILED"` to `failed_nodes.txt`, echoes `[COMMIT_FAILED] <nid>`; `next: dequeue_next`

### Call Path

`check_leaf_deviation.on_no` → `commit_leaf` → (success) `record_leaf_done` → `dequeue_next`
`commit_leaf` → (failure) `record_failure` → `dequeue_next`

## Implementation Steps

1. Rewrite `commit_leaf` action with bare `set -e` (corpus form, per Decision Rationale) and unconditional baseline write on the success path only.
2. Reroute `commit_leaf.on_error` to `record_failure` (or add `record_leaf_commit_failed`).
3. Audit/fix sibling swallow shapes (`capture_baseline`, `verify_leaf`) or file follow-up issues.
   > ⚠ Superseded — `capture_baseline` does not exist; see § Codebase Research Findings under Implementation Steps
4. Add `TestCommitLeafSafety` cases: identity-failure, happy path with explicit identity, routing assertions.
5. Verify: `python -m pytest scripts/tests/test_rn_refine.py scripts/tests/test_builtin_loops.py` and `ll-loop validate rn-refine`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Step 3's sibling names are wrong: no `capture_baseline` state exists — the empty-baseline `|| : >` write is in `reset_leaf_repair` (`scripts/little_loops/loops/rn-refine.yaml:417-431`), and the `verify_leaf`-attributed `|| true` is in `snapshot_leaf_diff` (`:475`, deliberately never-fail per its comment at `:463-468`). File audits/follow-ups against those state names.
- An `on_error` change needs its own routing assertion — the existing pin (`test_commit_leaf_then_record_leaf_done_then_dequeue_next`, `scripts/tests/test_rn_refine.py:1666-1669`) asserts `commit_leaf.next == "record_leaf_done"` only; per-edge negative-assertion style precedent at `:1632-1640`.
- The rewritten action must keep its MR-11 markers valid or `TestMr11MarkerSet` (`scripts/tests/test_builtin_loops.py:20792-20821`) fails in lockstep with the `MR11_MARKER_ALLOWLIST`.
- The success path is pinned by `test_commit_leaf_commits_pending_changes` (`test_rn_refine.py:1816-1847`): `COMMITTED` stdout, commit-log subject, non-empty `leaf-baseline-commit.txt` must all survive the rewrite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Preserve `mr11-ok(...)` markers adjacent to their `${captured.*}` refs when restructuring the action (adjacency contract in `scripts/little_loops/fsm/validation/shell_safety.py`); keep the existing ENH-3358 marker reasons, or add BUG-3438 tuples to `MR11_MARKER_ALLOWLIST` in lockstep
- Make `test_commit_leaf_commits_pending_changes` hermetic (repo-local `git config user.email/user.name` after `git init`)
- Pin the reroute's resume semantics with a test: commit-failed leaves carry no `leaf_impl_` marker → `check_resume`/`resume_reconcile` re-enqueue them
- Broaden the step-5 verify command with the corpus gates that re-scan rn-refine on any edit: `scripts/tests/test_builtin_loop_interpolation.py`, `scripts/tests/test_fsm_flow.py`, `scripts/tests/test_fsm_schema.py`
- If `record_leaf_commit_failed` is chosen: declare the state with `next: dequeue_next`, add it to `test_chain_states_exist`'s tuple (:1614-1630, membership-only — additive-safe), and update the chain enumerations in `docs/reference/loops.md:637-649` and the `rn-stepwise.yaml` description (:11-16)

## Impact

- **Priority**: P1 - Silent data-integrity failure in the stepwise implement loop: failed commits masquerade as verified leaves and misattribute changes to subsequent leaf commits.
- **Effort**: Small - One action rewrite, one routing edge, one focused test class; established render/run test pattern to follow.
- **Risk**: Low - Narrows a swallow-all path; the `NO_CHANGES` passthrough and success path are preserved verbatim.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-09-11T01:36:32 - `baec27a2-e9d2-4434-851e-afe0bfd070d4.jsonl`
- `/ll:verify-issues` - 2026-09-11T01:30:05 - `d72bd4c5-bd63-412a-b4aa-6f32a387ff10.jsonl`
- `/ll:wire-issue` - 2026-09-11T00:20:41 - `8f2b9975-276a-4a01-bf0b-f0ce8216df48.jsonl`
- `/ll:decide-issue` - 2026-09-10T23:42:12 - `d0293195-1c81-4d81-ac17-fa584ee4566b.jsonl`
- `/ll:refine-issue` - 2026-09-10T23:03:56 - `c5f928c1-0152-48c5-b6b1-4132651d57a3.jsonl`
- `/ll:format-issue` - 2026-09-10T21:55:58 - `82016d7d-cfd1-41eb-a02d-fdc1a376c905.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
