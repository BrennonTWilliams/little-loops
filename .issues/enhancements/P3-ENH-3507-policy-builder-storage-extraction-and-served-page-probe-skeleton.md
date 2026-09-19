---
id: ENH-3507
type: ENH
title: Policy builder storage extraction and served-page probe skeleton
priority: P3
status: open
discovered_by: manual-split
discovered_date: '2026-09-19'
captured_at: '2026-09-19T03:00:00Z'
parent: EPIC-3493
labels:
- policy-builder
blocks:
- FEAT-3505
relates_to:
- FEAT-3504
- ENH-3487
- FEAT-3488
---

# ENH-3507: Policy builder storage extraction and served-page probe skeleton

## Summary

Behavior-neutral prerequisite split from FEAT-3505 on 2026-09-19 (its former implementation steps 1–2, which that issue already required to land as a separate commit). Extracts the builder's inline draft/meta storage from `policy-router-builder.html.tmpl` into an exported, injected-storage `createBuilderStorage` in `policy_builder_core.mjs` — workspace-namespaced when served connected, byte-identical keys offline — and adds the on-demand Playwright served-page probe in skeleton form. No submission, review, polling, or UI change here; FEAT-3505 builds the controller on top.

## Current Behavior

Draft/meta storage is inline in the template (`policy-router-builder.html.tmpl:388-470`: `_DRAFT_KEY_PREFIX + mode`, `_META_KEY`, `_persistDraft`/`_persistAllDrafts`/`_clearDraftKeysExcept`/`_persistMeta`/`_readDraft`/`_readMeta`/`hydrateFromStorage`), unscoped by workspace and invisible to the Node gate. `CONNECTED_CONTEXT` is stamped at `.tmpl:192` (FEAT-3504) but read nowhere, so two repositories served at the same origin (`--port` pinned) restore each other's drafts. No probe starts `ll-artifact serve`; the existing FEAT-3488 probe loads a `file://` page only.

## Expected Behavior

All draft, scenario, meta, and issue-selection storage goes through `createBuilderStorage({storage, connectedContext, warn})`. Offline (`connectedContext == null`) the keys and value shapes are byte-identical to today's, so existing drafts keep loading and the FEAT-3488 probe keeps passing. Connected, every key is namespaced by `workspaceId`; unscoped data is never auto-migrated into a workspace. A served-page probe skeleton exists and asserts the stamped context end-to-end.

## Motivation

This refactor has its own regression surface (BUG-3502 vm harness, FEAT-3488 offline probe, HTML golden) independent of the submission controller. Landing it as its own issue means a failed or reverted extraction cannot strand a half-built controller, and FEAT-3505's controller tests start from a Node-testable storage seam and a working probe harness.

## Proposed Solution

### Probe skeleton

Add the on-demand Playwright probe under `.loops/probes/` (never a pytest gate; Playwright resolves from `~/.npm-global/@playwright/test`), following the `.loops/probes/feat-3488-browser-probes.mjs` convention (`PROBES = [{id, needs, acs, run(browser)}]`, `loadPlaywright()`, `--check` preflight, fresh context per probe, exit codes 0/2/1/3, final marker line, JSON report under `${context.run_dir}/`). Skeleton behavior: spawn `ll-artifact serve --policy-builder`, parse the builder URL (the **second** printed line — `bridge.url + "policy-builder"`, `serve.py:240`), load it over `http://127.0.0.1` (secure context), and assert the page's `CONNECTED_CONTEXT.workspaceId` equals the server's `workspaceId`. Kill the server on exit. FEAT-3505 extends this file.

### `createBuilderStorage`

Exported from `policy_builder_core.mjs`; `deps = {storage, connectedContext, warn}`.

