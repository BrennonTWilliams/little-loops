---
id: FEAT-3149
title: 'll-mcp: tier-2 guarded mutation tools (dry-run default + per-method transport
  policy)'
type: FEAT
priority: P3
status: open
discovered_date: '2026-08-11'
discovered_by: issue-review
labels:
- multi-host
- mcp
parent: EPIC-3127
depends_on:
- FEAT-3135
- FEAT-3143
- BUG-3150
relates_to:
- EPIC-3127
- FEAT-3145
- FEAT-3134
size: Medium
testable: true
---

# FEAT-3149: ll-mcp: tier-2 guarded mutation tools

## Summary

Add the write half of `ll-mcp`'s tool surface — a small set of issue-mutating
tools (`issue_capture`, `issue_set_status`, `issue_link`, `issue_append_log`)
behind two guards EPIC-3127 names but nothing implements yet: a
**dry-run-by-default convention** and a **per-method transport policy**. This is
tier 2 of EPIC-3127's three-tier ordering, and it is the missing prerequisite for
tier 3 (FEAT-3145).

## Context

Filed 2026-08-11 during review of FEAT-3145. EPIC-3127 defines three tiers with
strict ordering — "Tier 1 blocks tier 2… Tier 2 blocks tier 3, and tier 3 is
additionally evidence-gated" — and enumerates tier 2's tools by name. Tier 1 has
shipped (FEAT-3128, FEAT-3132, FEAT-3135, FEAT-3136, FEAT-3137 all `done`;
FEAT-3134 deferred). Tier 3 has an issue (FEAT-3145). **Tier 2 had no issue at
all** — the gap was invisible because the epic's `relates_to` list jumps straight
from tier-1 FEATs to FEAT-3145.

## Current Behavior

`ll-mcp` serves five read-only tools (`issues_query`, `issue_get`,
`history_search`, `deps_check`, `capabilities` — `mcp_server/tools.py:182-279`).
`handle_call_tool` (`tools.py:294`) dispatches by name through `_TOOL_HANDLERS`
with no notion of a tool being mutating, no dry-run parameter, and no
transport-level policy hook. `mcp_server/__init__.py`'s docstring and
`docs/guides/MCP_SERVER_GUIDE.md`'s "Read-Only by Design" section both state the
server has no write path.

A host that wants to capture an issue or flip a status must shell out to
`ll-issues` directly, which defeats the point of the facade for any host that
isn't sitting on the same filesystem — notably over the FEAT-3143 HTTP transport.

## Expected Behavior

A host can capture an issue, set its status, link it to another, and append a
session-log entry through MCP tool calls. Every such call:

- **defaults to dry-run** — returns the diff/plan it *would* apply, and only
  mutates when the caller explicitly opts in;
- **is classified as mutating in the tool catalog**, so a host can present it
  differently and so transport policy can key off it;
- **can be refused at the transport layer per method**, before JSON-RPC body
  parsing, via SEP-2243 `Mcp-Method` / `Mcp-Name` header routing.

## Use Case

A developer runs a Claude Code session on their laptop against the workstation's
`ll-mcp` over the FEAT-3143 HTTP transport. Triaging a backlog, they want to mark
three issues `deferred` and capture a new bug they just noticed. Today that means
SSH. With tier 2 they call `issue_set_status` and see the dry-run diff first —
which issue file, which frontmatter field, old value → new value — then re-call
with the apply flag. On a deployment where the workstation owner would rather the
HTTP transport stay read-only, the same server refuses the mutating methods at
the transport layer while continuing to serve tier-1 reads.

## Motivation

Three things depend on this:

1. **FEAT-3145 (tier 3) is blocked on it.** Without tier 2, the first write path
   into a project over MCP would be "spawn an agent and run for minutes" — the
   highest-blast-radius mutation on the surface, with no guarding convention to
   sit behind. The dry-run and per-method-policy machinery tier 2 builds is
   exactly what tier 3 needs to reuse.
