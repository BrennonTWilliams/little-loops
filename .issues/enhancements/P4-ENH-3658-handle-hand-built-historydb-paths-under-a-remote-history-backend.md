---
id: ENH-3658
type: ENH
title: Handle hand-built history.db paths under a remote history backend
priority: P4
status: open
blocked_by:
- ENH-3677
supersedes:
- ENH-3670
relates_to:
- ENH-3657
- ENH-3700
- ENH-3680
- ENH-3728
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:29:44Z'
decision_needed: false
reconcile_attempted: true
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3658: Handle hand-built history.db paths under a remote history backend

## Summary

Five Python call sites construct `<project>/.ll/history.db` directly and can mistake an opt-in remote history backend for a missing local database. Resolve the target against the **project root**, refuse snapshot-only operations cleanly, and give advisory views an explicit unavailable reason. Also remove the stale-shadow-DB hazard in `skills/update-docs/SKILL.md` and add a narrow regression gate. `context-monitor.sh` is cancelled-in-place (ENH-3680 cancelled 2026-10-02): remote writes are intentionally skipped, so it gets a permanent hazard-gate allowlist entry; its former detached-write plan is superseded.

## Current Behavior

- `cli/artifact/serve.py` builds the path in `make_history_route()` and `_make_page_html_factory()`. Under remote config, the route can serve an empty HTTP 200 snapshot and the page can show an empty history panel.
- The served client is `scripts/little_loops/templates/dashboard.llat/template.html.j2:refreshHistory` (currently lines 334–360). Any non-2xx throws a generic error, the catch sets an error status, and the polling interval continues; HTTP 501 currently needs an in-scope client edit.
- `cli/artifact/dashboard.py:cmd_dashboard()` reports a missing local file before its existing snapshot-export refusal can run.
- `cli/doctor_trim.py` builds the default path for `collect_trim_report()`, which `cli/doctor.py:main_doctor()` calls for `--trim`; remote telemetry reads as absent. The guard belongs in `main_doctor`, not in the local-only report helper.
- `cli/loop/run.py:cmd_run` constructs the path for its `--serve` dashboard render; a remote store can appear empty or a propagated refusal can abort serve startup.
- `skills/update-docs/SKILL.md` checks `Path('.ll/history.db').exists()`, so remote users fall back silently or read a stale shadow file. `workflow_sequence/io.py` receives a caller-supplied path and already falls back to JSONL correctly; it needs no change. The hand-built `cli/logs.py` reader sites belong to ENH-3657.

## Expected Behavior

Classify each default-shaped path with `resolve_history_store(path, root=project_root)` before filesystem checks. Use the **returned local Path**, not the original hand-built path, for local and `LL_HISTORY_DB` overrides. Under a `RemoteTarget`:

| Site | Outcome |
|---|---|
| `cmd_dashboard` without `--db` | Refuse snapshot export with exit 1 naming `libsql`, not "history database not found". Explicit `--db` remains local. |
| `make_history_route` | Return HTTP 501 with a JSON reason naming the provider; do not `stat()` a nonexistent local DB or return empty HTTP 200. |
| `_make_page_html_factory` and `cmd_run --serve` | Skip the history panel with the same stated reason; continue serving. |
| `main_doctor --trim` | Show an informational unsupported result (text and JSON), keep `ll-doctor`'s advisory exit code, and do not call `collect_trim_report`. |
| `skills/update-docs` | Use an explicit filesystem-scan fallback or a target-aware CLI; never consult a stale shadow DB. |

Keep one shared safe reason for route/page responses: `History snapshots are not supported with a remote libsql backend.` HTTP 501 returns `{"verdict":"unsupported","reason":"<shared reason>"}`. In `refreshHistory`, handle 501 separately, parse its reason, render it with `textContent`, and clear the stored polling interval. Treat it as an unavailable panel state, with no error toast. Network errors and 5xx retain retry behavior. The initial remote page skips snapshot loading entirely. Local-missing behavior and explicit local overrides remain unchanged. `skills/update-docs` stays DB-first for an actual local history file and uses the documented file scan only for a remote target or truly missing local file.

