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
confidence_score: 85
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
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

- Add the opt-in `--policy-builder` flag on `ll-artifact serve` (registered in `add_serve_parser()`, `cli/artifact/serve.py:37`); no config flag is needed. Without this flag, none of the four connected routes is registered. With it, print the full tokenized builder URL alongside the existing serve URL. Serve the builder at `GET /{token}/policy-builder` using a renderer factored from `cmd_policy_builder`, with a server-derived connected context (`{workspaceId}`) stamped in. **No endpoint URL is stamped**: the page is served under the token prefix, so it calls its routes with relative URLs (`./run-request`, `./run-request/{id}`, `./issues`). This keeps rendering independent of the bridge (the token exists only after `SseBridge` binds) and makes "persist request data, not a tokenized endpoint" hold by construction. The `file://` copy stays offline-only. Preserve Host/token checks for every method and route; no CORS headers.
- First connected release accepts `issue_lifecycle` policies only. Rubric requires a subject and other modes need different binding contracts; keep their offline exports available and explain why connected Run is unavailable.
- Bind repository identity and filesystem access to `BRConfig.project_root`, never a browser-supplied path. Add a project-scoped issue-list/read endpoint using `find_issues(config)` (`little_loops.issue_parser`) with its default `status_filter` — active issues only (done/cancelled/deferred excluded); the same call backs the new-request issue-exists check in submit step 5. `projectId` from ENH-3487 identifies the builder document, not the repository. Reject cross-workspace requests. The serve process anchors the queue db at `BRConfig.project_root` via the `db_path`/`root` parameters FEAT-3498 adds.
- **Workspace identifier**: no derivation helper exists today. Define `workspace_id` as a deterministic function of the resolved project root — `hashlib.sha256(str(config.project_root.resolve()).encode()).hexdigest()[:16]` — so it is stable across serve restarts. **Resolve the root once** in `cmd_serve` (`root = config.project_root.resolve()`) and use that single value for `workspace_id`, the step-4 binding comparison, `create_or_get_run_request(project_root=..., root=...)`, `validate_policy_revision`, and `persist_policy_revision`: the store binds on `str(project_root)`, so a symlinked cwd on a later restart would otherwise keep the workspace ID but change the stored string and turn an exact retry into a `409`. It must **not** be derived from the per-process serve token: request dedup and readback both key on `(workspace_id, request_id)`, so a per-process value would break the reload/retry acceptance criterion. The server stamps it into the page and rejects any submit/readback whose `workspaceId` differs.
- **Builder emit fix (prerequisite)**: `_serializeIssueLifecycle` emits `category: issue_lifecycle` so its output passes `validate_policy_revision`. Regenerate the `sample-issue-lifecycle*.yaml` golden fixtures. This is the first time builder-emitted YAML meets the validator; FEAT-3498's tests used hand-built YAML.

### Renderer split

`cmd_policy_builder` has a clean split point: `BRConfig` construction through the five `html.replace(...)` injections (lines 73-115) is pure computation producing an in-memory `html` string; only the output-dir resolution and `write_text`/`logger.success` tail (lines 117-125) is CLI-specific. Factor a `render_policy_builder_html(config, *, workspace_id=None) -> str` (the active theme is derived from `config` inside, as today) and make `cmd_policy_builder` a thin wrapper. Add one new placeholder, `/*__CONNECTED_CONTEXT_JSON__*/`, replaced with `json.dumps({"workspaceId": workspace_id})` when serving and `null` for the offline CLI output. Precedent: `_make_page_html_factory` (`cli/artifact/serve.py:138`) builds HTML from config and hands it to `bridge.set_page_html(...)`. The byte-identity golden test in `test_enh3035_artifact_template_kit.py` must pass unchanged at step 1 (pure refactor); the golden is regenerated once in step 4 when the template gains the placeholder and connected UI, after which the CLI path must match the regenerated golden.

### Routes and POST handling

