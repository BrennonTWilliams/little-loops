---
id: ENH-2418
title: 'rn-refine finalize: diff-invariant guard and rollback for in-place source
  overwrite'
type: ENH
priority: P3
status: open
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Medium
relates_to:
- EPIC-2412
labels:
- loops
- rn-refine
- safety
- data-integrity
decision_needed: false
confidence_score: 97
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 23
---

# ENH-2418: rn-refine finalize — diff-invariant guard and rollback for in-place source overwrite

## Summary

`rn-refine`'s `finalize` state **overwrites the user's source plan file in place**
with LLM-reassembled content whose only quality gate is a self-scored rubric
(`plan_rubric_score`, `final_score` is records-only). A degenerate synthesis can
silently clobber the original with no diff-size invariant, no confirmation, and no
rollback beyond the retained `.loops/` working copy. Add a guard so a catastrophic
reassembly cannot destroy the source.

## Motivation

The recursive descent → bottom-up synthesis is the family's showcase, but its final
write is unguarded. If `assemble`/`integrate_node` produces a truncated or empty
`final.md` (LLM error, timeout phantom), `finalize` writes it straight over the user's
file. The `.loops/` copy is recoverable only if the user knows to look.

## Current Behavior

`rn-refine`'s `finalize` state overwrites the user's source plan file in place with
LLM-reassembled content. The only quality gate is a self-scored rubric
(`plan_rubric_score`; `final_score` is records-only). There is no diff-size invariant,
no confirmation, and no rollback beyond the retained `.loops/` working copy, so a
degenerate synthesis can silently clobber the original.

## Expected Behavior

Before overwriting, `finalize` enforces a diff-size invariant and writes a timestamped
backup. If the reassembled content is empty, drops below a floor fraction of the
original length, or loses required top-level sections, the run aborts to a safe
`finalize_aborted` state, leaves the source untouched, and terminates non-`done` with
the backup and `.loops/` working-copy paths surfaced.

## Proposed Solution

1. Before overwrite, compute a **diff-size invariant**: reject (route to a safe
   `finalize_aborted` state) if the new content is empty, below a floor fraction of the
   original length, or drops required top-level sections present in the source.
2. Write a timestamped backup of the original next to the source (or into `${run_dir}/`)
   and record its path in the report.
3. On invariant failure, keep the original untouched, surface a loud warning + the
   `.loops/` working-copy path, and terminate non-`done`.
4. Optional `--context confirm_overwrite=true` / `dry_run=true` knobs (dry-run writes
   only the working copy and prints the diff).

### Concrete Patterns To Reuse

_Added by `/ll:refine-issue` — anchors below are from codebase findings:_

- **Diff-size computation**: Mirror `DIFF_SIZE=$(diff "$A" "$B" | wc -c | tr -d ' ')` from `scripts/little_loops/loops/adversarial-redesign.yaml:144-169` `svg_diff`. For the floor-fraction invariant, prefer `NEW_LEN=$(wc -c < "$RUN_DIR/plan.md")` and `ORIG_LEN=$(wc -c < "$SOURCE")` instead — `DIFF_SIZE` includes line-noise on long plans; the **ratio** `NEW_LEN / ORIG_LEN >= floor_fraction` is the more robust signal.
- **Backup filename**: Use `$(date -u +%Y%m%dT%H%M%SZ)` per `scripts/little_loops/loops/integrate-sdk.yaml:218`. Recommended: write to `${RUN_DIR}/source-backup-$(date -u +%Y%m%dT%H%M%SZ).md` so the backup lives with the per-run artifacts (not next to the user's source, which keeps the user's project tree clean).
- **Per-iteration counter fallback**: If the timestamp-collision risk matters, use the `iter_counter` + `iter-$N/` pattern from `scripts/little_loops/loops/lib/common.yaml:205-231`. Either is sufficient; ISO timestamp is simpler for a one-shot.
- **Safe-abort state shape**: Mirror `scripts/little_loops/loops/loop-composer-adaptive.yaml:752-766` `abort_composer` exactly — `terminal: true`, `action_type: shell`, JSON payload with `success: false`, `summary: <invariant_violation_reason>`, `backup_path: <path>`, `working_copy: <run_dir/plan.md>`, `original_unchanged: true`, trailing `exit 1`.
- **Splitting finalize into two states**: Recommended approach — add a new `preflight_check` state *before* `finalize`. `preflight_check` runs the invariant computation, emits `INVARIANT_OK` / `INVARIANT_FAIL: <reason>` to stdout, has `evaluate.type: output_contains` with `on_yes: finalize` (backup + overwrite), `on_no: finalize_aborted`. This separates the **policy** (preflight) from the **mechanism** (finalize), so the existing `finalize.on_error: report` semantic for shell failures stays untouched. Alternative (inline approach) is to keep the check in `finalize` and emit a sentinel the action routes on, but that mixes concerns and breaks the existing `on_error` semantics.

  > **Selected:** Add a new `preflight_check` state before `finalize` — separates read-only policy from write-mechanism and preserves `finalize.on_error: report` semantics unchanged. Inline precedents (`svg_diff`, `vega-viz validate`, `general-task verify_step`, `cli-anything-bootstrap verify_cli`) all gate **non-destructive** side-effects; none gate a destructive overwrite of user-owned content, and inline gating would shift `on_error` from exit-code-bound to verdict-bound. Score 11/12 (consistency 3, simplicity 2, testability 3, risk 3).
