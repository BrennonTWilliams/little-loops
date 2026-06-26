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
decision_needed: false
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

## Current Behavior

When the LLM returns HTTP 401/403 for the `plan` state, the subprocess exits
with code 0 but output lacks the expected `"commands"` JSON key.
`evaluate_output_contains` returns `"no"` (never `"error"`), routing:
`_route_plan_verdict` → `_route_plan_verdict2` → `plan` — an unbounded loop
capped only at `max_steps: 50`. Each retry is identical; no new token arrives
mid-run. The `on_error: _handle_plan_error` branch (which has a working
`plan_error_max` counter) is never invoked because no exception is raised.

`classify_failure()` in `issue_lifecycle.py` has no auth-pattern recognition,
so it returns `(REAL, "Implementation error")` for 401/403 output — the same
classification as genuine code bugs — causing `ll-auto`/`ll-parallel` to misfile
an expired token as a code defect.

## Expected Behavior

An expired or invalid token causes the CUA `plan` state to abort within **one**
iteration to a terminal state (`failed` or `diagnose`). `.plan_errors.log` shows
a classified auth entry (e.g., `"Plan LLM auth failure (401/403) at iteration N"`).
`classify_failure()` returns a new `NON_RECOVERABLE` type for auth signatures,
which callers route to a terminal/skip path rather than retrying (like `TRANSIENT`)
or filing a bug (like `REAL`).

## Steps to Reproduce

1. Configure `cua-agent-desktop.yaml` with an expired or invalid LLM API token.
2. Run `ll-loop run cua-agent-desktop` on any task.
3. Observe the `plan` state iterating up to 50 times with identical 401/403 output.
4. Check `.plan_errors.log`: entry reads `"Plan LLM API error or timeout"` (generic), not `"auth failure"`.
5. Confirm `_handle_plan_error` was never invoked (no `plan_error_max` counter increment for auth path).

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

## Implementation Steps

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

**Part 2 — dispatcher wiring (critical, easy to miss):**
- Update `evaluate()` dispatcher in `scripts/little_loops/fsm/evaluators.py` at line 1568–1573: pass `error_patterns=config.error_patterns` when calling `evaluate_output_contains()`; the dataclass field addition alone is inert without this.

**Part 3 — `_cmd_scan_failures()` filter:**
- In `scripts/little_loops/cli/logs.py:1051`, extend `if failure_type == FailureType.TRANSIENT: continue` → `if failure_type in (FailureType.TRANSIENT, FailureType.NON_RECOVERABLE): continue` so auth failures are skipped in `ll-logs scan-failures` output.

**Documentation (add after all Python changes are tested):**
- `docs/guides/LOOPS_GUIDE.md:286` — update `output_contains` verdict column from `yes / no` to `yes / no / error (with error_patterns)`
- `docs/reference/API.md` — update `EvaluateConfig` dataclass listing (line 4587) and `evaluate_output_contains` signature (line 4694) to include `error_patterns`
- `docs/generalized-fsm-loop.md:643-659` — add `error_patterns` field to YAML example and `error` row to verdict table

**New tests (one per part; add before merge):**
- Part 1: `test_builtin_loops.py` — simulate CUA `plan` state with `"401"` output, assert single-iteration abort
- Part 2: `test_fsm_executor.py` — exit-0 + pattern-not-found + `error_patterns` match → `on_error`
- Part 3: `test_issue_manager.py` — `NON_RECOVERABLE` in `_process_single_issue()` routes to suppress path (not bug creation)
- Part 3: `test_cli_logs.py` or `test_issue_lifecycle.py` — `NON_RECOVERABLE` filtered in `_cmd_scan_failures()` (coverage gap; no corpus-based test exists today)

**Verify CUA YAML structure after Part 1:**
- `test_builtin_loops.py::test_all_validate_as_valid_fsm` must pass; if `_check_plan_auth_failure` references `_auth_failure_abort` which references `failed`, all three must be defined
- Check `test_all_failure_terminals_have_diagnostic_action` — `_auth_failure_abort` should emit a diagnostic echo (already in the code sketch) to satisfy this guard