- Add method-aware dispatch plus bounded parameterized path matching in `SseBridge`: `POST /{token}/run-request`, `GET /{token}/run-request/{requestId}`, `GET /{token}/issues`, `GET /{token}/policy-builder`. Existing exact GET/history/SSE routes keep working. Factor the Host-header check and token prefix-strip out of `do_GET` into a shared helper so `do_POST` does not duplicate it. **Plumbing**: `SseBridge` takes routes in its constructor (before the token exists) and `serve_sse_bridge` owns both construction and `print(bridge.url)`, so add a keyword-only `method_routes: list[tuple[str, str, handler]] | None = None` to both (the existing GET-only `routes` dict is unchanged and still checked first by exact match), plus `extra_url_suffixes: list[str] | None = None` on `serve_sse_bridge`, which prints `bridge.url + suffix` for each after the main URL (`["policy-builder"]` here). Handlers for parameterized routes receive the captured segment as a second argument.
- POST hygiene: cap the request body at a fixed module constant, `_MAX_RUN_REQUEST_BYTES = 1 << 20` (1 MiB); `Content-Length` above it returns `413`. Do **not** reuse `artifacts.export.max_artifact_bytes` — that key governs outbound history-snapshot exports, which is the wrong meaning and far too large a bound for a policy YAML. Missing/invalid `Content-Length`, non-`application/json` Content-Type, or a JSON parse failure returns `400`. Do not copy `LocalBridgeTransport`'s `do_POST` (`transport.py:693-698`), which reads `Content-Length` uncapped.
- **Error body and status codes** (no JSON error convention exists in `transport.py`/`serve.py` yet; this issue establishes it). After successful Host/token checks and dispatch to a registered connected route, every non-2xx application response is `application/json` with the shape `{"error": {"code": "<slug>", "message": "<text>", "errors": [...], "warnings": [...]}}` (`errors`/`warnings` present only for validation failures):

  | Status | `code` | When |
  |---|---|---|
  | `400` | `bad_request` | missing/invalid `Content-Length`, wrong Content-Type, JSON parse failure, missing/mistyped/malformed payload field (see field shapes below) |
  | `413` | `body_too_large` | `Content-Length` > `_MAX_RUN_REQUEST_BYTES` |
  | `422` | `revision_mismatch` | recomputed SHA-256 ≠ `revisionId` |
  | `403` | `wrong_workspace` | `workspaceId` ≠ the server's |
  | `404` | `issue_not_found` / `request_not_found` | issue absent from the project; `get_run_request` returned `None` |
  | `422` | `validation_failed` | `ValidationOutcome.ok` is False (includes unsupported mode); carries `errors` and `warnings` |
  | `409` | `request_conflict` | `create_or_get_run_request` raised `ValueError` (same request UUID, different revision/issue/project) or `persist_policy_revision` raised `PolicyRevisionConflictError` |
- **Transport error boundary**: preserve existing pre-dispatch Host/token failures (`403`/`404` with stdlib HTML bodies), unknown-route errors, and the existing bare-token GET redirect. They are outside the connected application `ErrorBody` contract. The browser checks status and Content-Type before decoding JSON and reports a connection/authorization failure for non-JSON responses without deleting submission state. Test both HTML transport rejection and JSON application rejection; do not change legacy GET/history/SSE response contracts.
- Serve routes only submit/read requests. They never approve, drain, launch a process, or use `LocalBridgeTransport`/level-3 interactions. An AST import guard is supplementary; the authoritative test submits through the route while a real queue watcher is active and asserts zero dispatches before explicit approval.
- Submit path, cheapest checks first so junk POSTs never reach the filesystem (`validate_policy_revision` writes a temp file under `.loops/policy-builder/`):
  1. Body guards (size, Content-Type, JSON parse, field presence/types/shapes) → build `RunRequest` with `yaml` encoded to UTF-8 bytes. Field shapes: `requestId` is a canonical lowercase UUID (`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`); `revisionId` is `^[0-9a-f]{64}$` (it feeds a filename via `revision_id[:12]`); `workspaceId` is `^[0-9a-f]{16}$`; `projectId` and `issueId` are non-empty strings ≤ 128 chars (`issueId` is further constrained by the issue lookup). The readback path segment applies the same `requestId` UUID check and returns `400 bad_request` otherwise.
  2. Recompute `hashlib.sha256(yaml_bytes).hexdigest()` and reject a mismatch with `revisionId`. **This check lives only in the route**: `persist_policy_revision` does *not* recompute the hash (it uses `revision_id[:12]` as the filename and compares bytes only when that file already exists), despite what the `RunRequest` docstring implies. Correct that docstring as part of this issue.
  3. `workspaceId` equals the server's.
  4. Look up `get_run_request(request_id, workspace_id, root=config.project_root)` **before mutable issue/validator checks**. For an existing row, compare `revision_id`, `issue_id`, and `project_root` using the same binding contract as `create_or_get_run_request`; mismatch returns `409 request_conflict`, otherwise return `200 {requestId, queueId: entry.id, created: false}` regardless of terminal status. This path does not revalidate the YAML, require the issue still to exist, or re-persist the revision. The supplied YAML hash must still match step 2. Existing storage does not bind the builder-document `projectId`; retain it in the client request envelope but do not claim server-side document-ID conflict detection in this issue.
  5. For a new request only, require the issue to exist in the project (existing issue discovery under `BRConfig.project_root`). A missing issue returns `404 issue_not_found`.
  6. For a new request only, `validate_policy_revision(yaml_bytes, project_root=config.project_root)`; `ok=False` returns `422` with `errors` and `warnings` and enqueues nothing.
  7. `dest = persist_policy_revision(yaml_bytes, revision_id, project_root=config.project_root)`.
  8. Build `ActionSpec(name=f"policy-builder:{issue_id}", runner=RunnerType.LOOP, target=str(dest), timeout=None)` (`timeout=None` is mandatory: the default of 120 s would kill a real lifecycle run), then call `create_or_get_run_request(request, action=action, project_root=config.project_root, root=config.project_root)`. The early lookup is an optimization, not a replacement for the store's transactional binding check: two first submissions may both miss it, and the final create-or-get still guarantees one row or a conflict.
  9. Return `200 {requestId, queueId: entry.id, created}`. Exact retries after issue removal or validator changes return the original row; genuinely new requests still undergo every creation check.
