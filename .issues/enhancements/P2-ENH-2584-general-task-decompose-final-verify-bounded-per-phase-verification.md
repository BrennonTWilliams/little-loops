---
id: ENH-2576
title: "general-task \u2014 decompose final_verify into bounded per-batch verification"
type: ENH
priority: P2
status: open
discovered_date: '2026-07-10'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- general-task
- verification
- audit
decision_needed: false
relates_to:
- ENH-2575
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# ENH-2576: general-task — decompose final_verify into bounded per-batch verification

## Summary

Root cause of the `failed` verdict in audit `general-task-audit-2026-07-09T232714.md`:
`final_verify` is a single `action_type: prompt` state asked to independently
re-verify EVERY DoD criterion (38 hard + soft in the audited run, ~56 total
items) — including full `test:coverage` and `test:e2e` runs — inside one
1800s timeout. The verification surface scales with the task, but the budget
doesn't. On any large task the state times out deterministically, and (before
ENH-2575) forfeited the run.

## Current Behavior

`final_verify` (`general-task.yaml:427-458`) is a single `action_type: prompt`
state that independently re-verifies every DoD criterion in one `1800s` timeout,
including whole-suite `test:coverage`/`test:e2e` runs. The verification workload
scales with DoD size (~56 items in the audited run) while the timeout is fixed,
so large tasks time out deterministically; before ENH-2575 that forfeited the
run outright.

## Expected Behavior

Split final verification so no single state's work grows unbounded with DoD
size. Substrate locked to **Option B (flat-file counter cursor)** via
`/ll:decide-issue` 2026-07-10 — see Proposed Solution § Decision Rationale:

- A shell state (`partition_verify`) partitions all criteria from `dod.md` into
  fixed batches of K (`ceil(N/10)`; phase-heading batching is out of scope —
  `dod.md` is a flat list), writing the criteria list once plus a
  `batch-cursor.txt` integer.
- A `verify_batch` prompt state re-verifies one batch per visit with its own
  bounded timeout, appending evidence to the `## Final Verification` section;
  loops via the cursor until all batches are processed.
- Whole-suite commands (coverage, e2e) stay in `run_final_tests` — already a
  separate mechanical state (ENH-2225) — and MUST NOT be re-run inside prompt
  verification batches.
- A batch timeout marks only that batch's criteria unverified and continues,
  routing to the ENH-2575 partial-credit chain at the end if anything is
  unverified — one slow batch can no longer forfeit the run.

## Constraints / gotchas

- `max_steps` accounting: batched verification multiplies state executions;
  audited run used 206/500. Keep batch count bounded (e.g. ceil(N/10)).
- The `count_final` gate reads `FAILED` lines from `## Final Verification`;
  batched appends must preserve that contract (or count_final must dedupe by
  criterion across batch appends).
- `check_done`'s Sample Verification replace-section logic shows the prior art
  for section rewriting; batch appends must not corrupt it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **"Batch by phase heading" is NOT available** — the canonical `dod.md` format
  written by `define_done` (`general-task.yaml:42-81`) is a *flat* bulleted list
  under one `## Verification Criteria`; there are no `## Phase N` sub-headings.
  All three shell counters (`count_done`, `count_final`, `write_partial_summary`)
  scan flat with `awk` bounded only by `/^## Verification Criteria/`…`/^## /`.
  The "Phase 3/6/7/8" labels in the audit were task-authored criterion text, not
  a structural convention. **Batch only by K.**
- **`count_final` awk resets `count=0` on EVERY `## Final Verification` heading**
  (`general-task.yaml:493-515`) — it tallies only the *most-recent* section
  (guarded by `test_two_sections_only_counts_most_recent`,
  `test_general_task_loop.py:1198`). A batched design that appends a *new*
  `## Final Verification` per batch would silently drop all but the last batch's
  FAILEDs. **Batches must append lines to a single `## Final Verification`
  section, OR `count_final`'s awk must be changed to accumulate across sections
  (drop the `count=0` reset).** The former is lower-risk and preserves the
  existing test.
