---
id: ENH-3084
type: ENH
title: Learning gate has no verdict distinguishing infra contention from implementation
  failure
priority: P3
status: open
testable: true
captured_at: '2026-08-06T16:17:02Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- learning-gate
- ll-auto
- autodev
- fsm-concurrency
relates_to:
- BUG-3083
- BUG-2864
- BUG-2833
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3084: Learning gate has no verdict distinguishing infra contention from implementation failure

## Summary

`run_learning_gate_for_issue()` returns one of four verdicts —
`passed` / `blocked` / `impl_failed` / `skipped` (`learning_tests/gate.py:66-72`).
There is no verdict for "the gate never ran." Every non-zero, non-
`FAILURE_TERMINAL_EXIT_CODE` exit — scope-lock conflict, missing binary, crash —
collapses to `impl_failed` (`gate.py:169-183`), which `issue_manager.py:1130-1147`
turns into `IMPLEMENT_FAILED <ID>` and a `failure_reason` of
"Learning gate: implementation failed."

> **Anchor refresh, 2026-08-06.** Every `gate.py` line number and the constant name
> `_QUEUE_WAIT_TIMEOUT_SECONDS` cited by this issue's original refine pass were captured
> *before* BUG-3085's fix rewrote the targets branch. They have been corrected throughout.
>
> **All `gate.py` anchors below refer to the working tree, not `HEAD`.** BUG-3085's fix is
> **uncommitted local work** as of 2026-08-06 — `HEAD` still carries
> `_QUEUE_WAIT_TIMEOUT_SECONDS = 900` at `gate.py:27`, while the working tree has
> `_QUEUE_WAIT_BACKSTOP_SLACK_SECONDS` and the `--queue-timeout` child flag. Implement on
> top of that working tree, and re-verify the anchors if it is rebased or discarded before
> this issue starts.
>
> See [Post-BUG-3085 rewrite](#post-bug-3085-the-timeoutexpired-path-no-longer-means-what-this-issue-assumed)
> — the change is not cosmetic; it moves the scope-lock case out of the `TimeoutExpired`
> path entirely.

That verdict is a deliberate improvement over BUG-2864's prior behavior (which
misreported these as `blocked`), but it is still wrong in the other direction:
an infra condition is reported as a claim about the implementation.

## Current Behavior

A scope-lock conflict produces:

```
[01:18:47] Learning gate impl-failed for ENH-3073: implementation failed
IMPLEMENT_FAILED ENH-3073
```

Downstream, `IMPLEMENT_FAILED` is the generic-failure marker that `autodev` /
`rn-remediate.yaml:907` route to remediation. So a transient lock contention
burns a remediation cycle on an issue whose implementation was never attempted,
and the run summary reports it as a failed implementation.

## Expected Behavior

A verdict that says the gate could not run, distinct from both "targets refuted"
and "implementation failed." Callers can then retry, skip the gate, or defer
with an accurate reason, instead of consuming remediation budget.

## Motivation

Failure-reason accuracy is what makes the automation loops' routing decisions
correct. A misclassified infra failure is worse than a loud crash: it produces a
plausible-looking but false statement about the issue ("implementation failed"),
which then drives the wrong remedy. This is the third iteration on the same
classification boundary (BUG-2833 split `impl_failed` from `blocked`; BUG-2864
split infra from `blocked`) — the missing axis is infra vs. impl.

The operator-facing cost: someone reading the run summary sees `ENH-3073: Learning
gate: implementation failed` and has no signal that nothing was implemented at
all. Recovering the real reason requires reading the logged subprocess stderr.

## Proposed Solution

Add a fifth verdict, e.g. `infra_failed`, to the `Literal` return type:

```python
) -> Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]:
```

