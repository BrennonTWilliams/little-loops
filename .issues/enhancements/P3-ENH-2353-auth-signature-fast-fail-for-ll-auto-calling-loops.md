---
id: ENH-2353
type: ENH
priority: P3
status: open
captured_at: '2026-06-27T21:58:52Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
relates_to: [FEAT-1496]
decision_needed: true
labels:
- captured
- loops
- fast-fail
- ll-auto
- host-compat
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

**`capture` + `output_contains` pattern already in `rn-remediate.yaml`.** The `gate_decision` state (line 311) uses `capture: gate_decision` then references `${captured.gate_decision.output}` in an `output_contains` evaluator — this is the exact two-state pattern (capture → check) needed for the auth guard.

**Per-call-site implementation complexity:**

| Loop | State | Auth guard approach | Complexity |
|------|-------|---------------------|------------|
| `rn-remediate.yaml` | `implement` | Add `capture: implement_output`; insert `check_impl_auth` state routing to `ENV_NOT_READY` terminal before `emit_implement_failed` | Low — already routes on exit_code |
| `autodev.yaml` | `implement_current` | Auth check must intercept before `dequeue_next`; both on_yes/on_no currently advance queue | Medium — intentional dequeue-always routing complicates abort |
| `eval-driven-development.yaml` | `implement` | Unconditional `next: commit_impl`; must add `capture` + convert to conditional routing | Medium |
| `oracles/implement-issue-chain.yaml` | `implement_issue` | Unconditional `next: implement_next` + `with_rate_limit_handling` fragment; auth failure should distinguish from rate-limit | Medium |

**Shared lib fragment (Option 1) cannot be a transparent wrapper.** Loop FSM lib fragments replace a state, not inject middleware. To share the auth-check logic, the preferred approach is: (a) add a new `ll_auto_auth_check` fragment to `lib/common.yaml` that operates on a named `captured` variable, and (b) each call site adds a `capture:` field to its implement state + inserts a new `check_auth` state referencing the fragment. This means 4 state edits + 4 new check states, but the grep pattern stays in one place.

## Implementation Steps

1. **Extend the grep pattern** beyond `cua-agent-desktop.yaml:_check_plan_auth_failure`'s `401|403|unauthorized|forbidden` to include `could not resolve authentication|authentication method` — the `ll-auto` fatal credential string does not match the existing pattern
2. **Add `ll_auto_auth_check` fragment** to `scripts/little_loops/loops/lib/common.yaml` (or `lib/cli.yaml`): shell action that greps a `${captured.<name>.output}` variable for the extended pattern and emits `AUTH_FAILED` or `OK`; evaluate with `output_contains: AUTH_FAILED`
3. **Modify `rn-remediate.yaml:implement`** (highest priority): add `capture: implement_output` to the state; insert new `check_impl_auth` state (using the fragment) between `implement` and `emit_implement_failed`; route `on_yes` (auth detected) to a new `emit_env_not_ready` terminal that aborts the parent queue
4. **Apply the same two-state pattern** to `autodev.yaml:implement_current`, `eval-driven-development.yaml:implement`, `oracles/implement-issue-chain.yaml:implement_issue` — note `autodev` requires bypassing its `dequeue_next` routing, and `oracles` must distinguish auth failure from rate-limit exhaustion
5. **Add tests in `scripts/tests/test_builtin_loops.py`**: structural assertions that (a) each `implement` state has `capture:` set, (b) a `check_*_auth` state exists following each implement state, (c) the ENV_NOT_READY terminal exists; follow the `test_score_state_has_capture` pattern (line 553)
6. **Validate** with a simulated auth failure (one-issue run with invalid creds): confirm `ENV_NOT_READY` result is emitted and no further issues are dequeued

## Integration Map

### Files to Modify
- `loops/rn-remediate.yaml` — `implement` state: add output capture + auth-signature route
- `loops/autodev.yaml` — `ll-auto` call site: same guard
- `loops/eval-driven-development.yaml` — `ll-auto` call site: same guard
- `loops/oracles/implement-issue-chain.yaml` — `ll-auto` call site: same guard
- `loops/lib/auth_fast_fail.yaml` — new shared fragment (option 1 / preferred)

### Dependent Files (Callers/Importers)
- `loops/cua-agent-desktop.yaml` — `_check_plan_auth_failure` (reference pattern; not modified)
- `scripts/little_loops/host_runner.py` — `resolve_host` (not modified; host-agnostic constraint preserved)

### Similar Patterns
- `loops/cua-agent-desktop.yaml` `_check_plan_auth_failure` — existing auth-guard template to replicate (grep pattern: `grep -qiE '401|403|unauthorized|forbidden'`; NOTE: insufficient for `ll-auto` output — must be extended)
- `loops/cua-agent-desktop.yaml` `_handle_plan_error` — parallel auth check on `on_error` path; same grep, same abort terminal
- `loops/rn-remediate.yaml` `gate_decision` — uses `capture: gate_decision` + `output_contains` with `source: "${captured.gate_decision.output}"` — the exact two-state (capture → check) pattern to replicate for auth detection
- `loops/lib/cli.yaml` `ll_auto` fragment (line 22) — the existing `ll-auto` fragment with bare `exit_code` evaluator; new auth-check fragment pairs with this

### Tests
- `scripts/tests/test_builtin_loops.py` — add test verifying auth-signature detection routes to `ENV_NOT_READY`

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Severity**: Medium — wastes minutes per batch and corrupts failure
  attribution under any unconfigured-auth environment.
- **Scope**: all autonomous loops that call `ll-auto`.

## Session Log
- `/ll:refine-issue` - 2026-06-27T22:13:25 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:format-issue` - 2026-06-27T22:06:59 - `6b0c656c-eeda-41cc-b69d-3c47161977e7.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
