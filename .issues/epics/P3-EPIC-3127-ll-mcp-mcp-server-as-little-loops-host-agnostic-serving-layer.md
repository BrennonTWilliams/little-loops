---
id: 3127
title: 'll-mcp: MCP server as little-loops'' host-agnostic serving layer'
type: EPIC
priority: P3
status: open
discovered_date: '2026-08-09'
labels:
- multi-host
- mcp
relates_to:
- FEAT-3133
- FEAT-3134
- FEAT-3135
- FEAT-3136
- FEAT-3137
- FEAT-3143
- ENH-3144
- FEAT-3145
---

## Summary

Ship `ll-mcp`, a stdio MCP server in the `scripts` package — a thin facade that
imports the same `little_loops` library functions the CLIs use, never a second
implementation. MCP's three primitives map almost one-to-one onto structure the
project already has, so the server mostly formalizes it rather than inventing
anything:

| MCP primitive | little-loops equivalent |
|---|---|
| Tools | CLI commands (`ll-issues`, `ll-deps`, `ll-history`, …) |
| Resources | Files (issue files, `ll-goals.md`, research reports, design docs) |
| Prompts | Skills (`SKILL.md` — named, parameterized prompt templates) |

`ll-mcp` becomes a new console entry point sibling to `ll-action`. No shelling
out and no daemon: the host spawns it per session like any stdio server.
`ll-adapt --host <x>` grows the ability to emit that host's MCP config snippet
(`.mcp.json` for Claude Code, TOML for Codex), so per-host artefact generation
shifts from "generate per-host skill/agent files" toward "register one server."

This EPIC exists to keep the tiers landing in dependency order, to keep the
server a facade over library code, and to hold the job-API tier behind an
evidence gate.

## The three surfaces

### Tools ← CLIs

**Anti-goal:** mirroring all ~40 `ll-issues` subcommands as ~40 tools — a
context-budget disaster (`ll-ctx-stats` exists to catch exactly this). Instead a
coarse surface of ~8–12 tools:

- **Read-only:** `issues_query` (list / search / show / next-issue / sequence
  behind one parameterized tool), `issue_get` (full body + sections),
  `history_search`, `deps_check`, `capabilities` (the existing
  `CapabilityReport`).
- **Mutating:** `issue_capture`, `issue_set_status`, `issue_link`,
  `issue_append_log`, `route`. Each returns the same JSON the CLI emits today;
  the JSON Schemas from `ll-generate-schemas` become tool output schemas nearly
  for free.

**Not tools:** `ll-auto`, `ll-parallel`, `ll-loop`, `ll-action invoke` — anything
that spawns an agent or runs for minutes. Orchestration stays on the CLI; if it
is ever exposed, it belongs behind the job-API tier and its evidence gate.

### Resources ← files

Issue files, `ll-goals.md`, research reports, and design docs served as MCP
resources under an `ll://` scheme (`ll://issues/FEAT-042`,
`ll://docs/…`).

### Prompts ← skills

MCP prompts are named, parameterized prompt templates — exactly what a
`SKILL.md` is. `ll-mcp` serves every skill as an MCP prompt mechanically (name,
description, and args read from frontmatter). This is the biggest strategic
payoff: skills become invocable from any MCP host with zero per-host adaptation,
making `ll-adapt-skills-for-codex` largely obsolete rather than another artefact
family to maintain.

## Tiers and dependency ordering

1. **Read-only serving.** Issue queries + resources + prompts-from-skills. No
   write path. Proves the facade pattern and establishes the context-cost
   profile.
2. **Guarded mutations.** The write tools listed above, behind a dry-run-by-
   default convention plus per-method transport policy.
3. **Job API (evidence-gated).** Long-running orchestration, built only if real
   usage of the first two tiers shows hosts wanting to *drive* runs rather than
   plan them.

The ordering is strict:

- **Tier 1 blocks tier 2.** The mutation tools extend the tier-1 facade,
  output-schema reuse, and resource surface; there is nothing to guard until the
  read-only server exists and its context cost is measured.
- **Tier 2 blocks tier 3, and tier 3 is additionally evidence-gated.** Until
  that evidence exists, anything that spawns an agent or runs for minutes stays
  off the tool surface by design.

## Spec target: MCP 2026-07-28

The design was drafted one day after the 2026-07-28 spec release — the largest
protocol revision since launch. The core architecture is unchanged by it, and in
several places is strengthened:

- **Statelessness.** Per-instance state is explicit (handles passed in
  arguments) rather than implicit (a session-id cookie). This reinforces the
  facade-not-second-implementation argument.