- Readback: `GET /{token}/run-request/{requestId}?workspaceId=...` → `get_run_request(request_id, workspace_id, root=config.project_root)`, which returns `QueueEntry | None` (there is no `RunRequestStatus` type; the route builds the wire dict). `None` → `404 request_not_found`. Otherwise `{requestId: entry.request_id, queueId: entry.id, status: entry.status, bindings: {issueId: entry.issue_id, revisionId: entry.revision_id}, loopInstanceId: entry.loop_instance_id, runDir: entry.run_dir, result: entry.result}`. Never pass a request UUID to `get_entry`.
- Host rejection is `ll-queue cancel`, which surfaces as `status: "cancelled"`. There is no distinct "rejected" status; the page labels `cancelled` as "Rejected / cancelled by host".

### Page behavior

- Request payload: `{requestId, projectId, workspaceId, revisionId, yaml, issueId}`. At the explicit submission action, synchronously freeze **all** unhashed fields `{requestId, projectId, workspaceId, issueId, yaml}` and an operation generation before the first await. Hash the frozen YAML's exact UTF-8 bytes with `crypto.subtle`; never reread current selection, project, or draft to finish that request. Later draft edits leave the snapshot unchanged and mark the UI as showing an older snapshot; a changed preview requires rebuilding/reviewing its snapshot before a new submission.
- Persist the **complete hashed request envelope** outside undoable authoring history **before POST**. Retries/reloads resend those exact fields and bytes with the same UUID; never regenerate YAML from the current draft for a retry. A deliberate Run again creates a new UUID and a newly reviewed envelope. If durable storage fails, report it and do not POST; authoring remains usable. This keeps the reload/retry guarantee honest.
- Maintain a per-submission operation identity and a submission-in-flight guard: repeated clicks while hashing/submitting reuse or ignore the pending action, never generate multiple request UUIDs. Open, workspace/document changes, or issue-selection changes while hashing invalidate automatic dispatch of that pending operation; no POST occurs until the user submits in the new context. Draft edits alone may continue while the frozen request completes. Responses/polls update only the matching `{workspaceId, projectId, requestId}` record, never the active document or a newer request by accident. An already-sent request is not cancelled by changing authoring context.
- Poll readback every 2 s while keeping authoring usable; stop on a terminal status (`done`, `failed`, `dead_letter`, `cancelled`) and pause (without clearing state) after a transport/authorization failure until the user retries. On reload, reconcile a persisted envelope through readback; if unknown, an explicit retry sends the same envelope. A lost response after server acceptance must recover the existing queue ID without a second request. Offline (`file://`) and non-lifecycle pages show connected controls unavailable with a reason.
- **Storage and token rotation:** browser storage is origin-scoped, but its connected authoring and submission keys must also include the server-derived `workspaceId`; submission records additionally include `projectId` and `requestId`. Two repositories served at the same origin must not restore each other's drafts, issue selection, or pending submissions. Keep the offline storage path compatible; do not migrate unscoped data into a workspace automatically. Persist request data, not a tokenized endpoint as authority.
- **Restart recovery requires the new URL.** `SseBridge` generates a fresh token on each construction. Pinning `--port` preserves the storage origin but does not keep the old URL working. After restart, the user opens the newly printed tokenized builder URL; that page restores its matching workspace/document state and uses its own token-relative URLs for readback/retry. The old page reports disconnection/authorization failure and preserves state; it cannot discover the new token automatically. Document the same-origin limitation, stable hostname/port, new-URL step, and workspace isolation.
- **The submission state machine lives in `policy_builder_core.mjs`, not the `.tmpl`.** The Node gate imports only the `.mjs`; the template's inline script (including today's draft storage at `policy-router-builder.html.tmpl:346-420`) is untested. Export a `createSubmissionController({fetch, storage, subtle, setTimeout, clearTimeout, randomUUID, connectedContext})` that owns envelope freezing, hashing, persist-before-POST, the in-flight/generation guards, request-scoped response routing, polling, reload reconciliation, and workspace-scoped storage keys, and exposes state + a change callback. The `.tmpl` only constructs it with the real browser globals and binds DOM events/rendering. Every page-behavior test below runs against this controller with fakes. For context-change invalidation, follow the existing `_beginRead`/`boundProject` stale-guard in the import handler (`policy-router-builder.html.tmpl:1655`) — the one in-repo precedent for these guards.
- Hashing lives in `policy_builder_core.mjs` as an exported async function over `globalThis.crypto.subtle` (available in Node ≥ 22 as well as the browser), so UTF-8/hash parity with Python — including non-ASCII YAML — is tested under the existing pytest-wrapped Node gate (`scripts/tests/test_policy_builder_node_gate.py`) with no browser.
- **FEAT-3503 overlap**: FEAT-3503 (scenario boundary suggestions + local issue-file import) edits the same `.mjs`/`.tmpl` files. Its local file import is an offline, scenario-authoring input; this issue's issue list is the connected, server-scoped run binding. They do not share state. FEAT-3503 is now **done**, so build this on top of its landed `.mjs`/`.tmpl` changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- The only existing "connected controls" gating in a browser template is whole-block presence/absence via template conditionals (`dashboard.llat/template.html.j2:356-380`'s `[[% if serve_enabled %]]`), driven by an always-present boolean computed from `serve_context is not None` (`cli/artifact/dashboard.py:322`). No existing template shows a control in a visibly-disabled state annotated with an unavailability-reason string — the "connected controls unavailable with a reason" UI this issue proposes for offline/non-lifecycle pages has no in-repo convention to follow.
- No `crypto.subtle` usage and no existing JS-side/Python-side SHA-256 parity test exists anywhere in this codebase (repo-wide search, zero hits) — the browser/Python hash-parity requirement is new surface with no established pattern to reuse.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs`: emit `category: issue_lifecycle` from `_serializeIssueLifecycle`; exported SHA-256 helper; `createSubmissionController` (dependency-injected: envelope freezing, persist-before-POST, operation guards, polling, reload reconciliation, workspace-scoped keys); do not run actions from scenario evaluation.
- `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle*.yaml`: regenerate goldens for the added `category:` line.
- `scripts/little_loops/cli/artifact/policy_revision.py`: correct the `RunRequest` docstring (the route, not `persist_policy_revision`, recomputes the hash).
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: `/*__CONNECTED_CONTEXT_JSON__*/` placeholder; construct the controller with browser globals; DOM binding only — issue selection, review/submission/status UI, offline/non-lifecycle unavailable-with-reason messaging. No submission state logic inline.
- `scripts/little_loops/cli/artifact/policy_builder.py`: `render_policy_builder_html` renderer; `cmd_policy_builder` becomes the CLI wrapper.
- `scripts/little_loops/cli/artifact/serve.py`, `cli/artifact/__init__.py`: `--policy-builder` opt-in flag and project/issue/page/request routes, including early existing-request readback and binding comparison.
- `scripts/little_loops/transport.py`: shared Host/token helper, `do_POST`, parameterized route matching with body-size and content-type guards; `method_routes` on `SseBridge`/`serve_sse_bridge` and `extra_url_suffixes` on `serve_sse_bridge`.

### Dependent Files (Callers/Importers)

- `scripts/tests/test_enh3035_artifact_template_kit.py` (line 19,65) — calls `cmd_policy_builder` directly and holds the byte-identical golden-HTML assertion; must pass unchanged after the renderer split.
- `scripts/tests/test_policy_builder_emit.py` — calls `cmd_policy_builder` directly (its golden tests cover YAML fixtures, not HTML).
- `scripts/tests/test_transport.py::TestLocalBridgeTransport` (line 1052-1295) — POST dispatch precedent using `_lb_http_request`; model for new `SseBridge.do_POST` tests.
- `scripts/tests/test_wiring_reference_docs.py` — parametrized `DOC_STRINGS_PRESENT` table (line 215-224); new row once the level-2 render target is declared in `ARTIFACT_CONTROL_LEVELS.md`.

### Tests

- Builder-output validity: each regenerated `sample-issue-lifecycle*.yaml` fixture passes `validate_policy_revision` with `ok=True, mode="issue_lifecycle"` (today all three fail with `mode=None`).
- New `SseBridge` tests: method-aware dispatch, parameterized path bounds, 400/413 body guards, Host/token HTML rejection on every new route, connected application JSON errors, opt-in route absence, no CORS headers, existing GET/history/SSE tests unchanged.
- Route-level submit tests against a real queue watcher: zero dispatches before approval; concurrent duplicate submits map to one queue UUID; conflicting payload under one request UUID fails; revision-hash mismatch, missing issue, wrong workspace, unsupported mode, and ERROR diagnostics are rejected with structured bodies and no row.
- Route retry tests: accept a request, remove its issue or change the validator outcome, then retry the exact payload and recover the original row without validation/persistence; conflicting existing bindings still return 409. Concurrent first submissions retain transactional dedup.
- Node tests (new `scripts/tests/js/policy_submission.test.mjs`, run by the existing Node gate) against `createSubmissionController` with fake `fetch`/storage/`subtle`/timers, for full-envelope freezing, persistence-before-POST, delayed hashing/response, double clicks, issue selection/Open during hashing, stale poll responses, storage failure, lost POST response, and SHA-256 parity with Python (non-ASCII YAML).
- Restart tests, no real browser: (Python) construct a second `SseBridge` over the same project and read back the original request under the new token, and assert the old token path returns the HTML transport error; (Node) a controller rebuilt over the same fake storage recovers the stored request via readback, handles a non-JSON error without clearing state, polls at the documented cadence and stops on terminal status, and a controller with a different `workspaceId` sees none of the first one's drafts/submissions. Any real-browser check is an on-demand Playwright probe loop under `.loops/`, never a pytest gate.
- Golden and applicable local pytest/Node gates pass.

### Documentation

- `docs/reference/API.md` `### SseBridge` section (heading near line 11448; existing prose near line 11482 "Extra `GET` routes...") — describe method-aware POST dispatch and parameterized matching while preserving the Host/token security contract.
- `docs/reference/CLI.md` — `ll-artifact policy-builder` subsection (lines 5081-5102) and `ll-artifact serve` subsection (lines 5192-5257): `--policy-builder` flag and the connected route.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — add level-2 row to `## Declared levels by render target` (line 49-59): `| \`ll-artifact serve\`'s policy-builder route (FEAT-3504; connected same-origin authoring + submission with host approval via FEAT-3498, project-scoped issue binding, immutable revision persistence) | 2 (project-local) |`.
- `docs/guides/POLICY_ROUTER_GUIDE.md` — cross-link the level-2 declaration per the "**Binding now:**" requirement in `ARTIFACT_CONTROL_LEVELS.md:61-63`; document the connected flow, fixed-origin/new-token-URL restart recovery, workspace isolation, durable-storage failure behavior, and local-only verification instructions.
- `docs/ARCHITECTURE.md` `## Artifact Control Layer` (line 920-936) — mention the serve submit/readback routes alongside `_drain_inbound()` if warranted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- _(Superseded 2026-09-18 by the post-FEAT-3498 review below: FEAT-3498 is done and all of its symbols now resolve; the resolved `blocked_by: FEAT-3498` edge was removed.)_
- `SseBridge`'s handler (`_make_sse_bridge_handler`, `transport.py:1200`) defines only `do_GET` (`transport.py:1209-1245`); no `do_POST` method exists on this class today.

