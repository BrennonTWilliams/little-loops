---
id: ENH-3649
type: ENH
title: Session-reader isolation gate, no-session diagnostics and read-side fake-host
  coverage
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
completed_at: '2026-09-29T08:22:45Z'
captured_at: '2026-09-29T01:55:17Z'
labels:
- observability
- multi-host
relates_to:
- ENH-3549
- ENH-3656
- ENH-3428
- ENH-3429
- ENH-3430
unproven_mechanism: true
spike_attempted: true
spike_completed: true
---

# ENH-3649: Session-reader isolation gate, no-session diagnostics and read-side fake-host coverage

## Summary

Finish read-side session isolation that does not depend on stored usage: a mechanical gate against direct host-transcript-root access, a named-cause warning in `ll-ctx-stats` on empty discovery, promotion of the ENH-3549 spike's fake-host injection into conformance tests, and a fix for the `extract_user_messages` host gate so fake hosts reach actual message/log readers. Split out of ENH-3549 (2026-09-28) and detached from EPIC-3562 (2026-09-29) because most work covers general message/log readers rather than token accounting. ENH-3549 keeps the stored-usage cache-rate consumer. This issue has no blockers; coordinate its empty-discovery stderr warning with ENH-3656's distinct stored-usage diagnostics so either can land first.

## Current Behavior

- Discovery in `ll-messages`, `ll-ctx-stats` and `ll-logs` already goes through `detect_sessions`/`iter_events` (ENH-3428/3429/3430). There is no `SessionWatcher` symbol; the seam is `SessionHandle`/`detect_sessions`/`iter_events` in `session_store/sessions.py`.
- Direct host-root joins remain in `user_messages._get_claude_project_folder` (plus `.opencode`/`.pi`/`.qwen` `projects` joins and gemini/kimi/omp probes), `sessions._list_claude_workspaces`, `sessions._explain_encoded_dir_host`, the `_ENCODED_DIR_HOSTS` root, and `writers.host_layout_for` / the qwen `projects_root` in `writers.py`. These are legitimate seam/layout internals, but nothing mechanically stops new readers from adding more.
- Non-reader `.claude` joins also exist and are not violations: `cli/messages.py` output dir, `init/tui.py`, `init/writers.py`, `worktree_utils.py`.
- `main_ctx_stats` does not call the no-sessions explainer when discovery is empty.
- The messages and logs CLIs already do (two `print(..., file=sys.stderr)` lines each).
- The spike at `scripts/tests/spike/enh3549_read_side_fake_hosts/` proves fake-host injection at the seam layer only (`_PARSERS`, `_REGISTERED_HOSTS`, `_LAYOUT_HOSTS`, `sessions._project_folder_for_layout_host`, `writers.host_layout_for`, all via `monkeypatch`). `user_messages.extract_user_messages` gates on `_CLAUDE_SHAPED_HOSTS` and skips unknown hosts, so fakes never reach the actual message reader.
- `cli/logs.py:_cmd_extract` keeps a pre-`iter_events` raw probe so unreadable files land in `skipped` (`test_extract_unreadable_file_reported`).

## Expected Behavior

- A gate test fails when reader code under `scripts/little_loops/` joins a host transcript root (`.claude/projects`, `.codex/sessions`, `.opencode`, `.pi`, `.qwen`, gemini/kimi/omp roots) outside a narrowly justified allowlist. Key the pattern on the transcript-root pairing (e.g. `.claude` + `projects`), not on `.claude` alone, so config/output-dir joins are not flagged.
- The allowlist is `(file, enclosing function)`-keyed with a reason per entry, **and** has both a stale-entry test (as in `test_history_store_chokepoint_gate.py`) and a stray-site self-check (as in `test_usage_selection_chokepoint_gate.py`). Lint-tool examples in `test_verify_private_refs.py` / `test_verify_skill_prose.py` are out of the scan scope with a reason.
- `main_ctx_stats` emits the `No sessions found for: {cwd}` + `explain_no_sessions` reason pair to stderr on empty discovery; `--json` stdout stays parseable. Match the patch target to however `ctx_stats` imports `explain_no_sessions` (module-level vs lazy).
- The spike's injection fixtures move into `scripts/tests/conformance/` beside `test_host_composition.py`. Divergent fake hosts pass through the actual `ll-messages`/`ll-logs` readers, not only discovery helpers. Close the `extract_user_messages` gap with an explicit per-host consumer dispatch (or fixture adapter) that preserves real-host output; do not add a common tool-call or token abstraction to the seam, and do not extend production registries for fake hosts.
- Remaining raw `open()` calls in `cli/logs.py`/`cli/messages.py` are classified as transcript or non-transcript; only genuine transcript bypasses route through the seam. `_cmd_extract`'s unreadable-file reporting is preserved.

## Scope Boundaries

- **In scope**: isolation gate, `ll-ctx-stats` empty-discovery diagnostics, spike promotion, reader-level fake-host coverage, raw-open classification.
- **Out of scope**: cache-rate accounting and the stored-usage consumer (ENH-3549); redoing discovery migration; relocating legitimate seam/layout resolvers only to satisfy the gate; token normalization.

