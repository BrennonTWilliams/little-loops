---
captured_at: "2026-04-21T16:34:42Z"
completed_at: "2026-04-21T17:01:37Z"
discovered_date: 2026-04-21
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1230: autodev skips implementation when size review declines decomposition

## Summary

When `/ll:issue-size-review --auto` declines to decompose an issue (returns "skipped" because the issue is already leaf-sized or effort is small), the `enqueue_or_skip` state in `autodev.yaml` unconditionally marks the issue as skipped without checking whether it passes confidence/outcome thresholds. Issues that are ready to implement are silently dropped instead of being passed to `implement_current`.

## Current Behavior

After `run_size_review` completes and no child issues are created, `enqueue_or_skip`'s `else` branch (line 380-382 of `autodev.yaml`) always executes:

```sh
echo "${captured.input.output}" >> .loops/tmp/autodev-skipped.txt
echo "Skipped: ${captured.input.output} (no further decomposition possible)"
```

The issue is written to `autodev-skipped.txt` and the loop moves to `dequeue_next`. No score check is performed. `implement_current` is never reached.

## Expected Behavior

When `enqueue_or_skip` finds no children (size review declined to decompose), it should perform a final score check — mirroring the logic in `recheck_scores`. If the issue passes `readiness_threshold` and `outcome_threshold` at that point, it should route to `implement_current`. Only if scores still fail should it mark the issue as skipped.

## Motivation

This caused FEAT-1228 (Parallel State Outer-CLI Awareness and Warnings, confidence 93/100) to be silently skipped during an autodev run. The size review correctly identified the issue as not needing decomposition ("effort is genuinely small"), but the FSM had no path back to implementation from that determination. Users must manually re-queue or implement such issues, defeating the purpose of the autodev loop.

## Steps to Reproduce

1. Run `ll-loop run autodev "FEAT-XXXX"` on an issue that:
   - Does not pass refinement thresholds going into `run_size_review`
   - Is declined for decomposition by `/ll:issue-size-review --auto` (score high by heuristic but effort genuinely small)
2. Observe the autodev summary: the issue appears in `Skipped`, not `Passed`.
3. Check `ll-issues show FEAT-XXXX --json`: confidence and outcome scores may already meet thresholds by this point.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `enqueue_or_skip` state, `else` branch (the no-children path)
- **Cause**: The `else` branch assumes "no children = no further progress possible = skip". It does not distinguish between "issue is too large to implement but can't decompose further" and "issue is leaf-sized and ready to implement". A score re-check is needed in the no-children path before deciding to skip.

## Proposed Solution

Add a final score check in `enqueue_or_skip`'s `else` branch (no-children path). If scores meet thresholds, write to `autodev-passed.txt` and exit with a signal that routes to `implement_current`. If scores fail, proceed with the existing skip.

Option A — modify `enqueue_or_skip` shell action to emit a distinct exit code and split routing:

```yaml
enqueue_or_skip:
  fragment: shell_exit          # already used for if/else routing
  on_yes: implement_current     # scores passed → implement
  on_no: dequeue_next           # no children, scores failed → skip
```

The shell action's `else` branch would become a Python score-check (same pattern as `recheck_scores`) that exits 0 on pass / 1 on fail.

Option B — add a new `recheck_after_size_review` state between `enqueue_or_skip` and `dequeue_next`, reusing the existing `recheck_scores` Python block. The `enqueue_or_skip` else-branch clears inflight and routes to this new state; the new state routes to `implement_current` or `dequeue_next`.

Option B is lower-risk: it keeps `enqueue_or_skip`'s shell action as `action_type: shell` (no fragment change) and isolates the new check in a dedicated state.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `enqueue_or_skip` state (else branch) and/or new `recheck_after_size_review` state

### Dependent Files (Callers/Importers)
- N/A — `autodev.yaml` is a self-contained FSM loop

### Similar Patterns
- `recheck_scores` state in `autodev.yaml` — exact Python score-check pattern to reuse
- `check_passed` state in `autodev.yaml` — same score-check logic, alternative reference

### Tests
- `scripts/tests/test_builtin_loops.py:TestAutodevLoop` (lines 1009-1293) — all autodev FSM structural and routing tests; new routing assertions for `recheck_after_size_review` belong here, following the pattern at lines 1182-1210

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests to update:**
- `scripts/tests/test_builtin_loops.py:1268` — `test_enqueue_or_skip_clears_autodev_inflight`: docstring says "either decomposed or skipped" but after the fix inflight clearing moves to `recheck_after_size_review` for the skip path; string `"autodev-inflight"` still appears in `enqueue_or_skip.action` (children-found branch) so assertion technically still passes, but docstring and comment must be corrected [Agent 3 finding]

