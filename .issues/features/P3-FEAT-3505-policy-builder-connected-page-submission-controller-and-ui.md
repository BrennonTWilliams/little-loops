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
- FEAT-3504
relates_to:
- FEAT-3498
- FEAT-3503
- ENH-3487
---

# FEAT-3505: Policy builder connected page submission controller and UI

## Summary

Page half of the connected policy builder, split from FEAT-3504 on 2026-09-18 at the seam that issue named (server steps 0–3 vs. page step 4). FEAT-3504 delivers the serializer fix, `render_policy_builder_html`, `SseBridge` method/parameterized dispatch, the `--policy-builder` flag, the stamped `/*__CONNECTED_CONTEXT_JSON__*/` context, and the issues/submit/readback routes with their JSON `ErrorBody` contract — all testable over HTTP. This issue builds the browser side against that landed contract: a dependency-injected submission controller and workspace-scoped storage in `policy_builder_core.mjs`, DOM binding in the `.tmpl`, the served-page browser probe, and the user guide. No route, queue, loop, or approval semantics change here.

## Current Behavior

After FEAT-3504, `ll-artifact serve --policy-builder` serves the builder at `GET /{token}/policy-builder` with `{workspaceId}` stamped in, and the submit/readback/issues routes work over HTTP, but the page has no connected controls: nothing selects an issue, reviews a snapshot, submits, or polls. Draft/meta storage is inline in the template (`policy-router-builder.html.tmpl:346-420`, keys `_DRAFT_KEY_PREFIX + mode` and `_META_KEY`), unscoped by workspace and outside the Node gate.

## Expected Behavior

From the served page a user selects a project issue, reviews an immutable policy snapshot, and submits it. The page shows awaiting-approval, running, completion/failure, and host cancellation ("Rejected / cancelled by host") with the real loop instance ID and run dir. Network failures, reloads, and serve restarts preserve the draft, suite, and submission identity. Validation warnings returned with an accepted request are shown as non-blocking (`sample-issue-lifecycle-destinations.yaml` validates `ok=True` with a "State is not reachable from initial state" warning).

## Motivation

The page state machine (freeze/persist/guard/poll/token rotation) is where FEAT-3504's outcome risk concentrated, and it has the thinnest automated coverage. Building it after the server contract has landed and stabilized means the controller is written against real status codes and wire shapes rather than a spec.

## Proposed Solution

### Probe skeleton first

Before any controller or template work, add the on-demand Playwright probe under `.loops/` (never a pytest gate; Playwright resolves from `~/.npm-global/@playwright/test`) in skeleton form: start `ll-artifact serve --policy-builder`, open the printed builder URL, and assert the stamped connected context equals the server's `workspaceId`. Extend it as each page behavior lands so wiring breaks surface during the `.tmpl` work instead of at the end.

### Storage extraction (before the controller)

Workspace-scoping the draft/scenario/meta/selection keys means rewriting the inline storage code at `.tmpl:346-420`, which the Node gate cannot see. Extract it into an exported, injected-storage helper in `policy_builder_core.mjs` — `createBuilderStorage({storage, connectedContext})` — owning draft, scenario, meta, and issue-selection keys. With `connectedContext == null` (offline `file://`) the keys are byte-identical to today's, so existing offline drafts keep loading; with a `workspaceId` every key is namespaced by it. Do not migrate unscoped data into a workspace automatically. The theme key (`ll-policy-builder-theme`) stays unscoped. The `.tmpl` keeps only the calls. This makes the workspace-isolation criterion Node-testable instead of resting on the browser probe alone.

### Page behavior