2. **The facade is half-useful without it.** Tier 1 proved the pattern; a
   read-only server still forces every mutation back onto the CLI, so a remote
   host can look but not touch.
3. **The guards are cheaper to design now than to retrofit.** Adding a dry-run
   convention across four tools is a convention; adding it after a dozen
   mutating tools exist is a migration.

## Proposed Solution

### Tool set

Scope to issue mutations that map onto existing `ll-issues` subcommands, each of
which already exists and is already tested:

| Tool | Backing CLI | Notes |
|---|---|---|
| `issue_capture` | `ll-issues create` | Creates a new issue file |
| `issue_set_status` | `ll-issues set-status` | Frontmatter status transition |
| `issue_link` | `ll-issues link` | Cross-issue relationship edges |
| `issue_append_log` | `ll-issues append-log` | Session-log append |

Following the tier-1 convention, these register as additional entries in the
existing `_TOOL_HANDLERS` dict and `_TOOLS` list rather than a parallel
mechanism (`tools.py:182`, `:192`).

### Guard 1 — dry-run by default

Every mutating tool's input schema carries an `apply: boolean` (default `false`).
With `apply` unset or false the handler computes and returns the intended change
without writing. The default must be **refusal to mutate**, not an opt-out flag —
a host that omits the parameter entirely must not write.

Open design question: whether dry-run is implemented per-handler or as a shared
wrapper around `_TOOL_HANDLERS` entries marked mutating. A wrapper is preferable
(one place to audit, impossible to forget on a new tool) but depends on every
backing CLI path having a computable no-write mode — which needs verifying per
subcommand, since `ll-issues create` writing a new file is a different shape from
`set-status` editing frontmatter in place.

Per **Decision 1**, the wrapper's contract is "describe the intended change,"
not "return the resulting record" — `issue_capture`'s target does not have an
identity until apply, so a wrapper that assumes every tool can name its target
up front will not fit it.

### Guard 2 — per-method transport policy

EPIC-3127 points at SEP-2243 header-based routing (`Mcp-Method` / `Mcp-Name`) as
the hook that lets policy run *before* JSON-RPC body parsing. Needs verification
against `mcp==2.0.0` — see Open Questions — but the intent is a deployment-level
switch that can make the HTTP transport read-only while stdio stays full-access,
without two server builds.

### Tool annotations

Mark mutating tools in the `types.Tool` catalog so hosts can distinguish them
(the MCP `readOnlyHint` / `destructiveHint` annotation family). Verify what
`mcp==2.0.0`'s `types.Tool` actually exposes — current `_TOOLS` entries set only
`name`/`description`/`input_schema`.

## Decisions

### Decision 1 — a dry-run `issue_capture` returns no issue ID

Dry-run returns the *shape* of what would be written — type, priority, slug,
target directory, and the rendered body — and states explicitly that the ID is
allocated at apply time. It does **not** return a concrete ID, not even a
predicted one.

**Rationale:** allocation happens inside `create_issue`'s lock hold at write
time (Open Question 4), so any ID produced before apply is a guess with no
binding force. Returning one invites the host to treat it as authoritative —
echoing it to a user, or writing it into prose or a commit message — and a host
that does so is wrong exactly when it matters: when something else allocated
concurrently. The apply response carries the real ID, which is the only value
that was ever true. A `predicted_id` key was considered and rejected: the
cosmetic benefit of previewing "will create FEAT-3150" does not justify putting
a value in the response whose correctness depends on nothing else racing.

**Consequence for Guard 1:** the shared dry-run wrapper contemplated under
Guard 1 must not assume every mutating tool can name its target up front.
`issue_capture` is precisely the case where the identity of the thing being
mutated does not exist until apply — so the wrapper's contract is "describe the
intended change," not "return the resulting record."

### Decision 2 — the concurrency defect is fixed in BUG-3150, not here

FEAT-3149 `depends_on` **BUG-3150**, which wraps `set-status`, `link`, and
`append-log` in `acquire_lock` and converts them to `atomic_write`.

