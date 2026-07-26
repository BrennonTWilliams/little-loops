---
id: ENH-2825
type: ENH
priority: P2
status: open
captured_at: "2026-07-26T05:58:30Z"
discovered_date: 2026-07-26
discovered_by: capture-issue
relates_to: [ENH-2814]
---

# ENH-2825: Add `failed` terminals to the 39 built-in loops that lack one

## Summary

ENH-2814 (commit `66cec5a8`) made FSM failure terminals observable end-to-end: a
state marked `failure: true` now sets `ExecutionResult.failure_terminal`, exits
`FAILURE_TERMINAL_EXIT_CODE` (2), persists `final_status: "failed"` and
`loop_runs.failure_terminal`, and is read by `history_reader._WASTED_RUN_PREDICATE`,
`parallel/worker_pool.py`, and `learning_tests/gate.py`.

That mechanism is only as good as the loops that declare it. 39 of the 85
loadable built-in loops under `scripts/little_loops/loops/` still declare **only**
a `done` terminal, so their error and abort edges route into the success terminal.
Those runs exit 0 and persist as `completed` no matter what happened.

This is the audit §2.2 / rec #8 sweep that ENH-2814 was explicitly sequenced
before, and which is now unblocked.

## Current Behavior

Genuine failure edges terminate at `done`:

```yaml
# scripts/little_loops/loops/worktree-health.yaml
check_branches:
  on_error: done      # <-- the check errored; run still exits 0 as "completed"
  on_no: prune_branches
  on_yes: done
```

```yaml
# scripts/little_loops/loops/docs-sync.yaml
route_results:
  on_error: verify_docs   # error is indistinguishable from "needs another pass"
  on_no: fix_docs
  on_yes: done
```

Consequences for every loop in the affected list:

- `ll-loop run <loop>` exits 0 on failure, so shell callers, `ll-queue run`, and
  CI-style gates cannot detect it.
- `loop_runs.final_status` records `completed`; `failure_terminal` is 0.
- `history_reader`'s wasted-run analytics under-count these runs.
- A sub-loop delegating to one of these loops routes `on_yes` (success) on a
  failed child, because sub-loop routing now keys on the `failure` flag.

## Expected Behavior

Every built-in loop has at least one `failure: true` terminal (conventionally
named `failed`), and every edge that represents a genuine error or abort routes
to it rather than to `done`. Legitimate no-op-success edges (nothing to do,
already clean, empty input) keep routing to `done`.

After the sweep:

```bash
python - <<'PY'
import pathlib, logging; logging.disable(logging.CRITICAL)
from little_loops.cli.loop._helpers import load_loop
root = pathlib.Path("scripts/little_loops/loops")
missing = [p for p in root.rglob("*.yaml") if "/lib/" not in str(p)
           and not load_loop(str(p), root, logging.getLogger("x")).get_failure_states()]
assert not missing, missing
PY
```

exits 0.

## Motivation

ENH-2814 built the observability plumbing; without this sweep 46% of built-in
loops still report every outcome as success. The cost is concentrated in the
automation loops users actually run unattended (`autodev`, `scan-and-implement`,
`sprint-refine-and-implement`, `fix-quality-and-tests`, `docs-sync`), where a
silent failure means the operator believes work landed that did not.

It also removes the last reason `failure:` remains a name-convention default
rather than an explicit declaration.

## Proposed Solution

Per loop, a three-step edit — mechanical in shape, but the routing decision is
per-loop judgment and must not be scripted blindly:

1. Add a bare failure terminal (no `action:` — see the BUG-2813
   `terminal-action-ok` rule; put any reporting in a penultimate non-terminal
   state with `next: failed`, the `rn-implement::report` shape):

   ```yaml
   failed:
     terminal: true
     failure: true
   ```

2. Re-route genuine error/abort edges (`on_error:` from a shell/CLI state whose
   failure is not recoverable, `on_no:` from a gate that means "cannot proceed")
   from `done` to `failed`.

