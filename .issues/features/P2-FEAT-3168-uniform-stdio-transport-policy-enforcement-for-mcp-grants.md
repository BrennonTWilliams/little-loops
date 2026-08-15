---
id: FEAT-3168
type: FEAT
title: 'll-mcp: enforce stdio transport policy for both grants across all three guarded
  surfaces'
priority: P2
status: done
verify_verdict: VALID
discovered_by: issue-review
discovered_date: '2026-08-14'
captured_at: '2026-08-14T22:40:00Z'
completed_at: '2026-08-15T00:17:38Z'
parent: EPIC-3127
labels:
- multi-host
- mcp
- security
relates_to:
- FEAT-3145
- FEAT-3149
- FEAT-3151
size: Large
testable: true
confidence_score: 100
outcome_confidence: 86
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-3168: ll-mcp — enforce stdio transport policy for both grants

## Summary

`mcp.transport_policy.stdio.*` is **advisory today: setting any of its knobs to `false`
has no effect.** The policy decision function is only ever called from the HTTP
transport's ASGI middleware, so over stdio nothing consults it. An operator who
deliberately locks down stdio gets silent non-enforcement.

This issue plumbs transport identity into the handler layer so the same
`check_tool_call` decision applies on both transports.

(Two config grants — `allow_mutations` and `allow_tasks` — covering three guarded
surfaces: the mutation tools, `tasks/*`, and `loop_start`.)

## Current Behavior

`policy.check_tool_call` (`scripts/little_loops/mcp_server/policy.py`) encodes all three
grants correctly. It has exactly **one call site** in the package:
`TransportPolicyMiddleware`, which is HTTP-only (`server.py::build_http_app` wraps the
ASGI app; `run_stdio` has no equivalent). The handlers themselves
(`tools.py::handle_call_tool`, `tasks.py::handle_tasks_get`/`handle_tasks_cancel`) never
invoke the policy.

Consequences over stdio:

- `stdio.allow_mutations: false` does not stop FEAT-3149's four mutation tools.
- `stdio.allow_tasks: false` does not stop FEAT-3145's `tasks/get` / `tasks/cancel`.
- `stdio.allow_tasks: false` does not stop FEAT-3151's `loop_start` — which spawns an
  agent with the project's full tool permissions.

The gap predates FEAT-3151; that issue's Decision 8 recorded it explicitly, accepted it
rather than half-fixing it for one tool, and owed this follow-up. `MCP_SERVER_GUIDE.md`
already documents the knobs as advisory, so this is a known gap, not a silent one.

## Expected Behavior

`check_tool_call` reaches its decision on **both** transports. A denied call over stdio
returns the same `-32001` JSON-RPC error the HTTP path returns (minus the HTTP 403, which
has no stdio analogue), for both grants and all three guarded surfaces uniformly.

## Motivation

The default posture is unaffected — stdio defaults open, and it is a same-machine,
same-user channel, so this is not a live exposure. What is wrong is that a **setting the
config schema advertises does nothing**. An operator hardening a shared or automation-run
workstation sets `stdio.allow_tasks: false`, reads no warning, and believes run control is
off when it is not. A knob that silently no-ops is worse than an absent one.

`loop_start` raises the stakes enough to be worth doing now rather than deferring
indefinitely: it is the only MCP surface that spawns an agent.

## Use Case