## Implementation Steps

0. Emit `category: issue_lifecycle` from `_serializeIssueLifecycle`, regenerate the lifecycle YAML goldens, and add the test that each passes `validate_policy_revision`. Do this first: nothing downstream can be exercised end-to-end until it holds.
1. Factor `render_policy_builder_html` from `cmd_policy_builder`; golden byte-identity test still passes.
2. Add the shared Host/token helper, `do_POST`, parameterized matching, and body guards to `SseBridge` with transport tests; existing GET/SSE tests unchanged.
3. Add the `--policy-builder` serve flag, the once-resolved project root, `workspace_id` derivation, `method_routes`/`extra_url_suffixes` plumbing, page route, issue-list route, submit route (the nine ordered steps above, including the existing-request early return, building the `ActionSpec` with `timeout=None`), and readback route (mapping `QueueEntry` to the wire dict), with the JSON error shape and status table; route-level tests against a live watcher. Steps 0–3 are fully testable over HTTP with no page work.
4. Build `createSubmissionController` in the `.mjs` test-first under the Node gate, then bind it in the `.tmpl` and regenerate the HTML golden: freeze the full request before hashing, persist its complete envelope before POST, add operation/double-click guards and request-scoped responses, workspace-scoped storage, new-token restart recovery, submit/poll/status UI, and offline/non-lifecycle messaging. Exercise delayed hashing, Open/selection changes, stale responses, lost responses, and storage failures.
5. Update docs, golden output, and the `ARTIFACT_CONTROL_LEVELS.md` level-2 declaration.