**Rationale:** the defect predates MCP and affects every consumer of the CLI —
it is not introduced by this issue, only made reachable by it, because exposing
these mutations as MCP tools removes the implicit "one human runs one command at
a time" safety property they were relying on. It therefore deserves its own
issue and its own regression test rather than being absorbed as a sub-task of an
MCP feature. But shipping guarded mutation tools onto a substrate that can
produce torn issue files is unsound, so this issue blocks on it.

**Rejected — locking at the MCP tool layer only.** This is unsound by
construction: a lock held inside `ll-mcp` cannot serialize against a direct
`ll-issues` invocation or a running `ll-auto`/`ll-parallel` job, which is
precisely the race the concern names. The lock has to live at the CLI layer that
every writer goes through.

**Rejected — accepting last-write-wins.** Defensible for lost updates; not
defensible for `write_text` truncation, which can leave an empty or partial
issue file. That is data loss, not a policy choice.

Note the blast radius when implementing BUG-3150: every project on this machine
is `local-editable` against this checkout, so these mutators go live everywhere
with no reinstall step.

## Open Questions

1. **Does `mcp==2.0.0` support SEP-2243 header routing? — RESOLVED: split verdict**
   (2026-08-11). Learning test:
   [`.ll/learning-tests/mcp-header-routing.md`](../../.ll/learning-tests/mcp-header-routing.md).

   - **Header routing exists.** The SDK module `mcp.shared.inbound` implements
     SEP-2243 and exports `MCP_METHOD_HEADER` (`"mcp-method"`), `MCP_NAME_HEADER`
     (`"mcp-name"`), and `NAME_BEARING_METHODS`
     (`tools/call`→`name`, `prompts/get`→`name`, `resources/read`→`uri`).
   - **But the SDK exposes no pre-parse hook.** `classify_inbound_request` takes
     the **decoded body** as its first required positional parameter and headers
     only as an optional keyword used to *cross-check* it — it cannot be called on
     headers alone. `handle_modern_request` parses the body (`json.loads`,
     `_streamable_http_modern.py:343`) **before** validating headers
     (`:381`). The library's only use of these headers is a mismatch rejection
     (`HEADER_MISMATCH`, `-32020`); they are never used to dispatch.

   **Verdict: the ASGI-middleware fallback is the implementation, and it is
   proven to work.** The spike wraps `streamable_http_app()` in middleware that
   reads `Mcp-Method`/`Mcp-Name` off the raw ASGI `scope["headers"]`, denies a
   named tool, and returns a JSON-RPC error with status 403 — **without ever
   awaiting `receive()`**. Guard 2 survives at full scope; it does not shrink to
   guard 1. See the AC 5 substitution recorded below.

   Two design consequences:
   - The middleware only exists on the HTTP path, so policy expressed there is
     silently absent over stdio. Implement the policy decision once at a policy
     layer and *invoke* it from the middleware, rather than encoding rules inside
     the middleware.
   - The guard is sound against header spoofing: because the server independently
     enforces header/body agreement, a request whose `Mcp-Method` lies about its
     body is rejected downstream rather than silently trusted.

2. **What is the `route` tool the epic lists? — RESOLVED: it does not exist**
   (2026-08-11). There is no `ll-route` entry point in `scripts/pyproject.toml`
   (the only related entry is `ll-action = "little_loops.cli:main_action"`),
   `ll-action` exposes exactly `invoke`/`capabilities`/`list`, and no `"route"`
   command or tool name appears anywhere in `scripts/little_loops/`. The epic's
   sole mention is the tier-2 tool list itself (EPIC-3127 line 60) — nothing
   defines it. **It was aspirational.** It stays excluded from this issue's tool
   table, and EPIC-3127's tier-2 list should drop it (see Follow-ups).

