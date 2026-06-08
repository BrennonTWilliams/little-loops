# Fix rn-build resume: sub-loop `run_dir` crash + silent "done" masking

## Context

The `rn-build` resume run (`rn-build-20260608T150202`) reported **"done (6 iterations, 1m 45s)"** but built and verified **nothing**. The user expected it to continue until the project was fully built and verified.

It did not "stop partway" — it never started building. The 6 iterations were all plumbing: `init → resume → resume_read_harness → cluster_execute → check_harness_name → synthesize_result → done`. The one state that took real time (`synthesize_result`, 1m45s) just wrote a report *about* the failure.

### Root cause (source-confirmed)

When a sub-loop is invoked with an explicit `with:` block, `FSMExecutor._execute_sub_loop` builds the child context **without inheriting the parent's auto-injected `run_dir`**:

```python
# scripts/little_loops/fsm/executor.py:545  (the `if state.with_:` branch)
child_fsm.context = {**child_fsm.context, **resolved}   # parent run_dir is dropped
```

Contrast the legacy passthrough branch, which *does* inherit parent context:

```python
# executor.py:553  (the `elif state.context_passthrough:` branch)
child_fsm.context = {**self.fsm.context, **captured_as_context, **child_fsm.context}
```

`rn-build`'s `cluster_execute` state uses a `with:` block (`goals`, `auto`, `propagate_context`, `schedule_mode`, `max_batch_size`) but does **not** pass `run_dir`. `goal-cluster` declares no `run_dir` in its `context:` defaults yet references `${context.run_dir}` in 14 places — the very first being `load_goals`:

```python
# goal-cluster.yaml:44-45  (load_goals)
run_dir = '${context.run_dir}'      # interpolates to '' in the sub-loop
os.makedirs(run_dir, exist_ok=True) # os.makedirs('') -> FileNotFoundError
```