3. Where the loop has no `on_max_steps`/`on_max_iterations` handler and budget
   exhaustion means the work did not complete, point it at `failed` — but note
   the BUG-158 exemption: a terminal named as the `on_max_steps` handler *does*
   run its action, so it may legitimately carry one.

Reference shapes already in-tree: `spike-gate.yaml` (`blocked`, `impl_failed`),
`rn-build.yaml` (`abort_normalize`, `build_failed`, `failed`),
`proof-first-task.yaml`.

**Do not** blanket-rewrite every `on_error` — some are deliberate retry or
fall-through edges (e.g. `docs-sync`'s `route_results.on_error -> verify_docs`
re-runs the check). Each edge needs a read.

## Integration Map

### Files to Modify

39 loop YAMLs under `scripts/little_loops/loops/` (all currently terminal-`done`-only):

`apo-beam`, `apo-contrastive`, `apo-feedback-refinement`, `apo-opro`,
`apo-textgrad`, `autodev`, `backlog-flow-optimizer`, `context-health-monitor`,
`dataset-curation`, `dead-code-cleanup`, `docs-sync`, `examples-miner`,
`fix-quality-and-tests`, `harness-multi-item`, `harness-optimize`,
`harness-plan-research-implement-report`, `harness-single-shot`,
`incremental-refactor`, `issue-discovery-triage`, `issue-refinement`,
`issue-staleness-review`, `learning-tests-audit`, `loop-specialist-eval`,
`migrate-sdk-version`, `oracles/integrate-node`, `oracles/oracle-capture-issue`,
`oracles/plan-research-iteration`, `oracles/research-coverage`, `p5js-sketch-generator`
(pending re-check), `policy-refine`, `prompt-regression-test`, `rl-rlhf`,
`rlhf-svg-refine`, `rn-plan-apo`, `rubric-refine`, `scan-and-implement`,
`sft-corpus`, `sprint-refine-and-implement`, `test-coverage-improvement`,
`worktree-health`.

