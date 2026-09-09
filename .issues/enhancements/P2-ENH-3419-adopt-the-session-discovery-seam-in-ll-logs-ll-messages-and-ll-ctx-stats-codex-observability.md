---
id: ENH-3419
type: ENH
title: Adopt the session-discovery seam in ll-logs, ll-messages, and ll-ctx-stats
  (Codex observability)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T05:27:16Z'
labels:
- multi-host
- observability
blocked_by:
- FEAT-3417
blocks:
- ENH-3420
---

# ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and ll-ctx-stats (Codex observability)

## Summary

Split from FEAT-3417 on 2026-09-09. FEAT-3417 now delivers only the session-discovery seam (`session_store/sessions.py`: `SessionHandle`, `SessionEvent`, `detect_sessions`, `iter_events`, `list_workspaces`, `parse_claude_transcript`, `parse_codex_rollout`), the Codex fixtures and learning test, and retirement of the dead `~/.codex/projects/` probe. This issue is the second half: adopt that seam in the three log-derived CLIs (`ll-logs`, `ll-messages`, `ll-ctx-stats`) so a Codex session becomes observable through the same commands as a Claude Code session, and update the docs and the one FSM loop that depend on their current wording.

Split rationale: FEAT-3417's outcome confidence sat at 33/100 with change surface 0/25 across four consecutive `/ll:confidence-check` passes, and the issue's own trigger for splitting ("if change surface stays a blocker at implementation time") was met. Steps 1–3 of its original plan are self-contained and independently testable; steps 4–6 plus the Wiring Phase are this issue.

## Current Behavior

`ll-logs`, `ll-messages`, and `ll-ctx-stats` each reach directly for the Claude Code project folder via `get_project_folder`/`get_sessions_folder` with no `host=` argument, then glob `*.jsonl` and parse every record against the Claude Code schema:

- `scripts/little_loops/cli/messages.py` — `main_messages` calls `get_project_folder(cwd)` (line 173) and then `extract_user_messages(project_folder, ...)` (192) and `extract_commands(project_folder, ...)` (201–207).
- `scripts/little_loops/user_messages.py` — `extract_user_messages` (638) and `extract_commands` (721) take a bare `project_folder: Path`, glob `*.jsonl`, and parse via `_parse_user_record` (858). `extract_user_messages` defaults to `include_agent_sessions=True`.
- `scripts/little_loops/cli/ctx_stats.py` — `_compute_cache_rate_from_jsonl(cwd)` (342, called from `main_ctx_stats` at 753) calls `get_sessions_folder(cwd)`, picks the newest non-`agent-*` file, and sums Claude-shaped `message.usage` keys.
- `scripts/little_loops/cli/logs.py` — 11 un-hosted `get_project_folder(...)` calls across 6 functions: `_collect_sequences` (653, 658, 667), `_cmd_sequences` (693), `_cmd_extract` (774, 783), `_collect_failure_clusters` (1353, 1358, 1367; second caller `_cmd_fleet_review` at 2843), `_cmd_scan_failures` (1554), `_cmd_eval_export` (2032). Plus the `--all` enumeration path (~line 196) that walks `host_layout_for(host).projects_root.iterdir()` — which FEAT-3417 sets to `None` for Codex, so `extract --all` / `scan-failures --all` yield nothing for Codex until this issue lands.

No `--host` flag exists on any of the three CLIs (grep-confirmed). The only ambient host source is `LL_HOOK_HOST`, which is exported only inside host hook adapters (`hooks/adapters/*/`), never in a user's interactive shell.

## Expected Behavior

The three CLIs obtain sessions through `detect_sessions(cwd, host=None)` (union across hosts, newest first — FEAT-3417 § Decided: host resolution) and iterate records via `iter_events`, rather than resolving a folder and globbing. A user who ran a Codex session in a workspace sees it in `ll-messages` and `ll-logs` output with no flag; an optional `--host` flag on all three CLIs narrows to one host. Claude Code output for every existing test is unchanged, including `include_agent_sessions=True` behaviour (handles carry an agent discriminator, so `extract_user_messages` passes `include_agents=True` through).

`ll-ctx-stats` under Codex either reports a cache rate from a Codex-only usage reader or prints "cache rate: unavailable for codex sessions" — never silently computes zero from Claude-shaped keys.

## Motivation

`ll-adapt --host codex` ships today, so little-loops writes artifacts for Codex and then cannot read a single Codex session back. Goal 6's dataset export (`ll-logs eval-export`) and goal 7's quality rollups (`ll-logs scan-failures`, `fleet-review`) silently cover one host while claiming to generalize. FEAT-3417 builds the seam; without this issue nothing consumes it.

