---
id: FEAT-3417
title: Runtime-adapter seam for host log ingestion, with Codex as the second implementation
type: FEAT
priority: P2
status: open
discovered_date: '2026-09-08'
labels:
- multi-host
- observability
- testing
decision_needed: false
reconcile_attempted: true
learning_tests_required:
- codex
- codex-rollout
confidence_score: 85
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
verify_verdict: VALID
missing_artifacts: true
spike_attempted: true
spike_completed: true
blocks:
- ENH-3419
relates_to:
- ENH-3420
---

## Summary

`ll-logs`, `ll-messages`, and `ll-ctx-stats` all reach directly for `~/.claude/projects/<munged-cwd>/`, and nothing in the tree parses a Codex rollout file. That is the observability half of goal 2 going unbuilt while the generation half is already done: `ll-adapt --host codex` ships today, so little-loops writes artifacts for Codex and then cannot read a single Codex session back. Every log-derived capability downstream — goal 6's dataset export, goal 7's quality rollups — silently covers one host while claiming to generalize.

Introduce a session-discovery seam, not a Codex feature. The interface is small and covers the lifecycle only: enumerate the workspaces a host has sessions for, enumerate the sessions for a workspace, iterate their typed events (live `watch`/`stop` deferred to the first consumer that needs it — see § Live watch is deferred). Per-host parsers live behind it and share nothing above it.

**Scope after the 2026-09-09 split.** This issue delivers the seam itself, the Codex implementation, its fixtures and learning test, and retirement of the dead `~/.codex/projects/` probe (original Implementation Steps 1–3). Adoption of the seam by the three CLIs, the `--host` flag, the docs sweep, and the FSM-loop string check moved to **ENH-3419** (blocked by this issue). The `HostLayout`/seam unification that three confidence checks flagged as unfiled is **ENH-3420**. Rationale: outcome confidence sat at 33/100 with change surface 0/25 across four `/ll:confidence-check` passes, meeting the issue's own split trigger.

## Current Behavior

`ll-logs`, `ll-messages`, and `ll-ctx-stats` each reach directly for `~/.claude/projects/<munged-cwd>/` — Claude Code's own JSONL session layout — with no seam between the CLI and the on-disk format. Nothing in the tree parses a Codex rollout file. `ll-adapt --host codex` already generates Codex-targeted artifacts, but no code reads a Codex session back, so a workspace driven by Codex is invisible to every log-derived command.

The tree's existing Codex "support" in this area is dead code: `_get_codex_project_folder` (`user_messages.py:458`), `host_layout_for("codex").projects_root` (`session_store/writers.py:2593`), and `test_host_codex_probes_codex_projects` (`scripts/tests/test_user_messages.py:147`) all probe `~/.codex/projects/<encoded>`, a directory Codex has never written (see § Codex On-Disk Layout below). `ll-session backfill --host codex` is therefore wired but always resolves zero sessions.

A spike (`scripts/tests/spike/session_discovery_lifecycle/`, 11 passing tests) has proven the discovery algorithm in isolation but is not shipped as a production module.

## Expected Behavior

A production module `session_store/sessions.py` exposes the session-discovery interface — `list_workspaces`, `detect_sessions`, `iter_events` — with per-host parsers behind it. Claude Code is the first implementation (the existing per-line JSONL read lifted verbatim) and a Codex rollout parser is the second. Codex rollout files are discovered from `~/.codex/sessions/` via the sqlite `threads` index with a date-directory scan fallback. `_get_codex_project_folder` and `host_layout_for("codex").projects_root` no longer claim a `~/.codex/projects/` layout. Two captured Codex fixtures and a `codex-rollout` learning test proven against the currently installed Codex CLI ship alongside the parser. No CLI is rewired here (ENH-3419).

## Codex On-Disk Layout (verified 2026-09-08 against a live `~/.codex`; corpus cli_version 0.98.0/0.130.0)

_Added by review on 2026-09-08; refreshed 2026-09-09. Every claim below was checked against the real directory on the maintainer's machine (8,858 rollouts; 1,788 for this repo's exact cwd, 2,064 including subdirectory launches). This corrects the "working Codex path probe" premise carried by earlier refinement passes._

**Corpus staleness (2026-09-09).** The installed CLI is now `codex-cli 0.152.1`. Every local rollout is from 0.98.0 (6,696) or 0.130.0 (2,162), the newest dated 2026-07-02, and the sqlite schema is at `_sqlx_migrations` version 31. The layout claims and the `codex-rollout` learning test were proven against that older corpus. Step 1's fixture capture runs on 0.152.1 and must be followed by a re-prove of the learning test; expect the state DB to migrate (possibly to `state_6.sqlite` — the newest-`N` selection handles this).