- **`## Final Verification` is append-only today** (no "remove existing section
  first" instruction, unlike `## Sample Verification` in `check_done:323-336`).
  Since batched verification writes across multiple visits, the batch state must
  either seed the single section on the first batch and append lines on
  subsequent batches, or the count contract above must be adjusted.
- **No per-criterion "verified/unverified" tri-state exists** — the only state is
  the `[x]`/`[ ]` checkbox in `## Verification Criteria` plus free-form evidence
  lines. `write_partial_summary` (`:639-680`) counts whatever is still `[ ]` at
  the moment of error. A batch cursor tracks *which criteria have been
  re-verified this run*, distinct from checked/unchecked.
- **`max_steps: 500`, `on_max_steps: summarize_partial`** (`:5,9`); audited run
  used 206/500. Every state visit is one step regardless of `action_type`, so K
  batch visits cost K steps. `ceil(N/10)` (≈6 batches at N=56) stays well within
  headroom. `${context.run_dir}/plan.md` and `dod.md` are already
  circuit-exempted (`circuit.repeated_failure`, `:24-30`), so repeated `dod.md`
  touches across batch visits won't trip the repeated-failure diagnosis.

## Acceptance Criteria

- [ ] No prompt state's verification workload grows unbounded with DoD size;
      per-batch timeout is bounded and documented.
- [ ] A single batch timeout does not terminate the run; unverified criteria
      route to the partial-credit chain (ENH-2575) rather than `failed`.
- [ ] Whole-suite gates remain final-only in `run_final_tests` (ENH-2225
      invariant preserved).
- [ ] `count_final` still gates terminal `done` on zero FAILED criteria.
- [ ] Tests in `scripts/tests/test_general_task_loop.py` cover batch cursor
      progression, timeout-of-one-batch behavior, and count_final compatibility.

## Scope Boundaries

_Inferred by `/ll:format-issue --auto` from the Expected Behavior, research
findings, and the selected Option B; adjust if intent differs._

- **In scope**: decomposing `final_verify` into `partition_verify` (shell cursor)
  + a bounded-timeout `verify_batch` prompt loop that appends to a single
  `## Final Verification` section, plus rewiring the two entry edges, retargeting
  the break-on-removal tests, and updating the three doc references.
- **Out of scope**: moving or re-running whole-suite gates (`${context.test_cmd}`,
  coverage, e2e) — they remain exclusively in `run_final_tests` (ENH-2225
  invariant).
- **Out of scope**: phase-heading partitioning — `dod.md` is a flat list;
  batching is by fixed K only (`ceil(N/10)`).
- **Out of scope**: new terminal states — unverified criteria route through the
  existing `count_final.on_no` / ENH-2575 `partial` chain.
- **Out of scope**: rewriting `count_final`'s single-most-recent-`## Final
  Verification`-section awk contract; Option B preserves it (append to one
  section, cursor tracked separately in `batch-cursor.txt`).
- **Out of scope**: any persistent per-criterion tri-state beyond the run-scoped
  cursor.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — replace the single
  `final_verify` state (lines 427-458) with a partition state + a `verify_batch`
  loop; wire the terminal path `... → run_final_tests → count_final → ...`
  unchanged. `final_verify` currently has two entry edges: `count_done.on_yes`
  (line 423) and `continue_work.on_yes` (line 610) — both must route to the new
  partition state.
- `scripts/tests/test_general_task_loop.py` — add batch-cursor progression,
  timeout-of-one-batch, and `count_final` single-section compatibility tests.
- `docs/guides/LOOPS_REFERENCE.md` — general-task flow narrative names
  `final_verify` as a routing target at **four** sites (`:117`, `:119`, `:127`,
  `:129` — verified live 2026-07-10, not just "~117-119"); all four need the new
  batched shape. See the Documentation wiring subsection below for the per-line
  breakdown.

### States Involved (current line refs)
- `final_verify` — `general-task.yaml:427-458` (the monolith to decompose);
  `next: run_final_tests`, `on_error: summarize_partial` (ENH-2575).
- `run_final_tests` — `:460-491` (ENH-2225 whole-suite gate; `fragment:
  shell_exit`). **Invariant: keep `${context.test_cmd}` / coverage / e2e here
  only.** `verify_step` is already test-blocked by
  `test_verify_step_does_not_resolve_test_cmd` (`:516`, `:1228`) — model the new
  batch state on that same "no whole-suite command" constraint.
- `count_final` — `:493-515` (awk over `## Final Verification`;
  `evaluate.path: .failed_finals`, `on_no: continue_work`).
- `summarize_partial` → `write_partial_summary` → `partial` — `:616-687`
  (ENH-2575 partial-credit chain; `partial` is a distinct non-`done` terminal).
- `check_done` Step 3 — `:323-336` (replace-section prior art for `## Sample
  Verification`).

### Existing Patterns to Reuse (pattern-finder)
- **Directory batch-queue**: `goal-cluster.yaml` `init_cluster_queue` (`:287-309`)
  + `execute_cluster` (`:311-353`) — writes per-batch JSON files under
  `${context.run_dir}/batch-queue/`, pops by `os.rename` into `batch-done/`,
  signals exhaustion via `exit 1` → `on_no` exits the loop.
- **Flat-file FIFO pop + counter**: `queue_pop` / `queue_track` fragments
  (`lib/common.yaml:131-146`); consumed by `rn-implement.yaml` `fifo_pop`
  (`:147-182`) with a companion `dequeue_count.txt` cursor.
- **Counter-gate**: `retry_counter` fragment (`lib/common.yaml:23-45`,
  `output_numeric` + `lt`); consumed by `loop-composer-adaptive.yaml`
  `check_replan_budget` (`:443-456`).
- **In-loop cursor idioms already in general-task**: `select_step` treats the
  first `- [ ]` line in `plan.md` as an implicit cursor (`:158`);
  `step-attempts.txt` is an append-only per-step counter (`:171-180`);
  `checkpoint.json` (`:183-185`) is a JSON marker read by `resume_check`.

