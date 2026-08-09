---
id: 3128
title: 'll-mcp: read-only server (queries, resources, prompts-from-skills)'
type: FEAT
priority: P3
status: open
discovered_date: '2026-08-09'
labels:
- multi-host
- mcp
parent: EPIC-3127
---

## Summary

The first tier of the `ll-mcp` EPIC: a read-only stdio MCP server, shipped as a
new `ll-mcp` console entry point in the `scripts` package. It imports the same
`little_loops` library functions the CLIs use — no shelling out, no daemon; the
host spawns it per session like any stdio server.

Three surfaces:

1. **Coarse read-only tools** — `issues_query` (list / search / show /
   next-issue / sequence behind one parameterized tool), `issue_get` (full body
   + sections), `history_search`, `deps_check`, and `capabilities` (the existing
   `CapabilityReport`).
2. **MCP resources** for issue files, `ll-goals.md`, and docs, under an `ll://`
   scheme (`ll://issues/FEAT-042`, `ll://docs/…`).
3. **Prompts from skills** — every `SKILL.md` served mechanically as an MCP
   prompt, with name, description, and args read from frontmatter.

No write path. Alongside the server, `ll-adapt --host` learns to emit the host's
MCP config snippet (`.mcp.json` for Claude Code, TOML for Codex), and
`ll-ctx-stats` learns to measure the MCP surface's context cost *before* this
ships, so tool granularity is decided on data rather than guesswork.

This tier exists to prove the facade pattern and establish the context-cost
profile. It blocks the mutation tier, which extends this facade, its
output-schema reuse, and its resource surface.

## Spec assumptions (MCP 2026-07-28)

- **Stdio transport unchanged.** This tier ships stdio-only; an HTTP entry point
  is a future addition if needed.
- **Caching metadata is part of the contract.** `tools/list`, `resources/list`,
  `prompts/list`, and `resources/read` responses MUST include `ttlMs` and
  `cacheScope` per SEP-2549, and tool ordering is guaranteed stable. For the
  prompts-from-skills list this directly answers the context-cost open question:
  the host prompt cache can reuse list responses per the declared TTL, and
  `ll-ctx-stats` should consume these protocol-level fields rather than
  re-measuring transport bytes.
- **Explicitly opt out of deprecated primitives.** Do NOT advertise or depend on
  Roots, Sampling, or Logging — all three were deprecated in 2026-07-28 with a
  12-month minimum window. New implementations should not adopt them; this ships
  as a clean-slate consumer.
- **No `initialize` handshake.** Servers handle each request on its own merits
  (protocol version + capabilities arrive in `_meta`). The Python SDK v2
  implements this; `ll-mcp` must pin the SDK version that ships the new
  behavior.

## Bind resource resolution at discovery, not at call time

The design does not yet say how a resource path is resolved. Because this server
exposes skill-derived resources to arbitrary MCP clients, `little-loops` is the
loader and the trust boundary is external — unlike host-CLI-owned skill loading
elsewhere in the project, where the caller is already inside the trust boundary.
Specify the resolution rule before this ships rather than after:

- **Pre-enumerate supporting files at discovery time.** Walk each skill once
  during startup and record the exact set of readable paths. A resource request
  then accepts a skill name, or a `skill-name/relative/path` that was
  enumerated, and is rejected otherwise. The server must never perform an
  arbitrary filesystem read derived from client-supplied input at call time —
  the enumeration, not path sanitization, is what makes traversal impossible.
- **Parse frontmatter only when listing.** `prompts/list` and `resources/list`
  need name, description, and args; reading full skill bodies at list time is
  both a context cost and an unnecessary widening of what is loaded. Fetch
  bodies on demand.
- **Treat a nested `SKILL.md` as a separate skill.** When a skill directory
  contains a subdirectory with its own `SKILL.md`, register it as its own skill
  and do not descend into it as supporting files of the parent, so one skill can
  never serve another's contents.

This applies to the resources surface and the prompts-from-skills surface alike,
and must carry forward to the mutation tier, where the same boundary widens.

## Anti-goals

- **Do not mirror all ~40 `ll-issues` subcommands as tools.** That is a
  context-budget disaster, and `ll-ctx-stats` exists to catch exactly this. The
  whole surface stays coarse.
- **Do not expose orchestration.** `ll-auto`, `ll-parallel`, `ll-loop`, and
  `ll-action invoke` — anything that spawns an agent or runs for minutes — stay
  off the tool surface.
- **Do not reimplement CLI logic.** The server is a facade over the same library
  functions, never a second implementation. Any behavior divergence between a
  tool and its CLI equivalent is a bug in this tier.

## Acceptance criteria

- `ll-mcp` is registered as a console entry point in the `scripts` package and
  runs as a stdio MCP server against the 2026-07-28 spec.
- The tool surface is exactly the five read-only tools listed above; no
  mutating tool is advertised.
- Every tool calls into `little_loops` library functions directly — no
  subprocess invocation of the CLIs.
- Issue files, `ll-goals.md`, and docs are listed and readable as MCP resources
  under the `ll://` scheme.
- Every discovered `SKILL.md` is advertised as an MCP prompt with its name,
  description, and args derived from frontmatter; a nested `SKILL.md` is
  registered as its own skill.
- `resources/read` resolves only against the discovery-time enumeration; a
  request for a path outside it is rejected without a filesystem read.
- `tools/list`, `resources/list`, `prompts/list`, and `resources/read` responses
  include `ttlMs` and `cacheScope`, and tool ordering is stable across calls.
- The server advertises no Roots, Sampling, or Logging capability.
- `ll-adapt --host <x>` emits a working MCP config snippet for that host.
- `ll-ctx-stats` reports the MCP surface's context cost, consuming the
  protocol's `ttlMs` / `cacheScope` fields rather than measuring transport bytes.
