---
id: 3127
title: 'll-mcp: MCP server as little-loops'' host-agnostic serving layer'
type: EPIC
priority: P3
status: open
verify_verdict: NON_VALID
discovered_date: '2026-08-09'
labels:
- multi-host
- mcp
relates_to:
- FEAT-3128
- FEAT-3132
- FEAT-3133
- FEAT-3134
- FEAT-3135
- FEAT-3136
- FEAT-3137
- FEAT-3143
- ENH-3144
- FEAT-3145
- FEAT-3149
- FEAT-3151
- FEAT-3168
- ENH-3171
- ENH-3172
- ENH-3173
- ENH-3174
- ENH-3175
- BUG-3177
- BUG-3178
- BUG-3180
- BUG-3181
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

## Status: what shipped (updated 2026-08-15)

**All three tiers have landed.** Everything below in "The three surfaces" and
"Tiers and dependency ordering" was written as a plan and is retained as the
design record; this section is the authority on what the code actually does.
Implementation lives in `scripts/little_loops/mcp_server/` (`__init__.py`,
`server.py`, `tools.py`, `resources.py`, `prompts.py`, `policy.py`, `tasks.py`),
behind the optional `mcp` extra (`mcp==2.0.0`, pinned exactly). User-facing
documentation is `docs/guides/MCP_SERVER_GUIDE.md`.

**Ten tools**, each wrapping a `little_loops` library function directly — no
subprocess, no second implementation:

| Group | Tools | Shipped by |
|---|---|---|
| Read | `issues_query`, `issue_get`, `history_search`, `deps_check`, `capabilities` | FEAT-3135 |
| Write | `issue_capture`, `issue_set_status`, `issue_link`, `issue_append_log` | FEAT-3149 |
| Start | `loop_start` | FEAT-3151 |

**Resources** (FEAT-3136): `ll://issues/<ID>`, `ll://goals`, `ll://docs/<path>`.
**Prompts** (FEAT-3137): every discovered `SKILL.md`, via recursive `rglob`,
skipping `disable-model-invocation: true`.
**Run control** (FEAT-3145): `tasks/get` / `tasks/cancel`, registered via
`Server.add_request_handler`, sharing `ll-loop`'s `instance_id` space so a run
started from one host is pollable and stoppable from another.
**Transports** (FEAT-3143): stdio by default, streamable HTTP via `--http` or
`LL_MCP_TRANSPORT=http`.
**Host registration** (FEAT-3133): `ll-adapt --host claude-code|codex --apply`
emits `.mcp.json` / `.codex/ll-mcp.toml`.

**Guarding**, as specified and then some. Guard 1 is dry-run-by-default on all
four mutators, fail-closed — only the literal boolean `True` opts in. Guard 2 is
per-transport policy (`mcp.transport_policy` in `.ll/ll-config.json`) with two
*independent* grants: `allow_mutations` and `allow_tasks`. HTTP denies both by
default (that transport ships with no authentication); stdio allows both.
FEAT-3168 closed the gap where the policy was enforced only in HTTP's ASGI
middleware — the `tools/call` and `tasks/*` handlers now consult
`policy.check_tool_call` themselves, so stdio gets identical enforcement and the
same `-32001` denial.

Deviations from the plan above, all recorded in the qualifying blockquotes in
their sections: the `route` tool was dropped (no such CLI ever existed);
`ll-generate-schemas` output was not reusable, so output schemas were
hand-written; SEP-2243 header routing has no pre-parse SDK hook, so the HTTP
guard is ASGI middleware and exists on the HTTP path only; the SDK ships no
`io.modelcontextprotocol/tasks` extension, so `tasks/*` is locally authored,
SEP-2663-shaped, and deliberately **not** advertised in capabilities.

### Known gaps, captured as children

- ~~**ENH-3171** (P2) — the project root is `Path.cwd()` with no override. A host
  that spawns from `$HOME` produces a server that answers truthfully about
  nothing, silently. This is the most common real-world failure.~~ **done**
- ~~**ENH-3172** (P2) — resource and prompt indices are enumerated once at startup
  and never invalidated, so the server does not see issues its own
  `issue_capture` / `loop_start` created.~~ **done**
- ~~**ENH-3173** (P3) — `--http` cannot be told where to bind; `127.0.0.1:8765` is
  unreachable from the console script.~~ **done**
