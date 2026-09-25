---
id: ENH-3549
title: Migrate ll-logs, ll-messages, and ll-ctx-stats onto the session-watcher seam
  so every reader is host-agnostic
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

# Migrate ll-logs, ll-messages, and ll-ctx-stats onto the session-watcher seam so every reader is host-agnostic

## Summary

The runtime-adapter seam for host log ingestion shipped in v1.162.0 (FEAT-3417, with Codex as the second implementation), and the write-side divergent-fakes acceptance landed in v1.164.0 (ENH-3456/ENH-3459). The migration itself has not: `ll-logs`, `ll-messages`, and `ll-ctx-stats` still reach directly for `~/.claude/projects/<munged-cwd>/`, so every log-derived surface remains Claude-Code-only by construction even though the seam that fixes it is in the tree. The toolkit can write a Codex session's artifacts and then cannot read a single Codex session back.

Migrate all three readers onto the session-watcher seam — detect, watch, emit typed events, stop — with per-host parsers behind it and one shared fan-in above it, so a Codex session reads back as naturally as a Claude Code one. One implementation serves many readers: `ll-logs`, `ll-messages`, `ll-ctx-stats`, and any future dashboard or export consumer attach to the same seam rather than each re-parsing host transcripts directly. Downstream, the dataset export and the quality rollups consume these readers and remain single-host until this lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Scope is narrower than the Summary states.** `cli/logs.py`, `cli/messages.py` and `cli/ctx_stats.py` contain no `.claude/projects` literal and make no calls into the `user_messages` project-folder helpers; they already route through `detect_sessions`/`iter_events` (ENH-3428/3429/3430). The direct joins remain in `user_messages._get_claude_project_folder`, `sessions._list_claude_workspaces`, `sessions._explain_encoded_dir_host`, and `writers.host_layout_for` (write-side).
- **No `SessionWatcher` symbol exists in code.** "Session-watcher seam" is the session-discovery seam (`SessionHandle`, `detect_sessions`, `iter_events`) in `session_store/sessions.py`.
- **Related open work overlaps:** ENH-3419 (adopt seam in the three readers), ENH-3546 (non-Codex cache-rate provenance, referenced in `_compute_cache_rate_from_jsonl`). Confirm which acceptance criteria these already satisfy before implementing.
- **Read-side divergent-fake gap confirmed:** the fakes (`FakeHostRunner`, `FakeMinimalHostRunner`) have no session-log discovery or parser; `_PARSERS`/`_REGISTERED_HOSTS` hold only the eight real hosts. The composition test would need read-side fake session records or an equivalent fixture.

## Current Behavior

The three CLIs already discover sessions through `detect_sessions` and read events through `iter_events` (or handle-taking extractors in `little_loops.user_messages`); ENH-3428/3429/3430 landed that. The remaining gaps are narrower than the Summary states:

- `little_loops.user_messages._get_claude_project_folder` and `little_loops.session_store.sessions._list_claude_workspaces` still join `~/.claude/projects` themselves, and `detect_sessions` reaches the former.
- `ll-ctx-stats` (`_compute_cache_rate_from_jsonl`) reads Codex through `iter_events` but keeps a raw `open(handle.path)` reader for every other host, and labels non-Codex cache figures `provenance: "unknown"`.
- `ll-ctx-stats` has no named-cause warning when no sessions are found (`explain_no_sessions` is not called).
- The composition suite (`tests/conformance/test_host_composition.py`) exercises only the write/executor side; no fake host has a read-side session record, and no test asserts source files avoid a `.claude/projects` literal.

## Expected Behavior

All three readers attach to the session-watcher seam (detect, watch, emit typed events) and consume per-host parsers behind it. A Codex session for the current workspace reads back in `ll-logs` and `ll-messages` like a Claude Code one, `ll-ctx-stats` carries per-observation provenance (authoritative vs estimate), and no migrated reader references `~/.claude/projects/` directly.

## Design constraints

