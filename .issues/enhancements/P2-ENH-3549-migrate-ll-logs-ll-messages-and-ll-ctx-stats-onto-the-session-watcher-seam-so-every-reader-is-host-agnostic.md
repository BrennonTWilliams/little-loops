---
id: ENH-3549
title: Finish session-reader isolation and consume stored usage in ll-ctx-stats
type: ENH
priority: P2
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-24'
labels:
- observability
- multi-host
depends_on:
- ENH-3532
- ENH-3534
confidence_score: 65
outcome_confidence: 52
unproven_mechanism: true
spike_attempted: true
spike_completed: true
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
---

# ENH-3549: Finish session-reader isolation and consume stored usage in ll-ctx-stats

## Summary

Finish the remaining read-side isolation and diagnostics after ENH-3428/3429/3430 migrated discovery in `ll-messages`, `ll-ctx-stats`, and `ll-logs`. The existing seam is `detect_sessions`/`iter_events`; there is no new watcher lifecycle to build. Remove the remaining cache-accounting transcript bypass by reading stored normalized observations through `select_usage_observations`, preserve workspace/session selection, add named-cause diagnostics, and prove the reader boundary with divergent fake hosts.

The existing Codex parser/captures and the read-side spike are evidence to reuse. This issue does not redo discovery migration, add a new Codex parser, or define another token normalizer.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Discovery migration already landed.** `cli/logs.py`, `cli/messages.py` and `cli/ctx_stats.py` contain no `.claude/projects` literal and make no calls into the legacy project-folder helpers; they already route through `detect_sessions`/`iter_events` (ENH-3428/3429/3430). The direct joins remain in `user_messages._get_claude_project_folder`, `sessions._list_claude_workspaces`, `sessions._explain_encoded_dir_host`, and `writers.host_layout_for` (write-side).
- **No `SessionWatcher` symbol exists in code.** "Session-watcher seam" is the session-discovery seam (`SessionHandle`, `detect_sessions`, `iter_events`) in `session_store/sessions.py`.
- **Ownership:** ENH-3419 and its reader-migration children are done. ENH-3546 owns Claude producer eligibility; ENH-3534 owns the other remaining hosts. This issue consumes stored provenance and does not certify producers.
- **Read-side divergent-fake gap confirmed:** the fakes (`FakeHostRunner`, `FakeMinimalHostRunner`) have no session-log discovery or parser; `_PARSERS`/`_REGISTERED_HOSTS` hold only the eight real hosts. The spike below supplies fixture registration at the seam layer; actual reader-consumer integration remains outstanding.

## Current Behavior

The three CLIs already discover sessions through `detect_sessions` and read events through `iter_events` (or handle-taking extractors in `little_loops.user_messages`); ENH-3428/3429/3430 landed that. The remaining gaps are:

- `little_loops.user_messages._get_claude_project_folder` and `little_loops.session_store.sessions._list_claude_workspaces` still join `~/.claude/projects` themselves, and `detect_sessions` reaches the former.
- `ll-ctx-stats` (`_compute_cache_rate_from_jsonl`) reads Codex through `iter_events` but keeps a raw `open(handle.path)` reader for every other host, and labels non-Codex cache figures `provenance: "unknown"`.
- `ll-ctx-stats` has no named-cause warning when no sessions are found (`explain_no_sessions` is not called).
- The production composition suite (`tests/conformance/test_host_composition.py`) exercises the write/executor side. The separate spike now supplies read-side fake records and proves seam injection, but actual reader-consumer coverage and the transcript-root isolation gate remain outstanding.

## Expected Behavior

Session discovery and message/log parsing stay behind `detect_sessions`/`iter_events`. Cache-rate accounting uses persisted normalized `usage_events` through `select_usage_observations`, preserving the existing latest-session/workspace/host selection (including agent exclusion) instead of summing the entire database. Producer eligibility stays with ENH-3532/3534/3546 and reconciliation stays with ENH-3543.

For a discovered session without stored eligible usage, return unavailable with a diagnostic explaining missing/not-yet-ingested usage; do not silently parse raw transcripts or backfill during a read-only report. Missing fields are unknown/unavailable, and estimates exist only when an actual estimator supplies them. An unreadable store and genuine absence remain distinguishable. Empty discovery emits `explain_no_sessions` diagnostics to stderr so JSON stdout remains valid.

