---
id: ENH-2353
type: ENH
priority: P3
status: done
captured_at: '2026-06-27T21:58:52Z'
completed_at: '2026-06-29T23:26:27Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
relates_to:
- FEAT-1496
decision_needed: false
labels:
- captured
- loops
- fast-fail
- ll-auto
- host-compat
confidence_score: 98
outcome_confidence: 76
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 21
score_change_surface: 18
---

# ENH-2353: Auth-signature fast-fail for `ll-auto`-calling loops

## Summary

Loops that invoke `ll-auto` (notably `rn-remediate`'s `implement` state, plus
`autodev`, `eval-driven-development`, and `oracles/implement-issue-chain`) have
no detection for a host-auth failure. When the Anthropic/host auth is not
configured, `ll-auto` prints `Fatal error: Could not resolve authentication
method...` and exits non-zero, which the loop records as a generic
implementation failure. A batch then churns one issue after another (~60s each
on `ready-issue` before hitting the wall) and mislabels an environment
misconfiguration as N implementation failures.

Observed in `rn-implement` run `2026-06-27T210732`: 4 of 5 issues failed with an
identical auth `Fatal error`; the run reported `failed: 5` with no indication
the root cause was environmental (`rn-implement-audit-2026-06-27.md`,
Proposal #1).

## Motivation

- **Fast-fail**: abort the whole run on the first auth failure instead of
  burning ~60s × N issues to rediscover the same unconfigured environment.
- **Honest attribution**: an env/auth misconfig should be reported as
  `ENV_NOT_READY`, not laundered into the `failed` (implementation failure)
  bucket — this also feeds directly into BUG-2351's honest-failure verdict.

## Current Behavior

`rn-remediate.yaml` `implement` runs `ll-auto --only "$ID" 2>&1` and routes
solely on exit code (`on_no`/`on_error` → `emit_implement_failed`). An auth
`Fatal error` is indistinguishable from a real implementation failure, and the
parent (`rn-implement`) keeps dequeuing.

## Expected Behavior

Detect auth-failure signatures in the captured `ll-auto` output and emit a
distinct `ENV_NOT_READY` (or `AUTH_FAILED`) outcome that aborts the run with a
clear, actionable message ("No host auth configured — set the host credential or
run the host login, then re-run"). The parent should treat this terminally for
the whole queue, not per-issue.

## Scope Boundaries

- **In scope**: Runtime auth-signature detection from captured `ll-auto` output in the three active call sites (`rn-remediate:implement`, `autodev:implement_current`, `eval-driven-development:implement`); a new `ll_auto_auth_check` fragment in `lib/common.yaml`; `ENV_NOT_READY` terminal state that aborts queue processing.
- **Out of scope**: Host preflight / static env-probe checks — that is FEAT-1496's `ll-doctor` territory (done); this issue is the in-loop runtime complement.
- **Out of scope**: `oracles/implement-issue-chain.yaml` — file was never created (ENH-1874 implemented via delegation to `autodev`); only 3 call sites exist, not 4.
- **Out of scope**: Rate-limit handling (429s) — already covered by the existing `with_rate_limit_handling` fragment in `lib/common.yaml`.
- **Constraint**: Detection must be host-agnostic — grep output signatures only; do NOT hardcode `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` env probes (would violate `resolve_host()` abstraction and break non-Claude hosts).

## Proposed Solution

Reuse the established little-loops pattern from `cua-agent-desktop.yaml`
(`_check_plan_auth_failure`, BUG-2302): grep captured output for
`401|403|unauthorized|forbidden` plus the `ll-auto` auth string
(`could not resolve authentication`/`authentication method`).

Implementation approaches (pick during refinement):

1. **Shared lib fragment** (preferred — DRY across the 4 call sites): add an
   `auth_fast_fail` fragment under `loops/lib/` that wraps an `ll-auto` call,
   captures output, and routes to an `ENV_NOT_READY` emit on signature match.
   Apply it to `rn-remediate.implement`, `autodev`, `eval-driven-development`,
   and `oracles/implement-issue-chain`.

> **Selected:** Shared lib fragment — DRY cross-cutting auth guard fits `lib/common.yaml` pattern; 3/4 loops already import it; ties on overall score (9/12 each), wins on Consistency tiebreaker (3/3 vs 2/3).

2. **Inline guard** in `rn-remediate.implement` only (smaller blast radius,
   leaves the other three uncovered).

Keep it **host-agnostic**: detect the failure from output signatures, do NOT
hardcode `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` env probes (would violate
the `resolve_host()` abstraction and break for codex/opencode/pi). A genuinely
host-aware static probe is FEAT-1496's `ll-doctor` territory (done); this issue
is the in-loop runtime fast-fail that complements it.

Anchors: `rn-remediate.yaml` `implement`; `cua-agent-desktop.yaml`
`_check_plan_auth_failure` (reference pattern); `host_runner.py` `resolve_host`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CRITICAL: Auth pattern mismatch.** The existing `_check_plan_auth_failure` grep targets HTTP-layer auth errors from LLM API calls:
```bash
grep -qiE '401|403|unauthorized|forbidden'
```
`ll-auto`'s fatal credential error prints:
```
Fatal error: Could not resolve authentication method...
```
This string does NOT contain `401`, `403`, `unauthorized`, or `forbidden` — the existing pattern would miss `ll-auto` auth failures entirely. The new fragment/check state must extend the pattern to include `could not resolve authentication` and `authentication method`:
```bash
grep -qiE '401|403|unauthorized|forbidden|could not resolve authentication|authentication method'
```

**Lib fragment mechanism confirmed.** `loops/lib/cli.yaml` already contains an `ll_auto` fragment (line 22) with bare `action: "ll-auto"` and `evaluate.type: exit_code`. The new auth-check fragment should go in `lib/cli.yaml` or `lib/common.yaml`. Import syntax at loop top-level: `import: [lib/cli.yaml]`. State-level fields override fragment fields.

**`capture` + `output_contains` pattern already in `rn-remediate.yaml`.** The `gate_implement` state (anchor: `gate_implement`, ~line 377) uses `capture: gate_decision` then references `${captured.gate_decision.output}` in an `output_contains` evaluator in `route_gate_refine` — this is the exact two-state pattern (capture → check) needed for the auth guard.

**Per-call-site implementation complexity:**

| Loop | State | Auth guard approach | Complexity |
|------|-------|---------------------|------------|
| `rn-remediate.yaml` | `implement` | Add `capture: implement_output`; insert `check_impl_auth` state routing to `ENV_NOT_READY` terminal before `emit_implement_failed` | Low — already routes on exit_code |
| `autodev.yaml` | `implement_current` | Auth check must intercept before `dequeue_next`; both on_yes/on_no currently advance queue | Medium — intentional dequeue-always routing complicates abort |
| `eval-driven-development.yaml` | `implement` | Unconditional `next: commit_impl`; must add `capture` + convert to conditional routing | Medium |
| ~~`oracles/implement-issue-chain.yaml`~~ | N/A — file never created; ENH-1874 delegated to `autodev` instead | N/A | **Dropped** — `autodev:implement_current` covers this path |

**Shared lib fragment (Option 1) cannot be a transparent wrapper.** Loop FSM lib fragments replace a state, not inject middleware. To share the auth-check logic, the preferred approach is: (a) add a new `ll_auto_auth_check` fragment to `lib/common.yaml` that operates on a named `captured` variable, and (b) each call site adds a `capture:` field to its implement state + inserts a new `check_auth` state referencing the fragment. This means 4 state edits + 4 new check states, but the grep pattern stays in one place.

**`ENV_NOT_READY` token is new** — no existing loop YAML uses this sentinel. It must be introduced alongside the abort terminal state.

**Global test guard: `test_all_failure_terminals_have_diagnostic_action` (line 240 of `test_builtin_loops.py`).** Any new terminal state (`terminal: true`) representing failure must carry a diagnostic `echo` in its `action:`, or this cross-cutting assertion fails. The `cua-agent-desktop.yaml:_auth_failure_abort` state already satisfies this with `echo "Aborting: non-recoverable LLM auth failure (see .plan_errors.log)"`. The new `emit_env_not_ready` terminal state must follow the same pattern.

**Routing-only states** (evaluator with no action) can also route on captured output — `route_gate_refine` in `rn-remediate.yaml` has no `action_type:`/`action:` and uses only `evaluate.source: "${captured.gate_decision.output}"`. This lighter pattern is an alternative to the full shell-grep state used in `_check_plan_auth_failure` when the check is simpler.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-27.

**Selected**: Shared lib fragment (DRY across 4 call sites)

**Reasoning**: Options tie on overall score (9/12 each). The shared lib fragment wins on the Consistency tiebreaker (3/3 vs 2/3): `lib/common.yaml` already holds `with_rate_limit_handling` and `subloop_rate_limit_diagnostic` as direct precedents for cross-cutting shell fragments, 3/4 target loops already import `lib/common.yaml`, and the inline-only option would leave `autodev` (`scan-and-implement` caller), `eval-driven-development`, and `oracles/implement-issue-chain` (`auto-refine-and-implement` + `sprint-refine-and-implement` caller) perpetually unprotected — covering all 4 active call sites is required to achieve honest failure attribution across all `ll-auto`-calling loops.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Shared lib fragment | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| Inline guard (rn-remediate only) | 2/3 | 3/3 | 3/3 | 1/3 | 9/12 |

**Key evidence**:
- Shared lib fragment: `lib/common.yaml` has `with_rate_limit_handling` and `subloop_rate_limit_diagnostic` as direct structural precedents; 3/4 target loops already import `lib/common.yaml`; all 4 call sites covered
- Inline guard: direct copy template from `cua-agent-desktop.yaml:_check_plan_auth_failure` (lines 328–358); minimal change scope; but `autodev` and `oracles/implement-issue-chain` serve high-traffic orchestrator loops — leaving them unguarded perpetuates the auth-failure attribution problem

## Implementation Steps

1. **Extend the grep pattern** beyond `cua-agent-desktop.yaml:_check_plan_auth_failure`'s `401|403|unauthorized|forbidden` to include `could not resolve authentication|authentication method` — the `ll-auto` fatal credential string does not match the existing pattern
2. **Add `ll_auto_auth_check` fragment** to `scripts/little_loops/loops/lib/common.yaml` (or `lib/cli.yaml`): shell action that greps a `${captured.<name>.output}` variable for the extended pattern and emits `AUTH_FAILED` or `OK`; evaluate with `output_contains: AUTH_FAILED`
3. **Modify `rn-remediate.yaml:implement`** (highest priority): add `capture: implement_output` to the state; insert new `check_impl_auth` state (using the fragment) between `implement` and `emit_implement_failed`; route `on_yes` (auth detected) to a new `emit_env_not_ready` terminal that aborts the parent queue
4. **Apply the same two-state pattern** to `autodev.yaml:implement_current`, `eval-driven-development.yaml:implement`, `oracles/implement-issue-chain.yaml:implement_issue` — note `autodev` requires bypassing its `dequeue_next` routing, and `oracles` must distinguish auth failure from rate-limit exhaustion
5. **Add tests in `scripts/tests/test_builtin_loops.py`**: structural assertions that (a) each `implement` state has `capture:` set, (b) a `check_*_auth` state exists following each implement state, (c) the ENV_NOT_READY terminal exists; follow the `test_score_state_has_capture` pattern (line 553)
6. **Validate** with a simulated auth failure (one-issue run with invalid creds): confirm `ENV_NOT_READY` result is emitted and no further issues are dequeued

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add `import: [lib/common.yaml]` to `loops/eval-driven-development.yaml` top-level — currently has no `import:` block at all; the `ll_auto_auth_check` fragment will raise `ValueError: fragment not found` at runtime without this
8. Modify `loops/rn-implement.yaml` `classify_remediation` chain — insert `route_rem_env_not_ready` state between `route_rem_scores_missing.on_no` and `record_failure`, routing `ENV_NOT_READY` to a new `abort_env_not_ready` terminal with diagnostic echo; without this, auth failures fall through into `record_failure → dequeue_next` and the queue is never aborted
9. Name the abort terminal in `oracles/implement-issue-chain.yaml` something other than `"failed"` (e.g., `abort_env_not_ready`) — `TestImplementIssueChainOracle.test_no_unreachable_failed_state` (`test_builtin_loops.py:6118`) asserts `"failed" not in data["states"]`; using `"failed"` will break this test
10. Update 7 breaking tests after routing changes: `TestAutodevLoop` (lines 2006, 2018, 2023, 2671, 2700, 2728) and `TestImplementIssueChainOracle.test_implement_issue_routes_to_implement_next` (line 6189) — run `pytest scripts/tests/test_builtin_loops.py -k "TestAutodevLoop or TestImplementIssueChain"` to verify
11. Add new tests to `scripts/tests/test_rn_remediate.py` (new `TestRnRemediateAuthGuard` class) and `scripts/tests/test_fsm_fragments.py` (fragment field assertions for `ll_auto_auth_check`)

_Wiring pass (2nd) additions by `/ll:wire-issue`:_
12. `emit_env_not_ready` action MUST write `subloop_outcome_` before routing to `failed` — `TestSubloopSidecarContract.test_terminal_routing_states_write_sidecar` (`test_builtin_loops.py:332`) asserts every rn-remediate state transitioning to a terminal contains `subloop_outcome_` in its action; follow the pattern of existing emit states (e.g., `emit_implement_failed`)
13. `ll_auto_auth_check` fragment MUST include a `description` field — `test_all_common_yaml_fragments_have_description` (`test_fsm_fragments.py:1131`) auto-iterates all `lib/common.yaml` fragments and asserts `description` is non-empty; omitting it fails this test immediately upon adding the fragment
14. All bash variable references in new shell state actions MUST use `$${VAR}` form per MR-7 — `test_no_bare_bash_variable_in_shell_actions` (`test_builtin_loops.py:190`) enforces this; FSM namespace refs like `${captured.implement_output.output}` pass through correctly, but bash-level variables (`$ID`, `$VAR`) must be doubled to `$${ID}` / `$${VAR}`

## Integration Map

### Files to Modify
- `loops/rn-remediate.yaml` — `implement` state: add output capture + auth-signature route
- `loops/autodev.yaml` — `ll-auto` call site: same guard
- `loops/eval-driven-development.yaml` — `ll-auto` call site: same guard
- `loops/oracles/implement-issue-chain.yaml` — `ll-auto` call site: same guard
- `loops/lib/common.yaml` — add `ll_auto_auth_check` fragment under `fragments:` key (pre-decision filename `auth_fast_fail.yaml` was incorrect; `lib/common.yaml` is the actual target per implementation steps and decide-issue rationale)
- `loops/rn-implement.yaml` — add `route_rem_env_not_ready` routing state to the `classify_remediation` chain; `ENV_NOT_READY` currently falls through all token checks (`route_rem_implemented` → `route_rem_scores_missing`) into `record_failure → dequeue_next`, so the queue is never aborted on auth failure [Wiring pass]

### Dependent Files (Callers/Importers)
- `loops/cua-agent-desktop.yaml` — `_check_plan_auth_failure` (reference pattern; not modified)
- `scripts/little_loops/host_runner.py` — `resolve_host` (not modified; host-agnostic constraint preserved)

_Wiring pass (2nd) added by `/ll:wire-issue` (advisory — scope depends on ENV_NOT_READY propagation design):_
- `loops/auto-refine-and-implement.yaml` (line 107) — calls `autodev` sub-loop; if `autodev:implement_current` writes an `ENV_NOT_READY` sidecar, this loop reads `subloop_outcome_autodev.txt` and may need to route `ENV_NOT_READY` to abort rather than to its failure path
- `loops/sprint-refine-and-implement.yaml` (line 23) — calls `auto-refine-and-implement`; would cascade `ENV_NOT_READY` upward if propagation is desired
- `loops/scan-and-implement.yaml` (line 75) — calls `autodev` sub-loop directly; same `ENV_NOT_READY` sidecar concern as `auto-refine-and-implement`

### Similar Patterns
- `loops/cua-agent-desktop.yaml` `_check_plan_auth_failure` — existing auth-guard template to replicate (grep pattern: `grep -qiE '401|403|unauthorized|forbidden'`; NOTE: insufficient for `ll-auto` output — must be extended)
- `loops/cua-agent-desktop.yaml` `_handle_plan_error` — parallel auth check on `on_error` path; same grep, same abort terminal
- `loops/rn-remediate.yaml` `gate_decision` — uses `capture: gate_decision` + `output_contains` with `source: "${captured.gate_decision.output}"` — the exact two-state (capture → check) pattern to replicate for auth detection
- `loops/lib/cli.yaml` `ll_auto` fragment (line 22) — the existing `ll-auto` fragment with bare `exit_code` evaluator; new auth-check fragment pairs with this

### Tests
- `scripts/tests/test_builtin_loops.py` — add per-loop test classes (`TestRnRemediateLoop`, etc.) with structural assertions following patterns at lines 553, 674, 1103; use `yaml.safe_load` only (no mocks, no subprocess)
- Test assertions to add per loop: (a) `implement` state has `capture:` set, (b) `check_auth` state exists with `output_contains` evaluator, (c) `emit_env_not_ready` terminal state has diagnostic `echo` (required by `test_all_failure_terminals_have_diagnostic_action` line 240), (d) `on_yes` from auth check routes to abort terminal

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py` — existing 1434-line dedicated test file for rn-remediate; add structural assertions for `check_impl_auth` and `emit_env_not_ready` states in a new `TestRnRemediateAuthGuard` class
- `scripts/tests/test_fsm_fragments.py` — fragment composition tests; add a test asserting `ll_auto_auth_check` fragment has required fields (`action_type: shell`, `evaluate.type: output_contains`, `evaluate.pattern`)

**Tests to update (WILL BREAK from routing changes):**
- `TestAutodevLoop.test_implement_current_on_no_routes_to_dequeue_next` (`test_builtin_loops.py:2018`) — `on_no` changes from `dequeue_next` to `check_impl_auth`
- `TestAutodevLoop.test_implement_current_on_error_routes_to_done` (`test_builtin_loops.py:2023`) — `on_error` routing may change
- `TestAutodevLoop.test_implement_current_runs_ll_auto_only` (`test_builtin_loops.py:2006`) — action body changes (capture added before `ll-auto --only`)
- `TestAutodevLoop.test_implement_current_reconciliation_prepends_stale_inflight` (`test_builtin_loops.py:2671`) — runs action shell verbatim; fails if action body changes
- `TestAutodevLoop.test_implement_current_reconciliation_noop_when_inflight_equals_current` (`test_builtin_loops.py:2700`) — same reason
- `TestAutodevLoop.test_implement_current_reconciliation_skips_done_inflight` (`test_builtin_loops.py:2728`) — same reason
- `TestImplementIssueChainOracle.test_implement_issue_routes_to_implement_next` (`test_builtin_loops.py:6189`) — `next: implement_next` changes to conditional routing; assertion must be updated

_Wiring pass (2nd) added by `/ll:wire-issue`:_
- `TestSubloopSidecarContract.test_terminal_routing_states_write_sidecar` (`test_builtin_loops.py:332`) — iterates every non-terminal rn-remediate state that transitions to `done` or `failed` and asserts `subloop_outcome_` is in its action; `check_impl_auth` routes to `emit_env_not_ready` terminal so `check_impl_auth`'s action MUST contain the sidecar write — follow the pattern of `emit_implement_failed` for expected structure
- `TestRnImplementDiagnosticOutcomes.test_route_rem_scores_missing_splits_to_record_state` (`test_builtin_loops.py:7462`) — asserts `state["on_no"] == "record_failure"` and `state["on_error"] == "record_failure"`; both break when `route_rem_scores_missing.on_no` is re-pointed to the new `route_rem_env_not_ready` state
- `TestRemediationActions.test_implement_failure_routes_to_failed` (`test_rn_remediate.py`) — asserts `impl["on_no"] == "emit_implement_failed"` and `impl["on_error"] == "emit_implement_failed"`; breaks when `on_no`/`on_error` are re-pointed to `check_impl_auth`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — advisory update after implementation; specific subsections: (1) rn-remediate Phase 3 FSM flow table (add `check_impl_auth → emit_env_not_ready` path), (2) rn-remediate outcome token list (add `ENV_NOT_READY`), (3) `lib/common.yaml` fragment table (~line 3083, add `ll_auto_auth_check` row), (4) autodev FSM flow if `implement_current` routing changes

_Wiring pass (2nd) added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` (line 201) — `lib/common.yaml` fragment catalog lists `shell_exit`, `llm_gate`, `with_rate_limit_handling`, etc. but will not include `ll_auto_auth_check`; add entry after implementation

### Configuration
- N/A

### Codebase Research Findings (2nd pass — 2026-06-29)

_Added by `/ll:refine-issue` — stale-reference verification:_

**RESOLVED (not deferred): `oracles/implement-issue-chain.yaml` was never created — ENH-1874 is done but implemented differently.** ENH-1874 (completed 2026-06-02) eliminated the mirrored 5-state chain by having `sprint-refine-and-implement.yaml` delegate `loop: auto-refine-and-implement` (line 23) and `auto-refine-and-implement.yaml` delegate `loop: autodev` (line 107). The `implement_issue` state no longer exists in either sprint loop (`test_builtin_loops.py:1994` asserts those states are gone). The canonical `ll-auto` invoker for the entire refine-and-implement chain is now `autodev.yaml:implement_current`. **Effective call site count is 3, not 4**: `rn-remediate.yaml:implement`, `autodev.yaml:implement_current`, and `eval-driven-development.yaml:implement`. Wiring steps 8–9 (implement-issue-chain terminal naming/routing) are entirely moot — drop them from the implementation scope.

**STALE: `TestImplementIssueChainOracle` does not exist.** The referenced test class is not present in `scripts/tests/`. Lines 6118 and 6189 in `test_builtin_loops.py` are inside `TestGeneratorEvaluatorLoop` and `TestGeneratorEvaluatorCliOracle` (unrelated to this issue). Wiring step 9 (naming the abort terminal to avoid a test collision) is moot and should be dropped.

**CORRECTED: TestAutodevLoop test line numbers have drifted.** Current actual lines:
- `test_implement_current_runs_ll_auto_only`: line 2168 (issue listed 2006)
- `test_implement_current_on_no_routes_to_dequeue_next`: line 2180 (issue listed 2018)
- `test_implement_current_on_error_routes_to_done`: line 2185 (issue listed 2023)
- Reconciliation behavior tests (BUG-1870 pattern, `subprocess.run` shell): lines 2833–2922 (issue listed 2671, 2700, 2728)

**CORRECTED: `test_rn_remediate.py` is 1577 lines** (issue previously stated 1434; has grown since wiring pass).

**CORRECTED: `test_all_failure_terminals_have_diagnostic_action` is at lines 255–292** (not 240). The test only checks terminals named exactly `"failed"`, `"error"`, or `"aborted"` — a terminal named `emit_env_not_ready` will NOT be caught by this assertion. The diagnostic-echo requirement on the new terminal must be enforced by a new dedicated assertion in `TestRnRemediateAuthGuard` (e.g., `assert "echo" in states["emit_env_not_ready"].get("action", "")`).

**PARTIAL COMPLETION: `eval-driven-development.yaml:implement` already has `capture: implement_result`** (lines 20–25, confirmed). Implementation Step 3 says "must add `capture`" — capture is already present. Only the routing change (unconditional `next: commit_impl` → conditional routing through auth check) and the `import: [lib/common.yaml]` addition (Wiring step 7) remain for this loop.

## Impact

- **Severity**: Medium — wastes minutes per batch and corrupts failure
  attribution under any unconfigured-auth environment.
- **Scope**: all autonomous loops that call `ll-auto`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-27_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 71/100 → borderline (slightly below 75 threshold)

### Outcome Risk Factors
- **Moderate per-site complexity at 2 of 4 call sites**: `autodev:implement_current` uses dequeue-always routing where both `on_yes`/`on_no` currently advance the queue; the issue notes this complicates abort but doesn't specify the bypass design. `oracles/implement-issue-chain.yaml` uses `with_rate_limit_handling` and must distinguish auth failure from rate-limit exhaustion — no prescribed mechanism.
- **Broad change surface across 6 loop YAML files**: each requires separate state surgery; a missed site leaves that loop unprotected and the honest-attribution goal partially unmet.

## Session Log
- `/ll:ready-issue` - 2026-06-29T23:11:52 - `ff070c6d-f5f6-495d-8cac-2a4db16e1595.jsonl`
- `/ll:confidence-check` - 2026-06-29T00:00:00Z - `b1006a99-bdbc-4153-a8b2-31663a197ee3.jsonl`
- `/ll:format-issue` - 2026-06-29T23:02:10 - `c3659e49-4b53-4c9d-bc76-03d724100145.jsonl`
- `/ll:wire-issue` - 2026-06-29T22:59:54 - `b46c99c9-2455-4efd-b57f-5edcd95d8d8a.jsonl`
- `/ll:refine-issue` - 2026-06-29T22:25:28 - `ef4faaee-26af-4ab7-8467-41e6baa1c484.jsonl`
- `/ll:confidence-check` - 2026-06-27T23:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:wire-issue` - 2026-06-27T22:46:17 - `c505fdec-528c-43ee-bb73-c9762312bc9c.jsonl`
- `/ll:decide-issue` - 2026-06-27T22:28:21 - `e0ce2dea-8fca-4b08-b38d-f983f2d62cd9.jsonl`
- `/ll:refine-issue` - 2026-06-27T22:13:25 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:format-issue` - 2026-06-27T22:06:59 - `6b0c656c-eeda-41cc-b69d-3c47161977e7.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
