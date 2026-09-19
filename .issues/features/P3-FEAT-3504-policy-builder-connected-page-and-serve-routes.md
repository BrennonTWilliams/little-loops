---
id: FEAT-3504
type: FEAT
title: Policy builder connected page and serve routes
priority: P3
status: done
discovered_by: manual-split
discovered_date: '2026-09-18'
captured_at: '2026-09-18T02:19:33Z'
completed_at: '2026-09-19T00:17:43Z'
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
blocks:
- FEAT-3505
confidence_score: 85
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3504: Policy builder connected page and serve routes

## Summary

Second half of the connected-execution split from FEAT-3498. FEAT-3498 (Part A, **done** — all contracts below are landed and importable) delivers the host-side contracts: the `awaiting_approval` queue status, `create_or_get_run_request`/`approve_and_claim_entry`/`record_loop_started`/`get_run_request`, `ll-queue run --id ID --approve`, builder-origin LOOP dispatch (cwd, no timeout, `--context issue_id=`), the structured start-metadata channel, and `persist_policy_revision`/`validate_policy_revision` as plain Python functions. This issue (Part B1, server side) exposes those contracts over HTTP: serve the policy builder at a same-origin route with a stamped connected context, and add project-scoped issue-list and request submit/readback endpoints on `SseBridge`. Everything here is testable over HTTP with no page work. The page's review/submission/status UI, the `.mjs` submission controller, workspace-scoped browser storage, the served-page browser probe, and the user guide were split out to **FEAT-3505** (Part B2, blocked by this issue) on 2026-09-18. No queue, loop, or approval semantics change here.

## Current Behavior

`ll-artifact serve` uses `SseBridge` with token/Host-checked GET routes only (`transport.py:1200-1246`, exact-string match on `_routes`; no `do_POST`, no parameterized path matching). `cmd_policy_builder` (`cli/artifact/policy_builder.py:62`) renders to a file only; the `file://` builder has no connected controls. With FEAT-3498 landed, a builder-origin request can be created and approved from Python/CLI, but nothing in the browser can submit one or observe it.

**The builder's own lifecycle output does not pass the landed validator.** `validate_policy_revision` (`cli/artifact/policy_revision.py:69`) reads the policy mode from the loop's `category:` field and accepts only `issue_lifecycle` (`_SUPPORTED_MODES`, `policy_revision.py:35`). `_serializeIssueLifecycle` (`policy_builder_core.mjs:2736`) emits no `category:` line, so all three `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle*.yaml` fixtures return `ok=False, mode=None, errors=["Unsupported policy mode None; ..."]`. Until the serializer emits `category: issue_lifecycle`, every browser submission would be rejected.

## Expected Behavior

With `ll-artifact serve --policy-builder`, an HTTP client holding the token can list the project's active issues, submit a hash-verified `issue_lifecycle` policy snapshot bound to one issue, and read back that request's status. The host sees the exact project/issue/revision and explicitly runs or rejects that one request via FEAT-3498's `ll-queue run --id ID --approve`. Readback exposes approval, running/completion/failure/cancellation and the real loop instance identifier once execution starts. The served page carries the server's `workspaceId`; its connected UI is FEAT-3505.

## Motivation

Without this half, FEAT-3498's approval contracts are reachable only from Python and `ll-queue`; the policy builder stays a `file://` export tool and the authoring-to-execution gap in EPIC-3493 remains open. Splitting it out keeps the transport/page surface (Host/token, POST hardening, renderer split, UI state) reviewable on its own and lets FEAT-3498's concurrency risk land and stabilize first.

## Proposed Solution

### Scope and origin

- Add the opt-in `--policy-builder` flag on `ll-artifact serve` (registered in `add_serve_parser()`, `cli/artifact/serve.py:37`); no config flag is needed. Without this flag, none of the four connected routes is registered. With it, print the full tokenized builder URL alongside the existing serve URL. Serve the builder at `GET /{token}/policy-builder` using a renderer factored from `cmd_policy_builder`, with a server-derived connected context (`{workspaceId}`) stamped in. **No endpoint URL is stamped**: the page is served under the token prefix, so it calls its routes with relative URLs (`./run-request`, `./run-request/{id}`, `./issues`). This keeps rendering independent of the bridge (the token exists only after `SseBridge` binds) and makes "persist request data, not a tokenized endpoint" hold by construction. The `file://` copy stays offline-only. Preserve Host/token checks for every method and route; no CORS headers.
- First connected release accepts `issue_lifecycle` policies only. Rubric requires a subject and other modes need different binding contracts; keep their offline exports available and explain why connected Run is unavailable.
- Bind repository identity and filesystem access to `BRConfig.project_root`, never a browser-supplied path. Add a project-scoped issue-list/read endpoint using `find_issues(config)` (`little_loops.issue_parser`) with its default `status_filter` — active issues only (done/cancelled/deferred excluded); the same call backs the new-request issue-exists check in submit step 5. `projectId` from ENH-3487 identifies the builder document, not the repository. Reject cross-workspace requests. The serve process anchors the queue db at `BRConfig.project_root` via the `db_path`/`root` parameters FEAT-3498 adds.
- **Workspace identifier**: no derivation helper exists today. Define `workspace_id` as a deterministic function of the resolved project root — `hashlib.sha256(str(config.project_root.resolve()).encode()).hexdigest()[:16]` — so it is stable across serve restarts. **Resolve the root once** in `cmd_serve` (`root = config.project_root.resolve()`) and use that single value for `workspace_id`, the step-4 binding comparison, `create_or_get_run_request(project_root=..., root=...)`, `validate_policy_revision`, and `persist_policy_revision`: the store binds on `str(project_root)`, so a symlinked cwd on a later restart would otherwise keep the workspace ID but change the stored string and turn an exact retry into a `409`. It must **not** be derived from the per-process serve token: request dedup and readback both key on `(workspace_id, request_id)`, so a per-process value would break the reload/retry acceptance criterion. The server stamps it into the page and rejects any submit/readback whose `workspaceId` differs.
- **Builder emit fix (prerequisite)**: `_serializeIssueLifecycle` emits `category: issue_lifecycle` so its output passes `validate_policy_revision`. Regenerate the `sample-issue-lifecycle*.yaml` golden fixtures. This is the first time builder-emitted YAML meets the validator; FEAT-3498's tests used hand-built YAML.

