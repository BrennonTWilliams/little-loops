---
id: FEAT-3504
type: FEAT
title: Policy builder connected page and serve routes
priority: P3
status: open
discovered_by: manual-split
discovered_date: '2026-09-18'
captured_at: '2026-09-18T02:19:33Z'
parent: EPIC-3493
labels:
- policy-builder
relates_to:
- FEAT-3498
- FEAT-3503
- ENH-3487
- ENH-3491
- ENH-3492
- BUG-3490
---

# FEAT-3504: Policy builder connected page and serve routes

## Summary

Second half of the connected-execution split from FEAT-3498. FEAT-3498 (Part A, **done** — all contracts below are landed and importable) delivers the host-side contracts: the `awaiting_approval` queue status, `create_or_get_run_request`/`approve_and_claim_entry`/`record_loop_started`/`get_run_request`, `ll-queue run --id ID --approve`, builder-origin LOOP dispatch (cwd, no timeout, `--context issue_id=`), the structured start-metadata channel, and `persist_policy_revision`/`validate_policy_revision` as plain Python functions. This issue (Part B) exposes those contracts to the browser: serve the policy builder at a same-origin route, add project-scoped issue-list and request submit/readback endpoints on `SseBridge`, and wire the page's review/submission/status UI. No queue, loop, or approval semantics change here.

## Current Behavior

`ll-artifact serve` uses `SseBridge` with token/Host-checked GET routes only (`transport.py:1200-1246`, exact-string match on `_routes`; no `do_POST`, no parameterized path matching). `cmd_policy_builder` (`cli/artifact/policy_builder.py:62`) renders to a file only; the `file://` builder has no connected controls. With FEAT-3498 landed, a builder-origin request can be created and approved from Python/CLI, but nothing in the browser can submit one or observe it.

**The builder's own lifecycle output does not pass the landed validator.** `validate_policy_revision` (`cli/artifact/policy_revision.py:69`) reads the policy mode from the loop's `category:` field and accepts only `issue_lifecycle` (`_SUPPORTED_MODES`, `policy_revision.py:35`). `_serializeIssueLifecycle` (`policy_builder_core.mjs:2736`) emits no `category:` line, so all three `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle*.yaml` fixtures return `ok=False, mode=None, errors=["Unsupported policy mode None; ..."]`. Until the serializer emits `category: issue_lifecycle`, every browser submission would be rejected.

## Expected Behavior

From a same-origin connected page, a user selects an issue in the server's project, reviews an immutable policy snapshot, and submits a request. The host sees the exact project/issue/revision and explicitly runs or rejects that one request via FEAT-3498's `ll-queue run --id ID --approve`. The browser observes approval, running/completion/failure/rejection and the real loop instance identifier once execution starts. Network failures preserve the draft and suite.

## Motivation

Without this half, FEAT-3498's approval contracts are reachable only from Python and `ll-queue`; the policy builder stays a `file://` export tool and the authoring-to-execution gap in EPIC-3493 remains open. Splitting it out keeps the transport/page surface (Host/token, POST hardening, renderer split, UI state) reviewable on its own and lets FEAT-3498's concurrency risk land and stabilize first.

## Proposed Solution

### Scope and origin

- Add an opt-in flag on `ll-artifact serve` (registered in `add_serve_parser()`, `cli/artifact/serve.py:37`); no config flag is needed. Serve the builder at `GET /{token}/policy-builder` using a renderer factored from `cmd_policy_builder`, with the endpoint URL and server-derived workspace identifier stamped in. The `file://` copy stays offline-only. Preserve Host/token checks for every method and route; no CORS headers.
- First connected release accepts `issue_lifecycle` policies only. Rubric requires a subject and other modes need different binding contracts; keep their offline exports available and explain why connected Run is unavailable.
- Bind repository identity and filesystem access to `BRConfig.project_root`, never a browser-supplied path. Add a project-scoped issue-list/read endpoint using existing issue discovery. `projectId` from ENH-3487 identifies the builder document, not the repository. Reject cross-workspace requests. The serve process anchors the queue db at `BRConfig.project_root` via the `db_path`/`root` parameters FEAT-3498 adds.
- **Workspace identifier**: no derivation helper exists today. Define `workspace_id` as a deterministic function of the resolved project root — `hashlib.sha256(str(config.project_root.resolve()).encode()).hexdigest()[:16]` — so it is stable across serve restarts. It must **not** be derived from the per-process serve token: request dedup and readback both key on `(workspace_id, request_id)`, so a per-process value would break the reload/retry acceptance criterion. The server stamps it into the page and rejects any submit/readback whose `workspaceId` differs.
- **Builder emit fix (prerequisite)**: `_serializeIssueLifecycle` emits `category: issue_lifecycle` so its output passes `validate_policy_revision`. Regenerate the `sample-issue-lifecycle*.yaml` golden fixtures. This is the first time builder-emitted YAML meets the validator; FEAT-3498's tests used hand-built YAML.