3. **Is the epic's output-schema claim true? — RESOLVED: no** (2026-08-11).
   `ll-generate-schemas --help` states verbatim: "Generate JSON Schema files for
   all **LLEvent types**." It takes only `-h` and `-o/--output`; there is no mode
   that emits schemas for `ll-issues` command output. LLEvent schemas describe the
   *telemetry event* vocabulary, which is a disjoint surface from the JSON these
   four tools return.

   **Consequence:** tool output schemas are hand-written work, not free. This
   raises the effort estimate — budget for four hand-authored output schemas plus
   their drift risk against the CLI's actual JSON. EPIC-3127's claim should be
   corrected (see Follow-ups).
4. **Does dry-run compose with `ll-issues create`? — RESOLVED: yes, and the
   dry-run returns no ID** (2026-08-11). See Decision 1.

   The question's premise was false in both halves. `get_next_issue_number`
   (`issue_parser.py:1559`) is a **pure filesystem scan** — it finds the highest
   existing number across all issue dirs and adds one. `next-id` therefore
   reserves nothing and consumes nothing, so a dry-run *cannot* have an ID side
   effect to worry about. And `create_issue` (`cli/issues/create.py:202`) already
   allocates and writes **under a single `acquire_lock` hold** on
   `.issues/.id-alloc.lock`, retrying on collision, with `open(path, "x")`
   exclusive-create so a racer bypassing the lock fails loudly rather than
   clobbering. Allocation genuinely happens at write time, atomically.

5. **Concurrency — RESOLVED: it is a real pre-existing CLI defect, split out as
   BUG-3150** (2026-08-11). See Decision 2.

   Investigation found the gap is worse than "no lock," and is not uniform:

   | Command | Lock | Atomic write | Worst case |
   | --- | --- | --- | --- |
   | `create` (`create.py:202`) | yes | `open(path,"x")` | safe |
   | `scaffold-epic` (`scaffold_epic.py:83`) | yes | — | safe |
   | `set-status` (`set_status.py:127`, `:209`) | **no** | **no** (`write_text`) | torn / empty file |
   | `link` (`link.py:149`, `:170`, `:202`) | **no** | **no** (`write_text`) | torn file; half-linked graph |
   | `append-log` (`session_log.py:245`) | **no** | yes (`atomic_write`) | lost update only |

   `write_text` truncates before writing, so `set-status` and `link` risk **file
   corruption**, not merely a lost update — a correctness bug rather than a
   concurrency policy choice. `link` additionally writes source and target as two
   independent unprotected writes, so an interruption between them leaves the
   source claiming a link the target has no backlink for.

## Anti-goals

- **Do not mirror all ~40 `ll-issues` subcommands as tools.** EPIC-3127 names
  this explicitly as "a context-budget disaster." Four tools, coarse and
  parameterized.
- **Do not add orchestration.** `ll-auto`, `ll-parallel`, `ll-loop`, `ll-action
  invoke` stay off the tool surface — that is tier 3 (FEAT-3145) and separately
  evidence-gated.
- **Do not add authentication as part of this issue.** FEAT-3143 deferred it; the
  per-method transport policy here is a coarse allow/deny switch, not an authz
  model. If policy work reveals auth is a hard prerequisite for the HTTP
  transport, file it separately rather than absorbing it.
- **Do not change tier-1 tool behavior or output shapes.**

## Acceptance Criteria

1. Each of the four tools appears in `tools/list` output with a mutating
   annotation distinguishing it from the five read-only tools.
2. Calling any mutating tool **without** an explicit apply opt-in leaves the
   filesystem unchanged — asserted per tool by comparing issue-file bytes before
   and after the call — and returns a description of the intended change.
3. Calling with the apply opt-in performs the same mutation the equivalent
   `ll-issues` subcommand performs — asserted by comparing resulting file state
   against a direct CLI invocation on an identical fixture.

   3a. Per Decision 1: a dry-run `issue_capture` response contains **no issue-ID
   field** — asserted by schema check on the dry-run result — while the apply
   response carries the ID actually allocated by `create_issue`, asserted equal
   to the created file's frontmatter `id`.
