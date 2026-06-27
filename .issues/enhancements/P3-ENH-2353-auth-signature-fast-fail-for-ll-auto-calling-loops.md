---
id: ENH-2353
type: ENH
priority: P3
status: open
captured_at: '2026-06-27T21:58:52Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
relates_to: [FEAT-1496]
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

## Impact

- **Severity**: Medium — wastes minutes per batch and corrupts failure
  attribution under any unconfigured-auth environment.
- **Scope**: all autonomous loops that call `ll-auto`.

## Session Log
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
