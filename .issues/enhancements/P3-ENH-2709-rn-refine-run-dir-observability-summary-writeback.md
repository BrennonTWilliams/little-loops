---
id: ENH-2709
status: done
captured_at: '2026-07-20T19:30:00Z'
completed_at: '2026-07-20T22:07:24Z'
discovered_date: 2026-07-20
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 20
---

# ENH-2709: rn-refine run-dir observability (summary.json + writeback.json)

## Summary

`rn-refine` (`scripts/little_loops/loops/rn-refine.yaml`) never writes a `summary.json` or a write-back marker to its run dir, unlike sibling loops `rn-implement` and `auto-refine-and-implement` which already emit `summary.json`. This forces anyone auditing a run (success, partial, or timeout) to reconstruct status by parsing `events.jsonl` and diffing files by hand.

## Current Behavior

In the `rn-refine-20260720T002123` audit (`rn-refine-audit-2026-07-20T134636.md`), the investigator could not tell from the run dir alone whether the 6-hour run had succeeded or timed out:

- No `summary.json` anywhere in the run dir — had to infer node counts from `leaves.txt`/`capped.txt`/`failed_nodes.txt`/`queue.txt` and cross-reference `dequeue_count.txt`
- No write-back marker — had to `diff` the source `phase-2-only-plan.md` against the run's `plan.md` and check mtimes to confirm the source was untouched
- `finalize`/`finalize_aborted` and the timeout path all leave the run dir in this same ambiguous state

The audit's own scorecard makes the cost explicit: it could not distinguish a 6-hour timeout from a 6-hour success without parsing `events.jsonl` directly.

## Expected Behavior

`rn-refine` should write, at minimum:

1. **`summary.json`** — written by `finalize`, `finalize_aborted`, and any timeout/deadline-drain exit path. Should include: `nodes_processed`, `leaves`, `capped`, `failed`, `pending_queue`, `wip_nodes`, `source_overwritten`, `terminated_by` (`success`/`timeout`/`aborted`).
2. **`writeback.json`** — written by `finalize` immediately after the source plan file is overwritten (or its absence implied by `summary.json.source_overwritten: false` on non-finalize exits), recording `{written, timestamp, source_path, backup_path}`.

This gives parity with `rn-implement`/`auto-refine-and-implement` and lets `/ll:audit-loop-run` (and any operator) determine run status from the run dir alone, without parsing `events.jsonl`.

## Motivation

Parity with existing harness convention (`rn-implement`, `auto-refine-and-implement` already emit `summary.json`) and directly reduces audit cost — the audit for this exact run had to hand-parse `events.jsonl` and `diff` files to answer "did this succeed."

## Proposed Solution

Fold the audit's proposals 1 and 6 together (needs `/ll:refine-issue` for concrete diffs against the current FSM structure):

- Add a `summary.json` write at the top of `finalize` and `finalize_aborted`, and at the deadline-guard exit in `dequeue_next` (and any other exit path found during investigation) — computed from the same artifacts the audit hand-parsed (`leaves.txt`, `capped.txt`, `failed_nodes.txt`, `queue.txt`, `dequeue_count.txt`).
- Add a `writeback.json` write in `finalize` right after the source file copy, recording whether/when the write-back happened.
- Verify against a real (non-simulated) timeout run, since `ll-loop simulate` returns synthetic strings that won't exercise the artifact-reading logic realistically.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exit-path inventory (concrete, from current `rn-refine.yaml`):**

- `finalize` — success write-back path. Reads `SOURCE` from `$RUN_DIR/.source-path`, has three early-exit guards (empty `SOURCE`/missing `plan.md`; `DRY_RUN=true`; `CONFIRM=true` — note the confirm guard currently *blocks* rather than permits the overwrite), then `cp "$SOURCE" "$BACKUP"` (`source-backup-<TS>.md`), echoes `BACKUP_PATH=$BACKUP` to stdout only (never persisted), then `cp "$RUN_DIR/plan.md" "$SOURCE"`. Routes `next: report`, `on_error: report`. This is exactly where `writeback.json` `{written, timestamp, source_path, backup_path}` hooks in — including `written: false` records on each early-exit guard so all four finalize outcomes are distinguishable.
- `finalize_aborted` (`terminal: true`) — already builds the right JSON payload via `python3 -c` (`success: false`, `original_unchanged: true`, `working_copy`, `backup_path: null`) but only **prints it to stdout**; changing `print(...)` to also write `$RUN_DIR/summary.json` is nearly the whole fix for this state.
- `dequeue_next` deadline-drain branch (ENH-2707) — on `ELAPSED_MS >= BUDGET_MS`: `cp "$QUEUE" "$RUN_DIR/undrained.txt"; : > "$QUEUE"; echo "DEADLINE_DRAIN"`. Not itself terminal — the run continues to `build_synth` → … → `finalize`/`finalize_aborted`, so `terminated_by: timeout` can be derived at summary-write time from `[ -s "$RUN_DIR/undrained.txt" ]` rather than requiring a separate write here.
- `assemble` appends `PARTIAL_DRAIN:` / `RECOVERY_NEEDED:` lines to `plan-rubric.md`; `synth_failure_record` appends `RECOVERY_NEEDED:` too — prose-only signals today.
- `report` is `action_type: prompt` (writes nothing); `done`/`failed` are bare terminals; `diagnose` is the shared `loop_failure_diagnose` fragment.