## Program Design

### Types

- `RunRequest`, `ValidationOutcome`, `PolicyRevisionConflictError` — imported from `little_loops.cli.artifact.policy_revision`; `QueueEntry` from `little_loops.queue_store`; `ActionSpec`, `RunnerType` from `little_loops.runner_spec`. This issue serializes them, it does not redefine them. There is no `RunRequestStatus` type — FEAT-3498 landed `get_run_request -> QueueEntry | None`; the readback wire dict `{requestId, queueId, status, bindings: {issueId, revisionId}, loopInstanceId, runDir, result}` is built in the route.
- `ErrorBody {error: {code, message, errors?, warnings?}}` — the JSON error shape for connected application errors after successful Host/token checks and route dispatch; pre-dispatch transport failures retain their existing HTML contract.
- `SubmissionEnvelope {requestId, projectId, workspaceId, issueId, yaml, revisionId}` — immutable client record persisted before POST, scoped outside authoring history; retry resends the exact envelope. Operation generation and current UI association are separate from the immutable payload.
- `IssueSummary {id, title, priority, status, path}` — wire shape of `GET /{token}/issues`, built from `find_issues(config)` (active issues only).

### Signatures

- `render_policy_builder_html(config: BRConfig, *, workspace_id: str | None = None) -> str` — factored from `cmd_policy_builder` (`cli/artifact/policy_builder.py:62`); with `workspace_id=None` the connected-context placeholder renders `null` and the output equals the CLI golden.
- `createSubmissionController(deps) -> controller` — exported from `policy_builder_core.mjs`; all browser globals injected.
- `SseBridge(..., method_routes: list[tuple[str, str, handler]] | None = None)` and `serve_sse_bridge(..., method_routes=None, extra_url_suffixes=None)` — each tuple is `(method, pattern, handler)`; pattern is a literal path with at most one `{name}` segment; matching is anchored, single-segment, and bounded (no regex from user input). `do_POST` reuses a `_check_host_and_strip_token(handler) -> str | None` helper factored out of `do_GET` (`transport.py:1200-1246`).
- `make_run_request_routes(config: BRConfig, *, workspace_id: str) -> list[tuple[str, str, handler]]` in `cli/artifact/serve.py` — submit, readback, and issue-list handlers. Landed FEAT-3498 keyword names differ by function: `validate_policy_revision(yaml_bytes, *, project_root)`, `persist_policy_revision(yaml_bytes, revision_id, *, project_root) -> Path`, `create_or_get_run_request(request, *, action, project_root, db_path, root) -> tuple[QueueEntry, bool]`, `get_run_request(request_id, workspace_id, *, db_path, root) -> QueueEntry | None`.
- `derive_workspace_id(project_root: Path) -> str` in `cli/artifact/serve.py` — first 16 hex chars of SHA-256 over the resolved project root; stable across serve restarts.