Handle 501 **before** a generic 5xx/error branch; it is itself a 5xx. The retryable-5xx promise excludes this explicit unsupported verdict. Plant the rendered-client test so a generic retry branch would cause another fetch and fail it.

## Motivation

A remote backend should not look like an empty local database. These paths bypass the normal target resolver and make wrong but plausible output, making the failure harder to spot than a traceback.

## Proposed Solution

1. At each of the five Python call sites, resolve the default path using the owning project's root. Branch on `RemoteTarget` before `is_file()`, `stat()`, or snapshot export. For `cmd_dashboard`, keep the existing `snapshot_export` refusal operation; no new `_REMOTE_REFUSALS` or `_REJECTED` entry is needed.
2. Guard `--trim` in `main_doctor` using its existing `_remote_target()` pattern. For a local target, pass the resolver's returned Path to the existing `collect_trim_report(..., db_path=...)` parameter; otherwise a redirected `LL_HISTORY_DB` would still be ignored. Leave `doctor_trim.py` local-only. Add one shared unavailable-reason value consumed by the serve route, page factory, and loop `--serve` render.
3. Replace the `skills/update-docs` literal-path existence check with target-aware behavior. Add a pytest hazard gate over `skills/`, `commands/`, `loops/*.yaml`, and `hooks/` for executable `history.db` existence tests and `resolve_history_db()` calls, with reasoned allowlist entries. This issue is no longer `blocked_by` ENH-3657/ENH-3700 (2026-10-02 Opus review): it never edits `session_store/backend.py`, and its five Python sites classify with `resolve_history_store`, not the central guard. CT-0 (`skills/improve-claude-md/SKILL.md` ~L206-209) calls `resolve_history_db()` directly, so the gate flags it until ENH-3728 switches it to `resolve_history_store`: add a **temporary** allowlist entry for CT-0 that ENH-3728's PR removes. Add a **permanent** allowlist entry for `context-monitor.sh` with the reason "remote writes intentionally skipped (ENH-3680 cancelled)". Do not flag the bare string in prose.
4. Add remote-stub tests and local twins, then update the remote-history support docs with end-user wording.

The CT-0 exemption is conditional on a **still-present** executable hazard, not on an assumed merge order. If ENH-3728 landed first, never introduce it. Add a stale-exemption check requiring each scoped allowlist entry to match its actual current hazard; when CT-0 changes, the gate must pass without its entry. This preserves independent eligibility and does not add a dependency edge.

### Preserve explicit snapshot-target intent through export

`cmd_dashboard --db` is an explicit local override even when it names `.ll/history.db` (relative or absolute). Record this intent as `LocalTarget`, keeping a separate local Path for filesystem operations. `session_store.queries.build_snapshot_db` currently calls `refuse_on_remote(db, "snapshot_export")` and then `Path(db)`: passing the plain default-shaped Path downstream would reclassify the explicit local override as remote. Extend this snapshot-only seam to accept `Path | LocalTarget`, refuse before unwrapping, and carry the already-classified local target through `build_dashboard_html` / `build_history_payload` to that seam. Do not change the remote refusal or `_resolve_once` contract, and do not broaden the history-reader package's signatures in this issue. Test both default-shaped `--db` forms and a non-default file under remote config with real snapshot content.

Carry `LocalTarget` for **every already-classified local result**, including default local-project paths and env/config redirections in serve/page/loop routes. Otherwise a local owning root served from a foreign remote cwd can be reclassified by the snapshot refusal seam even without `--db`. Keep the returned Path for stat/ETag/file work, and the typed local target for export. Direct unclassified payload-builder callers retain their existing remote refusal. Tests cover both foreign-cwd directions through actual snapshot content, not just the initial resolver.

### Render an unavailable history panel without doing snapshot work

The remote page needs a renderer path, not only a precheck at its caller: add an optional safe unavailable reason to `ServeContext`, skip `build_history_payload` and history SQL initialization/polling in that branch, and populate the template's required data keys in every branch (`StrictUndefined`). Render the notice through the existing escaping rules and preserve SSE/interaction regions. An explicit 501 received by an already-running client sets an unavailable flag, cancels its interval and returns before gunzip/instantiate; later queued ticks must check the flag before fetching. Local snapshots and retryable failures keep their existing behavior.

