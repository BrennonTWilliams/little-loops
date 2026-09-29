---
id: ENH-3649
type: ENH
title: Session-reader isolation gate, no-session diagnostics and read-side fake-host
  coverage
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T01:55:17Z'
parent: EPIC-3562
epic: EPIC-3562
labels:
- observability
- multi-host
relates_to:
- ENH-3549
- ENH-3428
- ENH-3429
- ENH-3430
---

# ENH-3649: Session-reader isolation gate, no-session diagnostics and read-side fake-host coverage

## Summary

Finish read-side session isolation that does not depend on stored usage: a mechanical gate against direct host-transcript-root access, a named-cause warning in `ll-ctx-stats` on empty discovery, promotion of the ENH-3549 spike's fake-host injection into conformance tests, and a fix for the `extract_user_messages` host gate so fake hosts reach actual message/log readers. Split out of ENH-3549 (2026-09-28); ENH-3549 keeps the stored-usage cache-rate consumer, which depends on ENH-3532. This issue has no blockers.

## Current Behavior

- Discovery in `ll-messages`, `ll-ctx-stats` and `ll-logs` already goes through `detect_sessions`/`iter_events` (ENH-3428/3429/3430). There is no `SessionWatcher` symbol; the seam is `SessionHandle`/`detect_sessions`/`iter_events` in `session_store/sessions.py`.
- Direct host-root joins remain in `user_messages._get_claude_project_folder` (plus `.opencode`/`.pi`/`.qwen` `projects` joins and gemini/kimi/omp probes), `sessions._list_claude_workspaces`, `sessions._explain_encoded_dir_host`, the `_ENCODED_DIR_HOSTS` root, and `writers.host_layout_for` / the qwen `projects_root` in `writers.py`. These are legitimate seam/layout internals, but nothing mechanically stops new readers from adding more.
- Non-reader `.claude` joins also exist and are not violations: `cli/messages.py` output dir, `init/tui.py`, `init/writers.py`, `worktree_utils.py`.
- `main_ctx_stats` does not call `explain_no_sessions` when discovery is empty; `cli/messages.py` and `cli/logs.py` do (two `print(..., file=sys.stderr)` lines).
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

- `detect_sessions`, `iter_events`, `explain_no_sessions` — unchanged.
- `extract_user_messages` — public signature unchanged; internal dispatch becomes per-host explicit rather than a `_CLAUDE_SHAPED_HOSTS` membership gate.

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

- [ ] Divergent fake fixtures pass through the actual message/log readers; real-host readback and agent/session selection are unchanged.
- [ ] The isolation gate catches a stray transcript-root join, fails on a stale allowlist entry, and does not flag config/output-dir joins.
- [ ] `ll-ctx-stats` empty discovery emits named-cause diagnostics to stderr; `--json` stdout parses.
- [ ] Unit-level fixture tests run without installed host CLIs; the spike directory is removed after promotion.

## Status

**Open** | Created: 2026-09-29 | Priority: P2