---

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Part 1 — `.plan_errors.log` write template** (model after `_handle_plan_error` at `cua-agent-desktop.yaml:802`):
```yaml
_check_plan_auth_failure:
  action_type: shell
  action: |
    ABS_DIR="${captured.run_dir.output}"
    if echo "${captured.plan_output.output}" | grep -qiE '401|403|unauthorized|forbidden'; then
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Plan LLM auth failure (401/403) at iteration ${state.iteration}" \
        >> "$ABS_DIR/.plan_errors.log"
      echo "AUTH_FAILURE_DETECTED"
    else
      echo "NO_AUTH_FAILURE"
    fi
  evaluate:
    type: output_contains
    pattern: "AUTH_FAILURE_DETECTED"
  on_yes: _auth_failure_abort
  on_no: _route_plan_verdict

_auth_failure_abort:
  action_type: shell
  action: echo "Aborting: non-recoverable auth failure — see .plan_errors.log"
  on_yes: failed
```
Note: the `diagnose` state at `cua-agent-desktop.yaml:990` already reads `.plan_errors.log` into `diagnostics.md` — a classified entry will surface there automatically.

**Part 2 — `EvaluateConfig` + JSON Schema 4-location addition** (for `error_patterns`):
1. **`schema.py` field** (after `negate: bool = False` ~line 77): `error_patterns: list[str] | None = None`
2. **`schema.py` `to_dict()`**: `if self.error_patterns is not None: result["error_patterns"] = self.error_patterns`
3. **`schema.py` `from_dict()`**: `error_patterns=data.get("error_patterns")`
4. **`fsm-loop-schema.json`** inside `"properties"` of `evaluateConfig` (add near `negate` ~line 552–557):
   ```json
   "error_patterns": {
     "type": "array",
     "description": "Regex/substring patterns that, when matched in output, yield verdict='error' (output_contains only)",
     "items": { "type": "string" }
   }
   ```
   `additionalProperties: false` at ~line 649 means this MUST be inside `"properties"` or schema rejects loops using it.
5. **`validation.py`**: `EVALUATOR_REQUIRED_FIELDS` at line 68 only requires `pattern` for `output_contains`; no change needed unless `error_patterns` should be forbidden on other evaluator types.

**Part 2 — `evaluate_output_contains` insertion point** — current verdict logic at lines 340–343; insert before final return:
```python
# Check error_patterns before returning "no"
if not matched and error_patterns:
    for ep in error_patterns:
        if ep in output:  # or re.search(ep, output)
            return EvaluationResult(verdict="error", details={"error_pattern": ep, "pattern": pattern})
```
Model the `EvaluationResult(verdict="error", ...)` return on `evaluate_output_numeric:178-185`.

**Part 3 — auth pattern strings to add to `classify_failure()`** (lines 54–184):
```python
auth_patterns = [
    "401", "403", "unauthorized", "forbidden",
    "authentication", "invalid api key", "expired token",
    "invalid_api_key",
]
```
Match against `error_output.lower()`. Return `(FailureType.NON_RECOVERABLE, "Auth/credentials failure")`. Place this check before the `server_error_patterns` block (line ~133) since "api error" in `server_error_patterns` could match auth error text.

## Integration Map

### Files to Modify
| Part | File | Change |
|------|------|--------|
| 1 | `scripts/little_loops/loops/cua-agent-desktop.yaml` | Add `_check_plan_auth_failure` + abort state; classified `.plan_errors.log`; route to existing terminal (no `cua_claims.json`) |
| 2 | `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_contains` | `error_patterns` field → `verdict="error"` when matched |
| 2 | `scripts/little_loops/fsm/fsm-loop-schema.json`, `fsm/schema.py`, `fsm/validation.py` | Schema + validation for `error_patterns` |
| 3 | `scripts/little_loops/issue_lifecycle.py` — `classify_failure()`, `FailureType` | `FailureType.NON_RECOVERABLE` + auth patterns; update all callers |

