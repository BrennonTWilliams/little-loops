---
id: BUG-2302
type: BUG
priority: P2
status: open
captured_at: '2026-06-25T18:00:00Z'
discovered_date: 2026-06-25
discovered_by: cross-repo-audit
relates_to:
- ENH-1665
- ENH-1917
labels:
- bug
- loops
- fsm
- evaluators
- error-classification
- cua
---

# BUG-2302: CUA loop never fast-fails on LLM auth failure; `output_contains` + `on_error` is a dead-code class

## Summary

When the LLM backing `cua-agent-desktop.yaml`'s `plan` state returns an HTTP
`401`/`403` (expired/invalid token), the process **succeeds** but its output
text lacks the expected `"commands"` pattern. The `output_contains` evaluator
returns `"no"` (never `"error"`), so the FSM routes through
`_route_plan_verdict` → `_route_plan_verdict2` → back to `plan` in an unbounded
loop, capped only by `max_steps: 50`. The `on_error: _handle_plan_error` path —
the only place that classifies and back-offs — is **unreachable** for this
failure mode because it fires solely on exceptions/timeouts, not on a process
that *runs* and returns error text.

Net effect: an entire run is wasted retrying a condition retrying cannot fix.
No new token appears mid-run, so every iteration re-fails identically until
`max_steps` or a `BrokenPipe` crash.

This was surfaced by a downstream `qa-pipeline` audit in the **cards** repo
(their BUG-357, closed "Won't Do — Upstream"). The fix belongs here because
`cua-agent-desktop.yaml` is a little-loops **library loop**. The cards decision
record (ARCHITECTURE-042) was scoped to *their* constraints and is **not**
imported verbatim — see "Decision" below.

## Root Cause (verified against little-loops `main`, 2026-06-25)

Three independent gaps, all confirmed in this repo:

### 1. The dead-code trap in `cua-agent-desktop.yaml`

```
scripts/little_loops/loops/cua-agent-desktop.yaml
  plan (L321-326):
    evaluate: output_contains '"commands"'
    on_yes: execute_action
    on_no:  _route_plan_verdict      ← 401/403 output lands here
    on_error: _handle_plan_error     ← UNREACHABLE for auth (no exception)
  _route_plan_verdict (L328): output_contains '"complete": true' → on_no: _route_plan_verdict2
  _route_plan_verdict2 (L337): output_contains '"error": "'      → on_no: plan   ← UNBOUNDED
```

`_handle_plan_error` (L802) has a working `plan_error_max` counter, but it only
sees `on_error` (exit-code/exception) failures — never auth-error *output*.

### 2. `output_contains` cannot return `"error"` (class-level defect)

`evaluate_output_contains` (`scripts/little_loops/fsm/evaluators.py:312`,
verdict set at L341/343) returns only `"yes"`/`"no"`. Contrast
`evaluate_exit_code` / `evaluate_output_numeric` / `evaluate_output_json`,
which **do** emit `"error"`. Consequence: **any** loop state pairing
`output_contains` with an `on_error` handler has the same latent trap — if the
action runs but emits unexpected/error output, `on_error` is bypassed. This is
not unique to the CUA loop.

### 3. `classify_failure()` has no auth concept

`classify_failure()` (`scripts/little_loops/issue_lifecycle.py:54`) recognizes
quota/`429`, network, timeout, and server-error/`529` patterns, but **none** of
`401`, `403`, `unauthorized`, `forbidden`, `authentication`, `invalid api key`,
`expired token`. Auth failures fall through to the default `(REAL,
"Implementation error")` — so `ll-auto`/`ll-parallel` misfile an expired token
as a real code bug. Worse, the type system only has `TRANSIENT` and `REAL`:
auth is **neither** — retrying won't help (unlike `TRANSIENT`) and it is not a
code bug (unlike `REAL`).

## Evidence (from cards run `2026-06-25T023634`)

| Count | Signature | Should be |
|-------|-----------|-----------|
| 6 | `401` | non-recoverable (auth) |
| 2 | `403` | non-recoverable (forbidden) |
| 6 | `529` | retryable (already handled) |

`.plan_errors.log` recorded only the generic "Plan LLM API error or timeout"
label; the inner `cua-agent-desktop` sub-loop hit `failed` after 29 iterations
with the run stopping mid-`plan`.

## Decision: full systemic fix (3 parts), decoupled from cards' contract

Cards selected a YAML-only Option A that writes
`cua_claims.json {"terminal_state":"unavailable"}` and rejected a Python/
evaluator fix for "cross-repo blast radius." **Both premises invert here:**

- We own the package and the release — the evaluator-level fix is *more*
  available to us, not blocked.