4. A tool error (unknown issue ID, invalid status value, malformed link target)
   returns `is_error=True` rather than raising into the SDK dispatch loop,
   matching `handle_call_tool`'s existing contract (`tools.py:312-318`).
5. Per-method transport policy: with the policy configured to deny mutations, a
   mutating tool call over HTTP is refused while `issues_query` continues to
   succeed on the same server instance.

   **Substitution recorded (2026-08-11, per Open Question 1):** the mechanism is
   **ASGI middleware wrapped around `Server.streamable_http_app()`**, not an SDK
   pre-parse hook — no such hook exists in `mcp==2.0.0`. The AC is otherwise
   unchanged in scope. Two additional assertions this substitution requires:

   - The middleware reaches its deny decision from `Mcp-Method`/`Mcp-Name` on the
     raw ASGI `scope["headers"]` **without awaiting the request body**, asserted
     by a test that confirms the denial response is produced with `receive()`
     un-awaited.
   - The denial is expressed as a JSON-RPC error response, so a compliant client
     surfaces it as a protocol error rather than a transport failure.
6. Existing tier-1 tests pass unchanged: `test_mcp_server.py` and
   `test_feat_3143_mcp_http_transport.py`, including
   `test_build_server_signature_unchanged`.
7. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — matches the epic and its tier-1 siblings. Not urgent, but it
  is the ordering prerequisite for FEAT-3145, so it should not be skipped.
- **Effort**: Medium — the four backing CLI paths already exist and are tested,
  so the tool handlers are thin. The cost is in the two guards: dry-run needs a
  no-write mode verified per backing subcommand, and transport policy has an
  unverified SDK premise (Open Question 1). Could grow to Large if
  `ll-generate-schemas` doesn't supply output schemas (Open Question 3).
- **Risk**: Medium — first write path into a project over MCP. The dry-run
  default is the primary mitigation and is why it must default to refusing.
  Concurrency (Open Question 5) is the main unmitigated hazard.
- **Breaking Change**: No — additive tools; tier-1 catalog and shapes unchanged.
  Documentation asserting read-only-ness becomes false and must be updated.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/tools.py` — add four handlers to
  `_TOOL_HANDLERS` (`:182`) and four `types.Tool` entries to `_TOOLS` (`:192`,
  source-order literal — note the comment at `:190` that list order *is* the
  ordering guarantee); extend `handle_call_tool` (`:294`) with the dry-run guard.
- `scripts/little_loops/mcp_server/server.py` — `build_server()` (`:30`) if
  transport policy needs a construction-time hook.
- `scripts/little_loops/mcp_server/__init__.py` — module docstring says "five
  coarse read-only tools"; goes stale.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_mcp_server.py` — imports `build_server`, exercises tool
  dispatch via `mcp.client.Client(server)`
- `scripts/tests/test_feat_3143_mcp_http_transport.py` — imports `build_server`;
  `test_build_server_signature_unchanged` (`:67-69`) asserts zero parameters, so
  any policy hook must be additive inside the body or that test changes
- `scripts/little_loops/cli/issues/` — backing subcommands: `create.py`,
  `set_status.py`, `link.py`, `append_log.py`; a no-write mode may need adding here
  rather than in the MCP layer

### Similar Patterns
- Tier-1 tool handlers (`_tool_issues_query`, `_tool_issue_get`, …
  `tools.py:42-180`) — the shape to follow for the four new handlers.
- `_TOOL_HANDLERS`/`_TOOLS` paired-registry convention — do not introduce
  per-tool SDK registration.

### Tests
- New test module for mutating-tool dispatch, dry-run default, and apply
  behavior; model on `test_mcp_server.py`'s `mcp.client.Client(server)` +
  `_make_project(tmp_path, monkeypatch)` + `anyio.run(run)` conventions.
- New test for transport policy over HTTP, using
  `test_feat_3143_mcp_http_transport.py`'s `_envelope()`/`_post()` raw-JSON-RPC
  helpers.
