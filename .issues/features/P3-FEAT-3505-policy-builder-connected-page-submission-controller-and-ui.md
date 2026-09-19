---
id: FEAT-3505
type: FEAT
title: Policy builder connected page submission controller and UI
priority: P3
status: open
discovered_by: manual-split
discovered_date: '2026-09-18'
captured_at: '2026-09-18T23:20:16Z'
parent: EPIC-3493
labels:
- policy-builder
blocked_by:
- ENH-3507
blocks:
- ENH-3500
relates_to:
- FEAT-3504
- ENH-3506
- FEAT-3498
- FEAT-3503
- ENH-3487
confidence_score: 90
outcome_confidence: 66
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 18
missing_artifacts: true
---

# FEAT-3505: Policy builder connected page submission controller and UI

## Summary

Page half of the connected policy builder, split from FEAT-3504 on 2026-09-18 at the seam that issue named (server steps 0–3 vs. page step 4). FEAT-3504 delivers the serializer fix, `render_policy_builder_html`, `SseBridge` method/parameterized dispatch, the `--policy-builder` flag, the stamped `/*__CONNECTED_CONTEXT_JSON__*/` context, and the issues/submit/readback routes with their JSON `ErrorBody` contract — all testable over HTTP. This issue builds the browser side against that landed contract: a dependency-injected submission controller and workspace-scoped submission storage in `policy_builder_core.mjs`, DOM binding in the `.tmpl`, the completed served-page browser probe, and the user guide. The behavior-neutral prerequisites — `createBuilderStorage` (draft/meta/issue-selection extraction) and the probe skeleton — were split into ENH-3507 on 2026-09-19 and land first. No route, queue, loop, or approval semantics change here.

## Current Behavior

After FEAT-3504, `ll-artifact serve --policy-builder` serves the builder at `GET /{token}/policy-builder` with `{workspaceId}` stamped in, and the submit/readback/issues routes work over HTTP, but the page has no connected controls: nothing selects an issue, reviews a snapshot, submits, or polls. After ENH-3507, draft/meta/issue-selection storage goes through `createBuilderStorage` (workspace-namespaced when connected) and a probe skeleton asserts the stamped context, but no submission record, controller, or connected UI exists.

## Expected Behavior

From the served page a user selects a project issue, reviews an immutable policy snapshot, and submits it. The page shows awaiting-approval, running, completion/failure, and host cancellation ("Rejected / cancelled by host") with the real loop instance ID and run dir. Network failures, reloads, and serve restarts preserve the draft, suite, and submission identity. Validation warnings returned with an accepted request are shown as non-blocking (`sample-issue-lifecycle-destinations.yaml` validates `ok=True` with a "State is not reachable from initial state" warning).

## Motivation

The page state machine (freeze/persist/guard/poll/token rotation) is where FEAT-3504's outcome risk concentrated, and it has the thinnest automated coverage. Building it after the server contract has landed and stabilized means the controller is written against real status codes and wire shapes rather than a spec.

## Proposed Solution

### Prerequisite (ENH-3507)

`createBuilderStorage({storage, connectedContext, warn})` and the served-page probe skeleton land in ENH-3507. This issue consumes them: the controller reads/writes issue selection through that helper, uses the same injected `storage`, and extends the probe file as each page behavior lands so wiring breaks surface during the `.tmpl` work instead of at the end. Exact connected key formats for draft/meta/issue-selection are pinned there (`ll-policy-builder-draft-<workspaceId>-<mode>`, `ll-policy-builder-meta-<workspaceId>`, `ll-policy-builder-issue-<workspaceId>`); the probe and Node tests here assert those same strings.

### Page behavior