(`learning-tests-audit` and `migrate-sdk-version` currently have `done` +
`done_empty`; both are non-failure.)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/executor.py` — sub-loop routing reads
  `failure_terminal`; flipping these edges changes child-loop routing outcomes.
- `scripts/little_loops/parallel/worker_pool.py`,
  `scripts/little_loops/learning_tests/gate.py` — read subprocess exit code 2.
- `scripts/little_loops/history_reader.py` — `_WASTED_RUN_PREDICATE`.

### Similar Patterns

- The 15 loops already converted by ENH-2814 are the reference; match their
  naming (`failed` / `<verb>_failed` / `blocked`).

### Tests

- `scripts/tests/test_builtin_loops.py` — add a coverage assertion that every
  non-`lib/` loop yields a non-empty `get_failure_states()`, so new loops cannot
  regress the invariant.
- `scripts/tests/test_enh2814_failure_terminal_e2e.py` — existing e2e shape to
  extend if a representative loop is smoke-tested.

### Documentation

- `docs/generalized-fsm-loop.md` — failure-terminal convention section (already
  written by ENH-2814; update if the sweep changes guidance).
- `CHANGELOG.md`.

### Configuration

- N/A.

## Resolution Note (2026-07-26)

The scope above was refined during implementation. Two findings changed it:

1. **Budget exhaustion was already observable.** `max_steps` maps to
   `final_status: "interrupted"` and `EXIT_CODES["max_steps"] == 1`, so the ~17
   loops whose only "failure" was running out of steps already exit non-zero.
   Routing `on_max_steps` at a failure terminal would have *lost* the
   ran-out-of-budget distinction, so step 3 above was dropped.
2. **The real defect is narrower and sharper than "no failure terminal".** It is
   an edge that routes a *failure* into a *success terminal* — exit 0,
   `final_status: "completed"`. Counting loops by "has a `failure: true`
   terminal" both over- and under-counted: several of the 39 had no failure edge
   at all, while loops **not** in the 39 (`general-task`, `rn-build`,
   `outer-loop-eval`, `rlhf-svg-evaluate`, `html-website-generator`,
   `pixi-generative-art`, `prompt-across-issues`, `refine-to-ready-issue`) had a
   failure terminal *and still* routed `on_error` to `done`.

The implemented rule: **no `on_error` / `on_failure` / `on_retry_exhausted` edge
may terminate in a terminal lacking `failure: true`.** Recoverable edges that
route to a non-terminal retry/fallback state are untouched. 31 edges across 26
loops were repointed; new `failed` terminals were added only where one was
needed as a target. Enforced by
`test_builtin_loops.py::test_no_failure_edge_routes_to_a_success_terminal`.

### Deliberate exemptions

Two `general-task.yaml` edges were repointed and then **reverted**: they encode a
prior decision, not an accident, and the sweep should not silently override it.

- `summarize_success.on_error -> done` (ENH-2365)
- `write_partial_summary.on_error -> partial` (ENH-2575)

In both cases the state writes a *summary file* after the verdict is already
determined. A failed summary write does not retract the verdict the run earned.
`partial` is additionally a non-`done` terminal, so parent sub-loop dispatch
already routes it to `on_failure` rather than laundering it as success. Both are
carried as an explicit keyed exemption in the regression guard, tagged with the
owning issue.

### Known remaining gap

`autodev.yaml`'s `abort_env_not_ready` (host auth not configured) still routes
`next: finalize_done` → `done`, so an auth abort exits 0. Fixing it means either
losing the run summary or splitting `finalize_done`, and it interacts with the
BUG-1226 in-flight warning — left for a follow-up rather than guessed at here.

## Implementation Steps

1. Re-run the detection scan to get the current list (it shifts as loops land).
2. Batch the 39 loops by shape: simple linear loops with one `done` (majority),
   loops with an existing `done_empty`/partial terminal, and the large
   orchestrators (`autodev`, `scan-and-implement`, `sprint-refine-and-implement`)
   which need individual review.
3. Edit each loop; run `ll-loop validate <loop>` after each batch and require 0
   errors (filter `--json` on severity — grepping for "error" false-positives on
   state names containing the word).
4. Add the `test_builtin_loops.py` invariant test.
5. Full suite + `ll-loop validate` sweep; update CHANGELOG.

## Impact

- **Blast radius**: 39 loop YAMLs; no Python production changes expected beyond
  one new test.
- **Behavioral change**: loops that previously exited 0 on failure now exit 2.
  Any caller currently treating exit 0 as "ran" will start seeing failures — that
  is the point, but `ll-parallel` / `ll-sprint` / `ll-queue` behavior on the
  touched loops should be spot-checked.
- **Risk**: mis-classifying a recoverable edge as terminal-failure would abort
  runs that previously self-corrected. Mitigated by per-edge review, not scripting.

## Scope Boundaries

**In scope**: adding failure terminals and re-routing error/abort edges in the 39
built-in loops; the regression-guard test.

**Out of scope**: migrating the 15 already-converted loops from the name-convention
default to explicit `failure:` declarations (separate follow-on); changing the
FSM engine, exit-code contract, or persistence schema (ENH-2814, done); adding
`on_max_steps` handlers to loops that lack them for reasons unrelated to failure
terminals.

## Backwards Compatibility

Exit code changes from 0 to 2 on failing runs of the touched loops. This is a
deliberate breaking change to an incorrect contract, consistent with ENH-2814.
`loop_runs` rows written before the sweep keep `final_status: "completed"`;
`history_reader` already carries the documented NULL fallback for pre-ENH-2814
rows.

## API/Interface

No Python API change. The loop-authoring contract gains an enforced expectation:
every loop declares at least one `failure: true` terminal.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Failure-terminal convention and schema table |
| `.claude/CLAUDE.md` § Loop Authoring | Meta-rule table incl. `terminal-action-ok` (BUG-2813) |
| `docs/reference/CLI.md` § Exit Codes (ENH-2814) | Exit-code contract this sweep activates |

## Session Log
- `/ll:capture-issue` - 2026-07-26T05:58:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-07-26