- **Review precedes submission**: the Review action synchronously freezes a `ReviewedSnapshot {projectId, workspaceId, issueId, yaml}` and operation generation before any await, hashes its exact UTF-8 YAML bytes, then presents that same snapshot and its `revisionId` for review. Submit is unavailable until review preparation completes and consumes only this snapshot; it never serializes the current draft. Draft edits may continue and mark the review as an older snapshot: the user may explicitly submit that visibly identified older snapshot, or rebuild/review to use the new draft. Open, workspace/document changes, or issue-selection changes invalidate an unsent review and require a new review. Test review A → edit B → submit: only reviewed A can be submitted, with the older-snapshot indicator visible.
- Request payload: `{requestId, projectId, workspaceId, revisionId, yaml, issueId}`. Submit synchronously allocates one request UUID and freezes the complete envelope from the reviewed snapshot before any await. Persist it outside undoable authoring history **before POST**. Retries/reloads resend those exact fields and bytes with the same UUID. A deliberate Run again requires a newly reviewed envelope and a new UUID. If durable storage fails, report it and do not POST; authoring remains usable.
- **Client delivery states are separate from queue status**. Persist mutable delivery metadata alongside, never inside, the immutable envelope: `prepared` (durable, never attempted), `outcome_unknown` (attempt may have reached the server), `rejected` (definitive JSON application rejection with diagnostics), and `accepted` (queue binding known). Persist `outcome_unknown` before invoking POST; failure to persist that transition sends nothing. Success records `accepted` plus queue ID. Recognized application 4xx errors record `rejected`; retain their code/message/validation diagnostics across reload. A conflict must remain a conflict, not silently adopt a differently bound row. Network loss, non-JSON/unrecognized responses, and 5xx leave the outcome unknown. If recording a response fails, retain the durable envelope and reconcile conservatively on reload.
- **Recovery**: a prepared record can be explicitly submitted unchanged. A rejected record stays rejected on reload; corrections require a newly reviewed envelope and UUID, rather than treating a later readback 404 as an interrupted attempt. An unknown outcome is reconciled through readback: a matching row records acceptance, and `404 request_not_found` allows an explicit retry of the identical envelope. Other readback failures preserve state. Already accepted records reconcile their queue status; a missing accepted row is reported as missing and is not automatically recreated. Ordinary Submit is guarded while a request is unresolved; only an explicit new-run choice (explaining that an earlier request may still exist) can create another UUID. A lost response after acceptance must recover the original queue ID.
- Maintain operation identity and an in-flight guard across review hashing and submission: repeated clicks reuse or ignore the pending action. Recheck generation after asynchronous preparation/storage and immediately before POST. Context changes invalidate unsent operations; draft edits alone do not alter reviewed bytes. Responses/polls update only the matching `{workspaceId, projectId, requestId}` record. An already-sent request is not cancelled by changing authoring context.
- Poll readback with at most one in-flight read per request, scheduling the next read 2 s after the preceding read settles. Stop on terminal queue status (`done`, `failed`, `dead_letter`, `cancelled`); pause without clearing state after transport/authorization/server failure until explicit retry. Controller disposal or document/context switch clears timers, aborts outstanding reads via an injected abort-controller factory, and invalidates late callbacks; resuming that document reconciles its persisted record. Aborting a read or abandoning a POST response never cancels a server request. Offline (`file://`) and non-lifecycle pages show connected controls unavailable with a reason.
- **Transport vs. application errors**: FEAT-3504 keeps pre-dispatch Host/token failures as stdlib HTML (`403`/`404`) and returns JSON `ErrorBody` only after dispatch. The client checks status and Content-Type before decoding JSON and reports a connection/authorization failure for non-JSON responses without deleting submission state.
- **Storage and token rotation:** browser storage is origin-scoped, but connected authoring and submission keys must also include the server-derived `workspaceId`; submission records additionally include `projectId` and `requestId`. Two repositories served at the same origin must not restore each other's drafts, issue selection, or pending submissions. Persist request data, not a tokenized endpoint as authority; the page calls its routes with token-relative URLs (`./run-request`, `./run-request/{id}`, `./issues`).
- **Restart recovery requires the new URL.** `SseBridge` generates a fresh token on each construction. Pinning `--port` preserves the storage origin but does not keep the old URL working. After restart, the user opens the newly printed tokenized builder URL; that page restores its matching workspace/document state and uses its own token-relative URLs for readback/retry. The old page reports disconnection/authorization failure and preserves state; it cannot discover the new token automatically.
- **The submission state machine lives in `policy_builder_core.mjs`, not the `.tmpl`.** Export a `createSubmissionController({fetch, storage, subtle, setTimeout, clearTimeout, randomUUID, makeAbortController, connectedContext})` that owns review-time snapshot freezing, hashing, delivery-state transitions, persist-before-POST, the in-flight/generation guards, request-scoped response routing, polling, reload reconciliation, and workspace-scoped submission keys, and exposes state + a change callback. The `.tmpl` only constructs it with the real browser globals and binds DOM events/rendering. For context-change invalidation, follow the existing `_beginRead`/`boundProject` stale-guard in the import handler (`policy-router-builder.html.tmpl:1655`).
- Hashing lives in `policy_builder_core.mjs` as an exported async function accepting injected `subtle` (defaulting to `globalThis.crypto.subtle`, available in Node ≥ 22). `SseBridge` binds `127.0.0.1` only and its Host allowlist is `127.0.0.1:<port>`/`localhost:<port>`, both secure contexts, so `crypto.subtle` and `crypto.randomUUID` are available on the served page.
- **Revision guarantee wording**: UI and docs describe an immutable *submitted YAML snapshot* executed with current project dependencies. No claims of dependency pinning, reproducible execution, or approval-time byte verification (see FEAT-3504 § Revision guarantee).
- "Connected controls unavailable with a reason" has no in-repo convention (the only precedent is whole-block presence via `[[% if serve_enabled %]]` in `dashboard.llat/template.html.j2`); this issue establishes it.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs`: `createBuilderStorage` (extracted draft/scenario/meta/selection storage, workspace-namespaced when connected); exported SHA-256 helper; `createSubmissionController`.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: replace inline storage with `createBuilderStorage` calls; construct the controller with browser globals; DOM binding only — issue selection, review/submission/status UI, warning display, offline/non-lifecycle unavailable-with-reason messaging. No submission state logic inline.
- `scripts/tests/js/policy_submission.test.mjs` (new) and a storage test alongside it, run by the existing Node gate (`scripts/tests/test_policy_builder_node_gate.py`).
- HTML golden for `scripts/tests/test_enh3035_artifact_template_kit.py`: regenerate once for the connected UI.
- `.loops/` Playwright probe (on-demand).
- `docs/guides/POLICY_ROUTER_GUIDE.md`: connected flow, fixed-origin/new-token-URL restart recovery, workspace isolation, durable-storage failure behavior, reviewed-versus-current drafts, delivery-state recovery, the submitted-snapshot/current-dependency guarantee, and local-only verification instructions.

### Dependent Files (Callers/Importers)

- `little_loops.cli.artifact.policy_builder_routes` (new module created by FEAT-3504) — the wire contract this page consumes; not modified here.

## Program Design

### Types

- `ReviewedSnapshot {projectId, workspaceId, issueId, yaml, revisionId}` — immutable review artifact; `revisionId` is filled from frozen bytes before review becomes ready. Draft edits do not change it; binding changes invalidate it.
- `SubmissionEnvelope {requestId, projectId, workspaceId, issueId, yaml, revisionId}` — immutable client record persisted before POST, scoped outside authoring history; retry resends the exact envelope.
- `SubmissionDelivery {state, queueId?, error?}` — mutable persisted metadata separate from the envelope; state is `prepared | outcome_unknown | rejected | accepted`. Queue execution status remains separate.
- Consumed from FEAT-3504 (not redefined): `ErrorBody`, `IssueSummary`, the readback wire dict `{requestId, queueId, status, bindings, loopInstanceId, runDir, result}`.

### Signatures

- `createBuilderStorage(deps) -> storageApi` — exported from `policy_builder_core.mjs`; `deps = {storage, connectedContext}`.
- `createSubmissionController(deps) -> controller` — exported from `policy_builder_core.mjs`; all browser globals injected.
- `sha256Hex(text, subtle) -> Promise<string>` — exported from `policy_builder_core.mjs`; hashes the UTF-8 encoding of `text`.

### Call Path

Served page boot → `createBuilderStorage` restores the workspace-scoped draft → `createSubmissionController` reconciles any persisted submission via `GET ./run-request/{requestId}?workspaceId=...` → user selects an issue from `GET ./issues` → Review freezes the YAML from the existing `serializeLoopYaml(model)` (`policy_builder_core.mjs`) into the snapshot and computes `sha256Hex` → Submit persists the envelope and `outcome_unknown`, then `POST ./run-request` → `accepted` with queue ID → poll readback every 2 s after settle until terminal status. Server side, the page is rendered by `cmd_policy_builder`'s factored renderer and readback is answered by `get_run_request` (`little_loops.queue_store`).

## Implementation Steps

1. Add the Playwright probe skeleton (serve, load builder URL, assert stamped `workspaceId`).
2. Extract inline draft/meta storage into `createBuilderStorage` test-first under the Node gate; offline keys unchanged, connected keys workspace-namespaced; rebind the `.tmpl`.
3. Build the SHA-256 helper and `createSubmissionController` test-first with fakes: review freezing, persist-before-POST, delivery states, guards, request-scoped responses, non-overlapping disposable polling, reload/restart reconciliation.
4. Bind the controller in the `.tmpl` (issue selection, review/submit/status, warnings, unavailable-with-reason); regenerate the HTML golden.
5. Complete and run the probe; record the result in verification notes; write the guide section.

## Impact

- Priority: P3 — completes the browser-to-host path in EPIC-3493.
- Effort: Medium — one controller, one storage extraction, template binding, probe, guide.
- Risk: Medium — stateful client logic; mitigated by keeping all of it in the Node-gated `.mjs` and by the served-page probe.

## Use Case

A maintainer opens the served builder, picks BUG-123 from the project's issue list, reviews the frozen lifecycle policy, and submits. The page shows "awaiting approval" with the request and queue IDs. From a terminal the maintainer runs `ll-queue run --id ID --approve`; the page transitions to running, shows the real loop instance ID and run dir, then the result, while the author's current draft stays editable and marked as newer than the submitted revision.

## Acceptance Criteria

- [ ] Draft, scenario, meta, and issue-selection storage go through an exported `createBuilderStorage` in `policy_builder_core.mjs` covered by the Node gate; offline keys are unchanged from today, connected keys are namespaced by `workspaceId`, and a controller/storage pair with a different `workspaceId` sees none of another workspace's drafts or submissions. Unscoped data is not auto-migrated.
- [ ] Browser SHA-256 of the review-frozen UTF-8 YAML bytes matches Python, including non-ASCII content. Submit consumes only the completed reviewed snapshot; review A → edit B → submit sends visibly identified A. Delayed-hash tests prove all review bindings are captured before the first await; Open/selection changes invalidate unsent operations, while draft edits do not alter a frozen request. Double clicks create one UUID; stale responses/polls update only their originating submission.
- [ ] The submission state machine is an exported, dependency-injected controller in `policy_builder_core.mjs` covered by the Node gate; the `.tmpl` holds DOM binding only. The served page uses token-relative URLs; polling is non-overlapping, runs at the documented cadence, stops on terminal status, and clears/aborts on disposal or document change without losing request identity.
- [ ] Complete envelopes are persisted before POST outside undo history. Reload/retry resends the exact envelope; a lost response after server acceptance recovers the original queue row. Persistence failure sends no request and shows a diagnostic while leaving authoring usable.
- [ ] Persisted delivery states distinguish prepared, rejected, unknown, and accepted outcomes. Rejected diagnostics survive reload; corrected requests require new review/UUID. Unknown outcomes reconcile before identical retry; ordinary Submit cannot silently create duplicates. Missing accepted rows are reported rather than recreated. `500`/non-JSON responses leave the outcome unknown and clear nothing.
- [ ] After a serve restart on the same origin, opening the newly printed builder URL restores the matching workspace/document envelope and recovers the original queue ID; the old URL fails gracefully without clearing state.
- [ ] The page shows status, bindings, `loopInstanceId`, and `runDir` while running and after completion; `cancelled` is labelled "Rejected / cancelled by host"; validation warnings on an accepted request are shown as non-blocking.
- [ ] Offline/non-lifecycle pages show connected controls unavailable with a reason; connection failure/reload retains authoring/scenarios and submission identity; edited drafts distinguish current and submitted revisions.
- [ ] The on-demand served-page Playwright probe (skeleton landed first) verifies real DOM/controller wiring, review/edit/submit behavior, reload recovery, and actual workspace-scoped draft/scenario/meta/selection/submission storage across two workspaces served sequentially at the same origin; results are recorded. It is not a pytest gate.
- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` documents the connected flow with local-only verification instructions and the submitted-YAML/current-dependency guarantee, without claims of reproducible execution or approval-time hash verification; golden and applicable local pytest/Node gates pass.

## Scope Boundaries

Includes the `.mjs` storage helper, hash helper, submission controller, `.tmpl` binding, browser probe, and guide. Excludes every server route, `SseBridge` change, error-body contract, and serializer fix (FEAT-3504); queue/loop/approval semantics (FEAT-3498); dependency pinning and approval-time hash verification; all-mode connected inputs.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-18 | Priority: P3