An operator runs little-loops' MCP server over stdio on a shared or automation-run
workstation and sets `mcp.transport_policy.stdio.allow_tasks: false` in
`.ll/ll-config.json`, intending to prevent any MCP client on that box from starting
loop runs (`loop_start`) or inspecting/cancelling other users' runs (`tasks/get`,
`tasks/cancel`). Today that config write is silently ignored — `loop_start` still
spawns an agent with the project's full tool permissions over stdio. After this issue
lands, the same `tools/call` for `loop_start` is denied with a `-32001` JSON-RPC error
before any process is spawned, so the config knob the operator set actually does what
it says.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/server.py` — `build_server()` currently takes no
  parameters and is transport-agnostic. Handlers need to know which transport they are
  serving. Note `test_build_server_signature_unchanged`
  (`test_feat_3143_mcp_http_transport.py:67-69`) pins the zero-parameter signature — see
  Q1 below (decided: option (a)). **Both call sites must pass explicitly**:
  `build_http_app()` must change its `build_server()` call (`server.py:51`) to
  `build_server(transport="http")`, and `run_stdio()` (`server.py:150`) to
  `build_server(transport="stdio")` — the default parameter exists only to keep the ~37
  zero-arg test call sites green, not as a value either production path relies on.
  Default `transport="stdio"`, chosen for failure-mode asymmetry: a forgotten HTTP call
  site then *over*-denies (stdio-locked config wrongly denies HTTP — visible, annoying,
  not a hole), whereas default `"http"` would let a forgotten `run_stdio` call site
  silently regress this entire feature back to advisory.
- `scripts/little_loops/mcp_server/tools.py` — `handle_call_tool` gains the policy check
  (guard 0, ahead of FEAT-3149's dry-run guard 1).
- `scripts/little_loops/mcp_server/tasks.py` — `handle_tasks_get` / `handle_tasks_cancel`
  likewise.
- `scripts/little_loops/mcp_server/policy.py` — `check_tool_call` itself should not need
  to change; it already takes `transport` as a parameter.

### Similar Patterns
- `TransportPolicyMiddleware` (`policy.py`) is the model for the denial shape (`-32001`,
  the reason string).

_Wiring pass added by `/ll:wire-issue`:_
- `raise MCPError(...)` precedent also exists outside `tasks.py::_not_found()`:
  `resources.py` (4 sites: lines 156, 170, 182, 235) and `prompts.py` (2 sites: lines
  134, 142) both raise `MCPError` directly rather than hand-building JSON-RPC, but with
  SDK-defined `types.INVALID_PARAMS`, not a custom implementation-defined code —
  secondary precedent behind `_not_found()`'s custom-code shape, useful if `tools.py`'s
  denial (which has no local `raise MCPError` precedent at all today) needs a second
  reference point.

### Tests
- New module `test_feat_3168_stdio_policy_enforcement.py`, modeled on
  `test_feat_3149_transport_policy.py` but driving the stdio server. Note BUG-3167's
  fix to the stdio test harness (do not close stdin early) applies here.
- Assert all three guarded surfaces deny over stdio when their grant is set to `false`,
  and that the default-open
  posture is unchanged when unset.
- **Wrong-transport-closure guard** (added by issue review, 2026-08-14): with
  `stdio.allow_mutations: false` / `stdio.allow_tasks: false` **and** the http knobs
  open (or unset), requests driven through `build_http_app()` must still succeed. AC 5's
  "test_feat_3149 passes unmodified" does not cover this — those tests never combine a
  locked stdio config with HTTP traffic, and that config split is exactly what catches a
  handler closure capturing the wrong transport identity (e.g. `build_http_app` failing
  to pass `transport="http"`).

_Wiring pass added by `/ll:wire-issue`:_
- `test_feat_3149_transport_policy.py:103-105` — `test_build_server_signature_still_unchanged`
  is a **second** strict-equality pin (`inspect.signature(build_server).parameters == {}`)
  distinct from the one already named at `test_feat_3143_mcp_http_transport.py:67-69` —
  both need the same sanctioned edit if `build_server` gains a parameter.
- No existing test drives `loop_start` over real stdio via `_stdio_call()` — confirmed
  gap; AC 3's "no process is spawned" assertion needs either a monkeypatched
  `run_background` (pattern at `test_feat_3151_mcp_start_path.py` around line 260) or an
  equivalent spawn-assertion in the new module.
- Confirmed non-breaking (informational, no action needed): every existing zero-arg
  `build_server()` call site — `test_mcp_server.py` (22 sites), `test_feat_3149_mcp_mutation_tools.py`
  (11 sites), `test_feat_3145_mcp_tasks.py:167`, `test_feat_3151_mcp_start_path.py:459`,
  `test_feat_3143_mcp_http_transport.py:74,96,108` — none set a `transport_policy` config
  block, so a defaulted `transport` parameter keeps all of them passing unchanged.

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md` — remove the "stdio knobs are currently advisory"
  paragraph once this lands. It is currently accurate and must not be removed before.