- The seam stays at the lifecycle only. Per-host parsers live behind it and share nothing above it. Do not introduce a common abstraction over tool-call shapes or token accounting: the runtimes do not overlap enough for a forced common record to beat two honest per-host ones.
- Discovery failure and genuine absence must remain distinguishable after the migration. A workspace whose sessions exist on disk but match nothing renders a named-cause warning, not an empty result; the migration must not regress that behavior where it exists today.
- The Codex parser is tested against a captured real-shape rollout fixture, treated as perishable — vendor shape drift is one re-capture away from detection. The fixture complements, not replaces, the scripted fake hosts.

## Acceptance criteria

- The divergent fakes pass on the **read** side, not only the write side: the composition test drives both fakes' session records through the migrated readers, proving the readers host-agnostic rather than asserting it.
- A Codex session for the current workspace appears in `ll-logs` and `ll-messages` output with the same fidelity as a Claude Code session over the same period.
- `ll-ctx-stats` carries per-observation provenance for the records it counts: where a host exposes authoritative token counts they are read, and where it does not the figure is labeled an estimate (companion work: ENH-3528 and its ingestion splits ENH-3532/ENH-3534).
- No reader in the migrated set reaches for `~/.claude/projects/` directly; a mechanical check (grep or import rule) proves it.

---

## Scope Boundaries

- **In scope**: migrating `ll-logs`, `ll-messages`, and `ll-ctx-stats` onto the session-watcher seam; Codex parser behind the seam with a captured real-shape rollout fixture; read-side divergent-fake composition test; mechanical no-direct-`~/.claude/projects/` check.
- **Out of scope**: a common abstraction over tool-call shapes or token accounting; the `UsageObservation` normalization (ENH-3532, ENH-3534) and `select_usage_coverage` aggregation (ENH-3543); dataset export and quality rollups (downstream consumers).

### Scope Boundary Note

**Note** (added by `/ll:audit-issue-conflicts`): The "no common abstraction over tool-call shapes or token accounting" constraint applies to the session-watcher seam and its per-host typed events only. It does not prohibit the downstream `usage_events` contract: the shared `UsageObservation` normalization (ENH-3532, ENH-3534) and the single `select_usage_coverage` aggregation entry point (ENH-3543) are out of scope here and remain valid. `ll-ctx-stats` provenance (third acceptance criterion) consumes those stored observations; it does not re-derive token accounting in the seam.


## Impact

- **Priority**: P2 - every log-derived surface is Claude-Code-only until this lands; blocks host-agnostic dataset export and quality rollups.
- **Effort**: Large - three readers plus a Codex parser, fixture, and composition test.
- **Risk**: Medium - `user_messages` has many dependents; discovery-failure vs genuine-absence warnings must not regress.
- **Breaking Change**: No

## Program Design

### Types