### Call Path

Planned command (new flag implemented by this issue): `ll-artifact serve --policy-builder` → `cmd_serve` resolves the project root once, derives `workspace_id`, renders `render_policy_builder_html(config, workspace_id=...)` once (no bridge needed — the page uses relative URLs), and passes the page, issues, submit, and readback routes as `method_routes` plus `extra_url_suffixes=["policy-builder"]` to `serve_sse_bridge` → browser `POST /{token}/run-request` → body guards → `RunRequest` → hash recompute → workspace check → existing-request lookup (binding match: return original row; conflict: 409) → new-request issue-exists check → `validate_policy_revision` → `persist_policy_revision` → build `ActionSpec(runner=LOOP, target=<persisted path>, timeout=None)` → `create_or_get_run_request` (row `awaiting_approval`) → `{requestId, queueId, created}`. Browser polls `GET /{token}/run-request/{requestId}` → `get_run_request` → `QueueEntry` → wire dict. Host approval is FEAT-3498's `ll-queue run --id ID --approve`; host rejection is `ll-queue cancel`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- `SseBridge._routes: dict[str, Callable[[http.server.BaseHTTPRequestHandler], None]]` is built in `__init__` (`transport.py:1285-1290`): seeded with `{"": self._serve_page, "events": self._serve_events}`, then `.update(routes)` for caller-supplied extras (e.g. `cli/artifact/serve.py:189`'s `"history"` route). `do_GET` (`transport.py:1221-1245`) strips the `/{token}` prefix, looks up the remaining suffix as an exact dict key via `bridge._routes.get(route)`, and 404s on a miss — no `{name}`-segment or regex matching exists anywhere in this dict-based dispatch.
- A bare `/{token}` path (no trailing slash) issues a `301` redirect to `/{token}/` (`transport.py:1228-1234`) before route lookup; `LocalBridgeTransport`'s separate `_route()` (`transport.py:638-646`) instead accepts both forms as route `""` with no redirect. The new parameterized matcher inherits one of these two prefix-handling behaviors — they are not currently unified.
- `LocalBridgeTransport._handle_interaction` (`transport.py:692-716`) is the uncapped precedent the issue warns against: it parses `Content-Length` with a bare `try/except ValueError: length = 0` (no upper-bound check, `transport.py:693-696`), always responds `204` before parsing the body (`transport.py:699-702`), and on a JSON-parse or type failure only calls `_record_inbound_drop(...)` — it never returns a 400/413 status. Every existing error response in `transport.py`/`cli/artifact/serve.py` uses stdlib `send_error()`'s text/html body or a hand-built `text/plain` body (the one existing size-driven `413`, `cli/artifact/serve.py:102-109`, guards an *outbound* export against `artifacts.export.max_artifact_bytes`, not an inbound POST); no JSON-structured error-body convention exists yet in this code to reuse.
- No `{name}`-segment path-param matcher (regex or otherwise) exists anywhere in `scripts/little_loops/**/*.py` today (repo-wide search, no hits) — the `method_routes` bounded single-segment matching has no in-repo precedent to model; it is new surface, not an extension of an existing pattern.
- The renderer-factoring precedent is `build_dashboard_html` (`cli/artifact/dashboard.py:257`, a keyword-only function returning a `RenderedDashboard`) plus its CLI wrapper `cmd_dashboard` (`dashboard.py:398`, which does `write_text`/`logger.success`/`logger.error`) — `_make_page_html_factory` (`serve.py:138`) is a second *consumer* of that same renderer, not itself the factoring precedent. `cmd_policy_builder` is today the only other HTML-emitting `cli/artifact/*.py` command with no such split (`policy_builder.py:62-128`, inline `try`/`write_text` in one function) — this issue's renderer split is the first of its kind for this file, following an established sibling pattern rather than inventing one.
- `_lb_http_request` (`test_transport.py:963-989`) — not the `TestLocalBridgeTransport` class body generally — is the exact helper that drives real HTTP GET/POST requests over a loopback `http.client.HTTPConnection` with explicit `Host`-header control; existing POST call sites (`test_transport.py:1192`, `:1223-1225`) are the direct model for new `SseBridge.do_POST` tests.

