---
discovered_date: 2026-04-16
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1127: Interleave Refinement and Implementation in autodev Loop

## Summary

Change the `autodev` loop so that when `/ll:issue-size-review` decomposes an issue into sub-issues, each sub-issue is implemented as soon as it passes refinement, rather than waiting for the entire decomposition tree to be refined first. Today the loop fully drains `recursive-refine`'s tree before any implementation runs, which delays real code progress behind arbitrary amounts of refinement work.

## Motivation

`scripts/little_loops/loops/autodev.yaml` currently sequences work as **refine-all → implement-all**:

1. `refine_issue` (autodev.yaml:64-73) delegates the entire input issue to the `recursive-refine` sub-loop via `loop: recursive-refine`.
2. `recursive-refine` internally drains its own depth-first queue — on decomposition, `enqueue_children` / `enqueue_or_skip` (`recursive-refine.yaml:185-206, 286-333`) prepend new child IDs to `.loops/tmp/recursive-refine-queue.txt` and keep refining until the queue is empty.
3. Only after the whole tree is refined does autodev's `seed_impl_queue` (autodev.yaml:75-93) copy the full passed list from `.loops/tmp/recursive-refine-passed.txt` to `.loops/tmp/autodev-impl-queue.txt`.
4. `implement_next` / `implement_issue` (autodev.yaml:95-119) then drain the impl queue via `ll-auto --only`.

The consequence: if `/ll:issue-size-review` breaks down a top-level issue into N children (and any of those into grandchildren), the user waits for the entire tree to reach readiness before the first line of implementation code is written. This is a long feedback delay, and early implementation attempts often surface information that would reshape sibling refinement — information we're currently discarding by ordering refinement before any implementation.

Interleaving (refine leaf → implement leaf → refine next leaf → …) lets real implementation progress start earlier, surfaces integration issues while refinement context is still fresh, and produces partial forward progress even if the overall run is interrupted by timeout, rate limit, or user cancellation.

## Proposed Solution

Replace autodev's current three-phase structure (`refine_issue` → `seed_impl_queue` → `implement_next` loop) with a single interleaved loop. The cleanest shape: inline the refinement orchestration into autodev instead of delegating the whole tree to `recursive-refine`, so autodev owns the queue and can implement each leaf the moment it passes.

Sketch of the new state machine (replacing autodev.yaml:64-119):

1. **Single unified queue** — `.loops/tmp/autodev-queue.txt` already seeded from `context.input` in `init`. Use this same file as the working queue throughout; drop the separate `autodev-impl-queue.txt`.
2. **`dequeue_next`** — unchanged: pops head, captures as `input`, routes to `refine_current`.
3. **`refine_current`** — delegate a *single* issue to `refine-to-ready-issue` (not `recursive-refine`). This is the leaf-level sub-loop that recursive-refine already uses internally; using it directly gives autodev per-issue control. Mirror recursive-refine's `capture_baseline` → `run_refine` → `check_passed` → `detect_children` → `enqueue_or_skip` pattern (recursive-refine.yaml:72-333).
4. **On pass** (thresholds met): route to `implement_current` — run `ll-auto --only ${captured.input.output}` — then back to `dequeue_next`.
5. **On decomposition detected** (new child IDs tagged `Decomposed from <parent>`): prepend children to `.loops/tmp/autodev-queue.txt` depth-first, mark parent skipped, move parent to `.issues/completed/`, return to `dequeue_next`. Reuse the exact shell logic from `recursive-refine.yaml:185-206`.
6. **On no-decomposition skip** (sub-loop failed and no children exist): mark parent skipped, return to `dequeue_next`. Mirror `enqueue_or_skip`'s else-branch (recursive-refine.yaml:327-330).

### Alternative considered: teach `recursive-refine` to emit per-leaf events

Rejected — would require FSM streaming hooks that don't exist today, and would push autodev-specific behavior into a general-purpose refinement loop. Inlining keeps the change local to autodev.

### Migration notes

