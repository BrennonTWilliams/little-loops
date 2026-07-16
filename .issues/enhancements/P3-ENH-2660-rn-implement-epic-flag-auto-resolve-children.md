---
id: ENH-2660
title: Add `--epic` flag to `rn-implement` for auto-resolving children
type: enhancement
priority: P3
status: open
decision_needed: false
captured_at: '2026-07-16T20:52:21Z'
discovered_date: 2026-07-16
discovered_by: capture-issue
labels:
- enhancement
- loops
- fsm
- rn-implement
- captured
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-2660: Add `--epic` flag to `rn-implement` for auto-resolving children

## Summary

The `rn-implement` FSM loop (`scripts/little_loops/loops/rn-implement.yaml`) is the project's queue orchestrator for recursive plan-and-implement runs, and it already has two paths that produce children of an EPIC:

1. **Auto-decompose** via `rn-remediate` → `rn-decompose` — used when an EPIC is passed bare and the remediation path emits `NEEDS_DECOMPOSE` (line 1106: `loop: rn-decompose`). This is the "I have an EPIC, decompose it for me" path.
2. **Pre-existing children** — used when an EPIC's children were already created out-of-band (e.g. via `/ll:scope-epic` or `/ll:create-epics-from-unparented`) and are linked via `parent:` frontmatter. **There is no first-class path for this.** The `init` state (line 80) only normalizes the IDs it receives; it does not walk `parent:` frontmatter, so the user must either manually enumerate the children or shell-pipe `ll-issues list --parent EPIC-XXX`.

The fix: add a `--epic EPIC-XXX` flag (or auto-detect when the input resolves to an EPIC) that seeds `queue.txt` with the EPIC's `parent:`-linked children, preserving all downstream behavior (cycle detection via `max_depth`, `check_blocked_by` gating, `re_enqueue_unblocked`, `schedule_mode: value_ranked`).

## Current Behavior

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The `init` state's queue-seeding block lives at lines 79-103 of `scripts/little_loops/loops/rn-implement.yaml`, with the broader `init` action body spanning lines 57-132 (including the empty-input guard at 61-64, the `RESUME` short-circuit at 71-77, and tracking-file initialization at 106-119).
- **BUG-2003 Layer 1 canonicalization** (lines 86-97) is the existing mechanism that collapses mismatched type prefixes (e.g. `FEAT-1903` → `ENH-1903`). Child IDs returned by `ll-issues list --parent` are already canonical (they came from `parent:` frontmatter resolution, not user input), so the new `epic` branch can write directly to `queue.txt` without re-running the BUG-2003 normalization loop.
- The `RESUME` short-circuit at lines 71-77 (`[ -n "$RESUME" ] && [ -s "$RUN_DIR/queue.txt" ]`) is the structural template for the new `epic` branch: same `[ -n "$EPIC" ]` guard, same `echo "$RUN_DIR"; exit 0` short-circuit shape, same stderr logging convention.
- The `ll-issues list --parent` primitive is implemented at `scripts/little_loops/cli/issues/list_cmd.py:55-87`. It uses `compute_epic_progress` (`scripts/little_loops/issue_progress.py:120`) which walks `parent:` transitively (cycle-safe via `_issue_descends_to` with a `seen` guard) — direct children, grandchildren, and deep descendants are all included.
- The `--context KEY=VALUE` CLI parser at `scripts/little_loops/cli/loop/run.py:164-168` requires no CLI plumbing change: any `key=value` string is `partition("=")`-split and written to `fsm.context[key]`. The new `epic: ""` is auto-populated by `--context epic=EPIC-2457`.
- **MR-11 lint passes by name**: `_UNSAFE_CONTEXT_INTERP_RE` at `scripts/little_loops/fsm/validation.py:139-141` matches `input|goal|description|task|prompt|query|topic` only. `epic` is outside the regex set, so `${context.epic}` in the proposed shell body does not require `unsafe_context_interpolation_ok: true`.