- ~~**ENH-3174** (P3) — `resources/list` returns the whole enumeration (3,000+
  entries here) with the pagination params accepted and ignored.~~ **done**
- **FEAT-3134** (deferred) — the context-cost measurement this epic wanted
  *before* the first tier shipped. It never happened; see Open Question 1.
- ~~**BUG-3177** (P2) — `prompts/list` returns an empty list on any install where
  `skills/` is not on disk two directories above the package. `skills/` is not
  package data (`pyproject.toml` ships `little_loops/**` only) and
  `_find_plugin_root()`'s fallback encodes the source-checkout layout, so a
  wheel install without `CLAUDE_PLUGIN_ROOT` serves zero prompts, silently.~~ **done**
- ~~**BUG-3178** (P2) — `ll-adapt --host codex --apply` writes
  `mcp_servers = ["ll-mcp"]` into `.codex/ll-mcp.toml`: a name reference, not a
  server definition, so Codex has no `command` to spawn.~~ **done**
- **BUG-3180 / BUG-3181** (P2, both closed 2026-08-15) — found by reviewing ENH-3171's
  implementation *after* it closed: the resolved root reached only two of the four call
  sites the issue named. `tasks._loops_dir` read `config.loops.loops_dir` (the raw
  `".loops"` string) instead of the joining `get_loops_dir()`, so `loop_start` and
  `tasks/*` stayed on `$CWD/.loops`; `history_search` never used its `project_root` at
  all, since `search()`'s `db` default is the relative `.ll/history.db`. The second is the
  more instructive one: `resolve_history_db(<root>/.ll/history.db)` would *not* have fixed
  it, because a default-shaped path is discarded in favor of a cwd-anchored walk — the
  root had to become a parameter (`resolve_history_db(..., root=)`), which it now is.
  Both had ENH-3171's own tests passing over them; the `loop_start` guard asserted an
  error that occurred under either root.

Together, BUG-3177 and BUG-3178 mean **this epic's host-agnostic claim has never
been exercised end-to-end outside a Claude Code plugin checkout.** Both were
found by reading the code, not by a failing run — nothing here tests a
pip-installed `ll-mcp` spawned by a non-Claude-Code host, which is the
acceptance test the epic is missing. ENH-3171 (cwd-only project root) is the
third face of the same shape: roots resolved by guessing, answering truthfully
about nothing when the guess is wrong.