### Revision guarantee

The first release guarantees an immutable **submitted YAML snapshot**, identified by its exact-byte hash, using current project dependencies when executed. It does not provide reproducible execution: generated YAML imports `lib/policy-router.yaml` and invokes skills whose contents are not frozen by `revisionId`. The current FEAT-3498 approval path checks stored bindings and executes the persisted file path; it does not rehash that file at approval time. UI and documentation must not claim dependency pinning or execution-time byte verification. Changing the persisted file outside this flow is outside this guarantee. If exact-byte execution becomes a requirement, approval-time hash verification must be tracked as a separate prerequisite before making that stronger claim; no approval semantics are added here.

### Renderer split

`cmd_policy_builder` has a clean split point: `BRConfig` construction through the five `html.replace(...)` injections (lines 73-115) is pure computation producing an in-memory `html` string; only the output-dir resolution and `write_text`/`logger.success` tail (lines 117-125) is CLI-specific. Factor a `render_policy_builder_html(config, *, workspace_id=None) -> str` (the active theme is derived from `config` inside, as today) and make `cmd_policy_builder` a thin wrapper. Add one new placeholder, `/*__CONNECTED_CONTEXT_JSON__*/`, replaced with `json.dumps({"workspaceId": workspace_id})` when serving and `null` for the offline CLI output. Precedent: `_make_page_html_factory` (`cli/artifact/serve.py:138`) builds HTML from config and hands it to `bridge.set_page_html(...)`. The byte-identity golden test in `test_enh3035_artifact_template_kit.py` must pass unchanged at step 1 (pure refactor); the golden is regenerated once in step 3 when the template gains the placeholder (a single `const CONNECTED_CONTEXT = /*__CONNECTED_CONTEXT_JSON__*/;`-style assignment, no UI), after which the CLI path must match the regenerated golden. FEAT-3505 regenerates it again for the connected UI.

### Routes and POST handling

- Add method-aware dispatch plus bounded parameterized path matching in `SseBridge`: `POST /{token}/run-request`, `GET /{token}/run-request/{requestId}`, `GET /{token}/issues`, `GET /{token}/policy-builder`. Existing exact GET/history/SSE routes keep working. Factor the Host-header check and token prefix-strip out of `do_GET` into a shared helper so `do_POST` does not duplicate it. **Plumbing**: `SseBridge` takes routes in its constructor (before the token exists) and `serve_sse_bridge` owns both construction and `print(bridge.url)`, so add a keyword-only `method_routes: list[tuple[str, str, handler]] | None = None` to both (the existing GET-only `routes` dict is unchanged and still checked first by exact match), plus `extra_url_suffixes: list[str] | None = None` on `serve_sse_bridge`, which prints `bridge.url + suffix` for each after the main URL (`["policy-builder"]` here). Handlers for parameterized routes receive the captured segment as a second argument.
- **Module boundary**: put connected issue/submit/readback handlers and their JSON parsing/error helpers in a new `cli/artifact/policy_builder_routes.py`; `serve.py` only composes these routes with the page renderer and flag. `SseBridge` owns generic method/path dispatch and shared Host/token checks, with no policy payload knowledge.
- POST hygiene (inside `policy_builder_routes.py`, after transport authorization and route dispatch): cap the request body at a fixed module constant, `_MAX_RUN_REQUEST_BYTES = 1 << 20` (1 MiB); `Content-Length` above it returns `413`. Do **not** reuse `artifacts.export.max_artifact_bytes` — that key governs outbound history-snapshot exports, which is the wrong meaning and far too large a bound for a policy YAML. Missing/invalid `Content-Length`, non-`application/json` Content-Type, or a JSON parse failure returns `400`. Do not copy `LocalBridgeTransport`'s `do_POST` (`transport.py:693-698`), which reads `Content-Length` uncapped.
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
  | `500` | `internal_error` | unexpected persistence/database or other application failure; log details server-side and return a generic message without traceback |