## Use Case

A maintainer opens the served builder, picks BUG-123 from the project's issue list, reviews the frozen lifecycle policy, and submits. The page shows "awaiting approval" with the request and queue IDs. From a terminal the maintainer runs `ll-queue run --id ID --approve`; the page transitions to running, shows the real loop instance ID and run dir, then the result, while the author's current draft stays editable and marked as newer than the submitted revision.

## Impact

- Priority: P3 — closes the browser-to-host gap once FEAT-3498's contracts exist.
- Effort: Medium-Large — serializer fix + golden regeneration, transport, renderer split, four routes, stateful page wiring, docs; establishes four conventions with no in-repo precedent (JSON error body, path-param matcher, disabled-with-reason controls, JS/Python hash parity). If it needs splitting, the seam is steps 0–3 (server side, fully testable over HTTP) vs. step 4 (page wiring).
- Risk: Medium — transport surface hardening; the concurrency risk lives in FEAT-3498.

## Acceptance Criteria

- [ ] The builder's own `issue_lifecycle` output (regenerated golden fixtures) passes `validate_policy_revision` with `mode="issue_lifecycle"`.
- [ ] Submitting through the route while a watcher runs produces `awaiting_approval` and zero subprocess dispatches; serve cannot approve/run; production behavioral tests enforce the level boundary.
- [ ] All four connected routes are absent unless `--policy-builder` is passed; when enabled, serve prints the tokenized builder URL. Existing Host/token checks cover every route/method and retain HTML transport errors; dispatched application errors use JSON ErrorBody. The client handles either format. Existing GET/history/SSE tests pass; no CORS headers; oversized, non-JSON, or malformed bodies return 413/400 with no side effects.
- [ ] Concurrent duplicate first submissions and exact retries after terminal completion, issue removal, or validator changes map to one queue UUID. Existing matching requests bypass mutable issue/validation/persistence checks; hash/workspace checks remain mandatory and differing stored bindings return `409`. New requests still require all creation checks; explicit Run again creates a fresh awaiting request.
- [ ] Restart on the same origin rotates the token: opening the newly printed builder URL restores the matching workspace/document envelope and recovers the original queue ID using the new endpoint. The old URL fails gracefully without clearing state. Different workspaces served at the same origin cannot restore each other's connected drafts or submissions.
- [ ] For new requests, invalid YAML, ERROR diagnostics, missing issue, wrong workspace, unsupported mode, and revision-hash mismatch are rejected with the documented status code and JSON `ErrorBody` and leave no runnable entry; hash/workspace/issue failures write nothing under `.loops/policy-builder/`.
- [ ] The enqueued `ActionSpec` has `runner=LOOP`, `timeout=None`, and `target` equal to the path `persist_policy_revision` returned.
- [ ] Readback of an unknown request returns `404`; a host `ll-queue cancel` surfaces as `cancelled` and the page shows it as rejected.
- [ ] Browser SHA-256 of the frozen UTF-8 YAML bytes matches Python, including non-ASCII content. Delayed-hash tests prove all bindings are captured before the first await; Open/selection changes invalidate unsent operations, while draft edits do not alter a frozen request. Double clicks create one UUID; stale responses/polls update only their originating submission.
- [ ] The submission state machine is an exported, dependency-injected controller in `policy_builder_core.mjs` covered by the Node gate; the `.tmpl` holds DOM binding only. The served page uses token-relative URLs and no stamped endpoint; polling runs at the documented cadence and stops on terminal status.
- [ ] Complete envelopes are persisted before POST outside undo history. Reload/retry resends the exact envelope; a lost response after server acceptance recovers the original queue row. Persistence failure sends no request and shows a diagnostic while leaving authoring usable.
- [ ] Readback exposes status, bindings, `loopInstanceId`, and `runDir` while running and after completion, distinct from request/queue IDs.
- [ ] Offline/non-lifecycle pages show connected controls unavailable with a reason; connection failure/reload retains authoring/scenarios and submission identity; edited drafts distinguish current and submitted revisions.
- [ ] `cmd_policy_builder`'s CLI output is byte-identical to the golden fixture after the renderer split.
- [ ] Connected builder is documented at level 2 with local-only verification instructions; golden and applicable local pytest/Node gates pass.

