---
id: BUG-2807
title: "request_path: sdk was inert — API-key-only credential probe, missing max_tokens, silent downgrade"
type: BUG
priority: P2
status: done
captured_at: '2026-07-25T18:25:08Z'
completed_at: '2026-07-25T18:25:08Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- ENH-2737
- FEAT-2673
- FEAT-2716
- ENH-2738
labels:
- token-cost
- fsm
- host-runner
- sdk
---

# BUG-2807: request_path: sdk was inert — API-key-only credential probe, missing max_tokens, silent downgrade

## Summary

With `orchestration.request_path: "sdk"` configured (2026-07-24), zero SDK
traffic ever flowed. Three stacked defects, all fixed and live-verified
2026-07-25:

1. **Credential probe too strict** — ENH-2737's fallback guard in
   `FSMExecutor._resolve_request_path()` checked only
   `os.environ.get("ANTHROPIC_API_KEY")`, contradicting the FEAT-2673
   correction (2026-07-19) that subscription users authenticate via
   `ANTHROPIC_AUTH_TOKEN` or an on-disk OAuth profile with no console API
   key. Every prompt-mode state silently downgraded to the CLI path.
2. **Silent downgrade** — the sdk/batch → cli fallback emitted nothing, so
   the misconfiguration was invisible (`usage_events` showed no SDK rows,
   EPIC-2456's F10 gate stayed "structurally dormant").
3. **Latent `max_tokens` crash** — `build_anthropic_request()` never set
   `max_tokens`, a required Messages API parameter; the first-ever real
   `messages.create()` call raised `TypeError`. Masked until now because all
   tests mock the client.

## Resolution

- `executor.py`: new `_sdk_credentials_available()` mirrors the SDK's real
  auth resolution — `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` /
  `CLAUDE_CODE_OAUTH_TOKEN` env statics, else the SDK's
  `anthropic.lib.credentials.default_credentials()` chain (explicit profile,
  workload identity federation, active on-disk OAuth profile). A raising
  chain counts as unresolvable, preserving ENH-2737's never-hard-fail
  contract. Key empirical finding: `default_credentials()` returns `None`
  even when `ANTHROPIC_API_KEY` is set (env statics are handled by the
  client, not the chain), so the probe must check both layers.
- Downgrade is now one-shot non-silent: `request_path_downgrade` event
  (registered as `RequestPathDowngradeVariant` in `observability/schema.py`
  to pass the F5 DES audit gate) + stderr warning naming the remedy.
- `host_runner.py`: new `_anthropic_client()` factory used by all three SDK
  call sites (dispatch, batch submit, batch poll); passes
  `CLAUDE_CODE_OAUTH_TOKEN` (the var `claude setup-token` instructs users to
  set) as `auth_token=` explicitly, since the SDK does not read that
  CLI-namespaced var. Live-verified: the raw Messages API accepts the
  subscription OAuth token as a plain Bearer credential, no beta header.
- `build_anthropic_request()` gained `max_tokens: int = 8192` (flows into
  `build_batch_request` too).
- Docs updated (CONFIGURATION.md, ARCHITECTURE.md, API.md).

## Verification

- Live end-to-end: `dispatch_anthropic_request()` with only
  `CLAUDE_CODE_OAUTH_TOKEN` set returned exit_code 0 with usage data.
- Tests: +8 (probe credential paths incl. auth-token-only, on-disk-profile,
  raising-chain, oauth-token; `_anthropic_client` precedence ×3) in
  `test_fsm_executor.py` / `test_host_runner_dispatch.py`; DES audit
  (`ll-verify-des-audit`) PASSED; mypy/ruff clean.

## Follow-on Finding (recorded, not fixed here)

A same-day `usage_events` traffic audit showed loop state-tagged traffic is
~1% of fleet tokens — the SDK path works but its savings surface is small.
Led to cancelling FEAT-2674/FEAT-2676, closing EPIC-2456, and capturing
ENH-2805 (pruning_profile coverage) as the higher-leverage successor.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-25T18:25:36 - `2b65dece-bf36-4022-a4e8-1a1ea6eed801.jsonl`
- `/ll:capture-issue` - 2026-07-25T18:25:08Z

---

## Status
- Status: done