## Scope Boundaries

- **In scope**: rewiring `ll-logs`, `ll-messages`, `ll-ctx-stats` (and `user_messages.py`'s `extract_user_messages`/`extract_commands`) onto `detect_sessions`/`iter_events`/`list_workspaces`; adding a `--host` flag to all three CLIs; the Codex `user_message`/`response_item` dedup logic in `extract_user_messages`; the `ll-ctx-stats` Codex cache-rate reader (or its "unavailable" fallback); the `hooks/session_start.py:162` host injection; the docs sweep listed under Integration Map.
- **Out of scope**: adding Codex-native equivalents of the Claude-schema-coupled content functions in `cli/logs.py` (`_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error`) — Codex events flow through the lifecycle but produce no ll-signal matches until a follow-up issue adds them (decided in FEAT-3417). qwen/gemini/omp support — `detect_sessions` gains Codex only here; wiring the other hosts into the seam (or unifying it with `HostLayout`) is ENH-3420. The `transcript_path`-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`) stay untouched, per FEAT-3417's decided boundary.

## Proposed Solution

Per-consumer, following FEAT-3417's "seam is refused on content" rule (lifecycle is shared; content interpretation stays per-host):

1. **`user_messages.py`**: `extract_user_messages` and `extract_commands` gain a `handles: list[SessionHandle]` (or `cwd`+`host`) entry point and iterate `iter_events(handle)`; the Claude branch keeps `_parse_user_record` byte-for-byte on `event.payload`. The Codex branch maps `event_msg.payload.type == "user_message"` → user text (`payload.message`); `response_item` messages with `role == "user"` are the same text echoed into model input and are deduplicated against it, not double-counted. Unknown `event_msg` types (e.g. `turn_aborted`, observed in the corpus) pass through untouched. Keep a thin `project_folder: Path` compatibility wrapper only if a test patches it directly; otherwise update the sole caller `cli/messages.py`.
2. **`cli/ctx_stats.py`**: `_compute_cache_rate_from_jsonl` picks the newest handle across hosts; for `host == "codex"` dispatch to a Codex-only reader if FEAT-3417's fixture capture found per-turn usage in the rollout (expected keys `cached_input_tokens`/`cache_write_input_tokens`/`input_tokens` per `docs/reference/HOST_COMPATIBILITY.md` `[^tok-codex]`), else return `None` and print the "unavailable" line. The outcome is recorded in the reader's docstring and in HOST_COMPATIBILITY.md.
3. **`cli/logs.py`**: route the 11 call sites through `detect_sessions`; route the `--all` enumeration through `list_workspaces(host)`. The Claude-schema-coupled content functions (`_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error`) stay Claude-Code-only in this issue (decided in FEAT-3417); Codex events flow through the lifecycle but produce no ll-signal matches until a follow-up adds Codex-native equivalents. Build on the existing partial precedent: `_has_ll_activity` (97), `_extract_cwd_from_project` (134), `_extract_ll_event_streams` (261) already take `layout: HostLayout | None`.
4. **`hooks/session_start.py:162`**: pass `host=event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` to `get_project_folder(cwd)` — the same expression already computed at line 178 for the backfill worker.
5. **`--host` flag**: add to `ll-logs`, `ll-messages`, `ll-ctx-stats` argparse; default `None` (union). Same vocabulary as `get_project_folder`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` (`main_messages`, lines 173, 192, 201–207)
- `scripts/little_loops/user_messages.py` (`extract_user_messages` 638, `extract_commands` 721)
- `scripts/little_loops/cli/ctx_stats.py` (`_compute_cache_rate_from_jsonl` 342, `main_ctx_stats` 753)
- `scripts/little_loops/cli/logs.py` (module docstring line 1; the 6 functions / 11 call sites above; the `projects_root` walk near 196; `_cmd_fleet_review` 2843)
- `scripts/little_loops/hooks/session_start.py:162`
- `.loops/ll-logs-telemetry-digest.yaml:66` — greps `ll-logs scan-failures` stderr for the literal `"No session project folder found"` to distinguish `FAILURES_NO_DATA` from `FAILURES_ERROR`. Keep that exact string in the no-sessions branch, or update the loop in the same change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` (module docstring lines 16, 18) — "Claude Code logs" / "~/.claude/projects/" framing, same sweep as the doc updates below.
- Note (caller-suitability, `cli/ctx_stats.py`): this issue's Program Design states `_compute_cache_rate_from_jsonl(handles: list[SessionHandle]) -> float | None`, but the function currently returns `dict[str, Any] | None` (keys `cache_read`, `cache_write`, `uncached`, `hit_rate_pct`), consumed by this same file's text renderer (~473-477) and JSON renderer (~598-601, emitting `cache_hit_rate_pct`/`cache_read_tokens`/`cache_write_tokens`/`uncached_tokens`). Preserve the dict shape (update the Program Design signature instead) or update both consumption sites in the same change — do not ship a bare `float | None` without touching lines 473-477 and 598-601.

### Dependent Files (must not change)
- `get_project_folder`/`get_sessions_folder`'s `Path | None` contract stays for `session_log.py:159-212`, `fsm/continuity.py:43`, `cli/session.py:664,702,718` (tests lock it: `test_session_log.py:26-95,384-458`, `test_fsm_continuity.py:53,61,82`, `test_ll_session.py:704`).
- transcript_path-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`) stay separate — decided out of scope in FEAT-3417.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/writers.py`'s `_CLAUDE_MD_DESC_OVERRIDES` (lines 282-288) deliberately keeps `"ll-messages": "Extract user messages from Claude Code logs"` / `"ll-logs": "... from Claude project logs"` for `.claude/CLAUDE.md` output specifically (the generic `_LL_COMMANDS` table at line 223 is already host-generic). This override is regression-test-locked by `test_init_core.py::test_claude_md_keeps_claude_specific_lines` (~1841-1845, asserts `"Claude Code logs" in content`) alongside `test_content_is_host_generic` (~1833-1839, asserts `AGENTS.md` never contains `"Claude"`). This is intentional design (`.claude/CLAUDE.md` is inherently Claude Code's own config) — the docs sweep in this issue must NOT touch this override or its test.

### Downstream consumers to verify
- `/ll:loop-suggester --from-sequences` (`commands/loop-suggester.md:740-768`, `skills/ll-loop-suggester/SKILL.md:303-309,408,631,650`) shells out to `ll-logs sequences --json`; confirm Codex-sourced sessions appear once `_collect_sequences` is rewired.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/fleet-loop-improve.yaml:78,80` — shells out to `ll-logs fleet-review --all --existing-only --exclude-project . | tail -n 1` and derives a `.json` sidecar path from the returned `.md` path; depends on `_cmd_fleet_review`'s (already-listed, `cli/logs.py:2843`) current stdout contract surviving the rewire.
- `scripts/little_loops/loops/examples-miner.yaml:38` and `scripts/little_loops/loops/lib/cli.yaml:86-94` (`ll_messages` fragment) — both shell out to `ll-messages --stdout` with no `--host` (default/union path); should be unaffected since Claude Code output must stay byte-identical, but re-run once the seam lands to confirm.
- `scripts/little_loops/loops/sft-corpus.yaml:53` — `ll-messages --sft-format --reader db` routes through `history.db`, not the JSONL/`get_project_folder` path being rewired — confirmed NOT affected.