**New tests to write** (follow routing assertion pattern at lines 1182-1210):
- `test_enqueue_or_skip_uses_shell_exit_fragment` — assert `state.get("fragment") == "shell_exit"` for `enqueue_or_skip` [Agent 3 finding]
- `test_enqueue_or_skip_on_yes_routes_to_dequeue_next` — assert `state.get("on_yes") == "dequeue_next"` (children-found path) [Agent 3 finding]
- `test_enqueue_or_skip_on_no_routes_to_recheck_after_size_review` — assert `state.get("on_no") == "recheck_after_size_review"` (no-children path) [Agent 3 finding]
- `test_recheck_after_size_review_uses_shell_exit_fragment` — assert `state.get("fragment") == "shell_exit"` [Agent 3 finding]
- `test_recheck_after_size_review_on_yes_routes_to_implement_current` — assert `state.get("on_yes") == "implement_current"` [Agent 3 finding]
- `test_recheck_after_size_review_on_no_routes_to_dequeue_next` — assert `state.get("on_no") == "dequeue_next"` [Agent 3 finding]
- `test_recheck_after_size_review_clears_autodev_inflight` — assert `"autodev-inflight" in action` for new state (inflight cleared on skip path) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:452-455` — FSM flow diagram shows `enqueue_or_skip → dequeue_next` as unconditional on both the children-found and `run_size_review` paths; must interpose `recheck_after_size_review` on the no-children path [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:460` — in-flight tracking paragraph states "`enqueue_or_skip` and `enqueue_children` clear it on resolution"; after the fix `enqueue_or_skip` only clears inflight in the children-found branch — clearing on the skip path moves to `recheck_after_size_review` [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Choose Option A or Option B** (recommendation: Option B for lower risk — see below for concrete steps for Option B)

2. **Modify `enqueue_or_skip`** (`autodev.yaml:338-389`):
   - Add `fragment: shell_exit` — the state currently uses `action_type: shell` with `next: dequeue_next` (unconditional). To add conditional routing, `fragment: shell_exit` must be added; this injects `evaluate.type: exit_code` so `sys.exit(0)` → `on_yes` and `sys.exit(1)` → `on_no`
   - Remove `next: dequeue_next`; add `on_yes: dequeue_next` (children-found path) and `on_no: recheck_after_size_review` (no-children path)
   - In the **children-found branch** (`if [ -s .loops/tmp/autodev-new-children.txt ]`): add `exit 0` at end of branch; move `rm -f .loops/tmp/autodev-inflight` into this branch
   - In the **no-children branch** (else): remove `echo "${captured.input.output}" >> .loops/tmp/autodev-skipped.txt`; do NOT clear inflight here (let `recheck_after_size_review` handle it); add `exit 1`
   - Remove the unconditional `rm -f .loops/tmp/autodev-inflight` at line 386 (it currently runs outside both branches, wiping inflight before `recheck_after_size_review` can preserve it for `implement_current`)

3. **Add new `recheck_after_size_review` state** (insert after `enqueue_or_skip`): copy the Python block verbatim from `recheck_scores` (`autodev.yaml:288-318`) and adapt:
   - On pass: write to `autodev-passed.txt`, exit 0 — do NOT clear `autodev-inflight` (mirrors `recheck_scores` behavior; `dequeue_next` overwrites it after `implement_current`)
   - On fail: write to `autodev-skipped.txt`, `Path('.loops/tmp/autodev-inflight').unlink(missing_ok=True)`, exit 1
   - Routing: `fragment: shell_exit`, `on_yes: implement_current`, `on_no: dequeue_next`, `on_error: dequeue_next`

4. **Update `test_builtin_loops.py:TestAutodevLoop`** (lines 1009-1293) with new routing assertions, following the pattern at lines 1182-1210:
   - `enqueue_or_skip.on_yes == "dequeue_next"` (children-found path)
   - `enqueue_or_skip.on_no == "recheck_after_size_review"` (no-children path)
   - `recheck_after_size_review.on_yes == "implement_current"`
   - `recheck_after_size_review.on_no == "dequeue_next"`
   - `"autodev-inflight" in recheck_after_size_review.action` (inflight cleared on skip path)
   - Update `test_required_states_exist` to include `"recheck_after_size_review"`

5. **Run tests**: `python -m pytest scripts/tests/test_builtin_loops.py::TestAutodevLoop -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_GUIDE.md:452-455` — revise FSM flow diagram to show `recheck_after_size_review` interposed between `enqueue_or_skip` and `dequeue_next` on the no-children / `run_size_review` path
7. Update `docs/guides/LOOPS_GUIDE.md:460` — revise in-flight tracking paragraph to say `enqueue_or_skip` clears inflight only on the children-found path; `recheck_after_size_review` clears it on the skip path

## Impact

- **Priority**: P2 — Autodev silently fails to implement ready issues; users must notice the skip in the summary and re-queue manually
- **Effort**: Small — Adds one state or a minor branch reusing existing Python block
- **Risk**: Low — FSM-only change; no Python package changes; isolated to the no-children path in `enqueue_or_skip`
- **Breaking Change**: No

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — FSM loop guide including `shell_exit` fragment and state routing patterns
- `.issues/completed/P2-BUG-1183-autodev-skips-parent-after-breakdown-signal-no-children.md` — prior fix for a related no-children handling bug; shows how `enqueue_or_skip` was modified before and adds context on the inflight-clearing pattern at line 386
- `.issues/completed/P2-ENH-1018-skip-size-review-when-scores-already-pass.md` — the feature that added `recheck_scores` as a gate before `run_size_review`; establishes the score-recheck pattern this fix reuses

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**State locations in `autodev.yaml`:**
- `enqueue_or_skip`: lines 338-389 — uses `action_type: shell` with `next: dequeue_next` (unconditional, no `fragment: shell_exit`). Conditional routing requires adding `fragment: shell_exit` and explicit `exit 0` / `exit 1` calls in the two branches
- `recheck_scores`: lines 282-323 — primary Python score-check pattern to reuse verbatim; uses `fragment: shell_exit`, `on_yes: implement_current`, `on_no: run_size_review`
- `check_passed`: lines 121-163 — identical Python block, alternative reference; `on_yes: implement_current`, `on_no: detect_children`
- `implement_current`: line 165-175 — does NOT clear `autodev-inflight`; routes `next: dequeue_next`
- `dequeue_next`: lines 54-89 — overwrites `autodev-inflight` at line 71 (`printf '%s' "$CURRENT" > .loops/tmp/autodev-inflight`)

**Critical inflight detail:**
- The `rm -f .loops/tmp/autodev-inflight` at line 386 of `enqueue_or_skip` sits OUTSIDE the if/else, executing for both the children-found and no-children branches. For the `recheck_after_size_review` → `implement_current` path to preserve the inflight issue ID (consistent with the existing `recheck_scores` → `implement_current` path), this line must be moved into the children-found branch (if-block) and removed from the unconditional position. The new state handles clearing on the skip path.

**`fragment: shell_exit` definition:**
- `scripts/little_loops/loops/lib/common.yaml:15-22` — contributes `action_type: shell` and `evaluate.type: exit_code`; state must supply `action`, `on_yes`, `on_no`

**Test class location:**
- `scripts/tests/test_builtin_loops.py:TestAutodevLoop` (lines 1009-1293) — all autodev structural/routing tests. Routing assertion pattern at lines 1182-1210 is the template for new assertions. `test_required_states_exist` at line ~1019 must be updated to include `"recheck_after_size_review"`

## Labels

`automation`, `fsm`, `autodev`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-21T16:58:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40a31a98-3e00-4d84-8027-117ae4b9e3c2.jsonl`
- `/ll:confidence-check` - 2026-04-21T17:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2155dd42-ebcd-49ce-8574-83d280807475.jsonl`
- `/ll:wire-issue` - 2026-04-21T16:51:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d581d6a5-d731-4e65-99a4-4272affef8b4.jsonl`
- `/ll:refine-issue` - 2026-04-21T16:42:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/737eff25-6b1e-4b65-81b1-dc9954bf803e.jsonl`
- `/ll:format-issue` - 2026-04-21T16:36:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/64f366b3-49e5-473b-b710-925e21463a2f.jsonl`

- `/ll:capture-issue` - 2026-04-21T16:34:42Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24aea90c-410b-44e1-8768-f887bdf017e4.jsonl`

---

## Resolution

Added `recheck_after_size_review` state (Option B) between `enqueue_or_skip` and `dequeue_next`. When size-review declines to decompose an issue, the new state performs the same Python score check used by `recheck_scores`. Issues that pass thresholds route to `implement_current`; issues that fail write to `autodev-skipped.txt`, clear `autodev-inflight`, and route to `dequeue_next`. The `rm -f autodev-inflight` in `enqueue_or_skip` was moved into the children-found branch (exit 0) so the inflight ID is preserved through to `implement_current` on the pass path.

**Closed** | Created: 2026-04-21 | Completed: 2026-04-21 | Priority: P2