- **Terminal name registration**: New `finalize_aborted` either needs to be added to `FAILURE_TERMINAL_NAMES = {"failed", "error", "aborted"}` in `scripts/little_loops/fsm/validation.py:1037-1082`, or the abort should route to the existing `failed` terminal. Pre-registering `finalize_aborted` is the cleaner choice (it stays distinct from infrastructure-failure `failed`) and parallels `rn-build`'s `build_failed` precedent.

  > **Selected:** Pre-register `finalize_aborted` in `FAILURE_TERMINAL_NAMES` — parallels 3 rn-* family precedents (`build_failed`, `abort_composer`, `abort_cluster`); distinct terminal name surfaces semantic in run logs. Display layer substring-matches "abort" so reporting works regardless of registry membership. Cost is mechanical (1-line `frozenset` literal at `validation.py:1050` + 1-line tuple update at `test_builtin_loops.py:270`). Score 10/12 (consistency 3, simplicity 2, testability 3, risk 2).
- **Section-preservation check**: Inline a Python heredoc using `re.findall(r"^##\s+(.+)$", content, re.MULTILINE)` (per `scripts/little_loops/issue_parser.py:105`) on both source and reassembled content. The invariant is: `required_headings_in_source.issubset(reassembled_headings)` for any `## heading` present in source. Diff = `source_headings - reassembled_headings`; non-empty diff = invariant violation.
- **Test placement**: Add tests to `scripts/tests/test_rn_refine.py` next to the existing `TestAssembleAndFinalize` class (`:371-394`). Reuse `_render`, `_bash`, `_load_rn_refine` helpers at `:17-37`. Concrete cases to cover: (a) empty `final.md`, (b) truncated `final.md` below floor, (c) source with `## heading X` not present in reassembled content, (d) healthy path still writes AND now records a backup artifact. Mirror the structural-terminal-test pattern from `scripts/tests/test_loop_composer_adaptive.py:340-354`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-08.

#### Selected

1. **Architecture split (Set 1)**: Add a new `preflight_check` state before `finalize` (11/12)
2. **Terminal naming (Set 2)**: Pre-register `finalize_aborted` in `FAILURE_TERMINAL_NAMES` (10/12)
3. **Floor-fraction default (Set 3)**: Lock in `0.5` (single-option rule — no alternative offered by issue author)

#### Reasoning

The split-state architecture wins because the rn-* family consistently uses split-state for any pre-destructive-write check (`rn-build.build_failed`, `rn-remediate.emit_*_failed`, `loop-composer-adaptive.abort_composer`). Inline precedents (`svg_diff`, `vega-viz validate`, `general-task verify_step`, `cli-anything-bootstrap verify_cli`) all gate **non-destructive** side-effects — none gate a destructive overwrite of user-owned content. Inline would also shift `finalize.on_error: report` from exit-code-bound to verdict-bound, and the destructive overwrite would already have happened before the evaluator routes — defeating the rollback guarantee.