### Tests
- `scripts/tests/test_ll_logs.py` — `TestSequences`/`TestArgumentParsingSequences` (797-1339), `TestExtract` (1547-2127), `TestScanFailures` (2924-4155), `TestEvalExport*` (4437-4841). Every `_make_project_dir` helper hard-codes the Claude layout and patches `Path.home`; add `LL_HOOK_HOST=codex` / `--host codex` variants using FEAT-3417's committed fixtures under `scripts/tests/fixtures/codex/`.
- `scripts/tests/test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` (676-974) — add `test_resolves_codex_*_transcript` beside the qwen (937) / gemini (974) pairs.
- `scripts/tests/test_user_messages.py` — add Codex content tests (user_message extraction, response_item dedup) and an `include_agent_sessions=True` regression through the new path.
- Existing Claude Code tests in all three files must pass unmodified except where they patch `get_project_folder` directly.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` — `TestMainMessagesIntegration` (~651) and `TestMainMessagesAdditionalCoverage` (~1815), 18 call sites patching `little_loops.user_messages.get_project_folder`/`extract_user_messages`/`extract_commands` with a `MagicMock` — not in the original known-test list; will not break outright but need extended assertions to cover host-threading.
- `scripts/tests/test_cli_messages.py` — entirely dedicated to `main_messages()` flag interactions, also patches `little_loops.user_messages.get_project_folder`; same update needed as `test_cli.py` above.
- `scripts/tests/test_bug_3216_telemetry_digest_invocations.py` — regex-extracts every `ll-logs` invocation out of `.loops/ll-logs-telemetry-digest.yaml` and feeds the argv into `cli/logs.py`'s real argparse parser; run after adding `--host` to confirm the parser surface still accepts the loop's existing invocations.
- Test gap: no existing test asserts that `hooks/session_start.py:162`'s `get_project_folder(cwd)` call receives a `host=` kwarg (all patches use a `*a, **kw`-swallowing lambda). Add a capturing-stub variant of `TestSessionStartHookPassesHost` (`test_enh_3166_qwen_normalizer.py:577-638`) that asserts on the `get_project_folder` call's kwargs, not just the backfill-worker argv.
- Test gap: no `--host` flag-parsing test exists yet for `ll-logs`/`ll-messages`/`ll-ctx-stats`. Model new tests on `test_ll_session.py::TestBackfillArgs::test_backfill_host_choices_list` (41-61), which locks the choices list + rejects an invalid host via `pytest.raises(SystemExit)`.

### Documentation
- `docs/reference/CLI.md` — `### ll-logs` ("from Claude Code session logs") and `### ll-messages` (line ~3552, same framing); document the new `--host` flag on all three.
- `docs/guides/HISTORY_SESSION_GUIDE.md` (~503), `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` (10, 81, 429-454), `docs/guides/EXAMPLES_MINING_GUIDE.md` (146, 421) — remove or qualify Claude-Code-only framing.
- `docs/reference/HOST_COMPATIBILITY.md` — record the `ll-ctx-stats` Codex cache-rate outcome.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3424-3629,5461-5462` — full signature/docstring/usage-example documentation for `extract_user_messages`, `get_project_folder`, `get_sessions_folder`, showing the pre-change `project_folder: Path` parameter; update alongside the code signature change.
- `scripts/little_loops/cli/__init__.py` module docstring (lines 16, 18) — hardcodes `"ll-messages: Extract user messages from Claude Code logs"` and `"ll-logs: ... from ~/.claude/projects/"`; update this source-level docstring too, not just `docs/reference/CLI.md`.
- `scripts/little_loops/loops/lib/cli.yaml:86-94`'s `ll_messages` fragment description text ("Extract user messages from **Claude Code session logs**") carries the same Claude-Code-only framing as `docs/reference/CLI.md` and should be updated in the same sweep.
- Convention note: `docs/reference/CLI.md`'s shared "Common Flags" table does not list `--host` despite three existing consumers (`ll-session`, `ll-advise`, `ll-adapt`) — document the new `--host` flag per-tool-section (matching current practice), not by adding it to the shared table.

## Program Design

### Types

- `SessionHandle` (`session_store/sessions.py`, FEAT-3417) — discovered-session identity, carries `host` and the agent discriminator
- `SessionEvent` (`session_store/sessions.py`, FEAT-3417) — one record, `payload` kept host-native (no cross-host normalization)

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None) -> list[SessionHandle]` (FEAT-3417, existing)
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` (FEAT-3417, existing)
- `extract_user_messages(handles: list[SessionHandle], limit: int | None = None, since: datetime | None = None, include_agent_sessions: bool = True, include_response_context: bool = False) -> list[UserMessage]` — replaces the current `project_folder: Path` parameter (`user_messages.py:638`)
- `_compute_cache_rate_from_jsonl(handles: list[SessionHandle]) -> float | None` — replaces the current `cwd: Path` parameter (`cli/ctx_stats.py:342`)

### Call Path

`main_messages` (`cli/messages.py:13`) -> `detect_sessions(cwd, host=args.host)` -> `extract_user_messages(handles, ...)` -> `iter_events(handle)` -> `_parse_user_record(event.payload)` (Claude) / Codex `event_msg.payload` mapping (new)

## Implementation Steps

1. Confirm FEAT-3417 has landed: `from little_loops.session_store import detect_sessions, iter_events, list_workspaces` imports, fixtures exist under `scripts/tests/fixtures/codex/`, and the fixture README records whether the interactive rollout carries per-turn usage (drives step 4).
2. Add `--host` (default `None`) to the three CLIs' argparse.
3. Rewire `user_messages.py` (`extract_user_messages` + `extract_commands`) and `cli/messages.py`; add Codex user_message/dedup handling; run `test_user_messages.py` unmodified.
4. Rewire `cli/ctx_stats.py`; implement either the Codex usage reader or the "unavailable" branch; add the Codex test pair.
5. Rewire `cli/logs.py` (11 call sites + `--all` via `list_workspaces` + `_cmd_fleet_review`); preserve the `"No session project folder found"` string or update the loop YAML; run `test_ll_logs.py` unmodified, then add Codex fixture variants.
6. `hooks/session_start.py:162` host injection.
7. Docs sweep (CLI.md, three guides, HOST_COMPATIBILITY.md); verify `/ll:loop-suggester --from-sequences` against a workspace with a Codex session.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolve the `_compute_cache_rate_from_jsonl` return-type mismatch between this issue's Program Design (`float | None`) and the function's actual `dict[str, Any] | None` shape consumed by `cli/ctx_stats.py`'s text renderer (~473-477) and JSON renderer (~598-601) — preserve the dict or update both render sites in the same change.
- Update `scripts/little_loops/cli/__init__.py` module docstring (lines 16, 18) and `scripts/little_loops/loops/lib/cli.yaml`'s `ll_messages` fragment description (86-94) alongside the `docs/reference/CLI.md`/guides sweep — same "Claude Code logs" framing lives here too.
- Do NOT touch `scripts/little_loops/init/writers.py`'s `_CLAUDE_MD_DESC_OVERRIDES` (282-288) or its regression test `test_init_core.py::test_claude_md_keeps_claude_specific_lines` — that Claude-specific wording is intentional and test-locked, unrelated to this issue's Claude-Code-only-framing removal.
- Add `--host` argparse tests for `ll-logs`/`ll-messages`/`ll-ctx-stats` modeled on `test_ll_session.py::TestBackfillArgs::test_backfill_host_choices_list` (41-61); add a capturing-stub test asserting `hooks/session_start.py:162` threads `host=` into `get_project_folder`, extending `test_enh_3166_qwen_normalizer.py`'s `TestSessionStartHookPassesHost` pattern (577-638).
- Update `scripts/tests/test_cli.py` (`TestMainMessagesIntegration`/`TestMainMessagesAdditionalCoverage`) and `scripts/tests/test_cli_messages.py`'s mocked `get_project_folder`/`extract_user_messages`/`extract_commands` call sites for the new parameter shape; re-run `test_bug_3216_telemetry_digest_invocations.py` after adding `--host` to confirm the loop-YAML-derived argv still parses.
- Verify `scripts/little_loops/loops/fleet-loop-improve.yaml`, `examples-miner.yaml`, and `loops/lib/cli.yaml` still work post-rewire (no code change expected — default/union path).

## Impact

- **Priority**: P2 — this is the half that makes FEAT-3417 user-visible.
- **Effort**: Medium — mechanical rewire at ~14 call sites plus three per-site judgment calls (ctx_stats usage reader, messages dedup, session_start host injection).
- **Risk**: Medium — touches read paths automation already depends on; mitigated by the "existing tests pass unmodified" gate and the seam's Claude parser being the existing per-line read lifted verbatim.
- **Breaking Change**: No — Claude Code behaviour preserved; Codex additive; `--host` optional.

## Acceptance Criteria

- `ll-logs`, `ll-messages` (user messages **and** commands), and `ll-ctx-stats` obtain sessions via `detect_sessions`/`iter_events` and never call `get_project_folder`/`get_sessions_folder` for session enumeration; `ll-logs --all` enumerates workspaces via `list_workspaces`.
- With no flag, a workspace containing both a Claude Code and a Codex session shows both in `ll-messages` and `ll-logs sequences`; `--host codex` / `--host claude-code` narrows to one.
- Claude Code output for every existing test in `test_ll_logs.py`, `test_user_messages.py`, `test_cli_ctx_stats.py` is unchanged; `include_agent_sessions=True` still includes `agent-*` sessions.
- `ll-ctx-stats` under Codex reports a Codex-derived cache rate or prints "cache rate: unavailable for codex sessions"; never a zero computed from Claude-shaped keys.
- `.loops/ll-logs-telemetry-digest.yaml`'s `scan_failures` state still distinguishes no-data from error (string preserved or loop updated in the same change).
- `docs/reference/CLI.md` and the three guides no longer frame `ll-logs`/`ll-messages` as Claude-Code-only; `--host` is documented.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-09T14:51:24 - `8e56ec89-cd99-46e0-b932-f07e5ea9315c.jsonl`
- `/ll:refine-issue` - 2026-09-09T14:01:26 - `fc9ca416-ac94-40a4-8082-2af225a0464c.jsonl`
- `/ll:format-issue` - 2026-09-09T13:22:13 - `94cf9e94-a0b2-480c-8238-e366777de95e.jsonl`