- Delete `seed_impl_queue` and `implement_next` states; their queue-management logic collapses into the single unified queue.
- Rename `implement_issue` → `implement_current`; its rate-limit handling stays identical (`fragment: with_rate_limit_handling`, `on_rate_limit_exhausted: done`, `next: dequeue_next` instead of `implement_next`).
- `recursive-refine` itself is untouched — it remains usable standalone via `ll-loop run recursive-refine` and continues to be the right tool when a user wants refine-only (no implementation).
- **`refine-to-ready-issue` side-effect to handle**: on entry, `refine-to-ready-issue.yaml:21-26` writes `0` to `.loops/tmp/recursive-refine-broke-down`. If autodev invokes `refine-to-ready-issue` directly, autodev must read this file after the sub-loop returns (as `recursive-refine:check_broke_down` does at `recursive-refine.yaml:221-234`) to decide whether to still run `/ll:issue-size-review` or skip it. To avoid cross-loop collision, autodev should *copy* the flag to `.loops/tmp/autodev-broke-down` after the sub-loop returns, or simply read `recursive-refine-broke-down` and treat it as the handshake file (accepting the shared name).

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — replace states `refine_issue` (lines 64-73), `seed_impl_queue` (lines 75-93), `implement_next` (lines 95-112), `implement_issue` (lines 114-119) with the interleaved state machine described above. Keep `init`, `dequeue_next`, and `done` structurally the same (`dequeue_next` will route to the new `refine_current` instead of `refine_issue`).

### Files to Study (but likely not modify)

- `scripts/little_loops/loops/recursive-refine.yaml` — source of the queue/decomposition shell logic to copy into autodev. Do not modify; autodev's new states should be near-byte-compatible mirrors of `capture_baseline` (lines 72-88), `run_refine` (lines 90-101), `check_passed` (lines 103-144), `detect_children` (lines 146-183), `enqueue_children` (lines 185-206), `size_review_snap` (lines 208-219), `check_broke_down` (lines 221-234), `recheck_scores` (lines 236-276), `run_size_review` (lines 278-284), `enqueue_or_skip` (lines 286-333). Substitute `autodev-*` file paths for `recursive-refine-*` where appropriate (see Temp File Changes above for which files are namespaced vs. shared).
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the per-issue sub-loop autodev will delegate to via `loop: refine-to-ready-issue` + `context_passthrough: true`. Already used inside `recursive-refine:run_refine` (lines 90-101) and `issue-refinement:run_refine_to_ready` (`issue-refinement.yaml:28-32`), so invocation pattern is established.
- `scripts/little_loops/loops/lib/common.yaml` — `with_rate_limit_handling` fragment defined at lines 49-55 (3 retries, 30s backoff) is already imported by autodev.yaml:21-22; reuse on both `refine_current` (sub-loop invocation — pattern from `recursive-refine.yaml:90-101`) and `implement_current` (shell `ll-auto` invocation — pattern from current `autodev.yaml:114-119`).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — an older sibling loop with the same refine-all-then-implement-all anti-pattern this issue fixes. Not modified by this issue, but worth inspecting for confirmation that the pattern being replaced is localized to autodev alone. Its `get_passed_issues` state (lines 41-73) shows the same reliance on `recursive-refine-passed.txt`.

### Tests