- **Review precedes submission**: the Review action synchronously freezes a `ReviewedSnapshot {projectId, workspaceId, issueId, yaml}` and operation generation before any await, hashes its exact UTF-8 YAML bytes, then presents that same snapshot and its `revisionId` for review. Submit is unavailable until review preparation completes and consumes only this snapshot; it never serializes the current draft. Draft edits may continue and mark the review as an older snapshot: the user may explicitly submit that visibly identified older snapshot, or rebuild/review to use the new draft. Open, workspace/document changes, issue-selection changes, or switching the active mode away from `issue_lifecycle` invalidate an unsent review and require a new review. Test review A → edit B → submit: only reviewed A can be submitted, with the older-snapshot indicator visible.
- Request payload: `{requestId, projectId, workspaceId, revisionId, yaml, issueId}`. Submit synchronously allocates one request UUID and freezes the complete envelope from the reviewed snapshot before any await. Persist it outside undoable authoring history **before POST**. Retries/reloads resend those exact fields and bytes with the same UUID. A deliberate Run again requires a newly reviewed envelope and a new UUID. If durable storage fails, report it and do not POST; authoring remains usable.
- **Client delivery states are separate from queue status**. Persist mutable delivery metadata alongside, never inside, the immutable envelope: `prepared` (durable, never attempted), `outcome_unknown` (attempt may have reached the server), `rejected` (definitive JSON application rejection with diagnostics), and `accepted` (queue binding known). Persist `outcome_unknown` before invoking POST; failure to persist that transition sends nothing. Success records `accepted` plus queue ID. Recognized application 4xx errors record `rejected`; retain their code/message/validation diagnostics across reload. A conflict must remain a conflict, not silently adopt a differently bound row. Network loss, non-JSON/unrecognized responses, and 5xx leave the outcome unknown. If recording a response fails, retain the durable envelope and reconcile conservatively on reload.
- **Recovery**: a prepared record can be explicitly submitted unchanged. A rejected record stays rejected on reload; corrections require a newly reviewed envelope and UUID, rather than treating a later readback 404 as an interrupted attempt. An unknown outcome is reconciled through readback: a matching row records acceptance, and `404 request_not_found` allows an explicit retry of the identical envelope. Other readback failures preserve state. Already accepted records reconcile their queue status; a missing accepted row is reported as missing and is not automatically recreated. Ordinary Submit is guarded while a request is unresolved; only an explicit new-run choice (explaining that an earlier request may still exist) can create another UUID. A lost response after acceptance must recover the original queue ID.
- Maintain operation identity and an in-flight guard across review hashing and submission: repeated clicks reuse or ignore the pending action. Recheck generation after asynchronous preparation/storage and immediately before POST. Context changes invalidate unsent operations; draft edits alone do not alter reviewed bytes. Responses/polls update only the matching `{workspaceId, projectId, requestId}` record. An already-sent request is not cancelled by changing authoring context.
- Poll readback with at most one in-flight read per request, scheduling the next read 2 s after the preceding read settles. Stop on terminal queue status (`done`, `failed`, `dead_letter`, `cancelled` — verified equal to `QUEUE_TERMINAL_STATUSES`, `little_loops.queue_store`); pause without clearing state after transport/authorization/server failure until explicit retry. Controller disposal or document/context switch clears timers, aborts outstanding reads via an injected abort-controller factory, and invalidates late callbacks; resuming that document reconciles its persisted record. Aborting a read or abandoning a POST response never cancels a server request. Offline (`file://`) and non-lifecycle pages show connected controls unavailable with a reason.
- **Terminal is not permanent.** `ll-queue requeue` revives `failed`/`dead_letter`/`cancelled` rows (back to `awaiting_approval` when never approved, else `pending`). After polling stops, the page offers an explicit **Refresh status** action, and reload reconciliation re-reads accepted records even when their last seen status was terminal; a non-terminal readback resumes polling.
- **Status labels cover all seven `QUEUE_STATUSES`**: `awaiting_approval` → "Awaiting approval", `pending` → "Approved — waiting to run", `running`, `done`, `failed`, `dead_letter` → "Failed — moved to dead letter", `cancelled` → "Rejected / cancelled by host". An unrecognized status is shown verbatim and treated as non-terminal.
- **"Matching row" is defined by bindings.** A readback reconciles a record only when `bindings.issueId` and `bindings.revisionId` equal the envelope's; a mismatch is reported as a conflict and never recorded as `accepted`. Readback carries no `projectId` (the server never stores the page's `projectId`), so that binding is client-only — it scopes storage, not server identity.
- **Warnings are persisted with the accepted record.** Only the first `created:true` response carries `warnings`; the `created:false` early return and readback do not. Store them in `SubmissionDelivery` on acceptance; when acceptance is recovered via readback or a `created:false` retry, show "validation warnings unavailable for this request" rather than implying there were none.
- **Storage layout and retention.** Submission keys: `ll-policy-builder-submission-<workspaceId>-<projectId>-<requestId>` (envelope + delivery), plus one index key `ll-policy-builder-submissions-<workspaceId>-<projectId>` holding `{activeRequestId, recent: [requestId…]}` so reload finds the active record without scanning. **Write order before POST**: record key first, then the index key, and POST only after both writes succeed (a record without an index entry is an orphan reload cannot find; treat either failure as the durable-storage failure case and send nothing). Retain the active record plus the 5 most recent terminal/rejected records per `{workspaceId, projectId}`; prune older ones only after the new index write succeeds. **Strip `yaml` from resolved records** (terminal-`accepted` or `rejected`), keeping `revisionId` and byte length: only `prepared`/`outcome_unknown` records ever resend bytes, and six retained 1 MiB envelopes would otherwise exhaust the ~5 MB origin quota and break draft persistence. A requeued (revived) stripped record still polls normally — it never needs to resend. Never prune or strip an unresolved (`prepared`/`outcome_unknown`/non-terminal `accepted`) record.
- **Multi-tab is out of scope.** The in-flight/generation guards are in-memory per page; two tabs on the same workspace may each mint a UUID. No `storage`-event coordination here — the guide states that one tab per project is the supported shape.
- **Review preconditions.** Review is unavailable (with a reason) when `updatePreview()`'s existing gate fails — `serializeLoopYaml` throws or validation has an error-severity finding — mirroring how copy/download are disabled. Before presenting the snapshot, measure the UTF-8 byte length of the JSON request body that would be sent; if it exceeds the server's 1 MiB cap (`_MAX_RUN_REQUEST_BYTES`), refuse review with a size diagnostic so no UUID is spent on a guaranteed `413 body_too_large`.
- **Mode is page state, not page identity.** Mode is a dropdown on one page (`#mode-switch`, `.tmpl:175`), so "non-lifecycle" means the *active mode*. Outside `issue_lifecycle`, connected controls are disabled with a reason and an unsent review is invalidated; an already-sent record is unaffected — its status stays visible and polling continues, since the request exists on the server regardless of what is being authored.
- **Requeue leaves stale run identity.** `requeue_entry` resets `status`/`result` but does not clear `loop_instance_id`/`run_dir` (`queue_store.py`), and rewrites `result` to `{previous: <prior result>}`. Show `loopInstanceId`/`runDir` as the current run only for `running` and terminal statuses; for `awaiting_approval`/`pending` with those fields set, label them "previous run". Render `result.previous` as the prior attempt's outcome, not as the current result.
- **`result` rendering.** The wire `result` is `{exit_code, timed_out, error, stdout, stderr}` (written by the queue worker, `cli/queue.py`) or `{previous: …}` after requeue, or `null`. It is unbounded and re-fetched on every poll. Show `exit_code`, `timed_out`, `error`, and a truncated tail of `stderr`/`stdout` (last ~40 lines, in a collapsed details element). Loop output is untrusted text: render via `textContent` only, never `innerHTML`. Never persist `result` to storage — it is held in memory and re-read on reload.
- **Issue list.** `GET ./issues` sends no `Cache-Control` (unlike readback) and no server change is in scope, so fetch it with `cache: "no-store"`. The server lists active issues only (`find_issues` default hides `done`/`cancelled`/`deferred`), so a persisted selection can vanish from the list: keep showing the selected ID marked "no longer listed" rather than silently clearing it; submit still gets the authoritative `404 issue_not_found`. Never persist or display the absolute `path` field.
- **Conflict copy.** `409 request_conflict` has two server causes — a `requestId` already bound to a different revision/issue, and `PolicyRevisionConflictError` (same revision name, different stored bytes). Both record `rejected`; UI copy says the request conflicts with an existing one on the host and shows the server `message`, without asserting which cause.
- **Design tokens**: new CSS uses only `var(--name, …)` names declared in the rendered `:root` block (ENH-3506 lands first and adds `--color-status-{success,warning,error,info}-{bg,text}`, which the rejected/warning/unknown states use); ENH-3506's parity pytest enforces this.
- **Transport vs. application errors**: FEAT-3504 keeps pre-dispatch Host/token failures as stdlib HTML (`403`/`404`) and returns JSON `ErrorBody` only after dispatch. The client checks status and Content-Type before decoding JSON and reports a connection/authorization failure for non-JSON responses without deleting submission state.
- **Storage and token rotation:** browser storage is origin-scoped, but connected authoring and submission keys must also include the server-derived `workspaceId`; submission records additionally include `projectId` and `requestId`. Two repositories served at the same origin must not restore each other's drafts, issue selection, or pending submissions. Persist request data, not a tokenized endpoint as authority; the page calls its routes with token-relative URLs (`./run-request`, `./run-request/{id}`, `./issues`).
- **Restart recovery requires the new URL.** `SseBridge` generates a fresh token on each construction. Pinning `--port` preserves the storage origin but does not keep the old URL working. After restart, the user opens the newly printed tokenized builder URL; that page restores its matching workspace/document state and uses its own token-relative URLs for readback/retry. The old page reports disconnection/authorization failure and preserves state; it cannot discover the new token automatically.
- **The submission state machine lives in `policy_builder_core.mjs`, not the `.tmpl`.** Export a `createSubmissionController({fetch, storage, subtle, setTimeout, clearTimeout, randomUUID, makeAbortController, connectedContext})` that owns review-time snapshot freezing, hashing, delivery-state transitions, persist-before-POST, the in-flight/generation guards, request-scoped response routing, polling, reload reconciliation, and workspace-scoped submission keys, and exposes state + a change callback. The `.tmpl` only constructs it with the real browser globals and binds DOM events/rendering. For context-change invalidation, follow the *shape* of the existing `_beginRead`/`boundProject` stale-guard in the import handler (`policy-router-builder.html.tmpl:1653-1660`) but **not its counter**: `sessionRevision` bumps on every `commit()`/`restoreFromSnapshot()` (`.tmpl:447`, `:466`), so reusing it would make every draft edit invalidate the review. The controller owns a separate **context generation**, bumped only by Open-project (`projectId` change), issue-selection change, and active-mode change; the `.tmpl` calls an explicit `controller.contextChanged({projectId, issueId, mode})`. Draft edits reach the controller only as a `draftChanged()` notification that sets the older-snapshot indicator.
- Hashing lives in `policy_builder_core.mjs` as an exported async function accepting injected `subtle` (defaulting to `globalThis.crypto.subtle`, available in Node ≥ 22). `SseBridge` binds `127.0.0.1` only and its Host allowlist is `127.0.0.1:<port>`/`localhost:<port>`, both secure contexts, so `crypto.subtle` and `crypto.randomUUID` are available on the served page.
- **Revision guarantee wording**: UI and docs describe an immutable *submitted YAML snapshot* executed with current project dependencies. No claims of dependency pinning, reproducible execution, or approval-time byte verification (see FEAT-3504 § Revision guarantee).
- "Connected controls unavailable with a reason" has no in-repo convention (the only precedent is whole-block presence via `[[% if serve_enabled %]]` in `dashboard.llat/template.html.j2`); this issue establishes it.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs`: exported SHA-256 helper; `createSubmissionController` (consumes ENH-3507's `createBuilderStorage`).
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: construct the controller with browser globals; DOM binding only — issue selection, review/submission/status UI, warning display, offline/non-lifecycle unavailable-with-reason messaging. No submission state logic inline.
- `scripts/tests/js/policy_submission.test.mjs` (new; the storage test lands in ENH-3507), run by the existing Node gate (`scripts/tests/test_policy_builder_node_gate.py`).
- HTML golden for `scripts/tests/test_enh3035_artifact_template_kit.py`: regenerate once for the connected UI.
- `.loops/probes/` served-page Playwright probe (on-demand): extend ENH-3507's skeleton.
- `docs/guides/POLICY_ROUTER_GUIDE.md`: connected flow, fixed-origin/new-token-URL restart recovery, workspace isolation, durable-storage failure behavior, reviewed-versus-current drafts, delivery-state recovery, the submitted-snapshot/current-dependency guarantee, and local-only verification instructions.

### Dependent Files (Callers/Importers)

- `little_loops.cli.artifact.policy_builder_routes` (new module created by FEAT-3504) — the wire contract this page consumes; not modified here.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/policy_builder.py` — `render_policy_builder_html()` splices the core verbatim at `/*__BUILDER_CORE_JS__*/` and stamps `/*__CONNECTED_CONTEXT_JSON__*/`; no change needed, but the core must contain no leftover `/*__` text and must not reference `CONNECTED_CONTEXT` by bare name (Node import would throw `ReferenceError`) — take it as a `createBuilderStorage`/controller parameter [Agent 1/2 finding]
- `scripts/little_loops/cli/artifact/serve.py` — `--policy-builder` branch renders once with `workspace_id` and serves `_serve_policy_builder_page`; consumer of the page, unchanged [Agent 1 finding]
- `scripts/tests/js/policy_scenarios.test.mjs`, `scripts/tests/js/policy_suggestions.test.mjs` — ES-import named exports from the core; new exports are additive, do not rename/remove existing ones [Agent 1/3 finding]
- `scripts/little_loops/templates/policy_builder_core.mjs` tail `window.PolicyBuilderCore = {…}` bridge (`:3671`, `createBuilderStorage` already exported at `:3597`/`:3704`) — new template-facing exports must be added here; the core shares one module scope with ~2000 lines of template glue, so new top-level names (`createBuilderStorage`, `sha256Hex`, `createSubmissionController`) must not collide with `.tmpl` declarations [Agent 2 finding]
- `scripts/little_loops/fsm/frontmatter_scores.py` — mirrors `encodeFrontmatterScores`/`normalizeDimName()` in the core; unaffected unless those are touched [Agent 1 finding]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- _(Moved to ENH-3507 — listed for awareness; re-check after `.tmpl` binding changes here.)_ `scripts/tests/js/policy_validator.test.mjs` (BUG-3502 harness, `_BOOTSTRAP_SRC`/`_OPEN_HANDLER_SRC`/`_newBug3502Sandbox()`) — **will break**: `_extractBetween(_templateSrc, "let state = seedExample();", "function buildModel() {")` slices the region holding `_persistDraft`/`_readMeta`/`hydrateFromStorage`/`commit`. Once storage moves into `createBuilderStorage`, the vm sandbox lacks it (`ReferenceError`), and bare `CONNECTED_CONTEXT`/`createBuilderStorage`/`PolicyBuilderCore` are undefined there. Inject `createBuilderStorage` (bound to the sandbox `localStorage` stub) and `CONNECTED_CONTEXT` into the sandbox, and keep the four marker strings (`let state = seedExample();`, `function buildModel() {`, `$("open-project-input").onchange = (e) => {`, `$("undo-btn").onclick = () => {`) in the `.tmpl` or update them [Agent 2/3 finding]
- `scripts/tests/test_policy_builder_emit.py` — `test_emit_writes_html` asserts `"/*__" not in html` and `serializeLoopYaml`/`seedExample()`/`blankModel()` present; `test_no_internal_jargon_in_visible_markup` denylist (`Axis A`, `Axis B`, `context.subject`, `policy_rules`, `predicate`, `weight`) applies to new submission UI copy; `id="yaml-details"` must stay non-`open` with `#yaml-preview` nested [Agent 2/3 finding]
- `scripts/tests/test_feat3504_policy_builder_serve.py` — `TestPageRoute.test_serves_html_with_stamped_workspace_context` regex-matches `const CONNECTED_CONTEXT = (\{.*?\});`; keep the classic-script declaration in that exact form (it is a global lexical `const`, not `window.CONNECTED_CONTEXT`) [Agent 2 finding]
- `scripts/tests/test_wiring_reference_docs.py` (`DOC_STRINGS_PRESENT`, line ~254) — pins heading text `Connected authoring & submission` in `POLICY_ROUTER_GUIDE.md`; do not rename that heading; add a FEAT-3505 needle row for the new guide content [Agent 3 finding]
- `scripts/tests/test_docs_audience_gate.py` — applies to `docs/guides/POLICY_ROUTER_GUIDE.md`; the guide must not cite `policy_submission.test.mjs`, `.loops/` probe paths, or `scripts/tests/…` [Agent 3 finding]
- `scripts/tests/test_policy_builder_node_gate.py` — `_serialize_with_node`/`test_round_trip_yaml_validates_for_each_mode` import the real `serializeLoopYaml`; new files under `scripts/tests/js/*.test.mjs` are auto-globbed (no registration) [Agent 3 finding]
- `.loops/probes/feat-3488-browser-probes.mjs` (`:338-343`, `:415`) and `.loops/verify-feat-3488-browser-persistence.yaml` — hardcode `ll-policy-builder-draft-<mode>` and `ll-policy-builder-meta` and the value shapes (`{model, scenarios}`; meta `{projectId, activeMode, schemaVersion, generatorVersion}`); the offline (`connectedContext == null`) byte-identical-keys criterion keeps these passing — re-run after the `.tmpl` rebind [Agent 2 finding]
- New test to write: Node-side non-ASCII `sha256Hex` parity vs Python `hashlib.sha256` (server hashes bytes at `policy_builder_routes.py:200`); no existing JS hash test or fake fetch/timer/`AbortController`/`crypto.subtle` helper exists — `policy_submission.test.mjs` establishes them [Agent 3 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/POLICY_ROUTER_GUIDE.md` — extend the existing `Connected authoring & submission (FEAT-3504)` block (`:365`) rather than adding a parallel section; persistence prose at `:318-335` and scenario-suite persistence at `:532-538` describe drafts (no key names) and should mention workspace scoping; new headings need a `## Contents` entry (`:10-23`) [Agent 2/3 finding]
- `docs/reference/CLI.md` — `Connected policy builder` section (`:5279-5300`) and `--policy-builder` flag rows (`:5228`, `:5234`); pinned by `test_wiring_reference_docs.py`; update only if the page-facing description there changes [Agent 2 finding]
- `docs/ARCHITECTURE.md:936` — FEAT-3504 note on submit/readback routes; add the page-side controller/storage split if it describes the flow [Agent 2 finding]
- `docs/reference/API.md` — `little_loops.cli.artifact.policy_builder_routes` section (pinned heading); no signature change here, so no edit expected [Agent 2 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` (`include = ["little_loops/**", …]`) — package-data glob already covers `templates/*.mjs`/`.tmpl`; no registration needed unless a new template file is introduced [Agent 1 finding]
- `.gitignore:99` (`.loops/policy-builder/`) — probe run output location; confirm the probe's report dir is covered [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

**Landed wire contract (`policy_builder_routes.py`, FEAT-3504) — ground truth the controller must match:**
- Routes under `/{token}/`: `GET policy-builder`, `POST run-request`, `GET run-request/{requestId}?workspaceId=…`, `GET issues`. Pre-dispatch failures (`transport.py` `_make_sse_bridge_handler` / `_check_host_and_strip_token`) are stdlib HTML `403`/`404` (bare `/{token}` GET gets a 301 to `/{token}/`), so the client must check Content-Type before decoding JSON.
- Submit body (`_parse_run_request`): `requestId` lowercase-hex UUID, `revisionId` 64 lowercase hex, `workspaceId` 16 lowercase hex, `projectId`/`issueId` non-empty ≤128 chars, `yaml` non-empty; request must be `Content-Type: application/json` and ≤ 1 MiB (`_MAX_RUN_REQUEST_BYTES`, else `413 body_too_large`); missing/invalid `Content-Length` → `400 bad_request`.
- Server recomputes `sha256(utf8(yaml))`; mismatch with `revisionId` → `422 revision_mismatch`. The client hash must therefore be byte-exact, lowercase hex.
- Application error codes (`ErrorBody = {"error": {code, message, errors?, warnings?}}`, `errors`/`warnings` only on `validation_failed`): `400 bad_request`, `413 body_too_large`, `422 revision_mismatch`, `403 wrong_workspace`, `409 request_conflict`, `404 issue_not_found`, `422 validation_failed`, `500 internal_error`; readback adds `404 request_not_found` and `400 bad_request` (non-UUID id).
- Existing-request early return in `_submit` (`get_run_request` at `policy_builder_routes.py:210`) answers `200 {requestId, queueId, created:false}` **without a `warnings` key** and skips issue/validation/persist steps; only a newly created request returns `warnings`. Readback (`_readback`, `:288`) also carries no warnings. Consequence: validation warnings survive only if the client persists them from the first accepted response — a lost-response recovery cannot re-obtain them.
- Readback body: `{requestId, queueId, status, bindings: {issueId, revisionId}, loopInstanceId, runDir, result}` — `issueId`/`revisionId` are nested under `bindings`, not top-level; sent with `Cache-Control: no-store`. This module does not enumerate queue statuses; the terminal set `done|failed|dead_letter|cancelled` equals `QUEUE_TERMINAL_STATUSES` (`queue_store.py:187`, verified 2026-09-19).
- `GET issues` → `{"issues": [{id, title, priority, status, path}]}`; `path` is an absolute filesystem path (do not persist or display it as identity — `id` is the key). No query handling.

**Connected context and page seams (`policy-router-builder.html.tmpl`):**
- Stamped context is exactly `{"workspaceId": "<16-hex>"}` (`render_policy_builder_html`, `policy_builder.py:66`; `derive_workspace_id` in `serve.py`) or `null` offline. It carries **no `projectId`**; the page's `projectId` is the template-owned value in `_META_KEY` (`_newProjectId`). It is declared `const CONNECTED_CONTEXT = /*__CONNECTED_CONTEXT_JSON__*/;` in a classic `<script>` at `.tmpl:192` and is not read anywhere else yet; visibility from the later module script is unverified.
- Storage surface (extracted into `createBuilderStorage` by ENH-3507): `_DRAFT_KEY_PREFIX + mode`, `_META_KEY` (`{projectId, activeMode, schemaVersion, generatorVersion}`), `_persistDraft`/`_persistAllDrafts`/`_clearDraftKeysExcept`/`_persistMeta`/`_readDraft`/`_readMeta`/`hydrateFromStorage`, called from `commit()`, `restoreFromSnapshot()` and the Open-project path. No scenario-specific, issue-selection, or submission key exists today (scenarios ride inside the draft record `{model, scenarios}`), so "scenario" and "issue-selection" namespacing is new surface. Theme key `ll-policy-builder-theme` has its own inline try/catch.
- Stale-guard precedent: `sessionRevision` (bumped in `commit`/`restoreFromSnapshot`), `_latestReadToken`, `_beginRead()`, `_readStatus(token)` → current/superseded/stale; the import handler binds `boundMode`/`boundProject` and reports "Import discarded…" to `#import-diagnostics`.
- UI attach points: export button row (`#copy-btn`, `#download-btn`, `#save-project-btn`, `#open-project-btn`), `#live-status` (`role="status"`), `#yaml-preview`/`#yaml-details`; `updatePreview()` is the only place YAML is produced (`serializeLoopYaml(buildModel())`, try/catch, disables copy/download on error-severity validation).

**Tests and gates:**
- `scripts/tests/test_policy_builder_node_gate.py::test_node_conformance_suite_passes` globs `scripts/tests/js/*.test.mjs` (180 s timeout, skips when Node < 22), so new `.test.mjs` files are picked up automatically; subdirectory tests (e.g. `js/feat3304/`) are not.
- Golden: `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` compares offline `cmd_policy_builder` output (connected context `null`) with `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`. No regeneration script or flag exists; `.ll/decisions.yaml` (BUG-2303, advisory) requires verifying the captured output before overwriting a golden. Stamped-variant coverage lives in `test_feat3504_policy_builder_serve.py`.
- The existing probe `.loops/probes/feat-3488-browser-probes.mjs` (+ `.loops/verify-feat-3488-browser-persistence.yaml`) loads a `file://` page and does not start a server; `.loops/probes/enh-3507-served-page-probes.mjs` (ENH-3507) does spawn `ll-artifact serve --policy-builder` and parse its printed URL; the FEAT-3488 probe does not. `SseBridge` prints `bridge.url` then `bridge.url + suffix` per `extra_url_suffixes` (`["policy-builder"]` under `--policy-builder`, `serve.py:240`), so the builder URL is the second printed line.

## Program Design

### Types

- `ReviewedSnapshot {projectId, workspaceId, issueId, yaml, revisionId}` — immutable review artifact; `revisionId` is filled from frozen bytes before review becomes ready. Draft edits do not change it; binding changes invalidate it.
- `SubmissionEnvelope {requestId, projectId, workspaceId, issueId, yaml, revisionId}` — immutable client record persisted before POST, scoped outside authoring history; retry resends the exact envelope.
- `SubmissionDelivery {state, queueId?, error?, warnings?}` — mutable persisted metadata separate from the envelope; state is `prepared | outcome_unknown | rejected | accepted`. Queue execution status remains separate.
- Consumed from FEAT-3504 (not redefined): `ErrorBody`, `IssueSummary`, the readback wire dict `{requestId, queueId, status, bindings, loopInstanceId, runDir, result}`.

### Signatures

- `createBuilderStorage(deps) -> storageApi` — delivered by ENH-3507 (`deps = {storage, connectedContext, warn}`); consumed here, not redefined.
- `createSubmissionController(deps) -> controller` — exported from `policy_builder_core.mjs`; all browser globals injected.
- `sha256Hex(text, subtle) -> Promise<string>` — exported from `policy_builder_core.mjs`; hashes the UTF-8 encoding of `text`.

### Call Path

Served page boot → `createBuilderStorage` (ENH-3507) restores the workspace-scoped draft → `createSubmissionController` reconciles any persisted submission via `GET ./run-request/{requestId}?workspaceId=...` → user selects an issue from `GET ./issues` → Review freezes the YAML from the existing `serializeLoopYaml(model)` (`policy_builder_core.mjs`) into the snapshot and computes `sha256Hex` → Submit persists the envelope and `outcome_unknown`, then `POST ./run-request` → `accepted` with queue ID → poll readback every 2 s after settle until terminal status. Server side, the page is rendered by `cmd_policy_builder`'s factored renderer and readback is answered by `get_run_request` (`little_loops.queue_store`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Environment-access convention: `policy_builder_core.mjs` exports are pure functions of their arguments (comments at `rulesFingerprint` and `validateProjectStructure`: no ID generation, clock reads, storage, hashing or `fetch`); the template owns `localStorage`, `crypto.randomUUID` (with a `Date.now()`/`Math.random()` fallback in `_newProjectId`/`_newScenarioId`) and each storage call is try/catch with a once-per-session `showLiveStatus` warning (`_storageWarned`). The DI factories this issue adds (`createBuilderStorage`, `createSubmissionController`) are a deliberate departure — no `createXxx(deps)` precedent exists in the core — so the injected-globals boundary is a new convention to establish, not one to copy.
- The core is spliced verbatim into the template's `<script type="module">` at `/*__BUILDER_CORE_JS__*/` and re-exposed to template glue through the tail `window.PolicyBuilderCore = {…}` bridge (guarded by `typeof window !== "undefined"`); new exports meant for the template must be added to that bridge as well as exported for Node.
- Node test convention: `import { test } from "node:test"`, `assert from "node:assert/strict"`, relative import of the core, issue-ID header comment and issue-ID-prefixed test names (`policy_scenarios.test.mjs`, `policy_validator.test.mjs`). Template glue is tested by slicing source text and running it in a `node:vm` sandbox with faked `localStorage`/`FileReader` (`policy_validator.test.mjs` BUG-3502 section); no fake `fetch`, timers, or `crypto.subtle` helper exists yet — injected fakes for those are new.
- Probe convention (`.loops/probes/feat-3488-browser-probes.mjs`): `PROBES = [{id, needs, acs, run(browser)}]`, `loadPlaywright()` resolution order, `--check` preflight, fresh context per probe, fault injection via `addInitScript`, exit codes 0/2 blocked/1 fail/3 infra with a final `BROWSER_PROBES_*` marker and a JSON report under `${context.run_dir}/`.
- Guide convention (`docs/guides/POLICY_ROUTER_GUIDE.md`): new headings need a `## Contents` entry (line ~10); existing Visual Builder subsections are second-person, bold lead-in labels, no code paths from `scripts/`; the docs-audience gate (`test_docs_audience_gate.py`) applies.

## Implementation Steps

0. Prerequisite: ENH-3507 (storage extraction + probe skeleton) is done, with the offline FEAT-3488 probe re-run and the suite green.
1. Build the SHA-256 helper and `createSubmissionController` test-first with fakes: review preconditions and freezing, context generation (draft edits do not bump it; Open/selection/mode do), persist-before-POST with record→index write order, delivery states, guards, request-scoped responses, non-overlapping disposable polling, reload/restart reconciliation, requeue/`result.previous` handling, retention with YAML stripping.
2. Bind the controller in the `.tmpl` (issue selection, review/submit/status, warnings, result rendering via `textContent`, unavailable-with-reason incl. non-lifecycle mode); regenerate the HTML golden.
3. Complete and run the probe; record the result in verification notes; write the guide section.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `sha256Hex`, `createSubmissionController` to the `window.PolicyBuilderCore` bridge (`createBuilderStorage` is already there from ENH-3507) in `policy_builder_core.mjs`; verify no top-level name collides with `.tmpl` glue; keep the core free of bare `CONNECTED_CONTEXT`/`window`/`crypto` references at module top level (Node dual loading)
- Keep `const CONNECTED_CONTEXT = /*__CONNECTED_CONTEXT_JSON__*/;` in the classic script in its current form (asserted by `test_feat3504_policy_builder_serve.py`); read it as a bare identifier from the module script and pass it into the factories
- Keep new submission UI copy clear of the `test_policy_builder_emit.py` jargon denylist and keep `"/*__" not in html`
- Regenerate `golden_policy_router_builder.html` from `cmd_policy_builder()` output after verifying it (BUG-2303 advisory); no regeneration script exists
- Add a FEAT-3505 needle to `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT`; keep the `Connected authoring & submission` heading text; add `## Contents` entries for any new guide headings; avoid `scripts/tests/` and `.loops/` paths in the guide (audience gate)
- Probe must load the page over `http://127.0.0.1`/`localhost` (secure context) so `crypto.subtle`/`randomUUID` exist; the offline `file://` page has no `crypto.subtle`, so the controller must report connected controls unavailable rather than throw

## Impact

- Priority: P3 — completes the browser-to-host path in EPIC-3493.
- Effort: Medium — one controller, template binding, probe completion, guide (storage extraction moved to ENH-3507).
- Risk: Medium — stateful client logic; mitigated by keeping all of it in the Node-gated `.mjs` and by the served-page probe.

## Use Case

A maintainer opens the served builder, picks BUG-123 from the project's issue list, reviews the frozen lifecycle policy, and submits. The page shows "awaiting approval" with the request and queue IDs. From a terminal the maintainer runs `ll-queue run --id ID --approve`; the page transitions to running, shows the real loop instance ID and run dir, then the result, while the author's current draft stays editable and marked as newer than the submitted revision.

## Acceptance Criteria

- [ ] A controller with a different `workspaceId` sees none of another workspace's submissions (draft/meta/selection isolation is ENH-3507's criterion and is re-verified end-to-end by the probe).
- [ ] Review is unavailable with a reason when serialization throws, validation has an error-severity finding, or the request body would exceed 1 MiB; no UUID is allocated in those cases.
- [ ] Browser SHA-256 of the review-frozen UTF-8 YAML bytes matches Python, including non-ASCII content. Submit consumes only the completed reviewed snapshot; review A → edit B → submit sends visibly identified A. Delayed-hash tests prove all review bindings are captured before the first await; Open/selection/mode changes bump the controller's context generation and invalidate unsent operations, while draft edits (which bump the template's `sessionRevision`) neither invalidate the review nor alter a frozen request. Double clicks create one UUID; stale responses/polls update only their originating submission.
- [ ] The submission state machine is an exported, dependency-injected controller in `policy_builder_core.mjs` covered by the Node gate; the `.tmpl` holds DOM binding only. The served page uses token-relative URLs; polling is non-overlapping, runs at the documented cadence, stops on terminal status, and clears/aborts on disposal or document change without losing request identity.
- [ ] Complete envelopes are persisted before POST outside undo history. Reload/retry resends the exact envelope; a lost response after server acceptance recovers the original queue row. Persistence failure sends no request and shows a diagnostic while leaving authoring usable.
- [ ] Persisted delivery states distinguish prepared, rejected, unknown, and accepted outcomes. Rejected diagnostics survive reload; corrected requests require new review/UUID. Unknown outcomes reconcile before identical retry; ordinary Submit cannot silently create duplicates. Missing accepted rows are reported rather than recreated. `500`/non-JSON responses leave the outcome unknown and clear nothing.
- [ ] After a serve restart on the same origin, opening the newly printed builder URL restores the matching workspace/document envelope and recovers the original queue ID; the old URL fails gracefully without clearing state.
- [ ] The page shows status, bindings, `loopInstanceId`, and `runDir` while running and after completion; all seven queue statuses have a label (`cancelled` is "Rejected / cancelled by host"); validation warnings on an accepted request are persisted with the record, shown as non-blocking, and survive reload; a recovered acceptance says warnings are unavailable.
- [ ] After a terminal status, Refresh status and reload both re-read the row; a requeued request (`cancelled` → `awaiting_approval`) resumes polling. Readback with non-matching `bindings` is reported as a conflict, not accepted. After requeue, a non-running row's `loopInstanceId`/`runDir` are labelled as the previous run and `result.previous` is shown as the prior attempt.
- [ ] `result` is rendered through `textContent` only (a Node/probe test feeds `<img onerror>`-style stdout and asserts no element is created), shown truncated, and never written to storage.
- [ ] Submission storage uses the documented key scheme with a per-`{workspaceId, projectId}` index; the record is written before the index and POST happens only after both succeed; pruning keeps the active record plus 5 recent resolved ones, resolved records have `yaml` stripped, and an unresolved record is never pruned or stripped.
- [ ] Every `var(--…)` name the new UI CSS references is declared in the rendered `:root` block (ENH-3506 parity test green).
- [ ] Offline pages and non-`issue_lifecycle` active modes show connected controls unavailable with a reason, while an already-sent record keeps its status visible and keeps polling across a mode switch; the issue list is fetched with `cache: "no-store"` and a selected issue missing from the list is shown as no longer listed rather than cleared; connection failure/reload retains authoring/scenarios and submission identity; edited drafts distinguish current and submitted revisions.
- [ ] The on-demand served-page Playwright probe (skeleton from ENH-3507) verifies real DOM/controller wiring, review/edit/submit behavior, reload recovery, and actual workspace-scoped draft/scenario/meta/selection/submission storage across two workspaces served sequentially at the same origin; results are recorded. It is not a pytest gate.
- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` documents the connected flow with local-only verification instructions and the submitted-YAML/current-dependency guarantee, without claims of reproducible execution or approval-time hash verification; golden and applicable local pytest/Node gates pass.

## Scope Boundaries

Includes the hash helper, submission controller and its submission-record storage, `.tmpl` binding, browser probe completion, and guide. Excludes `createBuilderStorage` and the probe skeleton (ENH-3507); every server route, `SseBridge` change, error-body contract, and serializer fix (FEAT-3504); queue/loop/approval semantics (FEAT-3498); dependency pinning and approval-time hash verification; all-mode connected inputs; cross-tab coordination.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-18 | Priority: P3

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-09-18 (re-run)_

> **Stale as of 2026-09-19** — predates the ENH-3507 split and the review additions (context generation, mode switch, review preconditions, requeue identity, `result` rendering, YAML stripping). FEAT-3504 and ENH-3506 are done; the only open blocker is ENH-3507. Re-run `/ll:confidence-check`.

**Readiness Score**: 90/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 66/100 → MODERATE (clears 65 gate)

### Gaps to Address
- Unresolved `blocked_by`: `ENH-3506 (open)` — design-token/theme parity work that this issue's new CSS and its parity pytest depend on (FEAT-3504 is completed). Land ENH-3506 first, or drop it from `blocked_by` if the token dependency no longer applies.

### Concerns
- ~~Terminal queue status set not verified~~ — **resolved 2026-09-19**: equals `QUEUE_TERMINAL_STATUSES = {done, failed, dead_letter, cancelled}` (`queue_store.py:187`); `QUEUE_STATUSES` adds `pending`, `running`, `awaiting_approval`.
- ~~`const CONNECTED_CONTEXT` visibility from the module script unverified~~ — **resolved 2026-09-19**: a top-level `const` in a classic script lives in the global lexical environment, which module scripts resolve bare identifiers against (it is not a `window` property). The probe skeleton still asserts it end-to-end.
- Re-run `/ll:confidence-check` after these edits: `outcome_confidence` 64 is below the 65 gate and predates the resolved concerns, the storage-layout/retention spec, and the steps 1–2 commit boundary.
- `createXxx(deps)` DI factories are a deliberate departure from the core's pure-function convention (no precedent) — acceptable, but the injected-globals boundary is a new convention.

### Outcome Risk Factors
- Deep per-site complexity: one stateful controller (freeze/persist/guard/poll/reconcile) with shared state across delivery states, generations, and workspace-scoped storage.
- Broad enumeration across ~8+ sites (core, `.tmpl`, new Node tests, golden, probe, guide, plus existing `policy_validator.test.mjs` BUG-3502 vm harness that will break on storage extraction).
- Test infrastructure for fake `fetch`/timers/`AbortController`/`crypto.subtle` does not exist yet and must be built alongside the controller.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-19_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Line anchors had drifted after FEAT-3504/ENH-3506 landed; updated: inline storage `.tmpl:346-420` → `388-470`, `CONNECTED_CONTEXT` `.tmpl:146-152` → `192`, import stale-guard `:1655` → `1695`, storage warning `:376` → `410-416`, guide block `:359` → `:365`.
- Stale prose: the wire-contract note said the terminal status set was unverified; it equals `QUEUE_TERMINAL_STATUSES` (`queue_store.py:187`).
- Dependencies: `FEAT-3504` and `ENH-3506` are both completed (satisfied `blocked_by`); the Confidence Check Notes' "ENH-3506 open" gap is obsolete. `ENH-3500` backlink present.
- Verified accurate: wire contract (`policy_builder_routes.py` 1 MiB cap, `created:false` early return without `warnings`, readback `bindings`, `request_not_found`), `window.PolicyBuilderCore` bridge (`:3671`, `createBuilderStorage` already exported at `:3597`/`:3704`), `--color-status-*` tokens now in `:root`, `test_wiring_reference_docs.py:254` needle. `ll-verify-evidence` clean; no active required decision rules; Proposed Solution checks (exception handling, fixtures, AC↔Integration Map coverage) found no conflicts.
- Graph: not used (no symbol-anchor mismatches needing relocation).

## Verification Notes (2026-09-19, post-ENH-3507)

_Added by `/ll:verify-issues` — 2026-09-19_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- ENH-3507 is now completed: `createBuilderStorage` exists (`policy_builder_core.mjs:3597`, exported via the `window.PolicyBuilderCore` bridge at `:3704`), key formats match the issue (`ll-policy-builder-draft-<ws>-<mode>`, `-meta-<ws>`, `-issue-<ws>`), the `.tmpl` constructs it (`:412`), and `.loops/probes/enh-3507-served-page-probes.mjs` is the probe skeleton to extend (Implementation Step 0 is satisfied; `blocked_by: ENH-3507` is resolved). `sha256Hex`/`createSubmissionController` are correctly not yet present.
- Line anchors re-drifted after ENH-3507 and were updated: mode dropdown `.tmpl:178` → `175`, `sessionRevision` bumps `:489`/`:508` → `:447`/`:466`, import stale-guard `:1695` → `:1653-1660`, `window.PolicyBuilderCore` bridge `:3587` → `:3671`.
- The Codebase Research Findings bullet "Existing storage surface to be extracted" describes pre-ENH-3507 state; that extraction has landed.
- Probe: the existing `.loops/probes/feat-3488-browser-probes.mjs` note is joined by `enh-3507-served-page-probes.mjs` (spawns `ll-artifact serve --policy-builder`); the "no probe spawns `ll-artifact serve`" claim is obsolete.
- Confidence Check Notes remain stale; re-run `/ll:confidence-check`.
- Verified: `_MAX_RUN_REQUEST_BYTES = 1 << 20`, `QUEUE_TERMINAL_STATUSES` (`queue_store.py:187`), `test_wiring_reference_docs.py:254` needle, guide block `:365`. `ll-verify-evidence` clean; no active required decision rules. Graph: provider=codegraph freshness=fresh (not needed for verdicts).

## Session Log
- `/ll:verify-issues` - 2026-09-19T04:16:29 - `3d7a92b4-7861-4b9c-8726-6a9684278ee3.jsonl`
- manual review + split (ENH-3507) - 2026-09-19
- `/ll:verify-issues` - 2026-09-19T02:19:41 - `c52721e6-1af8-440e-9e0d-6edc23637c58.jsonl`
- `/ll:confidence-check` - 2026-09-19T01:19:27 - `cf4adcf7-d6e9-48b2-bbbd-604a08a5e678.jsonl`
- `/ll:confidence-check` - 2026-09-19T00:55:57 - `5ee7867c-50c0-4d83-996d-3e02625b05e3.jsonl`
- `/ll:wire-issue` - 2026-09-19T00:54:02 - `11fbe36a-230e-4c61-845b-8c1fb6ba2d32.jsonl`
- `/ll:refine-issue` - 2026-09-19T00:47:56 - `2114fa22-5111-44f1-a4b4-c86114783c2c.jsonl`