## Scope Boundaries

- **In scope:** the five Python call sites, renderer unavailable branch/501 client, snapshot-local provenance through export, the `main_doctor` guard and existing `db_path=` override, `skills/update-docs` and mirrors, the narrow hazard gate, tests and user-facing docs.
- **Out of scope:** `context-monitor.sh` behavior (ENH-3680, cancelled: remote writes stay skipped); `cli/logs.py` readers (ENH-3657) and CT-0 behavior (ENH-3728); `workflow_sequence/io.py` (correct JSONL fallback); `doctor_trim.py` internals; remote snapshot export itself.

## Behavior Parity

For local SQLite, a present `history.db` still drives all five Python views and `skills/update-docs` remains DB-first. A truly missing local file still follows each existing missing-file path. Explicit `--db` where supported and `LL_HISTORY_DB` continue to use the resolved local file; only a configured remote target changes the verdict.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/artifact/serve.py` (`make_history_route`, `_make_page_html_factory`), `scripts/little_loops/templates/dashboard.llat/template.html.j2` (`refreshHistory`, polling interval handle, unavailable status), `cli/artifact/dashboard.py`, `cli/doctor.py`, `cli/loop/run.py` (`cmd_run --serve` dashboard render; locate by function, not the old `:691` anchor).
- `cli/artifact/dashboard.py` owns the shared serve/dashboard reason or `ServeContext` field. `session_store/queries.py` owns `build_snapshot_db` local-target provenance. Also modify `skills/update-docs/SKILL.md` and regenerated `.gemini/`, `.kimi-code/`, `.qwen/` mirrors (`ll-adapt --host <gemini|kimi-code|qwen> --apply`), one pytest hazard-gate test, and remote/local tests in `test_feat3323_sse_bridge.py`, `test_feat3304_artifact_dashboard.py`, `test_remote_doctor.py` / `test_cli_doctor_trim.py`, plus a `cmd_run --serve` render test.
- `docs/reference/CONFIGURATION.md` and `docs/reference/CLI.md`; pin new user-facing strings in `test_wiring_reference_docs.py` and keep `test_docs_audience_gate.py` green. Add/update this slice's rows in the single support table even if ENH-3657 has not landed; integrate rows without replacing siblings' entries. No generated `site/` copies are edited directly.

### Dependent Files and Similar Patterns

- `session_store/db.py:resolve_history_store` returns a local `Path` or `RemoteTarget`; its `root=` argument prevents a foreign cwd from selecting the wrong project. `cli/doctor.py:_remote_target()` already shapes advisory remote results.
- `workflow_sequence/io.py` and `doctor_trim.py` remain unchanged. ENH-3657 may edit the same remote-operation test file; merge independent assertions rather than replacing its rows.

## Program Design

### Types

- `HistoryTarget = LocalTarget | RemoteTarget`; a shared `history_unavailable_reason` (or equivalent) feeds `ServeContext` and the route response.

### Signatures

- `resolve_history_store(path: Path | str | HistoryTarget | None = None, *, root: Path | None = None) -> Path | RemoteTarget` — classify defaults against the owning project; typed `LocalTarget` preserves explicit intent.
- `build_snapshot_db(db: Path | LocalTarget, dest: Path, ...)` — preserve snapshot-local provenance through the refusal precheck, then unwrap for the unchanged local SQL opener.
- `build_dashboard_html(..., db_path: Path, db_target: LocalTarget | None = None)` / `build_history_payload(..., db_path: Path, db_target: LocalTarget | None = None)` — optional already-classified provenance passed through to snapshot export; filesystem work still uses the Path. Existing direct callers retain their default refusal behavior.
- `make_history_route(config: BRConfig) -> Callable[..., None]` — performs the remote precheck before ETag/stat work. `main_doctor()` owns the `--trim` guard.

### Call Path

- `cmd_serve` → route/page factory → root-aware target resolution → remote HTTP 501 or panel notice; local returned Path → existing payload builder.
- `cmd_dashboard` → target resolution → existing `snapshot_export` refusal on remote or existing local render on returned Path.
- `main_doctor --trim` → `_remote_target()` → informational skip on remote or `collect_trim_report()` on local.
- `cmd_run --serve` → root-aware target resolution → panel notice on remote or render from returned Path on local.
- An explicit `--db` exists for `cmd_dashboard`; `serve` and `cmd_run --serve` do not gain one. `LL_HISTORY_DB` and applicable `db_path=` overrides resolve locally. No advisory path raises through the CLI boundary.

## Implementation Steps

1. Land ENH-3677's shared `remote` test fixture, then implement the Python target checks and one shared unavailable reason. ENH-3657/ENH-3700 may edit the same remote-operation test file: merge independent assertions rather than replacing rows. ENH-3698 and ENH-3679 are already done; preserve their landed `cli/doctor.py` / `CLI.md` install-surface check behavior rather than scheduling them as pending work.
2. Implement the named `refreshHistory` 501 branch and polling cancellation. Update `skills/update-docs` and add the narrow hazard gate with a **temporary** CT-0 allowlist entry only while ENH-3728's CT-0 change remains pending (its PR removes the entry), and a **permanent** `context-monitor.sh` entry (reason: remote writes intentionally skipped). Scan packaged built-in loops under `scripts/little_loops/loops/` as well as repository `loops/` and `.loops/` executable artifacts.
3. Add a remote stub plus local twin for each changed path, including a foreign-cwd/project-root case and `LL_HISTORY_DB` redirection. Confirm the existing local missing-file behavior.
4. Update documentation and run `python -m pytest scripts/tests/`, `ruff check scripts/`, and `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote-backend paths currently give misleading output.
- **Effort:** Medium — five call sites, one skill check, a hazard gate, tests and docs.
- **Risk:** Medium — routing the wrong project root or dropping an explicit local override would change behavior.
- **Breaking Change:** No for local users.