- **Unexpected failures**: wrap connected application handlers in the JSON error boundary. A `500` or an interrupted response does not prove that enqueue failed: the queue transaction may already have committed. The client retains the envelope, marks the outcome unknown, and reconciles through readback before offering an identical retry. Do not roll back/delete a potentially accepted request in response to an HTTP write failure.
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
  9. Return `200 {requestId, queueId: entry.id, created, warnings}` (`warnings` from step 6; `[]` on the existing-request path). Exact retries after issue removal or validator changes return the original row; genuinely new requests still undergo every creation check.
- Readback: `GET /{token}/run-request/{requestId}?workspaceId=...` → `get_run_request(request_id, workspace_id, root=config.project_root)`, which returns `QueueEntry | None` (there is no `RunRequestStatus` type; the route builds the wire dict). `None` → `404 request_not_found`. Otherwise `{requestId: entry.request_id, queueId: entry.id, status: entry.status, bindings: {issueId: entry.issue_id, revisionId: entry.revision_id}, loopInstanceId: entry.loop_instance_id, runDir: entry.run_dir, result: entry.result}`. Never pass a request UUID to `get_entry`. Return `Cache-Control: no-store` on all readback responses, including errors, so polling and reload reconciliation cannot use a cached status or cached absence.
- Host rejection is `ll-queue cancel`, which surfaces as `status: "cancelled"`. There is no distinct "rejected" status; the page labels `cancelled` as "Rejected / cancelled by host".

### Page behavior (moved to FEAT-3505)

Review/submission UI, `createSubmissionController`, the JS SHA-256 helper, delivery-state recovery, polling, workspace-scoped browser storage, and offline/non-lifecycle messaging are FEAT-3505. Contract points that issue relies on and this one must hold: the stamped `{workspaceId}` context, token-relative routes, the `ErrorBody`/status table, HTML (non-JSON) pre-dispatch transport errors, `Cache-Control: no-store` readback, and stable `workspace_id` across restarts with a rotated token. `validate_policy_revision` warnings on an accepted request are returned in the `200` body as `warnings` so the page can show them as non-blocking (`sample-issue-lifecycle-destinations.yaml` validates `ok=True` with a "State is not reachable from initial state" warning).