- Byte-comparison fixture helper for AC 2 (filesystem unchanged on dry-run).

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md` — `## What ll-mcp Is` ("exposes a
  little-loops project read-only") and the whole `## Read-Only by Design` section
  are falsified; needs a new section on the mutation surface and its guards.
- `docs/reference/CLI.md` — `### ll-mcp`: "exposing five coarse, read-only tools"
  goes stale.
- `docs/index.md` — line 45 calls it "the read-only `ll-mcp` server."
- `.issues/epics/P3-EPIC-3127-ll-mcp-mcp-server-as-little-loops-host-agnostic-serving-layer.md` — add FEAT-3149 to `relates_to` (the
  omission is what let this gap go unnoticed).

### Configuration
- **RESOLVED** (see Open Questions item 1). There is no `mcp` key in
  `scripts/little_loops/config-schema.json` today — top-level sections run
  `analytics` … `tamper_guard` with no MCP entry — so this adds a new section:

  ```json
  "mcp": {
    "transport_policy": {
      "http":  { "allow_mutations": false },
      "stdio": { "allow_mutations": true }
    }
  }
  ```

  Deny-by-default on HTTP is the deliberate choice: FEAT-3143 landed the HTTP
  transport with no authentication, so the safe posture is that the transport a
  remote host reaches is read-only until someone opts in. stdio is a
  same-machine, same-user channel, so it defaults open. This is the "deployment
  switch without two server builds" the Guard 2 section asks for, and it is also
  the policy hook FEAT-3145's Open Question 2 (unauthenticated run-start over
  HTTP) would extend rather than reinvent.

## Program Design

### Types
- `apply: bool` — added to each mutating tool's `input_schema`, default `false`.
- Dry-run result payload — **settled** by Decision 1. The payload describes the
  *intended change*, never the resulting record:

  ```json
  {
    "applied": false,
    "tool": "issue_set_status",
    "target": { "issue_id": "FEAT-3149", "path": ".issues/features/P3-FEAT-3149-….md" },
    "changes": [ { "field": "status", "from": "open", "to": "deferred" } ]
  }
  ```

  `issue_capture` is the one shape that differs: it has no `target.issue_id`,
  because the ID does not exist until apply allocates it under the lock. Its
  dry-run carries the resolved `type`, `priority`, slug, target directory, and
  rendered body instead, plus an explicit note that the ID is assigned at apply
  time. The apply response for every tool carries `"applied": true` and, for
  `issue_capture`, the real allocated `issue_id`.

### Signatures
- `_tool_issue_capture(arguments: dict[str, Any]) -> Any` — and three siblings
  (`_tool_issue_set_status`, `_tool_issue_link`, `_tool_issue_append_log`),
  matching the existing tier-1 handler signature (`tools.py:42`).
- `handle_call_tool(_ctx: ServerRequestContext[Any], params:
  types.CallToolRequestParams) -> types.CallToolResult` — `tools.py:294`,
  existing; gains the dry-run guard before `handler(params.arguments or {})`
  at `:313`.
- `build_server() -> Server` — `mcp_server/server.py:30`, existing; unchanged
  signature (see AC 6).

### Call Path
`MCP host tools/call` -> `handle_call_tool` (`tools.py:294`) -> dry-run guard
(new) -> `_TOOL_HANDLERS[name]` -> `little_loops.cli.issues.<subcommand>` backing function ->
issue file write (only when `apply` is true)

Transport policy sits earlier: `HTTP request` -> policy check on `Mcp-Method`
header (new, pre-parse) -> SDK JSON-RPC dispatch -> `handle_call_tool`

### Decision Rules
- **Dry-run default:** mutate only when `apply is True`. Absent, null, or any
  non-`True` value means do not write. Fail closed.
- **Method classification:** a tool is mutating iff it appears in the mutating
  registry — one list, consulted by both the dry-run guard and transport policy,
  so the two guards cannot disagree about what counts as a write.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.
Tier 2 (guarded mutations).

## Status

**Open** | Created: 2026-08-11 | Priority: P3
