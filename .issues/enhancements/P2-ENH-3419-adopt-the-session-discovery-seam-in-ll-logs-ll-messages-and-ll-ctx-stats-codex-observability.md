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
blocked_by: []
relates_to:
- ENH-3422
- FEAT-3417
- ENH-3420
missing_artifacts: true
verify_verdict: PROPOSAL_UNSOUND
confidence_score: 90
outcome_confidence: 45
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
---

# ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and ll-ctx-stats (Codex observability)

## Summary

Split from FEAT-3417 on 2026-09-09. FEAT-3417 has landed (`scripts/little_loops/session_store/sessions.py`: `SessionHandle`, `SessionEvent`, `detect_sessions`, `iter_events`, `list_workspaces`, `parse_claude_transcript`, `parse_codex_rollout`; Codex fixtures under `scripts/tests/fixtures/codex/`; `codex-rollout` learning test proven on 0.152.1; dead `~/.codex/projects/` probe retired). This issue is the consumer half: adopt that seam in the three log-derived CLIs (`ll-logs`, `ll-messages`, `ll-ctx-stats`) so a Codex session becomes observable through the same commands as a Claude Code session, and update the docs and the one FSM loop that depend on their current wording.

**Sequencing (2026-09-09 review, updated 2026-09-09):** ENH-3420 has landed (status `done`) — `_REGISTERED_HOSTS` (`sessions.py:268-277`) now lists all 8 hosts (`claude-code`, `codex`, `opencode`, `pi`, `kimi-code`, `qwen`, `gemini`, `omp`), so the sequencing concern this paragraph originally raised (rewiring before qwen/gemini/omp were registered would silently regress `test_cli_ctx_stats.py:909,941` / `test_enh_3166_qwen_normalizer.py:277-296`) is resolved; `FEAT-3417` and `ENH-3420` have moved from `blocked_by` to `relates_to` accordingly (both `done`). ENH-3422 (backfill half) remains independent of this issue.

## Current Behavior

`ll-logs`, `ll-messages`, and `ll-ctx-stats` each reach directly for the host project folder via `get_project_folder`/`get_sessions_folder` (host resolved from `LL_HOOK_HOST`, default `claude-code` — `user_messages.py:395,442`), then glob `*.jsonl` and parse every record against the Claude Code schema:

- `scripts/little_loops/cli/messages.py` — `main_messages` calls `get_project_folder(cwd)` (line 173) and then `extract_user_messages(project_folder, ...)` (192) and `extract_commands(project_folder, ...)` (201–207).
- `scripts/little_loops/user_messages.py` — `extract_user_messages` (639) and `extract_commands` (722) take a bare `project_folder: Path`, glob `*.jsonl`, and parse via `_parse_user_record`. `extract_user_messages` defaults to `include_agent_sessions=True`. A **third** globbing function, `extract_conversation_turns` (1028, `*.jsonl` glob at 1096), is called from `main_messages` for `--sft-format` (`cli/messages.py:250`) with the same `project_folder`; its `--reader auto|jsonl` modes read JSONL directly (only `--reader db` bypasses it).
- `scripts/little_loops/cli/ctx_stats.py` — `_compute_cache_rate_from_jsonl(cwd) -> dict[str, Any] | None` (342, called from `main_ctx_stats` at ~753) calls `get_sessions_folder(cwd)` (355), picks the newest non-`agent-*` file, sums Claude-shaped `message.usage` keys (`cache_read_input_tokens`, `cache_creation_input_tokens`, `input_tokens`), and returns `{cache_read, cache_write, uncached, hit_rate_pct}`, consumed by the text renderer (~473-477) and JSON renderer (~598-601).
- `scripts/little_loops/cli/logs.py` — 11 un-hosted `get_project_folder(...)` calls across 6 functions: `_collect_sequences` (653, 658, 667), `_cmd_sequences` (693), `_cmd_extract` (774, 783), `_collect_failure_clusters` (1353, 1358, 1367; second caller `_cmd_fleet_review` at ~2843), `_cmd_scan_failures` (1554), `_cmd_eval_export` (2040). Every one of them then globs `*.jsonl` **excluding `agent-*`** (725, 797, 1375, 2050). Plus the `--all` enumeration in `discover_all_projects` (166-215) that walks `host_layout_for(host).projects_root.iterdir()` — `None` for Codex (`writers.py:2591`), so `ll-logs discover` never lists a Codex workspace. `discover_all_projects` also **filters to workspaces with ll activity** (`_has_ll_activity`, 213) and has **seven** consumers, not two: `_collect_sequences` (664), `_cmd_extract` (780), `_cmd_dead_skills` (1075), `_collect_failure_clusters` (1364), `_cmd_stats` (1639), `_cmd_loop_fleet` (2335), `_cmd_fleet_review` (2782), plus the `discover` subcommand itself (3235). `_collect_sequences` also resolves a `HostLayout` from `LL_HOOK_HOST` directly (649).

**What this issue does and does not deliver for Codex under `--all` (review 2026-09-09):** because the ll-signal content functions stay Claude-only (§ Scope Boundaries), a Codex workspace has no ll activity under `_is_ll_relevant` and so `extract --all` / `scan-failures --all` / `sequences --all` will still surface nothing Codex-sourced after this issue lands. What lands here is Codex visibility in `ll-messages`, `ll-ctx-stats`, `ll-logs discover`, and the shared session lifecycle every `ll-logs` path iterates; Codex ll-signal mining is the follow-up issue named in § Scope Boundaries.

No `--host` flag exists on any of the three CLIs (grep-confirmed). The only ambient host source is `LL_HOOK_HOST`, which is exported only inside host hook adapters (`hooks/adapters/*/`), never in a user's interactive shell.