Not gaps, but deliberate boundaries worth restating: `ll-auto`, `ll-parallel`,
`ll-queue`, and `ll-action invoke` remain off the surface entirely; `ll-loop` is
the sole orchestration exception. Roots, Sampling, and Logging are not
advertised. MRTR (`resultType: "input_required"`) is designed for but not
implemented — no tool currently needs interactive confirmation.

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
  `issue_append_log`. Each returns the same JSON the CLI emits today; tool output
  schemas are hand-written per tool.

  > **Corrected 2026-08-11 (FEAT-3149 OQ2/OQ3).** Two claims in the original text
  > were wrong. (1) A fifth mutating tool, `route`, was listed; no `ll-route`
  > entry point exists and no `route` command or tool appears anywhere in
  > `scripts/little_loops/` — it was aspirational and has been dropped.
  > (2) The text claimed "the JSON Schemas from `ll-generate-schemas` become tool
  > output schemas nearly for free." `ll-generate-schemas` emits schemas for
  > **LLEvent types** only — the telemetry event vocabulary, a surface disjoint
  > from these tools' return JSON. Output schemas are hand-written work, and
  > FEAT-3149's effort estimate accounts for it.

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

  > **Tier-3 split 2026-08-11.** Tier 2 shipped (FEAT-3149, commit `24e2c0c8`),
  > so the *ordering* half of this rule is now satisfied. The *evidence* half is
  > not, and this epic has not been amended to say otherwise.
  >
  > Tier 3 is now two issues, split along exactly the line this rule draws:
  >
  > - **FEAT-3145** — `tasks/get` + `tasks/cancel` + the transport policy gate.
  >   Spawns nothing; `tasks/cancel` signals an already-running process. This
  >   sits *inside* the sentence above rather than across it, and is a plausible
  >   way to **generate** the tier-3 evidence rather than assume it: a host that
  >   polls runs from a second machine is the observable "wants to drive runs"
  >   behavior this gate is waiting for.
  > - **FEAT-3151** — the SEP-2663 start path. This is the part that spawns an
  >   agent, and is what the gate holds back.
  >
  > **Opening the gate is a decision to record here, not in the child issues.**
  > If FEAT-3151 is implemented, amend this bullet to state that the gate opened
  > and on what evidence — otherwise the children permanently contradict their
  > parent and every automation pass re-derives "gated, do not implement."

  > **Gate opened 2026-08-11, by product decision, not observed usage.** The
  > original plan was to wait for real tier-1/tier-2 usage to show hosts wanting
  > to *drive* runs rather than plan them; that usage evidence never
  > materialized. The gate is opened anyway on an explicit call: job control over
  > MCP (start/poll/stop) is 100% aligned to and required by product strategy, so
  > the epic proceeds on strategic commitment rather than waiting on the
  > usage-evidence signal it originally specified. Both FEAT-3145 (poll/cancel)
  > and FEAT-3151 (start path) are cleared to implement. This does not relax any
  > other constraint in this epic — FEAT-3151 still owes the client-capability
  > gate on task materialization (its own carried-over TODO(L56) caveat), and
  > FEAT-3145's transport-policy gate (Decision 4) still applies regardless of
  > this decision.

  > **Gate closed 2026-08-15 — both cleared issues shipped.** FEAT-3145
  > (`tasks/get` / `tasks/cancel`) and FEAT-3151 (`loop_start`) are `done`. The
  > client-capability gate FEAT-3151 owed is implemented: `TasksExtension`
  > requires three independent signals — the tasks extension declared in the
  > request's `_meta.clientCapabilities.extensions`, `params.task` set on that
  > call, and a modern protocol version — before it reshapes the response into a
  > task envelope. Missing any one yields the ordinary tool result. The detached
  > spawn is identical either way, so only the envelope varies, never the
  > behavior. FEAT-3145's Decision 4 transport gate is in force as the
  > `allow_tasks` grant, and FEAT-3168 extended enforcement from HTTP-only to
  > both transports. Nothing in this epic is gated any longer.

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

  > **Qualified 2026-08-11 (FEAT-3149 OQ1), learning test
  > `.ll/learning-tests/mcp-header-routing.md`.** The conclusion holds but the
  > mechanism does not: `mcp==2.0.0` ships **no pre-parse hook**.
  > `classify_inbound_request` requires the *decoded body* and uses headers only
  > to cross-check it, and `handle_modern_request` parses the body before
  > validating headers — the SDK's only use of these headers is a mismatch
  > rejection (`-32020`), never dispatch. Per-method policy before body parsing
  > is still achievable, and is proven working, via **ASGI middleware wrapped
  > around `streamable_http_app()`** reading the raw `scope["headers"]`. Note the
  > guard then exists on the HTTP path only — stdio has no headers.
- **The job tier must build its own `tasks/*` surface, shaped to SEP-2663, not
  wrap an extension the pinned SDK doesn't ship.** `mcp==2.0.0` implements no
  `io.modelcontextprotocol/tasks` extension — confirmed by learning test
  `.ll/learning-tests/mcp-extension-mechanism.md` (`proven`, mcp 2.0.0, 6/6).
  The formal `Extension` API only attaches via `MCPServer(extensions=[...])`,
  and the lowlevel `Server` that `build_server()` uses has no `extensions`
  parameter. The real, proven path is
  `Server.add_request_handler("tasks/get", params_type, handler)` on the
  unmodified lowlevel server.

  > **Qualified 2026-08-11 (FEAT-3145 OQ1), learning test
  > `.ll/learning-tests/mcp-tasks-start-path.md` (11/11).** "Even the extension
  > mechanism itself is unreachable as built" was too strong. The *absent
  > `extensions=` parameter* is real, but `compose_tool_call_handler(extensions,
  > handler)` is a **free function** that folds any `Extension`'s
  > `intercept_tool_call` around a `tools/call` handler on the lowlevel `Server`
  > — proven working end-to-end. This matters because SEP-2663's **start** path
  > is not a method at all: it is an ordinary `tools/call` whose response carries
  > `CreateTaskResult` (`resultType: "task"`) instead of a `CallToolResult`, and
  > `runner._serialize` passes non-core `resultType` shapes through unsieved by
  > design. So the line-by-line SEP-2663 fidelity this bullet asks for is
  > achievable, and the additive-only `MethodBinding` rule is never engaged
  > (nothing re-registers `tools/call`). A proposed `job_start` / `job_status` /
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

