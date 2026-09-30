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
- ENH-3680
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:29:44Z'
decision_needed: false
reconcile_attempted: true
---

# ENH-3658: Handle hand-built history.db paths under a remote history backend

## Summary

Five Python call sites construct `<project>/.ll/history.db` directly and can mistake an opt-in remote history backend for a missing local database. Resolve the target against the **project root**, refuse snapshot-only operations cleanly, and give advisory views an explicit unavailable reason. Also remove the stale-shadow-DB hazard in `skills/update-docs/SKILL.md` and add a narrow regression gate. `context-monitor.sh` is owned entirely by ENH-3680; its former detached-write plan is superseded.

## Current Behavior

- `cli/artifact/serve.py` builds the path in `make_history_route()` and `_make_page_html_factory()`. Under remote config, the route can serve an empty HTTP 200 snapshot and the page can show an empty history panel.
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

Keep one shared end-user reason string for route/page responses. Local-missing behavior and explicit local overrides remain unchanged. `skills/update-docs` stays DB-first for an actual local history file and uses the documented file scan only for a remote target or truly missing local file.

## Motivation

A remote backend should not look like an empty local database. These paths bypass the normal target resolver and make wrong but plausible output, making the failure harder to spot than a traceback.

## Proposed Solution

1. At each of the five Python call sites, resolve the default path using the owning project's root. Branch on `RemoteTarget` before `is_file()`, `stat()`, or snapshot export. For `cmd_dashboard`, keep the existing `snapshot_export` refusal operation; no new `_REMOTE_REFUSALS` or `_REJECTED` entry is needed.
2. Guard `--trim` in `main_doctor` using its existing `_remote_target()` pattern. Leave `collect_trim_report` / `doctor_trim.py` local-only. Add one shared unavailable-reason value consumed by the serve route, page factory, and loop `--serve` render.
3. Replace the `skills/update-docs` literal-path existence check with target-aware behavior. Add a pytest hazard gate over `skills/`, `commands/`, `loops/*.yaml`, and `hooks/` for executable `history.db` existence tests and `resolve_history_db()` calls, with reasoned allowlist entries. Allowlist ENH-3657's CT-0 site until that issue lands and `context-monitor.sh` until ENH-3680 lands; do not flag the bare string in prose.
4. Add remote-stub tests and local twins, then update the remote-history support docs with end-user wording.

## Scope Boundaries

- **In scope:** the five Python call sites, the `main_doctor` guard, `skills/update-docs`, the narrow hazard gate, tests and user-facing docs.
- **Out of scope:** `context-monitor.sh` (ENH-3680); `cli/logs.py` readers and CT-0 behavior (ENH-3657); `workflow_sequence/io.py` (correct JSONL fallback); `doctor_trim.py` internals; remote snapshot export itself.

## Behavior Parity

