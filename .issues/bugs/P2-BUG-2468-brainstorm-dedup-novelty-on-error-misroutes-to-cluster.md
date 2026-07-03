---
id: BUG-2468
title: "brainstorm dedup_novelty `on_error: cluster` misroutes real crashes as 'no novel ideas'; produces zero artifacts while reporting Loop completed: done"
type: BUG
status: open
priority: P2
captured_at: '2026-07-02T23:30:00Z'
discovered_date: '2026-07-02'
discovered_by: manual
relates_to:
- ENH-2251
- ENH-2356
- ENH-2444
labels:
- bug
- brainstorm
- loops
- fsm
- silent-data-loss
- error-routing
- on-error-misroute
---

# BUG-2468: brainstorm dedup_novelty `on_error: cluster` misroutes real crashes as 'no novel ideas'; produces zero artifacts while reporting Loop completed: done

## Summary

The `dedup_novelty` state in the `brainstorm` built-in loop declares
`on_error: cluster` (the same destination as `on_no: cluster`). Combined
with the `exit_code` evaluator's mapping of any non-zero exit to either
`verdict=no` (exit 1) or `verdict=error` (exit 2+), this means a real
Python crash inside the heredoc that exits with code 1 — which is what
uncaught `SyntaxError`, `IndentationError`, `KeyError`, etc. produce
by default — is indistinguishable from "dedup found zero novel ideas."

## Steps to Reproduce

1. **Trigger a Python crash inside the `dedup_novelty` heredoc.** The simplest reproducible trigger is a `captured.round_ideas.output` payload whose parsed contents cause a runtime exception in the existing dedup logic (e.g., a payload that decodes to a non-dict where a dict is expected, raising `AttributeError`; or a payload containing a literal `"""` substring that prematurely terminates the triple-quoted `raw = """..."""` assignment, raising `SyntaxError`). The exact trigger varies by payload, but the crash path is identical: any uncaught exception → Python exits 1 → FSM misroutes.
2. **Run the loop:** `ll-loop run brainstorm "What changes should the next version of our design document include?"`.
3. **Observe:** the loop traverses `init → frame → pop_lens → diverge → dedup_novelty → cluster → rank → converge → route_sink → done` in 9 iterations. `dedup_novelty` exits in ~200 ms with `exit_code=1` and `output_preview=null` (stderr is not surfaced — see ENH-2469).
4. **Inspect the artifacts** in `.loops/runs/<instance-id>/`:
   - `ideas.jsonl` is 0 bytes (the 5 IDEAS_JSON objects emitted by `diverge` were captured into `captured.round_ideas.output` but never written to disk).
   - `brainstorm.md` is 0 bytes.
   - `clusters.md` and `winners.md` do not exist.
   - `ranked.md` exists and contains an honest refusal-to-fabricate diagnostic.
5. **Read the run summary:** `Loop completed: done (9 iterations, 3m 2s)` — green check, success color.

The user observes success. The data is gone.

The same trigger can be reproduced deterministically in unit tests by feeding a malformed `captured.round_ideas.output` directly into the `dedup_novelty` action without invoking the full loop.
Downstream states (`cluster`, `rank`, `converge`) operate on an empty
`ideas.jsonl`, refuse to fabricate, and report success. The user sees
`Loop completed: done (N iterations, Xm Ys)` with `ideas.jsonl`,
`brainstorm.md`, `clusters.md`, and `winners.md` all empty or missing.

This is **silent data loss** for every brainstorm run where the
Python heredoc crashes on parsing the LLM-emitted `IDEAS_JSON` payload.

## Motivation

The user invoked
`ll-loop run brainstorm "What changes should the next version of our design document include?"`
against a target repo. The loop completed in 3m 2s, reported
`Loop completed: done (9 iterations, 3m 2s)`, and produced **zero
usable artifacts**. The user's question was never answered.

This is not "the loop ran but produced nothing useful" — it is "the
loop ran, internally crashed, and the user was told it succeeded."

Detailed diagnosis in `.loops/reviews/brainstorm-20260702-225858-failure.md`.

## Root cause

`scripts/little_loops/loops/brainstorm.yaml:124-198` — `dedup_novelty` state:

