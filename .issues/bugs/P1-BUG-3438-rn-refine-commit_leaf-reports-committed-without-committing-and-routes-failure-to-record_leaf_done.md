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
---

# BUG-3438: rn-refine commit_leaf reports COMMITTED without committing and routes failure to record_leaf_done

## Summary

commit_leaf (rn-refine.yaml ~602-616) has no set -e and ends in `|| true`, so a failed `git commit` (no identity, pre-commit reject, index lock) still echoes COMMITTED, exits 0, and writes the pre-leaf HEAD to leaf-baseline-commit.txt. Worse, its on_error already routes to record_leaf_done, which marks the leaf `verified`, so `set -euo pipefail` alone is insufficient: the error path must go to record_failure (or a new record_leaf_commit_failed state). Audit sibling actions for the same `echo SUCCESS; ... || true` shape. Test: give the ephemeral repo an explicit git identity (hermetic) and add a failing-commit case asserting non-zero exit and no COMMITTED marker (B2).

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
- `commit_leaf`'s error path routes to `record_failure` (leaf lands in `failed_nodes.txt`, `[FAILED] <nid>`) — or a new `record_leaf_commit_failed` state with equivalent semantics — never to `record_leaf_done`.
- Sibling states with the same swallow shape (`capture_baseline`'s `|| : > file` producing an empty baseline; `verify_leaf`'s `|| true` producing an empty touched-files list) are audited and either fixed or filed as follow-ups.

## Steps to Reproduce

1. Create an ephemeral repo: `git init` + one committed file (the baseline), then modify/add a file so `git add -A` stages a change.
2. Make the commit deterministically fail: hide the git identity (`GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null`, no repo-local `user.name`/`user.email`) → `git commit` exits 128 with "Please tell me who you are". (A pre-commit hook exiting 1 works equally.)
3. Run the rendered `commit_leaf` action (the `_render`/`_bash` pattern from `scripts/tests/test_rn_refine.py::TestFinalizeSafety`) with `captured.run_dir.output` pointing at a run dir and `captured.input.output` = a node id.
4. Observe: exit code 0; stdout contains `COMMITTED <nid>`; `leaf-baseline-commit.txt` holds the pre-leaf HEAD; downstream `record_leaf_done` writes `leaf_impl_<nid>.txt` = `verified` with the changes still uncommitted.

## Root Cause

- **File**: `scripts/little_loops/loops/rn-refine.yaml`
- **Anchor**: `states.commit_leaf.action` (and its `on_error` routing edge)
- **Cause**: The shell action has no `set -e`/`pipefail`; `echo "COMMITTED"` is not conditioned on commit success; the trailing `git rev-parse HEAD ... || true` both swallows its own failure and guarantees an exit-0 tail; and `on_error: record_leaf_done` maps any surfaced failure onto the verified-marker state.

## Proposed Solution

Rewrite the `commit_leaf` action with an explicit failure surface:

```bash
set -euo pipefail
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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml` — `commit_leaf` action body + `on_error` edge; possible sibling touch-ups (`capture_baseline`, `verify_leaf`).

### Dependent Files (Callers/Importers)
- FSM executor consumes the YAML (`scripts/little_loops/fsm/executor.py`); `ll-loop validate` (`scripts/little_loops/fsm/validation/`) re-validates on change — keep the `ll-lint: mr11-ok(...)` comments intact.
- Package data: the YAML ships inside `scripts/little_loops/loops/` — no mirror/host-adapted copy exists for loops.

### Similar Patterns
- `record_deviation` / `record_leaf_done` / `record_failure` states for marker-file conventions; `TestFinalizeSafety` in the test file for the render-and-run action-testing pattern.

### Tests
- `scripts/tests/test_rn_refine.py` — new test class (e.g. `TestCommitLeafSafety`) using `_render`/`_bash`: hermetic identity-failure case (assert non-zero exit, no `COMMITTED`, baseline not advanced), happy path with an explicit repo-local git identity (`git config user.email/user.name` so it doesn't depend on the machine's global identity), and routing assertions (`fsm.states["commit_leaf"].on_error == "record_failure"`).
- `scripts/tests/test_builtin_loops.py` references rn-refine — confirm no assumptions about the old routing.

### Documentation
- N/A (loop-internal behavior; `docs/` doesn't document commit_leaf semantics).

### Configuration
- N/A.

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

1. Rewrite `commit_leaf` action with `set -euo pipefail` and unconditional baseline write on the success path only.
2. Reroute `commit_leaf.on_error` to `record_failure` (or add `record_leaf_commit_failed`).
3. Audit/fix sibling swallow shapes (`capture_baseline`, `verify_leaf`) or file follow-up issues.
4. Add `TestCommitLeafSafety` cases: identity-failure, happy path with explicit identity, routing assertions.
5. Verify: `python -m pytest scripts/tests/test_rn_refine.py scripts/tests/test_builtin_loops.py` and `ll-loop validate rn-refine`.

## Impact

- **Priority**: P1 - Silent data-integrity failure in the stepwise implement loop: failed commits masquerade as verified leaves and misattribute changes to subsequent leaf commits.
- **Effort**: Small - One action rewrite, one routing edge, one focused test class; established render/run test pattern to follow.
- **Risk**: Low - Narrows a swallow-all path; the `NO_CHANGES` passthrough and success path are preserved verbatim.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P1


## Session Log
- `/ll:format-issue` - 2026-09-10T21:55:58 - `82016d7d-cfd1-41eb-a02d-fdc1a376c905.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
