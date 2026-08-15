---
id: ENH-3173
type: ENH
title: 'll-mcp --http: expose bind host/port (and the TransportSecuritySettings allow-lists
  that must accompany a non-loopback bind)'
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:26:15Z'
completed_at: '2026-08-15T07:52:32Z'
parent: EPIC-3127
labels:
- mcp
relates_to:
- FEAT-3143
- ENH-3171
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

**Coordinate with ENH-3171** (`--project-root`): both issues add flags to `main_mcp`,
which today is deliberately not an `argparse` CLI (it checks a bare `--http` literal).
Whichever lands first should make the argparse decision once; the second builds on it
rather than accreting another bare-literal check or independently introducing a parser.

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


## Program Design

### Types

- No new dataclasses/models — reuses the SDK's `mcp.server.transport_security.TransportSecuritySettings(enable_dns_rebinding_protection: bool = True, allowed_hosts: list[str], allowed_origins: list[str])`.

### Signatures

- `main_mcp(argv: list[str] | None = None) -> int` — extend the existing `argparse.ArgumentParser` (added by ENH-3171) with `parser.add_argument("--host", default=None)` / `parser.add_argument("--port", type=int, default=None)`, resolved against `mcp.http.host` / `mcp.http.port` from `.ll/ll-config.json` (flag wins), defaulting to the current `127.0.0.1` / `8765` literals.
- `run_http(host: str = "127.0.0.1", port: int = 8765, project_root: Path | None = None) -> None` (`scripts/little_loops/mcp_server/server.py:245`) — no signature change needed; `main_mcp` already threads `host`/`port` positionally/by keyword into this coroutine.
- `build_http_app(host: str = "127.0.0.1", project_root: Path | None = None) -> Any` (`scripts/little_loops/mcp_server/server.py:82`) — add the allow-list derivation here (the single App-construction call site), passing `transport_security=TransportSecuritySettings(allowed_hosts=[...], allowed_origins=[...])` into `Server.streamable_http_app(..., host=host)` when `host` is non-loopback, mirroring the loopback auto-fill the SDK already performs for `127.0.0.1`/`localhost`.

### Call Path

`main_mcp` -> `run_http(host, port, project_root)` -> `build_http_app(host, project_root)` -> `Server.streamable_http_app(host=host, transport_security=...)`

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

## Scope Boundaries

- **No authentication.** Making the bind address configurable does not add any auth to
  the HTTP transport; that gap is tracked as its own future issue (see "Related but
  deliberately out of scope" above).
- **No change to `mcp.transport_policy`.** Mutation/task allow-lists for HTTP stay
  deny-by-default; this issue only affects where the server listens and which
  `Host`/`Origin` headers it accepts, not what it permits once connected.
- **No change to stdio transport.** `--host`/`--port` and `mcp.http.*` apply to the
  HTTP transport only.
- **No TLS termination.** Binding a non-loopback address does not add HTTPS; operators
  fronting `ll-mcp --http` with a reverse proxy remain responsible for transport
  encryption.
- **No automatic `allowed_hosts`/`allowed_origins` derivation beyond the bind host
  itself** — e.g. no wildcard/subnet expansion, no DNS lookup to resolve additional
  aliases. The allow-lists are seeded from the explicit `--host` value (and its
  loopback aliases, matching the SDK's existing auto-fill behavior); anything broader
  is a config the operator supplies, not inferred here.

## Status

**Open** | Created: 2026-08-15 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-15T07:52:08 - `d32f69ed-4207-401e-9bc5-bf812b8631e2.jsonl`
- `/ll:ready-issue` - 2026-08-15T07:32:08 - `9796d8d8-2a77-4d62-914f-046c89794a73.jsonl`