The new terminal wins by consistency tiebreaker: 3 rn-* family precedents establish the domain-specific failure-terminal convention. `finalize_aborted` (matching "abort" substring) displays correctly in run logs regardless of registry membership.

#### Scoring Summary

| Set | Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|---|
| 1 | A: preflight_check state | 3/3 | 2/3 | 3/3 | 3/3 | **11/12** |
| 1 | B: inline check | 1/3 | 2/3 | 1/3 | 0/3 | 4/12 |
| 2 | A: new `finalize_aborted` terminal | 3/3 | 2/3 | 3/3 | 2/3 | **10/12** |
| 2 | B: route to existing `failed` | 2/3 | 3/3 | 2/3 | 1/3 | 8/12 |
| 3 | `floor_fraction = 0.5` | — | — | — | — | locked by single-option rule |

#### Key Evidence

- **Set 1 A (11/12)**: `rn-implement.yaml::check_issue_status:656-680` literally named "pre-flight gate"; `rn-build.yaml::check_structure → llm_normalize → verify_structure → abort_normalize`; `goal-cluster.yaml::route_cluster_reassess → abort_cluster`; `harness-*.yaml::check_invariants`. `output_contains` is non-LLM so MR-4/MR-8 don't fire. Reuse: 3.
- **Set 1 B (4/12)**: 4 inline precedents all gate non-destructive side-effects. Destructive overwrite executes BEFORE evaluator reads stdout; rollback guarantee lost. No `lib/common.yaml` fragment does "check + write + route" combined. Reuse: 2.
- **Set 2 A (10/12)**: 3 rn-* family precedents (`build_failed:723-748`, `abort_composer:752-766`, `abort_cluster:740-754`). Display layer (`logs.py:1767-1770`) substring-matches "abort". Cross-cutting test at `test_builtin_loops.py:255-292` requires mirror update. Reuse: 2.
- **Set 2 B (8/12)**: 13+ loops route semantic/invariant failures to generic `failed`. `brainstorm.yaml::verify_artifacts:392-393` is closest analog. Risk: rn-refine's `failed` is currently reached only via `init.on_error → diagnose`; direct route skips diagnose. Reuse: 2.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete, anchored to actual code locations:_