Return it from the three infra paths in the targets branch (non-terminal
non-zero exit, `TimeoutExpired`, `FileNotFoundError`), and keep `impl_failed`
for the `proof-first-task` fallback branch's genuine delegated-impl failures
(BUG-2833's case).

In `issue_manager.py`, handle `infra_failed` with its own marker and reason —
e.g. print `GATE_INFRA_FAILED <ID>` (mirroring the existing `LEARNING_GATE_BLOCKED`
/ `ENV_NOT_READY` token convention, ENH-2353) and set
`failure_reason="Learning gate could not run: <reason>"`. Loops that capture
`ll-auto --only ... 2>&1` can then route on the new token — retry or skip rather
than remediate.

Decide as part of implementation whether `ll-auto` should retry once in-process
on `infra_failed` before giving up, or leave the retry policy entirely to the
calling loop. Prefer leaving it to the loop unless a cheap bounded retry is
clearly safe.

## API/Interface

`run_learning_gate_for_issue()`'s return `Literal` widens by one member. All
call sites must handle it: `issue_manager.py:1110`, and check
`cli/sprint/run.py` (`_run_learning_gate_preflight()`) and
`parallel/worker_pool.py:88` for the same pattern.

## Scope Boundaries

- **In scope**: the verdict enum, the three infra return paths, the caller
  branches and their stdout markers, and the loop YAML routing that consumes
  the new token.
- **Out of scope**: fixing the scope-lock conflict itself (BUG-3083, **already
  landed — `status: done`**) and the queue-timeout budget mismatch (BUG-3085,
  **fixed in the working tree but not yet committed** as of 2026-08-06; `HEAD`
  still has the old 900s constant). This issue makes the failure *legible*; those
  make it *rare*. Both have now done so, which lowers the frequency this issue
  addresses but not its correctness argument — a misclassified infra failure is
  still reported as an implementation failure whenever one does occur.
  **Sequencing note:** BUG-3085's working-tree change should be committed before
  this issue is implemented, or the two will conflict in the same ~60 lines of
  `gate.py`'s targets branch.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/learning_tests/gate.py` | `run_learning_gate_for_issue` | New `infra_failed` verdict |
| `scripts/little_loops/issue_manager.py` | learning-gate block, ~1105-1147 | New branch + marker |
| `scripts/little_loops/cli/sprint/run.py` | `_run_learning_gate_preflight` | Handle new verdict |
| `scripts/little_loops/loops/rn-remediate.yaml` | outcome-token routing | Route the new token |
| `scripts/tests/test_learning_tests_gate.py` | — | Cover each infra path |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `scripts/little_loops/cli/sprint/run.py` (`_run_learning_gate_preflight`, lines 198-262) and `scripts/little_loops/parallel/worker_pool.py` (`_run_per_worktree_proof_first_gate`, lines 52-125, not line 88 specifically) do not call `run_learning_gate_for_issue()`. Both shell out to their own subprocess independently (`ready-to-implement-gate` and `proof-first-task` respectively) and branch on raw `returncode` into a binary `int`/`bool`, already collapsing terminal-refuted and infra-crash outcomes identically. A repo-wide grep confirms `run_learning_gate_for_issue` is imported/called only from `scripts/little_loops/issue_manager.py:46,1110` in production. See Program Design → Call Path for the full analysis.
- `GATE_FAILED` vs. `GATE_FAILED_INFRA` (`scripts/little_loops/loops/rn-remediate.yaml:552-601`) is a direct existing precedent for this same infra-vs-impl split, already shipped for the code-run gate (`record_gate_failure` vs. `record_gate_error`) under FEAT-2552/ENH-2005.
- Marker tokens (`IMPLEMENT_FAILED`, `LEARNING_GATE_BLOCKED`, `ENV_NOT_READY`, `GATE_FAILED_INFRA`) are hardcoded string literals at each Python `print(..., flush=True)` / YAML `echo` emission site — no shared constants module. `rn-remediate.yaml:913` keeps a manually-updated prose inventory comment listing all current tokens that would need a new `GATE_INFRA_FAILED` entry.
- `rn-remediate.yaml`'s outcome-token routing (lines 945-1009) is a linear chain of single-pattern `output_contains` router states, most-specific-token-first, each `on_no` falling through to the next. `check_learning_gate` (`rn-remediate.yaml:603-619`) only greps for `LEARNING_GATE_BLOCKED` via the `ll_auto_learning_gate_check` fragment (`loops/lib/common.yaml:340`) — that fragment needs to recognize the new token before any router state can act on it. `rn-implement.yaml:754-1020` duplicates this routing chain independently and would need the same new state — there is no shared fragment for this specific chain today.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — a **third** routing chain beyond the two the plan names: its own `check_learning_gate` state (`:928-940`) consumes the shared `ll_auto_learning_gate_check` fragment. If the fragment is widened to also grep `GATE_INFRA_FAILED` while still emitting the single `GATE_BLOCKED` signal, autodev would route an infra failure to `mark_gate_blocked` (`:942-964`), which defers via `--reason gate_blocked` with the "unproven external-API deps / /ll:explore-api" message — the wrong reason/message for infra contention. Needs a distinct infra discriminator before the fragment is extended. [Agent 1 + Agent 2 finding]
- Confirmed **not affected** (module-level `is_record_stale`/`format_nudge_message` imports, untouched by this change — do not edit): `scripts/little_loops/cli/ctx_stats.py:30`, `scripts/little_loops/cli/history_context.py:67`, `scripts/little_loops/cli/learning_tests.py:42`, `scripts/little_loops/learning_tests/release_gate.py:19`, `scripts/little_loops/hooks/install_learning_gate.py:31`, `scripts/little_loops/hooks/learning_tests_gate.py:28`, `scripts/little_loops/fsm/executor.py:1113`. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_implement.py:788-821` — `test_state_count_is_orchestrator_sized` asserts `state_count <= 46`; the new `route_rem_gate_infra_failed` router pushes it to 47 → **will break**; raise the ceiling (the docstring keeps a per-issue raise history). [Agent 3 finding]
- `scripts/tests/test_rn_implement.py:1310-1318` — `test_route_rem_learning_gate_points_at_prove_state` asserts `router["on_no"] == "route_rem_gate_failed"`; inserting the infra router on that edge → **will break**. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:14360-14382` — `test_rn_implement_routes_learning_gate_before_failure` asserts the same `on_no == "route_rem_gate_failed"` edge → **will break**. [Agent 3 finding]
- `scripts/tests/test_issue_manager.py` — `TestAutoManagerLearningGate` (`:4767-5026`) has no `infra_failed` case; add an AC 3 anti-fall-through test (model `test_impl_failed_gate_verdict_skips_implement_phase`, `:4889-4915`) and an AC 4 marker/reason test (model `:4917-4942`). [Agent 2 + Agent 3 finding]
- `scripts/tests/test_rn_implement.py` — new `TestRouteRemGateInfraFailed`, mirroring `TestRouteRemGateFailed` (`:1789-1847`) — the AC 7 "token not silently swallowed by the generic bucket" router shape. [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py` — add a `GATE_INFRA_FAILED` parallel of `test_learning_gate_check_still_detects_marker_amid_adversarial_output` (`:2576-2582`). [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` — add a `GATE_INFRA_FAILED` emit-state test (model `test_record_gate_error_writes_gate_failed_infra_sidecar`, `:2157-2164`). [Agent 3 finding]
- Anchor correction: AC 6's `test_scope_conflict_never_clearing_yields_impl_failed` lives at `test_learning_tests_gate.py:323-337` in the current working tree, not `:280-294` — the BUG-3085 rewrite shifted it. [Agent 3 finding]

Conditional — only if the infra discriminator is wired through the shared fragment (adds a state):
- `scripts/tests/test_builtin_loops.py:14323-14329` — `test_rn_remediate_check_learning_gate_falls_through_to_auth` asserts `check_learning_gate.on_yes/on_no`; those edges change if the discriminator lives on the fragment. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:233-240` — `test_autodev_topology` asserts exactly 79 autodev states; breaks only if autodev gains a state. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:249-326` — outcome-token table lists `LEARNING_GATE_BLOCKED`; add a `GATE_INFRA_FAILED` row and update the fragment-screening prose. [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:3346` — `ll_auto_learning_gate_check` fragment table row ("greps ... for the `LEARNING_GATE_BLOCKED` marker ... emits `GATE_BLOCKED` or `OK`") goes stale once the fragment recognizes the new token. [Agent 2 finding]
- Note: `rn-implement.yaml` has **no** parallel token-inventory comment (only `rn-remediate.yaml:913` does), so nothing to update there. [Agent 2 finding]

## Program Design

### Types

- `Literal["passed", "blocked", "impl_failed", "skipped"]` (`scripts/little_loops/learning_tests/gate.py:66-72`, the return type of `run_learning_gate_for_issue()`) widens to `Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]`. This is the first true widening of this `Literal`'s member set — BUG-2833 and BUG-2864 (the two prior iterations on this classification boundary) each reused the existing `impl_failed` member and changed only which code paths returned it, not the enum's shape.

### Signatures

Current, at `gate.py:66-72` — only the return `Literal` widens, params are unchanged. Note
every parameter after `issue_path` is **keyword-only** (`*,` at `gate.py:68`); an earlier
draft of this section quoted the signature without it:

`run_learning_gate_for_issue(issue_path: Path, *, skip: bool = False, cwd: Path | None = None, targets: list[str] | None = None) -> Literal["passed", "blocked", "impl_failed", "skipped"]`

Widened:

`run_learning_gate_for_issue(issue_path: Path, *, skip: bool = False, cwd: Path | None = None, targets: list[str] | None = None) -> Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]`

Unchanged constant, imported function-locally in both branches of `gate.py` (lines 167 and 202):

`FAILURE_TERMINAL_EXIT_CODE: int = 2` — defined at `scripts/little_loops/fsm/types.py:25`.

Constants local to `gate.py`'s targets branch, post-BUG-3085:

- `_QUEUE_WAIT_BACKSTOP_SLACK_SECONDS = 60` (`gate.py:28`) — module-level.
- `_queue_wait_budget` — a **local**, read per-call from
  `BRConfig(working_dir).loops.queue_wait_timeout_seconds` (default `86400`,
  `config/features.py:748`). It is passed to the child as `--queue-timeout` *and* used as
  the outer `subprocess.run(timeout=_queue_wait_budget + _QUEUE_WAIT_BACKSTOP_SLACK_SECONDS)`.
  The module-level constant `_QUEUE_WAIT_TIMEOUT_SECONDS` that this issue originally named
  **no longer exists**.

### Call Path

`issue_manager.py:1110-1112` (`run_learning_gate_for_issue()` call site) → **targets branch** (`gate.py:121` `if targets:`) has two of the three infra paths already implemented and one entirely missing:
- `TimeoutExpired` (`gate.py:155-162`, caught around the `subprocess.run(..., timeout=_queue_wait_budget + _QUEUE_WAIT_BACKSTOP_SLACK_SECONDS)` call at `gate.py:148-154`) — currently `return "impl_failed"` at line 162. **Read the post-BUG-3085 note below before treating this as the scope-lock path — it no longer is.**
- Non-terminal non-zero exit (`gate.py:169-183`, the branch after checking `returncode == 0` → `"passed"` at `:170` and `returncode == FAILURE_TERMINAL_EXIT_CODE` → `"blocked"` at `:172`) — currently `return "impl_failed"` at line 183, with an existing comment explicitly identifying this as "Infra failure (scope-lock conflict, crash, missing binary)." Post-BUG-3085 this branch also absorbs queue-wait exhaustion.
- `FileNotFoundError` — **not currently caught anywhere in `gate.py`** (zero `except FileNotFoundError` matches). If the `ll-loop` binary is missing, `subprocess.run()` at `gate.py:148-154` raises uncaught, propagating out of `run_learning_gate_for_issue()` rather than yielding any verdict at all. This path needs new `try/except` coverage, not a re-mapping of an existing return.

#### Post-BUG-3085: the `TimeoutExpired` path no longer means what this issue assumed

_Added 2026-08-06 during pre-implementation review._ BUG-3085's fix (present in the working
tree, not yet committed) changed the shape of the targets branch in a way that directly
affects this issue's trigger set:

The child is now invoked with `--queue --queue-timeout <budget>` (`gate.py:132-146`), and
the parent's `subprocess.run` timeout is deliberately set *above* that budget
(`budget + 60s`) as a backstop for a genuinely wedged child. So a scope-lock wait that
exhausts its budget now makes **`ll-loop` exit non-zero on its own** and lands in the
`returncode not in (0, FAILURE_TERMINAL_EXIT_CODE)` branch. It no longer raises
`TimeoutExpired` in the parent.

Two consequences for implementation:

1. **`TimeoutExpired` now means "genuinely wedged child," not "scope-lock contention."**
   Both are still `infra_failed`, so the verdict is unaffected — but the *reason string*
   this issue wants to surface must not describe a `TimeoutExpired` as a lock conflict.
   The `logger.error` text currently at `gate.py:156-161` still says "did not clear a
   scope-lock conflict within its %ds queue-wait budget," which is now the wrong
   description for the only condition that can reach it. Correct it while here.
2. **A finer split may now be available for free.** Because queue exhaustion is a distinct
   child exit rather than a parent-side exception, `ll-loop`'s queue-timeout exit code — if
   it is distinguishable from a crash or a missing binary — would let `infra_failed` carry a
   sub-reason ("contention, retry later" vs. "broken environment, do not retry"). Check
   `ll-loop`'s exit codes during implementation. If a distinct code exists, use it for the
   `failure_reason` text; do **not** add a sixth `Literal` member for it — the verdict axis
   this issue establishes is infra-vs-impl, and splitting infra further belongs in the
   reason string, not the enum.

→ **proof-first-task fallback branch** (`gate.py:185-209`, reached when `targets` is falsy) keeps `impl_failed` unchanged: on `returncode == FAILURE_TERMINAL_EXIT_CODE` it consults `list_run_history()` and returns `"blocked"` only if the archived `LoopState.current_state == "blocked"`, else `"impl_failed"` (this is BUG-2833's genuine delegated-impl-failure case, not an infra path). This branch currently has no `try/except`/`timeout=` at all — a hang or missing-binary here is unhandled by either verdict scheme, out of scope per the issue's own Scope Boundaries but worth the implementer noting since it is asymmetric with the targets branch.

→ `issue_manager.py:1113-1147` consumes the verdict via a plain sequential `if`/`elif` chain (not a `match`, no `assert_never`/exhaustiveness enforcement anywhere in this codebase — repo-wide grep for `assert_never` returns zero hits). `"passed"` has no explicit branch; it simply falls through the whole chain to Phase 2. A new `"infra_failed"` value, if left unhandled, would silently fall through as if `"passed"` — implementation proceeds unimplemented gates instead of erroring. The existing `"blocked"` branch (`1115-1129`, marker `LEARNING_GATE_BLOCKED`) and `"impl_failed"` branch (`1130-1147`, marker `IMPLEMENT_FAILED`) are the two-line shape (`logger.warning(...)`, `print(f"{TOKEN} {info.issue_id}", flush=True)`, `_stamped_result(success=False, failure_reason=...)`) a new `"infra_failed"` branch would follow.

**Correction to this issue's own API/Interface section**: `cli/sprint/run.py`'s `_run_learning_gate_preflight()` (`run.py:198-262`) and `parallel/worker_pool.py`'s `_run_per_worktree_proof_first_gate()` (`worker_pool.py:52-125`, not line 88 — that line falls inside this function but isn't the call site) do **not** call `run_learning_gate_for_issue()` and do not consume this `Literal` at all. Both independently shell out to their own subprocess (`ready-to-implement-gate` and `proof-first-task` respectively) and branch on raw `returncode` into a binary `int`/`bool`, collapsing terminal-refuted and infra-crash outcomes identically already. A repo-wide grep confirms `run_learning_gate_for_issue` is imported/called only from `issue_manager.py:46,1110` in production. "Sweep the other call sites" (Implementation Steps item 3) therefore has no `Literal`-consuming code to update in those two files today — if the new `infra_failed` distinction is meant to also improve routing there, that is new plumbing on a `returncode`, not a `Literal` branch, and is a separate design decision from the `Literal` widening itself.

### Decision Rules

- **New verdict**: `infra_failed`, returned when the gate subprocess never reached a genuine pass/blocked terminal — the same condition set as today's silently-mismarked `impl_failed` targets-branch returns.
- **Exact trigger set** (targets branch only, `gate.py:121-183` plus new coverage): (1) `TimeoutExpired` on the `subprocess.run` call bounded by `_queue_wait_budget + _QUEUE_WAIT_BACKSTOP_SLACK_SECONDS` — post-BUG-3085 this is the *wedged-child backstop*, not the scope-lock path; (2) `returncode not in (0, FAILURE_TERMINAL_EXIT_CODE)` — which post-BUG-3085 is where scope-lock/queue-wait exhaustion actually lands; (3) `FileNotFoundError` on the subprocess invocation (new — currently uncaught).
- **Explicit non-trigger / escape hatch**: the proof-first-task fallback branch (`gate.py:185-209`) is excluded — its `impl_failed` return (delegated-impl crash reaching a genuine FSM terminal, BUG-2833) must NOT be reclassified as `infra_failed`, per this issue's own Proposed Solution ("keep `impl_failed` for the proof-first-task fallback branch's genuine delegated-impl failures").
- **Marker convention** (no central registry — repo-wide grep confirms marker strings like `IMPLEMENT_FAILED`, `LEARNING_GATE_BLOCKED`, `ENV_NOT_READY`, `GATE_FAILED_INFRA` are hardcoded string literals at each Python `print(..., flush=True)`/YAML `echo` emission site, not sourced from a shared constants module): new token `GATE_INFRA_FAILED <ID>`, following the `f"{TOKEN} {info.issue_id}"` shape used by `LEARNING_GATE_BLOCKED`/`IMPLEMENT_FAILED`. `rn-remediate.yaml:913` keeps a manually-updated prose inventory comment of all current tokens (`IMPLEMENTED | NEEDS_DECOMPOSE | ... | GATE_FAILED_INFRA | GATE_SKIP`) that would need a new entry — nothing enforces this list stays in sync with actual emission sites.
- **Direct precedent for this exact infra-vs-impl split**: `GATE_FAILED` vs. `GATE_FAILED_INFRA` already exists for the *code-run gate* (`rn-remediate.yaml:552-601`, `record_gate_failure` vs. `record_gate_error`), shipped under FEAT-2552/ENH-2005 — same axis, different gate.
- **Routing shape**: `rn-remediate.yaml`'s outcome-token routing (`945-1009`) is a linear chain of single-pattern `output_contains` router states, most-specific-token-first, each `on_no` falling through to the next, terminating in the generic-failure bucket (`record_failure`). A new `GATE_INFRA_FAILED` token needs its own router state inserted into this chain (the codebase has no multi-branch dispatcher precedent) — and the existing `check_learning_gate` state (`rn-remediate.yaml:603-619`) only greps for `LEARNING_GATE_BLOCKED` via the `ll_auto_learning_gate_check` fragment (`loops/lib/common.yaml:340`), so that fragment (or a new one) needs to recognize the new token before any router chain can act on it. `rn-implement.yaml:754-1020` duplicates this same routing chain independently — both files need the new state, there is no shared fragment for this specific chain today.

## Implementation Steps

1. Widen the `Literal` and return `infra_failed` from the three infra paths (adding the
   `except FileNotFoundError` that does not exist today). Correct the now-inaccurate
   `TimeoutExpired` log text per the post-BUG-3085 note above.
2. Add the `elif verdict == "infra_failed":` branch in `issue_manager.py` — placed
   **before** the chain falls through — emitting `GATE_INFRA_FAILED <ID>` and setting
   `failure_reason="Learning gate could not run: <reason>"`, following the two-line shape
   of the existing `blocked` (`:1115-1129`) and `impl_failed` (`:1130-1147`) branches.
3. ~~Sweep the other call sites for exhaustive handling (mypy will flag them).~~
   **Struck 2026-08-06 — this step was wrong on both halves.** There are no other call
   sites: repo-wide grep confirms `run_learning_gate_for_issue` is imported and called
   only from `issue_manager.py:46,1110`, and the two files this issue originally named
   (`cli/sprint/run.py`, `parallel/worker_pool.py`) shell out independently and branch on
   a raw `returncode`, consuming no `Literal`. And mypy will **not** flag anything:
   widening a return `Literal` does not make an unhandled member an error in a sequential
   `if`/`elif` chain, and the repo uses no `assert_never` anywhere (zero hits).
   **Replace with the real hazard:** `"passed"` has no explicit branch — it reaches Phase 2
   by falling off the end of the chain. An unhandled `"infra_failed"` therefore falls
   through *as if it passed*, and implementation proceeds on an issue whose gate never ran.
   That silent-success path is the single most important thing to test here (AC 3).
4. Route the new token in the consuming loop YAMLs — note this is **two** independent
   routing chains (`rn-remediate.yaml:945-1009` and `rn-implement.yaml:754-1020`, which
   duplicate each other with no shared fragment), plus the `ll_auto_learning_gate_check`
   fragment (`loops/lib/common.yaml:340`) which greps only for `LEARNING_GATE_BLOCKED`
   today and must recognize the new token before any router state can act on it, plus the
   manually-maintained token inventory comment at `rn-remediate.yaml:913`.
   > ⚠ Superseded — autodev.yaml is a third routing chain
5. Tests: one per infra path, asserting the verdict and the emitted marker.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_
- Route the token in **autodev.yaml** — a third chain (`check_learning_gate`, `:928-940`) beyond the two the plan names. Give it (and rn-remediate's `check_learning_gate`, `:603-619`) a distinct infra discriminator — a second fragment emitting `GATE_INFRA`, or a discriminator state after `check_learning_gate` — before widening the shared `ll_auto_learning_gate_check` fragment; a single `GATE_BLOCKED` output cannot carry both meanings and would mis-defer an infra failure as `gate_blocked` (wrong reason/message). [Agent 2 finding]
- Insert `route_rem_gate_infra_failed` in rn-implement.yaml's `classify_remediation` chain (`:971-1009`) on `route_rem_learning_gate`'s `on_no` edge, ahead of `route_rem_gate_failed` → `record_failure` — `GATE_INFRA_FAILED` is not a substring of `GATE_FAILED`, so today it falls to the generic bucket (AC 7's failure mode). This edge churn breaks `test_rn_implement.py:1310-1318` and `test_builtin_loops.py:14360-14382`. [Agent 2 + Agent 3 finding]
- Add a `GATE_INFRA_FAILED` emit state in rn-remediate.yaml (sibling to `emit_learning_gate_blocked`, `:1129-1138`) so infra writes its own sidecar, not a `LEARNING_GATE_BLOCKED` one (`:1136`). [Agent 2 finding]
- Update the three breaking tests and add the four new test groups listed in Integration Map → Tests. [Agent 3 finding]
- Update `docs/guides/RECURSIVE_LOOPS_GUIDE.md` and `docs/guides/LOOPS_REFERENCE.md` per Integration Map → Documentation. [Agent 2 finding]

## Acceptance Criteria

_Added 2026-08-06 during pre-implementation review — this issue previously had none._

1. `run_learning_gate_for_issue`'s return `Literal` includes `infra_failed`, and the
   targets branch returns it for all three infra conditions: `TimeoutExpired`,
   `returncode not in (0, FAILURE_TERMINAL_EXIT_CODE)`, and `FileNotFoundError`.
2. `FileNotFoundError` from `subprocess.run` is caught and yields `infra_failed` rather
   than propagating out of the function uncaught, as it does today.
3. **Anti-fall-through:** a test asserts that a gate returning `infra_failed` causes
   `issue_manager` to stop and report failure — *not* to proceed to Phase 2. Without this,
   the widening's failure mode is a silent success, which is strictly worse than the
   misclassification this issue fixes.
4. `issue_manager` prints `GATE_INFRA_FAILED <ID>` and sets a `failure_reason` naming the
   infra cause, distinct from "Learning gate: implementation failed."
5. The proof-first-task fallback branch (`gate.py:185-209`) still returns `impl_failed` for
   its genuine delegated-implementation failure; BUG-2833's tests
   (`TestRunLearningGateForIssueTerminalDiscrimination`) are unchanged.
6. The two existing tests that assert the collapsed verdict are flipped to `infra_failed`:
   `test_infra_failure_yields_impl_failed_not_blocked` (`test_learning_tests_gate.py:225-243`)
   and `test_scope_conflict_never_clearing_yields_impl_failed` (`:280-294`). Rename both —
   their names encode the behavior being removed.
7. Both routing chains (`rn-remediate.yaml`, `rn-implement.yaml`) have a router state for
   `GATE_INFRA_FAILED` ahead of the generic-failure bucket, and the token routes to
   retry/skip rather than remediation. A test asserts the token is not silently swallowed
   by the generic bucket in either file.
8. `loops/lib/common.yaml:340`'s `ll_auto_learning_gate_check` fragment recognizes the new
   token, and `rn-remediate.yaml:913`'s token inventory comment lists it.
9. `docs/reference/API.md`'s `little_loops.learning_tests.gate` entry documents the fifth
   verdict.
10. `python -m pytest scripts/tests/` exits 0.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Two existing tests in `scripts/tests/test_learning_tests_gate.py` (class `TestRunLearningGateForIssueDirectInvocation`) currently assert the collapsed `impl_failed` verdict for exactly the two implemented infra paths and must flip their assertion to `infra_failed`: `test_infra_failure_yields_impl_failed_not_blocked` (lines 225-243, mocks a plain `returncode=1` result) and `test_scope_conflict_never_clearing_yields_impl_failed` (lines 280-294, mocks `subprocess.TimeoutExpired`).
- A third test for the `FileNotFoundError` path does not yet exist and needs to be added new (not converted) — that path is currently uncaught entirely, not merely collapsed into `impl_failed`. Existing tests patch `little_loops.learning_tests.gate.subprocess.run` with `return_value=`/`side_effect=` against a `tmp_path`-built issue file with minimal frontmatter (`f"---\nid: {ID}\n---\n"`) — a `side_effect=FileNotFoundError(...)` test would follow this same shape.
- `TestRunLearningGateForIssueTerminalDiscrimination` (the proof-first-task fallback branch's `blocked`/`impl_failed` tests, lines 107-173) is out of scope for this change — those assertions target BUG-2833's genuine delegated-impl-failure case, which this issue's Proposed Solution explicitly keeps as `impl_failed`.
- `cli/sprint/run.py`'s `_run_learning_gate_preflight()` and `parallel/worker_pool.py`'s `_run_per_worktree_proof_first_gate()` do not call `run_learning_gate_for_issue()` and do not consume this `Literal` — see Program Design → Call Path for the full correction. "Sweep the other call sites" (step 3) has no `Literal`-consuming branch to update in either file as currently written.

## Impact

Correct routing for a failure mode that currently consumes remediation cycles
and misreports outcomes. Low risk — additive to an enum with a small, statically
checkable set of call sites.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | `little_loops.learning_tests.gate` signature |
| `docs/reference/DEFERRAL_CODES.md` | Where an infra deferral code would be registered |

## Status

open


## Session Log
- `/ll:confidence-check` - 2026-08-07T18:16:42 - `c3385b65-8008-4cbd-a89f-ad4cc3a58492.jsonl`
- `/ll:wire-issue` - 2026-08-07T18:11:49 - `55969b1e-cf03-47ea-b399-a117b1306df5.jsonl`
- `/ll:confidence-check` - 2026-08-06T18:14:17 - `2714e173-0113-42e1-b8e8-e7f650c61db7.jsonl`
- `/ll:refine-issue` - 2026-08-06T17:41:21 - `bf1b7c6a-6d5b-4c22-84fe-40280423c7d4.jsonl`
- `/ll:capture-issue` - 2026-08-06T16:20:22 - `ee676905-966c-42aa-ac9d-d7d4aaeea91d.jsonl`