For local SQLite, a present `history.db` still drives all five Python views and `skills/update-docs` remains DB-first. A truly missing local file still follows each existing missing-file path. Explicit `--db` where supported and `LL_HISTORY_DB` continue to use the resolved local file; only a configured remote target changes the verdict.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/artifact/serve.py` (`make_history_route`, `_make_page_html_factory`), `cli/artifact/dashboard.py`, `cli/doctor.py`, `cli/loop/run.py` (`cmd_run --serve` dashboard render; locate by function, not the old `:691` anchor).
- The shared serve/dashboard reason constant or `ServeContext` field, `skills/update-docs/SKILL.md`, one pytest hazard-gate test, and remote/local tests in `test_feat3323_sse_bridge.py`, `test_feat3304_artifact_dashboard.py`, `test_remote_doctor.py` / `test_cli_doctor_trim.py`, plus a `cmd_run --serve` render test.
- `docs/reference/CONFIGURATION.md` and `docs/reference/CLI.md`; pin new user-facing strings in `test_wiring_reference_docs.py` and keep `test_docs_audience_gate.py` green. No generated `site/` copies are edited directly.

### Dependent Files and Similar Patterns

- `session_store/db.py:resolve_history_store` returns a local `Path` or `RemoteTarget`; its `root=` argument prevents a foreign cwd from selecting the wrong project. `cli/doctor.py:_remote_target()` already shapes advisory remote results.
- `workflow_sequence/io.py` and `doctor_trim.py` remain unchanged. ENH-3657 may edit the same remote-operation test file; merge independent assertions rather than replacing its rows.

## Program Design

### Types

- `HistoryTarget = LocalTarget | RemoteTarget`; a shared `history_unavailable_reason` (or equivalent) feeds `ServeContext` and the route response.

### Signatures

- `resolve_history_store(path: Path | str, *, root: Path) -> Path | RemoteTarget` — classifies against the owning project.
- `make_history_route(config: BRConfig) -> Callable[..., None]` — performs the remote precheck before ETag/stat work. `main_doctor()` owns the `--trim` guard.

### Call Path

- `cmd_serve` → route/page factory → root-aware target resolution → remote HTTP 501 or panel notice; local returned Path → existing payload builder.
- `cmd_dashboard` → target resolution → existing `snapshot_export` refusal on remote or existing local render on returned Path.
- `main_doctor --trim` → `_remote_target()` → informational skip on remote or `collect_trim_report()` on local.
- `cmd_run --serve` → root-aware target resolution → panel notice on remote or render from returned Path on local.
- An explicit `--db` exists for `cmd_dashboard`; `serve` and `cmd_run --serve` do not gain one. `LL_HISTORY_DB` and applicable `db_path=` overrides resolve locally. No advisory path raises through the CLI boundary.

## Implementation Steps

1. Land ENH-3677's shared `remote` test fixture, then implement the Python target checks and one shared unavailable reason.
2. Update `skills/update-docs` and add the narrow hazard gate with temporary allowlist entries for work owned by ENH-3657/3680.
3. Add a remote stub plus local twin for each changed path, including a foreign-cwd/project-root case and `LL_HISTORY_DB` redirection. Confirm the existing local missing-file behavior.
4. Update documentation and run `python -m pytest scripts/tests/`, `ruff check scripts/`, and `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote-backend paths currently give misleading output.
- **Effort:** Medium — five call sites, one skill check, a hazard gate, tests and docs.
- **Risk:** Medium — routing the wrong project root or dropping an explicit local override would change behavior.
- **Breaking Change:** No for local users.

## Acceptance Criteria

- [ ] Every listed Python site classifies with the owning project root. A foreign cwd does not change the verdict; `LL_HISTORY_DB` uses the resolver's returned local Path.
- [ ] Remote `cmd_dashboard` exits 1 with a snapshot-export refusal; local-missing and explicit `--db` behavior remain unchanged.
- [ ] Remote `make_history_route` returns HTTP 501 JSON without local `stat()` or an empty HTTP 200; the page factory and `cmd_run --serve` display the same reason without aborting.
- [ ] Remote `ll-doctor --trim` has an informational text/JSON result, no traceback, and the same advisory exit code as a run without `--trim`.
- [ ] `skills/update-docs` stays DB-first for a real local history file, takes the explicit scan fallback for a remote target or missing local file, and never reads a stale shadow DB; the narrow hazard gate passes with documented temporary allowlist entries.
- [ ] Remote-stub and local-twin tests cover every changed site; `python -m pytest scripts/tests/` passes.

## Related

- BUG-3652 (done startup/write caller audit), FEAT-3535 (remote libSQL backend), ENH-3677 (shared fixture prerequisite), ENH-3657 (reader-CLI sibling), ENH-3680 (`context-monitor.sh` spool, separate scope). ENH-3670 is cancelled and superseded by this issue.

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` (Remote history backend), `docs/reference/CLI.md` (`ll-artifact dashboard`, `ll-doctor --trim`).

## Status

**Open** | Created: 2026-09-29 | Priority: P4

## Session Log
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