## Design constraints

- The discovery seam owns discovery and per-host event parsing. Do not add a common tool-call or token-accounting abstraction to that seam. The existing downstream normalized usage store and selector remain the accounting contract consumed by reports.
- Discovery failure and genuine absence must remain distinguishable after the migration. A workspace whose sessions exist on disk but match nothing renders a named-cause warning, not an empty result; the migration must not regress that behavior where it exists today.
- The Codex parser is tested against a captured real-shape rollout fixture, treated as perishable — vendor shape drift is one re-capture away from detection. The fixture complements, not replaces, the scripted fake hosts.

## Acceptance Criteria

- [ ] Divergent fake fixtures pass through the actual message/log readers and stored-usage cache-rate consumer, not only discovery/parser helpers. Reuse the spike injection surface and close the `extract_user_messages` host-gate gap identified by the spike.
- [ ] Existing Codex/Claude workspace readback and agent/session selection stay equivalent; reuse captured Codex fixtures rather than creating another parser.
- [ ] Cache-rate reporting uses stored normalized observations via `select_usage_observations`, preserving producer provenance and coverage qualification; no host-wide unknown override or direct transcript accounting remains.
- [ ] Missing/partial usage, no stored rows, unreadable store and empty discovery have conservative, distinguishable behavior. No usage is labeled estimated without an estimator, and report reads do not mutate ingestion state.
- [ ] A mechanical AST/path-join gate catches direct reader access to host transcript roots, with narrowly justified seam/layout allowlist entries, a stale-entry test and a stray-site self-check.
- [ ] Named-cause diagnostics go to stderr and JSON stdout remains parseable. Unit-level fixture tests run without installed host CLIs; project tests pass.

## Scope Boundaries

- **In scope**: remaining reader bypass classification/removal, stored-usage cache-rate integration, empty-discovery/store diagnostics, read-side composition tests, and a mechanical host-layout isolation gate.
- **Out of scope**: redoing completed discovery migration, replacing the Codex parser, a new watcher service, common tool-call shapes, token normalization/producer promotion, live/rollout reconciliation, dataset export or quality rollup redesign.
- **Accounting boundary**: ENH-3532/3534 persist normalized observations; ENH-3546 qualifies Claude provenance; ENH-3543 enhances the existing `select_usage_observations` policy. This issue consumes that entry point with conservative behavior before reconciliation exists.
- **Dependencies**: ENH-3532/3534 remain dependencies for complete stored host coverage. Diagnostics/gate/spike promotion can proceed independently. No reader-local normalization or UUID-based usage deduplication replaces producer identity contracts.

## Impact

- **Priority**: P2 — closes the remaining raw accounting bypass and strengthens multi-host reader regression coverage.
- **Effort**: Medium — existing discovery/parsers are reused; stored-usage selection and consumer-level fake integration remain substantive.
- **Risk**: Medium — latest-session selection, missing-store behavior, provenance and consumer dispatch must remain consistent.
- **Breaking Change**: No command-line interface change; missing un-ingested usage is explicitly unavailable rather than silently parsed from disk.

## Program Design

### Types

- Reuse `SessionHandle`, `SessionEvent`, and `NoSessionsCause` from `session_store`; no watcher type is introduced.
- Reuse the stored observation/provenance contract and existing selection entry point. No common tool-call representation or new token-accounting type is needed in the discovery seam.

### Signatures

- Keep existing `detect_sessions`, `iter_events`, and `explain_no_sessions` signatures.
- `_compute_cache_rate_from_usage(cwd: Path, host: str | None, *, db: Path | str | None = None) -> dict | None` — proposed stored-observation consumer. Preserve existing numeric keys and add qualification from stored observations. Retire the misleading private `_compute_cache_rate_from_jsonl` helper and update its callers/tests; any temporary compatibility wrapper delegates to the stored consumer, never parses transcripts.
- Record the existing latest-session selection and missing-store/no-eligible-rows diagnostic contract in focused tests before replacing the helper.

### Call Path

- `main_messages` / `main_logs` → `detect_sessions` → `iter_events` / handle-taking extractors.
- `main_ctx_stats` → selected `SessionHandle` → read-only history connection → `select_usage_observations` → selected session's cache components and provenance.
- Empty discovery → `explain_no_sessions` → stderr; missing/unreadable stored usage → distinct stderr diagnostic and unavailable cache result.