**0.152.1 layout drift (confirmed 2026-09-09 via live fixture capture, one interactive + one `exec` session, this repo's cwd).** The record shape below was verified against the 0.98.0/0.130.0 corpus and is stale on 0.152.1 in four ways:

1. A fifth top-level `type: "world_state"` appears in both captured rollouts (line 7 of 34 and 7 of 14 respectively), payload `{full, state}` — not in the `session_meta | turn_context | response_item | event_msg` enum below. `iter_events`/`parse_codex_rollout` must treat an unrecognized top-level `type` the same as an unrecognized subtype — pass through untouched, never raise — so this needs no schema change, only a docstring/table update.
2. `response_item.payload.type` gained `custom_tool_call`, `custom_tool_call_output`, and `reasoning` (the interactive fixture has three `custom_tool_call`s, `name: "exec"`, running shell commands via `tools.exec_command`) — this is the tool-call shape AC #2 needed and the captured interactive fixture now has it.
3. `event_msg.payload.type` gained `item_completed` (not in the documented `user_message | task_started | task_complete | turn_aborted` list).
4. `session_meta.payload` gained five fields not in the table below: `context_window`, `git`, `history_mode`, `session_id`, `thread_source`.

None of this changes the discovery strategy (sqlite `threads` query / scan fallback, both `cwd` spellings) — it is confined to per-record content, which the parser already treats opaquely. Step 1 must fold these into the Record shape table before promotion (Step 2).

**Layout.** Codex writes one rollout per session at `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-timestamp>-<uuid>.jsonl`, keyed by **date**, not by project. There is no `~/.codex/projects/`. The workspace is only recoverable from inside the file: `session_meta.payload.cwd` on line 1, and `turn_context.payload.cwd` on every turn. Consequence: sessions for one cwd are scattered across many date directories, so no single folder satisfies `get_project_folder`'s "Path containing `*.jsonl`" contract for Codex. Codex must not route through `get_project_folder`; the seam returns per-session file handles instead.

**Session index.** Codex also maintains `~/.codex/state_<N>.sqlite` (currently `state_5.sqlite`, WAL mode with `-shm`/`-wal` sidecars) with a `threads` table. Columns observed: `id` (= `session_meta.payload.id`, verified), `rollout_path`, `created_at`/`updated_at` (**integer epoch seconds**; `*_ms` twins also exist), `source`, `model_provider`, `cwd`, `title`, `sandbox_policy`, `approval_mode`, `tokens_used`, `has_user_event`, `archived`, `archived_at`, `git_sha`, `git_branch`, `git_origin_url`, `cli_version`, `first_user_message`, `agent_nickname`, `agent_role`, `memory_mode`, `model`, `reasoning_effort`, `agent_path`, `thread_source`; indexed on `(archived, cwd, updated_at_ms)`. A `thread_spawn_edges` table records subagent threads. This is the cheap, authoritative index for "sessions for cwd X", but the filename version suffix and schema are vendor-private and unversioned from our side, so it cannot be the only path.

**Discovery strategy (decided):** `detect_sessions(cwd, "codex")` queries the newest `state_*.sqlite` `threads` table matching `cwd` against **both** `str(cwd)` and `str(cwd.resolve())` (macOS `/tmp` → `/private/tmp`; `get_project_folder` already resolves), ordered by `updated_at` desc; if the DB is absent, unusable (any `sqlite3.Error` — note that `sqlite3.connect(..., mode=ro)` *succeeds* on a non-database file and on a WAL database whose `-shm` sidecar is not writable; the error surfaces at the **first statement**, so the guard must wrap the `PRAGMA`/`SELECT`, not only the connect), or lacks the expected columns, fall back to scanning the rollout date directories newest-first, reading only line 1 of each rollout and matching `payload.cwd` against the **same two spellings**. Both paths return the same handle type; `updated_at` is seconds on both (DB integer vs. `st_mtime` float) — do not "correct" to `updated_at_ms`. Every `rollout_path` from the DB is verified to exist before being returned (the DB can outlive deleted files). Subdirectory launches are excluded, matching Claude Code's per-exact-cwd project folders. Subagent threads (`agent_role IS NOT NULL` or present in `thread_spawn_edges`) set `SessionHandle.is_agent = True`, the Codex counterpart of Claude Code's `agent-*.jsonl` prefix.

**Archived threads (decided 2026-09-09; source-read prediction corrected 2026-09-09 by live capture on 0.152.1).** Archived threads are included (batch analytics wants them). Codex archives a thread by **moving its rollout out of `sessions/`** into `~/.codex/archived_sessions/` (https://github.com/openai/codex/blob/main/codex-rs/rollout/src/lib.rs: `SESSIONS_SUBDIR = "sessions"`, `ARCHIVED_SESSIONS_SUBDIR = "archived_sessions"`), and `threads.archived` is *derived* from whether `rollout_path` sits under that directory (https://github.com/openai/codex/blob/main/codex-rs/thread-store/src/local/helpers.rs, `rollout_path_is_archived`). Consequence: the sqlite path returns archived sessions naturally (the file exists, just elsewhere), but a scan that walks only `sessions/` silently drops them.

**Corrected 2026-09-09 by live capture: `archived_sessions/` is FLAT on `codex-cli 0.152.1`, not date-keyed.** `codex archive <session-id>` was run against the exec fixture session (`01a086eb-75f9-75c2-b2ad-59202d992489`); the rollout landed at `~/.codex/archived_sessions/rollout-2026-09-09T11-06-13-01a086eb-75f9-75c2-b2ad-59202d992489.jsonl` — directly under `archived_sessions/`, with **no `YYYY/MM/DD/` subdirectory** — and `threads.rollout_path` was rewritten to match, `threads.archived = 1`, `threads.archived_at` set. The `main`-branch source reading that predicted a date-tree mirror of `sessions/` was wrong for the installed CLI (a version/build difference, or the source read didn't reflect the actual archive-write path). **The scan fallback must therefore walk `archived_sessions/` as its own tree (glob `*.jsonl` at its root, not `YYYY/MM/DD/*.jsonl`), separately from the date-keyed walk over `sessions/`**, and should not assume either has the other's structure; a defensive implementation globs `**/*.jsonl` under `archived_sessions/` so it tolerates either shape if the layout changes again. `SessionHandle` needs no new field. This finding must be folded into Program Design / Implementation Steps §2 and the new fallback test (Integration Map → Tests) before promotion.

**Record shape (0.98.0/0.130.0 corpus baseline; see 0.152.1 drift below).** Every line is `{"timestamp": <ISO>, "type": <str>, "payload": {...}}`:

```
type: session_meta | turn_context | response_item | event_msg
session_meta.payload:   id, timestamp, cwd, originator, cli_version, source, model_provider,
                        base_instructions{text}  (inlined — ~22 KB on line 1 in the sample)
turn_context.payload:   turn_id, cwd, model, approval_policy, sandbox_policy, ...
response_item.payload.type: message   (role: user|assistant; content: [{type: input_text|output_text, text}])
event_msg.payload.type:     user_message{message} | task_started | task_complete | turn_aborted
```

`turn_aborted` was observed in the 2026-09-09 sample (3 of 400 files); the parser is generic over `type` and must pass unknown `event_msg`/`response_item` subtypes through untouched rather than enumerating them.

**Record shape, 0.152.1 additions (confirmed 2026-09-09 via live fixture capture — see § 0.152.1 layout drift above).**

```
type: ... | world_state                                          (payload: {full, state}; unknown top-level type, pass through)
session_meta.payload:   ...also context_window, git, history_mode, session_id, thread_source
response_item.payload.type: ...also custom_tool_call{id,status,call_id,name,input,internal_chat_message_metadata_passthrough},
                             custom_tool_call_output{id,call_id,output}, reasoning
event_msg.payload.type:     ...also item_completed, token_count{info:{total_token_usage,last_token_usage,model_context_window},rate_limits}
```

The parser's "pass unknown subtypes through untouched" rule (previous paragraph) now also has to apply one level up, to an unrecognized top-level `type` (`world_state`) — `iter_events` must not raise or special-case it, just yield/pass through like any other unmapped record.

**Per-turn usage is confirmed present in the rollout itself** (event_msg `token_count`, both interactive and `exec` fixtures) — this resolves the open question Testing → Fixture capture item 2 posed; see that section for the corrected finding. `HOST_COMPATIBILITY.md`'s `[^tok-codex]` footnote is not contradicted by this — it documents `codex exec --json` stdout's `turn.completed` event, a different data source — but it also doesn't establish the rollout-file answer, which was genuinely open until this capture.

Records are per-line parseable; the session id and cwd live only in the header line, so `parse_codex_rollout` is the gemini/omp whole-file-context case for identity and the qwen per-record case for everything else. The oversized-first-line hazard this issue's Testing section cites is real-shape here (`base_instructions` is inlined into `session_meta`); Python `open()` text iteration has no line ceiling, so the risk is a downstream consumer with a fixed buffer, not the parser itself — note it in the parser docstring.

**What the local corpus does NOT contain.** All 8,858 local sessions are `source = "exec"` one-shots (`codex exec`): zero `function_call`, zero `function_call_output`, zero `token_count`, zero reasoning items, `tokens_used = 0` and `has_user_event = 0` on every `threads` row. Interactive/TUI sessions with tool use and per-turn usage have a different payload vocabulary — now observed directly via the 2026-09-09 fixture capture (§ 0.152.1 layout drift above), which also shows `token_count` present in the plain `exec` one-shot fixture, contradicting the corpus's `zero token_count` finding for that `source` value on the newer CLI. See Testing → Fixture capture.

## The seam is at the lifecycle, and is refused on content

Deliberately keep the seam at the lifecycle and refuse it on content. Tool-call shapes and token accounting do not overlap enough between hosts to justify a common abstraction, and forcing one produces a lowest-common-denominator record that is worse than two honest per-host ones.

Evidence from a visualizer that independently shipped two host integrations against the same two runtimes supports exactly this split. It introduced a four-method session-watcher interface *and* explicitly refused a shared tool summarizer in the same release, recording the reason in a header comment: the two runtimes' tool shapes don't overlap enough. Token counting followed the same rule in the other direction — Codex exposes authoritative token counts, so the estimator was deleted there; Claude Code exposes no equivalent field, so estimation stayed. Two runtimes, two strategies, no forced uniformity.

This is a real counterweight to the standing proposal for a declarative host-adapter schema — a host described as a YAML stanza with capability booleans. That proposal assumes hosts are uniform enough for one schema to describe them. The evidence from two hosts actually implemented is that the *lifecycle* generalizes cleanly and the *content* does not, which suggests the seam belongs at the watcher with per-host content code behind it, rather than at a schema that tries to describe the content. Weigh it when that design decision is actually made; it is not a refutation.

## Sequencing

Build the seam when the second implementation makes the duplication concrete, not in anticipation of it. Codex is that second implementation, so the seam is now earned. The reference implementation followed the same order — the first host was built with no abstraction at all, and the interface arrived only once the second host made the duplication real.

Keeping the Codex reader free of any UI-framework dependency is what lets one implementation serve `ll-logs`, `ll-ctx-stats`, and a future dashboard without modification.

### Live watch is deferred (review decision, 2026-09-08)

The original four-method interface (`detect_session`/`watch`/`stop`) was borrowed from a visualizer that has a live panel. Nothing in the eventual call path is live: `ll-logs sequences`/`extract`/`scan-failures`/`eval-export`, `ll-messages`, and `ll-ctx-stats` are all batch reads over finished files, and `ll-logs tail` tails loop event files, not host sessions. v1 therefore ships the batch half only — `list_workspaces`, `detect_sessions` (plural: `_collect_sequences` needs every session for a project, not "the active one") and `iter_events` — and leaves `watch`/`stop` for the first consumer that actually tails a host session (a dashboard). The interface must be shaped so `watch(handle)` can be added later without changing `detect_sessions`/`iter_events`.

### Decided (review, 2026-09-09): three design gaps closed

1. **Host resolution.** `detect_sessions(cwd, host: str | None = None)`. With `host=None` the seam returns the union of every registered host's sessions for `cwd`, newest `updated_at` first, each handle carrying its `host`. Reason: none of the eventual consumers has a `--host` flag, and `LL_HOOK_HOST` is exported only inside host hook adapters (`hooks/adapters/*/`), never in a user's shell — so a required `host` argument would have left Codex sessions invisible by default, contradicting the Use Case's "no host-specific flag required". Callers that want one host pass it explicitly; ENH-3419 adds `--host` as the CLI surface for that.
2. **Agent sessions.** `SessionHandle.is_agent: bool` and `detect_sessions(..., include_agents: bool = False)`. Reason: `extract_user_messages` defaults to `include_agent_sessions=True`, while the spike's Claude detector drops `agent-*.jsonl` unconditionally — the "byte-identical Claude Code behaviour" AC in ENH-3419 cannot hold without the discriminator. Claude Code: filename prefix `agent-`. Codex: `threads.agent_role IS NOT NULL` or membership in `thread_spawn_edges`; in the scan fallback, `session_meta.payload.originator` if it distinguishes subagents, else `False` (record what the capture shows).
3. **Workspace enumeration.** `list_workspaces(host: str) -> list[Path]`. Reason: `cli/logs.py` (~line 196) walks `host_layout_for(host).projects_root.iterdir()` for `extract --all`/`scan-failures --all`; step 3 sets Codex's `projects_root` to `None`, so `--all` would silently yield nothing for Codex. Claude Code: the existing `projects_root` walk plus `_extract_cwd_from_project`. Codex: `SELECT DISTINCT cwd FROM threads` (scan fallback: distinct line-1 `cwd`s), filtered to paths that exist when the caller asks.

## Testing

Test the Codex parser against a captured real-shape rollout fixture — actual JSONL from a real session, committed alongside the parser — not hand-minimized stubs. This is complementary to, not a substitute for, the scripted fake-host work: a fake host tests our handling of a sequence we chose, a captured fixture tests our parser against a record shape the vendor chose and can change under us without telling us.

Treat the fixture as perishable and re-capture it periodically. The concrete precedent: a vendor started inlining full base instructions into the first line of its rollout file, that line blew past a consumer's fixed 64KB read buffer, `cwd` extraction failed, and sessions were silently skipped — an empty panel with no error. Neither a scripted fake host nor the existing unit tests would have caught it; re-capturing the fixture would have.

### Fixture capture

A fixture lifted from the local corpus covers only the `exec` one-shot vocabulary (`session_meta`, `turn_context`, `message`, `user_message`, `task_started`, `task_complete`, `turn_aborted`). That is insufficient for AC #2 (per-host tool-call shapes and token accounting). Required before the parser is considered tested:

1. Deliberately run one **interactive** Codex session in this repo (`codex`, not `codex exec`; CLI 0.152.1) that issues at least one shell tool call and one file read, then copy its rollout to `scripts/tests/fixtures/codex/rollout-interactive.jsonl`. Use a throwaway prompt — every user turn lands verbatim in the committed fixture. Also commit one fresh `exec` one-shot as `rollout-exec.jsonl`. Record in the README whether the interactive session appears in `threads` with `agent_role`/`thread_spawn_edges` rows (drives Decided #2's Codex agent rule). ~~Archive one thread during capture and confirm the § Archived threads finding on 0.152.1.~~ **Done 2026-09-09**: archiving the exec fixture session moved its rollout to `~/.codex/archived_sessions/rollout-...jsonl` — **flat, no `YYYY/MM/DD/` subdirectory**, contradicting the source-read prediction — and rewrote `threads.rollout_path`/`archived`/`archived_at` accordingly (§ Archived threads, corrected above). Record the observed path in the README.

   **Sanitization (both fixtures, before commit):**
   - Strip `base_instructions.text` to a short placeholder, keep the key so the oversized-header code path is still exercised; record the original line-1 byte length in the README.
   - Rewrite every absolute home-directory path to a neutral placeholder that is *not* under a `Users/` or `home/` prefix (e.g. `/workspace/project`) — `session_meta.payload.cwd`, every `turn_context.payload.cwd`, and any path inside tool-call arguments/outputs in the interactive rollout, used consistently so the id/cwd tests can match on it. `ll-verify-private-refs`'s `abs_user_path` rule rejects real home paths, and `test_check_private_refs_hook.py` enforces it in the suite and the pre-commit hook — an unsanitized fixture fails the gate at commit time.
   - Scrub tool outputs of anything else machine-specific (shell snapshots, env dumps); `git.repository_url`/`commit_hash` are public and may stay.
   - Tests build their fake `~/.codex` (state DB rows + date dirs) around the fixture's *rewritten* cwd, not the capture machine's.
2. ~~While capturing, confirm whether rollout files carry per-turn usage at all.~~ **Answered 2026-09-09 by the live capture: yes.** Both the interactive and `exec` fixtures contain `event_msg.payload.type == "token_count"` records carrying `total_token_usage`/`last_token_usage`/`model_context_window` (see § Codex On-Disk Layout → Record shape, 0.152.1 additions). `docs/reference/HOST_COMPATIBILITY.md`'s `[^tok-codex]` footnote documents a different, complementary source (`codex exec --json` stdout's `turn.completed` event) and needs no correction, but the rollout-file question it left open is now closed. Record this in the fixture README and the parser docstring; ENH-3419's `ll-ctx-stats` step branches on it.
3. **Perishability marker = the learning test.** The `codex-rollout` learning-test record exists (`.ll/learning-tests/codex-rollout.md`, proven 2026-09-08, 7 claims) but was proven against the 0.130.0 corpus and asserts only a `rollout_path` column on `threads`. Re-prove after the 0.152.1 capture, adding claims for: `threads.cwd`, `threads.updated_at`, `threads.agent_role` columns; `turn_context.payload.cwd`; `session_meta.payload.id == threads.id`; and whether `token_count` events exist in the interactive rollout. Stamp with the `cli_version` read from the captured `session_meta`. The fixture README's re-capture rule is then mechanical: "re-run `ll-learning-tests prove codex-rollout` and re-capture both fixtures whenever `codex --version` differs from the `cli_version` recorded here." The existing `codex` learning-test record covers MCP `config.toml` shape only and does not stand in for this.

## Relations

- **ENH-3419** (blocked by this issue): adopts the seam in `ll-logs`, `ll-messages`, `ll-ctx-stats`; adds `--host`; docs sweep; loop-YAML string check.
- **ENH-3420** (blocked by ENH-3419): unify `HostLayout` with this seam, or document the boundary.
- Relates to the session-id minting work, which fixes run↔transcript pairing precision above this layer, and to the declarative host-adapter schema proposal discussed above.

## Use Case

**Who**: A little-loops maintainer (and, via ENH-3419, `ll-logs`/`ll-messages`/`ll-ctx-stats`) that needs every session for a workspace regardless of which host wrote it.

**Context**: The workspace has been driven by both Claude Code and Codex (`ll-adapt --host codex`), so session data lives in `~/.claude/projects/<munged-cwd>/*.jsonl` and in date-keyed `~/.codex/sessions/` rollouts.

**Goal**: Call `detect_sessions(cwd)` and get handles for both hosts' sessions, newest first; call `iter_events(handle)` on any of them and get typed events with the host's native payload.

**Outcome**: One implementation serves every batch consumer. Goal 6's dataset export and goal 7's quality rollups can then cover both hosts once ENH-3419 rewires them.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

Research surfaced a real fork. A per-host content-parsing seam already exists (`session_store/writers.py`'s `HostLayout.normalize`/`normalize_file`, covering `qwen`/`gemini`/`omp`), and it takes the opposite position from this issue's stated design: those three normalizers translate host-native records *into a shared Claude-shaped record* ("yields Claude-shaped `user`/`assistant` records" — `gemini.py`, `omp.py` docstrings), whereas this issue explicitly refuses a shared content abstraction. Codex has no entry in that seam today (falls through to `normalize=None`).

**Option A**: Extend the existing `HostLayout` seam with a Codex `normalize`/`normalize_file` entry that translates Codex rollout records into the existing Claude-shaped record schema. Lowest new-surface-area option, but inherits the "unify to Claude shape" convention this issue's "seam is refused on content" section argues against.

**Option B**: Build the session-discovery interface as specified in `## Program Design` (`SessionHandle`, `SessionEvent` carrying a host-native `payload` dict, `parse_codex_rollout` as the second implementation), independent of `HostLayout`. Keeps per-host content genuinely separate. Leaves two parallel per-host dispatch mechanisms in the codebase until ENH-3420 resolves them.

> **Selected:** Option B — consistent with the "seam is refused on content" design section; Option A's apparent advantage ("`ll-session backfill --host codex` already wired end-to-end", "`get_project_folder` already has a working Codex probe") was illusory because the probe targets a directory Codex never writes (§ Codex On-Disk Layout), so the Codex discovery path is net-new either way.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-08; corrected by review the same day (the "live-watch requirement" ground was circular and is withdrawn; Option B stands on content-refusal alone).

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (extend HostLayout) | 1/3 | 2/3 | 2/3 | 1/3 | 6/12 |
| Option B (session-discovery interface) | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

`SessionEvent` has a direct field-for-field precedent in `LLEvent`/`LLHookEvent`; the parser's generator shape matches the `gemini.py`/`omp.py` convention; the spike (`scripts/tests/spike/session_discovery_lifecycle/`) has since proven the discovery algorithm.

## Integration Map

### Files to Modify
- **New** `scripts/little_loops/session_store/sessions.py` — promoted from the spike (`scripts/tests/spike/session_discovery_lifecycle/lifecycle.py`), with the three Decided additions (`host=None` union, `is_agent`/`include_agents`, `list_workspaces`), the `cwd`/`cwd.resolve()` double match on both Codex paths, and the `archived_sessions/` walk in the scan fallback. **Keep the spike's `home` parameter**, relaxed to keyword-only `home: Path | None = None` resolving to `Path.home()` at call time (decided by review 2026-09-09). **The Claude Code branch must honour `home` too**: it does *not* call `get_sessions_folder`/`get_project_folder` (both read `Path.home()` internally and would ignore the override); it computes `home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))` locally, importing the production `encode_project_path` from `user_messages` (no cycle — `user_messages` only lazy-imports `session_store` inside function bodies). Encode the **resolved** cwd, exactly as `get_project_folder` does; the spike encodes the raw spelling, and pytest's `tmp_path` is already resolved on macOS, so a test cannot catch that drift — the ENH-3419 "byte-identical Claude Code behaviour" AC depends on it. Reason for `home`: `conftest.py`'s autouse `_isolate_session_log_dir` points `Path.home()` at a *session-scoped, shared* fake home that is read-only by convention ("nothing writes"); the new tests must create `state_N.sqlite`, `sessions/YYYY/MM/DD/`, and `.claude/projects/<encoded>/` trees, and writing those into the shared home cross-contaminates tests under xdist. Passing `home=tmp_path` avoids patching entirely. Tests that go through a production caller (later, ENH-3419) monkeypatch `Path.home` to `tmp_path` per test, the `TestSessionLogHostAware` pattern — never write into the shared fake home.
- `scripts/little_loops/session_store/__init__.py` — eager import + `__all__` entries following the gemini/omp precedent (lines ~67/91/100, `__all__` 176-283).
- `scripts/little_loops/user_messages.py:458` — `_get_codex_project_folder` returns `None` with a docstring pointing at `detect_sessions`.
- `scripts/little_loops/session_store/writers.py:~2593` — `host_layout_for("codex").projects_root` becomes `None` (gemini/omp strict-None convention).
- `scripts/little_loops/cli/session.py:664-718` — `backfill --host codex` prints a clear "Codex backfill via detect_sessions is ENH-3420" notice instead of silently finding nothing.
- **New** `scripts/tests/fixtures/codex/rollout-interactive.jsonl`, `rollout-exec.jsonl`, `README.md`.
- `.ll/learning-tests/codex-rollout.md` — re-proven with the added claims.

### Dependent Files (must not change)
- `get_project_folder`/`get_sessions_folder`'s `Path | None` contract stays for `session_log.py:159-212`, `fsm/continuity.py:43`, `cli/session.py`, `cli/logs.py`, `cli/ctx_stats.py`, `hooks/session_start.py:162` (tests lock it: `test_session_log.py:26-95,384-458`, `test_fsm_continuity.py:53,61,82`, `test_ll_session.py:704`). No consumer is rewired in this issue.
- `cli/logs.py`'s `layout: HostLayout | None` parameters (`_has_ll_activity` 97, `_extract_cwd_from_project` 134, `_extract_ll_event_streams` 261) are untouched. `list_workspaces("claude-code")` must **not** import `_extract_cwd_from_project` from `cli/logs.py`: `cli/logs.py` already imports `host_layout_for` from `session_store`, so a `session_store → cli` import inverts the dependency direction and risks a cycle. Reimplement the cwd-from-first-record read locally in `sessions.py` (it is a `*.jsonl` glob skipping `agent-*`, then the first record's `cwd` field); ENH-3419 may then point `cli/logs.py` at the new helper when it rewires that module.
- Neither `scripts/little_loops/__init__.py` nor `.claude-plugin/plugin.json` needs a change for a new `session_store` module (confirmed).

### Conventions in Force
- Per-host dispatch is a literal-string `if`/`elif` chain or dict over a fixed host vocabulary (`get_project_folder` `user_messages.py:373-419`, `host_layout_for` `writers.py:2527-2604`); host discrimination is a bare `str` (no enum).
- Generator parsers: `from collections.abc import Iterator`, `yield`, malformed input → early bare `return`, never raise (`session_store/gemini.py:40-52`, `omp.py:54`).
- Uniform per-line JSONL resilience: `strip` → skip empty → `json.loads` in `try/except JSONDecodeError: continue`; per-file `OSError` caught and skipped (`user_messages.py:703-707`, `cli/ctx_stats.py:387-405`).
- `LLEvent` (`events.py:32`) / `LLHookEvent` (`hooks/types.py:21`) are the field-shape precedent for `SessionEvent`; `history_reader/models.py`'s `ts`-named dataclasses are a different (DB-row) convention and not the model.

### Tests
- **New** `scripts/tests/test_session_discovery.py` — promote the spike's 11 tests, then add: `host=None` union ordering across a fake `~/.claude` + `~/.codex`; `include_agents` on both hosts; `list_workspaces` for both hosts; `cwd` vs `cwd.resolve()` match on the sqlite path **and** the scan fallback; scan fallback finds a rollout placed under `archived_sessions/YYYY/MM/DD/` and orders it with `sessions/` rollouts by date; unusable-DB fallback — write garbage bytes to `state_1.sqlite` so `connect` succeeds and the `sqlite3.DatabaseError` fires at the first statement (this is the real failure point; a missing file or a schema mismatch are separate, already-covered cases); parser tests against both committed fixtures (header id/cwd/cli_version, oversized line 1, `turn_aborted` passthrough). Template for `SessionEvent`: `test_hook_intents.py::TestLLHookEvent`; for detect branches: `test_host_runner.py::TestResolveHost::test_detect_binary_probe_order`.
- `scripts/tests/test_user_messages.py:147` — rewrite `test_host_codex_probes_codex_projects` to assert the `None` contract; `:509` (`LL_HOOK_HOST=codex`) likewise.
- `scripts/tests/test_enh_3166_qwen_normalizer.py:232` — `test_registered_claude_shaped_hosts_get_projects_roots` asserts `host_layout_for("codex").projects_root == ~/.codex/projects`; move `codex` to the strict-`None` assertion alongside gemini/omp.
- `scripts/tests/test_session_log.py:386` (`test_get_current_session_jsonl_auto_detects_codex`) and `:461` (`test_append_session_log_entry_works_with_codex_host`) build a fake `~/.codex/projects/<encoded>/codex-session.jsonl` and expect `get_current_session_jsonl()` to resolve it under `LL_HOOK_HOST=codex`; after step 3 it returns `None`. Rewrite both to assert the `None`/no-op outcome (the `:448` "returns None for missing dir" test already passes and stays). No production behaviour changes: the directory never existed, so these tests were locking a path that never fired.
- `scripts/tests/test_ll_session.py` — add a `backfill --host codex` notice test.
- Fixture conventions to reuse: `conftest.py`'s `fixtures_dir`/`load_fixture`, autouse `_isolate_session_log_dir`; README shape after `scripts/tests/fixtures/streaming_parity/rebuild.sh`'s `WHEN TO RE-RUN:` block.
- Delete the spike directory once promoted (it has an isolation guard test asserting no production imports, which would be false after promotion).

### Documentation
- `docs/reference/API.md` — new `little_loops.session_store.sessions` entry (types, three functions, content-refusal rule, watch deferral).
- `docs/reference/HOST_COMPATIBILITY.md` — add a "session log readable via `detect_sessions`" row/column: claude-code ✓, codex ✓, others ✗ (ENH-3420); record the per-turn-usage finding from the capture.
- `docs/codex/usage.md` — short "Rollout files" subsection pointing at § Codex On-Disk Layout's facts.
- CLI docs and guides are ENH-3419's.

### Codebase Research Findings (integration-map verification)

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- `scripts/little_loops/session_store/writers.py:2591-2604` — `host_layout_for("codex").projects_root` evaluates *today* to a concrete `Path.home() / ".codex" / "projects"` (from the generic dict-literal tail shared with `claude-code`/`opencode`/`pi`), not `None` — confirmed by direct read. The Impact section's "already returned `None` in practice" refers to the functional outcome (the directory never exists, so downstream callers always get zero results), not the literal value; Step 3's change makes that `None` explicit at the source rather than leaving it as an always-empty glob target. The same generic tail also gives Codex Claude-shaped `HostLayout` defaults (`glob="*/subagents"`, `sessions_subdir=""`) that never match any real Codex path — these fields go unused once `projects_root` is `None`, no separate cleanup needed.
- `scripts/little_loops/cli/session.py:654-722` — the silent-zero-sessions behavior is confined to the **no-`--since` (full backfill) branch** (702-722): `get_project_folder(host=args.host)` returns `None` for Codex, so `full_jsonl_files`/`sessions_root` become `None`, and `backfill()`'s `if jsonl_files:`/`if sessions_root is not None and sessions_root.is_dir():` guards (`session_store/lifecycle.py:1107-1111`) skip silently, logging `Backfilled 0 rows` as if successful. The **`--since` branch** (654-699) is already non-silent: `get_project_folder()` returning `None` there hits an explicit `logger.error("No session project folder found; cannot discover JSONL files.")` + `return 1` (665-667) — host-agnostic, not Codex-specific, but not the silent path. The step-3 notice belongs in the full-backfill branch (~702-722); the `--since` branch's existing error already surfaces the problem and needs no new notice.
- `scripts/tests/spike/session_discovery_lifecycle/lifecycle.py` — confirmed current signatures ahead of promotion: `detect_sessions(cwd: Path, host: str, *, home: Path, limit: int | None = None)` — `host` is a **required positional `str`** (no union/`None` support) and `home: Path` is a **required keyword-only** parameter (not yet `Path.home()`); `SessionHandle` has no `is_agent` field; `list_workspaces` has no counterpart anywhere in the spike file. All three are the Decided-section additions Step 2 must make during promotion, absent from the spike as written today — matches the issue's own Spike Results "Not covered by the spike" note, with exact signatures for the diff.

## Program Design

_Revised 2026-09-08 (watch/stop dropped) and 2026-09-09 (host=None, is_agent, list_workspaces)._

### Types

- `SessionEvent`: frozen dataclass — `type: str`, `timestamp: str`, `host: str`, host-native `payload: dict[str, Any]`; no cross-host content normalization of `payload`
- `SessionHandle`: frozen dataclass — `host: str`, `session_id: str`, `path: Path`, `cwd: Path`, `updated_at: float` (epoch seconds), `is_agent: bool = False`; one per session file (a Codex rollout, a Claude Code `<uuid>.jsonl`). `cwd` is always the **caller's spelling** of the workspace, even when the Codex row matched on `cwd.resolve()` — so handles from both hosts compare equal on `cwd` for the same call
- `SessionEvent.payload` is typed `dict[str, Any]` (the spike's bare `dict` fails strict mypy)

### Signatures

- `list_workspaces(host: str, *, existing_only: bool = True, home: Path | None = None) -> list[Path]` — every cwd the host has recorded sessions for; empty for a host with no home. Claude Code: `projects_root` walk + a local cwd-from-first-record read (not `cli/logs.py`'s helper — see Dependent Files). Codex: `SELECT DISTINCT cwd FROM threads`, scan fallback over line-1 `cwd`s
- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` — sessions for a workspace, newest `updated_at` first; `host=None` unions all registered hosts; empty list when none (never raises for a missing host home). **`limit` applies once, after the cross-host merge** (global newest-N, not N per host). `home=None` → `Path.home()`; tests pass `tmp_path`. Claude Code: `home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))` computed locally (not `get_sessions_folder`, which ignores `home`) + `*.jsonl` glob, `agent-*` → `is_agent`. Codex: sqlite `threads` query (both `cwd` spellings) with a scan fallback over both `sessions/` and `archived_sessions/` date trees (both `cwd` spellings), per § Codex On-Disk Layout
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — typed events for one finished-or-growing file, read once from offset 0; dispatches to the per-host parser by `handle.host`; unknown host → no yield
- `parse_codex_rollout(path: Path) -> Iterator[SessionEvent]` — Codex parser; reads line 1 for `session_meta` (id, cwd, cli_version); bare `return` on a missing/unparseable header, matching the gemini/omp generator convention; docstring records the oversized-line-1 note and the per-turn-usage finding
- `parse_claude_transcript(path: Path) -> Iterator[SessionEvent]` — the existing Claude Code per-line read lifted verbatim; `payload` is the whole record
- Deferred, not in v1: `watch(handle) -> Iterator[SessionEvent]` / `stop(handle)`. `SessionHandle` carries `path` so a later `watch` needs no signature change above it

### Call Path

In this issue: tests → `list_workspaces` / `detect_sessions` / `iter_events` (`session_store/sessions.py`) → per-host parser. `get_project_folder`/`get_sessions_folder` keep their Path contract for every existing caller; `_get_codex_project_folder` returns `None` with a docstring pointing at `detect_sessions`. Production consumers (`extract_user_messages`/`extract_commands`, `_compute_cache_rate_from_jsonl`, `cli/logs.py`) are rewired in ENH-3419.

## Implementation Steps

> **Maintainer pre-flight — do this by hand before handing the issue to `ll-auto`/`ll-parallel`.** Step 1 cannot be automated: it needs an interactive `codex` TUI session, and it is the first time `codex-cli 0.152.1` runs against this `~/.codex` (every local rollout is ≤ 0.130.0, newest 2026-07-02; sqlite migrations at v31). Expect the run to migrate the state DB and possibly change the layout that § Codex On-Disk Layout describes. If anything there changes, refresh that section **and** re-run `/ll:confidence-check` before implementation starts. Until step 1 is done, AC #6 is unsatisfiable by automation.

1. **Prove the layout on the installed CLI.** Capture both fixtures per Testing → Fixture capture using `codex-cli 0.152.1`; sanitize per that section's list (home paths, tool outputs, `base_instructions.text`); write `scripts/tests/fixtures/codex/README.md` (original line-1 byte length, `cli_version`, per-turn-usage finding, agent-thread finding, archive-behaviour finding, re-capture rule). Re-prove `codex-rollout` with the added claims (Fixture capture item 3). Run `ll-verify-private-refs` on the fixture directory before committing.
2. **Promote the spike** to `session_store/sessions.py`: `SessionHandle` (+`is_agent`), `SessionEvent` (`payload: dict[str, Any]`), `list_workspaces`, `detect_sessions` (`host=None` union, post-merge `limit`, `include_agents`, dual `cwd` match on both Codex paths, `archived_sessions/` in the scan fallback), `iter_events`, `parse_claude_transcript`, `parse_codex_rollout`. Keep `home` as keyword-only `Path | None = None` → `Path.home()`, and make the Claude Code branch compute its project dir from `home` + the production `encode_project_path` on the **resolved** cwd (see Files to Modify). Drop the spike's redundant double sort in `_scan_date_dirs` (sort once on the `(YYYY, MM, DD)` tuple). Module docstring carries the content-refusal rule and the watch deferral. Register in `session_store/__init__.py`. Move the spike tests to `scripts/tests/test_session_discovery.py`, add the tests listed under Integration Map → Tests, delete the spike directory.
3. **Retire the dead Codex probe**: `_get_codex_project_folder` → `None` + docstring; `host_layout_for("codex").projects_root` → `None`; rewrite the two `test_user_messages.py` Codex tests, the `test_enh_3166_qwen_normalizer.py:232` `projects_root` assertion, and the two `test_session_log.py` Codex-dir tests (`:386`, `:461`); `cli/session.py backfill --host codex` notice + test. While here, retire the one failing claim in `.ll/learning-tests/codex.md` ("Codex reads a standalone project-local `.codex/*.toml` file for MCP server definitions" — `result: fail`, unrelated to rollouts), which lifts the −5 modifier the confidence check carries. `ll-learning-tests` has no per-claim retire (`prove`/`mark-stale`/`check`/`list`/`orphans`/`backfill-versions` only), so: hand-delete that one `- claim:` block from `.ll/learning-tests/codex.md`, then run `ll-learning-tests check` to confirm the record still parses and reports 0 failing claims. Do not `mark-stale codex` + re-`prove` — that re-litigates the MCP `config.toml` claims this issue does not touch.
4. **Docs**: `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/codex/usage.md`.
5. Verify: `python -m pytest scripts/tests/` green; `ruff`/`mypy` clean on the new module.

## Acceptance Criteria

- `little_loops.session_store.sessions` exports `SessionHandle`, `SessionEvent`, `list_workspaces`, `detect_sessions`, `iter_events`, `parse_claude_transcript`, `parse_codex_rollout` with the signatures in Program Design (including the keyword-only `home` override and post-merge `limit`); live `watch`/`stop` are absent and the handle type needs no change to add them. `sessions.py` imports nothing from `little_loops.cli`.
- `scripts/tests/test_session_discovery.py` never writes into the shared fake home: every test passes `home=tmp_path` (or monkeypatches `Path.home` to `tmp_path` itself).
- Per-host parsers share no content-level code above the interface; the refusal is stated in the module docstring.
- `detect_sessions(cwd)` with no host returns Claude Code and Codex handles for the same workspace interleaved newest-first; `include_agents=False` (default) excludes `agent-*` Claude sessions and Codex subagent threads, `True` includes them with `is_agent=True`.
- Codex sessions are discovered via the sqlite `threads` index (both `cwd` spellings, stale `rollout_path` rows dropped) with a date-dir scan fallback over both `sessions/` and `archived_sessions/` (both `cwd` spellings) that also triggers on a DB whose first statement raises `sqlite3.Error`; a test proves the two paths return the same handles for a fixture tree containing one archived rollout. `list_workspaces("codex")` returns the distinct cwds.
- `detect_sessions(cwd, "claude-code", home=tmp_path)` resolves the project dir under `tmp_path` from `encode_project_path(str(cwd.resolve()))` without calling `get_project_folder`/`get_sessions_folder`.
- `_get_codex_project_folder` and `host_layout_for("codex").projects_root` return `None`; `ll-session backfill --host codex` prints a notice naming ENH-3420.
- Two captured real-shape fixtures from `codex-cli 0.152.1` (one interactive with tool calls, one `exec` one-shot) are committed, sanitized per Testing → Fixture capture (no real home paths anywhere in the file; `ll-verify-private-refs` clean), with a README stating the `cli_version`-keyed re-capture rule, the per-turn-usage finding, the agent-thread finding, and the archive-behaviour finding; the `codex-rollout` learning test is re-proven against them with the added claims.
- All existing tests pass unmodified except the five that lock the dead `~/.codex/projects/` layout: `test_user_messages.py:147` and `:509`, `test_enh_3166_qwen_normalizer.py:232`, `test_session_log.py:386` and `:461` (each rewritten to the `None` contract, not deleted); the spike directory is removed.

## Impact

- **Priority**: P2 - prerequisite for ENH-3419, which makes goal 6's dataset export and goal 7's quality rollups cover Codex.
- **Effort**: Medium - promote a proven spike, add three small interface extensions, capture two fixtures, retire dead code. Rewiring consumers was the Medium-High part and moved to ENH-3419.
- **Risk**: Low-Medium - no production consumer changes here; the only behavioural change is `_get_codex_project_folder`/`projects_root` going `None`, which already returned `None` in practice. Codex discovery depends on a vendor-private sqlite schema, mitigated by the scan fallback and the learning test.
- **Breaking Change**: No.

## Confidence Check Notes

_History collapsed 2026-09-09._ Four passes on 2026-09-08/09 scored readiness 85 and outcome 28→33. Recurring concerns, all now addressed or moved: unfiled `HostLayout` follow-up (→ ENH-3420); no production lifecycle yet (spike since proven; promotion is step 2); change surface 0/25 (→ split into ENH-3419); `codex-rollout` learning test missing (registered and proven 2026-09-08, re-prove required per step 1); `unapplied_decision` cap on `extract_user_messages`/`_compute_cache_rate_from_jsonl` (those identifiers are now ENH-3419's and no longer appear in this issue's Files to Modify). Re-run `/ll:confidence-check` after this rescope.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-08; gaps corrected 2026-09-09._ ~15 `file:line` citations spot-checked against HEAD, all matching, including the `host_layout_for("codex").projects_root` → `~/.codex/projects` dead-path claim. The two gaps found (call-site count 9→11; unresolved raw-transcript-reader question) were corrected; both now live in ENH-3419. `ll-verify-evidence`: clean.

_Re-verified by `/ll:verify-issues --auto` — 2026-09-09 (after the second review pass)._ **Verdict: VALID.** Graph: provider=`codegraph`, freshness=`fresh`. Every citation added by the second pass checked against HEAD: `writers.py:2591-2604` generic `projects_root` tail, `test_enh_3166_qwen_normalizer.py:232`, `test_session_log.py:386`/`:448`/`:461`, `test_user_messages.py:147`/`:509`, spike signatures in `lifecycle.py` (`_query_threads_db` catches `sqlite3.Error` at both connect and first statement; `_scan_date_dirs` walks `sessions/` only and matches one `cwd` spelling; `_detect_claude_sessions` encodes the raw cwd), `encode_project_path` at `user_messages.py:362` with `get_project_folder` resolving at `:397`, `user_messages` lazy-importing `session_store` only inside functions (`:446`, `:1054`). External claims checked against openai/codex `main` via `gh api`: `codex-rs/rollout/src/lib.rs:84-85` (`SESSIONS_SUBDIR`/`ARCHIVED_SESSIONS_SUBDIR`), https://github.com/openai/codex/blob/main/codex-rs/thread-store/src/local/helpers.rs lines 64-68 (`rollout_path_is_archived`). Live `~/.codex`: `_sqlx_migrations` max 31, `threads` cli_version ∈ {0.98.0, 0.130.0}, zero archived/agent rows, no `archived_sessions/`. `ll-learning-tests` subcommands confirmed (`check`, `list`, `mark-stale`, `orphans`, `prove`, `backfill-versions` — no per-claim retire). Dependencies: `blocks: ENH-3419` ↔ ENH-3419 `blocked_by: FEAT-3417` consistent; ENH-3420 `relates_to` symmetric. Decisions log: no active required rules. `ll-verify-evidence`: clean (0 findings). Proposal-consequence check (B6): the three fixture-invalidation findings from the earlier pass (five tests locking the dead layout, `home` ignored by the Claude branch, connect-vs-first-statement) are now written into the issue itself, so the proposal as written no longer contradicts the code it names.

## Spike Results

_Added by `/ll:spike` on 2026-09-08_

| Risk | Proven by | Result |
|------|-----------|--------|
| No precedent for a `detect`/`iter_events` lifecycle | `TestDetectSessionsCodexSqlitePath`, `TestIterEventsDispatch` | ✓ |
| sqlite `threads` query + newest-`state_*.sqlite` selection | `test_detect_sessions_codex_uses_sqlite_when_present`, `..._picks_newest_state_db_by_name` | ✓ |
| Stale `rollout_path` rows leak | `test_detect_sessions_codex_filters_stale_rollout_paths` | ✓ |
| DB-absent / schema-mismatch fallback and ordering | `..._falls_back_to_date_scan_when_db_missing`, `..._falls_back_when_db_schema_mismatched`, `..._scan_orders_newest_date_dir_first` | ✓ |
| Cross-host parser contamination | `test_iter_events_dispatches_by_host_without_cross_contamination` | ✓ |
| Isolation guard | `test_lifecycle_module_has_no_production_imports` | ✓ |

**Spike location**: `scripts/tests/spike/session_discovery_lifecycle/` (11 tests pass). **Not covered by the spike** (added by 2026-09-09 review, to be covered in step 2): `host=None` union, `is_agent`/`include_agents`, `list_workspaces`, dual `cwd` match, unopenable-DB fallback.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-09 (post-split)_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

All hard overrides inert: `check-design` passes, no `blocked_by`, `codex-rollout` proven (7/0/0), `format-check` reports zero gaps (the `unapplied_decision` cap that held Ambiguity at 10/25 across the prior four passes is cleared — the flagged identifiers now live in ENH-3419). Outcome rose 33 → 75: change surface fell from 11+ callers to the 3–5 consumers of `host_layout_for("codex").projects_root` and the single caller of `_get_codex_project_folder`; complexity breadth fell to ~14 mechanical/local sites with the one moderate site (the new module) already proven by the spike.

### Concerns
- No Duplicate Implementations (10/20): `get_project_folder`/`HostLayout` remain related-but-parallel code; the spike is the promotion source, not a duplicate. Carries the −5 learning-test modifier from the `codex` target's one failing claim (an MCP `config.toml` assertion unrelated to rollout parsing) — verify or retire that claim to lift it.
- Architecture Compliance (15/20): the parallel `HostLayout` dispatch pathway persists until ENH-3420; justified and tracked, not resolved.
- Step 1's interactive fixture capture is a manual maintainer action (`codex`, not `codex exec`) that automation cannot perform; run it before handing the issue to `ll-auto`, and record the per-turn-usage and agent-thread findings it depends on. (Promoted to the pre-flight block at the top of Implementation Steps by review 2026-09-09.)

### Review 2026-09-09 (pre-implementation)

Six corrections folded in, all verified against HEAD and the live `~/.codex`: (1) fixture sanitization now covers home paths and tool outputs, since `ll-verify-private-refs`'s `abs_user_path` rule would reject a raw capture; (2) the test-isolation plan no longer relies on the shared read-only fake home — `home: Path | None = None` stays on the seam; (3) `list_workspaces` must not import from `cli/logs.py` (dependency inversion); (4) step 1 promoted to a maintainer pre-flight gate with a confidence re-check if the 0.152.1 run changes the layout; (5) `limit` post-merge semantics, `SessionHandle.cwd` spelling, and archive-behaviour capture specified; (6) failing `codex` learning-test claim retired in step 3, spike double-sort and `payload` typing cleaned on promotion, duplicate H3 renamed.

### Review 2026-09-09 (second pass, pre-implementation)

Five more, verified against HEAD, the live `~/.codex` (schema v31, 8,858 threads, all cli 0.98.0/0.130.0, zero `agent_role`/`thread_spawn_edges` rows, no `archived_sessions/`, no `state_6` — 0.152.1 has not run here yet) and openai/codex `main`: (1) frontmatter `verify_verdict: NON_VALID` was stale and failed `ll-issues check-verify-verdict` — re-verified; (2) Codex archives by **moving** the rollout to `~/.codex/archived_sessions/` and derives `threads.archived` from that path, so the scan fallback now walks both trees (§ Archived threads) instead of leaving it as a capture-time question; (3) the "only two tests change" AC undercounted — `test_enh_3166_qwen_normalizer.py:232` and `test_session_log.py:386`/`:461` also lock the dead `~/.codex/projects/` layout; (4) Program Design said the Claude Code branch used `get_sessions_folder`, which reads `Path.home()` and would have ignored the `home` override — it now computes the dir locally from `home` + `encode_project_path` on the **resolved** cwd, and the dual-spelling match is stated for the scan fallback too; (5) the unusable-DB test targets the first statement, not `connect` (which succeeds on garbage), and the learning-test claim retirement names the mechanism (hand-delete + `check`) since the CLI has no per-claim retire.

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-09T16:02:36 - `861a7bfd-cb99-4e5e-b348-13b72b2b1f2e.jsonl`
- `/ll:verify-issues` - 2026-09-09T15:16:42 - `01ac0527-014a-4819-be27-8ea9cf7de48d.jsonl`
- `review (manual, second pass: stale verify_verdict, archived_sessions/ in scan fallback, 3 more tests lock dead layout, Claude branch honours home + resolved cwd, first-statement DB error + claim-retire mechanism)` - 2026-09-09T14:30:00
- `review (manual, pre-implementation: fixture sanitization/private-refs, home kwarg test isolation, no cli import, pre-flight gate, limit/cwd/archive semantics, cleanups)` - 2026-09-09T09:10:00
- `/ll:refine-issue` - 2026-09-09T13:23:29 - `dcb191ce-b0ed-49a1-8abe-52afc4b02a5b.jsonl`
- `/ll:confidence-check` - 2026-09-09T05:35:57 - `09379bb8-4076-4f1a-b109-7ecd1a03c12f.jsonl`
- `review (manual, split → ENH-3419/ENH-3420; decided host=None/is_agent/list_workspaces; refreshed Codex facts to cli 0.152.1)` - 2026-09-09T05:30:00
- `/ll:confidence-check` - 2026-09-09T05:07:56 - `3b63284d-d89c-432c-a42d-046e5a5d958e.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T05:02:53 - `8b35aec6-fb50-40b3-b5f0-c9df0c9253f6.jsonl`
- `/ll:confidence-check` - 2026-09-09T04:59:39 - `cc274703-f2ea-4ddf-a916-516d38f11017.jsonl`
- `/ll:spike` - 2026-09-09T04:55:35 - `f28c7c94-a5ec-4bd6-8ffd-7e716bc73371.jsonl`
- `/ll:confidence-check` - 2026-09-09T04:42:48 - `f50721ed-199a-4145-9872-764076c5886d.jsonl`
- `/ll:verify-issues` - 2026-09-09T04:38:38 - `4a00b9f5-2c1a-4bb9-8901-1abcda8ab946.jsonl`
- `/ll:verify-issues` - 2026-09-09T04:36:35 - `a78c41f1-909c-4220-a4df-fe4ab8b7ba0c.jsonl`
- `review (manual, Codex layout corrections)` - 2026-09-09T04:28:06 - `a78c41f1-909c-4220-a4df-fe4ab8b7ba0c.jsonl`
- `/ll:wire-issue` - 2026-09-09T04:17:56 - `3577db8f-8723-4e0e-adb7-90253d958f56.jsonl`
- `/ll:decide-issue` - 2026-09-09T04:03:15 - `25e4ccb6-3e7e-49fc-a6ff-da7c10596c03.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:59:43 - `6a60b145-4b40-4e2a-b6c3-1f8fc4e6cbf8.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T03:48:29 - `4c0c2553-e582-4b1a-aac5-1daf99f32574.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:42:59 - `96a64da7-7e7c-4bdc-9e11-d16d6c8ed5d2.jsonl`
- `/ll:wire-issue` - 2026-09-09T03:26:48 - `0961ed9a-8a16-4f5b-b6df-7c9ad07e35e7.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:13:40 - `1bbd8d24-c939-4e16-a513-a2fcf919d545.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:03:58 - `184f5f10-ed2d-4c54-a9b0-aeaf09c80493.jsonl`
- `/ll:format-issue` - 2026-09-09T02:31:56 - `41091f97-0a07-455f-8f9a-e78193f9f4b8.jsonl`