### Dependent Files (Callers/Importers)
- All `FailureType` consumers in `scripts/little_loops/` — enumerate before adding new enum member (missed branch silently falls to default)
- `ll-auto`/`ll-parallel` orchestration code that branches on `classify_failure()` return value

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py` — imports from fsm modules; audit for any `FailureType` branches that must handle `NON_RECOVERABLE` (currently no direct import found, but verify before merging Part 3)
- `scripts/little_loops/fsm/types.py` — TYPE_CHECKING import of `EvaluateConfig` at line 14; `EvaluatorFunction` type alias at line 89 uses `EvaluateConfig` in its signature — backward-compat with new `error_patterns` field, no code change needed but verify after schema change

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Enumerated `FailureType` consumers** — all four must be audited for `NON_RECOVERABLE`:
- `scripts/little_loops/fsm/executor.py:1154-1178` — `_route()` calls `classify_failure()` **only when `action_result.exit_code != 0`**; auth failures in the CUA `plan` state exit with code 0 (CLI subprocess succeeds; error is in stdout text), so this site is bypassed for the primary scenario. Still update for auth failures that do produce non-zero exit. Current branches: TRANSIENT+rate-limit → `_handle_rate_limit()`; TRANSIENT+server-error → `_handle_api_error()`; else → reset counters. Add: NON_RECOVERABLE → immediate terminal (no retry, no bug filing).
- `scripts/little_loops/issue_manager.py:921-936` — `_process_single_issue()`: `if TRANSIENT` → suppress bug creation; else (implicitly REAL) → create bug. `NON_RECOVERABLE` must route to the suppress path (it is not a code bug). Add explicit `elif failure_type == FailureType.NON_RECOVERABLE` before the REAL fallthrough.
- `scripts/little_loops/cli/logs.py:1050-1052` — `_cmd_scan_failures()`: `if TRANSIENT: continue`. Extend to `if failure_type in (FailureType.TRANSIENT, FailureType.NON_RECOVERABLE): continue`.
- `scripts/little_loops/__init__.py:34,113` — re-exports `FailureType` and `classify_failure` as public API; no logic change needed, but the new enum member is automatically exported.

**Prior related bugs on the same evaluator** (review before implementing Part 2):
- `BUG-1640` — `output_contains` treated timeout as `"no"` (may now be handled by the `exit_code==124 → "error"` short-circuit at `evaluators.py:1508`)
- `BUG-1815` — `output_contains` routed non-zero exit to `on_no` instead of `on_error` (fixed by the `_EXIT_CODE_AWARE_EVALUATORS` short-circuit at `evaluators.py:1518-1536`). BUG-2302 is the exit-0 counterpart that the short-circuit cannot catch.

### Tests
- `scripts/tests/test_fsm_evaluators.py` — unit tests for `error_patterns` in `evaluate_output_contains`
- `scripts/tests/test_fsm_validation.py` — schema validation for new `error_patterns` field
- `scripts/tests/test_builtin_loops.py` — regression for auth fast-fail path in CUA loop
- New test: `classify_failure()` returns `NON_RECOVERABLE` for 401/403/unauthorized/forbidden text
- `scripts/tests/test_issue_lifecycle.py:TestClassifyFailurePatterns` (~line 634) — add Part 3 auth cases here; existing convention is `FailureType["NON_RECOVERABLE"]` string-key lookup for parametrize
- `scripts/tests/test_fsm_schema.py` — also update for `error_patterns` field acceptance/rejection
- `scripts/tests/test_fsm_evaluators.py:TestEvaluateDispatcher` (~line 471) — add a `test_output_contains_error_patterns_match` case alongside the existing `test_dispatch_nonzero_exit_generalized_short_circuit` parametrize

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — add: `test_output_contains_error_patterns_routes_to_on_error` (exit-0 + pattern-not-found + `error_patterns` match → `on_error`); follow the structure of `test_action_zero_exit_with_missing_pattern_still_routes_to_on_no` (~line 2402), which is the exact BUG-2302 scenario pre-fix and will remain SAFE (its mock output `"nope"` won't match auth patterns)
- `scripts/tests/test_issue_manager.py` — gap: no existing test covers `classify_failure`/`FailureType` branching in `_process_single_issue()`. Add: verify `NON_RECOVERABLE` routes to suppress path (not bug creation); follow pattern from `test_issue_lifecycle.py::TestClassifyFailure`
- `scripts/tests/test_builtin_loops.py::test_all_validate_as_valid_fsm` — will BREAK if new CUA YAML states have dangling target references; no test code change needed, but YAML must be structurally valid before merge
- `scripts/tests/test_builtin_loops.py::test_all_failure_terminals_have_diagnostic_action` — inspect whether `_auth_failure_abort → failed` triggers the "no diagnostic action before terminal" guard; may require a diagnostic echo-action in `_auth_failure_abort` (the issue sketch already includes one)
- **Coverage gap**: `scripts/little_loops/cli/logs.py:1050-1052` (`_cmd_scan_failures`) — the only existing test (`test_scan_failures_returns_0`) uses an empty corpus and never reaches the classification branch. Add: verify `NON_RECOVERABLE` failures are filtered (skipped) same as `TRANSIENT` in scan-failures output

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:286` — verdict table shows `output_contains` as `yes / no` only; update to `yes / no / error (when error_patterns set)` after Part 2 lands
- `docs/reference/API.md:4587` — `EvaluateConfig` dataclass docs: add `error_patterns: list[str] | None = None  # For output_contains: patterns that yield verdict="error"` after `negate`
- `docs/reference/API.md:4694-4698` — `evaluate_output_contains` function signature: add `error_patterns` parameter and update docstring to describe the three-verdict behavior
- `docs/generalized-fsm-loop.md:643-659` — `#### output_contains` section: add `error_patterns` field to YAML example and add `error` row to the verdict table

