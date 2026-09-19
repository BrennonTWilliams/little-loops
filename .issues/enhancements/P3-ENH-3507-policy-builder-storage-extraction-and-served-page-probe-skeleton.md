---
id: ENH-3507
type: ENH
title: Policy builder storage extraction and served-page probe skeleton
priority: P3
status: done
discovered_by: manual-split
discovered_date: '2026-09-19'
captured_at: '2026-09-19T03:00:00Z'
completed_at: '2026-09-19T04:14:47Z'
parent: EPIC-3493
labels:
- policy-builder
blocks:
- FEAT-3505
relates_to:
- FEAT-3504
- ENH-3487
- FEAT-3488
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

- **Stdout flush (prerequisite server fix).** `serve_sse_bridge` prints the URLs with plain `print()` (`transport.py:1586-1588`); with stdout piped, Python block-buffers them and the probe never sees a line (reproduced 2026-09-18: `ll-artifact serve --policy-builder --port 8799 > file` wrote 0 bytes after 4 s, and 0 after SIGTERM). Add `flush=True` to the `print(bridge.url)` and `print(bridge.url + suffix)` calls — this also fixes any user piping `ll-artifact serve`. The probe additionally spawns with `PYTHONUNBUFFERED=1` as a backstop, and fails with exit 3 (infra) if no builder URL arrives within a bounded wait instead of hanging.
- **Port.** Always pass an explicit non-default `--port` (default `8766` collides with a developer's running `ll-artifact serve`; `EADDRINUSE` → exit 1). Accept the port as a CLI arg with a non-default fallback.
- **Independent expected id.** Compute the expected `workspaceId` in the probe as the first 16 hex chars of `sha256(realpath(cwd))`, mirroring `derive_workspace_id` (`serve.py:58`), and spawn the server with that same `cwd` — never compare the page against a value read from the page.
- **Reading the context.** `CONNECTED_CONTEXT` is a top-level `const` in a classic script: global lexical environment, **not** a `window` property. Read it as `page.evaluate("CONNECTED_CONTEXT.workspaceId")`, never `window.CONNECTED_CONTEXT`.
- **Cleanup.** Kill the server in a `finally` and on `SIGINT`/`SIGTERM`, so a failed assertion or Ctrl-C never strands a listener on the probe port.
- **Two probes.** `context` (`needs: []`) — the stamped-context assertion above; passes on current `main` before the refactor. `connected-storage` (`needs: ["storage-rebind"]`) — after the rebind: make one committed edit on the served page, then assert `localStorage` holds `ll-policy-builder-draft-<workspaceId>-<mode>` and `ll-policy-builder-meta-<workspaceId>` and **no** unscoped `ll-policy-builder-draft-<mode>` / `ll-policy-builder-meta` key was written. This is the only check that the `.tmpl` really passes `CONNECTED_CONTEXT` into the helper (Node tests use a stub; the BUG-3502 vm harness injects `null`).
- **Driver loop.** Add `.loops/verify-enh-3507-served-page.yaml` following `.loops/verify-enh-3506-theme.yaml` (`preflight` → `probe` → marker-owned verdict, `skipped-no-playwright` is never a pass). The loop supplies `${context.run_dir}` for the JSON report and logs; bash `${...}` in its shell actions must be escaped `$${...}`.

### `createBuilderStorage`

Exported from `policy_builder_core.mjs`; `deps = {storage, connectedContext, warn}`.

- **Key formats (exact).** Offline: `ll-policy-builder-draft-<mode>`, `ll-policy-builder-meta` (unchanged). Connected: `ll-policy-builder-draft-<workspaceId>-<mode>`, `ll-policy-builder-meta-<workspaceId>`, `ll-policy-builder-issue-<workspaceId>` (issue selection — new surface, connected-only; offline the selection API is a no-op returning `null`). `workspaceId` is 16 lowercase hex and modes are fixed identifiers, so connected keys cannot collide with offline ones. Scenarios keep riding inside the draft record `{model, scenarios}`; there is no separate scenario key. Theme key `ll-policy-builder-theme` stays unscoped and stays in the template.
- Value shapes unchanged: draft `{model, scenarios}`; meta `{projectId, activeMode, schemaVersion, generatorVersion}`. Issue selection stores `{issueId}` only (never the absolute `path` from `GET issues`).
- **API (exact; FEAT-3505 builds on these names):** `persistDraft(mode, model, scenarios)`, `persistAllDrafts(drafts)`, `clearDraftsExcept(keepModes, allModes)`, `persistMeta(meta)`, `readDraft(mode)`, `readMeta()`, `readIssueSelection()`, `writeIssueSelection(issueId | null)` (`null` removes the key). The helper reads no ambient state: `_persistMeta` today closes over `projectId`, `state.mode`, `BUILDER_PROJECT_SCHEMA_VERSION`, and `window.__GENERATOR_VERSION__`, so the template builds the `MetaRecord` and passes it in; `ALL_MODES` stays a template constant (`.tmpl:390`) and is passed to `clearDraftsExcept`.
- **Storage acquisition must not throw at construction.** Today the bare `localStorage` reference sits *inside* each try/catch; evaluating it at module top level to build `deps` would throw `SecurityError` when storage is blocked (cookies disabled, some `file://` contexts) and kill the entire module script. The template resolves it guarded — `let _ls = null; try { _ls = window.localStorage; } catch (e) { /* blocked */ }` — and passes `storage: _ls`. The helper tolerates `storage == null`: reads return `null`, writes/removes are failures (so `persistDraft` still warns once).
- **Warning semantics (unchanged from today).** Every storage call stays try/catch. Only a `persistDraft` failure (including via `persistAllDrafts`) calls `warn`; `persistMeta`, `clearDraftsExcept`, `writeIssueSelection`, and all reads fail silently. `warn()` takes no arguments — the message text and `showLiveStatus` call stay in the template (`.tmpl:410-416`) — and the once-only latch (`_storageWarned` today) moves inside the helper, per instance.
- The issue-selection API has no template consumer in this issue (FEAT-3505's controller is the first caller); it is Node-tested here and is not dead code.
- The core must not reference `CONNECTED_CONTEXT`, `window`, or `localStorage` by bare name at module top level (Node dual loading); the template reads `CONNECTED_CONTEXT` as a bare identifier from the module script and passes it in. Keep `const CONNECTED_CONTEXT = /*__CONNECTED_CONTEXT_JSON__*/;` in its exact current form (regex-asserted by `test_feat3504_policy_builder_serve.py`).
- Add `createBuilderStorage` to the `window.PolicyBuilderCore` bridge (`policy_builder_core.mjs:3587`); verify the name does not collide with `.tmpl` glue declarations (shared module scope). Update the purity comments (`:1054`, `:1173`) to carve out DI factories: the module still touches no ambient globals; factories receive them injected.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs` — `createBuilderStorage`, bridge entry, purity-comment carve-out.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — replace inline storage (`:388-470`) with `createBuilderStorage` calls; `commit()`, `restoreFromSnapshot()`, `hydrateFromStorage`, and the Open-project path keep only the calls.
- `scripts/tests/js/policy_storage.test.mjs` (new) — auto-globbed by `scripts/tests/test_policy_builder_node_gate.py`.
- `scripts/tests/js/policy_validator.test.mjs` — BUG-3502 harness **will break**: `_extractBetween(_templateSrc, "let state = seedExample();", "function buildModel() {")` slices the region holding the storage functions. Inject `createBuilderStorage` (bound to the sandbox `localStorage` stub) and `CONNECTED_CONTEXT` into `_newBug3502Sandbox()`; keep or update the four marker strings (`let state = seedExample();`, `function buildModel() {`, `$("open-project-input").onchange = (e) => {`, `$("undo-btn").onclick = () => {`).
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate from `cmd_policy_builder()` output after verifying it (BUG-2303 advisory; no regeneration script exists).
- `.loops/probes/enh-3507-served-page-probes.mjs` (new, git-tracked like its siblings) — served-page probe skeleton.
- `.loops/verify-enh-3507-served-page.yaml` (new) — on-demand driver loop; reports land under `${context.run_dir}` (`.loops/runs/`, already gitignored), so no `.gitignore` change is needed.
- `scripts/little_loops/transport.py` — `flush=True` on the two URL `print()` calls in `serve_sse_bridge` (`:1586-1588`). Check `scripts/tests/` for a capsys/stdout assertion on these lines (`flush=True` does not change captured text).

### Tests

- `scripts/tests/test_policy_builder_emit.py` — `"/*__" not in html` must still hold.
- `.loops/probes/feat-3488-browser-probes.mjs` + `.loops/verify-feat-3488-browser-persistence.yaml` — hardcode the offline key names and value shapes; re-run after the rebind.
- `scripts/tests/test_feat3504_policy_builder_serve.py::TestPageRoute::test_serves_html_with_stamped_workspace_context` — unchanged declaration form keeps it green.

### Documentation

- `docs/guides/POLICY_ROUTER_GUIDE.md` persistence prose (`:318-335`, `:532-538`): one sentence that drafts on a served page are kept per project workspace. No key names; audience gate applies. Full connected-flow docs stay in FEAT-3505.

## Program Design

### Types

- `BuilderStorageDeps {storage, connectedContext, warn}` — injected `Storage`-like object or `null` (blocked storage), the stamped `{workspaceId}` or `null`, and a zero-argument once-per-instance warning callback.
- `BuilderStorageApi {persistDraft, persistAllDrafts, clearDraftsExcept, persistMeta, readDraft, readMeta, readIssueSelection, writeIssueSelection}` — the returned object; closes over `deps` only, never ambient template state.
- `DraftRecord {model, scenarios}` and `MetaRecord {projectId, activeMode, schemaVersion, generatorVersion}` — unchanged persisted shapes.
- `IssueSelection {issueId}` — new, connected-only.

### Signatures

- `createBuilderStorage(deps) -> storageApi` — exported from `policy_builder_core.mjs`; owns key derivation and guarded draft/meta/issue-selection reads and writes.

### Call Path

Page boot → the module script reads the stamped `CONNECTED_CONTEXT` (from `render_policy_builder_html`, `little_loops.cli.artifact.policy_builder`) → `createBuilderStorage` → `hydrateFromStorage` reads meta and per-mode drafts through it → `commit()` / `restoreFromSnapshot()` / Open-project persist through it. Offline pages are emitted by `cmd_policy_builder` with a `null` context.

## Implementation Steps

1. Add `flush=True` to the two URL prints in `serve_sse_bridge`. Add the probe skeleton and its driver loop (`ll-loop validate` it); run the `context` probe against current `main` (passes before any refactor — it only reads the stamped context; `connected-storage` reports blocked on `needs`).
2. Write `policy_storage.test.mjs` test-first: offline keys byte-identical; connected keys match the exact formats above; two `workspaceId`s are mutually invisible; no auto-migration of unscoped data; `warn` fires once per helper instance and only for `persistDraft` failures; a throwing `storage` never throws out of the helper; `storage: null` yields `null` reads, no throws, and one `warn` on `persistDraft`; `persistMeta` writes exactly the record it is given; `writeIssueSelection(null)` removes the key and offline selection is a no-op returning `null`.
3. Implement `createBuilderStorage`; rebind the `.tmpl` (guarded `localStorage` acquisition); fix the BUG-3502 harness in the same change.
4. Verify and regenerate the golden; run the Node gate and the pytest suite; re-run the FEAT-3488 offline probe and both probes of the new served-page loop (`connected-storage` must now pass); record results in verification notes.

## Acceptance Criteria

- [ ] Draft, scenario, meta, and issue-selection storage go through an exported `createBuilderStorage` in `policy_builder_core.mjs`, covered by the Node gate; the `.tmpl` contains no direct `localStorage` draft/meta access (theme key excepted).
- [ ] Offline keys and value shapes are byte-identical to today's; the FEAT-3488 browser probe passes unchanged after the rebind.
- [ ] Connected keys use the exact documented formats; a storage instance with a different `workspaceId` sees none of another workspace's drafts, meta, or issue selection. Unscoped data is not auto-migrated.
- [ ] `createBuilderStorage` returns exactly the documented API; the helper reads no ambient template state (meta record and mode list are passed in).
- [ ] Storage failures never throw into authoring — including blocked storage at acquisition time (`storage: null`), which must not abort the module script; the once-per-session warning still appears via the injected callback, for `persistDraft` failures only.
- [ ] On the served page, a committed edit writes only the workspace-namespaced draft and meta keys and no unscoped key (`connected-storage` probe).
- [ ] `ll-artifact serve` emits its URL lines immediately when stdout is piped (`flush=True`).
- [ ] The BUG-3502 vm harness passes with the injected helper; golden regenerated after verification; `python -m pytest scripts/tests/` and the Node gate are green.
- [ ] The served-page probe skeleton starts `ll-artifact serve --policy-builder` on an explicit non-default port, loads the printed builder URL over `http://127.0.0.1`, asserts the stamped `workspaceId` against an independently computed value, and cleans up the server on every exit path. It runs via `.loops/verify-enh-3507-served-page.yaml`, is not a pytest gate, and its result is recorded.

## Scope Boundaries

Includes the storage helper, `.tmpl` rebind, harness fix, golden, storage Node tests, probe skeleton with its driver loop, and the `flush=True` fix on `serve_sse_bridge`'s two URL prints (the sole server-side change — required for the probe to read the URL). Excludes the submission controller, `sha256Hex`, submission storage keys/index/retention, all connected UI, and the connected-flow guide section (FEAT-3505); every server route and every other `SseBridge` change (FEAT-3504).

## Impact

- Priority: P3 — prerequisite for FEAT-3505 in EPIC-3493.
- Effort: Small–Medium — one helper, one template rebind, one harness fix, one probe file.
- Risk: Low–Medium — behavior-neutral, but touches the persistence path every builder session uses; mitigated by byte-identical offline keys and the existing offline probe.

## Resolution

**Completed** 2026-09-18. `createBuilderStorage` added to `policy_builder_core.mjs` (bridge-exported); template rebound with guarded `localStorage` acquisition; `flush=True` on `serve_sse_bridge` URL prints; BUG-3502 harness updated; golden regenerated; `policy_storage.test.mjs` (8 tests) added; served-page probe + `verify-enh-3507-served-page` loop added (both probes pass; `context` and `connected-storage`). FEAT-3488 offline probe 20/20 pass; Node gate 194/194. Full pytest: only failure is pre-existing `test_verify_evidence::test_no_new_unverifiable_evidence` (BUG-3484 issue file span, unrelated).

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

**Re-verified 2026-09-18 (`--auto`)**: Verdict at time of check: **VALID** (no corrections needed, none applied). Re-confirmed by direct grep/read: `.tmpl:388-470` storage functions and `:192` stamp (sole `CONNECTED_CONTEXT` reference), `hydrateFromStorage()` call at `:2169`, Open-project path `:2088-2090`, `ALL_MODES` at `:390`; core bridge at `:3587` with no `createBuilderStorage`/`sha256Hex` yet; `transport.py:1586-1588` unflushed `print()` calls; `serve.py:58` `derive_workspace_id`, `:240` suffix; BUG-3502 markers at `policy_validator.test.mjs:1559-1568`; sibling probes/loops exist and no ENH-3507 probe/loop exists yet. `ll-verify-evidence`: 0 findings. Graph: provider=codegraph, freshness=stale (every result treated as a lead and confirmed by targeted grep).

## Review Notes (2026-09-18)

> Confidence scores in frontmatter predate this review — re-run `/ll:confidence-check`.

Pre-implementation review added: the piped-stdout flush fix (reproduced: 0 bytes reached a redirected stdout), guarded `localStorage` acquisition with `storage: null` tolerance, the `connected-storage` probe (only end-to-end check of the `.tmpl` → helper context wiring), the exact `BuilderStorageApi` method list, explicit warning semantics, the driver loop file, and probe robustness (explicit port, independently computed `workspaceId`, bare-identifier context read, `finally` cleanup). The `.gitignore:99` bullet was dropped: reports land under `.loops/runs/`, and `.loops/probes/*.mjs` are tracked on purpose.

---

## Session Log
- `/ll:manage-issue` - 2026-09-19T04:14:47 - `461c9ca9-f0fd-4b35-9f7d-706cd6ce0bcd.jsonl`
- `/ll:ready-issue` - 2026-09-19T04:01:22 - `7e1385fd-b723-4024-9361-79dd02488f00.jsonl`
- `/ll:confidence-check` - 2026-09-19T03:58:37 - `b9ead17c-f2ec-4fb1-95f7-273953b3a566.jsonl`
- `/ll:verify-issues` - 2026-09-19T03:54:21 - `5b384fe7-b058-43d2-b91f-71136e38e4c1.jsonl`
- manual pre-implementation review - 2026-09-18
- `/ll:confidence-check` - 2026-09-19T03:14:29 - `83bed03f-c4e2-4c5c-81ea-69c28840da72.jsonl`
- `/ll:verify-issues` - 2026-09-19T02:35:35 - `c21faf03-4a0d-488c-8584-9577fe7b87f5.jsonl`
- manual split from FEAT-3505 - 2026-09-19