**Data sources for `summary.json` fields** (all under `$RUN_DIR`, seeded by `init`):
`dequeue_count.txt` → `nodes_processed`; `leaves.txt` (appended by `record_leaf`) → `leaves`; `capped.txt` → `capped` — **caution: `record_capped` only echoes `[CAPPED]` to stdout and never appends to `capped.txt`, so it is always empty as implemented** (worth a one-line fix or an honest `capped: 0` caveat); `failed_nodes.txt` (`record_failure` + `record_node_crash`) → `failed`; `queue.txt` + `undrained.txt` → `pending_queue`; `node_outcome_<id>.txt` markers vs `visited.txt` → `wip_nodes`; `undrained.txt` non-empty → `terminated_by: timeout`.

**JSON construction pattern to follow:** for this flat, all-scalar summary, the `auto-refine-and-implement.yaml` `finalize` pattern fits best — `count() { awk 'NF{c++} END{print c+0}' "$RUN_DIR/$1" 2>/dev/null || echo 0; }` plus a single `printf '{...}\n' ... > "$RUN_DIR/summary.json"` (bare ints unquoted, strings `"%s"`). `rn-implement.yaml`'s `report` state shows the Python-heredoc `json.dumps` alternative, only needed if nested per-node lists are added. Escaping: FSM tokens single-`$` (`${captured.run_dir.output}`), bash defaults double (`$${VAR:-0}`) per MR-7; MR-3 is satisfied since everything lives under the run dir; MR-5 does not trigger for single terminal writes.

## Scope Boundaries

In scope: `finalize`, `finalize_aborted`, and deadline-guard exit paths in `rn-refine.yaml` writing `summary.json`/`writeback.json`. Out of scope: fixing the underlying sub-loop outcome loss (see companion issue) or the deadline-drain queue-truncation issue.

## Impact

- **Priority**: P3 — observability improvement, not a correctness bug; doesn't lose work, just makes diagnosis slower.
- **Effort**: Small-medium — adding JSON writes to a handful of existing terminal/exit states; no routing changes.
- **Risk**: Low — additive artifact writes, no behavior change to the FSM's decision logic.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml` — add `summary.json` write to `finalize` (before/after write-back) and `finalize_aborted` (persist the JSON it already prints); add `writeback.json` write in `finalize` immediately after `cp "$RUN_DIR/plan.md" "$SOURCE"` (and `written:false` records on the DRY_RUN/CONFIRM/missing-source guards)
- `scripts/tests/test_rn_refine.py` — add artifact tests using the existing `InterpolationContext` + `interpolate()` + `_bash` scaffold (`TestDequeuePlumbing.test_deadline_drain_parks_queue_and_emits_sentinel`, lines ~440–460, is the model)

