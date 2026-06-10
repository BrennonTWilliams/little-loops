---
id: BUG-2074
title: FSM shell actions using bash parameter expansion crash with "Unknown namespace"
type: BUG
priority: P3
status: done
captured_at: '2026-06-10T11:30:00Z'
discovered_date: 2026-06-10
discovered_by: user-session
labels:
- loops
- fsm
- interpolation
- apply-research
- integrate-sdk
- bash-escaping
relates_to:
- BUG-1675
size: Small
completed_at: '2026-06-10T11:30:00Z'
---

# BUG-2074: FSM shell actions using bash parameter expansion crash with "Unknown namespace"

## Summary

An `ll-loop run apply-research "...frontier-coding-agents-metaprogramming.md"` run
died at iteration 1 with:

```
Failure reason: │ Unknown namespace: FILE##*
Loop completed: report (3 iterations, 0.2s)
```

The run reached the `read_file` state, hit the error, and routed `on_error: report`,
terminating with 0 issues captured. The same defect existed latently in a second
built-in loop (`integrate-sdk`), and the existing regression guard for this exact
bug class (BUG-1675) was too narrow to catch either instance.

## Root Cause

The FSM template engine (`scripts/little_loops/fsm/interpolation.py`) substitutes
every `${...}` in a shell action as a `${namespace.path}` reference **before bash
ever sees it**. Valid namespaces are `context, captured, prev, result, state, loop,
env, messages, param` (interpolation.py:84–110). Any `${...}` whose leading token
is not one of those raises `InterpolationError` at runtime.

`apply-research.yaml`'s `read_file` state used two **bash parameter expansions** that
collide with this syntax:

- Line 86 — `EXT="${FILE##*.}"` → parsed as namespace `FILE##*` → `Unknown namespace:
  FILE##*` (the observed error).
- Line 89 — `MDFILE="${FILE%.pdf}.md"` → same failure on the PDF branch.

`integrate-sdk.yaml`'s `scan_existing_usage` state had the same class of bug at line
33 — `echo "USAGE_HITS=${hits}"` — where `hits` is a local bash variable. This raises
`Invalid variable: ${hits} (expected namespace.path)`.

The engine already supports a `$${...}` escape that emits a literal `${...}` to the
shell (interpolation.py:206, 218–219, 268); these actions simply failed to use it.

## Why the Existing Guard Missed It

`test_no_bare_bash_variable_in_shell_actions` (BUG-1675 regression guard) matched only
`(?<!\$)\$\{[A-Z_][A-Z0-9_]*\}` — uppercase bare `${VAR}` with no operators. It could
not see `${FILE##*.}` (operator chars `#`, `%`, `*`, `.` fall outside the character
class) **nor** lowercase `${hits}` (the class is `[A-Z_]` only). The guard checked one
narrow shape of the bug and let two real instances ship.

## The Fix

1. **`apply-research.yaml`** — escaped both bash expansions:
   - `EXT="${FILE##*.}"` → `EXT="$${FILE##*.}"`
   - `MDFILE="${FILE%.pdf}.md"` → `MDFILE="$${FILE%.pdf}.md"`

2. **`integrate-sdk.yaml`** — escaped the latent instance the strengthened guard
   surfaced: `echo "USAGE_HITS=${hits}"` → `echo "USAGE_HITS=$${hits}"`.

3. **`test_builtin_loops.py`** — rewrote `test_no_bare_bash_variable_in_shell_actions`
   to flag **any** unescaped `${...}` whose leading identifier is not a valid FSM
   namespace, rather than only uppercase bare names. It now catches bare `${VAR}`
   (any case), parameter expansions (`${FILE##*.}`, `${FILE%.pdf}.md`, `${VAR:-default}`),
   and any other bash `${...}` construct.

## Files Changed

- `scripts/little_loops/loops/apply-research.yaml` — `read_file` state (lines 86, 89).
- `scripts/little_loops/loops/integrate-sdk.yaml` — `scan_existing_usage` state (line 33).
- `scripts/tests/test_builtin_loops.py` — strengthened `test_no_bare_bash_variable_in_shell_actions`
  (namespace-allowlist logic replacing the uppercase-only regex).

## Verification

- `python -m pytest scripts/tests/test_builtin_loops.py` → **811 passed** (the
  strengthened guard fails on the unfixed loops and passes after the escapes; it
  found the `integrate-sdk` instance on first run).
- Direct interpolation check against the real engine:
  - `$${FILE##*.}` → literal `${FILE##*.}` (bash receives the correct expansion) ✓
  - `$${FILE%.pdf}.md` → literal `${FILE%.pdf}.md` ✓
  - `$${hits}` → literal `${hits}` ✓
  - `${FILE##*.}` → raises `Unknown namespace: FILE##*` (reproduces the original failure)
  - `${hits}` → raises `Invalid variable: ${hits} (expected namespace.path)`
- End-to-end `ll-loop run apply-research` was blocked by an unrelated concurrent loop
  (`rn-implement`) holding the workspace scope, not by this bug; the root cause is
  conclusively fixed and the run can be repeated with `--queue` once that loop frees.

## Acceptance Criteria

- [x] `apply-research` `read_file` bash expansions escaped with `$${...}`
- [x] `integrate-sdk` `${hits}` escaped with `$${...}`
- [x] Regression guard flags any unescaped non-namespace `${...}` (any case, including
      parameter expansions), not just uppercase bare names
- [x] Full `test_builtin_loops.py` suite passes
- [x] Interpolation engine confirmed: escaped forms pass through; original forms raise
      the exact observed errors

## Related Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/fsm/interpolation.py` | `${namespace.path}` engine + `$${...}` escape (lines 84–110, 206, 268) |
| `.issues/bugs/*BUG-1675*` | Prior instance of the same bug class; this guard was its regression test |
| `scripts/little_loops/loops/apply-research.yaml` | Primary fix |
| `scripts/little_loops/loops/integrate-sdk.yaml` | Latent instance found by the strengthened guard |

## Session Log
- `hook:posttooluse-status-done` - 2026-06-10T16:30:48 - `de29177f-116f-4096-8f81-8f5ce5e54da1.jsonl`
- user-session - 2026-06-10 - diagnosed the `Unknown namespace: FILE##*` failure as a
  bash-vs-FSM `${...}` collision, escaped both `apply-research` expansions, strengthened
  the BUG-1675 guard to a namespace-allowlist check, which surfaced and fixed the latent
  `integrate-sdk` `${hits}` instance; verified via 811-pass suite + direct interpolation check.