`scripts/little_loops/loops/rn-implement.yaml` lines 79-103 (the `init` state's queue-seeding block) parses a comma-separated `INPUT` and resolves each ID via `ll-issues path`:

```bash
echo "$INPUT" | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -v '^$' > "$RUN_DIR/queue_raw.txt"
: > "$RUN_DIR/queue.txt"
while IFS= read -r raw_id; do
  [ -z "$raw_id" ] && continue
  resolved=$(ll-issues path "$raw_id" 2>/dev/null)
  if [ -n "$resolved" ]; then
    canon=$(basename "$resolved" | grep -oE '(BUG|FEAT|ENH|EPIC)-[0-9]+' | head -1)
    echo "$${canon:-$raw_id}" >> "$RUN_DIR/queue.txt"
  else
    echo "$raw_id" >> "$RUN_DIR/queue.txt"
  fi
done < "$RUN_DIR/queue_raw.txt"
```

It does **not** branch on EPIC type or resolve `parent:` frontmatter. A user running `ll-loop run rn-implement "EPIC-2457"` today:

- If the EPIC has no children: enters `run_remediation` → `rn-remediate` → likely `NEEDS_DECOMPOSE` → `rn-decompose` creates the children and enqueues them. Works as intended.
- If the EPIC already has children (the common case for EPICs created via `/ll:scope-epic`): enters `run_remediation` → `rn-remediate` attempts to remediate the EPIC itself. The EPIC's remediation often stalls or emits `MANUAL_REVIEW_NEEDED` because the EPIC's body is a coordination container, not an implementable unit. The pre-existing children never get queued automatically.

The user workaround today:

```bash
ll-loop run rn-implement "$(ll-issues list --json --parent EPIC-2457 | jq -r '.[].id' | paste -sd,)"
```

This is friction for a common workflow ("implement the children of this EPIC") and bypasses the loop's own ID-normalization and dedup path.

## Expected Behavior

Add a `--epic EPIC-XXX` flag that resolves the EPIC's `parent:`-linked children at `init` time and seeds `queue.txt` with them. Two equivalent invocations:

```bash
# New explicit flag
ll-loop run rn-implement --epic EPIC-2457

# Or auto-detect: if the input resolves to a file under .issues/epics/, treat as --epic
ll-loop run rn-implement "EPIC-2457"  # when EPIC-2457 has children, auto-resolve
```

The `init` state branches on `${context.epic}` (or, equivalently, on the input being an EPIC). When set:

1. Validate the EPIC exists and has at least one child.
2. Run `ll-issues list --parent EPIC-XXX --json` and extract the child IDs.
3. Seed `queue.txt` with the resolved IDs (preserving the existing `canon` normalization, dedup, and `queue_raw.txt` → `queue.txt` flow).
4. Continue into the normal `dequeue_next` → `check_blocked_by` → `check_learning_ready` → `check_depth` → `check_issue_status` chain unchanged.

The existing `auto-decompose` path (case 1 above) is preserved: passing an EPIC with no children still routes to `run_remediation` → `rn-decompose` as today.

## Motivation

`rn-implement` is the project's go-to orchestrator for "run the implementation pipeline against this issue" — invoked from `ll-auto`, `ll-sprint`, and ad-hoc operator runs. EPICs are a first-class issue type in this codebase, and the canonical workflow is:

1. Capture EPIC via `/ll:capture-issue` or `/ll:scope-epic`.
2. EPIC gets decomposed into N children with `parent: EPIC-XXX` frontmatter.
3. Operator runs `rn-implement` against the EPIC to implement the children.

Step 3 is the friction point. Today the operator must either:

- Hand-enumerate the children (error-prone, breaks if new children are added).
- Shell-pipe `ll-issues list --parent` (works, but bypasses the loop's own normalization/dedup and is invisible to the run record).
- Re-decompose the EPIC from scratch (loses the `parent:` wiring and any in-flight child status).

The cost is small per run but compounds: an operator working through a 10-child EPIC in `ll-parallel` (epic_branches mode) and then wanting to follow up on the remaining children via `rn-implement` has to rediscover them every time.

Precedent for the fix already exists: `prompt-across-issues` added an `ids` context var (ENH-2658) and earlier a `parent` filter (EPIC-1853 / ENH-2481). The `--context KEY=VALUE` shape is established. This enhancement brings the same ergonomics to `rn-implement`.

## Proposed Solution

Add an `epic: ""` context variable and branch the `init` state's queue-seeding block to resolve children when set:

```yaml
context:
  readiness_threshold: 85
  outcome_threshold: 75
  max_depth: 3
  max_remediation_passes: 3
  resume: ""
  schedule_mode: "fifo"
  skip_learning_gate: ""
  auto_prove_learning_gate: ""
  epic: ""  # Optional: EPIC-NNN whose parent:-linked children should be processed.
            # When set, overrides direct ID input — children are resolved at init time.
            # Usage: ll-loop run rn-implement --context epic=EPIC-2457
```

The `init` action branches before the existing comma-split block:

```bash
EPIC="${context.epic}"
if [ -n "$EPIC" ]; then
  EPIC_PATH=$(ll-issues path "$EPIC" 2>/dev/null)
  if [ -z "$EPIC_PATH" ]; then
    echo "ERROR: --epic target not found: $EPIC"
    exit 1
  fi
  # Resolve children via ll-issues list --parent (handles transitive parent: walk if --recursive added)
  CHILD_IDS=$(ll-issues list --parent "$EPIC" --json | python3 -c "
import json, sys
issues = json.load(sys.stdin)
for i in issues:
    print(i['id'])
")
  if [ -z "$CHILD_IDS" ]; then
    echo "ERROR: --epic $EPIC has no children. Pass the EPIC ID directly to trigger auto-decompose, or create children via /ll:scope-epic."
    exit 1
  fi
  echo "$CHILD_IDS" > "$RUN_DIR/queue.txt"
  echo "Resolved $EPIC -> $(wc -l < "$RUN_DIR/queue.txt" | tr -d ' ') child issue(s)" >&2
  echo "$RUN_DIR"
  exit 0
fi
# ... existing INPUT parsing unchanged ...
```

The pre-existing children are then dequeued individually, each one entering the normal `check_blocked_by` → `check_learning_ready` → `check_depth` → `check_issue_status` chain. Cross-child `blocked_by:` dependencies are honored (e.g. ENH-2493 blocked by ENH-2492 will not dequeue until ENH-2492 reaches `done`), and `re_enqueue_unblocked` (line 737) sweeps `deferred.txt` after each successful implementation so the chain unrolls naturally.

### `ll-issues list --parent` already exists

`scripts/little_loops/cli/issues/list_cmd.py` exposes `--parent EPIC-XXX`. The `epic_progress` consumer already walks parent: transitively (per `reference_epic_progress_non_recursive.md`), so the resolution shape is established. This change reuses that primitive — no `ll-issues` CLI work needed.

### `epic: ""` is regex-safe for MR-11

The FSM lint (`scripts/little_loops/fsm/validation.py:139-141`) flags `${context.(input|goal|description|task|prompt|query|topic)}` for unsafe interpolation. `epic` is outside that regex set, so the bare interpolation in the proposed shell body passes MR-11 by virtue of regex scope. The expected value is an EPIC ID (alphanumeric + hyphen), so the trust-boundary risk is the same as for the existing `INPUT` variable.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — add `epic: ""` to the `context:` block (around line 24-45); branch the `init` state's queue-seeding block (lines 79-103) on `${context.epic}`; update the YAML header `description:` block (lines 3-9) to document the new flag.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — add row for `epic` to the `Context variables:` table (around lines 411-418); update the `init` state-machine diagram caption at line 470 (currently reads "seed queue from comma-separated input" — must reflect the new epic short-circuit). [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — add `--context epic=EPIC-NNN` usage example alongside the existing `ll-loop run rn-implement "FEAT-1808,ENH-1842"` example at line 187 (and the parallel example at line 354). [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — update the `rn-implement` catalog row at line 63 (currently `<issue-id>` only) to add `or --context epic=EPIC-NNN`. [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py` — add `TestRnImplementEpicFlag` class (after `TestRnImplementAuthFastFail` at line 10736) covering default `epic=""`, branch reference, and the new error strings. [Agent 3 finding]
- `scripts/tests/test_rn_implement.py` — extend `TestInitAndInputValidation` (lines 33-83) with a byte-identical regression test asserting that `context.epic=""` produces the same `queue.txt` as the pre-change init for the same comma-separated INPUT. [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — add `test_mr11_does_not_fire_for_epic_context_var` to `TestUnsafeContextInterpolation` (after line 3456) to lock the regex-bounded scope so a future "tighten MR-11 regex" change cannot silently regress `rn-implement`'s `--epic` flag. [Agent 3 finding]

### Dependent Files (Callers/Importers)
- `ll-parallel` and `ll-sprint` invoke `rn-implement` programmatically — neither currently passes `--epic`, so the change is backward-compatible (existing direct-ID invocations work unchanged).
- `scripts/little_loops/loops/lib/common.yaml` is imported by `rn-implement` — no edit; the new context var is loop-local.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — references `rn-implement` (cross-loop); no edit; the new `epic` context var is loop-local and is not forwarded. [Agent 1 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — references `rn-implement` (the `rn-remediate → rn-decompose → rn-implement` chain); no edit; `--context epic=` is opt-in and never propagated by `rn-remediate`. [Agent 1 finding]
- `scripts/little_loops/loops/rn-decompose.yaml` — references `rn-implement`; the `enqueue_children` state at lines 128-214 is the existing precedent for fan-out from an EPIC to its children (with in-memory `survivors = []` dedup at lines 167-179 — the new `epic` branch must mirror this dedup step, see Wiring Phase). [Agent 1 + Agent 2 findings]
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — references `rn-implement`; no edit. [Agent 1 finding]
- `scripts/little_loops/recursive_finalize.py` — Python module that references `rn-implement`; no edit; orthogonal to the queue-seeding branch. [Agent 1 finding]
- `scripts/little_loops/cli/issues/list_cmd.py:55-87` — provides the `ll-issues list --parent EPIC-XXX` primitive the new branch calls; no edit (reused as-is). [Agent 1 finding]

### Similar Patterns
- `ENH-2658` added `ids:` to `prompt-across-issues` (same `--context KEY=VALUE` shape, same comma-separated parsing, same priority P3) — match the comment style and test placement.
- `EPIC-1853` / `ENH-2481` added `parent:` to `prompt-across-issues` — `ll-issues list --parent` is the established resolution primitive; reuse it rather than re-implementing the `parent:` walk inline.
- The existing `run_decomposition` (line 1098) and `select_next` (line 184) blocks both shell out to `ll-issues list` for resolution; their pattern is the template for the `epic` branch.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The closest **in-file** pattern is the `RESUME` branch in the SAME `init` state (lines 71-77 of `rn-implement.yaml`): the `[ -n "$RESUME" ] && [ -s "$RUN_DIR/queue.txt" ]` guard, the `echo "Resuming run..." >&2` log, and the `echo "$RUN_DIR"; exit 0` short-circuit are the exact shape to mirror for the new `[ -n "$EPIC" ]` branch. Place the new branch BEFORE the existing `INPUT` parsing at line 79 (matching where `RESUME` sits relative to the queue-seeding block).
- The `prompt-across-issues` `init` state (`scripts/little_loops/loops/prompt-across-issues.yaml:50-91`) shows the canonical 3-way branch: `if [ -n "${context.ids}" ] ... else if [ -n "${context.type}" || "${context.parent}" ] ... else`. The `python3 -c "import json, sys; ...for i in issues: print(i['id'])"` extractor at lines 80-85 is the established JSON-to-ID pattern to copy.
- The `enqueue_children` state at `scripts/little_loops/loops/rn-decompose.yaml:128-214` is the existing precedent for fan-out from an EPIC to its children — but the new `epic` branch runs BEFORE `dequeue_next`, so it writes directly to `queue.txt` (not through the rn-decompose `finalize_parent` mechanism).
- No existing rn-implement caller (`ll-auto` at `scripts/little_loops/cli/auto.py`, `ll-sprint` at `scripts/little_loops/cli/sprint/`, `ll-parallel` at `scripts/little_loops/cli/parallel.py`, `rn-build` at `scripts/little_loops/loops/rn-build.yaml`, `goal-cluster` at `scripts/little_loops/loops/goal-cluster.yaml`) currently passes `--context epic=`. The change is purely additive — backward compatibility preserved.
- **Status-filter caveat**: `ll-issues list --parent EPIC-XXX --json` filters by the configured `status:` filter (default `open`) AFTER `compute_epic_progress` computes the full transitive descendant set. Done children are silently excluded from JSON output. The init action would not re-queue already-done children — which is desirable from a work-avoidance standpoint. The `check_issue_status` pre-flight gate (`ALREADY_DONE` token) is a redundant safety net, not load-bearing here.
- The `auto_prove_learning_gate: ""` context var (line 45 in `rn-implement.yaml`) is the most recently-added opt-in string context var — its comment block (`# ENH-2431: ... #   ll-loop run rn-implement <id> --context auto_prove_learning_gate=1`) is the documentation style to match exactly for `epic: ""`.

### Tests
- `scripts/tests/test_builtin_loops.py` — add a `TestRnImplementLoop` class (or extend an existing structural test) verifying:
  - `context.epic` defaults to `""`.
  - The `init` action references `${context.epic}` or `context.epic`.
  - When `epic` is set, `queue.txt` is seeded from `ll-issues list --parent` output.
- `scripts/tests/test_fsm_fragments.py` — confirm the `rn-implement.yaml` migration smoke test still passes after the YAML edit.
- Regression: a test asserting that the existing comma-separated `INPUT` parsing path is byte-identical when `epic=""`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — the new `TestRnImplementEpicFlag` class should mirror `TestPromptAcrossIssuesLoop.test_init_supports_ids_filter` (lines 1838-1852): structural YAML assertions on `data["context"]["epic"] == ""` default and `${context.epic}` substring in `init["action"]`. Add **negative-path tests** for the new error strings (currently absent in the suite):
  - `test_init_action_errors_on_missing_epic` — asserts `"ERROR" in init_action` and `"not found" in init_action`
  - `test_init_action_errors_on_epic_with_no_children` — asserts `"no children" in init_action`
- `scripts/tests/test_rn_implement.py` — extend `TestInitAndInputValidation` (lines 33-83) with a **byte-identical regression test** for `context.epic=""`: spawn `bash -c init_action` with `${context.epic}` substituted to `""` and `${context.input}` set to a comma-separated INPUT string, then diff the resulting `queue.txt` against the same command with `epic` never referenced. Mirror the `TestCheckLearningReadyConfigReadShell._run` shape (lines 1283+). [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — add `test_mr11_does_not_fire_for_epic_context_var` to `TestUnsafeContextInterpolation` (after line 3456). The existing `test_mr11_does_not_fire_for_other_context_vars` covers `run_dir` but not `epic`; locking the regex-bounded scope prevents a future "tighten MR-11 regex" change from silently regressing the `--epic` flag. [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py` — already iterates `rn-implement.yaml` in `migration_targets` at line 1023 and calls `load_and_validate(path)`; the new `epic: ""` context var is picked up transparently. **No edit required.**
- `scripts/tests/test_rn_implement.py:732-740` (`TestValidation.test_context_defaults_match_spec`) — asserts five specific context keys; `epic` is additive. **No regression.**
- `scripts/tests/test_rn_implement.py:757-789` (`TestValidation.test_state_count_is_orchestrator_sized`) — asserts state count `≤ 46`; no new state is added (the epic branch lives inside the existing `init` state's `action:` body). **No regression.**

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — add the `--epic` usage example to the `rn-implement` section.
- `scripts/little_loops/loops/README.md` — mirror the example in the built-in loop catalog entry for `rn-implement`.
- The YAML header `description:` block — add the `--context epic=EPIC-NNN` example alongside the existing `Run as: ll-loop run rn-implement "<issue-id>"` line.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — has `ll-loop run rn-implement "FEAT-1808,ENH-1842"` at line 187 and again at line 354; add `--context epic=EPIC-NNN` to both examples. [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:470` — state-machine diagram caption reads "seed queue from comma-separated input, init tracking files"; update to "seed queue from epic-as-input OR comma-separated input, init tracking files" to reflect the new branch. [Agent 2 finding]

### Configuration
- N/A — no `config-schema.json` change. The `epic` context var is a loop-local CLI flag, not a project config field.

## Implementation Steps

1. Add `epic: ""` to the `context:` block of `rn-implement.yaml` (insert near the existing `auto_prove_learning_gate: ""` line, ~line 45).
2. Branch the `init` state's `action:` body on `${context.epic}` BEFORE the existing INPUT-parsing block (~line 79). When `epic` is set: validate, resolve children via `ll-issues list --parent`, seed `queue.txt`, exit 0 to short-circuit into `dequeue_next`. When `epic=""`: existing INPUT parsing runs unchanged.
3. Update the YAML header `description:` block with the new usage: `ll-loop run rn-implement --context epic=EPIC-2457`.
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` to confirm the YAML still parses and the existing tests pass.
5. Add a `TestRnImplementLoop` test class (or extend an existing one) covering: default `epic=""`, branch reference, and queue seeding shape.
6. Add a regression test asserting that `epic=""` produces byte-identical behavior to the pre-change `init` for the same comma-separated INPUT.
7. Update `docs/guides/LOOPS_REFERENCE.md` and `scripts/little_loops/loops/README.md` with the new usage.
8. Verify end-to-end on a real EPIC: `ll-loop run rn-implement --context epic=EPIC-XXXX --dry-run` (or `--baseline` if available) confirms the queue resolves to the expected children.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and MUST be included in the implementation:_

9. **Dedup the resolved child IDs** — the proposed shell body at lines 142-147 of this issue omits `sort -u` (or equivalent in-Python dedup) on the resolved child IDs from `ll-issues list --parent`. `compute_epic_progress` (`scripts/little_loops/issue_progress.py:120`) is cycle-guarded via `_issue_descendants_to`, but a transitive parent-chain cycle reachable via two parent-paths from the same EPIC could still emit the same child ID twice. Without dedup, `fifo_pop` would dequeue the duplicate child twice in series. The BUG-2003 canonicalization loop at lines 86-97 dedups implicitly via `ll-issues path` resolution, but `ll-issues list --parent` does not. **Mirror the `enqueue_children` dedup pattern at `scripts/little_loops/loops/rn-decompose.yaml:167-179`** (`survivors = []` in-memory set + visited check). [Agent 2 critical finding]

10. **Initialize tracking files BEFORE the epic short-circuit** — the proposed `exit 0` short-circuit at line 155 bypasses the tracking-file initialization block (lines 106-119) that creates `visited.txt`, `depth_capped.txt`, `skipped.txt`, `deferred.txt`, `blocked.txt`, `cycles.txt`, `rate_limits.txt`, `failures.txt`, `timeouts.txt`, `dequeue_count.txt`, `implemented_count.txt`, `decomposed_count.txt`, and `config.json`. Downstream states have `|| echo 0` fallbacks for missing files, so functional behavior is preserved — BUT `config.json` is never written for epic-seeded runs (silent semantic divergence from the comma-separated path). **Move the tracking-file init block to run BEFORE the epic branch**, OR explicitly run only the tracking-file init inside the epic branch before `exit 0`. [Agent 2 finding]

11. **Update `docs/guides/LOOPS_REFERENCE.md:411-418` Context variables table** — add a row for `epic`. The table currently lists the documented context vars; omitting `epic` would create a documentation drift. [Agent 2 finding]

12. **Update `docs/guides/LOOPS_REFERENCE.md:470` state-machine caption** — change "seed queue from comma-separated input, init tracking files" to reflect the new epic short-circuit ("seed queue from epic-as-input OR comma-separated input, init tracking files"). [Agent 2 finding]

13. **Update `docs/guides/RECURSIVE_LOOPS_GUIDE.md` lines 187 and 354** — add `--context epic=EPIC-NNN` to the usage examples. [Agent 2 finding]

14. **Update `scripts/little_loops/loops/README.md:63`** — extend the `rn-implement` catalog row's input shape to include `or --context epic=EPIC-NNN`. [Agent 2 finding]

15. **Add `test_mr11_does_not_fire_for_epic_context_var`** to `TestUnsafeContextInterpolation` in `scripts/tests/test_fsm_validation.py` (after line 3456) — locks the regex-bounded scope so a future "tighten MR-11 regex" change cannot silently regress the `--epic` flag. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The new test class should be named `TestRnImplementEpicFlag` (matching the `TestRnImplementAuthFastFail` style at `scripts/tests/test_builtin_loops.py:10679`) and live alongside it in `scripts/tests/test_builtin_loops.py`. The class should mirror the structural-test pattern from `TestPromptAcrossIssuesLoop.test_init_supports_ids_filter` (`scripts/tests/test_builtin_loops.py:1817-1852`): assert `data.get("context", {}).get("epic") == ""` for the default, then assert `"${context.epic}" in init_action` for the branch reference, then assert the `ll-issues list --parent` substring is present in `init_action`.
- A byte-identical regression test should also live in `scripts/tests/test_rn_implement.py:TestInitAndInputValidation` (lines 33-83) asserting that when `context.epic=""`, the resulting `queue.txt` is byte-identical to the pre-change init for the same comma-separated INPUT. The `init` action's body must still produce the same file output when `EPIC` is empty (per the BUG-2003 canonicalization preservation rule).
- The existing test at `scripts/tests/test_fsm_fragments.py:1015-1032` already runs `load_and_validate` over `rn-implement.yaml` — the new context var will be picked up transparently (no edit needed there).
- The `BUILTIN_LOOPS_DIR` fixture (`scripts/tests/test_builtin_loops.py:25`) and the `data` fixture pattern (`yaml.safe_load(self.LOOP_FILE.read_text())`) are the structural-test scaffolding already used; no new fixtures needed.
- For end-to-end verification (step 8), the dry-run path may need a real EPIC with children in `.issues/epics/`. The nearest real example is `EPIC-2457` (alignment-to-raw-event-transformation) which has child issues with `parent: EPIC-2457` frontmatter — but it has no `epic-XXXX.json` decision file, so it may not be wired. Operators should pick an EPIC with `status: open` AND `parent:`-linked children to verify.

## Impact

- **Priority**: P3 — completes the EPIC-as-input ergonomics for the orchestrator; doesn't unblock a current bottleneck but removes a recurring workflow friction.
- **Effort**: Small — ~25-line YAML edit (one context var + one branch in `init`) + one new test class + docs updates. Reuses `ll-issues list --parent` and the existing comma-separation pattern from ENH-2658.
- **Risk**: Low — purely additive; existing direct-ID and `auto_prove_learning_gate` paths are untouched. Edge risk: an EPIC with zero children aborts `init` (per the `ERROR` branch in the proposed code); this is a clear failure mode that mirrors the existing empty-INPUT abort at line 100-103.
- **Breaking Change**: No — direct ID input and `--context KEY=VALUE` overrides continue to work; `--context epic=` is opt-in.

## Scope Boundaries

- **Out of scope**: auto-detect EPIC type from bare input (e.g. `ll-loop run rn-implement "EPIC-2457"` auto-resolves to children). The proposed solution uses an explicit `--context epic=EPIC-XXX` flag to avoid surprising behavior (an operator passing an EPIC ID for `auto-decompose` would now silently get its children instead of the decompose path). Explicit > implicit here; auto-detect can be a follow-on if the ergonomics warrant it.
- **Out of scope**: changes to `ll-issues list --parent` semantics (e.g. transitive grandchild walking). The flag reuses the existing primitive.
- **Out of scope**: changes to `rn-decompose` — the `auto-decompose` path (case 1 in the Summary) continues to work as today for bare-EPIC input.
- **Out of scope**: a `--feature` / `--epic-set` DSL for arbitrary groupings. The minimal `--epic` covers the canonical use case; richer filters can be follow-on.

## Success Metrics

- A user can run `ll-loop run rn-implement --context epic=EPIC-2457` and have all the EPIC's `parent:`-linked children dequeued in one invocation, with cross-child `blocked_by:` deps honored and the same cycle detection as direct-ID input.
- The empty-`epic=""` path produces byte-identical behavior to the pre-change `init` for any comma-separated INPUT that existed before this change.
- The `run_dir/summary.json` shape is unchanged (children are still individually tracked in `per_issue`).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Orchestration layers / FSM loop architecture; relevant for `rn-implement` placement |
| `docs/guides/LOOPS_REFERENCE.md` | `rn-implement` usage section; needs the `--epic` example added |
| `docs/development/TROUBLESHOOTING.md` | May reference loop resolution patterns; verify no breakage |
| `.claude/CLAUDE.md` | `## Commands & Skills` / Loop Authoring sections; reference for the `--context KEY=VALUE` shape |

## Labels

`enhancement`, `loops`, `fsm`, `rn-implement`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-07-16T21:18:19 - `1512fb58-0770-4096-8672-0f98fe62b48f.jsonl`
- `/ll:refine-issue` - 2026-07-16T21:06:10 - `3875a64d-5808-46b9-81ae-98b6d0d858c2.jsonl`
- `/ll:capture-issue` - 2026-07-16T20:52:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b1f5f4d-99ee-4158-9ffa-3dfb5dc76405.jsonl`

## Status

**Open** | Created: 2026-07-16 | Priority: P3
