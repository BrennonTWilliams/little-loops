---
id: BUG-2981
title: autodev check_impl_auth leaks the inflight sentinel, and finalize_done double-counts the same issue as unverified
type: BUG
priority: P2
status: open
discovered_date: '2026-08-01'
discovered_by: audit-loop-run
relates_to:
- BUG-2908
- ENH-2353
labels:
- autodev
- loops
- fsm
decision_needed: false
testable: true
---

# BUG-2981: `autodev` `check_impl_auth` leaks `autodev-inflight`, and `finalize_done` double-counts the same issue as unverified

## Summary

Two coupled defects in `scripts/little_loops/loops/autodev.yaml`, found while
auditing an `autodev` run that finished with an `inflight_at_finalize` verdict.

1. **D1** — `check_impl_auth` is the only state on `implement_current`'s failure
   chain that routes onward without clearing `${context.run_dir}/autodev-inflight`.
   Every sibling failure/skip state clears it. This is the direct cause of the
   `inflight_at_finalize` verdict on a run whose implementation merely failed.
2. **D2** — `finalize_done` writes the same issue ID into
   `autodev-unverified.txt` twice (once bare, once suffixed
   `inflight_at_finalize`), and the `sort -u` that would collapse them cannot,
   because the suffix differs. `UNVERIFIED_COUNT` reports 2 for one issue.

They are filed together because D1 masks D2: fixing D1 removes the *instance*
(no residual sentinel → no second write) without fixing the double-count, which
still fires on any other path that leaves a sentinel behind.

## Current Behavior

**D1.** `check_impl_auth` (`autodev.yaml:877-885`):

```yaml
  check_impl_auth:
    fragment: ll_auto_auth_check
    on_yes: abort_env_not_ready
    on_no: dequeue_next
    on_error: dequeue_next
```

It is a `fragment:` state, so it has no `action` body of its own and cannot
clear the sentinel. Both non-auth legs (`on_no` — a genuine implementation
failure; `on_error` — a fault reading the auth signal) fall through to
`dequeue_next` with `autodev-inflight` still holding the current issue ID.