### Disposition, 2026-08-15

1. **Context cost measurement — still open, and now out of order.** FEAT-3134 is
   `deferred` (`readiness_stagnated`); the measurement that was supposed to
   happen *before* the first tier shipped never happened, and all three tiers
   shipped anyway. The tool surface was kept coarse (ten tools) on judgment
   rather than data, which is probably fine — but the resource surface was not,
   and now returns 3,000+ entries (ENH-3174). The `ttlMs`/`cacheScope` hints are
   emitted (5 minutes, `public`, on `tools/list`, `resources/list`,
   `resources/read`, `prompts/list`) but nothing consumes them. Reviving
   FEAT-3134 is the precondition for deciding ENH-3174 on data.
2. **SDK dependency posture — resolved: yes, as an optional extra.** `mcp==2.0.0`
   is pinned exactly under `[project.optional-dependencies].mcp`, not in the
   base dependency set, so `pip install little-loops` is unaffected. `main_mcp`
   imports `mcp` lazily and exits `2` with an actionable message when the extra
   is absent, so every `[project.scripts]` target still resolves in a checkout
   without it.
3. **Prompt fidelity — still open, unaddressed.** No capability filter was
   built. `prompts/list` serves every discovered `SKILL.md` unconditionally
   (minus `disable-model-invocation: true`), so a host lacking Bash or file
   editing receives skills it cannot execute. Not yet observed to cause a
   concrete failure, which is why this has no child issue; capture one if a real
   host degrades on it.
4. **Advertising the Tasks extension — resolved: no, and implemented that way.**
   `build_server()` registers `tasks/*` via `add_request_handler` and never
   declares `io.modelcontextprotocol/tasks` in capabilities. `TasksExtension`
   carries that identifier internally only to key off what the *client*
   declares. Revisit when a pinned SDK ships the real extension.

## Verification Notes

2026-08-10 (`/ll:verify-issues`): Verified 2026-08-10: Tier-1 (read-only serving) work has essentially shipped — 4 of 5 related FEATs (FEAT-3133, FEAT-3135, FEAT-3136, FEAT-3137) are status: done; only FEAT-3134 remains, status deferred. Document reads as fully speculative but should be updated to reflect landed Tier-1 scope.

2026-08-15 (manual review against `scripts/little_loops/mcp_server/`): Epic body
updated to reflect landed scope. All three tiers shipped; 12 of the 13 original
children are `done` and FEAT-3134 alone is `deferred`. FEAT-3168 was missing from
`relates_to` (added). Added a "Status: what shipped" section as the authority on
implemented behavior, closed the tier-3 gate note, and dispositioned all four open
questions (2 and 4 resolved, 1 and 3 still genuinely open). Four gap issues
captured as children: ENH-3171 (project-root resolution, P2), ENH-3172 (stale
resource/prompt indices, P2), ENH-3173 (HTTP bind host/port, P3), ENH-3174
(resource-surface bounding, P3).

2026-08-12 (`/ll:verify-issues`): Verdict: **NON_VALID (NEEDS_UPDATE)**. Two real children, FEAT-3128 and FEAT-3132 (both `status: done`, `parent: EPIC-3127`), were missing from frontmatter `relates_to` — added above. Also corrected the prior note's stated completion: actual status across the full child set (via `ll-issues show EPIC-3127`) is 10 of 12 done (FEAT-3134 and FEAT-3151 are `deferred`), not the "4 of 5" figure previously recorded.

2026-08-16 (`/ll:verify-issues`): `mcp_server/` exists, 23/24 items resolved, but the "Known gaps" section still listed ENH-3171, ENH-3172, ENH-3173, ENH-3174, BUG-3177, and BUG-3178 as unresolved even though they are now all `status: done` — updated the Known gaps section above to mark them done. Verdict: NEEDS_UPDATE.

## Session Log
- `/ll:verify-issues` - 2026-08-16T16:40:25 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:07:49 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:confidence-check` - 2026-08-12T02:07:06 - `2a82a443-5d46-418f-a842-19472b08c75b.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:52 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