### Tests to Model After
- Shell-state harness: `_load_state_script(name)`, `_setup_run_dir(tmp_path)`,
  `_bash(script, cwd)` (`test_general_task_loop.py:415-431`); `_load_count_done_script`
  interpolates `${context.*}` (`:821-838`).
- Fixture DoD constants: `_ALL_DONE_DOD`, `_HARD_UNCHECKED_DOD`,
  `_TWO_SECTIONS_FINAL_DOD` (`:854-919`, `:1157-1168`) written into
  `run_dir/dod.md`, then the extracted shell action is run and stdout JSON asserted.
- Structural/routing assertions: `TestChange8FinalVerifyGate` (`:1081-1135`);
  timeout guard `TestBUG1724TimeoutProtection` (`:1334-1349`) requires every
  prompt state to declare a positive per-state `timeout`.

### Documentation (added by `/ll:wire-issue`)

_Wiring pass — doc locations that name `final_verify` as `count_done`'s target
and will go stale when `count_done.on_yes` is rewired to `partition_verify`.
**Corrected by `/ll:refine-issue --full-rewrite` 2026-07-10** — the previously
cited `docs/reference/loops.md:1057` is a phantom (that file is 900 lines; line
1057 does not exist, and it contains **zero** `final_verify` references). The
`total == 0 → final_verify` routing claim lives in the two files below only:_
- `skills/create-loop/loop-types.md:1057` — "Partial DoD Satisfaction Threshold"
  section: "`.total` routing field — `total == 0` routes to `final_verify`
  (terminal gate); `total > 0` routes to `continue_work`." Update the
  `total == 0` target to the new partition state (verified live 2026-07-10)
  [Agent 2 finding; file corrected].
- `docs/guides/LOOPS_REFERENCE.md` — the general-task flow narrative names
  `final_verify` as a routing target at **four** sites, not the "~117-119" the
  Files-to-Modify entry claims: **:117** (`count_done` output-json route
  `total == 0 → final_verify`), **:119** (the four-state terminal-gate
  description), **:127** (the `WORK_COMPLETE` escape hatch: `continue_work`
  "routes directly to `final_verify`, bypassing `select_step`"), and **:129**
  (the per-iteration budget narrative enumerating the four-state gate
  `final_verify + run_final_tests + count_final + summarize_success`). All four
  must reflect the new `partition_verify` entry / batched `verify_batch` loop
  [file corrected 2026-07-10].
- `docs/reference/API.md:~4661` and `docs/reference/loops.md:886-890` — illustrative
  `run_final_tests → continue_work → …` cycling examples for `recurrent_window`.
  **No change needed** (`run_final_tests` is unchanged; neither example names
  `final_verify` — re-verified live), but they are literal `run_final_tests`
  hits, so confirm during review [Agent 2 finding].
- `.ll/decisions.yaml:902,908` (`ARCHITECTURE-037`, ENH-2225) — historical decision
  record; line 908 mentions "keeps coverage gate at final_verify"; immutable
  history log, **no action required**, noted so a future reader isn't misled
  [Agent 2 finding; line refs corrected — id at :902, mention at :908].

### Tests — will break on `final_verify` removal (added by `/ll:wire-issue`)

_Wiring pass — these existing tests hardcode the `final_verify` state key and will
`KeyError`/fail once it is replaced; they need retargeting to `verify_batch` /
`partition_verify`, not just the new-coverage tests already listed in the ACs:_
- `test_general_task_loop.py` `TestGeneralTaskLoopFile.test_expected_states_present`
  (`:52-74`) — required-states set includes `"final_verify"` (`:63`). Add the new
  state names; decide whether to keep `final_verify` in the set [Agent 3 finding].
- `test_general_task_loop.py`
  `TestBUG1724TimeoutProtection.test_final_verify_has_per_state_timeout`
  (`:1345-1349`) — asserts `states["final_verify"].get("timeout",0) > 0`; retarget
  to assert `verify_batch`'s bounded (~600s) timeout [Agent 3 finding].
- `test_general_task_loop.py`
  `TestENH2225FinalOnlyGate.test_final_verify_routes_to_run_final_tests`
  (`:1261-1262`) — duplicate `next: run_final_tests` assertion; the loop-exit edge
  now originates from the cursor-exhausted `verify_batch` route, not `final_verify`
  [Agent 3 finding].
- Convention note: `TestENH2225FinalOnlyGate` was **added alongside** (not in place
  of) `TestChange8FinalVerifyGate` when `run_final_tests` was inserted. Follow the
  same convention — add a `TestENH2576BatchedVerify` class documenting the routing
  delta rather than gutting `TestChange8FinalVerifyGate` in place [Agent 3 finding].

#### Codebase Research Findings

_Added by `/ll:refine-issue --full-rewrite` — completes the break-on-removal
enumeration flagged as incomplete by the confidence-check Outcome Risk Factor
(re-grep confirmed against live `test_general_task_loop.py`). Current line refs
verified; the three tests above are NOT the full set:_