### Renderer split

`cmd_policy_builder` has a clean split point: `BRConfig` construction through the five `html.replace(...)` injections (lines 73-115) is pure computation producing an in-memory `html` string; only the output-dir resolution and `write_text`/`logger.success` tail (lines 117-125) is CLI-specific. Factor a `render_policy_builder_html(config, *, active_theme, endpoint_url=None, workspace_id=None) -> str` and make `cmd_policy_builder` a thin wrapper. Precedent: `_make_page_html_factory` (`cli/artifact/serve.py:138`) builds HTML from config and hands it to `bridge.set_page_html(...)`. The byte-identity golden test in `test_enh3035_artifact_template_kit.py` must still pass for the CLI path.

### Routes and POST handling

- Add method-aware dispatch plus bounded parameterized path matching in `SseBridge`: `POST /{token}/run-request`, `GET /{token}/run-request/{requestId}`, `GET /{token}/issues`, `GET /{token}/policy-builder`. Existing exact GET/history/SSE routes keep working. Factor the Host-header check and token prefix-strip out of `do_GET` into a shared helper so `do_POST` does not duplicate it.
- POST hygiene: cap the request body at a fixed module constant, `_MAX_RUN_REQUEST_BYTES = 1 << 20` (1 MiB); `Content-Length` above it returns `413`. Do **not** reuse `artifacts.export.max_artifact_bytes` — that key governs outbound history-snapshot exports, which is the wrong meaning and far too large a bound for a policy YAML. Missing/invalid `Content-Length`, non-`application/json` Content-Type, or a JSON parse failure returns `400`. Do not copy `LocalBridgeTransport`'s `do_POST` (`transport.py:693-698`), which reads `Content-Length` uncapped.
- **Error body and status codes** (no JSON error convention exists in `transport.py`/`serve.py` yet; this issue establishes it). Every non-2xx response from the new routes is `application/json` with the shape `{"error": {"code": "<slug>", "message": "<text>", "errors": [...], "warnings": [...]}}` (`errors`/`warnings` present only for validation failures):

  | Status | `code` | When |
  |---|---|---|
  | `400` | `bad_request` | missing/invalid `Content-Length`, wrong Content-Type, JSON parse failure, missing/mistyped payload field |
  | `413` | `body_too_large` | `Content-Length` > `_MAX_RUN_REQUEST_BYTES` |
  | `422` | `revision_mismatch` | recomputed SHA-256 ≠ `revisionId` |
  | `403` | `wrong_workspace` | `workspaceId` ≠ the server's |
  | `404` | `issue_not_found` / `request_not_found` | issue absent from the project; `get_run_request` returned `None` |
  | `422` | `validation_failed` | `ValidationOutcome.ok` is False (includes unsupported mode); carries `errors` and `warnings` |
  | `409` | `request_conflict` | `create_or_get_run_request` raised `ValueError` (same request UUID, different revision/issue/project) or `persist_policy_revision` raised `PolicyRevisionConflictError` |