So `load_goals` crashes in **0 seconds** → `evaluate: exit_code` → `on_error: failed`. The log confirms this exactly: `fsm: · → [load_goals] → dedup_and_batch,failed` then `-> failed`. (The synthesis LLM's phrasing "Path 'run_dir' not found in context" was a correct-in-spirit diagnosis of the same empty-`run_dir` condition.)

### Why the failure was reported as success

Three compounding design issues turned a hard crash into a clean "done":

1. **Fire-and-proceed masking** — `cluster_execute` routes `on_error: check_harness_name`, swallowing the sub-loop crash.
2. **Resume skips eval silently** — no `--context resume_harness` was given, so `resume_read_harness` produced an empty harness name and `check_harness_name` routed `on_no/on_error: synthesize_result`, bypassing the eval gate entirely.
3. **`synthesize_result` always terminates `done`** — all four outcomes (`on_yes/on_no/on_partial/on_error`) → `done`. There is no non-success terminal, so the loop exits clean regardless.

Note: this project never installed a harness (the prior `12:04` run was force-shutdown during `commit`, before reaching `eval_harness`), and `EPIC-001` is still all-design with zero application code. So even with the crash fixed, resume has no harness to verify against and the EPIC's child list is stale.

---

## Changes

### 1. Framework fix — preserve `run_dir` across `with:` sub-loops (primary)

**File:** `scripts/little_loops/fsm/executor.py` (the `if state.with_:` branch, ~line 545)

After building `child_fsm.context = {**child_fsm.context, **resolved}`, re-inject the runner-managed `run_dir` invariant that every loop relies on, without leaking arbitrary parent context:

```python
child_fsm.context = {**child_fsm.context, **resolved}
# Runner-managed runtime keys must survive explicit `with:` binding. A child loop
# always expects run_dir to be present (writes goals.json, batch-plan.json, etc.);
# the legacy passthrough branch inherits it via **self.fsm.context, so the with:
# branch must too — otherwise ${context.run_dir} resolves to '' and the child's
# first os.makedirs('') crashes.
if "run_dir" in self.fsm.context:
    child_fsm.context.setdefault("run_dir", self.fsm.context["run_dir"])
```

`setdefault` keeps an explicit `with: run_dir:` override winning if a caller ever sets one. This fixes **all** `with:`-style sub-loop callers, not just `rn-build`.

### 2. Targeted fix — pass `run_dir` explicitly (belt-and-suspenders)

**File:** `scripts/little_loops/loops/rn-build.yaml` — `cluster_execute.with:` (~line 476)

```yaml
  with:
    goals: "${captured.epic_id.output}"
    run_dir: "${context.run_dir}"      # ADD: thread parent run dir into goal-cluster
    auto: "true"
    propagate_context: "true"
    schedule_mode: "value_ranked"
    max_batch_size: "5"
```

Undeclared `with:` keys flow through `interpolate_dict` → the merge at executor.py:545 unchanged, so this works even without change #1. Redundant once #1 lands, but documents the dependency and protects against regressions.

### 3. Stop reporting "done" when the build hard-failed (masking)

**File:** `scripts/little_loops/loops/rn-build.yaml`

- Split `cluster_execute` routing so a hard sub-loop crash is distinguishable from a partial/soft result:
  - `on_yes`/`on_no` → `check_harness_name` (unchanged — partial work is still worth validating).
  - `on_error` → a new `cluster_failed` state that records the failure (writes a marker into `${context.run_dir}`) and routes to `synthesize_result`.
- Add a non-success terminal and route the hard-failure synthesis to it, so `ll-loop`'s exit verdict reflects reality:
  ```yaml
  build_failed:
    terminal: true
    success: false   # match how other loops mark failed terminals (mirror `failed:`)
  ```
  Have `synthesize_result` route to `build_failed` instead of `done` when `cluster_result` is empty / a crash marker is present (gate via its `evaluate`, or branch through a small `check_build_outcome` shell state before the terminal). Keep `done` for genuine completions.

This is the change that most directly answers the user's complaint: a build that does nothing must not exit "done".

### 4. Resume must not silently skip verification (eval gate)

**File:** `scripts/little_loops/loops/rn-build.yaml` — `resume_read_harness` (~line 206)

Extend the harness lookup so resume can actually verify:
1. Use `${context.resume_harness}` if provided (current behavior).
2. Else scan the most recent **prior** `.loops/runs/rn-build-*/harness-name.txt` for a recorded harness.
3. Else scan `.loops/*.yaml` for an installed project harness loop.
4. If still none, print a **loud warning** that eval will be skipped (no silent bypass).

For *this* project specifically, steps 2–3 will find nothing because no harness was ever installed — so resume here cannot verify until a harness exists (see change #5 / Verification).

### 5. Reconcile EPIC-001 children with the real issue set

**Files:** `.issues/epics/P2-EPIC-001-*.md` and `.issues/features/P2-FEAT-009..014`, `FEAT-002`

`goal-cluster.load_goals` resolves an EPIC via `ll-issues list --parent EPIC-001 --format json`. EPIC-001's `relates_to`/children currently list `FEAT-003..008`, but the actual refined, implementation-ready issues are `FEAT-009..014` (+ `FEAT-002` done). Reconcile so the parent query returns the intended goals:
- Update EPIC-001 `relates_to` and its children section to the real set (`FEAT-002`, `FEAT-009..014`), or formally re-scope.
- Ensure each `FEAT-009..014` carries the `parent: EPIC-001` linkage that `ll-issues list --parent` keys on.
- Verify with `ll-issues list --parent EPIC-001 --format json` returning exactly the intended issues before re-running.

---

## Verification

1. **Unit-level (framework):** From `scripts/`, run the FSM executor tests (`pytest` for `fsm/executor`), and add a regression test asserting a sub-loop invoked with a `with:` block receives the parent's `run_dir` in `child_fsm.context`.
2. **Sub-loop smoke:** `ll-loop run goal-cluster --context goals=EPIC-001 --context run_dir=.loops/tmp/gc-smoke` and confirm `load_goals` writes `goals.json` (no `os.makedirs('')` crash).
3. **EPIC linkage:** `ll-issues list --parent EPIC-001 --format json` returns the reconciled `FEAT-002, FEAT-009..014` set.
4. **End-to-end resume (no harness):** Re-run the exact command:
   ```
   ll-loop run rn-build --clear --show-diagrams clean \
     --context resume_epic=EPIC-001 --context spec=PROJECT-SPEC.md
   ```
   Expect: `cluster_execute` now enters `goal-cluster` and proceeds past `load_goals` into `dedup_and_batch` and batch dispatch (iteration count climbs well past 6; wall-clock far exceeds 1m45s). With no harness installed, expect the **loud "eval skipped" warning** (change #4), not a silent `done`.
5. **End-to-end resume (with harness):** After a harness is installed (front-half `eval_harness`, or `ll-loop install harness-*` customized for this project), re-run with `--context resume_harness=<name>` and confirm the run reaches `eval_gate` and terminates `done` only on a real pass — and `build_failed` (non-success exit) if `goal-cluster` hard-crashes.

## Out of scope / follow-ups
- The prior `12:04` run's staged-but-uncommitted issue files (force-shutdown during `commit`). Commit/clean separately.
- Installing the actual project eval harness — required before resume can *verify*, but a distinct task from these loop fixes.