- **Two entry-edge tests hard-assert `final_verify` as the routing target** and
  break the moment `count_done.on_yes` / `continue_work.on_yes` are rewired to
  `partition_verify` (Wiring Phase step 1). Neither was in the list above; both
  must be retargeted:
  - `test_count_done_routes_yes_to_done` (`test_general_task_loop.py:184-186`) —
    asserts `count_done["on_yes"] == "final_verify"`. Retarget to
    `"partition_verify"`.
  - `test_continue_work_escape_hatch_routes_to_final_verify` (`:219-227`) —
    asserts `continue_work["on_yes"] == "final_verify"` AND that the WORK_COMPLETE
    `output_contains` escape hatch fires. Retarget the routing assertion to
    `"partition_verify"`; keep the WORK_COMPLETE evaluator assertions. Consider
    renaming the test method (`..._routes_to_partition_verify`) since the name
    encodes the old target.
- **`TestChange8FinalVerifyGate` (`:1081-1105`) has six `final_verify`-referencing
  members** (see corrected inventory below): five directly read
  `raw_data["states"]["final_verify"][...]` and `KeyError` if the state is
  removed/renamed to `verify_batch`; the sixth
  (`test_count_done_routes_yes_to_final_verify`, `:1084-1085`) reads
  `states["count_done"]["on_yes"]` and fails as a string-mismatch on the entry-edge
  rewire (not a `KeyError`) — so it is retargeted alongside, not for the same
  reason. Every member is affected, not just the routing/timeout tests named above.
  **Naming is decided, not open**: the Proposed Solution commits to the state
  key `verify_batch` for the per-batch prompt state throughout (Option A/B
  write-ups, Timeout & partial-credit wiring, Wiring Phase step 2). Because the
  key changes from `final_verify` to `verify_batch`, all five members below are
  **retargets** (not in-place edits), and their `states["final_verify"][…]` reads
  will `KeyError` until repointed. (The earlier "decide the naming first" caveat
  here was resolved by `/ll:decide-issue` and is removed to avoid contradicting
  the committed name.) The five members:
  - `test_final_verify_action_type_is_prompt` (`:1087-1088`)
  - `test_final_verify_routes_next_to_run_final_tests` (`:1090-1093`) — the
    `next: run_final_tests` edge now originates from the cursor-exhausted batch
    route; overlaps `TestENH2225FinalOnlyGate.test_final_verify_routes_to_run_final_tests`
    (`:1261-1262`) already listed above.
  - `test_final_verify_routes_error_to_summarize_partial` (`:1095-1098`) — the
    ENH-2575 `on_error → summarize_partial` edge; the per-batch timeout handler
    (Proposed Solution "mark batch unverified + advance cursor") changes this
    contract, so this assertion needs rethinking, not just retargeting.
  - `test_final_verify_action_references_dod_file` (`:1100-1101`)
  - `test_final_verify_action_has_final_verification_section` (`:1104-1105`) —
    the `## Final Verification` append instruction moves to `verify_batch`; this
    assertion follows the section-writing state.