## Acceptance Criteria

- [ ] Every listed Python site classifies with the owning project root. Both foreign-cwd directions preserve the verdict through actual rendering/export; every classified local result carries local intent to the snapshot seam, and `LL_HISTORY_DB` uses the resolver's returned Path.
- [ ] Remote `cmd_dashboard` exits 1 with a snapshot-export refusal; local-missing and explicit `--db` behavior remain unchanged, including relative/absolute default-shaped local overrides through the actual `build_snapshot_db` refusal seam.
- [ ] Remote `make_history_route` returns the specified HTTP 501 JSON before local `stat()`; initial remote pages skip snapshots and show the shared reason. `refreshHistory` in the dashboard template renders the 501 reason with `textContent` and stops polling without an error toast; network/5xx failures still retry. Cover safe rendering with an HTML-like canary reason and verify a second polling tick makes no 501 request.
- [ ] Remote `ll-doctor --trim` has an informational text/JSON result, no traceback, and the same advisory exit code as a run without `--trim`. A local/env override is supplied through `collect_trim_report(db_path=...)` and its real usage rows are observed.
- [ ] The remote page/loop render never calls `build_history_payload` or initializes/polls a history snapshot; SSE and interactions remain functional. Execute the rendered client's 501/timer behavior in a pytest-wrapped JavaScript test (skip gracefully if the runtime is absent), rather than checking strings or a copied implementation alone.
- [ ] A real history-route 501 is followed by a successful page/SSE request on the same server; the unavailable snapshot cannot terminate the server or disable its other routes. The notice is fixed safe text and remote classification never consults a stale local shadow snapshot.
- [ ] `skills/update-docs` stays DB-first for a real local history file, takes the explicit scan fallback for a remote target or missing local file, and never reads a stale shadow DB; source and regenerated skill mirrors agree. The narrow hazard gate passes with documented allowlist entries, temporary CT-0 only while needed and permanent context-monitor only for its intentional remote no-op.
- [ ] The hazard gate rejects stale scoped exemptions; either ENH-3658/3728 landing order ends with no CT-0 exemption after its hazard is removed. The client handles 501 before retryable 5xx logic and its next queued tick makes no fetch.
- [ ] Remote-stub and local-twin tests cover every changed site; `python -m pytest scripts/tests/` passes.