## Program Design

### Types

- Reuse `SessionHandle`, `SessionEvent`, `NoSessionsCause`; no new watcher type.

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` — unchanged.
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — unchanged.
- `explain_no_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, home: Path | None = None) -> tuple[NoSessionsCause, str]` — unchanged; newly called from `main_ctx_stats`.
- `extract_user_messages(handles: list[SessionHandle], limit: int | None = None, since: datetime | None = None, include_agent_sessions: bool = True, include_response_context: bool = False) -> list[UserMessage]` — public signature unchanged; internal dispatch becomes per-host explicit rather than a `_CLAUDE_SHAPED_HOSTS` membership gate.

### Call Path

- `main_messages` / `main_logs` → `detect_sessions` → `iter_events` / handle-taking extractors (fake hosts included under test monkeypatching).
- `main_ctx_stats` empty discovery → `explain_no_sessions` → stderr.

## Integration Map

- `scripts/little_loops/user_messages.py`, `scripts/little_loops/cli/ctx_stats.py`, `cli/logs.py`, `cli/messages.py`.
- `scripts/tests/test_session_reader_no_claude_projects_gate.py` (new), `scripts/tests/conformance/` (promoted spike), `test_cli_ctx_stats.py`, `test_user_messages.py`, `test_ll_logs.py`, `test_cli_messages.py`, `test_session_discovery.py`.
- Remove `scripts/tests/spike/enh3549_read_side_fake_hosts/` after promotion.
- Docs: `docs/ARCHITECTURE.md` (reader boundary, fake-host mechanism), `docs/reference/CLI.md` (ctx-stats stderr diagnostic).

## Implementation Steps

1. Add `explain_no_sessions` to `main_ctx_stats` with a stderr-only test under `--json`.
2. Promote spike fixtures to conformance; add the `extract_user_messages` per-host dispatch and drive fakes through the real readers.
3. Classify raw opens in `logs.py`/`messages.py`.
4. Add the isolation gate with reasoned allowlist, stale-entry and stray-site tests; update docs; run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 — locks in multi-host reader isolation.
- **Effort**: Medium.
- **Risk**: Low to medium — dispatch change in `extract_user_messages` must keep real-host output identical.
- **Breaking Change**: No.

## Acceptance Criteria

- [x] Divergent fake fixtures pass through the actual message/log readers; real-host readback and agent/session selection are unchanged.
- [x] The isolation gate catches a stray transcript-root join, fails on a stale allowlist entry, and does not flag config/output-dir joins.
- [x] `ll-ctx-stats` empty discovery emits named-cause diagnostics to stderr; `--json` stdout parses.
- [x] Unit-level fixture tests run without installed host CLIs; the spike directory is removed after promotion.

## Implementation Evidence

- `ll-ctx-stats` now reports `explain_no_sessions()`'s named reason on stderr
  when discovery is empty, with JSON stdout remaining parseable. Cache-rate
  accounting was not changed.
- `extract_user_messages()` uses a per-host reader table. Promoted fake fixtures
  monkeypatch that table and the session seam only; conformance tests exercise
  both actual CLI readers, a real Claude host, and agent selection.
- `ll-logs diff` now reads its direct JSONL input through `iter_events()`;
  `_cmd_extract` retains its raw openability probe for skipped-file reporting.
  Remaining raw opens in the two CLIs are classified in `docs/ARCHITECTURE.md`.
- `test_session_reader_no_host_roots_gate.py` checks root joins, a stray site,
  a stale allowlist, and non-transcript `.claude` paths.
- Focused verification: 701 affected reader/CLI tests, 18 conformance and
  gate tests, targeted Ruff and Mypy checks. The parent agent owns the full
  suite and lifecycle completion.

## Preserved Research Context (moved from ENH-3549)

_From `/ll:refine-issue` 2026-09-25 on ENH-3549; line numbers are as of that date._

- **Per-host joins are wider than one host.** `user_messages.py` carries `.opencode`/`.pi`/`.qwen` `projects` joins (`:516`, `:522`, `:580`) plus gemini/kimi/omp probes; `session_store/sessions.py` carries opencode/pi/qwen joins (`:586`, `:590`, `:595`) and the `_ENCODED_DIR_HOSTS` root (`:783`), and imports six per-host `_get_<host>_project_folder` probes from `user_messages` (`:48-53`, used `:361-375`). `writers.py` has a qwen `projects_root` (`:2717`) beside the `:2768` table. The gate's scan must cover all of these or allowlist them with reasons.
- **Session-registry constants:** `_REGISTERED_HOSTS` (`sessions.py:294`), `_LAYOUT_HOSTS` (`:308`), `_PARSERS` (`:1183`). `iter_events` yields nothing for a host absent from `_PARSERS`; `detect_sessions` returns `[]` for an unregistered host. The fakes are registered only in `_HOST_RUNNER_REGISTRY` under `TEST_ONLY_HOSTS`; `fake_host.py` has no transcript/session surface.
- **Existing read-side fixtures:** `scripts/tests/fixtures/codex/`, `fixtures/qwen/`, `fixtures/gemini/`, `fixtures/omp/`, Claude-shaped `fixtures/streaming_parity/trace_*/recorded.jsonl`. No `claude`, `opencode`, `pi` or `kimi` fixture directories. Neighbours: `scripts/tests/conformance/conftest.py`, `conformance/test_host_conformance.py`, `scripts/tests/spike/enh3430_workspace_union/` (`fixtures.py:37` references `_get_claude_project_folder`).
- **Tests referencing the seam:** `test_session_discovery.py:_write_claude_session` (`:1268`), `test_detect_sessions_claude_code_resolves_via_home_not_get_project_folder` (`:257`); `test_user_messages.py` per-host `get_project_folder` tests (`:106-594`); `test_session_store_lifecycle.py`, `test_enh3538_token_observations.py`, `test_enh_3393_gemini_normalizer.py`, `test_cli.py`. `test_verify_private_refs.py` and `test_verify_skill_prose.py` hold `.claude/projects` literals for the two lint tools the gate must exclude.
- **Docs holding seam symbols or `.claude/projects` literals:** `docs/reference/API.md` (`_get_claude_project_folder` `:3473`, `get_sessions_folder` `:3512-3526`), `docs/reference/HOST_COMPATIBILITY.md` (`:544`, `:566`, `:629`), `docs/codex/usage.md:95`, `docs/ARCHITECTURE.md` (fakes at `:880-881`), `docs/guides/HISTORY_SESSION_GUIDE.md`, `EXAMPLES_MINING_GUIDE.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/claude-code/*`. `skills/audit-claude-config/` and `agents/consistency-checker.md` (with `.qwen`/`.kimi-code`/`.gemini` mirrors) also carry the literal; editing any trips the mirror gates.
- **Convention — gate tests** scan `scripts/little_loops/**/*.py` with `ast.parse`, hold a module-level allowlist with a reason per entry, and assert collected `rel:lineno` violations equal `[]`. File-keyed (`test_history_store_chokepoint_gate.py`, has a stale-entry test) and `(file, enclosing function)`-keyed (`test_usage_selection_chokepoint_gate.py`, has `test_gate_detects_a_stray_site`). This issue needs both behaviours.
- **Convention — named-cause warnings** are two `print(..., file=sys.stderr)` lines — `cli/messages.py:188-196`, `cli/logs.py:583-589`, `cli/session.py:697-771`. `messages`/`logs` do not thread `home=` into `detect_sessions`, so CLI tests patch `Path.home`; the autouse `_isolate_session_log_dir` fixture already redirects it. `ctx_stats`/`logs` import `detect_sessions` at module level; `messages.py` imports lazily from `little_loops.session_store`.
- **Contested: unreadable-file handling.** `_cmd_extract` keeps a raw probe to report unreadable files (`cli/logs.py:721-730`, `test_extract_unreadable_file_reported`); `iter_events` yields nothing on `OSError`. Preserve the reporting contract.

## Spike Results (moved from ENH-3549)

_Added by `/ll:spike` on 2026-09-24_

| Risk | Proven by | Result |
|------|-----------|--------|
| No precedent injects a fake host into session discovery | `TestDiscovery::test_both_fakes_discovered_via_real_detect_sessions`, `test_union_discovery_carries_both_fake_hosts` | ✓ pass |
| Read side not proven host-agnostic across divergent shapes | `TestHostAgnosticRead::test_divergent_shapes_yield_same_observation`, `test_raw_payloads_really_diverge` | ✓ pass |
| Injection must not regress real hosts or named-cause warnings | `test_real_hosts_still_resolve_with_fakes_installed`, `TestNamedCause::*` | ✓ pass |

**Injection surface (all via `monkeypatch`)**: `_PARSERS`, `_REGISTERED_HOSTS`, `_LAYOUT_HOSTS`, `sessions._project_folder_for_layout_host`, `writers.host_layout_for`. No production change needed at the seam layer.

**Finding**: `user_messages.extract_user_messages` gates on `_CLAUDE_SHAPED_HOSTS` and skips unknown hosts; a read-side composition test through it needs a Claude-shaped fake or a dispatch hook. The spike proves `detect_sessions`/`iter_events`/`explain_no_sessions` only.

**Location**: `scripts/tests/spike/enh3549_read_side_fake_hosts/` (plan: `.ll/spikes/spike-ENH-3549.md`). **Verification**: 10 spike tests + 196 regression tests passed.

## Status

**Done** | Created: 2026-09-29 | Priority: P2


## Resolution

- **Action**: Implement
- **Completed**: 2026-09-29
- **Status**: Done

### Changes Made

- Reader isolation gate, empty-discovery diagnostics and fake-host conformance tests are promoted; the spike directory is removed.

### Verification Results

- Full local suite: 27,525 passed, 301 skipped.
- Ruff lint and format, host-map verifier and private-reference verifier: passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency; a run with the project config and Python 3.12 target reports existing `no-any-return` and `unused-ignore` errors across the package.


## Session Log
- `/ll:manage-issue` - 2026-09-29T08:22:45 - `688ef729-26a9-43d5-8442-56084d826e08.jsonl`
