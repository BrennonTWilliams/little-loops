---
id: ENH-3173
type: ENH
title: 'll-mcp --http: expose bind host/port (and the TransportSecuritySettings allow-lists
  that must accompany a non-loopback bind)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:26:15Z'
parent: EPIC-3127
labels:
- mcp
relates_to:
- FEAT-3143
---

# ENH-3173: ll-mcp --http: expose bind host/port (and the TransportSecuritySettings allow-lists that must accompany a non-loopback bind)

## Summary

`ll-mcp`'s HTTP transport (FEAT-3143) cannot be told where to listen. `main_mcp` checks
for a bare `--http` literal and then calls `anyio.run(run_http)` with no arguments, so
`run_http`'s `host="127.0.0.1", port=8765` defaults are the only values reachable from the
console script. `build_http_app(host)` and `run_http(host, port)` are parameterized
correctly — the parameters simply have no route to the command line or to
`.ll/ll-config.json`.

Consequences:

- Two projects cannot serve `ll-mcp --http` on the same machine at once; the second
  fails to bind 8765.
- Any deployment beyond loopback (a container, a tailnet, a VM the phone-side session
  reaches — the exact "start a run from a phone, poll from a workstation" scenario
  FEAT-3145/FEAT-3151 were built for) requires writing a Python shim that calls
  `run_http()` directly, bypassing the console script.
- The port is undiscoverable from config, so `ll-adapt` cannot emit an HTTP client entry
  that is correct by construction.

## Proposed change

Expose `host` and `port` through `--host` / `--port` on `main_mcp` and through an `mcp`
config block (`mcp.http.host` / `mcp.http.port`), with the flag winning. The `mcp` block
already exists in `config-schema.json` for `transport_policy`, so this is a sibling key,
not a new top-level section.

Two constraints that must survive:

1. **Loopback stays the default** (FEAT-3143 Decision 1) — no code path may default to
   `0.0.0.0`. Binding a non-loopback address is an explicit act.
2. **`streamable_http_app()` auto-fills `TransportSecuritySettings` only for a loopback
   `host`.** A non-loopback bind gets empty `allowed_hosts`/`allowed_origins` with
   DNS-rebinding protection on, which rejects every request — including legitimate ones.
   So exposing `--host` without also exposing (or deriving) the allow-lists ships a flag
   that produces a server rejecting 100% of traffic. That pairing is the substance of
   this issue, not an afterthought.

Related but deliberately out of scope: the HTTP transport has no authentication at all,
which is why `mcp.transport_policy.http` denies mutations and tasks by default. Making
the bind address configurable makes that gap easier to reach, so it is worth capturing
authentication as its own issue rather than folding it in here.


## Current Behavior

`ll-mcp --http` always binds `127.0.0.1:8765`. `main_mcp` calls `anyio.run(run_http)` with
no arguments, so `run_http`'s parameters are unreachable from the console script. Two
projects cannot serve HTTP simultaneously, and any non-loopback deployment requires
calling `run_http()` from a Python shim.

## Expected Behavior

`--host` / `--port` on the console script, and `mcp.http.host` / `mcp.http.port` in
`.ll/ll-config.json`, with the flag taking precedence. Loopback remains the default. A
non-loopback bind also configures `TransportSecuritySettings.allowed_hosts` /
`allowed_origins`, so the resulting server actually answers requests instead of rejecting
all of them via DNS-rebinding protection.

## Impact

- **Priority**: P3 - Blocks the cross-machine scenario FEAT-3145/FEAT-3151 were built
  for, but a Python shim is a working (if ugly) escape hatch, and the HTTP transport is
  deny-by-default for both mutations and tasks regardless.
- **Effort**: Small - Argument/config plumbing into two already-parameterized functions;
  the allow-list derivation is the only non-mechanical part.
- **Risk**: Medium - The flag makes it easy to expose an unauthenticated server on a
  non-loopback interface. The security posture must be stated at the point of use, not
  only in docs.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-15 | Priority: P3