- `cua-agent-desktop.yaml` writes **no** `cua_claims.json` today (verified — the
  marker is a cards `qa-pipeline` contract). Baking it into this
  general-purpose library loop would couple the core to one downstream
  consumer. Our loop reaching a clean terminal with a **classified**
  `.plan_errors.log` entry is sufficient; cards' own
  `cua_unavailable_skip`/`check_plan_errors` wiring stays at *its* layer.

Scope chosen: **all three** parts below.

## Implementation Plan

### Part 1 — Loop-local fast-fail (no cards coupling)

In `cua-agent-desktop.yaml`, intercept auth signatures on the `plan` failure
path. Add a `_check_plan_auth_failure` state (grep captured plan output for
`401|403|unauthorized|forbidden`) inserted ahead of `_route_plan_verdict`, and
an abort state that:

- logs a **classified** entry to `.plan_errors.log`
  (e.g. `Plan LLM auth failure (401/403) at iteration N`), and
- routes to an existing terminal (`failed` / `diagnose`) — **not** a new
  `cua_claims.json` writer.

Place the check on the `on_no` branch (auth output never contains `"commands"`,
so it reliably lands there). Consider folding the same classification into
`_handle_plan_error` so exception-path auth errors are labelled too.

### Part 2 — Make `output_contains` able to surface error output (the lever)

Give the FSM a way to route error-*output* to `on_error`. Preferred: an
optional `error_patterns` field on the `output_contains` evaluator (or
state-level) that, when matched, yields `verdict="error"`. Keep default
behavior unchanged (no `error_patterns` → today's yes/no). This closes the
dead-code class for every loop, not just CUA.

- Touch points: `evaluate_output_contains` (`fsm/evaluators.py:312`), the
  evaluator schema (`fsm/fsm-loop-schema.json`, `fsm/schema.py`), and
  validation (`fsm/validation.py`).
- Backward-compat: existing loops with `output_contains` + `on_error` keep
  working; they simply gain reachability of `on_error` when they declare
  `error_patterns`.

### Part 3 — `classify_failure()` auth + `NON_RECOVERABLE`

In `issue_lifecycle.py`:

- Add a `FailureType.NON_RECOVERABLE` member (retry cannot help, not a code
  bug). Update `classify_failure()` to return it for
  `401`/`403`/`unauthorized`/`forbidden`/`authentication`/`invalid api key`/
  `expired token`.
- Audit callers of `classify_failure()` / `FailureType` so the new category
  routes to a terminal/skip path rather than (a) retrying like `TRANSIENT` or
  (b) filing a bug like `REAL`. **Enumerate every `FailureType` switch before
  adding the member** — a missed branch silently falls into a default.

## Files to Modify

| Part | File | Change |
|------|------|--------|
| 1 | `scripts/little_loops/loops/cua-agent-desktop.yaml` | Add `_check_plan_auth_failure` + abort state; classified `.plan_errors.log`; route to existing terminal (no `cua_claims.json`) |
| 2 | `scripts/little_loops/fsm/evaluators.py:312` | `error_patterns` → `verdict="error"` in `evaluate_output_contains` |
| 2 | `scripts/little_loops/fsm/fsm-loop-schema.json`, `fsm/schema.py`, `fsm/validation.py` | Schema + validation for `error_patterns` |
| 3 | `scripts/little_loops/issue_lifecycle.py:54` | `FailureType.NON_RECOVERABLE` + auth patterns; update callers |

## Acceptance Criteria

- [ ] Expired/invalid token → CUA `plan` aborts within **one** iteration to a
      terminal state (no 29× retry).
- [ ] `.plan_errors.log` shows a **classified** auth entry, not the generic
      "Plan LLM API error or timeout" label.
- [ ] `cua-agent-desktop.yaml` writes **no** `cua_claims.json` (decoupling
      preserved).
- [ ] `output_contains` with `error_patterns` returns `"error"` and reaches
      `on_error`; without it, behavior is byte-for-byte unchanged.
- [ ] `classify_failure("...401...", ...)` → `NON_RECOVERABLE`; every
      `FailureType` consumer handles the new member.
- [ ] `529`/timeout still retries under the existing `plan_error_max` path.
- [ ] Valid-token path unaffected.
- [ ] `ll-loop validate cua-agent-desktop` passes; new states are reachable.
- [ ] `pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_evaluators.py scripts/tests/test_fsm_validation.py` green; add a regression for auth fast-fail and for `error_patterns`.

## Provenance

- cards BUG-357 findings: `rn-bug-357-cua-auth-failure-findings.md` (repo root)
- cards decision: ARCHITECTURE-042 (cards `.ll/decisions.yaml`) — scoped to
  cards; **not** imported. Decoupling rationale per the general-purpose
  library-loop principle.
- Closure commit (cards): `19bf612`