- **Complete inventory (re-grepped live 2026-07-10, `--full-rewrite`)** —
  `grep -n 'final_verify' scripts/tests/test_general_task_loop.py` returns:
  - `:63` — `test_expected_states_present` required-states set entry (retarget;
    already flagged in "Tests — will break on removal").
  - `:186` — `test_count_done_routes_yes_to_done` asserts
    `count_done["on_yes"] == "final_verify"` (entry-edge #1; **the prior inventory
    said `:184` — off by two**).
  - `:212, :219, :221–222` — `test_continue_work_escape_hatch_routes_to_final_verify`
    (entry-edge #2; keep WORK_COMPLETE evaluator assertions, retarget routing).
  - `:1067, :1082` — comments (no change).
  - `:1084–1085` — **`test_count_done_routes_yes_to_final_verify`, the SIXTH
    `TestChange8FinalVerifyGate` member the prior `×5` count omitted.** Unlike the
    five below it does **not** read `states["final_verify"]` (so it does not
    `KeyError` on state removal); it reads `states["count_done"]["on_yes"]` and
    asserts `== "final_verify"`, so it fails as a *string-mismatch* the moment
    `count_done.on_yes` is rewired to `partition_verify` — a duplicate of the `:186`
    assertion inside the class. Retarget with the class.
  - `:1087–1105` — the five `states["final_verify"][…]` reads (×5; `KeyError` on
    removal). Class total is therefore **six** `final_verify`-referencing members,
    not five.
  - `:1151` — fixture DoD criterion text, NOT a state ref (no change).
  - `:1261–1262` — `TestENH2225FinalOnlyGate.test_final_verify_routes_to_run_final_tests`
    (retarget).
  - `:1345–1347` — `test_final_verify_has_per_state_timeout` (retarget).
  - `:1500, :1501, :1536` — ENH-2575 comments (no change).

  Net: **10 live-state test references across 4 classes** (`:63, :186, :219, :1084,
  :1087, :1090, :1095, :1100, :1104, :1261, :1345`) must each be retargeted or
  covered by a new `TestENH2576BatchedVerify` assertion. After rewiring, re-run the
  grep and confirm zero uncovered live-state hits remain. This closes the residual
  "six-not-five member" gap flagged by both `/ll:confidence-check` passes.

### Tests — new-coverage enforcement + trace fixtures (added by `/ll:wire-issue`)

_Wiring pass:_
- `test_builtin_loops.py` `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm`
  (`:46-54`) — iterates every runnable builtin loop through `validate_fsm()` and
  fails on any `ERROR`. This is the mechanism that **auto-enforces MR-1/MR-7/MR-9**
  on the new `partition_verify`/`verify_batch` states with no new test needed —
  but it means an MR violation in the new states breaks this suite, not just
  general-task's own tests [Agent 3 finding].
- `test_fsm_interpolation.py`
  `test_general_task_run_final_tests_safe_with_empty_context` (`:784-788`) —
  unaffected (`run_final_tests` unchanged); listed to confirm no regression
  [Agent 1 finding].
- `scripts/tests/fixtures/tier0_traces/general-task-20260619T225602.json` and
  `general-task-20260608T194041.json` — frozen tier-0 traces (ENH-2518) that embed
  `"state": "final_verify"` as recorded historical data. **Verify** whether any
  test replays/validates these against *live* `general-task.yaml` state names (would
  break) or treats them as opaque history (would not) before touching them
  [Agent 2/Agent 1 finding].

### Configuration / Validation coupling (added by `/ll:wire-issue`)

_Wiring pass — `fsm/validation.py` MR-rule constraints the new states must satisfy
(enforced automatically via `test_all_validate_as_valid_fsm` above):_
- **MR-9 (ERROR)** — `partition_verify` is a new `shell` state; use single `$` for
  substitution/vars and `$${VAR}` only for literal brace escapes, else `$$` expands
  to the runner PID [Agent 2 finding].
- **MR-4 (WARN) + MR-8 (WARN)** — only fire if `verify_batch` adds an explicit
  `evaluate:` block of type `check_semantic`/`llm_structured`. If it stays a plain
  `action_type: prompt` with an `output_numeric` cursor gate on a *separate* shell
  state (the selected Option B shape), neither applies. If `verify_batch` itself
  gains an LLM `evaluate:` gate, it must (MR-4) route `on_no`/`on_partial` (not
  dead-end) and (MR-8) include an evidence-contract keyword or inherit
  `DEFAULT_LLM_PROMPT` [Agent 2 finding].
- `circuit.repeated_failure.exclude_paths` (`general-task.yaml:24-30`) lists only
  `plan.md` + `dod.md`. `progress_paths` is unset for this loop, so the new
  `batch-cursor.txt` needs no `exclude_paths` entry today — **design note only**,
  relevant if `progress_paths` is ever populated [Agent 2 finding].

### Composition / consumers — context only, no code change (added by `/ll:wire-issue`)

_Wiring pass — confirms the change is data-driven with no hardcoded `final_verify`
references in Python infra:_
- `fsm/executor.py`, `fsm/validation.py`, `fsm/schema.py`, `fsm/types.py` — **zero**
  hardcoded `final_verify`/`count_final`/`run_final_tests` references; all routing is
  YAML-data-driven, so no Python changes are required [Agent 1 finding].
- `scripts/little_loops/loops/proof-first-task.yaml` — sets
  `context.impl_loop: "general-task"` (composes it as a sub-loop) but references no
  internal state name; unaffected [Agent 1 finding].
- `skills/audit-loop-run/SKILL.md`, `agents/loop-specialist.md`,
  `scripts/little_loops/loops/README.md`, `skills/create-loop/loop-types.md` —
  reference `general-task` generically; only `loop-types.md` (above) needs an edit
  [Agent 1 finding].

## Proposed Solution

Two viable substrate patterns for the cursor. **Both** share the same shape:
`partition_verify` (shell) writes the batch plan + cursor under
`${context.run_dir}` → `verify_batch` (prompt, bounded timeout) re-verifies one
batch per visit and appends evidence **to a single `## Final Verification`
section** → loops back on "more batches" / exits to `run_final_tests` on
"cursor exhausted" → any batch timeout routes to the ENH-2575 chain but marks
only that batch's criteria unverified and continues.

### Option A — Directory batch-queue (goal-cluster pattern)
`partition_verify` splits `## Verification Criteria` into `ceil(N/10)` JSON files
under `${context.run_dir}/verify-queue/`; `verify_batch` pops the head file (by
`os.rename` into `verify-done/`), passes those criteria to the prompt, appends
result lines, and loops until `verify-queue/` is empty (`exit 1` → `on_no:
run_final_tests`). Durable, inspectable, resumable — the moved file *is* the
completion record. Higher YAML volume (inline Python for partition + pop).

### Option B — Flat-file counter cursor (queue_pop / retry_counter pattern)

> **Selected:** Option B — flat-file counter cursor is consistent with general-task's existing cursor idioms, shell-only (no new Python/directory machinery), and directly unit-testable with the loop's existing shell-state harness.

`partition_verify` writes the criteria list once and a `batch-cursor.txt`
integer (0); `verify_batch` reads the cursor, `awk`-slices criteria
`[cursor*K, (cursor+1)*K)`, verifies them, appends result lines, increments the
cursor, and routes via `output_numeric`: `cursor*K < N` → loop, else →
`run_final_tests`. Lighter-weight, matches the counter idioms already in this
loop (`step-attempts.txt`). Less durable (no per-batch artifact), but the
`## Final Verification` section itself records progress.

**Recommendation: Option B** — it reuses the existing counter-cursor idiom
already present in general-task (`step-attempts.txt`, `select_step`'s implicit
cursor), keeps the single-`## Final Verification`-section contract trivially
(one append target, cursor is separate), and avoids the goal-cluster directory
machinery which is overkill for an in-process flat criteria list. Option A is
preferable only if per-batch resumability across process restarts becomes a
requirement (it is not, given `final_verify` runs in the terminal arm).

### Timeout & partial-credit wiring (both options)
- `verify_batch.timeout`: bound per batch, e.g. **600s** (below `do_work`'s 900s
  ceiling; K=10 criteria is a fraction of the ~56-item monolith).
- `verify_batch.on_error`: route to a small "mark batch unverified + advance
  cursor" shell state that then loops back — a single batch timeout leaves that
  batch's criteria `[ ]` and continues rather than forfeiting. When the cursor
  exhausts with anything still unverified, `count_final`'s `on_no: continue_work`
  or the ENH-2575 `partial` terminal handles the shortfall (no new terminal
  needed).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and MUST be part of the
implementation, in addition to the YAML state work above:_

1. Rewire both entry edges — `count_done.on_yes` (`:423`) and `continue_work.on_yes`
   (`:610`) — from `final_verify` to `partition_verify` (already in Files to Modify).
2. Retarget the three break-on-removal tests (`test_expected_states_present`,
   `test_final_verify_has_per_state_timeout`, `TestENH2225FinalOnlyGate.
   test_final_verify_routes_to_run_final_tests`) to the new state names; add a new
   `TestENH2576BatchedVerify` class rather than gutting `TestChange8FinalVerifyGate`.
3. Update the `total == 0 → final_verify` routing claim to the new partition
   state in `skills/create-loop/loop-types.md:1057` and at all four
   `LOOPS_REFERENCE.md` sites (`:117`, `:119`, `:127`, `:129`). **Do not** hunt
   for `docs/reference/loops.md:1057` — it is a phantom ref (that file is 900
   lines and has no `final_verify` mentions); the routing claim was never there.
4. Verify the two tier-0 trace fixtures aren't replayed against live state names;
   if they are, decide whether to re-record or exempt them (ENH-2518 lock).
5. Confirm `partition_verify` (shell) passes MR-9 and the new states pass
   `ll-loop validate` / `test_all_validate_as_valid_fsm` before raising step budget.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-10.

**Selected**: Option B — Flat-file counter cursor (queue_pop / retry_counter pattern)

**Reasoning**: `general-task.yaml` already uses flat-file cursors exclusively
(`step-attempts.txt`, `checkpoint.json`, `select_step`'s implicit `- [ ]` grep
cursor) and contains zero `os.rename`/`glob.glob`/directory-queue machinery;
Option B extends that established style while Option A would introduce a
one-off structural idiom with only a single codebase precedent (goal-cluster)
and no shared fragment behind it. Option B is shell-only, and the loop's
existing shell-state test harness (`_load_state_script`/`_bash`,
`TestCheckpointWriteShellAction`) makes the cursor states directly unit-testable
— whereas goal-cluster's directory queue is only indirectly covered.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Directory batch-queue | 1/3 | 1/3 | 1/3 | 2/3 | 5/12 |
| Option B — Flat-file counter cursor | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: exact `init_cluster_queue`/`execute_cluster` precedent exists at
  `goal-cluster.yaml:287-353`, but it is the **only** directory-queue call site
  codebase-wide, has no reusable fragment, and is stylistically inconsistent
  with every cursor idiom `general-task.yaml` already uses. Reuse score 1.
- Option B: counter+gate skeleton is precedented (`retry_counter` fragment
  `lib/common.yaml:23-45`; proven inline in `loop-composer-adaptive.yaml:432-456`)
  and fits general-task's flat-file style; its distinguishing `awk`-slice
  mechanism has no direct precedent, so that logic is authored fresh — but on a
  well-worn `output_numeric` gate (27 loop files) and a ready test harness.
  Reuse score 1. Both scored reuse 1; the dimensional split (simplicity,
  testability, in-loop consistency) is decisive.

## Impact

_Inferred by `/ll:format-issue --auto` from frontmatter scores and issue content._

- **Priority**: P2 — reliability fix for deterministic large-task `final_verify`
  timeouts. ENH-2575 already prevents outright run forfeiture, so this is not
  P0/P1, but unverified DoDs on every large task degrade the loop's terminal gate.
- **Effort**: Medium — one YAML state decompose plus a cursor shell state that
  reuses existing counter idioms (`step-attempts.txt`, `retry_counter`), retarget
  ~3 break-on-removal tests + add a `TestENH2576BatchedVerify` class, and three
  doc edits (`score_change_surface: 18`, `score_complexity: 14`).
- **Risk**: Medium — touches the terminal verification arm and the `count_final`
  single-section contract; mitigated by the existing shell-state test harness and
  `test_all_validate_as_valid_fsm` auto-enforcing MR-1/MR-7/MR-9 on the new states.
- **Breaking Change**: No — internal loop refactor; no public API, CLI, or config
  surface changes.

## Notes

From audit recommendation 2 (`general-task-audit-2026-07-09T232714.md`,
run archive `.loops/.history/2026-07-09T232714-general-task/` in the cards
consumer project).


## Status

**Open** | Created: 2026-07-10 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-10_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Outcome Risk Factors
- The actual dependent count on `final_verify` is larger than the issue's own
  "Tests — will break on `final_verify` removal" enumeration: two additional
  tests assert the exact entry edges (`test_count_done_routes_yes_to_done`,
  `test_general_task_loop.py:186`, and
  `test_continue_work_escape_hatch_routes_to_final_verify`,
  `test_general_task_loop.py:219-227`) that the Wiring Phase already flags for
  rewiring, but neither is listed alongside the three tests the issue names as
  break-on-removal. Rerun `grep -n '"final_verify"' scripts/tests/test_general_task_loop.py`
  after rewiring `count_done.on_yes` / `continue_work.on_yes` and retarget any
  hit not already covered by `TestENH2576BatchedVerify` — this widens the
  Pattern-A dependent count past the "manageable surface" bucket.

================================================================================
CONFIDENCE CHECK: ENH-2576
================================================================================

## READINESS SCORES

| Criterion                    | Score | Details                                                                 |
|-------------------------------|-------|--------------------------------------------------------------------------|
| No duplicate implementations  | 20/20 | `final_verify` is still the single monolithic prompt state (`general-task.yaml:427-458`); no decomposition exists yet. |
| Architecture compliance       | 20/20 | Option B reuses the loop's existing flat-file cursor idioms (`step-attempts.txt`, `retry_counter`); decided via `/ll:decide-issue` with a scored comparison. |
| Rationale well-understood     | 20/20 | Current/Expected Behavior sections cite exact line numbers and a source audit run; all cited line refs verified against live YAML. |
| Issue well-specified          | 15/20 | AC, Integration Map, Scope Boundaries, and Wiring Phase are thorough, but the break-on-removal test list misses 2 of 5 actual `final_verify`-referencing tests (see Outcome Risk Factors). |
| Dependencies satisfied        | 20/20 | `relates_to: ENH-2575` is done (`a6db77c4`, confirmed in git log) — the partial-credit chain this issue routes into already exists. |

## OUTCOME CONFIDENCE SCORES

| Criterion       | Score | Details                                                                 |
|------------------|-------|--------------------------------------------------------------------------|
| Complexity       | 14/25 | Breadth 9/12 (general-task.yaml + test file + 3 doc files); Depth 5/13 (cursor + loop-back control flow within one loop, not a cross-loop contract change). |
| Test coverage    | 25/25 | Existing shell-state harness (`_load_state_script`/`_bash`) and named fixture DoDs directly cover the new states; AC mandates new coverage. |
| Ambiguity        | 20/25 | Locked to Option B via `/ll:decide-issue` with full scoring rationale; residual: Expected Behavior still says "(design open)," stale after the decision. |
| Change surface   | 10/25 | Pattern A (blast radius). ~2 YAML entry edges + 5 actual referencing tests (3 enumerated + 2 missed) + 2 doc files ≈ 9 dependents — "broad surface" bucket, not "manageable." |

## SUMMARY

READINESS SCORE:    95/100 → PROCEED
OUTCOME CONFIDENCE: 69/100 → MODERATE

## RECOMMENDATION: PROCEED

### Outcome Risk Factors
- See Outcome Risk Factors above — re-grep for `"final_verify"` in the test file after rewiring the two entry edges; two tests outside the issue's own enumeration will otherwise fail unexpectedly during implementation rather than being anticipated.

================================================================================

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-10_

**Readiness Score**: 97/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Outcome Risk Factors
- Re-verification confirms the break-on-removal enumeration (added by the prior
  `/ll:refine-issue --full-rewrite` pass) is now substantially complete, but a
  fresh `grep -n final_verify scripts/tests/test_general_task_loop.py` found one
  test still missing from the issue's own "Complete inventory":
  `test_count_done_routes_yes_to_final_verify`
  (`test_general_task_loop.py:1084-1085`, inside `TestChange8FinalVerifyGate`,
  which the issue describes as having five member tests but actually has six).
  It duplicates the already-flagged `test_count_done_routes_yes_to_done`
  assertion (`count_done.on_yes == "final_verify"`), so it will fail loudly
  alongside it once `count_done.on_yes` is rewired — low severity, but
  retarget it together with the other five `TestChange8FinalVerifyGate`
  members rather than assuming the class's coverage is fully described by the
  five named in the issue.
- Change surface remains Pattern A (blast radius): ~10-14 actual dependents (2
  entry edges + 10 test methods across 4 test classes + 2 doc files + 2 tier-0
  trace fixtures to verify) — broad enumeration across many sites, consistent
  with the existing Change Surface 10/25 score.

================================================================================

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-10_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- A stale caveat at line 279 ("Decide the state-key naming first") contradicts
  the Proposed Solution section, which already commits to naming the new
  per-batch state `verify_batch` throughout (Option A/B write-ups, Timeout &
  partial-credit wiring, Wiring Phase step 2). The naming choice is not
  actually open — but the leftover contradictory sentence risks confusing
  whoever retargets `TestChange8FinalVerifyGate`'s five state-key-reading
  members into thinking renaming is still undecided. Clean up or
  cross-reference the stale line before implementation starts.
- Change surface remains Pattern A blast radius: ~10-14 actual dependents (2
  YAML entry edges + 10 test methods across 4 test classes + 2 doc files + 2
  tier-0 trace fixtures to verify) — broad enumeration across many sites,
  consistent with the existing Change Surface 10/25 score. Each site's edit is
  mechanically uniform (retarget one string), but the mixed code+doc+fixture
  spread keeps this a deep per-site Pattern A surface rather than a Pattern B
  mechanical fanout.

================================================================================

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-10_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Re-verification closes both prior risk items: the stale "decide naming first"
  caveat is gone (line 279 no longer exists; the "Naming is decided, not open"
  language at :290 stands uncontradicted), and the two tier-0 trace fixtures
  (`general-task-20260619T225602.json`, `general-task-20260608T194041.json`)
  were confirmed safe — `test_tier0_traces.py` only validates a locked
  `states: {...}` cost-aggregate schema (input/output/cache tokens, cost_usd)
  per state name; it never diffs state names against live `general-task.yaml`,
  so renaming/removing `final_verify` cannot break these fixtures.
- Change surface remains the dominant outcome-risk axis (Change Surface
  10/25, lowest of the four criteria): a live re-grep confirms the issue's own
  "Complete inventory" is now exact — 10 test-file line refs
  (`:63, :186, :219, :1084, :1087, :1090, :1095, :1100, :1104, :1261, :1345`)
  across 4 test classes, 2 YAML entry edges (`count_done.on_yes`,
  `continue_work.on_yes`), and 5 doc-narrative sites across 2 files
  (`LOOPS_REFERENCE.md:117,119,127,129`, `loop-types.md:1057`) — a broad
  enumeration across ~17 sites. Each is a mechanically uniform string retarget,
  but the volume (not per-site depth) is what keeps outcome confidence at
  MODERATE rather than HIGH.

================================================================================

## Session Log
- `/ll:confidence-check` - 2026-07-10T21:15:00 - `01a6a3ca-9f56-4c7e-b53b-96b359574ce0.jsonl`
- `/ll:refine-issue` - 2026-07-10T20:00:13 - `25004c83-e48a-4cb5-b023-95550ad3c1cb.jsonl`
- `/ll:refine-issue` - 2026-07-10T19:59:45 - `25004c83-e48a-4cb5-b023-95550ad3c1cb.jsonl`
- `/ll:confidence-check` - 2026-07-10T21:00:00 - `0595af4e-e070-42af-8d72-740015a26455.jsonl`
- `/ll:refine-issue` - 2026-07-10T19:50:40 - `fe23b1db-58c2-4fe9-84e1-b886656e9817.jsonl`
- `/ll:confidence-check` - 2026-07-10T20:45:00 - `d930bc36-57eb-43d3-8eb7-357d1128a130.jsonl`
- `/ll:refine-issue` - 2026-07-10T19:42:29 - `d4c716f0-7ac0-451e-8839-6b0390e006e1.jsonl`
- `/ll:confidence-check` - 2026-07-10T20:15:00 - `82537ca5-40a1-48f1-ae65-faee1c5b4e2a.jsonl`
- `/ll:format-issue` - 2026-07-10T19:32:20 - `f9af5cde-d5b1-41eb-b984-292bb3623380.jsonl`
- `/ll:refine-issue` - 2026-07-10T17:56:31 - `d875bf4b-aee6-4f56-af17-ad70f0850e15.jsonl`
- `/ll:confidence-check` - 2026-07-10T17:37:42Z - `78029021-5fb5-460d-a2f5-fa62d4fea347.jsonl`
- `/ll:wire-issue` - 2026-07-10T17:33:55 - `5e560865-ead3-44d5-80c4-b2ca79c8525a.jsonl`
- `/ll:decide-issue` - 2026-07-10T17:16:37 - `430b0422-be2b-4e3c-bc94-9d992937894c.jsonl`
- `/ll:refine-issue` - 2026-07-10T17:05:51 - `a57c70cf-2763-46d3-80d2-4dda93924936.jsonl`