```yaml
dedup_novelty:
  fragment: parse_tagged_json
  action: |
    python3 << 'PYEOF'
    import json, sys, difflib
    raw = """${captured.round_ideas.output}"""
    # ... parse IDEAS_JSON, dedup via difflib, append to ideas.jsonl ...
    PYEOF
  evaluate:
    type: exit_code
  on_yes: saturation_gate
  on_no: cluster
  on_error: cluster      # ← THIS LINE — on_error routes to cluster, not failed
```

The `exit_code` evaluator (`scripts/little_loops/fsm/evaluators.py:155-174`) maps:
- `exit_code=0` → verdict=yes → `on_yes: saturation_gate`
- `exit_code=1` → verdict=no → `on_no: cluster`
- `exit_code=2+` → verdict=error → `on_error: cluster`

A real Python crash inside the heredoc — e.g., `SyntaxError` from a malformed substitution, `KeyError` from a missing dict key, `IndentationError` from whitespace handling — produces `exit_code=1` (Python's default for uncaught exceptions). This is **indistinguishable** from "the script ran successfully but found zero novel ideas" (also `exit_code=1` by design).

After `on_no → cluster`, the downstream states all see an empty `ideas.jsonl`. They complete the LLM call that asks "given empty input, what do you say?" — and the LLM, to its credit, refuses to fabricate. They exit `exit_code=0` (they successfully answered the prompt). The FSM never sees a real error. The terminal `done` state is reached via `route_sink → done`.

The user sees: 3 minutes of work, `Loop completed: done`, `ideas.jsonl` 0 bytes, `brainstorm.md` 0 bytes, `clusters.md` does not exist, `winners.md` does not exist, and `ranked.md` contains a diagnostic explaining "No ranking produced — source inputs are empty."

## Current Behavior

`dedup_novelty` (and `saturation_gate`) treat any non-zero exit as "no novel ideas," routing to `cluster`. A Python heredoc crash in `dedup_novelty` is misclassified as legitimate saturation. The loop completes with `Loop completed: done` and zero artifacts.

This is the failure observed in run `brainstorm-20260702-225858` against a target repo. Detailed diagnosis in `.loops/reviews/brainstorm-20260702-225858-failure.md`.

## Expected Behavior

1. A Python crash in `dedup_novelty` produces a **structured exit code** that distinguishes "I ran successfully and found zero novel ideas" from "I crashed." The current `exit 1` path conflates them.
2. The `dedup_novelty` state's `on_error` route goes to a terminal state that signals failure — `failed`, not `cluster`. A real crash should never silently route to the convergence path.
3. Downstream states (`cluster`, `rank`, `converge`) operate on real input, not on the silent aftermath of an upstream crash.
4. The terminal `done` state asserts `brainstorm.md` is non-empty (artifact invariant). An empty artifact set triggers routing to `failed`.

## Proposed Solution

### Fix 1 — Distinct exit codes in `dedup_novelty`

Replace the current `sys.exit(0)` / `sys.exit(1)` semantics with three explicit exit codes:

| Exit code | Meaning | Route |
|---|---|---|
| `sys.exit(0)` | At least one novel idea added | `on_yes: saturation_gate` |
| `sys.exit(1)` | All ideas were duplicates (legitimate saturation) | `on_no: cluster` |
| `sys.exit(2)` | Uncaught exception / script-level error | `on_error: failed` |

The `exit_code` evaluator already maps `exit_code=2+` to `verdict=error`, which routes via `on_error`. **No evaluator changes needed** — only the YAML route must change.

### Fix 2 — Wrap heredoc in try/except

The heredoc at `brainstorm.yaml:130-193` has no exception handling. An uncaught exception in the script is the trigger for this bug. Wrap the body:

```python
python3 << 'PYEOF'
import json, sys, difflib
try:
    raw = """${captured.round_ideas.output}"""
    # ... existing logic ...
except Exception as e:
    print(f"ERROR in dedup_novelty: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(2)
PYEOF
```

This makes any crash visible to the operator AND routed to the `failed` terminal state.

### Fix 3 — `done`-state artifact invariant

Add a sanity check before declaring success:

```yaml
done:
  action_type: shell
  action: |
    if [ ! -s "${captured.run_dir.output}/brainstorm.md" ]; then
      echo "ERROR: brainstorm.md is empty — loop completed without producing artifacts"
      exit 2
    fi
    # ... existing summary action ...
  evaluate:
    type: exit_code
  on_yes: <existing-prompt-summary>
  on_no: failed
  on_error: failed
```

This catches the case where upstream states (somehow) return `exit_code=0` but the artifacts are missing.

## Acceptance Criteria

- [ ] `dedup_novelty` exits with code 2 on any uncaught exception. Verified by injecting a malformed `captured.round_ideas.output` (e.g., `raw = """{not valid json`"""`) and observing exit code 2 + stderr message.
- [ ] `dedup_novelty.on_error` routes to `failed`, not `cluster`. Verified by reading the YAML and by simulating the loop.
- [ ] A real `dedup_novelty` crash results in the FSM terminating in `failed`, not `done`. Verified by `ll-loop simulate` or a unit test that asserts the terminal state.
- [ ] `done` state aborts to `failed` if `brainstorm.md` is empty or missing. Verified by `ll-loop simulate` with an empty artifact dir.
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_brainstorm.py -v`.
- [ ] `ll-loop validate brainstorm` reports clean validation (no new warnings).

## Implementation Steps

1. Edit `scripts/little_loops/loops/brainstorm.yaml:124-198`:
   - Replace `sys.exit(0)` and `sys.exit(1)` semantics with the three exit codes from Fix 1.
   - Wrap the heredoc body in `try/except` (Fix 2).
   - Change `on_error: cluster` → `on_error: failed`.
2. Edit `scripts/little_loops/loops/brainstorm.yaml:360-375` (`done` state):
   - Add the artifact-invariant shell check (Fix 3).
3. Update `scripts/tests/test_brainstorm.py` to add tests for:
   - `dedup_novelty` exits 2 on parse failure.
   - `dedup_novelty.on_error: failed` is correctly defined.
   - `done` state aborts on empty `brainstorm.md`.
4. Run `python -m pytest scripts/tests/test_brainstorm.py -v` to confirm green.
5. Run `ll-loop validate brainstorm` to confirm clean validation.

## References

- `scripts/little_loops/loops/brainstorm.yaml:124-198` — `dedup_novelty` state (target of fix)
- `scripts/little_loops/loops/brainstorm.yaml:360-375` — `done` state (target of artifact invariant)
- `scripts/little_loops/loops/brainstorm.yaml:377+` — `failed` terminal state (where crashes should route)
- `scripts/little_loops/loops/brainstorm.yaml:200-212` — `saturation_gate` state (adjacent: also has `on_error: cluster`, but the bug here is on `dedup_novelty`; saturation_gate's misroute only fires if the numeric evaluator itself errors, which is rare)
- `scripts/little_loops/fsm/evaluators.py:155-174` — `evaluate_exit_code`: `exit_code=2+` already maps to `verdict=error`, which routes via `on_error`. No evaluator change needed.
- **ENH-2251** — Harden brainstorm loop resilience and handoff. **This is the design origin of the misroute.** ENH-2251 added `on_error: cluster` to `saturation_gate` and `dedup_novelty` (line 45 of ENH-2251) as deliberate "resilience" routing. It correctly routed `frame`/`diverge`/`converge` errors to `failed`, but the `dedup_novelty` / `saturation_gate` decision turned out to misclassify crashes as legitimate saturation. The fix to `dedup_novelty`'s `on_error` was missing from that change.
- **ENH-2356** — brainstorm saturation/novelty gate inert. Distinct from this bug: ENH-2356 is about the saturation counter never firing because difflib is too lax; this bug is about the heredoc crashing and the failure being misclassified. They share the saturation path but have separate root causes.
- **ENH-2444** — Per-state tools allowlist. Unrelated to error routing, but worth cross-referencing because ENH-2444 fixed the `diverge` state's WebSearch problem — the same kind of "soft prompt instruction" vs "hard structural enforcement" distinction.
- `.loops/reviews/brainstorm-20260702-225858-failure.md` — Detailed failure investigation. The source diagnosis for this bug.

## Impact

- **Priority**: P2 — Silent data loss for every brainstorm invocation that triggers the heredoc crash path. Currently 100% reproducible.
- **Effort**: Small. The fix is ~15 lines of YAML plus a try/except wrapper.
- **Risk**: Low. The new exit codes are backward-compatible (existing scripts exit 0 or 1, both still route correctly). The `done` state artifact invariant adds an early-exit on empty artifacts, which is a tightening — existing healthy runs produce non-empty `brainstorm.md`, so the invariant never fires.
- **Breaking Change**: No. The change is purely additive on the error path; happy-path runs are unaffected.

## Status

Open | Created: 2026-07-02 | Priority: P2 | Type: BUG