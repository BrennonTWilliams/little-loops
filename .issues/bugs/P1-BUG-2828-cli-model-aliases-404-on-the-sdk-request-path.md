---
id: BUG-2828
type: BUG
priority: P1
status: done
captured_at: '2026-07-26T06:40:00Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
completed_at: '2026-07-26T06:55:00Z'
labels:
- fsm
- host-runner
- sdk
- request-path
relates_to:
- BUG-2818
- FEAT-2716
- FEAT-2710
- BUG-2826
---

# BUG-2828: host-CLI model aliases 404 against the Messages API under `request_path: sdk`

## Summary

Every prompt state resolves its model through
`FSMExecutor._resolve_action_model()`, which returns
`state.model or self.run_model or self.fsm.llm.model` **verbatim**. Those values
are host-CLI aliases — `fsm/schema.py` sets `DEFAULT_LLM_MODEL = "sonnet"`, and
the loop YAMLs use the same short names.

The host CLI binary resolves aliases itself. The Anthropic Messages API does
not: it returns `404 not_found_error: model: sonnet`. So under
`orchestration.request_path: "sdk"` (or `"batch"`), which routes prompt states
through `host_runner.dispatch_anthropic_request` / `dispatch_batch_request`
instead of the CLI, **every prompt state fails instantly** with no model call.

BUG-2818 fixed the adjacent empty-string case on this path (the SDK has no
downstream default, unlike the CLI binary) but did not map aliases to IDs.

## Current Behavior

Run `.loops/runs/autodev-20260726T011116/` — `ll-loop run autodev FEAT-2123` —
completed `done` in 7.1 seconds having done no work:

```
refine_issue   action: /ll:refine-issue FEAT-2123 --auto    exit 1 after 200ms
  stderr: Error code: 404 - {'type':'error','error':
          {'type':'not_found_error','message':'model: sonnet'},
          'request_id':'req_011CdQBU2XDbsJrYtZngUqv9'}
diagnose       exit 1 after 210ms, SAME 404
→ classify_terminal → failed → skip_inflight → "FEAT-2123  refine_failed"
```

Every shell state in the same run succeeded; only prompt states failed, and they
failed in ~200ms — the round-trip of a rejected request.

## Steps to Reproduce

1. `orchestration.request_path: "sdk"` in `.ll/ll-config.json`.
2. Run any loop with a prompt state that does not pin a full model ID
   (i.e. any loop that takes the `DEFAULT_LLM_MODEL` default).
3. The first prompt state exits 1 with `404 ... model: sonnet`.

## Expected Behavior

An alias resolves to a concrete model ID before the request leaves for the API;
the CLI path continues to pass aliases through untouched, since the binary
resolves them.

## Impact

Total loss of function on the `sdk` and `batch` request paths: every prompt
state fails, so any loop reaching one terminates immediately having done no
work. The failure is fast and silent — the observed autodev run reported `done`
in 7.1 seconds with a clean-looking summary — so it reads as a data or issue
problem rather than a configuration one. Shell-only loops are unaffected, as is
the CLI request path.

## Status

Done. Fix and tests landed in `host_runner.py` and
`scripts/tests/test_host_runner_dispatch.py`; full detail below.

## Resolution

Fixed in `host_runner.py`:

- Added `MODEL_ALIASES` (`fable`/`opus`/`sonnet`/`haiku` → `claude-fable-5` /
  `claude-opus-5` / `claude-sonnet-5` / `claude-haiku-4-5`) and
  `resolve_model_alias()`, exported via `__all__`.
- Applied it at the top of `build_anthropic_request()` rather than at each
  dispatch site, so `build_batch_request()` — which delegates to it — is covered
  by the same edit, and so the F1 cache-marking oracle keys off the same value
  the API sees (its family match is a substring test, so full IDs still match).
- Unknown values pass through unchanged: full IDs, dated snapshots, and
  `anthropic.`-prefixed Bedrock IDs are unaffected, making the call safe to
  apply unconditionally at the API boundary.

Tests in `scripts/tests/test_host_runner_dispatch.py::TestModelAliasResolution`
cover the alias table, pass-through for non-aliases, the resolved value reaching
both `messages.create` and `messages.batches.create`, and a regression guard
asserting `DEFAULT_LLM_MODEL` is a resolvable alias.

## Follow-ups

The same run exposed two further defects, filed separately:

- [[BUG-2826]] — the 404 was misclassified as a refine *quality* failure, so the
  issue was blamed for an infrastructure fault.
- [[BUG-2827]] — `finalize_done`'s counters emit two-line values.

`MODEL_ALIASES` is a hard-coded table and will drift as the model lineup moves;
if that becomes a maintenance problem, sourcing it from config or the Models API
is the natural next step.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-26T15:13:12 - `11c2772b-94e5-4249-b116-f80bb85fb67d.jsonl`