## Related

- BUG-3652 (done startup/write caller audit), FEAT-3535 (remote libSQL backend), ENH-3677 (shared fixture prerequisite), ENH-3657/ENH-3700 (reader-CLI siblings; no longer `blocked_by`; ENH-3728 removes the temporary CT-0 allowlist entry), ENH-3680 (cancelled 2026-10-02: `context-monitor.sh` stays a documented remote no-op). ENH-3670 is cancelled and superseded by this issue.

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` (Remote history backend), `docs/reference/CLI.md` (`ll-artifact dashboard`, `ll-doctor --trim`).

## Status

**Open** | Created: 2026-09-29 | Priority: P4

## Confidence Check Notes

_Updated 2026-10-02 after the EPIC-3693 pre-implementation review._

Prior 85/75 scores were cleared because the revised client/hazard-gate scope changed. The client question is resolved: the named dashboard template requires a safe 501 branch and polling cancellation. Implementation remains blocked by ENH-3677. Re-run `/ll:confidence-check` after that fixture lands; do not reuse the old aggregate as approval. Preserve the already-landed ENH-3679/3698 doctor behavior at integration.

## Session Log
- EPIC-3693 review #6 + `/ll:advise` (opus, user_requested, confidence 0.62) - 2026-10-06 - conditional CT-0 allowlisting now has an executable stale-exemption gate; rendered client explicitly handles 501 before generic 5xx retry. Existing independent eligibility and snapshot scope retained; implementation not performed.
- EPIC-3693 review #3 - 2026-10-05 - existing target/provenance/renderer scope retained, file ownership clarified and same-server usability after 501 made explicit; implementation not performed
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - explicit snapshot provenance, renderer skip path, trim override and mirror/test wiring amended; implementation not performed
- `/ll:confidence-check` - 2026-09-30T05:10:36 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
- `/ll:confidence-check` - 2026-09-29T22:09:10 - `c419efbf-94bc-4735-80cf-772ead8ae35e.jsonl`
- `/ll:verify-issues` - 2026-09-29T22:05:35 - `b6e9a962-45bc-4981-a31d-f5f911dc70c3.jsonl`
- `/ll:verify-issues` - 2026-09-29T21:59:39 - `f8adf1da-5f55-4437-ac1b-3cda2eb8384a.jsonl`
- `/ll:confidence-check` - 2026-09-29T15:35:24 - `4e126c30-e610-4bf7-836c-7acf607ff2dd.jsonl`
- `/ll:advise` - 2026-09-29 - Opus consult (user_requested); amendments applied
- `/ll:refine-issue` - 2026-09-29T06:53:44 - `ba092082-4ae3-43dd-9062-e948c741ef8f.jsonl`
- `/ll:decide-issue` - 2026-09-29T06:52:11 - `b6e8b863-de04-439b-86a0-163f69ae4ae5.jsonl`
- `/ll:confidence-check` - 2026-09-29T06:37:24 - `8bc00e90-4fb4-4186-b015-6ae8b54ba73f.jsonl`
- `/ll:verify-issues` - 2026-09-29T06:35:53 - `8072da21-2d78-4f2f-ada0-f03b231f5125.jsonl`
- `/ll:reconcile-issue` - 2026-09-29T06:34:15 - `877ea6e8-6250-465b-b992-d2e8d8b06ce5.jsonl`
- `/ll:verify-issues` - 2026-09-29T06:33:17 - `ff97b32f-aa84-46a2-9a7d-af053e342cd2.jsonl`
- `/ll:wire-issue` - 2026-09-29T06:31:23 - `7b6ba26a-d87e-4453-a694-b6e659ef24db.jsonl`
- `/ll:decide-issue` - 2026-09-29T06:23:36 - `bbc97752-9916-4650-a701-f5939b2c2ee3.jsonl`
- `/ll:refine-issue` - 2026-09-29T06:21:46 - `37d0b17a-7e47-4ff9-92ea-b1a095fee341.jsonl`