- Serve routes only submit/read requests. They never approve, drain, launch a process, or use `LocalBridgeTransport`/level-3 interactions. An AST import guard is supplementary; the authoritative test submits through the route while a real queue watcher is active and asserts zero dispatches before explicit approval.
- Submit path, cheapest checks first so junk POSTs never reach the filesystem (`validate_policy_revision` writes a temp file under `.loops/policy-builder/`):
  1. Body guards (size, Content-Type, JSON parse, field presence/types) → build `RunRequest` with `yaml` encoded to UTF-8 bytes.
  2. Recompute `hashlib.sha256(yaml_bytes).hexdigest()` and reject a mismatch with `revisionId`. **This check lives only in the route**: `persist_policy_revision` does *not* recompute the hash (it uses `revision_id[:12]` as the filename and compares bytes only when that file already exists), despite what the `RunRequest` docstring implies. Correct that docstring as part of this issue.
  3. `workspaceId` equals the server's.
  4. The issue exists in the project (existing issue discovery under `BRConfig.project_root`).
  5. `validate_policy_revision(yaml_bytes, project_root=config.project_root)`; `ok=False` returns `422` with `errors` and `warnings` and enqueues nothing.
  6. `dest = persist_policy_revision(yaml_bytes, revision_id, project_root=config.project_root)`.
  7. Build the action the store requires — `ActionSpec(name=f"policy-builder:{issue_id}", runner=RunnerType.LOOP, target=str(dest), timeout=None)` (`timeout=None` is mandatory: the `ActionSpec` default of 120 s would kill a real lifecycle run) — then `entry, created = create_or_get_run_request(request, action=action, project_root=config.project_root, root=config.project_root)`.
  8. Return `200 {requestId, queueId: entry.id, created}`.
- Readback: `GET /{token}/run-request/{requestId}?workspaceId=...` → `get_run_request(request_id, workspace_id, root=config.project_root)`, which returns `QueueEntry | None` (there is no `RunRequestStatus` type; the route builds the wire dict). `None` → `404 request_not_found`. Otherwise `{requestId: entry.request_id, queueId: entry.id, status: entry.status, bindings: {issueId: entry.issue_id, revisionId: entry.revision_id}, loopInstanceId: entry.loop_instance_id, runDir: entry.run_dir, result: entry.result}`. Never pass a request UUID to `get_entry`.
- Host rejection is `ll-queue cancel`, which surfaces as `status: "cancelled"`. There is no distinct "rejected" status; the page labels `cancelled` on a never-approved request as "Rejected by host".

### Page behavior

