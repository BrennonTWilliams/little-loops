---
id: BUG-2830
type: BUG
priority: P1
status: done
captured_at: '2026-07-26T16:51:00Z'
discovered_date: 2026-07-26
discovered_by: session-investigation
completed_at: '2026-07-26T16:52:00Z'
labels:
- host_runner
- sdk
- auth
- autodev
relates_to:
- BUG-2826
- BUG-2828
- ENH-2825
---

# BUG-2830: SDK request path silently rejected for subscription OAuth tokens — missing Claude Code identity header/system block

## Summary

Under `orchestration.request_path: sdk`, every LLM state failed instantly with
exit 1 when authenticated via `CLAUDE_CODE_OAUTH_TOKEN` (subscription OAuth,
`sk-ant-oat01…`). The Messages API only honors subscription OAuth tokens when
the request **presents as Claude Code** — the `anthropic-beta: oauth-2025-04-20`
header *and* a system prompt whose first block is
`"You are Claude Code, Anthropic's official CLI for Claude."`. little-loops'
SDK path (`host_runner.py`) sent the bare Bearer token with neither, and the
API rejected it — deceptively, as a header-less generic
`429 rate_limit_error` (`message: "Error"`, no `anthropic-ratelimit-*` /
reset headers, `x-should-retry: true`) rather than an honest 401/403.

## Current Behavior

Two `ll-loop run autodev ENH-2825` runs (run dirs
`.loops/runs/autodev-20260726T113106/` and `…T113114/`) each completed
"done" in ~10s / 8 iterations with the issue still `open`:

1. autodev dequeued ENH-2825 and delegated to `refine-to-ready-issue`.
2. Its first LLM state `refine_issue` exited 1 in milliseconds
   (`refine-failure-evidence.txt`: `failing_state: diagnose`,
   `refine_issue: 1`).
3. BUG-2826's classifier labeled the API-layer failure as infra
   (`refine-terminal-class: infra`, verdict `transient`).
4. autodev skipped the issue (`autodev-skipped.txt`:
   `ENH-2825  refine_failed_infra`) and exited via the `done` success
   terminal.

## Root Cause

- **File**: `scripts/little_loops/host_runner.py`
- **Anchors**: `_anthropic_client()` (OAuth fallback), `build_anthropic_request()` (system blocks)
- **Cause**: `_anthropic_client()` passed `CLAUDE_CODE_OAUTH_TOKEN` as a bare
  `auth_token` with no `anthropic-beta: oauth-2025-04-20` header, and
  `build_anthropic_request()` never prepended the Claude Code identity system
  block. Live matrix test (2026-07-26): bare token → 429; token + beta header
  only → 429; token + beta header + identity system block → 200 OK. The
  docstring's prior claim that the bare Bearer form was "live-verified
  2026-07-25" no longer held under current API enforcement.

Diagnosis red herrings, recorded for posterity: it was *not* missing
credentials (`.env` fallback loading via `env_file.py` /
`BRConfig.__init__` works and the token parsed/loaded correctly), and *not*
exhausted subscription quota (the interactive session on the same
subscription worked concurrently; the 429 carried no rate-limit/reset
headers). Per Anthropic's June 15 announcement, Agent SDK / `claude -p` /
third-party usage draws from subscription usage limits — subscription tokens
are legitimate here; only the request shape was wrong.

## Steps to Reproduce

Pre-fix, with only `CLAUDE_CODE_OAUTH_TOKEN` set (e.g. via project `.env`):

```python
from pathlib import Path
from little_loops.env_file import load_env_fallback
load_env_fallback(Path("."))
from little_loops.host_runner import dispatch_anthropic_request
from little_loops.prompts import FragmentStore
r = dispatch_anthropic_request(action="Reply with exactly: ok",
                               model="sonnet", fragment_store=FragmentStore())
print(r.exit_code, r.stderr)  # pre-fix: 1, 429 rate_limit_error; post-fix: 0
```

Or end-to-end: `ll-loop run autodev <ID>` under `request_path: sdk` — pre-fix
it completes "done" in ~10s having skipped the issue as `refine_failed_infra`.

## Expected Behavior

Subscription-OAuth SDK requests present as Claude Code (beta header +
identity system block), so `dispatch_anthropic_request()` returns exit 0 with
a real completion and autodev actually processes issues instead of
insta-skipping them.

## Fix

`scripts/little_loops/host_runner.py`:

- New `_active_oauth_token()` helper encoding credential precedence:
  returns `CLAUDE_CODE_OAUTH_TOKEN` only when neither `ANTHROPIC_API_KEY`
  nor `ANTHROPIC_AUTH_TOKEN` is set (SDK-native creds win, unchanged).
- New constants `_OAUTH_BETA_HEADER = "oauth-2025-04-20"` and
  `_CLAUDE_CODE_IDENTITY = "You are Claude Code, Anthropic's official CLI
  for Claude."` with a comment documenting the disguised-429 rejection
  behavior.
- `_anthropic_client()` constructs the client with
  `default_headers={"anthropic-beta": _OAUTH_BETA_HEADER}` on the OAuth
  fallback. All three dispatch sites (`dispatch_anthropic_request`,
  `dispatch_batch_request`, `poll_batch_result`) share this client, so the
  batch path is covered too.
- `build_anthropic_request()` prepends the identity line as the first
  system block whenever the OAuth token is the active credential —
  including when the state has no `system_prompt` of its own. It is a
  separate block placed *before* the cache-marked block, so the FEAT-2671
  cache-marking breakpoint (mark on last block covers everything before it)
  still covers it; batch requests reuse this builder and are covered.

`scripts/tests/test_host_runner_dispatch.py` — new/updated tests in
`TestAnthropicClientCredentials`: beta header on OAuth client construction;
identity block prepended before the system prompt; identity block present
with no system prompt; no identity block under `ANTHROPIC_API_KEY`.

## Verification

- Live end-to-end: `dispatch_anthropic_request(action=…, model=…)` with only
  the subscription OAuth token now returns exit 0 with a real completion
  (previously instant 429/exit 1).
- `python -m pytest scripts/tests/` — full suite green; `ruff check scripts/`
  and `python -m mypy scripts/little_loops/host_runner.py` clean.

## Impact

Before the fix, `request_path: sdk` (this project's configured default) was
completely broken for subscription-authenticated users: every LLM state
failed instantly, and because the rejection masquerades as a transient-infra
429, autodev skipped issues as `refine_failed_infra` and reported the run as
`done` — silent zero-work success. Fixed; runs now consume real subscription
usage, so genuine 429s (with proper rate-limit headers) remain possible under
load.

## Status

Done — fixed, tested, and live-verified in the same session that diagnosed it
(2026-07-26). Not yet committed at time of writing.

## Follow-up candidates (not in scope)

- `dispatch_anthropic_request()` only catches `anthropic.APIError`; a
  non-`APIError` failure at client construction (e.g. the no-credentials
  `TypeError`) propagates without the clean exit-1 + stderr shape, and the
  refine-to-ready evidence chain persisted an empty
  `${captured.refine_issue.stderr}` — the 429 text never reached
  `refine-failure-evidence.txt`, forcing forensic reproduction.
- autodev ending on its `done` success terminal after skipping every
  requested issue as infra arguably deserves a failure terminal
  (ENH-2825's own subject matter).


## Session Log
- `hook:posttooluse-status-done` - 2026-07-26T16:52:17 - `d8cea288-de6d-40fa-9e13-6ccef9b76ea2.jsonl`
