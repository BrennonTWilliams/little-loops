---
id: ENH-3175
type: ENH
title: 'll-mcp: make build_server''s transport parameter required, with no default'
priority: P2
status: done
verify_verdict: VALID
discovered_by: user-review
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:50:40Z'
completed_at: '2026-08-15T00:50:40Z'
parent: EPIC-3127
labels:
- multi-host
- mcp
- security
relates_to:
- FEAT-3149
- FEAT-3168
size: Small
testable: true
confidence_score: 100
outcome_confidence: 95
score_complexity: 6
score_test_coverage: 10
score_ambiguity: 4
score_change_surface: 14
---

# ENH-3175: ll-mcp — make `build_server`'s `transport` parameter required

## Summary

FEAT-3168 introduced `build_server(transport: str = "stdio")` to thread transport
identity into the handler layer. The **default was the weak point**: `transport`
selects which half of `mcp.transport_policy` applies, so there is no value that is
safe to guess. This issue removes the default, makes every call site state its
transport explicitly, and re-points the two signature pins at the absence of a
default so it cannot be reintroduced.

Behaviour-preserving: no policy decision changes for any existing configuration.

## Current Behavior

`build_server(transport: str = "stdio")` (`server.py:56`). Both production call sites
already passed `transport=` explicitly (`build_http_app` → `"http"`, `run_stdio` →
`"stdio"`), so the default existed **solely** to keep 43 zero-arg test call sites
compiling unchanged.

FEAT-3168's D1 defended the default as fail-safe (over-deny). That justification is
only half true, and the untrue half is the dangerous one:

- A forgotten **stdio** call site defaults to `"stdio"` — correct by luck.
- A forgotten **HTTP** call site also defaults to `"stdio"` — and then applies the
  operator's *stdio* grants to an HTTP server. `mcp.transport_policy.stdio` defaults
  open while an operator locking down HTTP would be setting the `http` half, so this
  direction is fail-**open**, not fail-safe.

Both signature pins actively asserted the default's presence
(`assert params["transport"].default == "stdio"`), so the weaker posture was pinned
in place by tests.

## Expected Behavior

`transport` is required. A call site that omits it raises `TypeError` at construction
time — a loud, immediate failure — rather than silently enforcing the wrong operator
grant at request time. The signature pins assert the default is *absent*, so
reintroducing one for call-site convenience fails the suite.

## Root Cause