- `SessionHandle`: frozen dataclass (`host: str`, `session_id: str`, `path: Path`, `cwd: Path`, `updated_at: float`, `is_agent: bool`) in `little_loops.session_store.sessions`; existing, unchanged
- `SessionEvent`: frozen dataclass (`type: str`, `timestamp: str`, `host: str`, `payload: dict[str, Any]`, `line_no: int | None`); existing, unchanged
- `NoSessionsCause`: `str` Enum naming why discovery came back empty; existing, consumed by `ll-ctx-stats` after this change

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` — existing seam entry point
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing per-host parser dispatch
- `explain_no_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, home: Path | None = None) -> tuple[NoSessionsCause, str]` — existing; to be called from `ll-ctx-stats`
- `_compute_cache_rate_from_jsonl(cwd: Path, host: str | None) -> dict | None` — existing in `little_loops.cli.ctx_stats`; non-Codex branch to move onto `iter_events`
- `_get_claude_project_folder(encoded_path: str, *, home: Path | None = None) -> Path | None` — existing in `little_loops.user_messages`; the one join the seam still delegates to

### Call Path

`main_messages` -> `detect_sessions` -> `iter_events` -> `extract_user_messages`

`main_logs` -> `detect_sessions` -> `iter_events`

`main_ctx_stats` -> `_compute_cache_rate_from_jsonl` -> `detect_sessions` -> `iter_events`

### Decision Rules

N/A — no new decision logic

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` — non-Codex branch of `_compute_cache_rate_from_jsonl` opens `handle.path` directly; no `explain_no_sessions` on empty discovery
- `scripts/little_loops/user_messages.py` — `_get_claude_project_folder` and sibling per-host joins; module docstring line 4
- `scripts/little_loops/session_store/sessions.py` — `_list_claude_workspaces` and `_explain_encoded_dir_host` carry their own `home / ... / "projects"` joins
- `scripts/tests/conformance/test_host_composition.py` — write-side only today

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_reader_no_claude_projects_gate.py` — NEW gate test (name suggested); no gate over Python source exists today (`test_session_log_prose_sweep.py` only scans skill prose) [Agent 1, 2, 3 finding]
- `scripts/little_loops/cli/ctx_stats.py:main_ctx_stats` — the `explain_no_sessions` call belongs here, not inside `_compute_cache_rate_from_jsonl`; changing that function's `dict | None` return would break the `None`-on-empty tests [Agent 2, 3 finding]

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` — already on the seam: `detect_sessions` (`:157`, `:583`, `:1958`, `:2705`), `iter_events`, `explain_no_sessions`; several raw `open()` sites remain (`:659`, `:726`, `:827`, `:1633`, `:2108`), not yet classified as transcript vs. non-transcript reads [Agent 1, 3 finding]
- `scripts/little_loops/cli/messages.py:main_messages` — already calls `detect_sessions` (`:188`) and `explain_no_sessions`; `extract_user_messages` not traced for direct file reads [Agent 1, 2 finding]
- `scripts/little_loops/session_store/__init__.py` — re-exports `NoSessionsCause`, `explain_no_sessions`, `iter_events`, `host_layout_for`; `ctx_stats` should import via this path [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` — calls `iter_events` (`:796`) and `host_layout_for` (`:1127`); consumers of the seam, unaffected unless signatures change [Agent 1 finding]
- `scripts/little_loops/session_store/sessions.py:19-47` — imports `_get_claude_project_folder` from `user_messages` (circular seam); `_explain_encoded_dir_host` is used only inside `sessions.py` (`:778`, `:916`) [Agent 1 finding]
- `scripts/little_loops/cli/verify_private_refs.py`, `scripts/little_loops/cli/verify_skill_prose.py` — carry `~/.claude/projects` regex/docstring literals; lint tools, not readers — must be excluded from (or allowlisted in) the new gate [Agent 1, 2 finding]

### Wiring Notes
_Wiring pass added by `/ll:wire-issue`:_
- `iter_events` payload sufficiency for the non-Codex branch: `claude-code`, `opencode`, `pi` yield the full record (`_parse_claude_shaped`), so `uuid` and `message.usage` are reachable and the `uuid` dedup stays in the caller. `qwen`, `gemini`, `omp` normalizers strip `message.usage` and `kimi-code` yields raw wire records, so those hosts stay `unknown` regardless of this migration (ENH-3546 territory). `iter_events` swallows `OSError`, so the `open()` vanish-guard collapses into the existing "no eligible events → `None`" return [Agent 2 finding]
- Gate scan method: `_ENCODED_DIR_HOSTS` in `sessions.py` builds the path from separate `".claude"` / `"projects"` strings, so a contiguous-substring scan would miss it. Use an AST `Path`-join scan plus a string-constant scan. Files holding the literal today: `user_messages.py:_get_claude_project_folder` (`:503`, docstring `:4`), `session_store/sessions.py:_list_claude_workspaces` (`:612`), `session_store/writers.py:host_layout_for` (`:2768`) [Agent 1, 2 finding]
- No live consumer of `ll-ctx-stats --json` was found in `hooks/`, `commands/`, `skills/`, or `scripts/little_loops/loops/`; `.loops/` live loop YAMLs were not inspected (search returned only run logs) [Agent 2 finding]
- `scripts/little_loops/cli/session.py` — non-Codex `backfill` paths still call `get_project_folder(host=...)` (lines 710, 769)
- `scripts/little_loops/hooks/session_start.py` — `get_project_folder(root, host=...)`
- `scripts/little_loops/session_log.py`, `scripts/little_loops/fsm/continuity.py` — `get_sessions_folder`
- `scripts/little_loops/session_store/writers.py` — `host_layout_for` `projects_root` table (write-side layout, not a reader)

### Conventions in Force
- Readers take `SessionHandle`s from `detect_sessions` and parse only through `iter_events`; `home=` is threaded so tests pass `tmp_path` — evidence: `cli/logs.py`, `cli/messages.py`, `cli/ctx_stats.py`
- `session_store` never imports from `cli` — evidence: `list_workspaces` docstring (ENH-3430)
- Mechanical "must not reference X" gates are pytest tests with a reasoned allowlist that fails when an entry goes stale — evidence: `test_history_store_chokepoint_gate.py`, `test_usage_selection_chokepoint_gate.py`
- Codex fixtures are committed captures with a version-keyed re-capture rule — evidence: `scripts/tests/fixtures/codex/README.md`, `.ll/learning-tests/codex-rollout.md`
- Token provenance is `Literal["measured","estimated","unknown"]`, components `None` when unreported — evidence: `subprocess_utils.TokenUsage`, `token_provenance.py`

### Tests
- `scripts/tests/test_cli_ctx_stats.py`, `test_ll_logs.py`, `test_cli_messages.py`, `test_session_discovery.py`, `test_user_messages.py` — existing reader coverage that must keep passing
- `scripts/tests/conformance/test_host_composition.py` — hosts the read-side composition test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_ctx_stats.py:TestComputeCacheRateFromJsonl` — update: non-Codex tests (`test_computes_hit_rate`, `test_aggregates_multiple_turns`, `test_deduplicates_by_uuid`, `test_skips_agent_jsonl_files`, `test_returns_none_when_total_zero`, `test_skips_non_assistant_entries`) write Claude-shaped JSONL read by raw `open()`; `test_skips_file_that_vanishes_before_stat` asserts the `OSError` path that `iter_events` swallows [Agent 3 finding]
- `scripts/tests/test_cli_ctx_stats.py:test_resolves_qwen_chats_transcript`, `test_resolves_gemini_chats_transcript` — highest break risk: unpatched real chain asserting `cache_read == 61559`, but qwen/gemini normalizers strip `message.usage` [Agent 3 finding]
- `scripts/tests/test_cli_ctx_stats.py` — render tests `test_hit_rate_line_shows_host_suffix_for_non_claude_host` and `test_hit_rate_line_byte_identical_for_claude_code_host` get `[unknown]` from the `_cache_rate_provenance` fallback, not the reader; keep passing if the reader still returns no `provenance` key [Agent 2 finding]
- `scripts/tests/test_enh3528_token_provenance.py:TestCacheRateFromTranscript` — update: `test_absent_keys_are_missing_not_zero` asserts `provenance == "unknown"`; `test_explicit_null_does_not_crash` and `test_usage_without_any_key_is_not_an_observation` share the raw-file path; `test_codex_result_is_measured` is unaffected [Agent 3 finding]
- `scripts/tests/test_cli_ctx_stats.py` — NEW: empty-discovery test patching `little_loops.cli.ctx_stats.explain_no_sessions`, modelled on `scripts/tests/test_ll_session.py` (patches at `:792`, `:814`) and `_EXPLAIN_NO_SESSIONS_PATH` in `test_cli_messages.py:344` [Agent 3 finding]
- `scripts/tests/test_ll_logs.py` — may break: fake-home `~/.claude/projects/<encoded-cwd>` helpers (docstring ~`:168`, `:1635`, `:4480`) if any raw `open()` site in `cli/logs.py` is replaced [Agent 3 finding]
- `scripts/tests/test_cli_messages.py` — may break only if the `explain_no_sessions` import location changes (patch target `little_loops.session_store.explain_no_sessions`) [Agent 3 finding]
- `scripts/tests/conformance/test_host_composition.py` — read-side test builds `SessionHandle(host="fake"|"fake-minimal", ...)` directly; `FakeHostRunner`/`FakeMinimalHostRunner` (`host_runner.py:2066`, `:2151`) have no session-log surface and neither host is in `_PARSERS`/`_REGISTERED_HOSTS`, so the test needs either registered fake parsers or a fixture-driven per-host parser stub; `_FAKES = ("fake", "fake-minimal")` at `:47` [Agent 3 finding]
- `scripts/tests/test_usage_selection_chokepoint_gate.py`, `scripts/tests/test_history_store_chokepoint_gate.py` — templates for the new gate: string-constant scan with `_enclosing_functions()` and `test_gate_detects_a_stray_site` (usage gate); stale-entry test `test_allowlist_entries_still_exist_and_still_have_raw_connects` (history gate) [Agent 1, 3 finding]
- `scripts/tests/conftest.py:_isolate_session_log_dir` (`:1135`) — autouse fixture redirecting `Path.home` to an empty fake home; per-test overrides win [Agent 3 finding]
- `scripts/tests/test_session_log_prose_sweep.py:30` — only existing `.claude/projects` check (skill prose); unaffected [Agent 1 finding]
- Indirect only, no direct unit tests exist for `_get_claude_project_folder`, `_list_claude_workspaces`, `_explain_encoded_dir_host` — covered via `test_session_discovery.py` (`explain_no_sessions` tests `:1277`–`:1484`) and `test_user_messages.py` [Agent 3 finding]
- `scripts/tests/test_hook_session_start.py`, `test_fsm_continuity.py`, `test_session_log.py`, `test_ll_session.py`, `test_enh_3166_qwen_normalizer.py` — monkeypatch `get_project_folder`/`host_layout_for`; break only if those helpers' signatures change [Agent 1 finding]

### Documentation
- `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md` — reader host-coverage statements

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` `### ll-ctx-stats` — "Cache figures" bullet ("Codex observations are `measured`; other hosts are `unknown`") stays accurate until ENH-3546; add a bullet describing the new empty-discovery named-cause output [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — footnote on `ll-ctx-stats`'s cache-rate reader (ENH-3429) says `_codex_cache_usage` returns the same four keys "the Claude reader returns"; reword if the non-Codex reader changes [Agent 2 finding]
- `docs/reference/API.md` — `get_project_folder` prose ("`ll-ctx-stats`'s cache-rate reader moved off this helper onto `detect_sessions` — ENH-3429") is historical and stays accurate [Agent 2 finding]
- `skills/configure/areas.md` — mentions `ll-ctx-stats`; no edit needed, and any edit trips the host-mirror gates (`ll-adapt --apply`) [Agent 2 finding]
- `scripts/tests/test_wiring_cli_registry.py`, `scripts/tests/test_wiring_init_and_configure.py` — presence-only assertions for `ll-ctx-stats` in `CLI.md` / `areas.md`; unaffected [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Per-host joins are wider than the map lists.** `user_messages.py` also carries `.opencode`/`.pi`/`.qwen` `projects` joins (`:516`, `:522`, `:580`) plus the gemini/kimi/omp probes, and `session_store/sessions.py` carries opencode/pi/qwen joins (`:586`, `:590`, `:595`) and the `_ENCODED_DIR_HOSTS` root (`:783`). `sessions.py` imports six per-host `_get_<host>_project_folder` probes from `user_messages` (`:48-53`, used `:361-375`), not only the claude one. `writers.py` has a further qwen `projects_root` (`:2717`) beside the `:2768` table. The gate's scan scope must cover all of these, or its allowlist must name them with reasons.
- **Non-reader `.claude` joins exist and are not violations:** `cli/messages.py:334` (output dir), `init/tui.py`, `init/writers.py`, `worktree_utils.py` (CLAUDE.md/config dirs). A gate keyed on `.claude` alone would flag them; keyed on the `projects` pairing it would not.
- **Session-registry constants:** `_REGISTERED_HOSTS` (`sessions.py:294`), `_LAYOUT_HOSTS` (`:308`), `_PARSERS` (`:1183`); `iter_events` yields nothing for a host absent from `_PARSERS`, and `detect_sessions` returns `[]` for an unregistered host. The two fakes are registered only in `_HOST_RUNNER_REGISTRY` under `TEST_ONLY_HOSTS`, and `fake_host.py` has no transcript/session surface at all.
- **Existing read-side fixtures usable without new capture:** `scripts/tests/fixtures/codex/` (`rollout-exec.jsonl`, `rollout-interactive.jsonl`, `rollout-exec-resume.jsonl`), `fixtures/qwen/`, `fixtures/gemini/`, `fixtures/omp/`, and Claude-shaped `fixtures/streaming_parity/trace_*/recorded.jsonl`. No `claude`, `opencode`, `pi` or `kimi` fixture directories exist. Also in the neighbourhood: `scripts/tests/conformance/conftest.py`, `conformance/test_host_conformance.py`, and `scripts/tests/spike/enh3430_workspace_union/` (`fixtures.py:37` references `_get_claude_project_folder`).
- **Test helpers and coverage not previously listed:** `test_session_discovery.py:_write_claude_session` (`:1268`) and `test_detect_sessions_claude_code_resolves_via_home_not_get_project_folder` (`:257`); `test_user_messages.py` `get_project_folder` per-host tests (`:106-594`); `test_session_store_lifecycle.py`, `test_enh3538_token_observations.py`, `test_enh_3393_gemini_normalizer.py`, `test_cli.py` reference the seam symbols; `test_verify_private_refs.py` and `test_verify_skill_prose.py` hold `.claude/projects` literals for the two lint tools the gate must allowlist.
- **Documentation not previously listed:** `docs/reference/API.md` documents `_get_claude_project_folder` (`:3473`) and `get_sessions_folder` (`:3512-3526`); `docs/reference/HOST_COMPATIBILITY.md` has further `get_project_folder` mentions (`:544`, `:566`, `:629`); `docs/codex/usage.md:95`; `docs/ARCHITECTURE.md` (seam symbols; fakes at `:880-881`). Docs holding a `.claude/projects` literal that the existing prose sweep does not cover: `docs/guides/HISTORY_SESSION_GUIDE.md`, `EXAMPLES_MINING_GUIDE.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/claude-code/*`. `skills/audit-claude-config/` and `agents/consistency-checker.md` (with `.qwen`/`.kimi-code`/`.gemini` mirrors) also carry the literal; editing any trips the mirror gates.
- **Convention — fake hosts are runner-side only.** Fakes register in `_HOST_RUNNER_REGISTRY`/`TEST_ONLY_HOSTS` and drive a real `ll-fake-host` executable; the session-side registries are module constants that no test patches (`monkeypatch.setattr` on `_PARSERS`/`_REGISTERED_HOSTS`/`detect_sessions`/`iter_events` has zero hits in `scripts/tests`). Tests that need the seam either mock it by dotted string (`_DETECT_SESSIONS_PATH`, `_EXPLAIN_NO_SESSIONS_PATH` in `test_cli_messages.py`) or write real files under a fake home.
  ⚠ Unproven mechanism — no precedent injects a fake host into session discovery
- **Convention — gate tests** scan `scripts/little_loops/**/*.py` with `ast.parse`, hold a module-level allowlist with a reason per entry, and assert collected `rel:lineno` violations equal `[]`. Two allowlist shapes exist: file-keyed (`test_history_store_chokepoint_gate.py`) and `(file, enclosing function)`-keyed (`test_usage_selection_chokepoint_gate.py`). They disagree on staleness: only the history gate fails on a stale entry (`test_allowlist_entries_still_exist_and_still_have_raw_connects`); the usage gate instead has a scan-pattern self-check (`test_gate_detects_a_stray_site`). The ENH's own criterion requires both behaviours.
- **Convention — named-cause warnings** are two plain `print(..., file=sys.stderr)` lines (`No sessions found for: {cwd}` then the `explain_no_sessions` reason; cause discarded) — `cli/messages.py:188-196`, `cli/logs.py:583-589`, `cli/session.py:697-771`. `messages`/`logs` do not thread `home=` into `detect_sessions`, so their CLI tests rely on patching `Path.home`; seam-level tests thread `home=`. The autouse `_isolate_session_log_dir` fixture already redirects `Path.home` in every test.

## Implementation Steps

1. The three readers reach transcripts only through `detect_sessions`/`iter_events`, including `ll-ctx-stats` for non-Codex hosts; `test_cli_ctx_stats.py` keeps passing.
2. `ll-ctx-stats` surfaces `explain_no_sessions` output when discovery is empty, matching `ll-messages`/`ll-logs`.
3. A read-side composition test drives both divergent fakes' session records through the migrated readers, alongside the existing write-side suite.
4. A gate test asserts no reader module carries a `.claude/projects` literal, with an allowlist for the seam's own path resolvers that fails when stale.
5. `pytest scripts/tests/` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/ctx_stats.py` — call `explain_no_sessions` in `main_ctx_stats` (not inside `_compute_cache_rate_from_jsonl`, whose `dict | None` contract the existing tests pin); import it via `little_loops.session_store`
- Update `scripts/little_loops/cli/ctx_stats.py:_compute_cache_rate_from_jsonl` — replace the raw `open(latest.path)` with `iter_events(handle)`, reading `event.payload["message"]["usage"]`; keep `uuid` dedup in the caller; keep `provenance` absent/`unknown` for non-Codex
- Update `scripts/tests/test_cli_ctx_stats.py` and `scripts/tests/test_enh3528_token_provenance.py` — adapt the non-Codex raw-reader tests; re-verify `test_resolves_qwen_chats_transcript` / `test_resolves_gemini_chats_transcript` (qwen/gemini normalizers strip `message.usage`)
- Add empty-discovery test in `scripts/tests/test_cli_ctx_stats.py` — patch `little_loops.cli.ctx_stats.explain_no_sessions`
- Add read-side composition test in `scripts/tests/conformance/test_host_composition.py` — decide how the divergent fakes get session records, since neither is in `_PARSERS`/`_REGISTERED_HOSTS`
- Add `scripts/tests/test_session_reader_no_claude_projects_gate.py` — AST `Path`-join + string-constant scan of `scripts/little_loops/**/*.py`, reasoned allowlist for `session_store/sessions.py`, `session_store/writers.py`, `user_messages.py`, `cli/verify_private_refs.py`, `cli/verify_skill_prose.py`, a stale-entry test, and a stray-site self-check
- Update `docs/reference/CLI.md` (`### ll-ctx-stats`) and `docs/reference/HOST_COMPATIBILITY.md` (`ll-ctx-stats` footnote) — describe empty-discovery output and, if changed, the reader wording

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 52/100 → LOW

### Concerns
- `depends_on` ENH-3532 and ENH-3534 are not yet done; the ctx-stats provenance criterion consumes their observations.

### Gaps to Address
- Program Design gate fails: `## Program Design` is missing. Populate it with the seam types, signatures and call path (`/ll:refine-issue` or `/ll:reconcile-issue`), or set `program_design_not_applicable: true`.
- No Integration Map, Files to Modify, or implementation steps. Which reader modules migrate (e.g. `little_loops/user_messages.py`, the ll-logs and ll-ctx-stats CLIs) and which session-watcher entry points they attach to are not enumerated.
- Missing sections: Current Behavior, Expected Behavior, Impact, Scope Boundaries, Status.

### Outcome Risk Factors
- Broad enumeration across three readers plus a Codex parser, with an unspecified per-reader migration design (moderate per-site complexity).
- Wide blast radius: `user_messages` has many dependents.

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