`detect_sessions` (`sessions.py:253-283`) takes `host: str | None = None, *, include_agents: bool = False, limit, home`; `host=None` is a pure union across `_REGISTERED_HOSTS` and does **not** consult `LL_HOOK_HOST`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- **Line-citation correction (`user_messages.py`)**: `get_project_folder` is defined at `user_messages.py:373` and `get_sessions_folder` at `user_messages.py:422` (this section's citation of `395,442` has drifted — both functions already accept a `host: str | None = None` kwarg, defaulting via `os.environ.get("LL_HOOK_HOST", "claude-code")` when unset).
- **Zero production adoption confirmed**: `detect_sessions`/`iter_events`/`list_workspaces` (`session_store/sessions.py`) have no production callers today — only `scripts/tests/test_session_discovery.py` and internal recursion inside `sessions.py` itself use them. Every consumer named above remains on the pre-seam path, confirming this issue's premise.
- **`_REGISTERED_HOSTS` now covers all 8 hosts** (`sessions.py:268-277`: `claude-code`, `codex`, `opencode`, `pi`, `kimi-code`, `qwen`, `gemini`, `omp`) — ENH-3420 (`status: done`) landed this. See Summary's Sequencing note.
- **Fail-soft contract to preserve**: every layer in the current path (`get_project_folder`, `get_sessions_folder`, `extract_user_messages`/`extract_commands`, `detect_sessions`, `iter_events`, `_compute_cache_rate_from_jsonl`) returns `None`/`[]`/an empty generator rather than raising, on a missing folder, unknown host, malformed JSONL, or `OSError`. The rewire must not turn any of these into an exception path.
- **`docs/reference/HOST_COMPATIBILITY.md`'s per-host session-log table** (`## State directory`, ~line 511; row "Session log readable via `detect_sessions()`" ~line 532) already marks all 7 non-`claude-code` hosts ✓, with `[^tok-codex]` (line 313, `codex exec --json` `turn.completed` source) and a second `[^codexsessions]` footnote (`detect_sessions`/`parse_codex_rollout` rollout-file source) already in place. The docs sweep in this issue extends/updates these two existing anchors rather than creating new ones.

## Expected Behavior

The three CLIs obtain sessions through `detect_sessions(cwd, host=<resolved>)` and iterate records via `iter_events`, rather than resolving a folder and globbing. Host resolution at every CLI entry point is:

```
host = args.host or os.environ.get("LL_HOOK_HOST") or None   # None = union across all registered hosts
```

so a hook-adapter context (which exports `LL_HOOK_HOST`) keeps today's single-host behaviour, an interactive user with no flag sees every host's sessions for the workspace (a Codex session appears in `ll-messages` and `ll-logs` output with no flag), and `--host` narrows explicitly. `detect_sessions` itself stays env-unaware (FEAT-3417 decided).

Claude Code output for every existing test is unchanged, including agent handling: `extract_user_messages`/`extract_commands` pass `include_agents=include_agent_sessions` (default `True`); every `cli/logs.py` path and `_compute_cache_rate_from_jsonl` pass `include_agents=False` (they skip `agent-*` today).

`ll-ctx-stats` under Codex reports a cache rate derived from the rollout's `token_count` events (§ Proposed Solution step 2) — never a zero computed from Claude-shaped keys, and never a value that double-counts cached tokens.

## Motivation

`ll-adapt --host codex` ships today, so little-loops writes artifacts for Codex and then cannot read a single Codex session back. Goal 6's dataset export (`ll-logs eval-export`) and goal 7's quality rollups (`ll-logs scan-failures`, `fleet-review`) silently cover one host while claiming to generalize. FEAT-3417 built the seam and ENH-3420 completes its host coverage; without this issue nothing user-facing consumes it.

## Scope Boundaries

- **In scope**: rewiring `ll-logs`, `ll-messages`, `ll-ctx-stats` (and `user_messages.py`'s `extract_user_messages`/`extract_commands`/`extract_conversation_turns`) onto `detect_sessions`/`iter_events`/`list_workspaces`; adding a `--host` flag to all three CLIs with the resolution rule above; the Codex user-turn extraction in `extract_user_messages`; the `ll-ctx-stats` Codex cache-rate reader; the `hooks/session_start.py:162` host injection; the docs sweep listed under Integration Map.
- **`extract_commands` is Claude-Code-only in this issue.** It parses Claude `tool_use` blocks for `Bash` (`user_messages.py:722-745`). The Codex equivalent is `response_item.payload.type == "custom_tool_call"` with `name: "exec"` (fixture `rollout-interactive.jsonl`, 3 occurrences), whose `input` is a JS snippet rather than a shell string — a content-level mapping that belongs with the other Codex-native content functions below. Codex handles flow through `extract_commands` and yield no `CommandRecord`s.
- **Out of scope**: Codex-native equivalents of the Claude-schema-coupled content functions in `cli/logs.py` (`_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error`) — Codex events flow through the lifecycle but produce no ll-signal matches until a follow-up issue adds them (decided in FEAT-3417). Registering the remaining hosts in `detect_sessions` (ENH-3420) and the backfill/`HostLayout` shrink (ENH-3422). The `transcript_path`-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`) stay untouched, per FEAT-3417's decided boundary.

## Proposed Solution

Per-consumer, following FEAT-3417's "seam is refused on content" rule (lifecycle is shared; content interpretation stays per-host). For qwen/gemini/omp handles, `iter_events` yields the host's existing-normalizer output, and opencode/pi are Claude-shaped on disk (ENH-3420's payload rule), so the Claude branches below apply to those five hosts unchanged. kimi-code handles yield **host-native** `wire.jsonl` events (kimi has no normalizer — corrected 2026-09-09), so kimi flows through the lifecycle like codex and produces no Claude-schema matches until a follow-up adds a kimi content mapping.

1. **`user_messages.py`**: `extract_user_messages` and `extract_commands` gain a `handles: list[SessionHandle]` entry point and iterate `iter_events(handle)`; the Claude branch keeps `_parse_user_record` byte-for-byte on `event.payload`. **Codex user-turn mapping (corrected 2026-09-09 against the 0.152.1 fixtures):** neither committed fixture contains any `event_msg` of type `user_message`; the user's prompt lives only in `response_item` events with `payload.type == "message"` and `payload.role == "user"`, text under `payload.content[].text` (`type: "input_text"`). That is the primary source. Two user-role messages per turn must be filtered out, not counted: the host-injected `<environment_context>...</environment_context>` block (first user-role message in `rollout-interactive.jsonl`) and any `role == "developer"` message. If an older CLI version also emits `event_msg.payload.type == "user_message"` (observed in the pre-0.152.1 corpus), deduplicate it against the `response_item` text rather than double-counting; it is the secondary source, not the primary. Unknown `event_msg` types (`task_started`, `task_complete`, `item_completed`, `turn_aborted`, `token_count`) pass through untouched. **Codex → `UserMessage` field mapping (review 2026-09-09):** `content` = joined `input_text` texts; `timestamp` = the envelope `timestamp` (same ISO-Z parse as Claude, file mtime fallback); `session_id` = `handle.session_id`; `uuid` = `payload.id` (`msg_…`); `cwd` = the `session_meta` payload's `cwd` if seen, else `str(handle.cwd)`; `git_branch` = `None`; `is_sidechain` = `False`. Keep a thin `project_folder: Path` compatibility wrapper only if a test patches it directly; otherwise update the sole caller `cli/messages.py`.
   **`extract_conversation_turns` (1028) is rewired in the same step** — it is the third JSONL-globbing function `main_messages` feeds `project_folder` (for `--sft-format` with `--reader auto|jsonl`, `cli/messages.py:250`). Its JSONL branch takes `handles` and iterates `iter_events`, with the same `include_agent_sessions` → `include_agents` mapping and the existing mtime-based `since` pre-filter re-expressed on `handle.updated_at`; the `--reader db` branch is untouched. `_extract_turn_pairs` stays Claude-shaped (Codex handles yield no windows in this issue). Without this, the AC's "never call `get_project_folder` for session enumeration" cannot be met because `main_messages` would still need a folder for the SFT path.
2. **`cli/ctx_stats.py`**: `_compute_cache_rate_from_jsonl` picks the newest non-agent handle for the resolved host (or across hosts when `None`) via `detect_sessions(cwd, host, include_agents=False, limit=1)`. **The seam is used only to pick the file (review 2026-09-09):** for every non-codex host, keep today's raw per-line reader (`ctx_stats.py:381-403`) on `handle.path` — do **not** route usage through `iter_events`. The qwen/gemini normalizers strip `message.usage`: `normalize_qwen_record` (`session_store/qwen.py:83-92`) replaces `message` with `{role, content}` and drops any record lacking `parts`, and `normalize_gemini_session` (`session_store/gemini.py:65-78`) skips line 1 as a header and yields only `user`/`gemini` types. The existing qwen/gemini tests (`test_cli_ctx_stats.py:909,941`) write Claude-shaped `message.usage` records into the qwen/gemini dirs and only pass because the raw reader sees them; through `iter_events` they yield nothing and the "pair passes unmodified" AC fails. Consequence to record in the docstring: real qwen/gemini/omp cache rates are unreachable through the normalizers today, so a native qwen/gemini usage reader stays a follow-up. `iter_events` is used for the codex branch only. **Codex reader is decided, not conditional** — `scripts/tests/fixtures/codex/README.md` § Per-turn-usage finding confirms `event_msg.payload.type == "token_count"` records with `payload.info.total_token_usage` / `payload.info.last_token_usage` (4 in the interactive fixture, 1 in exec). Two semantics differ from Claude and must be handled:
   - `total_token_usage` is **cumulative** across the session; take the last `token_count` event's `total_token_usage`, or equivalently sum `last_token_usage` across events. Do not sum `total_token_usage`.
   - Codex `input_tokens` is **inclusive** of cached and cache-write tokens (fixture: `input_tokens=14002`, `cached_input_tokens=0`, `cache_write_input_tokens=13999`; next turn `21854 = 13999 + 7852 + 3`). So `uncached = input_tokens - cached_input_tokens - cache_write_input_tokens`, `cache_read = cached_input_tokens`, `cache_write = cache_write_input_tokens`. Applying the Claude formula's denominator verbatim would count cached tokens twice.
   The return shape keeps the same four keys, so the text renderer (~473-477) and JSON renderer (~598-601) are untouched. **Add one additive key, `host`** (the `handle.host` the rate was read from): under the union default, `limit=1` picks the newest session across hosts, so a workspace with both a Claude Code and a Codex session silently switches source between runs; the JSON renderer should surface which host it was (text renderer may ignore it). Record the key semantics in the reader's docstring and in `docs/reference/HOST_COMPATIBILITY.md` next to `[^tok-codex]` (which documents the complementary `codex exec --json` `turn.completed` source).
3. **`cli/logs.py`**: route the 11 call sites through `detect_sessions(..., include_agents=False)`; route the `--all` enumeration in `discover_all_projects` through `list_workspaces(host, existing_only=...)` (the function already has an `existing_only` kwarg, 167). **`_extract_ll_event_streams` and line 649 (review 2026-09-09):** `_extract_ll_event_streams` (`logs.py:261-290`) still takes a `project_folder` and globs `layout.session_glob`, so routing `_collect_sequences` through `detect_sessions` alone does not rewire the sequences path. Give it a handles-based entry point — `_extract_ll_event_streams(handles: list[SessionHandle], *, cutoff, until)` iterating `iter_events(h)` and applying `_extract_tool_name(e.payload)` — and delete the `layout=` pass-through in `_collect_sequences` together with `host_layout_for(LL_HOOK_HOST)` at 649: `iter_events` already applies the qwen/gemini/omp normalizers, and "the same resolved host" is undefined when the host resolves to `None` (union). Same treatment for `_has_ll_activity` (97) if it is reused for the filter below. **Three `discover_all_projects` semantics to preserve explicitly (review 2026-09-09):**
   - **The ll-activity filter stays.** `list_workspaces` returns every workspace a host has ever recorded; `discover_all_projects` today returns only those where `_has_ll_activity` is true (213). Re-apply it per workspace as `any(_is_ll_relevant(e.payload) for h in detect_sessions(ws, host, include_agents=False) for e in iter_events(h))` (or an equivalent early-exit walk) so `discover`/`extract --all`/`scan-failures --all` output does not widen. Dropping it would be a visible behaviour change in `ll-logs discover` and a silent widening of the `history.db` candidate list in `stats`/`dead-skills`.
   - **The `list_workspaces → detect_sessions(ws)` round-trip must tolerate an unresolved recorded `cwd` (review 2026-09-09).** `_detect_claude_sessions` (`sessions.py:245`) and `_project_folder_for_layout_host` (`sessions.py:339`) encode only `cwd.resolve()`, while `list_workspaces` returns the `cwd` field as recorded. On macOS `tempfile`/`tmp_path` dirs live under `/var/...` which resolves to `/private/var/...`, and `test_ll_logs.py:109`'s `TestDiscover._make_project_dir` encodes the **unresolved** path and records an unresolved `cwd` — so the filter finds no sessions, the two positive discover tests (`test_discover_finds_project_via_queue_operation`, `..._dotted_worktree_subpath`) fail, and `test_discover_skips_non_ll_project` passes for the wrong reason. Fix in the seam, not the fixture: probe **both** spellings (resolved first, then `str(cwd)` as recorded) in `_detect_claude_sessions` and `_project_folder_for_layout_host`, mirroring what the codex path already does (`sessions.py:131` DB match, `sessions.py:174` scan match) and the cwd-spelling promise in `SessionHandle`'s docstring. Add a `test_session_discovery.py` case: a Claude project dir encoded from an unresolved symlinked cwd is found by `detect_sessions(unresolved_cwd, "claude-code", home=...)`. `get_project_folder` (contract-locked, § Dependent Files) is untouched.
   - **Union rule for `host=None`.** `list_workspaces(host: str)` is not Optional; when the resolved host is `None`, iterate `_REGISTERED_HOSTS`, concatenate, and dedupe on the resolved cwd (a workspace with both Claude Code and Codex sessions appears once). Return type stays `list[Path]` of cwds, sorted. **Known gap to document, not fix:** `list_workspaces("omp")` always returns `[]` (`sessions.py:471-474`, lossy session-dir encoding), so `--all` never enumerates omp workspaces under the union default; `--project <cwd>` still reaches omp sessions via `detect_sessions`. State this in the AC and in CLI.md's `--host` paragraph.
   - **All seven consumers** (`_collect_sequences`, `_cmd_extract`, `_cmd_dead_skills`, `_collect_failure_clusters`, `_cmd_stats`, `_cmd_loop_fleet`, `_cmd_fleet_review`, plus the `discover` subcommand) keep receiving a `list[Path]` of cwds — the per-consumer `get_project_folder(decoded_path)` follow-up (653/667/783/1353/1367) is what becomes `detect_sessions(decoded_path, host, include_agents=False)`. The Claude-schema-coupled content functions stay Claude-Code-only (decided in FEAT-3417). Build on the existing partial precedent: `_has_ll_activity` (97), `_extract_cwd_from_project` (134), `_extract_ll_event_streams` (261) already take `layout: HostLayout | None`; leave that parameter in place (ENH-3422 retires it).
4. **`hooks/session_start.py:162`**: pass `host=event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` to `get_project_folder(cwd)` — the same expression already computed at line 178 for the backfill worker (`_backfill_host`). This is the one call site in this issue that stays on `get_project_folder` (it feeds the backfill worker, which is ENH-3422's).
5. **`--host` flag**: add to `ll-logs`, `ll-messages`, `ll-ctx-stats` argparse; default `None`; resolved per § Expected Behavior. **Source the `choices=` list from the seam, not a copied literal (review 2026-09-09):** `_REGISTERED_HOSTS` (`sessions.py:268`) is private today; export it as `REGISTERED_HOSTS` from `little_loops.session_store` (add to `__all__`) and use `choices=list(REGISTERED_HOSTS)` in all three new flags **and** retrofit `cli/session.py:211-216`'s hand-written 8-item list, so a future host registration cannot drift between the seam and the CLIs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- **`cli/session.py:211-216`'s `--host` citation (backfill_parser) is confirmed accurate, no drift**: `choices=["claude-code", "codex", "opencode", "pi", "kimi-code", "qwen", "gemini", "omp"]`, `default=None`; its resolution logic lives separately at `cli/session.py:636`, not in the cited range.
- **No `_resolve_host` helper exists anywhere in the codebase** — a repo-wide search found zero definitions; it is genuinely new code, not something to locate and reuse. Two differently-scoped existing helpers must not be conflated with it: `resolve_host()` (`host_runner.py:2292-2336`) and `resolve_host_named()` (`host_runner.py:2339-2347`) resolve the *orchestration* host (`LL_HOST_CLI`, which host CLI binary to shell out to), not the session-log-discovery host this issue's flag controls.
- **The flag>env inline pattern this issue proposes centralizing is currently duplicated ad hoc at 5 sites across 4 files**, all using the identical literal default `"claude-code"`: `cli/session.py:636`, `user_messages.py:394-395` and `:442`, `hooks/session_start.py:178`, `cli/logs.py:189-190`. No shared flag+env-var helper exists in `cli_args.py` (596 lines, the shared argparse-helper module) today — whether to centralize via the new helper or continue the ad hoc pattern is an implementation choice, not an established convention either way.
- **Existing `--host` flag implementations diverge in shape** across the 4 sites that have one: `cli/session.py:211-216` (backfill: `choices=` 8-item list, `default=None`, separate env fallback) is the only one matching this issue's target semantic (session-log-discovery host). `cli/advise.py:132-136` has no `choices=`/env fallback and resolves via `.ll/ll-config.json`'s `advisor.host` (a different semantic — which model/host CLI the advisor uses, not session-log host). `cli/adapt.py:51-56` is `required=True` with no `choices=`/default/env fallback at all. `mcp_server/__init__.py:106` is an unrelated semantic entirely (HTTP bind address).
- **No existing test covers flag>env precedence** for any CLI's `--host` flag. The closest analog, `test_main_mcp_host_flag_wins_over_config`, tests flag-over-config (a different axis, not flag-over-env). The precedence tests this issue's Acceptance Criteria calls for have no existing pattern to model beyond `test_ll_session.py::TestBackfillArgs::test_backfill_host_choices_list`'s choices-list/invalid-value shape (already cited in this issue's Tests section).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` (`main_messages`, lines 173, 192, 201–207)
- `scripts/little_loops/user_messages.py` (`extract_user_messages` 639, `extract_commands` 722)
- `scripts/little_loops/cli/ctx_stats.py` (`_compute_cache_rate_from_jsonl` 342-355, `main_ctx_stats` ~753)
- `scripts/little_loops/cli/logs.py` (module docstring line 1; `discover_all_projects` 166-215; the 6 functions / 11 call sites above; 649; `_cmd_fleet_review` ~2843)
- `scripts/little_loops/hooks/session_start.py:162`
- `scripts/little_loops/session_store/sessions.py` (`_detect_claude_sessions` 236-265, `_project_folder_for_layout_host` 331 — both-spellings probe; `_REGISTERED_HOSTS` 268 → public `REGISTERED_HOSTS` re-export in `session_store/__init__.py`)
- `.loops/ll-logs-telemetry-digest.yaml:64-67` — greps `ll-logs scan-failures` stderr for the literal `"No session project folder found"` to distinguish `FAILURES_NO_DATA` from `FAILURES_ERROR`. **That branch is unreachable today (review 2026-09-09):** `_cmd_scan_failures` returns 1 on the no-folder path (`cli/logs.py:1554-1556`), and the loop tests `[ "$RC" -ne 0 ]` *before* the grep, so a missing folder always reports `FAILURES_ERROR:rc=1`. Do not merely preserve the string — fix the contract in this change. **Decided:** the no-sessions case is not an error: `scan-failures`/`sequences`/`extract`/`eval-export` emit `"No sessions found for: <cwd>"` on stderr and **exit 0** with empty output (`[]` / no rows), and the loop's grep is updated to the new string (its RC check is then correct as written). Add a test in `test_bug_3216_telemetry_digest_invocations.py` (or beside it) that runs the loop's `scan_failures` action shape against an empty home and asserts `FAILURES_NO_DATA`. Callers that today rely on `rc=1` for a missing folder: none found outside this loop (`ll-messages` keeps its own `return 1`, unchanged). No test asserts the old `"No session project folder found"` string (grep of `scripts/tests/`: 0 hits — review 2026-09-09), so the rename is safe; give `ll-messages`'s `return 1` path the same `"No sessions found for: <cwd>"` wording for consistency.
- `scripts/little_loops/cli/__init__.py` (module docstring lines 16, 18) — "Claude Code logs" / "~/.claude/projects/" framing, same sweep as the doc updates below.

### Behavior Parity

| Existing behavior | Status | Notes |
|---|---|---|
| `_compute_cache_rate_from_jsonl` raw per-line usage reader (`cli/ctx_stats.py:381-403`) | PRESERVED | Still the reader for every non-codex host; only the file pick moves to `detect_sessions(..., limit=1)`. Four return keys unchanged; `host` key additive. |
| `ll-ctx-stats` under `LL_HOOK_HOST=qwen|gemini` reading Claude-shaped `message.usage` (`test_cli_ctx_stats.py:909,941`) | PRESERVED | Depends on the row above — would break through `iter_events` (normalizers strip usage). |
| `_extract_ll_event_streams` qwen `functionCall` recognition via `layout.normalize` (`cli/logs.py:308-311`) | PRESERVED | Same normalization now arrives via `iter_events` → `parse_qwen_session`; `layout=` parameter and line 649 removed. |
| `discover_all_projects` ll-activity filter (`cli/logs.py:213`) and `list[Path]` return | PRESERVED | Re-applied over `detect_sessions`+`iter_events`; four `TestDiscover` tests pass unmodified. |
| `discover_all_projects` default host = `LL_HOOK_HOST` else `claude-code` (`cli/logs.py:189-190`) | CHANGED | `None` now unions all registered hosts (deduped on cwd); documented in CLI.md. omp workspaces absent under `--all`. |
| `ll-logs scan-failures/sequences/extract/eval-export` exit 1 on missing folder | CHANGED | Exit 0 + `"No sessions found for: <cwd>"`; telemetry-digest grep updated. `ll-messages` keeps exit 1 with the new wording. |
| `agent-*` exclusion in every `cli/logs.py` path and `ctx_stats`; inclusion by default in `extract_user_messages`/`extract_commands` | PRESERVED | `include_agents=False` / `include_agents=include_agent_sessions`. |
| `get_project_folder`/`get_sessions_folder` `Path | None` contract | PRESERVED | Untouched; see Dependent Files. |
| `detect_sessions` claude/layout-host folder probe encodes `cwd.resolve()` only (`sessions.py:245,339`) | CHANGED | Also probes the as-recorded spelling; additive (resolved wins), no existing handle changes. |

### Dependent Files (must not change)
- `get_project_folder`/`get_sessions_folder`'s `Path | None` contract stays for `session_log.py:159-212`, `fsm/continuity.py:43`, `cli/session.py:664,702,718` (tests lock it: `test_session_log.py:26-95,384-458`, `test_fsm_continuity.py:53,61,82`, `test_ll_session.py:704`).
- transcript_path-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`) — decided out of scope in FEAT-3417.
- `scripts/little_loops/init/writers.py`'s `_CLAUDE_MD_DESC_OVERRIDES` (lines 282-288) deliberately keeps `"ll-messages": "Extract user messages from Claude Code logs"` / `"ll-logs": "... from Claude project logs"` for `.claude/CLAUDE.md` output specifically (the generic `_LL_COMMANDS` table at line 223 is already host-generic). Regression-test-locked by `test_init_core.py::test_claude_md_keeps_claude_specific_lines` (~1841-1845) alongside `test_content_is_host_generic` (~1833-1839). Intentional design — the docs sweep must NOT touch this override or its test.

### Downstream consumers to verify
- `/ll:loop-suggester --from-sequences` (`commands/loop-suggester.md:740-768`, `skills/ll-loop-suggester/SKILL.md:303-309,408,631,650`) shells out to `ll-logs sequences --json`; confirm Codex-sourced sessions appear once `_collect_sequences` is rewired.
- `scripts/little_loops/loops/fleet-loop-improve.yaml:78,80` — shells out to `ll-logs fleet-review --all --existing-only --exclude-project . | tail -n 1` and derives a `.json` sidecar path from the returned `.md` path; depends on `_cmd_fleet_review`'s current stdout contract surviving the rewire.
- `scripts/little_loops/loops/examples-miner.yaml:38` and `scripts/little_loops/loops/lib/cli.yaml:86-94` (`ll_messages` fragment) — both shell out to `ll-messages --stdout` with no `--host`. Under the new default these run in the union path when `LL_HOOK_HOST` is unset; Claude Code records are byte-identical, but the output may now *also* contain Codex/qwen/etc. messages for the same workspace. Re-run both once the seam lands and confirm the loops tolerate extra hosts (or pin `--host claude-code` in the fragment if they must not).
- `scripts/little_loops/loops/sft-corpus.yaml:53` — `ll-messages --sft-format --reader db` routes through `history.db`, not the JSONL path being rewired — NOT affected.

### Tests
- `scripts/tests/test_ll_logs.py` — `TestSequences`/`TestArgumentParsingSequences` (797-1339), `TestExtract` (1547-2127), `TestScanFailures` (2924-4155), `TestEvalExport*` (4437-4841). Every `_make_project_dir` helper hard-codes the Claude layout and patches `Path.home`; add `--host codex` variants using the committed fixtures under `scripts/tests/fixtures/codex/` laid out under a `tmp_path` home as `test_session_discovery.py` does (`state_N.sqlite` `threads` row or `sessions/YYYY/MM/DD/` scan tree).
- `scripts/tests/test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` (676-974) — add `test_resolves_codex_rollout_cache_rate` beside the qwen (909) / gemini (941) pairs, asserting against the fixture's last (4th) `token_count` (`total_token_usage`: `input_tokens=84003`, `cached_input_tokens=57915`, `cache_write_input_tokens=26076` → `uncached=12`, `hit_rate_pct == 69` — the reader `round()`s to an int at `ctx_stats.py:415`, so assert `== 69`, not `≈ 68.9`; 57915/84003 = 68.94); the qwen/gemini pair must pass unmodified (they set `LL_HOOK_HOST` — the resolution rule preserves that — and they depend on the non-codex branch keeping the raw per-line reader, § Proposed Solution step 2).
- `scripts/tests/test_user_messages.py` — add Codex content tests: user-turn extraction from `response_item` role `user`; `<environment_context>` and `developer` messages excluded; `user_message` dedup when present; and an `include_agent_sessions=True` regression through the new path.
- `scripts/tests/test_session_discovery.py` — existing tests unchanged; add the both-spellings probe case (unresolved symlinked cwd found by `detect_sessions(..., "claude-code", home=...)` and by a layout host such as `qwen`). Consumers must not add `Path.home()` reads (pass `home=` through or patch `Path.home` as the CLI tests already do).
- Existing Claude Code tests in all files above must pass unmodified except where they patch `get_project_folder` directly.
- `scripts/tests/test_cli.py` — `TestMainMessagesIntegration` (~651) and `TestMainMessagesAdditionalCoverage` (~1815), 17 call sites patching `little_loops.user_messages.get_project_folder`/`extract_user_messages`/`extract_commands` with a `MagicMock`. **These WILL break or pass only by accident (review 2026-09-09):** once `main_messages` no longer calls `get_project_folder`, that patch is a no-op and the real `detect_sessions(Path.cwd(), None)` runs against the real `Path.home()`. On a dev machine it finds this repo's real Claude sessions and the mocked extractors mask it; on a clean runner it returns `[]` and trips the no-sessions early return. Re-patch `little_loops.cli.messages.detect_sessions` (or wherever it is imported) to return a fixed `[SessionHandle(...)]`, and assert the extractors receive that `handles` list plus the resolved host.
- `scripts/tests/test_cli_messages.py` — entirely dedicated to `main_messages()` flag interactions, patches the same `_PROJECT_FOLDER_PATH` (line 54); same re-patch as `test_cli.py`.
- `scripts/tests/test_user_messages.py` — 32 `get_project_folder` references; the ones exercising `extract_user_messages`/`extract_commands`/`extract_conversation_turns` with a `tmp_path` folder need a `handles` builder helper (`[SessionHandle(host="claude-code", session_id=f.stem, path=f, cwd=..., updated_at=f.stat().st_mtime, is_agent=f.name.startswith("agent-"))]`) or a `home=`-based `detect_sessions` call; the `get_project_folder`/`get_sessions_folder` unit tests themselves are untouched (those functions keep their contract, § Dependent Files).
- `scripts/tests/test_ll_logs.py::TestDiscover::test_discover_skips_non_ll_project` (204) — asserts the ll-activity filter (a project dir with non-ll records is excluded); this is the regression lock for § Proposed Solution step 3's "filter stays" rule and must pass unmodified. Its positive-case siblings (`test_discover_finds_project_via_queue_operation` 138, `..._dotted_worktree_subpath` 171) are the real lock: they only pass after the both-spellings probe in § Proposed Solution step 3 (the `_make_project_dir` helper at 109 encodes an unresolved path). Add a union-dedupe case: same cwd recorded under two hosts appears once. Note `test_ll_logs.py` also patches `little_loops.cli.logs.get_project_folder` directly with a `side_effect` (e.g. ~2083, `TestExtract`) — those patches go dead the same way as the `test_cli.py` ones and must move to `detect_sessions`.
- `scripts/tests/test_bug_3216_telemetry_digest_invocations.py` — regex-extracts every `ll-logs` invocation out of `.loops/ll-logs-telemetry-digest.yaml` and feeds the argv into `cli/logs.py`'s real argparse parser; run after adding `--host` to confirm the parser surface still accepts the loop's existing invocations.
- Test gap: no existing test asserts that `hooks/session_start.py:162`'s `get_project_folder(cwd)` call receives a `host=` kwarg (all patches use a `*a, **kw`-swallowing lambda). Add a capturing-stub variant of `TestSessionStartHookPassesHost` (`test_enh_3166_qwen_normalizer.py:577-638`) that asserts on the `get_project_folder` call's kwargs.
- Test gap: no `--host` flag-parsing test exists for `ll-logs`/`ll-messages`/`ll-ctx-stats`. Model new tests on `test_ll_session.py::TestBackfillArgs::test_backfill_host_choices_list` (41-61), which locks the choices list + rejects an invalid host via `pytest.raises(SystemExit)`. Add one resolution test per CLI: flag beats env, env beats union, neither → union.

### Documentation
- `docs/reference/CLI.md` — `### ll-logs` ("from Claude Code session logs") and `### ll-messages` (~3552, same framing); document the new `--host` flag on all three per-tool-section (the shared "Common Flags" table does not list `--host` for the three existing consumers `ll-session`/`ll-advise`/`ll-adapt` either — match that practice).
- `docs/guides/HISTORY_SESSION_GUIDE.md` (~503), `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` (10, 81, 429-454), `docs/guides/EXAMPLES_MINING_GUIDE.md` (146, 421) — remove or qualify Claude-Code-only framing.
- `docs/reference/HOST_COMPATIBILITY.md` — record the Codex cache-rate key semantics next to `[^tok-codex]`.
- `docs/reference/API.md:3424-3629,5461-5462` — signature/docstring/usage-example documentation for `extract_user_messages`, `get_project_folder`, `get_sessions_folder`, showing the pre-change `project_folder: Path` parameter; update alongside the signature change.
- `scripts/little_loops/cli/__init__.py` module docstring (16, 18) and `scripts/little_loops/loops/lib/cli.yaml:86-94`'s `ll_messages` fragment description ("Extract user messages from **Claude Code session logs**") — same sweep.

## Program Design

### Types

- `SessionHandle` (`session_store/sessions.py:57`) — `host`, `session_id`, `path`, `cwd`, `updated_at`, `is_agent`
- `SessionEvent` (`session_store/sessions.py:77`) — `type`, `timestamp`, `host`, `payload` (host-native for claude-code/codex; existing-normalizer output for qwen/gemini/omp/kimi per ENH-3420)

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` (existing, `sessions.py:291`)
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` (existing, `sessions.py:824`)
- `list_workspaces(host: str, *, existing_only: bool = True, home: Path | None = None) -> list[Path]` (existing, `sessions.py:455`)
- `_resolve_host(flag: str | None) -> str | None` (new, one shared helper — suggested home `user_messages.py` beside `get_project_folder`) — `flag or os.environ.get("LL_HOOK_HOST") or None`
- `extract_user_messages(handles: list[SessionHandle], limit: int | None = None, since: datetime | None = None, include_agent_sessions: bool = True, include_response_context: bool = False) -> list[UserMessage]` — replaces `project_folder: Path` (`user_messages.py:639`); callers pass `detect_sessions(cwd, host, include_agents=include_agent_sessions)`
- `extract_commands(handles: list[SessionHandle], limit, since, include_agent_sessions=True, tools=None) -> list[CommandRecord]` — same replacement (`user_messages.py:722`); Claude-shaped payloads only
- `extract_conversation_turns(handles: list[SessionHandle], since=None, context_window=3, include_agent_sessions=True, reader="auto") -> list[list[tuple[str, str]]]` — same replacement (`user_messages.py:1028`); the DB branch calls `resolve_history_db(None)` — no new `history_db` kwarg is needed (review 2026-09-09): `_is_default_shaped` (`session_store/db.py:18-26`) treats any `.ll/history.db` as default-shaped and `_resolve_db_path` reroutes it to the project root, so today's `project_folder / ".ll" / "history.db"` already resolves correctly and this is not a behaviour change; JSONL branch Claude-shaped only
- `_extract_ll_event_streams(handles: list[SessionHandle], *, cutoff: datetime | None = None, until: datetime | None = None) -> dict[str, list[InvocationEvent]]` — replaces `project_folder` + `layout` (`cli/logs.py:261`); iterates `iter_events(h)` and reads `e.payload`
- `_detect_claude_sessions` / `_project_folder_for_layout_host` (`sessions.py:236,331`) — probe `encode_project_path(str(cwd.resolve()))` then `encode_project_path(str(cwd))`; signatures unchanged
- `_compute_cache_rate_from_jsonl(cwd: Path, *, host: str | None = None) -> dict[str, Any] | None` — keeps the existing four keys (`cache_read`, `cache_write`, `uncached`, `hit_rate_pct`) plus additive `host: str`; internally `detect_sessions(cwd, host, include_agents=False, limit=1)` then dispatches on `handle.host`: codex → `_codex_cache_usage(iter_events(handle)) -> dict | None`; every other host → today's raw per-line reader on `handle.path` (not `iter_events`)
- `discover_all_projects(logger, *, host: str | None = None, existing_only: bool = False) -> list[Path]` — signature unchanged; `host=None` now means union (was: `LL_HOOK_HOST` default `claude-code`); body = `list_workspaces` per host → dedupe → ll-activity filter via `detect_sessions`+`iter_events`
- `REGISTERED_HOSTS` — public re-export of `sessions._REGISTERED_HOSTS` from `little_loops.session_store`; `choices=` source for every `--host` flag

### Call Path

`main_messages` (`cli/messages.py:13`) -> `_resolve_host(args.host)` -> `detect_sessions(cwd, host, include_agents=...)` -> `extract_user_messages(handles, ...)` -> `iter_events(handle)` -> `_parse_user_record(event.payload)` (Claude-shaped hosts) / Codex `response_item` role-`user` mapping (new)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- **Anchor drift correction (confirmed against HEAD, `session_store/sessions.py`)**: this section's `### Types`/`### Signatures`/`### Call Path` cite line numbers that have moved since this issue's last refine pass. Current locations: `SessionHandle` class def → `sessions.py:57` (cited: 41-57), `SessionEvent` class def → `sessions.py:77` (cited: 60-68), `detect_sessions` → `sessions.py:291` (cited: 255), `list_workspaces` → `sessions.py:455` (cited: 288), `iter_events` → `sessions.py:824` (cited: 472). Signatures and described behavior are unchanged — only the anchors drifted (the file grew between passes). Use the corrected line numbers above; `resolve_anchor()` does not catch this class of drift because all the stale numbers still resolve to *some* line within the file's current bounds, just not the cited symbol.

## Implementation Steps

1. Confirm ENH-3420 has landed: `detect_sessions(cwd, "qwen", home=tmp_path)` returns handles for a qwen fixture tree; `from little_loops.session_store import detect_sessions, iter_events, list_workspaces` imports. Then land the both-spellings probe in `_detect_claude_sessions`/`_project_folder_for_layout_host` with its `test_session_discovery.py` case (§ Proposed Solution step 3) — it is a prerequisite for step 5's `TestDiscover` passing on macOS.
2. Export `REGISTERED_HOSTS` from `session_store`; add `_resolve_host` and `--host` (default `None`, `choices=list(REGISTERED_HOSTS)`) to the three CLIs' argparse and retrofit `cli/session.py:211-216`; add the flag/env/union resolution tests.
3. Rewire `user_messages.py` (`extract_user_messages` + `extract_commands` + `extract_conversation_turns`) and `cli/messages.py`; add the Codex `response_item` user-turn mapping with `<environment_context>`/`developer` filtering, `user_message` dedup, and the `UserMessage` field mapping; re-patch `detect_sessions` in `test_cli.py`/`test_cli_messages.py`; run `test_user_messages.py`, `test_cli.py`, `test_cli_messages.py`.
4. Rewire `cli/ctx_stats.py`: `detect_sessions(..., limit=1)` picks the file, the non-codex branch keeps the raw per-line reader on `handle.path`; implement `_codex_cache_usage` with the last-`total_token_usage` + inclusive-`input_tokens` semantics; add the additive `host` key; add the Codex test (`hit_rate_pct == 69`) beside the qwen/gemini pair; run `test_cli_ctx_stats.py` unmodified.
5. Rewire `cli/logs.py` (11 call sites; `_extract_ll_event_streams` to handles and delete 649 + the `layout=` pass-through; `discover_all_projects` via `list_workspaces` with union-dedupe and the preserved ll-activity filter; `_cmd_fleet_review`); switch the no-sessions path to exit 0 + `"No sessions found for: <cwd>"` and update `.loops/ll-logs-telemetry-digest.yaml:66`'s grep; run `test_ll_logs.py` (re-patching its `cli.logs.get_project_folder` sites to `detect_sessions`) and `test_bug_3216_telemetry_digest_invocations.py`, add the `FAILURES_NO_DATA` reachability test, then add Codex fixture variants.
6. `hooks/session_start.py:162` host injection + capturing-stub test.
7. Docs sweep (CLI.md, three guides, HOST_COMPATIBILITY.md, API.md, `cli/__init__.py` docstring, `loops/lib/cli.yaml` fragment); re-run `examples-miner.yaml` / `fleet-loop-improve.yaml` / `/ll:loop-suggester --from-sequences` against a workspace with a Codex session.

## Impact

- **Priority**: P2 — this is the half that makes FEAT-3417 user-visible.
- **Effort**: Medium — mechanical rewire at ~14 call sites plus three per-site judgment calls (ctx_stats Codex usage semantics, messages user-turn filtering, session_start host injection). Change surface is wide (11 sites in `cli/logs.py` alone); mitigate by landing steps 3, 4, 5 as separate commits, each gated on its own test file passing unmodified.
- **Risk**: Medium — touches read paths automation already depends on; mitigated by the "existing tests pass unmodified" gate, the seam's Claude parser being the existing per-line read lifted verbatim, and ENH-3420 landing first so no host loses coverage.
- **Breaking Change**: No — Claude Code behaviour preserved; Codex additive; `--host` optional. Behavioural note: with `LL_HOOK_HOST` unset, no-flag output now unions hosts (documented in CLI.md).

## Acceptance Criteria

- `ll-logs`, `ll-messages` (user messages, commands, **and** `--sft-format --reader auto|jsonl` conversation turns), and `ll-ctx-stats` obtain sessions via `detect_sessions`/`iter_events` and never call `get_project_folder`/`get_sessions_folder` for session enumeration (`ll-ctx-stats` uses `detect_sessions` to pick the file and `iter_events` for codex only); `ll-logs --all` enumerates workspaces via `list_workspaces`, unions hosts when none is resolved (deduped on cwd; omp workspaces are a documented gap), and still applies the ll-activity filter (all four `TestDiscover` tests pass unmodified on macOS and Linux).
- `detect_sessions(cwd, "claude-code")` and the layout-host branch find a project folder encoded from either the resolved or the as-recorded spelling of `cwd`, asserted by a `test_session_discovery.py` case using a symlinked tmp dir.
- `_extract_ll_event_streams` takes handles and `cli/logs.py` no longer calls `host_layout_for(LL_HOOK_HOST)` (line 649 removed); `ll-logs sequences` output for the existing Claude Code and qwen tests is unchanged.
- Host resolution on all three CLIs is `--host` > `LL_HOOK_HOST` > union, with tests for each precedence step; `choices=` on all three flags (and the retrofitted `ll-session backfill --host`) comes from the exported `REGISTERED_HOSTS`; an invalid `--host` exits via argparse `SystemExit`.
- `ll-logs scan-failures`/`sequences`/`extract`/`eval-export` with no sessions for the target exit 0 with `"No sessions found for: <cwd>"` on stderr and empty output; `.loops/ll-logs-telemetry-digest.yaml`'s `scan_failures` state actually reaches `FAILURES_NO_DATA` on an empty home (test-asserted).
- With no flag and no `LL_HOOK_HOST`, a workspace containing both a Claude Code and a Codex session shows both in `ll-messages` and `ll-logs sequences`; `--host codex` / `--host claude-code` narrows to one.
- `ll-messages --host codex` yields the user's typed prompts from `response_item` role-`user` messages and excludes `<environment_context>` and `developer`-role messages; `extract_commands` yields no records for Codex handles.
- Claude Code output for every existing test in `test_ll_logs.py`, `test_user_messages.py`, `test_cli_ctx_stats.py` (including the qwen/gemini cache-rate pair) is unchanged; `include_agent_sessions=True` still includes `agent-*` sessions and every `cli/logs.py` path still excludes them.
- `ll-ctx-stats` under Codex reports `hit_rate_pct` computed from the last `token_count` event's `total_token_usage` with `uncached = input_tokens - cached_input_tokens - cache_write_input_tokens`; the fixture-derived test value matches; the four existing keys and both renderers are unchanged, and the JSON output carries the additive `host` key naming the session's source host.
- `ll-messages --host codex` records carry `session_id == handle.session_id`, `uuid == payload.id`, `cwd` from `session_meta`, `git_branch is None`, `is_sidechain is False` (asserted in the Codex content test).
- `hooks/session_start.py:162` passes `host=` to `get_project_folder`, asserted by a capturing-stub test.
- `docs/reference/CLI.md` and the three guides no longer frame `ll-logs`/`ll-messages` as Claude-Code-only; `--host` and the union default are documented.

## Related Key Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — per-host session-log table and `[^tok-codex]`
- `docs/reference/CLI.md` — `ll-logs`, `ll-messages`, `ll-ctx-stats` sections

## Verification Notes

Verified 2026-09-09 (`/ll:verify-issues`, graph provider=`codegraph` freshness=`fresh`). All
`Current Behavior`/`Integration Map`/`Program Design` file:line citations checked against HEAD
and matched exactly. Two prior findings from this same pass have been corrected in place:

- **`## Tests` fixture value** originally cited "the fixture's last `token_count`" as
  `total_token_usage: input_tokens=35856/cached=13999/cache_write=21851 → uncached=6, hit_rate≈39.0`
  — those numbers actually belonged to the **second** of four `token_count` events in
  `rollout-interactive.jsonl` (line 24, ordinal 23), not the last. Corrected to the actual last
  event's values (line 33, ordinal 32): `input_tokens=84003/cached_input_tokens=57915/
  cache_write_input_tokens=26076 → uncached=12, hit_rate_pct≈68.9`, cross-checked by summing
  `last_token_usage.input_tokens` across all four events (`14002+21854+22068+26079=84003`), which
  matches the line-33 total and confirms it is the cumulative "last" event.
- **Program Design line drift** corrected via `ll-code defines`: `iter_events` `sessions.py:457`→
  `472`; `detect_sessions` `253`→`255`; `list_workspaces` `286`→`288`; `SessionEvent` `60-67`→
  `60-68`. Signatures and described behavior were already verbatim-correct — only anchors moved.

No decisions-log violations (no active required rules), no evidence-quote fabrications
(`ll-verify-evidence --json`: `ok: true`), and dependency references (`blocked_by: [FEAT-3417,
ENH-3420]`, backlink in ENH-3420's `blocks:`) are all valid — FEAT-3417 is `done`, ENH-3420 is
`open` with `ENH-3419` correctly listed in its `blocks:`.

**Re-verified 2026-09-09 (`/ll:verify-issues`, later pass).** Verdict at time of check:
**OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to
date — this section is a record of what was wrong and fixed, not an outstanding action item).

- **Program Design `### Types`/`### Signatures` anchor drift, round 2**: this section's own
  `### Codebase Research Findings` note (below) had already identified that `sessions.py` grew
  between refine passes and gave corrected line numbers (`SessionHandle`→57, `SessionEvent`→77,
  `detect_sessions`→291, `list_workspaces`→455, `iter_events`→824), but that correction was never
  propagated into the `### Types`/`### Signatures` bullets themselves — they still read the
  stale numbers (41-57, 60-68, 255, 472, 288) from an even earlier pass. Re-verified directly
  against HEAD (`grep -n '^class SessionHandle\|^class SessionEvent\|^def detect_sessions\|^def
  list_workspaces\|^def iter_events'`) and confirmed the `Codebase Research Findings` numbers are
  the current ones; edited the `### Types`/`### Signatures` bullets in place to match.
- Every other file:line citation checked this pass matched HEAD exactly: `cli/logs.py`'s 11 call
  sites and their def lines (`_collect_sequences` 633, `_cmd_sequences` 691, `_cmd_extract` 770,
  `_collect_failure_clusters` 1331, `_cmd_scan_failures` 1552 with its `if`/`return 1` at
  1554-1556, `_cmd_eval_export` 2028, `discover_all_projects` 166, `_extract_ll_event_streams`
  261, module docstring line 1); `cli/ctx_stats.py` (`_compute_cache_rate_from_jsonl` 342,
  `main_ctx_stats` 734 with its call site at 753, current formula at 401-415); `user_messages.py`
  (`get_project_folder` 373, `get_sessions_folder` 422, `extract_user_messages` 639,
  `extract_commands` 722, `extract_conversation_turns` 1028); `cli/session.py` backfill `--host`
  block (211-216) and its resolution logic (636); `.loops/ll-logs-telemetry-digest.yaml:59-67`'s
  `RC=$?` check firing before the `grep "No session project folder found"` elif, confirming the
  issue's claim that the `FAILURES_NO_DATA` branch is currently unreachable; `qwen.py`/`gemini.py`
  normalizer behavior (both strip/never carry `message.usage`); `init/writers.py:281-288`'s
  `_CLAUDE_MD_DESC_OVERRIDES`. Codex fixture math independently recomputed from
  `rollout-interactive.jsonl`'s 4 `token_count` events: last event's `total_token_usage` =
  `{input_tokens: 84003, cached_input_tokens: 57915, cache_write_input_tokens: 26076}` →
  `uncached = 84003 - 57915 - 26076 = 12`, `hit_rate_pct = round(57915/84003*100) = 69` — matches
  the issue's asserted test value exactly; sum of `last_token_usage.input_tokens` across all four
  events (`14002+21854+22068+26079=84003`) matches, confirming cumulative semantics.
- Decisions log gate: both `.ll/decisions.yaml` and `.ll/decisions.d` present;
  `ll-issues decisions list --type rule --enforcement required --active-only` exited 0 with no
  entries — no active required rules, clean pass.
- `ll-verify-evidence` on this file: `{"ok": true, "count": 0}` — no fabricated evidence spans.
- **Dependency references re-checked directly** (`ll-issues show ENH-3420`/`FEAT-3417 --json`):
  both are `Completed`; both list `ENH-3419` in their own `blocks:`. This issue's frontmatter
  currently carries `blocked_by: []` with `FEAT-3417`/`ENH-3420` in `relates_to` instead (per the
  Summary's "moved from `blocked_by` to `relates_to`" note, since both blockers are done — the
  correct move per the deferral-discriminator rule that only `done`/`cancelled` resolve
  `blocked_by`). The two-passes-back Verification Notes paragraph above still asserts
  `blocked_by: [FEAT-3417, ENH-3420]` and "ENH-3420 is `open`" — both are now stale relative to
  the Summary's later edit, not a live dependency defect (§E's backlink check is one-directional
  from `blocked_by`, and this issue's `blocked_by` is empty, so there is nothing to check).
  No `DEP_ISSUES` finding.
- **Remaining (not corrected this pass, flagged for a future refine/wire pass):** the
  "Downstream consumers to verify" list (loop-suggester `--from-sequences`, `fleet-loop-improve.yaml`,
  `examples-miner.yaml`/`loops/lib/cli.yaml`) names three integration points with no corresponding
  Acceptance Criterion asking that they actually be re-run and confirmed post-rewire — an AC
  coverage gap per the B6 consequence check. Precedence: since a current-state citation defect was
  also found this pass, the overall verdict stays `OUTDATED` rather than `PROPOSAL_UNSOUND`; this
  gap is noted for whoever next touches the AC list. Frontmatter `verify_verdict` is set to
  `PROPOSAL_UNSOUND` (not `VALID`) to reflect this uncorrected residual, per 2.5's mapping applied
  to the post-fix state.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-09_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 45/100 → LOW

### Outcome Risk Factors
- Very wide blast radius: 11+ call sites in `cli/logs.py` alone plus `user_messages.py`, `cli/ctx_stats.py`, `hooks/session_start.py`, and `session_store/sessions.py` — broad enumeration across many sites, several of which need bespoke (not uniform) treatment, so a missed or mismatched site is easy to overlook despite the detailed per-site plan.
- Non-mechanical subcomponents carry the real correctness risk: the Codex cache-rate cumulative-vs-per-turn `token_count` semantics, the `cwd` both-spellings probe in `_detect_claude_sessions`/`_project_folder_for_layout_host`, and the Codex user-turn extraction/filtering logic are each judgment-heavy, not text substitutions.
- Multiple existing test suites (`test_cli.py`, `test_cli_messages.py`, `test_ll_logs.py`) patch `get_project_folder` directly; those patches go dead once the rewire lands and must be re-pointed at `detect_sessions` — an incomplete re-patch would leave tests passing for the wrong reason rather than failing loudly.

## Status

**Open** | Created: 2026-09-09 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-09-09T21:01:56 - `f3e8c388-f237-4461-9091-b0b23efd2cd3.jsonl`
- `/ll:verify-issues` - 2026-09-09T20:57:44 - `308c22fb-018f-45ce-acc8-645eeab79f84.jsonl`
- `review (manual: ctx-stats non-codex branch keeps raw reader — qwen/gemini normalizers strip message.usage; list_workspaces→detect_sessions round-trip fails TestDiscover on macOS → both-spellings probe in seam; _extract_ll_event_streams handles-based + line 649 removed; hit_rate_pct == 69 not ≈ 68.9; history_db kwarg dropped (resolve_history_db already reroutes); omp --all gap documented; ll-messages no-sessions string aligned)` - 2026-09-09T22:15:00
- `/ll:confidence-check` - 2026-09-09T20:42:30 - `cfabad4e-29d0-4bbf-8a3f-5a2f2c2e4144.jsonl`
- `review (manual: extract_conversation_turns added to scope; discover_all_projects ll-activity filter + union-dedupe + 7 consumers spelled out; Codex --all overclaim reworded; telemetry-digest FAILURES_NO_DATA branch found unreachable → no-sessions exits 0 with new string; test_cli/test_cli_messages/test_ll_logs get_project_folder patches go dead → re-patch detect_sessions; REGISTERED_HOSTS export for choices=; Codex UserMessage field mapping; additive host key in ctx-stats dict)` - 2026-09-09T21:30:00
- `/ll:refine-issue` - 2026-09-09T20:25:11 - `1a13a741-5120-4c1e-a389-069561e94486.jsonl`
- `/ll:verify-issues` - 2026-09-09T19:12:44 - `16a3bdad-e90f-4e75-82df-f1d6a2398c12.jsonl`
- `review (manual: FEAT-3417 landed; added ENH-3420 as blocker (seam covers 2/8 hosts); LL_HOOK_HOST precedence; Codex user-turn source corrected to response_item role=user; token_count semantics decided; include_agents mapping; extract_commands Claude-only; dict return type; line refs refreshed)` - 2026-09-09T19:10:00
- `/ll:confidence-check` - 2026-09-09T15:01:24 - `a4ac4148-e562-4d02-a9a9-889fd2f8dc3f.jsonl`
- `/ll:wire-issue` - 2026-09-09T14:51:24 - `8e56ec89-cd99-46e0-b932-f07e5ea9315c.jsonl`
- `/ll:refine-issue` - 2026-09-09T14:01:26 - `fc9ca416-ac94-40a4-8082-2af225a0464c.jsonl`
- `/ll:format-issue` - 2026-09-09T13:22:13 - `94cf9e94-a0b2-480c-8238-e366777de95e.jsonl`