- **FEAT-3503 overlap**: FEAT-3503 is **done**; build on its landed `.mjs`/`.tmpl` changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- The only existing "connected controls" gating in a browser template is whole-block presence/absence via template conditionals (`dashboard.llat/template.html.j2:356-380`'s `[[% if serve_enabled %]]`), driven by an always-present boolean computed from `serve_context is not None` (`cli/artifact/dashboard.py:322`). No existing template shows a control in a visibly-disabled state annotated with an unavailability-reason string — the "connected controls unavailable with a reason" UI this issue proposes for offline/non-lifecycle pages has no in-repo convention to follow.
- No `crypto.subtle` usage and no existing JS-side/Python-side SHA-256 parity test exists anywhere in this codebase (repo-wide search, zero hits) — the browser/Python hash-parity requirement is new surface with no established pattern to reuse.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs`: emit `category: issue_lifecycle` from `_serializeIssueLifecycle` only (controller/hash/storage work is FEAT-3505).
- `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle*.yaml`: regenerate goldens for the added `category:` line.
- `scripts/little_loops/cli/artifact/policy_revision.py`: correct the `RunRequest` docstring (the route, not `persist_policy_revision`, recomputes the hash).
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: `/*__CONNECTED_CONTEXT_JSON__*/` placeholder assignment only (UI binding is FEAT-3505).
- `scripts/little_loops/cli/artifact/policy_builder.py`: `render_policy_builder_html` renderer; `cmd_policy_builder` becomes the CLI wrapper.
- `scripts/little_loops/cli/artifact/serve.py`, `cli/artifact/__init__.py`: `--policy-builder` opt-in flag, workspace derivation, and composition of page/connected routes.
- `scripts/little_loops/cli/artifact/policy_builder_routes.py` (new): issue/submit/readback handlers, early existing-request readback and binding comparison, bounded JSON parsing, JSON error boundary, and no-store readback responses.
- `scripts/little_loops/transport.py`: shared Host/token helper, `do_POST`, parameterized route matching; `method_routes` on `SseBridge`/`serve_sse_bridge` and `extra_url_suffixes` on `serve_sse_bridge`.

### Dependent Files (Callers/Importers)

- `scripts/tests/test_enh3035_artifact_template_kit.py` (line 19,65) — calls `cmd_policy_builder` directly and holds the byte-identical golden-HTML assertion; must pass unchanged after the renderer split.
- `scripts/tests/test_policy_builder_emit.py` — calls `cmd_policy_builder` directly (its golden tests cover YAML fixtures, not HTML).
- `scripts/tests/test_transport.py::TestLocalBridgeTransport` (line 1052-1295) — POST dispatch precedent using `_lb_http_request`; model for new `SseBridge.do_POST` tests.
- `scripts/tests/test_wiring_reference_docs.py` — parametrized `DOC_STRINGS_PRESENT` table (line 215-224); new row once the level-2 render target is declared in `ARTIFACT_CONTROL_LEVELS.md`.

### Tests

- Builder-output validity: each regenerated `sample-issue-lifecycle*.yaml` fixture passes `validate_policy_revision` with `ok=True, mode="issue_lifecycle"` (today all three fail with `mode=None`).
- New `SseBridge` tests: method-aware dispatch, parameterized path bounds, Host/token HTML rejection on every new route, opt-in route absence, no CORS headers, existing GET/history/SSE tests unchanged. Connected route tests cover 400/413 body guards, JSON application errors, unexpected storage/database failures (including failure after commit), and no-store readback responses.
- Route-level submit tests against a real queue watcher: zero dispatches before approval; concurrent duplicate submits map to one queue UUID; conflicting payload under one request UUID fails; revision-hash mismatch, missing issue, wrong workspace, unsupported mode, and ERROR diagnostics are rejected with structured bodies and no row.
- Route retry tests: accept a request, remove its issue or change the validator outcome, then retry the exact payload and recover the original row without validation/persistence; conflicting existing bindings still return 409. Concurrent first submissions retain transactional dedup.
- Restart test (Python): construct a second `SseBridge` over the same project and read back the original request under the new token with the same `workspace_id`; the old token path returns the HTML transport error.
- Page route test: `GET /{token}/policy-builder` returns HTML whose stamped context equals `derive_workspace_id(root)`; the offline CLI render stamps `null`.
- Node controller tests and the served-page Playwright probe are FEAT-3505.
- Golden and applicable local pytest/Node gates pass.

### Documentation

- `docs/reference/API.md` `### SseBridge` section (heading near line 11448; existing prose near line 11482 "Extra `GET` routes...") — describe method-aware POST dispatch and parameterized matching while preserving the Host/token security contract.
- `docs/reference/CLI.md` — `ll-artifact policy-builder` subsection (lines 5081-5102) and `ll-artifact serve` subsection (lines 5192-5257): `--policy-builder` flag and the connected route.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — add level-2 row to `## Declared levels by render target` (line 49-59): `| \`ll-artifact serve\`'s policy-builder route (FEAT-3504; connected same-origin authoring + submission with host approval via FEAT-3498, project-scoped issue binding, immutable revision persistence) | 2 (project-local) |`.
- `docs/guides/POLICY_ROUTER_GUIDE.md` — cross-link the level-2 declaration per the "**Binding now:**" requirement in `ARTIFACT_CONTROL_LEVELS.md:61-63`, with the submitted-snapshot/current-dependency guarantee stated once. The full connected-flow walkthrough is FEAT-3505.
- `docs/ARCHITECTURE.md` `## Artifact Control Layer` (line 920-936) — add one sentence naming the serve submit/readback routes as the level-2 inbound path, alongside `_drain_inbound()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- _(Superseded 2026-09-18 by the post-FEAT-3498 review below: FEAT-3498 is done and all of its symbols now resolve; the resolved `blocked_by: FEAT-3498` edge was removed.)_
- `SseBridge`'s handler (`_make_sse_bridge_handler`, `transport.py:1200`) defines only `do_GET` (`transport.py:1209-1245`); no `do_POST` method exists on this class today.

## Implementation Steps

0. Emit `category: issue_lifecycle` from `_serializeIssueLifecycle`, regenerate the lifecycle YAML goldens, and add the test that each passes `validate_policy_revision`. Do this first: nothing downstream can be exercised end-to-end until it holds.
1. Factor `render_policy_builder_html` from `cmd_policy_builder`; golden byte-identity test still passes.
2. Add the shared Host/token helper, `do_POST`, and parameterized matching to `SseBridge` with transport tests; existing GET/SSE tests unchanged. Keep policy-specific body guards in the connected route module.
3. Add the `--policy-builder` serve flag, the once-resolved project root, `workspace_id` derivation, `method_routes`/`extra_url_suffixes` plumbing, page route, and the dedicated `policy_builder_routes.py` module with body guards, issue-list route, submit route (the nine ordered steps above, including the existing-request early return, building the `ActionSpec` with `timeout=None`), and readback route (mapping `QueueEntry` to the wire dict), with the JSON error boundary (including unexpected failures), status table, and no-store readback; route-level tests against a live watcher. Add the `/*__CONNECTED_CONTEXT_JSON__*/` placeholder to the template and regenerate the HTML golden once.
4. Update `API.md`, `CLI.md`, `ARCHITECTURE.md`, the `ARTIFACT_CONTROL_LEVELS.md` level-2 declaration (plus the `test_wiring_reference_docs.py` row), and the guide cross-link. Document the submitted-snapshot guarantee without claiming pinned dependencies or approval-time byte verification. Page work continues in FEAT-3505.

## Program Design

### Types

- `RunRequest`, `ValidationOutcome`, `PolicyRevisionConflictError` — imported from `little_loops.cli.artifact.policy_revision`; `QueueEntry` from `little_loops.queue_store`; `ActionSpec`, `RunnerType` from `little_loops.runner_spec`. This issue serializes them, it does not redefine them. There is no `RunRequestStatus` type — FEAT-3498 landed `get_run_request -> QueueEntry | None`; the readback wire dict `{requestId, queueId, status, bindings: {issueId, revisionId}, loopInstanceId, runDir, result}` is built in the route.
- `ErrorBody {error: {code, message, errors?, warnings?}}` — the JSON error shape for connected application errors after successful Host/token checks and route dispatch; pre-dispatch transport failures retain their existing HTML contract.
- `IssueSummary {id, title, priority, status, path}` — wire shape of `GET /{token}/issues`, built from `find_issues(config)` (active issues only).

### Signatures

- `render_policy_builder_html(config: BRConfig, *, workspace_id: str | None = None) -> str` — factored from `cmd_policy_builder` (`cli/artifact/policy_builder.py:62`); with `workspace_id=None` the connected-context placeholder renders `null` and the output equals the CLI golden.
- `SseBridge(..., method_routes: list[tuple[str, str, handler]] | None = None)` and `serve_sse_bridge(..., method_routes=None, extra_url_suffixes=None)` — each tuple is `(method, pattern, handler)`; pattern is a literal path with at most one `{name}` segment; matching is anchored, single-segment, and bounded (no regex from user input). `do_POST` reuses a `_check_host_and_strip_token(handler) -> str | None` helper factored out of `do_GET` (`transport.py:1200-1246`).
- `make_run_request_routes(config: BRConfig, *, workspace_id: str) -> list[tuple[str, str, handler]]` in `cli/artifact/policy_builder_routes.py` — submit, readback, and issue-list handlers. Landed FEAT-3498 keyword names differ by function: `validate_policy_revision(yaml_bytes, *, project_root)`, `persist_policy_revision(yaml_bytes, revision_id, *, project_root) -> Path`, `create_or_get_run_request(request, *, action, project_root, db_path, root) -> tuple[QueueEntry, bool]`, `get_run_request(request_id, workspace_id, *, db_path, root) -> QueueEntry | None`.
- `derive_workspace_id(project_root: Path) -> str` in `cli/artifact/serve.py` — first 16 hex chars of SHA-256 over the resolved project root; stable across serve restarts.

### Call Path

Planned command (new flag implemented by this issue): `ll-artifact serve --policy-builder` → `cmd_serve` resolves the project root once, derives `workspace_id`, renders `render_policy_builder_html(config, workspace_id=...)` once (no bridge needed — the page uses relative URLs), and passes the page, issues, submit, and readback routes as `method_routes` plus `extra_url_suffixes=["policy-builder"]` to `serve_sse_bridge` → browser `POST /{token}/run-request` → body guards → `RunRequest` → hash recompute → workspace check → existing-request lookup (binding match: return original row; conflict: 409) → new-request issue-exists check → `validate_policy_revision` → `persist_policy_revision` → build `ActionSpec(runner=LOOP, target=<persisted path>, timeout=None)` → `create_or_get_run_request` (row `awaiting_approval`) → `{requestId, queueId, created}`. Browser polls `GET /{token}/run-request/{requestId}` → `get_run_request` → `QueueEntry` → wire dict. Host approval is FEAT-3498's `ll-queue run --id ID --approve`; host rejection is `ll-queue cancel`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- `SseBridge._routes: dict[str, Callable[[http.server.BaseHTTPRequestHandler], None]]` is built in `__init__` (`transport.py:1285-1290`): seeded with `{"": self._serve_page, "events": self._serve_events}`, then `.update(routes)` for caller-supplied extras (e.g. `cli/artifact/serve.py:189`'s `"history"` route). `do_GET` (`transport.py:1221-1245`) strips the `/{token}` prefix, looks up the remaining suffix as an exact dict key via `bridge._routes.get(route)`, and 404s on a miss — no `{name}`-segment or regex matching exists anywhere in this dict-based dispatch.
- A bare `/{token}` path (no trailing slash) issues a `301` redirect to `/{token}/` (`transport.py:1228-1234`) before route lookup; `LocalBridgeTransport`'s separate `_route()` (`transport.py:638-646`) instead accepts both forms as route `""` with no redirect. **Resolved:** `method_routes` matching runs only on the suffix returned by the shared `_check_host_and_strip_token` helper, so it inherits `SseBridge`'s behavior — bare `/{token}` still `301`s to `/{token}/` for GET and is a `404` for POST; `LocalBridgeTransport._route()` is untouched and the two are deliberately not unified here.
- `LocalBridgeTransport._handle_interaction` (`transport.py:692-716`) is the uncapped precedent the issue warns against: it parses `Content-Length` with a bare `try/except ValueError: length = 0` (no upper-bound check, `transport.py:693-696`), always responds `204` before parsing the body (`transport.py:699-702`), and on a JSON-parse or type failure only calls `_record_inbound_drop(...)` — it never returns a 400/413 status. Every existing error response in `transport.py`/`cli/artifact/serve.py` uses stdlib `send_error()`'s text/html body or a hand-built `text/plain` body (the one existing size-driven `413`, `cli/artifact/serve.py:102-109`, guards an *outbound* export against `artifacts.export.max_artifact_bytes`, not an inbound POST); no JSON-structured error-body convention exists yet in this code to reuse.
- No `{name}`-segment path-param matcher (regex or otherwise) exists anywhere in `scripts/little_loops/**/*.py` today (repo-wide search, no hits) — the `method_routes` bounded single-segment matching has no in-repo precedent to model; it is new surface, not an extension of an existing pattern.
- The renderer-factoring precedent is `build_dashboard_html` (`cli/artifact/dashboard.py:257`, a keyword-only function returning a `RenderedDashboard`) plus its CLI wrapper `cmd_dashboard` (`dashboard.py:398`, which does `write_text`/`logger.success`/`logger.error`) — `_make_page_html_factory` (`serve.py:138`) is a second *consumer* of that same renderer, not itself the factoring precedent. `cmd_policy_builder` is today the only other HTML-emitting `cli/artifact/*.py` command with no such split (`policy_builder.py:62-128`, inline `try`/`write_text` in one function) — this issue's renderer split is the first of its kind for this file, following an established sibling pattern rather than inventing one.
- `_lb_http_request` (`test_transport.py:963-989`) — not the `TestLocalBridgeTransport` class body generally — is the exact helper that drives real HTTP GET/POST requests over a loopback `http.client.HTTPConnection` with explicit `Host`-header control; existing POST call sites (`test_transport.py:1192`, `:1223-1225`) are the direct model for new `SseBridge.do_POST` tests.

## Use Case

A maintainer opens the served builder, picks BUG-123 from the project's issue list, reviews the frozen lifecycle policy, and submits. The page shows "awaiting approval" with the request and queue IDs. From a terminal the maintainer runs `ll-queue run --id ID --approve`; the page transitions to running, shows the real loop instance ID and run dir, then the result, while the author's current draft stays editable and marked as newer than the submitted revision.

## Impact

- Priority: P3 — closes the browser-to-host gap once FEAT-3498's contracts exist.
- Effort: Medium — serializer fix + golden regeneration, transport, renderer split, four routes, reference docs; establishes two conventions with no in-repo precedent (JSON error body, path-param matcher). Split 2026-09-18 at the steps 0–3 / step 4 seam; page wiring is FEAT-3505.
- Risk: Medium — transport surface hardening; the concurrency risk lives in FEAT-3498.

## Acceptance Criteria

- [x] The builder's own `issue_lifecycle` output (regenerated golden fixtures) passes `validate_policy_revision` with `mode="issue_lifecycle"`.
- [x] Submitting through the route while a watcher runs produces `awaiting_approval` and zero subprocess dispatches; serve cannot approve/run; production behavioral tests enforce the level boundary.
- [x] All four connected routes are absent unless `--policy-builder` is passed; when enabled, serve prints the tokenized builder URL. Existing Host/token checks cover every route/method and retain HTML transport errors; dispatched application errors use JSON ErrorBody. The client handles either format. Existing GET/history/SSE tests pass; no CORS headers; oversized, non-JSON, or malformed bodies return 413/400 with no side effects.
- [x] Concurrent duplicate first submissions and exact retries after terminal completion, issue removal, or validator changes map to one queue UUID. Existing matching requests bypass mutable issue/validation/persistence checks; hash/workspace checks remain mandatory and differing stored bindings return `409`. New requests still require all creation checks; explicit Run again creates a fresh awaiting request.
- [x] Restart over the same project rotates the token but keeps `workspace_id`: readback under the new token returns the original queue row; the old token path returns the HTML transport error. A submit/readback carrying another workspace's `workspaceId` returns `403 wrong_workspace`.
- [x] For new requests, invalid YAML, ERROR diagnostics, missing issue, wrong workspace, unsupported mode, and revision-hash mismatch are rejected with the documented status code and JSON `ErrorBody` and leave no runnable entry; hash/workspace/issue failures write nothing under `.loops/policy-builder/`.
- [x] The enqueued `ActionSpec` has `runner=LOOP`, `timeout=None`, and `target` equal to the path `persist_policy_revision` returned.
- [x] Readback of an unknown request returns `404`; a host `ll-queue cancel` surfaces as `cancelled`.
- [x] The served page carries the stamped `{workspaceId}` context and no stamped endpoint or token; the offline CLI render stamps `null`. Readback responses use `Cache-Control: no-store`. An accepted submit returns validator `warnings` in its `200` body.
- [x] Unexpected application failures return JSON `500 internal_error` without a traceback and never roll back a possibly committed request.
- [x] Readback exposes status, bindings, `loopInstanceId`, and `runDir` while running and after completion, distinct from request/queue IDs.
- [x] `cmd_policy_builder`'s CLI output is byte-identical to the existing golden after the renderer split (step 1), and to the once-regenerated golden after the placeholder lands (step 3).
- [x] Connected builder routes are documented at level 2 (`API.md`, `CLI.md`, `ARTIFACT_CONTROL_LEVELS.md`, guide cross-link) with an explicit submitted-YAML/current-dependency guarantee, without claims of reproducible execution or approval-time hash verification; golden and applicable local pytest/Node gates pass.

## Scope Boundaries

Includes the same-origin page route with stamped context, issue-list/submit/readback routes, POST dispatch on `SseBridge`, the serializer `category:` fix, and reference docs. Excludes the page UI, submission controller, JS hashing, workspace-scoped browser storage, browser probe, and guide walkthrough (FEAT-3505), any queue/loop/approval semantics (FEAT-3498), autonomous page/serve execution, remote shell APIs, level-3 event interception, all-mode connected inputs, dependency pinning/reproducible execution and approval-time file hash verification, arbitrary YAML import, and the `_ResourceEntry` control-level forward slot.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

---

## Resolution

- **Action**: implement
- **Completed**: 2026-09-18
- **Status**: Completed

### Changes Made
- `scripts/little_loops/templates/policy_builder_core.mjs`: `_serializeIssueLifecycle` now emits `category: issue_lifecycle`.
- `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle*.yaml`: regenerated (added `category:` line + the connected-context placeholder's downstream golden HTML).
- `scripts/little_loops/cli/artifact/policy_revision.py`: corrected the `RunRequest` docstring (the route, not `persist_policy_revision`, recomputes the hash).
- `scripts/little_loops/cli/artifact/policy_builder.py`: factored `render_policy_builder_html(config, *, workspace_id=None)`; `cmd_policy_builder` is now a thin wrapper.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: added the `/*__CONNECTED_CONTEXT_JSON__*/` placeholder (`const CONNECTED_CONTEXT = ...;`).
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`: regenerated once (covers both the `.mjs` fix and the new placeholder).
- `scripts/little_loops/transport.py`: added `_check_host_and_strip_token`/`_match_method_route` helpers, `SseBridge.do_POST`, and `method_routes`/`extra_url_suffixes` plumbing on `SseBridge`/`serve_sse_bridge`.
- `scripts/little_loops/cli/artifact/policy_builder_routes.py` (new): `make_run_request_routes` — submit/readback/issue-list handlers, body guards, JSON `ErrorBody` boundary.
- `scripts/little_loops/cli/artifact/serve.py`: `--policy-builder` flag, `derive_workspace_id`, and `cmd_serve` composition of the page route + connected routes + `extra_url_suffixes`.
- `scripts/little_loops/cli/artifact/__init__.py`: usage-line example for `--policy-builder`.
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/reference/ARTIFACT_CONTROL_LEVELS.md`, `docs/ARCHITECTURE.md`, `docs/guides/POLICY_ROUTER_GUIDE.md`: level-2 declaration and full connected-route contract.
- Tests: `scripts/tests/test_policy_builder_emit.py` (mode-acceptance parametrized test), `scripts/tests/test_feat3323_sse_bridge.py` (`TestMethodRoutes`), `scripts/tests/test_feat3504_policy_builder_serve.py` (new — route-level HTTP tests against a real `SseBridge`), `scripts/tests/test_wiring_reference_docs.py` (doc-presence gate rows).

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 25044 passed, 53 skipped; 1 unrelated pre-existing failure in `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`, an evidence-quote drift in `.issues/bugs/P2-BUG-3484-...md` last touched 2026-09-15, before and independent of this branch)
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (`python -m mypy scripts/little_loops/`)
- Node conformance gate: PASS (`test_policy_builder_node_gate.py`)
- Doc-wiring gate: PASS (`test_wiring_reference_docs.py`)

## Verification Notes

Verdict at time of check: **VALID** (2026-09-18 `/ll:verify-issues --auto`; no corrections were required, so this section is a record of what was checked, not an outstanding action item)

- Confirmed: `_serializeIssueLifecycle` (`policy_builder_core.mjs:2736`) emits no `category:` line and none of the three `sample-issue-lifecycle*.yaml` fixtures contains one, while `validate_policy_revision` reads `fsm.category` and `_SUPPORTED_MODES = {"issue_lifecycle"}` — the blocker is real.
- Confirmed: FEAT-3498 contracts exist with the cited signatures (`create_or_get_run_request`, `get_run_request` in `queue_store.py`; `validate_policy_revision`/`persist_policy_revision`/`RunRequest`/`PolicyRevisionConflictError` in `policy_revision.py`); `SseBridge` handler has `do_GET` only (`transport.py:1221`) with exact-key `_routes`; `cmd_policy_builder`/`add_serve_parser`/`_make_page_html_factory` anchors hold. All referenced issues (FEAT-3498, ENH-3487/3491/3492, BUG-3490) are done. `ll-verify-evidence`: clean. Proposal-vs-code check found no contradiction.
- Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

Re-verified 2026-09-18 (`/ll:verify-issues --auto`, after the manual-review rewrite): verdict at time of check **VALID**, no corrections needed. `_serializeIssueLifecycle` still at `policy_builder_core.mjs:2736` with no `category:` emit; `SseBridge` `do_GET` at `transport.py:1221` with exact-key `_routes` lookup at `:1239` (the `do_POST` at `:663` belongs to `LocalBridgeTransport`); `cmd_policy_builder` `:62`, `add_serve_parser` `:37`, `_make_page_html_factory` `:138`; `policy_revision.py` `_SUPPORTED_MODES` `:35`, `validate_policy_revision` `:69`, `persist_policy_revision` `:120`; `create_or_get_run_request`/`get_run_request` accept `db_path`/`root`; `find_issues` exists in `issue_parser`. `ll-verify-evidence` clean; no required decision rules; proposal-vs-code check found no contradiction.

Re-verified 2026-09-18 (`/ll:verify-issues --auto`, after the manual architecture review): verdict at time of check **VALID**, no corrections needed. Anchors hold: `_serializeIssueLifecycle` `policy_builder_core.mjs:2736` (no `category: issue_lifecycle` emit; none of the three lifecycle fixtures contains `category`); `SseBridge` `do_GET` `transport.py:1221`, exact-key `_routes.get` `:1239`, `serve_sse_bridge` `:1463`, no `method_routes` yet (`do_POST` `:663` is `LocalBridgeTransport`'s); `cmd_policy_builder` `:62`, `add_serve_parser` `:37`, `_make_page_html_factory` `:138`; `_SUPPORTED_MODES` `:35`, `validate_policy_revision` `:69`, `persist_policy_revision` `:120`; `create_or_get_run_request` `queue_store.py:793`, `get_run_request` `:983`; `find_issues` in `issue_parser`; `policy_builder_routes.py` correctly absent (new). `ll-verify-evidence` clean; no required decision rules; proposal-vs-code check found no contradiction. Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

## Status

**Open** | Created: 2026-09-18 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-18 (re-scored after the FEAT-3505 split)_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- Criterion 4 capped at 10: `format-check` flags `ll-artifact serve --policy-builder` as `stale_cli_flag`. Advisory only — the flag is introduced by this issue, so it cannot resolve yet.
- Two conventions have no in-repo precedent (JSON error body, `{name}` path-param matcher); the bare-token redirect vs. `LocalBridgeTransport` prefix handling is still un-unified.

### Outcome Risk Factors
- Deep per-site complexity: `SseBridge` method-aware dispatch (shared Host/token helper, `method_routes` plumbing) and the nine-step ordered submit path touch shared state across several functions.
- Broad enumeration across ~8 code files plus 5 doc files; the new `policy_builder_routes.py` module and `do_POST` have no existing tests to extend, only the `_lb_http_request` precedent to model.

## Session Log
- `/ll:manage-issue` - 2026-09-19T00:17:26 - `727d50a4-3d11-4caa-b521-922a434d70d0.jsonl`
- `/ll:confidence-check` - 2026-09-18T23:35:38 - `0901fc8f-58be-4fe7-9498-cdadbbef0a77.jsonl`
- `/ll:confidence-check` - 2026-09-18T23:27:27 - `e70d94f5-5aea-4ae6-9697-95afacc0672e.jsonl`
- manual split - 2026-09-18 - moved page half (submission controller, JS hashing, workspace-scoped storage extraction, `.tmpl` binding, Playwright probe, guide walkthrough) to FEAT-3505 (blocked by this issue); kept serializer fix, renderer split, placeholder, transport, routes, reference docs; submit `200` now returns validator `warnings`; spike confirmed all three lifecycle fixtures validate `ok=True` once `category: issue_lifecycle` is prepended
- `/ll:confidence-check` - 2026-09-18T23:14:19 - `908a096d-31f0-483d-82a9-dedb13645d5f.jsonl`
- `/ll:verify-issues` - 2026-09-18T22:52:14 - `607ba042-d4a1-4223-a499-836731f9fcfa.jsonl`
- manual architecture review applied - 2026-09-18 - froze snapshots at Review; defined delivery-state recovery and ambiguous-submit guards; bounded immutability to submitted YAML/current dependencies; moved policy handlers/body guards into a dedicated module with JSON server errors; required a served-page browser probe; added no-store readback and non-overlapping disposable polling. Earlier verification/confidence notes predate this revision.
- `/ll:verify-issues` - 2026-09-18T22:28:52 - `7291996a-6593-4943-af6c-c0b3e4920407.jsonl`
- manual review applied - 2026-09-18 - moved submission state machine into a dependency-injected `.mjs` controller (Node-testable); replaced stamped endpoint URL with relative URLs + connected-context placeholder; specified `method_routes`/`extra_url_suffixes` plumbing, once-resolved project root, field shapes, polling cadence, `find_issues` active-only scope, golden-regeneration timing; dropped redundant `active_theme` param
- `/ll:confidence-check` - 2026-09-18T22:07:29 - `89462603-1252-4507-b232-c85a163bfde9.jsonl`
- `/ll:verify-issues` - 2026-09-18T21:59:57 - `bc5bab11-9b54-483b-9d88-6c04ae5945bc.jsonl`
- `/ll:ready-issue` - 2026-09-18T21:05:48 - `07c743d4-fb4d-457c-985e-2bfb140d83ca.jsonl`
- `/ll:verify-issues` - 2026-09-18T16:33:37 - `8bffa950-7522-4c88-bac6-c0f5c79c2f1a.jsonl`
- manual review applied - 2026-09-18 - moved existing-request recovery ahead of mutable creation checks; specified full-envelope freezing/persistence and async guards, token-rotation/new-URL recovery, workspace storage isolation, --policy-builder flag, and transport/application error boundary; updated tests, design, steps, and acceptance criteria together
- manual review vs. landed FEAT-3498 contracts - 2026-09-18 - added `category:` emit blocker, corrected store/validator signatures, defined workspace id, error-body/status table, submit ordering, body cap, origin-scoped storage, FEAT-3503 overlap; removed resolved `blocked_by: FEAT-3498`
- `/ll:refine-issue` - 2026-09-18T02:34:20 - `e526fcc4-a04f-4fa1-9b46-7e10044a1c18.jsonl`
- `/ll:format-issue` - 2026-09-18T02:26:59 - `17fa148c-98f6-4a6e-975e-5e4a6f742eec.jsonl`