- `docs/reference/CLI.md` — `### ll-mcp` transport policy notes.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` has **two** passages to update, not one: the "advisory"
  sentence in the `tasks/*`/`loop_start` gating description (~lines 4382-4391, the one
  the issue's line above refers to), and a separate mutations-denial description
  (~lines 4288-4293) that frames the deny mechanism as ASGI-middleware-only — both go
  stale once handler-level enforcement covers stdio too.
- `scripts/little_loops/config-schema.json:566` — the top-level `mcp.transport_policy`
  schema `description` field states policy is "Enforced for HTTP in ASGI middleware,"
  which becomes inaccurate once stdio enforces the same decision; update in the same
  change as the two doc passages above.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-14 — based on codebase analysis:_

- Denial-shape mechanics confirmed at `policy.py:73-76,202-208`: `POLICY_DENIED_CODE = -32001` is a module-level int constant (not a shared enum), docstring-scoped to the `-32000..-32099` implementation-defined band, explicitly citing the SDK's own `-32020 HEADER_MISMATCH` as the reserved-code precedent to avoid. `TransportPolicyMiddleware` builds the JSON-RPC error body by hand (`json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": POLICY_DENIED_CODE, "message": decision.reason}})`) and sends it via raw ASGI `send()` calls — there is no shared "build a JSON-RPC error" helper in the package.
- A second, structurally different error mechanism already exists in `tasks.py`: `_not_found()` (`tasks.py:78-79`) constructs and *raises* `mcp.shared.exceptions.MCPError(code=TASK_NOT_FOUND_CODE, message=...)`, letting the SDK's own request-handler dispatch serialize it — no manual `json.dumps` at that call site. `TASK_NOT_FOUND_CODE = -32002` (`tasks.py:47-51`) is docstring-cross-referenced as "parallel to" `policy.POLICY_DENIED_CODE`. Because `handle_tasks_get`/`handle_tasks_cancel` already use the raise-`MCPError` pattern for their existing `_not_found` case, a stdio policy denial in those two handlers has a same-file precedent to mirror that the ASGI-middleware's raw-dict construction does not.
- `MUTATING_TOOLS` (`policy.py:52-62`, a `frozenset`) is documented as "the single registry of tool names that write. Both guards consult it: `tools.py`'s dry-run wrapper (Guard 1) and the transport policy here (Guard 2)." — the issue's own "guard 0, ahead of ... guard 1" framing extends this existing two-guard numbering by one. `TASK_STARTING_TOOLS = frozenset({"loop_start"})` (`policy.py:71`) is deliberately kept out of `MUTATING_TOOLS` because `loop_start` joining it would make the dry-run guard require `apply: true`, which "has no coherent meaning for 'start'" (`policy.py:64-70`).
- Stdio end-to-end test harness to reuse (named generally in the existing Tests subsection above): `_stdio_call()` at `scripts/tests/test_mcp_server.py:576-662`. It spawns `subprocess.Popen([sys.executable, "-c", "from little_loops.mcp_server import main_mcp; main_mcp()"], stdin=PIPE, stdout=PIPE, ...)`, writes `initialize` + `notifications/initialized` + `tools/call` as newline-delimited JSON-RPC in one write+flush, then loops `readline()` on stdout for the matching response `id`. BUG-3167's fix is precisely: stdin is **not** closed until *after* the response is read (only in the `finally` block) — closing it earlier races the SDK's stdin-EOF cancellation of in-flight handlers and intermittently truncates or replaces the response with a `-32000 Connection closed` error (docstring at `test_mcp_server.py:584-591`). A `threading.Timer(60, proc.kill)` watchdog guards against a wedged handler.
- Existing precedent for asserting stdio policy decisions **without** a subprocess: `test_feat_3149_transport_policy.py:224-234,253-271,312-335` already calls `check_tool_call("stdio", "tools/call", "issue_set_status", config=config).allowed` directly against the policy layer. This is a viable/faster complement to a full `_stdio_call()` round-trip for asserting the decision itself, while `_stdio_call()` remains necessary for AC 1-3's actual over-the-wire `-32001` assertion.

_Added by `/ll:refine-issue` — 2026-08-14 — based on codebase analysis:_

- Factory naming convention for threading a construction-time value into a handler via closure: a uniform `make_<method_noun>_handler(...) -> Any` factory returning an inner `async def handle_<method_noun>(...)` closure, called at `build_server()` construction time and passed directly as `Server(...)` kwargs — evidence: `resources.py:197` (`make_list_resources_handler`), `resources.py:222` (`make_read_resource_handler`), `prompts.py:86`, `prompts.py:120`, wired at `server.py:112-115`. No factory of this shape currently exists for `handle_call_tool` / `handle_tasks_get` / `handle_tasks_cancel` — those three are registered by bare function reference (`server.py:102-105,134-135`), unlike the resource/prompt pair.
- Two established, non-interchangeable ways to signal a handler-level protocol error in this package: raising `mcp.shared.exceptions.MCPError(code=..., message=..., data=...)` from inside an `async def handle_*` coroutine (evidence: `resources.py:156,170,182,235`; `prompts.py:134,142`; `tasks.py:78-79` via the `_not_found()` helper, called as `raise _not_found(...)` at `tasks.py:128,176`) vs. hand-building a JSON-RPC error dict and sending it over raw ASGI `send()` (evidence: `policy.py:202-219`, `TransportPolicyMiddleware`). The ASGI-`send()` shape exists specifically because that code runs pre-parse, before any MCP handler/request context exists — it is not the general convention for handler-level denials. A third, disjoint shape exists only for tool-handler exceptions: `tools.py:863-877` catches exceptions from `_TOOL_HANDLERS` entries and turns them into `CallToolResult(is_error=True, ...)`, a tool-result error rather than a JSON-RPC protocol error — not the shape a pre-dispatch policy denial needs.
- No shared "build a JSON-RPC error dict" utility exists anywhere in `mcp_server/` — `policy.py:202-208`'s `json.dumps(...)` is inline, not extracted into a helper. `MCPError` is the only reusable error-construction primitive in the package.
- Test convention split for transport-conditional behavior: every existing stdio-vs-http policy comparison (`test_feat_3149_transport_policy.py:224-235,253-271,312-335`) asserts directly against `check_tool_call(transport, ...)`, never through the `_stdio_call()` subprocess round trip (`test_mcp_server.py:576-662`). `_stdio_call()`'s own docstring states it exists to catch encode/serialization failures the in-memory `Client` cannot observe, not to assert policy decisions — its one existing caller (`test_list_returning_tools_serialize_over_stdio`) tests wire serialization, not policy. No existing test pairs a `check_tool_call()` unit assertion with an actual `_stdio_call()` denial round trip on stdio; the HTTP side has both a full-request test and a raw-ASGI-scope test side by side (`test_feat_3149_transport_policy.py:108-131,159-201`), stdio has neither today.

## Open Questions

_Both questions below were closed by pre-implementation review, 2026-08-14 — see the
Decisions subsection that follows them. Original text retained for context._

1. **How does transport identity reach the handlers?** Options: (a) parameterize
   `build_server(transport=...)` and close over it in the handler factories — simplest,
   but breaks `test_build_server_signature_unchanged`, which would need a sanctioned
   edit; (b) a context variable set by `run_stdio`/`build_http_app`; (c) read it off the
   `ServerRequestContext` if the SDK exposes anything usable. (a) is the obvious default
   unless (c) turns out to be free.
2. **Should the HTTP middleware stay?** If handlers enforce uniformly, the middleware
   becomes a redundant early-out. Keeping it is still worthwhile: it denies *before* the
   JSON-RPC body is parsed, which is the property FEAT-3149 wanted. Recommend keeping
   both and asserting they agree.

### Decisions

_Added by issue review — 2026-08-14 — after direct inspection of the pinned MCP SDK
(`mcp/server/context.py`, `mcp/server/runner.py`, `mcp/shared/jsonrpc_dispatcher.py`):_

- **D1 (closes Q1): option (a).** `build_server(transport: str = "stdio")`, threaded
  into `make_*_handler(transport)` factories for `handle_call_tool` /
  `handle_tasks_get` / `handle_tasks_cancel` per the existing resource/prompt factory
  precedent. Option (c) is definitively rejected, not merely unconfirmed:
  `ServerRequestContext` (`mcp/server/context.py:31-49`) has **no transport field**.
  There is a tempting near-miss — `ctx.request: RequestT | None` is the attached HTTP
  request object on HTTP and `None` on stdio — but inferring transport identity from
  the *absence* of an HTTP request is fragile, undocumented SDK behavior; do not use
  it. Both signature-pin tests (`test_feat_3143_mcp_http_transport.py:67-69`,
  `test_feat_3149_transport_policy.py:103-105`) get a sanctioned edit that re-pins the
  new one-parameter signature — the pins' intent (no *accidental* widening) is
  preserved by pinning the widened shape, not by keeping them frozen. Both production
  call sites pass `transport=` explicitly (see Files to Modify); the `"stdio"` default
  exists only for the zero-arg test call sites and fails safe (over-deny) if a future
  call site forgets.
- **D2 (closes Q2): keep the middleware.** Handler-level checks become the uniform
  enforcement layer; `TransportPolicyMiddleware` stays for its pre-parse denial
  property (FEAT-3149's point). On HTTP, a denied request is therefore denied by the
  middleware *before* the handler check can run — the handler-level check on the HTTP
  path is reachable only by ASGI-bypass tests, which is the right redundancy shape.
  Add the "both layers agree" assertion to the new test module.
- **D3 (verified, not assumed): a raised `MCPError` with a custom code reaches the wire
  intact from the `on_call_tool` handler, on both transports.**
  `handler_exception_to_error_data` (`mcp/shared/jsonrpc_dispatcher.py:88-102`) returns
  `exc.error` verbatim for `MCPError`, and `modern_error_data`
  (`mcp/server/runner.py:534-548`) applies the same ladder on every transport — so
  `raise MCPError(code=POLICY_DENIED_CODE, message=decision.reason)` yields the AC's
  `-32001` JSON-RPC error over stdio and HTTP alike. The **only** mechanism that
  converts a tool-handler exception into `CallToolResult(is_error=True)` is this
  package's own catch-all at `tools.py:863-877`. That makes the insertion-point note
  ("before the `try:` block") **load-bearing, not stylistic**: a policy raise placed
  inside the `try:` is swallowed into a tool-result error and ACs 1/3 fail. Record
  this SDK finding as a learning-test entry (`.ll/learning-tests/`) per repo
  convention. Relatedly, AC 3's spawn-prevention is confirmed sound:
  `TasksExtension.intercept_tool_call` spawns nothing itself — the spawn lives inside
  `call_next` (`tasks.py:197-199,228-229`), so a guard-0 raise inside
  `handle_call_tool` propagates out through the extension before any envelope shaping.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-14 — based on codebase analysis:_

- On Open Question 1: option (c) is confirmed not free. A grep/import sweep of `scripts/little_loops/mcp_server/` found no `ContextVar`/`contextvar` usage anywhere in the package, and `ServerRequestContext` (imported in `tasks.py:41`, `server.py:23`, `tools.py:41`) exposes only `.meta` and `.protocol_version` in actual use (`tasks.py:233,239`, for SEP-2663 client-capability signals) — neither carries transport identity. The only two places a transport-identity literal exists today are both HTTP-side: `TransportPolicyMiddleware.__init__`'s `transport: str = "http"` parameter and `build_http_app`'s literal `transport="http"` call site (`server.py:53`). This leaves option (a) as the only currently-grounded route; (c) would require confirming the MCP SDK's own `ServerRequestContext` implementation exposes a transport field, which the local codebase and learning-test corpus (`.ll/learning-tests/mcp-header-routing.md`, `mcp-tasks-start-path.md`, `mcp-extension-mechanism.md`) do not settle either way — the SDK source itself is not present under this repo tree or a locally-discoverable venv path for direct inspection.
- Concrete shape for option (a): `build_server()` already has a same-function precedent for value-into-closure threading — `resource_index`/`prompt_index`/`config` are each passed into `make_*_handler(value)` factories (`server.py:90-91,112-115`) rather than the consuming handlers re-resolving state themselves. `handle_call_tool`/`handle_tasks_get`/`handle_tasks_cancel` are registered by bare function reference today (`server.py:102-105,134-135`), unlike the resource/prompt handlers — so adopting (a) would mean introducing a `make_call_tool_handler(transport)`-shaped factory for these three where none currently exists, not extending an existing one.

_Added by `/ll:refine-issue` — 2026-08-14 — based on codebase analysis:_

- On Open Question 1, option (a): the two existing pins on `build_server()`'s zero-parameter signature (`test_build_server_signature_unchanged`, `test_feat_3143_mcp_http_transport.py:67-69`; `test_build_server_signature_still_unchanged`, `test_feat_3149_transport_policy.py:103-105`) were each added by a prior feature (FEAT-3143, then FEAT-3149) that deliberately routed its own new functionality around `build_server()` specifically to keep the pin intact. No prior instance in this codebase shows that pinned signature being intentionally widened with the pin test updated to match — widening it now would be a new kind of change relative to what's on record, not a documented precedent to follow.

## Acceptance Criteria

1. With `mcp.transport_policy.stdio.allow_mutations: false`, a `tools/call` naming a
   `MUTATING_TOOLS` member over stdio is denied with `-32001`.
2. With `mcp.transport_policy.stdio.allow_tasks: false`, `tasks/get` and `tasks/cancel`
   over stdio are denied with `-32001`.
3. With `mcp.transport_policy.stdio.allow_tasks: false`, `loop_start` over stdio is
   denied with `-32001` and **no process is spawned**.
4. With the knobs unset, stdio behavior is unchanged from today (default open) — no
   existing test in `test_mcp_server.py` needs modifying to accommodate this.
5. HTTP enforcement is unchanged; `test_feat_3149_transport_policy.py` passes unmodified.
6. The "advisory" paragraph is removed from `MCP_SERVER_GUIDE.md` in the same change.
7. `python -m pytest scripts/tests/` exits 0.
8. With the stdio knobs set to `false` and the http knobs open (or unset), requests
   driven through `build_http_app()` still succeed — the handler layer evaluates the
   *http* policy on the HTTP path, not a closure-captured stdio identity (see the
   wrong-transport-closure guard in Tests).

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-14 — based on codebase analysis:_

### Types
- `PolicyDecision` (existing, `policy.py:79-84`): frozen dataclass `allowed: bool`, `reason: str = ""`. No new type is introduced by this issue.

### Signatures
- `check_tool_call(transport: str, method: str | None, tool_name: str | None, *, config: BRConfig | None = None) -> PolicyDecision` — `policy.py:87-93`. Already parameterized by `transport`; unchanged by this issue. Denial `reason` is built at `policy.py:143-150` (tasks/loop_start grant) or `:155-162` (mutations grant) and names the exact `mcp.transport_policy.<transport>.<knob>` to flip.
- `build_server() -> Server` — `server.py:56`. Confirmed zero-parameter today; pinned by two separate tests: `test_build_server_signature_unchanged` (`scripts/tests/test_feat_3143_mcp_http_transport.py:67-69`, asserts `inspect.signature(build_server).parameters == {}`) and `test_build_server_signature_still_unchanged` (`scripts/tests/test_feat_3149_transport_policy.py:103-105`).
- `run_stdio() -> None` — `server.py:140`. Zero-parameter; calls `build_server()` at line 150 with no transport-identity value available anywhere in its body — `"stdio"` exists only implicitly via the function's own name.
- `build_http_app(host: str = "127.0.0.1") -> Any` — `server.py:34`. Calls `build_server()` at line 51, then wraps the result in `TransportPolicyMiddleware(app, transport="http")` at line 53 — a literal string, not a derived or config value.
- `handle_call_tool(_ctx: ServerRequestContext[Any], params: types.CallToolRequestParams)` — `tools.py:833-834`. Single dispatch point for every `tools/call`, including `loop_start` (no separate entry point — dispatched via `_TOOL_HANDLERS["loop_start"] = _tool_loop_start` registered at `tools.py:518`, implementation at `tools.py:450-500`).
- `handle_tasks_get(...)` / `handle_tasks_cancel(...)` — `tasks.py:104-150` / `tasks.py:153-184`. Method identity (`"tasks/get"` / `"tasks/cancel"`) is implicit from SDK registration (`server.add_request_handler(...)`, `server.py:134-135`), not passed as a parameter to either function today.

### Call Path

**Today (broken)**:
- `run_stdio()` → `build_server()` → registers `handle_call_tool` / `handle_tasks_get` / `handle_tasks_cancel` by bare function reference (`server.py:102-105,134-135`) — none receives or closes over a `transport` value → `check_tool_call` is never reached over stdio.
- `build_http_app()` → `build_server()` → `TransportPolicyMiddleware(app, transport="http")` (`server.py:53`) → `check_tool_call("http", method, tool_name)` (`policy.py:197`) — confirmed by the code graph as the only live call site of `check_tool_call` in the package.

**Insertion points** (confirmed: neither `handle_call_tool` nor the tasks handlers, nor `ServerRequestContext`, currently has access to transport identity — no `ContextVar` exists anywhere in `mcp_server/`, and `ServerRequestContext`'s only read attributes, `.meta` and `.protocol_version` (`tasks.py:233,239`), carry SEP-2663 client-capability signals, not transport identity):
- `handle_call_tool` — before the existing dry-run "Guard 1" (`tools.py:844-849`), i.e. after the handler lookup at `tools.py:854` and before the `try:` block at `tools.py:863`. `params.name` is the only tool-identity datum needed; `check_tool_call` resolves `MUTATING_TOOLS` / `TASK_STARTING_TOOLS` membership itself.
- `handle_tasks_get` — top of function, before `tasks.py:122`'s `_loops_dir()` call; method is the literal `"tasks/get"` (not a variable in scope today).
- `handle_tasks_cancel` — top of function, before `tasks.py:168`'s imports; method is the literal `"tasks/cancel"`.

**Existing factory-closure precedent** for threading a value into a handler at `build_server()`-construction time (relevant to Open Question 1's option (a)): `resource_index = build_resource_index(config)` / `prompt_index = build_prompt_index(...)` are each passed into `make_list_resources_handler(resource_index)` / `make_read_resource_handler(resource_index, config)` / `make_list_prompts_handler(prompt_index)` / `make_get_prompt_handler(prompt_index)` (`server.py:90-91,112-115`) — an existing `make_*_handler(value) -> closure` shape already used in this exact function, unlike `handle_call_tool`/`handle_tasks_get`/`handle_tasks_cancel`, which are registered by bare reference today.

### Decision Rules
N/A — no new decision logic. `check_tool_call`'s classification (`is_mutating_call` / `is_task_call` / `is_task_starting_call`, `policy.py:120-122`) and its `MUTATING_TOOLS` / `TASK_STARTING_TOOLS` registries already exist and are unchanged by this issue; the work is plumbing an existing decision function's `transport` input, not authoring new decision logic.

## Impact

- **Priority**: P2 — not a live exposure (stdio is same-machine/same-user and defaults
  open), but a config knob that silently does nothing is a correctness and trust defect,
  and it now guards a run-spawning tool.
- **Effort**: Medium — the decision logic already exists and is already parameterized by
  transport; the work is plumbing identity into the handler layer plus a new test module.
- **Risk**: Low-Medium — touches the dispatch path of every tool. The default-open
  posture (AC 4) is what keeps it from breaking existing users.
- **Breaking Change**: No for anyone on defaults. For an operator who *had* set a stdio
  knob to `false`, behavior changes from "silently ignored" to "enforced" — which is the
  point, and should be called out in the changelog.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.

## Related Key Documentation

- [`docs/guides/MCP_SERVER_GUIDE.md`](../../docs/guides/MCP_SERVER_GUIDE.md)

## Resolution

- **Action**: implement
- **Completed**: 2026-08-15
- **Status**: Completed

### Changes Made
- `scripts/little_loops/mcp_server/server.py`: `build_server(transport: str = "stdio")` —
  threads transport identity into the handler factories; `build_http_app()` passes
  `transport="http"`, `run_stdio()` passes `transport="stdio"` explicitly (D1).
- `scripts/little_loops/mcp_server/tools.py`: `handle_call_tool` became
  `make_call_tool_handler(transport)`, a factory whose closure raises `MCPError(code=
  POLICY_DENIED_CODE, ...)` before the existing dry-run `try:` block (Guard 0, ahead of
  Guard 1).
- `scripts/little_loops/mcp_server/tasks.py`: `handle_tasks_get`/`handle_tasks_cancel`
  became `make_tasks_get_handler(transport)`/`make_tasks_cancel_handler(transport)`
  factories, each raising the same `MCPError` shape at the top of the handler.
- `scripts/tests/test_feat_3143_mcp_http_transport.py`,
  `scripts/tests/test_feat_3149_transport_policy.py`: re-pinned
  `build_server`'s signature to the widened one-parameter shape (Decision D1).
- `scripts/tests/test_feat_3168_stdio_policy_enforcement.py` (new): unit assertions
  against `check_tool_call("stdio", ...)` for all three surfaces, real `_stdio_roundtrip()`
  wire-level denials for AC 1-3, an in-process spawn-prevention assertion for AC 3, the
  wrong-transport-closure guard for AC 8, and a both-layers-agree assertion for HTTP
  (Decision D2).
- `docs/guides/MCP_SERVER_GUIDE.md`, `docs/reference/CLI.md`,
  `scripts/little_loops/config-schema.json`: removed the three "stdio is advisory only"
  passages now that enforcement is uniform.
- `.ll/learning-tests/mcp-stdio-policy-enforcement.md` (new): records Decision D3's SDK
  finding — a raised `MCPError` reaches the wire intact from `on_call_tool` on both
  transports, and the guard-0 raise must sit outside Guard 1's `try:` block.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 19275 passed, 43 skipped)
- Lint: PASS (`ruff check`)
- Format: PASS (`ruff format --check`)
- Types: PASS (`mypy scripts/little_loops/mcp_server/`)
- Integration: PASS

## Status

**Done** | Created: 2026-08-14 | Completed: 2026-08-15 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-15T00:16:49 - `f2a7b3a1-13a3-4789-a189-b1a33c413ed6.jsonl`
- `/ll:ready-issue` - 2026-08-14T23:58:16 - `106b1e2a-74ae-4ddb-a907-9236b65f5623.jsonl`
- `/ll:verify-issues` - 2026-08-14T23:22:40 - `e3ada8fd-7b00-4616-a2b4-3cdb1d665bcc.jsonl`
- `/ll:refine-issue` - 2026-08-14T23:20:06 - `c7faedd3-027b-4e54-b66d-0a14518cc970.jsonl`
- `/ll:verify-issues` - 2026-08-14T23:16:32 - `abed8dc6-2249-4b8a-a2a2-60359fde2b55.jsonl`
- `/ll:wire-issue` - 2026-08-14T23:13:24 - `260ef98c-37ab-4fa4-a62c-2d0e6f2777d1.jsonl`
- `/ll:refine-issue` - 2026-08-14T23:08:14 - `beca86bb-9c6b-4657-b382-6d07c5d89e00.jsonl`