- **Key formats (exact).** Offline: `ll-policy-builder-draft-<mode>`, `ll-policy-builder-meta` (unchanged). Connected: `ll-policy-builder-draft-<workspaceId>-<mode>`, `ll-policy-builder-meta-<workspaceId>`, `ll-policy-builder-issue-<workspaceId>` (issue selection — new surface, connected-only; offline the selection API is a no-op returning `null`). `workspaceId` is 16 lowercase hex and modes are fixed identifiers, so connected keys cannot collide with offline ones. Scenarios keep riding inside the draft record `{model, scenarios}`; there is no separate scenario key. Theme key `ll-policy-builder-theme` stays unscoped and stays in the template.
- Value shapes unchanged: draft `{model, scenarios}`; meta `{projectId, activeMode, schemaVersion, generatorVersion}`. Issue selection stores `{issueId}` only (never the absolute `path` from `GET issues`).
- API mirrors the extracted functions: persist/read/clear drafts, persist/read meta, read/write issue selection. Every storage call stays try/catch; the once-per-session warning (`.tmpl:410-416`, `_storageWarned`/`showLiveStatus`) is routed through the injected `warn` callback, with the once-only latch inside the helper.
- The core must not reference `CONNECTED_CONTEXT`, `window`, or `localStorage` by bare name at module top level (Node dual loading); the template reads `CONNECTED_CONTEXT` as a bare identifier from the module script and passes it in. Keep `const CONNECTED_CONTEXT = /*__CONNECTED_CONTEXT_JSON__*/;` in its exact current form (regex-asserted by `test_feat3504_policy_builder_serve.py`).
- Add `createBuilderStorage` to the `window.PolicyBuilderCore` bridge (`policy_builder_core.mjs:3587`); verify the name does not collide with `.tmpl` glue declarations (shared module scope). Update the purity comments (`:1054`, `:1173`) to carve out DI factories: the module still touches no ambient globals; factories receive them injected.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs` — `createBuilderStorage`, bridge entry, purity-comment carve-out.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — replace inline storage (`:388-470`) with `createBuilderStorage` calls; `commit()`, `restoreFromSnapshot()`, `hydrateFromStorage`, and the Open-project path keep only the calls.
- `scripts/tests/js/policy_storage.test.mjs` (new) — auto-globbed by `scripts/tests/test_policy_builder_node_gate.py`.
- `scripts/tests/js/policy_validator.test.mjs` — BUG-3502 harness **will break**: `_extractBetween(_templateSrc, "let state = seedExample();", "function buildModel() {")` slices the region holding the storage functions. Inject `createBuilderStorage` (bound to the sandbox `localStorage` stub) and `CONNECTED_CONTEXT` into `_newBug3502Sandbox()`; keep or update the four marker strings (`let state = seedExample();`, `function buildModel() {`, `$("open-project-input").onchange = (e) => {`, `$("undo-btn").onclick = () => {`).
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate from `cmd_policy_builder()` output after verifying it (BUG-2303 advisory; no regeneration script exists).
- `.loops/probes/` — new served-page probe (skeleton); confirm its report dir is gitignored (`.gitignore:99` covers `.loops/policy-builder/`).

### Tests

- `scripts/tests/test_policy_builder_emit.py` — `"/*__" not in html` must still hold.
- `.loops/probes/feat-3488-browser-probes.mjs` + `.loops/verify-feat-3488-browser-persistence.yaml` — hardcode the offline key names and value shapes; re-run after the rebind.
- `scripts/tests/test_feat3504_policy_builder_serve.py::TestPageRoute::test_serves_html_with_stamped_workspace_context` — unchanged declaration form keeps it green.

### Documentation

- `docs/guides/POLICY_ROUTER_GUIDE.md` persistence prose (`:318-335`, `:532-538`): one sentence that drafts on a served page are kept per project workspace. No key names; audience gate applies. Full connected-flow docs stay in FEAT-3505.

## Program Design

### Types

- `BuilderStorageDeps {storage, connectedContext, warn}` — injected `Storage`-like object, the stamped `{workspaceId}` or `null`, and a once-per-session warning callback.
- `DraftRecord {model, scenarios}` and `MetaRecord {projectId, activeMode, schemaVersion, generatorVersion}` — unchanged persisted shapes.
- `IssueSelection {issueId}` — new, connected-only.

### Signatures

- `createBuilderStorage(deps) -> storageApi` — exported from `policy_builder_core.mjs`; owns key derivation and guarded draft/meta/issue-selection reads and writes.

### Call Path

Page boot → the module script reads the stamped `CONNECTED_CONTEXT` (from `render_policy_builder_html`, `little_loops.cli.artifact.policy_builder`) → `createBuilderStorage` → `hydrateFromStorage` reads meta and per-mode drafts through it → `commit()` / `restoreFromSnapshot()` / Open-project persist through it. Offline pages are emitted by `cmd_policy_builder` with a `null` context.

## Implementation Steps

1. Add the probe skeleton; run it against current `main` (passes before any refactor — it only reads the stamped context).
2. Write `policy_storage.test.mjs` test-first: offline keys byte-identical; connected keys match the exact formats above; two `workspaceId`s are mutually invisible; no auto-migration of unscoped data; `warn` fires once per helper instance; a throwing `storage` never throws out of the helper.
3. Implement `createBuilderStorage`; rebind the `.tmpl`; fix the BUG-3502 harness in the same change.
4. Verify and regenerate the golden; run the Node gate and the pytest suite; re-run the FEAT-3488 offline probe and the new skeleton probe; record results in verification notes.

## Acceptance Criteria

- [ ] Draft, scenario, meta, and issue-selection storage go through an exported `createBuilderStorage` in `policy_builder_core.mjs`, covered by the Node gate; the `.tmpl` contains no direct `localStorage` draft/meta access (theme key excepted).
- [ ] Offline keys and value shapes are byte-identical to today's; the FEAT-3488 browser probe passes unchanged after the rebind.
- [ ] Connected keys use the exact documented formats; a storage instance with a different `workspaceId` sees none of another workspace's drafts, meta, or issue selection. Unscoped data is not auto-migrated.
- [ ] Storage failures never throw into authoring; the once-per-session warning still appears via the injected callback.
- [ ] The BUG-3502 vm harness passes with the injected helper; golden regenerated after verification; `python -m pytest scripts/tests/` and the Node gate are green.
- [ ] The served-page probe skeleton starts `ll-artifact serve --policy-builder`, loads the printed builder URL over `http://127.0.0.1`, asserts the stamped `workspaceId`, and cleans up the server. It is not a pytest gate; its result is recorded.

## Scope Boundaries

Includes the storage helper, `.tmpl` rebind, harness fix, golden, storage Node tests, and probe skeleton. Excludes the submission controller, `sha256Hex`, submission storage keys/index/retention, all connected UI, and the connected-flow guide section (FEAT-3505); every server route and `SseBridge` change (FEAT-3504).

## Impact

- Priority: P3 — prerequisite for FEAT-3505 in EPIC-3493.
- Effort: Small–Medium — one helper, one template rebind, one harness fix, one probe file.
- Risk: Low–Medium — behavior-neutral, but touches the persistence path every builder session uses; mitigated by byte-identical offline keys and the existing offline probe.

## Status

**Open** | Created: 2026-09-19 | Priority: P3

## Verification Notes

**Verdict: VALID** (verified 2026-09-18; no corrections needed)

- Template anchors hold: storage functions at `.tmpl:388-470`, `CONNECTED_CONTEXT` stamped at `:192` and read nowhere else, `hydrateFromStorage()` at `:531`/`:2169`, Open-project path at `:2088-2090`.
- Core anchors hold: bridge at `policy_builder_core.mjs:3587`, purity comments at `:1054` and `:1173`; no `createBuilderStorage` or `sha256Hex` exists yet (consistent with scope split).
- BUG-3502 harness markers all present (`policy_validator.test.mjs:1559-1568`, `_newBug3502Sandbox` at `:1572`).
- Probe convention confirmed in `feat-3488-browser-probes.mjs` (`PROBES`, `loadPlaywright`, `--check`, `BROWSER_PROBES_*` markers). "Second printed line" holds: `transport.py:1586-1588` prints `bridge.url` then `bridge.url + suffix`; `serve.py:240` sets suffix `policy-builder`.
- `.gitignore:99` covers `.loops/policy-builder/`; golden fixture and `test_feat3504` regex on `const CONNECTED_CONTEXT = ` exist. Decisions check ran, and `ll-verify-evidence` reported 0 findings. Proposal-vs-code check found no unsound consequences.
- Graph: provider=codegraph, freshness=fresh (used only for `defines` corroboration).

---

## Session Log
- `/ll:verify-issues` - 2026-09-19T02:35:35 - `c21faf03-4a0d-488c-8584-9577fe7b87f5.jsonl`
- manual split from FEAT-3505 - 2026-09-19