## Scope Boundaries

Includes the same-origin page, issue-list/submit/readback routes, POST dispatch on `SseBridge`, and page UI. Excludes any queue/loop/approval semantics (FEAT-3498), autonomous page/serve execution, remote shell APIs, level-3 event interception, all-mode connected inputs, arbitrary YAML import, and the `_ResourceEntry` control-level forward slot.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **VALID** (2026-09-18 `/ll:verify-issues --auto`; no corrections were required, so this section is a record of what was checked, not an outstanding action item)

- Confirmed: `_serializeIssueLifecycle` (`policy_builder_core.mjs:2736`) emits no `category:` line and none of the three `sample-issue-lifecycle*.yaml` fixtures contains one, while `validate_policy_revision` reads `fsm.category` and `_SUPPORTED_MODES = {"issue_lifecycle"}` — the blocker is real.
- Confirmed: FEAT-3498 contracts exist with the cited signatures (`create_or_get_run_request`, `get_run_request` in `queue_store.py`; `validate_policy_revision`/`persist_policy_revision`/`RunRequest`/`PolicyRevisionConflictError` in `policy_revision.py`); `SseBridge` handler has `do_GET` only (`transport.py:1221`) with exact-key `_routes`; `cmd_policy_builder`/`add_serve_parser`/`_make_page_html_factory` anchors hold. All referenced issues (FEAT-3498, ENH-3487/3491/3492, BUG-3490) are done. `ll-verify-evidence`: clean. Proposal-vs-code check found no contradiction.
- Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

## Status

**Open** | Created: 2026-09-18 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-18_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- Criterion 4 capped at 10: `format-check` flags `ll-artifact serve --policy-builder` as `stale_cli_flag`. Advisory only — the flag is introduced by this issue, so it cannot resolve yet.
- Four conventions have no in-repo precedent (JSON error body, `{name}` path-param matcher, disabled-with-reason controls, JS/Python SHA-256 parity); the bare-token redirect vs. `LocalBridgeTransport` prefix handling is still un-unified.

### Outcome Risk Factors
- Deep per-site complexity: `SseBridge` method-aware dispatch and a stateful page (freeze/persist/guard/poll/token-rotation) touch shared state across several functions.
- Broad enumeration across ~7 code files plus 5 doc files; the stateful `.tmpl` page wiring has the thinnest automated coverage (Node gate covers `.mjs` only).

## Session Log
- manual review applied - 2026-09-18 - moved submission state machine into a dependency-injected `.mjs` controller (Node-testable); replaced stamped endpoint URL with relative URLs + connected-context placeholder; specified `method_routes`/`extra_url_suffixes` plumbing, once-resolved project root, field shapes, polling cadence, `find_issues` active-only scope, golden-regeneration timing; dropped redundant `active_theme` param
- `/ll:confidence-check` - 2026-09-18T22:07:29 - `89462603-1252-4507-b232-c85a163bfde9.jsonl`
- `/ll:verify-issues` - 2026-09-18T21:59:57 - `bc5bab11-9b54-483b-9d88-6c04ae5945bc.jsonl`
- `/ll:ready-issue` - 2026-09-18T21:05:48 - `07c743d4-fb4d-457c-985e-2bfb140d83ca.jsonl`
- `/ll:verify-issues` - 2026-09-18T16:33:37 - `8bffa950-7522-4c88-bac6-c0f5c79c2f1a.jsonl`
- manual review applied - 2026-09-18 - moved existing-request recovery ahead of mutable creation checks; specified full-envelope freezing/persistence and async guards, token-rotation/new-URL recovery, workspace storage isolation, --policy-builder flag, and transport/application error boundary; updated tests, design, steps, and acceptance criteria together
- manual review vs. landed FEAT-3498 contracts - 2026-09-18 - added `category:` emit blocker, corrected store/validator signatures, defined workspace id, error-body/status table, submit ordering, body cap, origin-scoped storage, FEAT-3503 overlap; removed resolved `blocked_by: FEAT-3498`
- `/ll:refine-issue` - 2026-09-18T02:34:20 - `e526fcc4-a04f-4fa1-9b46-7e10044a1c18.jsonl`
- `/ll:format-issue` - 2026-09-18T02:26:59 - `17fa148c-98f6-4a6e-975e-5e4a6f742eec.jsonl`