1. **Register `finalize_aborted` as a valid failure terminal** — `scripts/little_loops/fsm/validation.py:1037-1082`. Add `"finalize_aborted"` to the `FAILURE_TERMINAL_NAMES` set so the new state passes validation with its `terminal: true` + `action` shape. Mirrors how `rn-build`'s `build_failed` is registered (or was originally warned-about).
2. **Add `preflight_check` state** to `scripts/little_loops/loops/rn-refine.yaml` between `final_score` (`:330-337`) and `finalize` (`:339-351`). Body: compute `NEW_LEN=$(wc -c < "$RUN_DIR/plan.md")`, `ORIG_LEN=$(wc -c < "$SOURCE")`, do `re.findall(r"^##\s+(.+)$", ..., re.MULTILINE)` on both source and reassembled content, emit `INVARIANT_OK` or `INVARIANT_FAIL: <reason>` (failure reasons: `EMPTY`, `BELOW_FLOOR:0.50`, `MISSING_SECTIONS:<list>`). Evaluator: `output_contains: pattern: "INVARIANT_OK"`. Routing: `on_yes: finalize`, `on_no: finalize_aborted`, `on_error: finalize_aborted` (defer to the new terminal rather than the existing `report` path).
3. **Modify `finalize` state** at `scripts/little_loops/loops/rn-refine.yaml:339-351` — wrap the existing `cp "$RUN_DIR/plan.md" "$SOURCE"` in two extra lines: write a timestamped backup `${RUN_DIR}/source-backup-$(date -u +%Y%m%dT%H%M%SZ).md` containing the **original** source, then perform the overwrite, then emit `BACKUP_PATH=<path>` on stdout for the report state's consumption. Honor `${context.confirm_overwrite:default=false}` and `${context.dry_run:default=false}` (read context via the standard `${context.X:default=Y}` interpolation form).
4. **Add `finalize_aborted` terminal state** at `scripts/little_loops/loops/rn-refine.yaml` near `failed` (`:407-410`). Body mirrors `scripts/little_loops/loops/loop-composer-adaptive.yaml:752-766` `abort_composer` — `terminal: true`, `action_type: shell`, JSON payload with `success: false`, `summary: "rn-refine finalize aborted: <reason>"`, `backup_path: <path-or-null>`, `working_copy: <run_dir>/plan.md`, `original_unchanged: true`, trailing `exit 1`.
5. **Update `report` state** at `scripts/little_loops/loops/rn-refine.yaml:353-391` to surface the backup path. Look for `${captured.run_dir.output}` access pattern; add backup-path surfacing via either (a) a sidecar file like `${RUN_DIR}/.backup-path` written by `finalize` and `cat`-read by `report`, or (b) extend the report fragment to read `source-backup-*.md` filenames in `run_dir`.
6. **(Optional)** Add `--context` defaults to `.ll/ll-config.json` under a `loops.run_defaults.rn-refine` block: `floor_fraction: 0.5`, `confirm_overwrite: false`, `dry_run: false`. Update `config-schema.json` if schema validation is enforced.
7. **Add regression tests** to `scripts/tests/test_rn_refine.py`. New class `TestFinalizeSafety` (or extend `TestAssembleAndFinalize`) with: `test_preflight_aborts_on_empty_final`, `test_preflight_aborts_on_truncated_below_floor`, `test_preflight_aborts_on_missing_required_sections`, `test_finalize_creates_timestamped_backup_on_healthy_path`, `test_finalize_aborts_when_dry_run_is_true`. Add `test_finalize_aborted_is_terminal` to `TestTerminalAndDiagnoseRouting` (`:106-128`).
8. **(Documentation)** Update `docs/guides/LOOPS_REFERENCE.md:346` note about in-place update and the `finalize → report → done` flow diagram (`docs/guides/LOOPS_REFERENCE.md:314-338`). Brief mention in `docs/guides/RECURSIVE_LOOPS_GUIDE.md:109-123`. Optional catalog update in `scripts/little_loops/loops/README.md:61`.
9. **Verify**: Run `python -m pytest scripts/tests/test_rn_refine.py -v` and `ll-loop validate rn-refine` (or the equivalent loop validator). Confirm new `_validate_failure_terminal_action` does not warn after step 1's registry update.
10. **Verify end-to-end**: Run a smoke test by invoking `ll-loop run rn-refine --context plan_file=<tmp>` against a synthetic bad input to confirm the abort path terminates with `finalize_aborted` and the source is byte-identical to pre-run.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. **Update BUG-1606 cross-cutting guard** — `scripts/tests/test_builtin_loops.py:267-271`. Add `"finalize_aborted"` to the membership tuple `("failed", "error", "aborted")` at line 270 so `test_all_failure_terminals_have_diagnostic_action` explicitly tracks the new terminal. The test literal is independent of `FAILURE_TERMINAL_NAMES` and does not auto-sync. [Phase 4 Agent 1 + 2 finding]
12. **Augment existing happy-path test** — `scripts/tests/test_rn_refine.py:383-394`. Extend `test_finalize_overwrites_source_in_place` with a glob-based assertion that the new `${run_dir}/source-backup-*.md` file exists after a healthy run, so the new backup artifact is verified end-to-end. [Phase 4 Agent 3 finding]

## Acceptance Criteria