### Decision Rules

Preserve latest eligible session and host/workspace scope, and exclude agent records as before. Do not widen to all-session totals, infer zeros, perform an implicit backfill, or fall back to a separate raw token parser. Usage deduplication belongs to persisted identity/coverage policy, not a reader-local UUID filter.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/ctx_stats.py` — replace raw cache-accounting helper with stored observation selection; preserve selection/return semantics, propagate provenance, and emit diagnostics outside the numeric helper.
- `scripts/little_loops/history_reader/usage.py`, `token_provenance.py` — reuse existing selection/qualification APIs; modify only if narrow support is required, without adding a bypass.
- `scripts/little_loops/user_messages.py` — close the fake-host extraction gate found by the spike using an explicit per-host consumer dispatch/fixture adapter; preserve real-host output and keep tool/token semantics out of discovery.
- `scripts/little_loops/cli/logs.py`, `cli/messages.py` — classify remaining raw opens as transcript or non-transcript; route only genuine transcript bypasses through the seam. They already use discovery and named-cause diagnostics.
- `scripts/little_loops/session_store/sessions.py`, `writers.py` — existing host-layout resolvers are legitimate seam internals. Do not relocate them solely to satisfy the gate.
- `scripts/tests/conformance/test_host_composition.py` and/or a neighboring read-side test module — promote the existing spike's injection mechanism, then test actual consumers. Fixture-only unit coverage must run without host binaries.
- `scripts/tests/test_session_reader_no_claude_projects_gate.py` — NEW: AST path-join/string scan with narrowly justified function-level exceptions where practical, stale-entry and stray-site tests. Scan all host transcript roots; exclude config/output directories and lint-tool examples with reasons.

### Tests and Compatibility

- Preserve `test_session_discovery.py`, `test_user_messages.py`, `test_ll_logs.py`, `test_cli_messages.py` and real-host parser regressions.
- Update `test_cli_ctx_stats.py` and `test_enh3528_token_provenance.py` to seed normalized usage via the store, then exercise actual session selection/reporting. Assert totals, provenance and missing counts; do not weaken Qwen/Gemini expectations just because their older parsers stripped usage.
- Add tests for no store, unreadable store, selected session not ingested, missing components, same-session multi-channel observations, host/agent exclusion and latest-session equivalence. Keep unresolved coverage qualified through the shared selector.
- Reuse `scripts/tests/spike/enh3549_read_side_fake_hosts/`; preserve real host registries outside test-scoped monkeypatching. The spike proves the seam only, not full message/log extraction.
- Keep `ll-ctx-stats --json` stdout machine-readable when discovery/storage diagnostics are present.

### Documentation

- `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/API.md` — document stored-usage selection, unavailable/not-yet-ingested cases, explicit backfill guidance, and stderr diagnostics. Do not claim all non-Codex hosts stay unknown after their producer contracts land.
- `docs/ARCHITECTURE.md` — describe the reader boundary and reused fake-host mechanism if its documented composition surface changes.

### Preserved Research Context

The following research records discovered paths and conventions. The Program Design and Implementation Steps above/below supersede earlier raw-transcript accounting proposals; the spike supersedes the lack-of-injection-precedent observation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Per-host joins are wider than the map lists.** `user_messages.py` also carries `.opencode`/`.pi`/`.qwen` `projects` joins (`:516`, `:522`, `:580`) plus the gemini/kimi/omp probes, and `session_store/sessions.py` carries opencode/pi/qwen joins (`:586`, `:590`, `:595`) and the `_ENCODED_DIR_HOSTS` root (`:783`). `sessions.py` imports six per-host `_get_<host>_project_folder` probes from `user_messages` (`:48-53`, used `:361-375`), not only the claude one. `writers.py` has a further qwen `projects_root` (`:2717`) beside the `:2768` table. The gate's scan scope must cover all of these, or its allowlist must name them with reasons.
- **Non-reader `.claude` joins exist and are not violations:** `cli/messages.py:334` (output dir), `init/tui.py`, `init/writers.py`, `worktree_utils.py` (CLAUDE.md/config dirs). A gate keyed on `.claude` alone would flag them; keyed on the `projects` pairing it would not.
- **Session-registry constants:** `_REGISTERED_HOSTS` (`sessions.py:294`), `_LAYOUT_HOSTS` (`:308`), `_PARSERS` (`:1183`); `iter_events` yields nothing for a host absent from `_PARSERS`, and `detect_sessions` returns `[]` for an unregistered host. The two fakes are registered only in `_HOST_RUNNER_REGISTRY` under `TEST_ONLY_HOSTS`, and `fake_host.py` has no transcript/session surface at all.
- **Existing read-side fixtures usable without new capture:** `scripts/tests/fixtures/codex/` (`rollout-exec.jsonl`, `rollout-interactive.jsonl`, `rollout-exec-resume.jsonl`), `fixtures/qwen/`, `fixtures/gemini/`, `fixtures/omp/`, and Claude-shaped `fixtures/streaming_parity/trace_*/recorded.jsonl`. No `claude`, `opencode`, `pi` or `kimi` fixture directories exist. Also in the neighbourhood: `scripts/tests/conformance/conftest.py`, `conformance/test_host_conformance.py`, and `scripts/tests/spike/enh3430_workspace_union/` (`fixtures.py:37` references `_get_claude_project_folder`).
- **Test helpers and coverage not previously listed:** `test_session_discovery.py:_write_claude_session` (`:1268`) and `test_detect_sessions_claude_code_resolves_via_home_not_get_project_folder` (`:257`); `test_user_messages.py` `get_project_folder` per-host tests (`:106-594`); `test_session_store_lifecycle.py`, `test_enh3538_token_observations.py`, `test_enh_3393_gemini_normalizer.py`, `test_cli.py` reference the seam symbols; `test_verify_private_refs.py` and `test_verify_skill_prose.py` hold `.claude/projects` literals for the two lint tools the gate must allowlist.
- **Documentation not previously listed:** `docs/reference/API.md` documents `_get_claude_project_folder` (`:3473`) and `get_sessions_folder` (`:3512-3526`); `docs/reference/HOST_COMPATIBILITY.md` has further `get_project_folder` mentions (`:544`, `:566`, `:629`); `docs/codex/usage.md:95`; `docs/ARCHITECTURE.md` (seam symbols; fakes at `:880-881`). Docs holding a `.claude/projects` literal that the existing prose sweep does not cover: `docs/guides/HISTORY_SESSION_GUIDE.md`, `EXAMPLES_MINING_GUIDE.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/claude-code/*`. `skills/audit-claude-config/` and `agents/consistency-checker.md` (with `.qwen`/`.kimi-code`/`.gemini` mirrors) also carry the literal; editing any trips the mirror gates.
- **Convention — fake hosts are runner-side only.** Fakes register in `_HOST_RUNNER_REGISTRY`/`TEST_ONLY_HOSTS` and drive a real `ll-fake-host` executable; the session-side registries are module constants that production does not dynamically extend; the spike below now patches them in tests (the earlier zero-hit search predates the spike). Tests that need the seam either mock it by dotted string (`_DETECT_SESSIONS_PATH`, `_EXPLAIN_NO_SESSIONS_PATH` in `test_cli_messages.py`) or write real files under a fake home.
  Historical risk retired at the seam layer by the spike below; end-to-end reader dispatch remains to be proven.
- **Convention — gate tests** scan `scripts/little_loops/**/*.py` with `ast.parse`, hold a module-level allowlist with a reason per entry, and assert collected `rel:lineno` violations equal `[]`. Two allowlist shapes exist: file-keyed (`test_history_store_chokepoint_gate.py`) and `(file, enclosing function)`-keyed (`test_usage_selection_chokepoint_gate.py`). They disagree on staleness: only the history gate fails on a stale entry (`test_allowlist_entries_still_exist_and_still_have_raw_connects`); the usage gate instead has a scan-pattern self-check (`test_gate_detects_a_stray_site`). The ENH's own criterion requires both behaviours.
- **Convention — named-cause warnings** are two plain `print(..., file=sys.stderr)` lines (`No sessions found for: {cwd}` then the `explain_no_sessions` reason; cause discarded) — `cli/messages.py:188-196`, `cli/logs.py:583-589`, `cli/session.py:697-771`. `messages`/`logs` do not thread `home=` into `detect_sessions`, so their CLI tests rely on patching `Path.home`; seam-level tests thread `home=`. The autouse `_isolate_session_log_dir` fixture already redirects `Path.home` in every test.

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Convention — a migrated reader parses transcripts only through `iter_events(handle)` and treats `event.payload` as the old parsed record**; raw `open()` survives only on non-transcript files plus two transcript cases. Evidence: `user_messages.extract_user_messages` (handle-based since ENH-3428), `cli/logs.py:_cmd_extract`. The two surviving transcript reads are `ctx_stats._compute_cache_rate_from_jsonl` (the one this issue migrates) and a pre-`iter_events` probe in `_cmd_extract` (`cli/logs.py:721-730`) kept so unreadable files land in `skipped`; `test_extract_unreadable_file_reported` locks that reporting contract.
- **Contested: unreadable-file handling.** `_cmd_extract` keeps a raw probe to report unreadable files; `ctx_stats` wraps the whole read and returns `None`; `iter_events` itself yields nothing on `OSError`. That concern applied to the earlier transcript-to-iter_events proposal. The revised stored-usage path distinguishes unreadable store from no eligible observations; retain unreadable-file reporting for message/log extraction.
- **Payload shape is host-dependent, so a raw-record reader sees different data per host.** `claude-code`, `codex`, `kimi-code` yield host-native records; `qwen`, `gemini`, `omp` yield normalizer-output (Claude-shaped, `message.usage` stripped); `opencode`, `pi` share the Claude loop. Codex `payload` is the inner payload of a `response_item`/`event_msg` record, not the whole record. Evidence: `sessions.py` module docstring "Payload rule (ENH-3420)", `_PARSERS`; `extract_user_messages` dispatches on `handle.host` and `_CLAUDE_SHAPED_HOSTS`.
- **Convention — parsers are `parse_<host>(path) -> Iterator[SessionEvent]` registered in `_PARSERS`, never raise on malformed lines.** `line_no` is the real file line for per-line parsers but an `enumerate` index for `parse_gemini_session`/`parse_omp_session`. No test file asserts `_PARSERS` membership; normalizer tests (`test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`) test the normalizer and layout only, with fixtures under `tests/fixtures/<host>/`.
- **Convention — home isolation has three co-existing styles.** (A) seam-level tests thread `home=tmp_path` (`test_session_discovery.py`, the spike tests); (B) CLI-level tests patch `Path.home` (`test_ll_logs.py`, `test_cli_ctx_stats.py:test_resolves_qwen_chats_transcript`) because the CLIs call `detect_sessions` without `home=`; (C) unit tests patch the seam call site with a hand-built `SessionHandle` (`test_cli_ctx_stats.py` helper `_handle`). Patch targets disagree: `ctx_stats`/`logs` import `detect_sessions` at module level (`little_loops.cli.<mod>.detect_sessions`), whereas `messages.py` imports lazily (`little_loops.session_store.detect_sessions`) — a new `explain_no_sessions` import in `ctx_stats` must pick one and its test patch target must match.
- **Convention — uuid dedup lives only in the `ctx_stats` single-session reader** (`seen_uuids`; `test_deduplicates_by_uuid`). `_codex_cache_usage` does not dedup; the `usage_events` backfill in `writers.py` dedups via `raw_events` `(source_path, line_no)`. `SessionEvent.line_no` is documented as matching that index, but the revised stored-usage reader delegates identity/coverage to the shared selector; do not carry this old local dedup proposal into the new accounting path.
- **Reusable helpers that already exist:** `token_provenance` (`counted_entry`, `json_pointer`, `format_figure`, `footnotes`; already imported by `ctx_stats`), `ctx_stats._known_int`, `subprocess_utils.normalize_codex_input`, `sessions.handles_from_paths`/`session_id_for` (synthesize handles from bare paths), and `cli/logs.py:_detect_project_handles`.
- **No read-side conformance precedent exists outside the spike.** `test_host_composition.py`, `test_host_conformance.py` and `conformance/conftest.py` contain no `detect_sessions`/`iter_events`/`Path.home` usage; the only test-side `_PARSERS` writes are `monkeypatch.setitem` in `scripts/tests/spike/enh3549_read_side_fake_hosts/fake_read_hosts.py`. The spike's `monkeypatch` injection is therefore the sole precedent, and its "no production change needed" result holds only at the seam layer (see Spike Results finding on `_CLAUDE_SHAPED_HOSTS`).

## Implementation Steps

1. Pin existing latest-session/host/agent selection and cache result semantics in store-backed tests; classify remaining message/log raw reads before changing them.
2. Replace cache transcript accounting with the read-only stored-observation helper through `select_usage_observations`; preserve known components and qualification, and make missing/unreadable usage explicit.
3. Call `explain_no_sessions` from `main_ctx_stats` on empty discovery; keep diagnostics off JSON stdout.
4. Promote the spike injection fixtures and extend them through actual reader consumers, resolving the `extract_user_messages` host gate without changing production registries for fake hosts.
5. Add the host transcript-root isolation gate with reasoned exceptions and stale-entry/stray-site checks. Update docs and run focused tests plus `python -m pytest scripts/tests/`.

## Confidence Check Notes

Historical score: readiness 65/100, outcome 52/100, recorded before refinement/spike and this epic review. Re-run confidence checking after the revised contracts are refined; these numbers do not certify the revised scope.

Resolved specification gaps: Program Design, Integration Map, implementation steps and standard sections are present; discovery migration is already complete; the seam-level fake injection mechanism has spike evidence.

Remaining readiness work: finalize/test stored-usage session selection and missing-store behavior; demonstrate fake fixtures through actual readers (the spike identifies an `extract_user_messages` gate); wait for ENH-3532/3534 for full stored host coverage. Preserve the completed spike and its limitations below.

## Spike Results

_Added by `/ll:spike` on 2026-09-24_

**Retired risks**

| Risk (from Outcome Risk Factors / Codebase Research) | Proven by | Result |
|------------------------------------------------------|-----------|--------|
| No precedent injects a fake host into session discovery | `TestDiscovery::test_both_fakes_discovered_via_real_detect_sessions`, `test_union_discovery_carries_both_fake_hosts` | ✓ pass |
| Read side not proven host-agnostic across divergent shapes | `TestHostAgnosticRead::test_divergent_shapes_yield_same_observation`, `test_raw_payloads_really_diverge` | ✓ pass |
| Injection must not regress real hosts or named-cause warnings | `test_real_hosts_still_resolve_with_fakes_installed`, `TestNamedCause::*` | ✓ pass |

**Injection surface (minimal, all via `monkeypatch`)**: `_PARSERS`, `_REGISTERED_HOSTS`, `_LAYOUT_HOSTS`, `sessions._project_folder_for_layout_host`, `writers.host_layout_for`. No production change needed.

**Finding**: `user_messages.extract_user_messages` gates on `_CLAUDE_SHAPED_HOSTS` and skips unknown hosts, so a read-side composition test through it needs either a Claude-shaped fake or a dispatch hook; the spike proves the seam layer (`detect_sessions`/`iter_events`/`explain_no_sessions`) only.

**Spike location**: `scripts/tests/spike/enh3549_read_side_fake_hosts/` (plan: `.ll/spikes/spike-ENH-3549.md`)
**Verification**: 10 spike tests + 196 regression tests pass across 2 commands.
**Promotion**: fold into `scripts/tests/conformance/` beside `test_host_composition.py`, in a separate PR.

## Session Log
- `/ll:refine-issue` - 2026-09-25T01:49:59 - `2a69c442-43f4-408a-839a-d32ff801a6aa.jsonl`
- `/ll:decide-issue` - 2026-09-25T01:45:38 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:spike` - 2026-09-25T01:44:07 - `d516d85d-c844-46f9-818c-1329a5ea8e8a.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:41:16 - `e0edff4d-cab8-40c4-ab83-ef8eab746346.jsonl`
- `/ll:wire-issue` - 2026-09-25T01:20:25 - `d7aee0ef-9942-42c4-9fcc-7d8d7c2a43ed.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:12:50 - `4d305eb6-e0ad-4528-8217-7edc572927c3.jsonl`
- `/ll:format-issue` - 2026-09-25T01:06:51 - `4d305eb6-e0ad-4528-8217-7edc572927c3.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:02:51 - `f35cbaf1-740e-46e5-84c9-0ecf04a645f4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T23:55:45 - `2bb94109-d967-427c-a647-9b0a7a8e368e.jsonl`

---

## Status

**Open** | Created: 2026-09-24 | Priority: P2