Note: `docs/reference/API.md` does NOT document `FailureType` or `classify_failure` — no doc update needed for Part 3.
Note: `docs/reference/CLI.md:627` lists `output_contains` as a valid MR-1 non-LLM evaluator — remains accurate, no change needed.

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `error_patterns` field definition (Part 2 schema change)

## Impact

- **Priority**: P2 — Wastes an entire run (up to 50 iterations) on a non-recoverable failure; misfiles auth errors as code bugs in `ll-auto`/`ll-parallel`, masking the real issue from operators
- **Effort**: Medium — Three independent parts, all touch points identified; Part 2 involves schema changes but is backward-compatible (no `error_patterns` → existing yes/no behavior unchanged)
- **Risk**: Low-Medium — Part 2 schema change affects all loops using `output_contains`, but backward-compat is explicitly preserved; Part 3 `FailureType` enum addition requires enumerating all switch sites before merging
- **Breaking Change**: No

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

## Status

**Open** | Created: 2026-06-25 | Priority: P2

## Provenance

- cards BUG-357 findings: `rn-bug-357-cua-auth-failure-findings.md` (repo root)
- cards decision: ARCHITECTURE-042 (cards `.ll/decisions.yaml`) — scoped to
  cards; **not** imported. Decoupling rationale per the general-purpose
  library-loop principle.
- Closure commit (cards): `19bf612`


## Session Log
- `/ll:wire-issue` - 2026-06-26T01:13:52 - `1d1f24c1-11ae-4edd-b18c-d140751e3f36.jsonl`
- `/ll:refine-issue` - 2026-06-26T01:04:47 - `f21b7294-6303-4dd4-9786-189804da8078.jsonl`
- `/ll:format-issue` - 2026-06-26T00:52:30 - `68368d4e-1eed-4865-91d4-e0d7215d922a.jsonl`