- A synthesized `final.md` that is **empty** OR whose byte-length is **below 50% of the original** (`floor_fraction` defaults to `0.5`, configurable via `--context floor_fraction=…`) OR that **drops any top-level `## heading` present in the source** does NOT overwrite the source; the run terminates via the new `finalize_aborted` state with a clear reason (one of `EMPTY`, `BELOW_FLOOR:<ratio>`, `MISSING_SECTIONS:<list>`) and the backup/working-copy paths surfaced in the report.
- A healthy run still overwrites in place AND now writes a timestamped backup to `${run_dir}/source-backup-<ISO-timestamp>.md` whose path is recorded in the run report.
- Unit/integration tests cover the degenerate-synthesis abort path with at least four scenarios: empty final, truncated-below-floor, missing required sections, and healthy-path-records-backup; the new `finalize_aborted` state passes `terminal: true` validation via the registered `FAILURE_TERMINAL_NAMES` set.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rn-refine.yaml` (primary change site):
  - `:317-328` `assemble` — current defensively copies `nodes/n0/final.md` → `run_dir/plan.md`; output is what `finalize` blindly overwrites source with.
  - `:330-337` `final_score` — `plan_rubric_score` fragment, **records-only** (both `on_yes` and `on_no` route to `finalize`); the only existing quality gate and it doesn't block the write.
  - `:339-351` `finalize` — the unguarded write `cp "$RUN_DIR/plan.md" "$SOURCE"`. **This is the line ENH-2418 protects.**
  - `:407-410` `failed` — existing non-`done` terminal; reached only via `init.on_error → diagnose`. Add new `finalize_aborted` terminal alongside (distinct semantic: invariant violation, not infrastructure crash).
  - `:41-44` `context:` block — only `plan_file`, `max_depth`, `max_node_iters`, `max_nodes` exist. The new optional knobs (`confirm_overwrite`, `dry_run`, `floor_fraction`) would be additive.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/validation.py:1037-1082` — `_validate_failure_terminal_action` enforces `FAILURE_TERMINAL_NAMES = {"failed", "error", "aborted"}`. A new `finalize_aborted` terminal will trigger a "non-standard failure terminal" warning until added to that set. **Either add `finalize_aborted` to `FAILURE_TERMINAL_NAMES` or route the abort to the existing `failed` terminal.**
- `scripts/little_loops/fsm/interpolation.py` — `${captured.run_dir.output}` and `${context.X:default=Y}` interpolation engine used by `finalize` action body. The `${VAR:-default}` shell escape pattern (per MR-7) must use `${VAR:default=value}` to be parseable by the FSM engine.
- `.ll/ll-config.json` and `config-schema.json` — no existing `confirm_overwrite`/`dry_run` defaults for `rn-refine`; the new context keys would need defaults wired here (optional).

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/logs.py:1767-1770` — `_derive_loop_outcome` substring-matches `"abort"`, `"fail"`, `"error"` against `final_state`. No code change needed: `finalize_aborted` contains the substring `"abort"` and is auto-detected by the display layer. This is the property the decision rationale at `.ll/decisions.yaml:4528-4531` depends on. [Agent 2 finding]
- `scripts/little_loops/fsm/evaluators.py:331` + `docs/guides/LOOPS_GUIDE.md:403,1160` — `output_contains` exit-code short-circuit routes shell non-zero exit to `on_error` (not to stdout match). Confirms the implementation step 2's `on_error: finalize_aborted` is the correct routing. [Agent 2 finding]
- `scripts/little_loops/loops/__init__.py` — empty file, no loop registry to update. [Agent 1 finding]
- `scripts/little_loops/fsm/schema.py:1333` `get_terminal_states()` — name-agnostic discovery via the `terminal=True` flag. `finalize_aborted` is auto-discovered; no update required. [Agent 1 finding]
- `scripts/tests/test_cli_loop_background.py:813,817,849,870,874,907` — uses `"rn-refine"` as a fixture name for `LockManager` / `run_background` scope-conflict tests. The test builds a synthetic `FSMLoop` and does NOT load `rn-refine.yaml`. No coupling to the new state. [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py:1358-1435` — `_loop_resolve_run_inheritance` parses `--context KEY=VALUE` and forwards to the engine at `:1435` via `cmd.extend(["--context", kv])`. The new context keys (`floor_fraction`, `confirm_overwrite`, `dry_run`) flow through the existing mechanism; no code change. [Agent 2 finding]
- `scripts/little_loops/parallel/types.py:166` `FAILED = "failed"` — Issue-status `failed`, not loop-state `finalize_aborted`; unrelated. [Agent 2 finding]
- `scripts/little_loops/fsm/persistence.py:564,860,873,912,920` — uses `{"completed", "failed", "timed_out"}` for "runner-exit bucket" classification, not FSM state names; irrelevant to `finalize_aborted`. [Agent 2 finding]
- **No skills/agents/commands invoke `ll-loop run rn-refine` directly** — zero coupling outside the loop YAML + primary test files. [Agent 1 + 2 finding]
- **No code-side loop catalog / registry** — loop discovery is filesystem-driven via the loader. [Agent 1 finding]
- **No `--context` CLI changes needed** — the new context keys flow through the existing `--context KEY=VALUE` mechanism. [Agent 2 finding]