Every sibling on the same chain does clear it — `autodev.yaml:349`, `:420`,
`:439`, `:862` (`mark_gate_blocked`, immediately upstream via
`check_learning_gate`'s `on_yes`). `check_impl_auth` is the sole hole.

`dequeue_next` overwrites the sentinel with the next issue (`:99`), so the leak
is invisible mid-run; it only surfaces when the failing issue is the **last**
one dequeued, leaving a residual sentinel at `finalize_done`.

**D2.** `finalize_done` writes the unverified bucket in two places:

- `autodev.yaml:1968-1978` — for each staged ID whose status is not
  `done|completed|cancelled`, `echo "$ID" >> autodev-unverified.txt` (bare ID).
- `autodev.yaml:2029-2032` — the BUG-2908 residual-sentinel check:

  ```bash
  if [ -n "$INFLIGHT" ] && ! grep -qxF "$INFLIGHT" ${context.run_dir}/autodev-passed.txt 2>/dev/null; then
    ABANDONED=1
    echo "$INFLIGHT  inflight_at_finalize" >> ${context.run_dir}/autodev-unverified.txt
  fi
  ```

The guard checks only `autodev-passed.txt`. An issue that was staged, failed to
close, and left a residual sentinel is by construction in **both** paths: the
staged loop already wrote it bare, then this appends it suffixed. The
`sort -u` at `:2033-2034` sees `FEAT-108` and `FEAT-108  inflight_at_finalize`
as distinct lines, so `UNVERIFIED_COUNT` (`:2035`) counts one issue twice.

## Expected Behavior

- **D1** — `check_impl_auth`'s non-auth legs clear `autodev-inflight` before
  reaching `dequeue_next`, matching every sibling failure/skip state. A run
  whose last issue merely failed implementation finalizes with no residual
  sentinel and no `abandoned` signal.
- **D2** — one issue contributes at most 1 to `UNVERIFIED_COUNT`, whichever
  path recorded it. The `inflight_at_finalize` reason is still visible on the
  line, not lost to dedup.

## Steps to Reproduce

**D1:**

1. Run `autodev` over a queue whose **last** issue fails implementation for a
   non-auth reason (`ll-auto --only` exits non-zero, no
   `LEARNING_GATE_BLOCKED` marker, auth configured).
2. `check_learning_gate` → `on_no` → `check_impl_auth` → `on_no` →
   `dequeue_next` → queue empty → `finalize_done`.
3. `cat <run_dir>/autodev-inflight` → still holds the failed issue ID.
4. Run summary reports `abandoned` / `inflight_at_finalize` for an issue that
   was not abandoned mid-flight — it failed and was correctly drained past.

**D2:** with the same run, `grep -c FEAT-NNN <run_dir>/autodev-unverified.txt`
→ 2; the summary's `Unverified (N)` count is inflated by one per affected issue.

## Root Cause

**D1** is a fragment-state gap. `check_impl_auth` was added by ENH-2353 to split
auth failures from genuine implementation failures. Because it is expressed as
`fragment: ll_auto_auth_check` it carries no `action`, and the sentinel-clearing
convention — an `rm -f ${context.run_dir}/autodev-inflight` line inside each
terminal-ish state's own action body — has no place to live. The convention is
enforced only by repetition across ~20 sites, not by structure, so a state with
no action body silently opts out.

**D2** is an incomplete guard. BUG-2908 Step 4 added the residual-sentinel fold
so an abandoned issue feeds the verdict rather than being an invisible advisory.
Its guard asks "was this issue already recorded as passed?" but the bucket it
writes into is the *unverified* one, so the correct question is "was this issue
already recorded **at all**?" The suffix that makes the reason legible is also
what defeats `sort -u`.

## Program Design

YAML-only change to one loop file plus tests. No Python.

**D1** — add a clearing state between `check_impl_auth`'s non-auth legs and
`dequeue_next`, rather than pointing both legs at an existing sibling. A
dedicated state keeps the auth-vs-implementation distinction that ENH-2353
introduced (the two legs mean different things and a future fix may want to
record them differently) and gives the structural test below a named target.

Routing after the fix:

```
check_impl_auth
  on_yes:   abort_env_not_ready      (unchanged)
  on_no:    clear_inflight_after_impl_failure  -> dequeue_next
  on_error: clear_inflight_after_impl_failure  -> dequeue_next
```

The new state's action is the same `rm -f` one-liner the siblings use, with
`next: dequeue_next` and `on_error: dequeue_next` (a failed `rm -f` must not
strand the queue).

**D2** — widen the guard at `:2030` to check the unverified bucket as well:

```bash
if [ -n "$INFLIGHT" ] \
   && ! grep -qxF "$INFLIGHT" ${context.run_dir}/autodev-passed.txt 2>/dev/null \
   && ! grep -qE "^${INFLIGHT}([[:space:]]|$)" ${context.run_dir}/autodev-unverified.txt 2>/dev/null; then
```

`ABANDONED=1` must still be set independently of whether the line is appended —
it is a verdict input (`:2076`, `:2080`), and an issue already in the unverified
bucket that *also* left a sentinel is still an abandonment. Only the duplicate
`echo` is suppressed.

### Call Path

- `scripts/little_loops/loops/autodev.yaml:877-885` — `check_impl_auth`,
  reroute `on_no`/`on_error`
- `scripts/little_loops/loops/autodev.yaml` — new
  `clear_inflight_after_impl_failure` state, adjacent to `check_impl_auth`
- `scripts/little_loops/loops/autodev.yaml:2029-2032` — widen the residual-
  sentinel guard; keep `ABANDONED=1` outside the append condition
- `scripts/little_loops/loops/autodev.yaml:99` — `dequeue_next`'s sentinel
  write (unchanged; the reason the leak is normally invisible)

## Implementation Steps

1. Add `clear_inflight_after_impl_failure` and repoint `check_impl_auth`'s
   `on_no`/`on_error`.
2. Widen the `finalize_done` guard; hoist `ABANDONED=1` above the append.
3. Add the two behavioral tests (below).
4. Add the structural test (below).
5. `ll-loop validate autodev` and `python -m pytest scripts/tests/test_builtin_loops.py`.

## Test Plan

The shell-execute-a-state's-action pattern already exists —
`test_builtin_loops.py:4452-4472` (`test_skip_inflight_*`) writes a temp
`run_dir`, substitutes `${context.run_dir}` and any `${captured.*}` refs into
the action string, runs it under `bash -c`, and asserts on both exit code and
the resulting files. Both behavioral tests follow it directly:

- **D1** — seed `run_dir/autodev-inflight` with an ID, execute
  `clear_inflight_after_impl_failure`'s action, assert exit 0 and
  `not (run_dir / "autodev-inflight").exists()`.
- **D2** — seed `autodev-unverified.txt` with a bare `FEAT-0001`, seed
  `autodev-inflight` with `FEAT-0001`, execute `finalize_done`'s action, assert
  the ID appears on exactly one line and that the summary JSON still carries
  `abandoned` truthy.

**Structural test (the one that prevents the next hole).** D1 is the second
sentinel leak of its kind; a test asserting only that `check_impl_auth` is fixed
would not have caught it in advance. Add a test that walks every state
reachable from `implement_current` along failure/skip routes
(`on_no`/`on_error`/`next`, stopping at `dequeue_next`, `finalize_done`, and
`abort_env_not_ready`) and asserts each either clears `autodev-inflight` in its
own action or routes only to states that do. Fragment states with no action
body are exactly what the walk must flag, since they cannot clear it themselves.

## Acceptance Criteria

- [ ] `check_impl_auth`'s `on_no` and `on_error` reach `dequeue_next` only via a
      state that clears `autodev-inflight`
- [ ] A run whose last issue fails implementation for a non-auth reason
      finalizes with no residual sentinel and no `abandoned` signal
- [ ] One issue contributes at most 1 to `UNVERIFIED_COUNT`, with the
      `inflight_at_finalize` reason still visible
- [ ] `ABANDONED` is still set when a residual sentinel names an issue already
      in the unverified bucket
- [ ] Structural test covers every state on `implement_current`'s failure chain
- [ ] `ll-loop validate autodev` passes; `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Impact

**Who is affected:** anyone running `autodev` over a queue where the last
issue fails implementation for a non-auth reason — the common case when a
backlog's tail contains a hard issue.

**What breaks:** the run reports `phantom` with an `abandoned` signal, which is
a stronger claim than the truth ("dispatched but never accounted for" vs.
"failed and correctly drained past"). Operators triaging a `phantom` verdict go
looking for a lost issue that was never lost. D2 compounds it by inflating
`UNVERIFIED_COUNT`, so a one-issue failure reads as two.

**Why it matters beyond cosmetics:** `ABANDONED` is a verdict input
(`autodev.yaml:2076-2082`), so D1 changes the run's verdict, not just its
prose. BUG-2908 hardened this predicate specifically so unverified work could
not be laundered into a pass; D1 pushes the error the other way, manufacturing
an abandonment signal from an ordinary failure. Both directions erode trust in
the verdict.

**Blast radius:** contained to `autodev`. `rn-remediate` has the parallel
learning-gate/auth ordering but its own sentinel handling; it should be checked
against the structural test once that test exists, but no defect is claimed
there.

## Scope Boundaries

**In scope:** `check_impl_auth`'s two non-auth legs; the `finalize_done`
residual-sentinel guard; tests for both plus the structural walk.

**Out of scope:**

- The remedy text on the Unverified line — filed as ENH-2982; it changes
  summary output other tooling reads.
- The `fragment:`-states-cannot-clear-the-sentinel design issue in general.
  The structural test surfaces any other instance, but converting the
  clear-the-sentinel convention into a schema-level guarantee is a larger FSM
  change and is not attempted here.
- `rn-remediate` and other loops with `ll_auto_auth_check` call sites — no
  defect verified, not changed.

## Notes

Found by `/ll:audit-loop-run` on an `autodev` run that reported an
`inflight_at_finalize` verdict. D3 from the same audit — `finalize_done`'s
unconditional "re-queue to retry" remedy text being wrong for a deterministic
`ready-issue` NOT_READY — is filed separately as an ENH, since it changes
summary output that other tooling reads.

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