- Request payload: `{requestId, projectId, workspaceId, revisionId, yaml, issueId}`. Freeze the YAML snapshot at submission; `revisionId` is SHA-256 of its exact UTF-8 bytes via `crypto.subtle` (serve binds loopback only, so the page is a secure context). Later draft edits leave the queued revision unchanged and mark the UI as showing an older submitted snapshot; disable submitting a changed preview until its snapshot is rebuilt.
- Generate the request UUID once per explicit submission and persist it with client submission state outside undoable authoring history. Retries, reconnects, and reloads reuse it; a deliberate Run again gets a new UUID after an explicit user action.
- Poll the readback route; keep authoring usable while hashing/request I/O is in flight. Offline (`file://`) and non-lifecycle pages show connected controls unavailable with a reason.
- Test UTF-8/hash parity with Python, including non-ASCII YAML.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- The only existing "connected controls" gating in a browser template is whole-block presence/absence via template conditionals (`dashboard.llat/template.html.j2:356-380`'s `[[% if serve_enabled %]]`), driven by an always-present boolean computed from `serve_context is not None` (`cli/artifact/dashboard.py:322`). No existing template shows a control in a visibly-disabled state annotated with an unavailability-reason string — the "connected controls unavailable with a reason" UI this issue proposes for offline/non-lifecycle pages has no in-repo convention to follow.
- No `crypto.subtle` usage and no existing JS-side/Python-side SHA-256 parity test exists anywhere in this codebase (repo-wide search, zero hits) — the browser/Python hash-parity requirement is new surface with no established pattern to reuse.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs`: build immutable lifecycle submission snapshots; do not run actions from scenario evaluation.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: same-origin availability, issue selection, review/submission/status UI, durable request retry metadata outside undo history.
- `scripts/little_loops/cli/artifact/policy_builder.py`: `render_policy_builder_html` renderer; `cmd_policy_builder` becomes the CLI wrapper.
- `scripts/little_loops/cli/artifact/serve.py`, `cli/artifact/__init__.py`: opt-in flag and project/issue/page/request routes.
- `scripts/little_loops/transport.py`: shared Host/token helper, `do_POST`, parameterized route matching with body-size and content-type guards.

### Dependent Files (Callers/Importers)

- `scripts/tests/test_enh3035_artifact_template_kit.py` (line 19,65) — calls `cmd_policy_builder` directly and holds the byte-identical golden-HTML assertion; must pass unchanged after the renderer split.
- `scripts/tests/test_policy_builder_emit.py` — calls `cmd_policy_builder` directly (its golden tests cover YAML fixtures, not HTML).
- `scripts/tests/test_transport.py::TestLocalBridgeTransport` (line 1052-1295) — POST dispatch precedent using `_lb_http_request`; model for new `SseBridge.do_POST` tests.
- `scripts/tests/test_wiring_reference_docs.py` — parametrized `DOC_STRINGS_PRESENT` table (line 215-224); new row once the level-2 render target is declared in `ARTIFACT_CONTROL_LEVELS.md`.

### Tests

- New `SseBridge` tests: method-aware dispatch, parameterized path bounds, 400/413 body guards, Host/token rejection on every new route, no CORS headers, existing GET/history/SSE tests unchanged.
- Route-level submit tests against a real queue watcher: zero dispatches before approval; concurrent duplicate submits map to one queue UUID; conflicting payload under one request UUID fails; revision-hash mismatch, missing issue, wrong workspace, unsupported mode, and ERROR diagnostics are rejected with structured bodies and no row.
- Node/browser-side tests for snapshot freezing, request-UUID persistence outside undo history, and SHA-256 parity with Python (non-ASCII YAML).
- Golden and applicable local pytest/Node gates pass.

### Documentation

- `docs/reference/API.md` `### SseBridge` section (heading near line 11448; existing prose near line 11482 "Extra `GET` routes...") — describe method-aware POST dispatch and parameterized matching while preserving the Host/token security contract.
- `docs/reference/CLI.md` — `ll-artifact policy-builder` subsection (lines 5081-5102) and `ll-artifact serve` subsection (lines 5192-5257): opt-in flag and the connected route.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — add level-2 row to `## Declared levels by render target` (line 49-59): `| \`ll-artifact serve\`'s policy-builder route (FEAT-3504; connected same-origin authoring + submission with host approval via FEAT-3498, project-scoped issue binding, immutable revision persistence) | 2 (project-local) |`.
- `docs/guides/POLICY_ROUTER_GUIDE.md` — cross-link the level-2 declaration per the "**Binding now:**" requirement in `ARTIFACT_CONTROL_LEVELS.md:61-63`; document the connected flow and local-only verification instructions.
- `docs/ARCHITECTURE.md` `## Artifact Control Layer` (line 920-936) — mention the serve submit/readback routes alongside `_drain_inbound()` if warranted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- `little_loops.queue_store` currently defines `QUEUE_STATUSES = frozenset({"pending","running","done","failed","dead_letter","cancelled"})` (`queue_store.py:155`, re-exported `:43`) with no `awaiting_approval` value; `little_loops.cli.artifact.policy_revision` is absent from the source tree. None of FEAT-3498's `RunRequest`, `validate_policy_revision`, `persist_policy_revision`, `create_or_get_run_request`, `approve_and_claim_entry`, `record_loop_started`, `get_run_request` resolve anywhere in `.py` source (repo-wide search, zero hits outside `.issues/features/*.md`) — confirms `blocked_by: FEAT-3498` is load-bearing and current, not stale.
- `SseBridge`'s handler (`_make_sse_bridge_handler`, `transport.py:1200`) defines only `do_GET` (`transport.py:1209-1245`); no `do_POST` method exists on this class today.

## Implementation Steps

1. Factor `render_policy_builder_html` from `cmd_policy_builder`; golden byte-identity test still passes.
2. Add the shared Host/token helper, `do_POST`, parameterized matching, and body guards to `SseBridge` with transport tests; existing GET/SSE tests unchanged.
3. Add the opt-in serve flag, page route, issue-list route, submit route (calling FEAT-3498's validate/persist/create-or-get), and readback route; route-level tests against a live watcher.
4. Wire the page: snapshot freezing, hashing, request-UUID persistence, submit/poll/status UI, offline and non-lifecycle unavailability messaging.
5. Update docs, golden output, and the `ARTIFACT_CONTROL_LEVELS.md` level-2 declaration.

## Program Design

### Types

- `RunRequest`, `RunRequestStatus`, `ValidationOutcome` — imported from FEAT-3498's `little_loops.cli.artifact.policy_revision` and `little_loops.queue_store`; this issue serializes them, it does not redefine them.
- `IssueSummary {id, title, priority, status, path}` — wire shape of `GET /{token}/issues`, built from existing issue discovery under `BRConfig.project_root`.

### Signatures

- `render_policy_builder_html(config: BRConfig, *, active_theme: str, endpoint_url: str | None = None, workspace_id: str | None = None) -> str` — factored from `cmd_policy_builder` (`cli/artifact/policy_builder.py:62`); with both keyword args `None` the output is byte-identical to today's CLI file.
- `SseBridge.add_route(method: str, pattern: str, handler)` — pattern is a literal path with at most one `{name}` segment; matching is anchored, single-segment, and bounded (no regex from user input). `do_POST` reuses a `_check_host_and_strip_token(handler) -> str | None` helper factored out of `do_GET` (`transport.py:1200-1246`).
- `make_run_request_routes(config: BRConfig, *, workspace_id: str) -> list[tuple[str, str, handler]]` in `cli/artifact/serve.py` — submit, readback, and issue-list handlers; each calls FEAT-3498 functions with `root=config.project_root`.

### Call Path

`ll-artifact serve --<opt-in flag>` → `cmd_serve` builds `render_policy_builder_html(...)` once and registers the page, issues, submit, and readback routes on `SseBridge` → browser `POST /{token}/run-request` → body guards → `RunRequest` → `validate_policy_revision` → `persist_policy_revision` → `create_or_get_run_request` (row `awaiting_approval`) → `{requestId, queueId, created}`. Browser polls `GET /{token}/run-request/{requestId}` → `get_run_request` → `RunRequestStatus`. Host approval and execution are FEAT-3498's `ll-queue run --id ID --approve`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- `SseBridge._routes: dict[str, Callable[[http.server.BaseHTTPRequestHandler], None]]` is built in `__init__` (`transport.py:1285-1290`): seeded with `{"": self._serve_page, "events": self._serve_events}`, then `.update(routes)` for caller-supplied extras (e.g. `cli/artifact/serve.py:189`'s `"history"` route). `do_GET` (`transport.py:1221-1245`) strips the `/{token}` prefix, looks up the remaining suffix as an exact dict key via `bridge._routes.get(route)`, and 404s on a miss — no `{name}`-segment or regex matching exists anywhere in this dict-based dispatch.
- A bare `/{token}` path (no trailing slash) issues a `301` redirect to `/{token}/` (`transport.py:1228-1234`) before route lookup; `LocalBridgeTransport`'s separate `_route()` (`transport.py:638-646`) instead accepts both forms as route `""` with no redirect. The new parameterized matcher inherits one of these two prefix-handling behaviors — they are not currently unified.
- `LocalBridgeTransport._handle_interaction` (`transport.py:692-716`) is the uncapped precedent the issue warns against: it parses `Content-Length` with a bare `try/except ValueError: length = 0` (no upper-bound check, `transport.py:693-696`), always responds `204` before parsing the body (`transport.py:699-702`), and on a JSON-parse or type failure only calls `_record_inbound_drop(...)` — it never returns a 400/413 status. Every existing error response in `transport.py`/`cli/artifact/serve.py` uses stdlib `send_error()`'s text/html body or a hand-built `text/plain` body (the one existing size-driven `413`, `cli/artifact/serve.py:102-109`, guards an *outbound* export against `artifacts.export.max_artifact_bytes`, not an inbound POST); no JSON-structured error-body convention exists yet in this code to reuse.
- No `{name}`-segment path-param matcher (regex or otherwise) exists anywhere in `scripts/little_loops/**/*.py` today (repo-wide search, no hits) — `SseBridge.add_route`'s bounded single-segment matching has no in-repo precedent to model; it is new surface, not an extension of an existing pattern.
- The renderer-factoring precedent is `build_dashboard_html` (`cli/artifact/dashboard.py:257`, a keyword-only function returning a `RenderedDashboard`) plus its CLI wrapper `cmd_dashboard` (`dashboard.py:398`, which does `write_text`/`logger.success`/`logger.error`) — `_make_page_html_factory` (`serve.py:138`) is a second *consumer* of that same renderer, not itself the factoring precedent. `cmd_policy_builder` is today the only other HTML-emitting `cli/artifact/*.py` command with no such split (`policy_builder.py:62-128`, inline `try`/`write_text` in one function) — this issue's renderer split is the first of its kind for this file, following an established sibling pattern rather than inventing one.
- `_lb_http_request` (`test_transport.py:963-989`) — not the `TestLocalBridgeTransport` class body generally — is the exact helper that drives real HTTP GET/POST requests over a loopback `http.client.HTTPConnection` with explicit `Host`-header control; existing POST call sites (`test_transport.py:1192`, `:1223-1225`) are the direct model for new `SseBridge.do_POST` tests.

## Use Case

A maintainer opens the served builder, picks BUG-123 from the project's issue list, reviews the frozen lifecycle policy, and submits. The page shows "awaiting approval" with the request and queue IDs. From a terminal the maintainer runs `ll-queue run --id ID --approve`; the page transitions to running, shows the real loop instance ID and run dir, then the result, while the author's current draft stays editable and marked as newer than the submitted revision.

## Impact

- Priority: P3 — closes the browser-to-host gap once FEAT-3498's contracts exist.
- Effort: Medium — transport, renderer split, page wiring, docs.
- Risk: Medium — transport surface hardening; the concurrency risk lives in FEAT-3498.

## Acceptance Criteria

- [ ] Submitting through the route while a watcher runs produces `awaiting_approval` and zero subprocess dispatches; serve cannot approve/run; production behavioral tests enforce the level boundary.
- [ ] Existing Host/token checks cover every new route and method; existing GET/history/SSE tests pass; no CORS headers; oversized, non-JSON, or malformed bodies return 413/400 with no side effects.
- [ ] Concurrent duplicate submits, reload/retry, and retries after terminal completion map to one queue UUID; conflicting payloads under one request UUID fail; explicit Run again creates a fresh awaiting request.
- [ ] Invalid YAML, ERROR diagnostics, missing issue, wrong workspace, unsupported mode, and revision-hash mismatch are rejected with structured diagnostics and no runnable entry.
- [ ] Browser SHA-256 of the UTF-8 YAML bytes matches Python, including non-ASCII content.
- [ ] Readback exposes status, bindings, `loopInstanceId`, and `runDir` while running and after completion, distinct from request/queue IDs.
- [ ] Offline/non-lifecycle pages show connected controls unavailable with a reason; connection failure/reload retains authoring/scenarios and submission identity; edited drafts distinguish current and submitted revisions.
- [ ] `cmd_policy_builder`'s CLI output is byte-identical to the golden fixture after the renderer split.
- [ ] Connected builder is documented at level 2 with local-only verification instructions; golden and applicable local pytest/Node gates pass.

## Scope Boundaries

Includes the same-origin page, issue-list/submit/readback routes, POST dispatch on `SseBridge`, and page UI. Excludes any queue/loop/approval semantics (FEAT-3498), autonomous page/serve execution, remote shell APIs, level-3 event interception, all-mode connected inputs, arbitrary YAML import, and the `_ResourceEntry` control-level forward slot.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-18 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-18T02:34:20 - `e526fcc4-a04f-4fa1-9b46-7e10044a1c18.jsonl`
- `/ll:format-issue` - 2026-09-18T02:26:59 - `17fa148c-98f6-4a6e-975e-5e4a6f742eec.jsonl`