### Similar Patterns (Reuse From)

- **Byte-diff convergence check** — `scripts/little_loops/loops/adversarial-redesign.yaml:144-169` `svg_diff` state. The idiom `DIFF_SIZE=$(diff "$A" "$B" | wc -c | tr -d ' ')` and the `output_contains` evaluator with `on_yes`/`on_no` routing is the closest existing diff-magnitude pattern.
- **Per-iteration snapshotting** — `scripts/little_loops/loops/lib/common.yaml:205-231` `snapshot_artifact` fragment. Uses `iter_counter` + `mkdir -p "$RUN_DIR/iter-$COUNTER"` + `cp` to retain snapshots before each iteration's overwrite.
- **ISO-timestamped one-shot filenames** — `scripts/little_loops/loops/integrate-sdk.yaml:218` uses `diagnosis-$(date -u +%Y%m%dT%H%M%SZ).md`. Established convention: `source-backup-$(date -u +%Y%m%dT%H%M%SZ).md`.
- **Non-`done` safe-abort terminal with JSON payload** — `scripts/little_loops/loops/loop-composer-adaptive.yaml:752-766` `abort_composer`, `scripts/little_loops/loops/goal-cluster.yaml:740-754` `abort_cluster`, and `scripts/little_loops/loops/rn-build.yaml:723-748` `build_failed` all encode the convention: `terminal: true`, JSON summary, `success: false`, trailing `exit 1` (cosmetic — runner exit derives from `terminated_by`).
- **Section-extraction utility** — `scripts/little_loops/issue_parser.py:105-126` provides `re.findall(r"^##\s+(.+)$", content, re.MULTILINE)` heading enumeration and `required.issubset(headings)` membership check. Same regex fits the "required top-level sections preserved" invariant.
- **Pre-terminal diagnose step** — `scripts/little_loops/loops/rn-refine.yaml:398-410` already wires `diagnose` → `failed` via the `loop_failure_diagnose` fragment in `lib/common.yaml:276-302`. New `finalize_aborted` may optionally route through `diagnose` for diagnostic richness.

### Tests