- `scripts/tests/test_builtin_loops.py` — validates built-in loop YAMLs against the FSM schema. Any schema-level assertion about autodev (state count, required routing keys) lives here. The new state machine must pass this suite.
- `scripts/tests/test_fsm_executor.py`, `scripts/tests/test_fsm_validation.py`, `scripts/tests/test_fsm_fragments.py` — generic FSM machinery tests; ensure `fragment: with_rate_limit_handling` still resolves on the renamed states.
- No existing integration test exercises autodev end-to-end. If adding one, model after `scripts/tests/test_outer_loop_eval.py` (outer-loop sub-loop delegation test).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:46-92` — `test_expected_loops_exist` is **currently failing** because `"autodev"` is absent from its hardcoded `expected` set while `autodev.yaml` exists on disk. Adding `"autodev"` to the expected set is a required fix that must be included in this implementation (pre-existing broken test, not caused by ENH-1127 but must be resolved alongside it). [Agent 1 + 3 finding]
- `scripts/tests/test_builtin_loops.py` — **new `TestAutodevLoop` class needed** (no autodev-specific structural tests exist today). Model after `TestAutoRefineAndImplementLoop` (line 849). Assert: required new states (`init`, `dequeue_next`, `refine_current`, `check_passed`, `detect_children`, `implement_current`, `done`); `refine_current` uses `loop: refine-to-ready-issue` + `context_passthrough: true`; `implement_current` has `fragment: with_rate_limit_handling` + `on_rate_limit_exhausted: done`; no state references `recursive-refine-passed.txt`; `init.action` references `autodev-queue.txt` but NOT `autodev-impl-queue.txt`. [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py:869-893` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` lists 10 loops to validate fragment resolution; `autodev.yaml` is absent. Add `"autodev.yaml"` to the migration targets list so fragment resolution is explicitly validated for the new states. [Agent 3 finding]

### Documentation

- `scripts/little_loops/loops/README.md` — built-in loop catalog describes autodev's behavior; update the autodev entry to reflect interleaved execution.
- `docs/guides/LOOPS_GUIDE.md` — main loops guide; any mention of autodev's refine-all-then-implement-all sequencing needs correcting.
- `CHANGELOG.md` — add an entry under the next unreleased section noting the behavior change (user-visible: earlier implementation progress, different log sequence).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:290` — summary table row for `autodev` reads "recursively refines each via `recursive-refine`, then implements all passed issues via `ll-auto --only`"; update to describe interleaved execution [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:429-430` — Technique paragraph describes the two-phase `recursive-refine` → `ll-auto` flow; rewrite to match interleaved pattern [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:446-449` — FSM flow diagram explicitly names the deleted states `refine_issue`, `seed_impl_queue`, `implement_next`, `implement_issue`; replace with new state machine diagram [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:453` — Notes paragraph names `implement_issue` and `on_rate_limit_exhausted: done` behavior; update to `implement_current` [Agent 2 finding]

### Temp File Changes

- Keep: `.loops/tmp/autodev-queue.txt` (now serves as the unified refine+implement queue).
- **Verified**: `.loops/tmp/recursive-refine-passed.txt` is written **exclusively** by `recursive-refine.yaml` — specifically by `check_passed` (lines 137-138) and `recheck_scores` (lines 269-270). `refine-to-ready-issue` never writes this file. Therefore autodev cannot rely on it and must write its own `.loops/tmp/autodev-passed.txt` from its new `check_passed` state for the final summary.
- **Verified**: `refine-to-ready-issue` emits no passed/failed signal via exit code, output, or `context_passthrough` — both terminal states (`done` line 238, `failed` line 241) have no action and no `context_passthrough`. Autodev must re-query `ll-issues show --json` after the sub-loop returns to check whether thresholds were met (use the same Python3 inline block as `recursive-refine.yaml:103-141`).
- Delete: `.loops/tmp/autodev-impl-queue.txt` — no longer needed.
- New: `.loops/tmp/autodev-pre-ids.txt`, `.loops/tmp/autodev-post-ids.txt`, `.loops/tmp/autodev-diff-ids.txt`, `.loops/tmp/autodev-new-children.txt`, `.loops/tmp/autodev-passed.txt`, `.loops/tmp/autodev-skipped.txt` — mirrors of the recursive-refine bookkeeping files, namespaced to autodev so the two loops never collide if both run concurrently.
- Shared: `.loops/tmp/recursive-refine-broke-down` — written by `refine-to-ready-issue:write_broke_down` (line 233) and cleared by `refine-to-ready-issue:resolve_issue` (line 25). Autodev must read this as its cross-loop handshake (same role as `recursive-refine:check_broke_down`, lines 221-234). Renaming would require modifying `refine-to-ready-issue.yaml`, which is out of scope.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Fix `scripts/tests/test_builtin_loops.py:48-90` — add `"autodev"` to the `expected` set in `test_expected_loops_exist` (currently failing pre-existing omission)
2. Write `TestAutodevLoop` class in `scripts/tests/test_builtin_loops.py` — cover new interleaved state machine; follow `TestAutoRefineAndImplementLoop` pattern (line 849)
3. Update `scripts/tests/test_fsm_fragments.py:869-893` — add `"autodev.yaml"` to `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` migration targets list
4. Update `docs/guides/LOOPS_GUIDE.md:290,429-430,446-449,453` — replace all references to deleted states and old two-phase flow with interleaved description and updated FSM diagram

## Acceptance Criteria

- Running `ll-loop run autodev "ID1"` where `/ll:issue-size-review` decomposes `ID1` into children `C1,C2,C3` produces this sequence in the loop log (approximate): refine C1 → implement C1 → refine C2 → implement C2 → refine C3 → implement C3. No "refine all → implement all" gap.
- Running `ll-loop run autodev "ID1"` where `ID1` passes refinement without decomposition produces: refine ID1 → implement ID1 → loop ends. Behavior indistinguishable from today for the non-decomposed path.
- Running `ll-loop run autodev "ID1,ID2"` with ID1 decomposed into two children and ID2 not decomposed produces: refine C1 → implement C1 → refine C2 → implement C2 → refine ID2 → implement ID2.
- Rate-limit handling on the implementation step continues to route to `done` (preserving today's `on_rate_limit_exhausted: done` on `implement_issue`, autodev.yaml:118).
- `recursive-refine` used standalone via `ll-loop run recursive-refine "ID1"` is unchanged.

## Risks and Open Questions

- **Partial tree under failure**: if `implement_current` fails on a child, siblings still get refined+implemented (same as today's behavior for `ll-auto --only`'s per-issue failure). Confirm this is the desired semantic before committing.
- **`refine-to-ready-issue` output contract** — *Resolved by research*: the sub-loop emits **no** direct pass/fail signal. Its `done` (line 238) and `failed` (line 241) states are action-less and carry no `context_passthrough`. Parent loops distinguish sub-loop success vs. failure only via terminal-state routing (`on_success`/`on_failure`), and must re-query `ll-issues show --json` to read actual confidence/outcome scores. **Autodev's new `check_passed` state must therefore use the same Python3 inline threshold check as `recursive-refine.yaml:103-141`** (reads `commands.confidence_gate.readiness_threshold` / `outcome_threshold` from `.ll/ll-config.json`, falls back to `${context.*}`, appends to passed file on success).
- **Parent issue moved to `completed/` mid-loop**: matches recursive-refine behavior (`enqueue_children` at recursive-refine.yaml:197-201, `enqueue_or_skip` at recursive-refine.yaml:319-323). Keep identical.
- **Cross-loop collision on `recursive-refine-broke-down`**: the broke-down flag file lives under `recursive-refine-*` but is actually authored by `refine-to-ready-issue` (write: `refine-to-ready-issue.yaml:232-235`; clear: `refine-to-ready-issue.yaml:25`). If autodev runs concurrently with a standalone `recursive-refine`, both will read/overwrite this file. Not a new risk (same risk exists today between `recursive-refine` and any other caller of `refine-to-ready-issue`), but worth documenting — users running concurrent loops should treat `.loops/tmp/` as single-reader.
- **`seed_impl_queue`'s temporal-coupling comment becomes obsolete**: `autodev.yaml:77-78` currently notes the fragility of relying on `recursive-refine-passed.txt` not being overwritten before `seed_impl_queue` runs. Removing `seed_impl_queue` also removes this subtle ordering dependency — net simplification.

## Session Log
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55b4de4f-cca6-43c5-91b9-e3975086b634.jsonl`
- `/ll:wire-issue` - 2026-04-16T20:42:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96d02ce5-8f98-44e4-8c86-7a470c9fbe61.jsonl`
- `/ll:refine-issue` - 2026-04-16T20:35:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2b798fe-90a5-495d-a364-a94a8c145fba.jsonl`

- `/ll:capture-issue` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba64c432-8f9f-4867-9fe9-0e01b12d2cf4.jsonl`

---

**Open** | Created: 2026-04-16 | Priority: P3