A security-relevant parameter was given a default for test-suite convenience. The
FEAT-3168 docstring stated this outright ("the default exists only to keep the ~37
zero-arg test call sites passing unchanged"). Defaults adopted for convenience tend
to outlive the convenience and are later read as intentional API design.

## Program Design

### Signatures

- `build_server(transport: str) -> Server` — was `transport: str = "stdio"`; the
  default is removed. Defined at `scripts/little_loops/mcp_server/server.py:56`.
- `check_tool_call(transport: str, method: str | None, tool_name: str | None, config=None) -> PolicyDecision`
  — unchanged; consumes the threaded value. `scripts/little_loops/mcp_server/policy.py:88`.

### Call Path

`build_http_app()` → `build_server(transport="http")` → `make_call_tool_handler(transport)`
/ `make_tasks_get_handler(transport)` / `make_tasks_cancel_handler(transport)` →
`check_tool_call(transport, ...)`. The stdio path is identical from
`run_stdio()` → `build_server(transport="stdio")`.

## Scope Boundaries

Explicitly out of scope:

- **Any change to policy semantics.** Which grants gate which surfaces is FEAT-3168's
  decision set and is untouched here.
- **Tightening `transport` to `Literal["stdio", "http"]`** — deferred to a follow-up
  covering all three signatures together (D3).
- **`policy.check_tool_call` and `TransportPolicyMiddleware` signatures** — unchanged.
- **`.ll/learning-tests/` prose** — historical proof records, deliberately not edited
  (D4).
- **The `mcp.transport_policy` config schema and its defaults** — unchanged; stdio
  still defaults open.

## Implementation Steps

1. `scripts/little_loops/mcp_server/server.py` — `build_server(transport: str)`;
   docstring rewritten to explain why no default is safe rather than to justify one.
2. Rewrite all 43 test call sites to pass `transport=` explicitly.
3. Re-point both signature pins from `default == "stdio"` to
   `default is inspect.Parameter.empty`.
4. Amend FEAT-3168 with decision **D1a** recording the reversal, and correct the two
   passages there that described the default as load-bearing.

## Files Modified

- `scripts/little_loops/mcp_server/server.py` — signature + docstring.
- `scripts/tests/test_mcp_server.py` — 22 sites → `"stdio"`.
- `scripts/tests/test_feat_3149_mcp_mutation_tools.py` — 11 sites → `"stdio"`;
  module docstring reflowed to the 100-char limit.
- `scripts/tests/test_feat_3145_mcp_tasks.py` — 1 site → `"stdio"`.
- `scripts/tests/test_feat_3151_mcp_start_path.py` — 1 site → `"stdio"`.
- `scripts/tests/test_feat_3143_mcp_http_transport.py` — 3 sites → `"http"` (all three
  feed `streamable_http_app`, so `"http"` is what they always meant); signature pin.
- `scripts/tests/test_feat_3149_transport_policy.py` — signature pin.
- `.issues/features/P2-FEAT-3168-*.md` — D1a amendment.

## Decisions

- **D1 (transport value per test site): preserve prior behaviour exactly.** `"stdio"`
  everywhere except the three `test_feat_3143` sites that build a
  `streamable_http_app`. None of the 43 sites set a `transport_policy` config block,
  so every rewritten site is provably inert with respect to policy — this is a
  signature change, not a behaviour change.
- **D2 (`test_http_tools_list_matches_stdio_path`): split the shared server.** The
  test built one server and drove it over both an in-memory `Client` and an HTTP app.
  A single `transport=` value would have been a lie about one of the two legs. Now
  builds one server per transport. `tools/list` is unguarded, so this is
  behaviour-identical, and it states the parity claim more directly: a stdio server
  and an HTTP server enumerate the same tools.
- **D3 (typing): keep `transport: str`; do not tighten to `Literal`.**
  `policy.check_tool_call` and `TransportPolicyMiddleware` both take plain `str`.
  Tightening one of three in isolation trades one inconsistency for another. Deferred
  as a follow-up covering all three together — see Follow-Ups.
- **D4 (`.ll/learning-tests/` references): leave unedited.** Six files mention
  `build_server()` in prose. They are historical records of what was proven against
  the SDK at a point in time, not live assertions about the current signature.
  Rewriting them would falsify the record.

## Acceptance Criteria

- [x] `inspect.signature(build_server).parameters["transport"].default is
      inspect.Parameter.empty` — asserted in both
      `test_feat_3143_mcp_http_transport.py` and `test_feat_3149_transport_policy.py`.
- [x] Both pins still assert `list(params) == ["transport"]` (no accidental further
      widening).
- [x] Zero `build_server()` zero-arg call sites remain in `scripts/` (remaining
      matches are docstring prose only).
- [x] `python -m pytest scripts/tests/` exits 0 — **19275 passed, 43 skipped** in
      14:50.
- [x] `ruff check` and `ruff format --check` clean on all changed files.
- [x] `python -m mypy scripts/little_loops/mcp_server/` — no issues in 7 source files.

## Verification

Full suite green at 19275 passed / 43 skipped, exit 0. The 7 MCP test modules pass as
a group (103 tests). Lint, format, and type gates clean.

Format check was scoped to changed files rather than run as bare `ruff format
scripts/`, which reformats ~30 unrelated files because `main` carries pre-existing
format drift.

## Impact

- **Breaking change**: No for `ll-mcp` operators — no config semantics change and no
  policy decision differs for any existing configuration. Technically breaking for
  any *out-of-tree* caller of `build_server()`; none exist (it is not re-exported from
  `little_loops.mcp_server.__init__`).
- **Risk**: Low. Compile-time signature change with full-suite verification; the
  failure mode of getting it wrong is an immediate `TypeError`, not silent misbehaviour.

## Follow-Ups

- Tighten `transport` to `Literal["stdio", "http"]` across all three signatures
  together — `build_server`, `policy.check_tool_call`, and
  `TransportPolicyMiddleware.__init__` (D3).

## Session Notes

Originated from a user question about whether FEAT-3168 had implemented anything
out of date, given a belief that current MCP no longer requires a server. Verified
against the spec and the code — it had not:

- stdio and Streamable HTTP are the two standard transports in the current spec, and
  clients *SHOULD* support stdio where possible. What was deprecated (2025-03-26) is
  the older **HTTP+SSE** two-connection transport.
- This repo never used SSE: `grep -rni "sse"` over `scripts/little_loops/mcp_server/`
  returns nothing. `run_stdio` uses `stdio_transport.stdio_server()`; `build_http_app`
  uses `Server.streamable_http_app()`. Pinned to `mcp==2.0.0`.
- Likely sources of the "no server needed" impression: the SSE deprecation; the fact
  that an stdio server is a spawned subprocess over pipes rather than a bound port; or
  skills/plugins as a local alternative. The last is a real design question but does
  not apply here — `ll-mcp` exists to serve non-Claude-Code hosts under EPIC-3127.

The `transport` default was flagged during that review as the one thing worth
changing, which produced this issue.


## Session Log
- `hook:posttooluse-status-done` - 2026-08-15T00:52:00 - `3e7c9d5c-db6b-4056-8147-8c79e66b7bc7.jsonl`

## Status

**Done** | Created: 2026-08-15 | Completed: 2026-08-15 | Priority: P2