- `scripts/tests/test_rn_refine.py:371-394` — Existing `TestAssembleAndFinalize` class has `test_assemble_prefers_root_final` and `test_finalize_overwrites_source_in_place`. The new degenerate-path test should sit next to these (or in a new `TestFinalizeSafety` sibling class) using the same `_render` / `_bash` / `_load_rn_refine` helpers.
- `scripts/tests/test_rn_refine.py:17-37` — reusable test helpers (`_render`, `_bash`, `_load_rn_refine`, `InterpolationContext`, `interpolate`, `load_and_validate`).
- `scripts/tests/test_loop_composer_adaptive.py:340-354` — structural `test_abort_composer_is_terminal` and `test_failed_is_terminal` patterns. Mirror as `test_finalize_aborted_is_terminal`.
- **No existing test covers the degenerate path** (empty `final.md`, truncated `final.md`, missing `plan.md`, missing `.source-path`, broken source symlink). ENH-2418's AC #3 expects a new test; the gap is currently real.

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_builtin_loops.py:267-271` — `test_all_failure_terminals_have_diagnostic_action` hardcodes `("failed", "error", "aborted")` as the membership tuple for the BUG-1606 guard. **Add `"finalize_aborted"` to the tuple** at line 270 so the cross-cutting guard explicitly tracks the new terminal. This tuple is independent of `FAILURE_TERMINAL_NAMES` in `validation.py:1050` — the test literal does not auto-sync. [Agent 1 + 2 finding]
- `scripts/tests/test_builtin_loops.py:39-54` — `test_all_validate_as_valid_fsm` is the regression gate that confirms step 1 (the `FAILURE_TERMINAL_NAMES` registration) actually shipped. The test re-validates every loop YAML and will pass automatically once `finalize_aborted` is registered. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:7582-7634` — `TestRnRefineRecursiveDecomposition` class loads `rn-refine.yaml` directly via `yaml.safe_load` (not through the validator). New `preflight_check` and `finalize_aborted` states will be visible to this class but no current assertion breaks; a re-read at PR time is recommended to confirm. [Agent 1 + 3 finding]
- `scripts/tests/test_rn_refine.py:383-394` — `test_finalize_overwrites_source_in_place` will need augmentation: add a glob-based assertion (e.g., `any((run_dir / "source-backup-*.md").exists() ...)`) so the new timestamped backup is verified on the healthy path. Current assertions (source contents match plan.md) are not affected by the change. [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — gap noted: no direct test of `_validate_failure_terminal_action`. The validator is exercised only via the cross-cutting guard above. Out of scope for ENH-2418. [Agent 3 finding]
- `scripts/tests/test_rn_refine.py:219-226` — existing `test_empty_queue_emits_sentinel` is the exact pattern to mirror for `INVARIANT_OK` / `INVARIANT_FAIL` assertions in `preflight_check` tests. [Agent 3 finding]
- `scripts/tests/test_rn_refine.py:150-172` — `test_seeds_root_node_and_worktree_files` is the file-system assertion pattern to mirror for `${run_dir}/source-backup-*.md` existence checks. [Agent 3 finding]
- `scripts/tests/test_rn_implement.py:408-452` — `_run_report` helper is the closest analog for rendering + executing action bodies that reference `${context.run_dir}` and `${captured.run_dir.output}`. Useful for the `finalize_aborted` JSON-payload tests. [Agent 3 finding]
- `scripts/tests/test_rn_decompose.py:285-302` — `test_failed_is_bare_terminal` + `test_terminal_states_have_no_outgoing_routes` patterns. Mirror as `test_finalize_aborted_has_no_outgoing_routes` if the new terminal is bare. [Agent 3 finding]
- **No end-to-end tests exist for `rn-refine`** — `scripts/tests/integration/test_loop_run_e2e.py`, `test_init_e2e.py`, `test_issue_lifecycle_e2e.py` do not reference `rn-refine`. ENH-2418 step 10's "verify end-to-end" remains a manual smoke test, not a pytest case. [Agent 3 finding]

### Documentation

- `docs/guides/LOOPS_REFERENCE.md:280-346` — `rn-refine` section with FSM flow diagram; the in-place update note (line 346) and the `finalize → report → done` portion of the diagram will need updating once the guard lands.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:109-123` — narrative description of rn-refine; will need a brief note about the new safety guard.
- `docs/reference/API.md:543` — documents `--context KEY=VALUE` CLI flag injection mechanism. Reference for documenting `confirm_overwrite`/`dry_run` invocation.
- `scripts/little_loops/loops/README.md:61` — loop catalog row for `rn-refine`; the new context knobs would need to be listed (optional columns to add).

### Configuration

- No existing `.ll/ll-config.json` keys for `rn-refine`'s safety knobs. Optional: add `loops.run_defaults.rn-refine` block with `confirm_overwrite: false`, `dry_run: false`, `floor_fraction: 0.5` defaults so the `--context KEY=VALUE` overrides work consistently.

## Scope Boundaries

- **In scope**: Diff-size invariant, timestamped backup, safe-abort terminal, and
  optional `confirm_overwrite`/`dry_run` knobs for `rn-refine`'s `finalize` write path.
- **Out of scope**: Redesigning the recursive-descent synthesis itself or changing the
  `plan_rubric_score` rubric; this issue only guards the final in-place write.

## Location

- `scripts/little_loops/loops/rn-refine.yaml` — `assemble` (`:317-328`), `final_score`
  (`:330-337`), `finalize` (`:339-351`), `report` (`:353-391`), `failed` terminal
  (`:407-410`); new state `preflight_check` slots between `final_score` and `finalize`;
  new terminal `finalize_aborted` slots near `failed`.
- `scripts/little_loops/fsm/validation.py:1037-1082` — register `finalize_aborted` in
  `FAILURE_TERMINAL_NAMES`.
- `scripts/tests/test_rn_refine.py` — extend `TestAssembleAndFinalize` (`:371-394`) or
  add `TestFinalizeSafety` sibling.

## Impact

- **Priority**: P3 - Data-integrity safeguard against a low-probability but destructive
  failure (silent overwrite of the user's source file).
- **Effort**: Medium - Adds an invariant check, backup write, and abort terminal to one
  state in `rn-refine.yaml` plus a regression test; no cross-loop changes.
- **Risk**: Low - Additive guard; a healthy run still overwrites in place, now with a
  recorded backup.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-30 | Priority: P3

## Codebase Research Findings Summary

_Added by `/ll:refine-issue` (auto mode) — distilled from the three research agents:_

- **Single risky write site**: `scripts/little_loops/loops/rn-refine.yaml:343` contains the unguarded `cp "$RUN_DIR/plan.md" "$SOURCE"` inside the `finalize` state's `action` block. No existing invariant or backup. (`assemble` (`:317-328`) and `final_score` (`:330-337`) precede it; both `final_score.on_yes` and `final_score.on_no` route here unconditionally.)
- **`rn-refine` is unique in the rn-* family**: every other rn-* loop either doesn't perform in-place writes (`rn-plan`, `rn-implement`, `rn-remediate`, `rn-decompose`, `rn-build`) or scopes writes narrowly (`rn-plan-apo` writes a config prompt, `rn-build` writes `docs/` artifacts). `rn-refine` is the only loop writing arbitrary user-supplied paths, which is why this guard is the only one that needs to exist.
- **Existing safe-abort pattern is mature**: `abort_composer` (`loop-composer-adaptive.yaml:752-766`), `abort_cluster` (`goal-cluster.yaml:740-754`), and `build_failed` (`rn-build.yaml:723-748`) all use the same shape — `terminal: true`, JSON summary, `success: false`, trailing `exit 1`. Mirroring one of these for `finalize_aborted` keeps the loop catalog's diagnostic UX consistent.
- **Test gap is real**: `scripts/tests/test_rn_refine.py:371-394` only covers the happy path (`assemble → finalize`). No degenerate-path coverage exists for empty final.md, truncated output, missing sections, missing source-path, or broken symlinks. ENH-2418's AC #3 expects new test coverage to land with the guard.
- **FSM engine constraint surfaced**: A new `finalize_aborted` terminal triggers a validator warning unless added to `FAILURE_TERMINAL_NAMES` in `scripts/little_loops/fsm/validation.py:1037-1082`. Step 1 of Implementation Steps addresses this.
- **Decision point**: ≥2 distinct implementation approaches remain on the table — splitting into a `preflight_check` state vs. inline checking inside `finalize`; using `finalize_aborted` vs. routing abort to the existing `failed` terminal; choosing the floor-fraction default (0.5 recommended). These warrant a `/ll:decide-issue` pass before `/ll:wire-issue`.


## Session Log
- `/ll:confidence-check` - 2026-07-08T19:40:46 - `1be81ae7-2a56-476a-afe4-10fc2599a89d.jsonl`
- `/ll:wire-issue` - 2026-07-08T19:38:30 - `28a33135-d85e-41db-a823-249d38b11664.jsonl`
- `/ll:decide-issue` - 2026-07-08T19:23:18 - `1fa0a2f6-4d3c-4cc6-b4dc-5ae278b14109.jsonl`
- `/ll:refine-issue` - 2026-07-08T19:11:06 - `61317e5b-3e91-4052-b766-c1270d8b1f55.jsonl`