- **Mutation guarding gets a transport-layer hook.** Header-based routing via
  `Mcp-Method` / `Mcp-Name` (SEP-2243) lets `ll-mcp` enforce per-method policy
  *before* JSON-RPC body parsing. This pairs with the dry-run-by-default
  convention rather than replacing it.
- **The job tier must build its own `tasks/*` surface, shaped to SEP-2663, not
  wrap an extension the pinned SDK doesn't ship.** `mcp==2.0.0` implements no
  `io.modelcontextprotocol/tasks` extension — confirmed by learning test
  `.ll/learning-tests/mcp-extension-mechanism.md` (`proven`, mcp 2.0.0, 6/6).
  The formal `Extension` API only attaches via `MCPServer(extensions=[...])`,
  and the lowlevel `Server` that `build_server()` uses has no `extensions`
  parameter, so even the extension mechanism itself is unreachable as built.
  The real, proven path is `Server.add_request_handler("tasks/get", ...)` on
  the unmodified lowlevel server. A proposed `job_start` / `job_status` /
  `job_cancel` shape should track SEP-2663's `tasks/get` / `tasks/cancel` /
  final-result-retrieval shape line-by-line so swapping to the official
  extension later is a registration change, not a client-visible protocol
  change. Progress events feed the `subscriptions/listen` change-notification
  stream regardless.
- **Multi Round-Trip Requests (MRTR) replace server-initiated
  `elicitation/create`.** Any mutation tool needing interactive confirmation
  should be designed around `resultType: "input_required"` plus the client
  retrying the original call with `inputResponses`.

Also load-bearing across all tiers:

- **Stdio transport is unchanged**, so the stdio-only entry point is unaffected.
  The HTTP transport now requires `Mcp-Method` and `Mcp-Name` headers for
  routing; pin the SDK version shipping that behavior if an HTTP entry point is
  ever added.
- **Roots, Sampling, and Logging were deprecated** (12-month minimum window).
  `ll-mcp` must not advertise or consume any of them — it ships as a clean-slate
  consumer.
- **No `initialize` handshake.** Protocol version and capabilities arrive
  per-request in `_meta`. Pin the Python SDK version that implements this.
- **Prefer CIMD over DCR** wherever `ll-adapt --host` emits config snippets
  containing OAuth hints; Dynamic Client Registration was formally deprecated
  (and keeps working during the 12-month window).

## Open questions

1. **Context cost measurement.** Even 10 tool schemas run ~2–4k tokens on hosts
   without deferred loading, and the prompts-from-skills list could be large.
   `ll-ctx-stats` should learn to measure the MCP surface *before* the first
   tier ships, so the coarse-vs-fine tool granularity decision is made on data.
   Partially closed by the spec: `tools/list`, `resources/list`, `prompts/list`,
   and `resources/read` now return `ttlMs` and `cacheScope` (SEP-2549) with
   guaranteed stable tool ordering, so hosts with prompt caching can reuse list
   responses per the declared TTL. `ll-ctx-stats` should consume those
   protocol-level fields rather than re-measuring transport bytes.
2. **SDK dependency posture.** The official Python `mcp` package would be a real
   runtime dependency — acceptable for an opt-in entry point, given the
   project's stdlib-leaning posture?
3. **Prompt fidelity.** Skills assume host affordances (Bash, file edits).
   Serving them as MCP prompts to a host lacking equivalent tools may degrade.
   Does the prompt surface need a capability filter keyed on the host's
   advertised tools? The mechanism (host advertises what it supports, server
   filters accordingly) survives the spec change intact, now via per-request
   `_meta` rather than a handshake.
4. **Should `ll-mcp` advertise the Tasks extension in its capabilities
   response?** No — not until an SDK actually ships
   `io.modelcontextprotocol/tasks`. `mcp==2.0.0` implements no such extension
   (see the "Spec target" section above), so declaring it would claim a
   capability the server only implements privately via
   `Server.add_request_handler`. Revisit this only when a pinned SDK version
   ships the real extension.

## Verification Notes

2026-08-10 (`/ll:verify-issues`): Verified 2026-08-10: Tier-1 (read-only serving) work has essentially shipped — 4 of 5 related FEATs (FEAT-3133, FEAT-3135, FEAT-3136, FEAT-3137) are status: done; only FEAT-3134 remains, status deferred. Document reads as fully speculative but should be updated to reflect landed Tier-1 scope.


## Session Log
- `/ll:verify-issues` - 2026-08-10T16:25:52 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