### Dependent Files (Consumers)
- `skills/audit-loop-run/SKILL.md` — Step 6a (~lines 279–294) already reads `summary.json` from run dirs; primary consumer
- `scripts/tests/test_audit_loop_run_skill.py` — tests for that consumer
- `scripts/little_loops/loops/oracles/plan-node-refine.yaml`, `oracles/integrate-node.yaml` — write the per-node run-dir artifacts summarized (no changes needed)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — `archive_run()` (~lines 506–556) copies `summary.json` from the run dir into `.loops/.history/<run_id>-<loop_name>/`; once rn-refine writes one it gets archived automatically — no code change needed, but archived-copy presence becomes part of the observable contract [Agent 1 finding]
- Confirmed: **no Python code in `scripts/little_loops/fsm/` or `scripts/little_loops/cli/` parses any loop's `summary.json`** — consumption is exclusively via the `audit-loop-run` skill markdown; and rn-refine's schema need not match `rn-implement`/`auto-refine-and-implement` field names (different domains, no shared contract) [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` `finalize` state — `count()` awk helper + single `printf` → `summary.json`, plus `subloop_outcome_<loop>.txt` sidecar (ENH-2005)
- `scripts/little_loops/loops/rn-implement.yaml` `report` state (~lines 1560–1658) — Python-heredoc `json.dumps` variant for nested summaries
- `scripts/little_loops/fsm/persistence.py:19` — documents the `.loops/.history/<run_id>-<loop_name>/summary.json` convention

### Tests
- `scripts/tests/test_rn_refine.py` — natural home for new render/exec/assert-on-disk tests
- `scripts/tests/test_builtin_loops.py` — structural string-assertion style (`test_finalize_writes_summary_json`, ~lines 2982–2987) and full-key-accounting style (~lines 2631–2646) to mirror

_Wiring pass added by `/ll:wire-issue`:_
- **No existing tests break**: `TestFinalizeSafety` tests (`test_rn_refine.py` ~1032–1180) use `glob("source-backup-*.md")` and routing assertions, not exhaustive run-dir listings or stdout-JSON assertions — adding `summary.json`/`writeback.json` writes is purely additive [Agent 3 finding]
- For `finalize`/`finalize_aborted` tests, the simpler `_render` + `_bash` pair (used throughout `TestFinalizeSafety`, e.g. `test_finalize_overwrites_source_in_place` ~1032–1047) is the closer analog than `InterpolationContext`/`elapsed_ms` — the latter is only needed for a `dequeue_next` deadline → `terminated_by: timeout` end-to-end test [Agent 3 finding]
- Seed `undrained.txt` for the timeout-derivation test the way `test_assemble_appends_partial_drain_marker...` does (~lines 1000–1016) [Agent 3 finding]
- `record_capped`/`capped.txt` has **zero existing test coverage** — the issue's "always empty" claim is unverified by any test; a net-new test either proves the gap or asserts the one-line fix [Agent 3 finding]
- `scripts/tests/test_audit_loop_run_skill.py` (~lines 126–159, 840) asserts Step 6/6a reads `summary.json` keys generically but is `auto-refine-and-implement`-focused; no rn-refine-specific consumer test exists — optional gap if `/ll:audit-loop-run` should recognize rn-refine's new schema [Agent 3 finding]

### Documentation
- `scripts/little_loops/loops/README.md` — rn-refine artifact list may need the two new files added
- `docs/guides/LOOPS_REFERENCE.md` — run-dir artifact reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — loop-summary table row for `rn-refine` (line ~41) lists output as "Recursively refined plan.md (in place)" only; the `rn-implement` row explicitly lists `summary.json` — update the rn-refine row when this lands [Agent 2 finding]
- `docs/reference/COMMANDS.md` (~lines 878–882) — generic `met`/`phantom`/`honest-failure` verdict table keyed off "summary.json present/absent"; no change needed (rn-refine becomes *more* compliant), listed for awareness only [Agent 2 finding]

## Implementation Steps

1. In `rn-refine.yaml` `finalize`: compute counts via the awk `count()` helper from `dequeue_count.txt`, `leaves.txt`, `capped.txt`, `failed_nodes.txt`, `queue.txt`+`undrained.txt`, and `node_outcome_*.txt`-vs-`visited.txt` diff; derive `terminated_by` (`timeout` if `undrained.txt` non-empty, else `success`); `printf` the flat JSON to `$RUN_DIR/summary.json` **before** the early-exit guards run their `exit 0` (or on every branch), so DRY_RUN/CONFIRM/missing-source exits still produce a summary with `source_overwritten: false`.
2. In `finalize`, right after `cp "$RUN_DIR/plan.md" "$SOURCE"`: `printf` `writeback.json` with `{written: true, timestamp, source_path, backup_path}`; on guard exits write `{written: false, ...}`.
3. In `finalize_aborted`: extend the existing `python3 -c` block to also write its payload (plus the summary counters, `terminated_by: "aborted"`, `source_overwritten: false`) to `$RUN_DIR/summary.json` before `exit 1`.
4. Decide whether to fix `record_capped` to actually append to `capped.txt` (one-line change) or document `capped` as best-effort; the summary reads the file either way.
5. Add tests in `scripts/tests/test_rn_refine.py` per the `TestDequeuePlumbing` idiom: seed a tmp run dir with the ledger files, render the state action with `interpolate()`, run under `_bash`, `json.loads` the produced `summary.json`/`writeback.json`, assert keys and `terminated_by` for success, dry-run, timeout (undrained non-empty), and aborted paths.
6. Run `python -m pytest scripts/tests/test_rn_refine.py -v` and `ll-loop validate rn-refine`; then verify against one real run per the issue's note (simulate won't exercise artifact reads).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — add `summary.json` (+ `writeback.json`) to the rn-refine row of the loop-summary table (~line 41), matching how the `rn-implement` row lists its outputs.
8. Optionally add an rn-refine-flavored fixture case to `scripts/tests/test_audit_loop_run_skill.py` so the audit skill's summary-reading step is exercised against the new schema (existing cases are auto-refine-and-implement-only).

## Related Key Documentation

| Document | Relevance |
|---|---|
| .claude/CLAUDE.md | Loop Authoring meta-loop rules (MR-3: intermediate artifacts should live under `${context.run_dir}/`, which `summary.json`/`writeback.json` already satisfy by design) |

## Status

- [x] Completed

## Resolution

Implemented in `scripts/little_loops/loops/rn-refine.yaml` (TDD, tests first):

- **`finalize`**: computes node counters (awk `count()` helper over `dequeue_count.txt`, `leaves.txt`, `capped.txt`, `failed_nodes.txt`, `queue.txt`+`undrained.txt`, and `visited.txt`-minus-`node_outcome_*.txt` for `wip_nodes`), derives `terminated_by` (`timeout` if `undrained.txt` non-empty, else `success`), and writes `$RUN_DIR/summary.json` + `$RUN_DIR/writeback.json` on **every** branch — the three early-exit guards (missing source/plan, DRY_RUN, CONFIRM) record `source_overwritten: false`/`written: false`; the success path records `written: true` with timestamp, source path, and backup path after both `cp`s.
- **`finalize_aborted`**: same counters computed in bash, exported into the existing `python3 -c` block (also fixing the latent bug where `RUN_DIR` was never exported, so the stdout payload's `working_copy` was empty), which now writes `summary.json` with `terminated_by: "aborted"` before `exit 1`. The stdout JSON contract is preserved.
- **`record_capped`**: one-line fix — now appends the node id to `capped.txt` (was stdout-only, so `capped` would always have read 0).
- **`dequeue_next`** deadline branch: unchanged per the plan — `timeout` is derived at summary-write time from `undrained.txt`.

Tests: new `TestRunSummaryArtifacts` (6 tests) in `scripts/tests/test_rn_refine.py` covering success, dry-run, missing-source, timeout-derivation, aborted, and the `capped.txt` fix — Red confirmed before implementation. Docs: rn-refine rows updated in `docs/guides/RECURSIVE_LOOPS_GUIDE.md` and `scripts/little_loops/loops/README.md`.

Verification: 15,603 passed / 38 skipped full suite; `ruff check` and `mypy` clean; `ll-loop validate rn-refine` valid. Note: the issue's "verify against a real (non-simulated) run" step is deferred to the next live rn-refine run — the tests execute the real rendered bash action bodies against seeded run dirs, which exercises the artifact-reading logic directly. Optional step 8 (rn-refine fixture in `test_audit_loop_run_skill.py`) was skipped: the audit skill reads `summary.json` keys generically.

## Session Log
- `/ll:manage-issue` - 2026-07-20T22:06:57Z - `37b7b2be-ab04-4639-8100-de7c84f2dd6a.jsonl`
- `/ll:ready-issue` - 2026-07-20T21:55:09 - `a9005080-682b-424c-8a21-db0ebb23af89.jsonl`
- `/ll:confidence-check` - 2026-07-20T22:10:00 - `ae96be70-7cc9-4272-bea0-1ad6facb6aca.jsonl`
- `/ll:wire-issue` - 2026-07-20T21:52:34 - `4878a212-dfff-4965-9808-57d1b1f5f243.jsonl`
- `/ll:refine-issue` - 2026-07-20T21:47:41 - `cf7aff05-068d-4b61-a537-ff8de388abb7.jsonl`
- `/ll:capture-issue` - 2026-07-20T19:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e43208e6-cc93-448d-8f8e-8ba33fb2cb7e.jsonl`
