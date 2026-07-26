---
id: BUG-2827
type: BUG
priority: P3
status: open
captured_at: '2026-07-26T06:40:00Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels:
- loops
- shell
- autodev
- summary
relates_to:
- BUG-2826
---

# BUG-2827: `grep -c ... || echo 0` yields a two-line count, breaking every summary counter

## Summary

Across 7 built-in loops (25 sites) counters are computed as:

```bash
COUNT=$(echo "$IDS" | grep -c '[^[:space:]]' || echo 0)
```

`grep -c` **prints its count and then exits 1 when the count is zero**. The
`|| echo 0` therefore fires *in addition to* grep's own `0`, and the variable is
assigned the two-line string `"0\n0"` rather than `0`. Every downstream use of
that variable then fails: `printf '%d'` rejects it as an invalid number, and
`[ "$COUNT" -gt 0 ]` errors with `integer expected`.

The `|| echo 0` was presumably written for the missing-file case — and there it
works, because `grep -c` on a nonexistent file prints nothing and exits 2. It is
the *empty-but-valid* case, which is the common one, that produces the double
value.

## Current Behavior

From the `finalize_done` state of run `.loops/runs/autodev-20260726T011116/`
(stderr captured in the run's events JSONL):

```
bash: line 29: printf: 0
0: invalid number
bash: line 31: [: 0
0: integer expected
bash: line 34: [: 0
0: integer expected
bash: line 37: [: 0
0: integer expected
```

The summary still rendered — `Passed (0)` / `Skipped (1)` — because `printf`
emits the first line before erroring and the failing `[` tests are inside `if`
guards whose sections happened to be empty anyway. So the defect is currently
**latent**: noisy stderr, and three conditional sections whose guards evaluate
by accident rather than by arithmetic.

Affected files and site counts:

| File | Sites |
|---|---|
| `scripts/little_loops/loops/recursive-refine.yaml` | 13 |
| `scripts/little_loops/loops/autodev.yaml` | 5 |
| `scripts/little_loops/loops/auto-refine-and-implement.yaml` | 2 |
| `scripts/little_loops/loops/rn-build.yaml` | 2 |
| `scripts/little_loops/loops/dead-code-cleanup.yaml` | 1 |
| `scripts/little_loops/loops/rn-refine.yaml` | 1 |
| `scripts/little_loops/loops/rl-coding-agent.yaml` | 1 |

Two variants exist and fail differently:

- `echo "$VAR" | grep -c ...` — broken whenever `$VAR` is empty (i.e. whenever
  the bucket is empty), which is the normal case for most buckets.
- `grep -c ... FILE 2>/dev/null || echo 0` — correct when the file is *missing*
  (exit 2, no stdout), broken when the file exists with no matching lines.

## Steps to Reproduce

```bash
$ EMPTY=""
$ COUNT=$(echo "$EMPTY" | grep -c '[^[:space:]]' || echo 0)
$ printf '%d\n' "$COUNT"
bash: printf: 0
0: invalid number
$ printf '%q\n' "$COUNT"
$'0\n0'
```

Or observe it end-to-end: run `ll-loop run autodev <ID>` on any issue that does
not populate every bucket and read the `finalize_done` stderr in the run's
events JSONL.

## Expected Behavior

Counters hold a single integer in every case — file missing, file empty, file
populated — so `printf '%d'` and `[ -gt ]` behave arithmetically rather than by
accident, and no spurious stderr is emitted.

## Impact

Currently latent: spurious stderr on most loop runs, and three `if` guards in
`autodev.yaml`'s summary whose conditions error rather than evaluate (a failing
`[` is treated as false, which happens to match the intended behaviour for an
empty bucket). No data loss and no wrong exit codes observed. The cost is
mainly that the reporting path is arithmetically unsound and the idiom is
replicated 25 times, so it propagates into every new loop written by example.

## Status

Open — not started. Root cause confirmed (`grep -c` prints `0` *and* exits 1 on
no matches) and all 25 call sites enumerated; no fix attempted.

## Motivation

Individually harmless, but it is a correctness landmine sitting in the reporting
path of the loops operators rely on to know what happened. The guards it breaks
(`INFRA_SKIPPED_COUNT`, `GATE_BLOCKED_COUNT`, `DECISION_UNRESOLVED_COUNT` in
`autodev.yaml`) are exactly the ones that surface *actionable* buckets — a `[`
that errors is treated as false, so a populated bucket could be suppressed if the
count string were ever malformed for a non-zero value. It also trains the pattern
into new loops: 25 copies already exist, and each one is a template for the next.

## Proposed Solution

Replace the idiom with one that cannot emit two values. Options, cheapest first:

1. **Count lines, don't grep-count**, e.g.
   `COUNT=$(printf '%s\n' "$IDS" | grep -c '[^[:space:]]' || true)` still has the
   dual-write problem — instead assign unconditionally and normalize:
   `COUNT=$(grep -c '[^[:space:]]' <<<"$IDS"); COUNT=${COUNT:-0}` with the
   pipeline's exit status ignored rather than branched on.
2. **Prefer a form whose exit status is irrelevant**, such as
   `COUNT=$(printf '%s' "$IDS" | grep -c '[^[:space:]]' 2>/dev/null); : "${COUNT:=0}"`.
3. Whatever form is chosen, apply it to **all 25 sites** — a one-file fix leaves
   the pattern alive and copy-pasted.
4. Consider a `ll-loop validate` lint for `grep -c ... || echo` so the idiom
   cannot re-enter the codebase, in the spirit of the existing MR-* shell rules
   (MR-7/MR-9/MR-10 already police shell shapes in loop YAML).

Note the FSM interpolates the whole action string before bash sees it, so any
replacement must keep `${...}` escaping consistent with the surrounding lines.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/loops/{recursive-refine,autodev,auto-refine-and-implement,rn-build,rn-refine,dead-code-cleanup,rl-coding-agent}.yaml` | replace all 25 counter sites |
| `scripts/little_loops/fsm/validation.py` | optional lint rule for the idiom |
| `scripts/tests/test_builtin_loops.py` | assert no loop YAML contains `grep -c` piped into `|| echo` |
