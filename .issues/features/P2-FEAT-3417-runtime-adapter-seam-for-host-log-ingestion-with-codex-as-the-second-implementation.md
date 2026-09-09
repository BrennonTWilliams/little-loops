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
outcome_confidence: 33
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 0
verify_verdict: NON_VALID
missing_artifacts: true
spike_attempted: true
spike_completed: true
---

## Summary

`ll-logs`, `ll-messages`, and `ll-ctx-stats` all reach directly for `~/.claude/projects/<munged-cwd>/`, and nothing in the tree parses a Codex rollout file. That is the observability half of goal 2 going unbuilt while the generation half is already done: `ll-adapt --host codex` ships today, so little-loops writes artifacts for Codex and then cannot read a single Codex session back. Every log-derived capability downstream — goal 6's dataset export, goal 7's quality rollups — silently covers one host while claiming to generalize.

Introduce a session-discovery seam, not a Codex feature. The interface is small and covers the lifecycle only: enumerate the sessions for a workspace, iterate their typed events (live `watch`/`stop` deferred to the first consumer that needs it — see § Live watch is deferred). Per-host parsers live behind it and share nothing above it. One implementation then serves `ll-logs`, `ll-ctx-stats`, and any future dashboard, the same way one extension point can serve a CLI and a UI without either knowing about the other.

## Current Behavior

`ll-logs`, `ll-messages`, and `ll-ctx-stats` each reach directly for `~/.claude/projects/<munged-cwd>/` — Claude Code's own JSONL session layout — with no seam between the CLI and the on-disk format. Nothing in the tree parses a Codex rollout file. `ll-adapt --host codex` already generates Codex-targeted artifacts, but no code reads a Codex session back, so a workspace driven by Codex is invisible to every log-derived command.

The tree's existing Codex "support" in this area is dead code: `_get_codex_project_folder` (`user_messages.py:458`), `host_layout_for("codex").projects_root` (`session_store/writers.py:2593`), and `test_host_codex_probes_codex_projects` (`scripts/tests/test_user_messages.py:147`) all probe `~/.codex/projects/<encoded>`, a directory Codex has never written (see § Codex On-Disk Layout below). `ll-session backfill --host codex` is therefore wired but always resolves zero sessions.

## Expected Behavior

A session-discovery interface exists covering the lifecycle only — enumerate the sessions for a workspace under a host, iterate their typed events — with per-host parsers living behind it. `ll-logs`, `ll-messages`, and `ll-ctx-stats` consume that interface instead of reaching for `~/.claude/projects/` directly, and a Codex rollout parser implements the same interface as the second host. A session started under Codex becomes observable through the same commands as one started under Claude Code, with no host-specific flag required.

## Codex On-Disk Layout (verified 2026-09-08 against a live `~/.codex`, cli_version 0.130.0)

_Added by review on 2026-09-08. Every claim below was checked against the real directory on the maintainer's machine (8,858 rollouts; 1,788 for this repo). This corrects the "working Codex path probe" premise carried by earlier refinement passes._

**Layout.** Codex writes one rollout per session at `~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-timestamp>-<uuid>.jsonl`, keyed by **date**, not by project. There is no `~/.codex/projects/`. The workspace is only recoverable from inside the file: `session_meta.payload.cwd` on line 1, and `turn_context.payload.cwd` on every turn. Consequence: sessions for one cwd are scattered across many date directories, so no single folder satisfies `get_project_folder`'s "Path containing `*.jsonl`" contract for Codex. Codex must not route through `get_project_folder`; the seam returns per-session file handles instead.

**Session index.** Codex also maintains `~/.codex/state_<N>.sqlite` (currently `state_5.sqlite`) with a `threads` table: `id`, `rollout_path`, `cwd`, `source`, `created_at`, `updated_at`, `tokens_used`, `cli_version`, `model`, indexed on `created_at`/`updated_at`. This is the cheap, authoritative index for "sessions for cwd X", but the filename version suffix and schema are vendor-private and unversioned from our side, so it cannot be the only path.

**Discovery strategy (decided):** `detect_sessions(cwd, "codex")` queries the newest `state_*.sqlite` `threads` table by exact `cwd` match, ordered by `updated_at` desc; if the DB is absent, unreadable, or lacks the expected columns, fall back to scanning `~/.codex/sessions/` date directories newest-first, reading only line 1 of each rollout and matching `payload.cwd`. Both paths return the same handle type. Every `rollout_path` from the DB is verified to exist before being returned (the DB can outlive deleted files).

**Record shape.** Every line is `{"timestamp": <ISO>, "type": <str>, "payload": {...}}`:

```
type: session_meta | turn_context | response_item | event_msg
session_meta.payload:   id, timestamp, cwd, originator, cli_version, source, model_provider,
                        base_instructions{text}  (inlined — 22 KB on line 1 in the sample)
turn_context.payload:   turn_id, cwd, model, approval_policy, sandbox_policy, ...
response_item.payload.type: message   (role: user|assistant; content: [{type: input_text|output_text, text}])
event_msg.payload.type:     user_message{message} | task_started | task_complete
```

Records are per-line parseable; the session id and cwd live only in the header line, so `parse_codex_rollout` is the gemini/omp whole-file-context case for identity and the qwen per-record case for everything else. The oversized-first-line hazard this issue's Testing section cites is real-shape here (`base_instructions` is inlined into `session_meta`); Python `open()` text iteration has no line ceiling, so the risk is a downstream consumer with a fixed buffer, not the parser itself — note it in the parser docstring.

**What the local corpus does NOT contain.** All 8,858 local sessions are `source = "exec"` one-shots (`codex exec`): zero `function_call`, zero `function_call_output`, zero `token_count`, zero reasoning items, and `tokens_used = 0` on every `threads` row. Interactive/TUI sessions with tool use and per-turn usage have a different payload vocabulary that has **not** been observed here. See Testing → Fixture capture.

## The seam is at the lifecycle, and is refused on content

Deliberately keep the seam at the lifecycle and refuse it on content. Tool-call shapes and token accounting do not overlap enough between hosts to justify a common abstraction, and forcing one produces a lowest-common-denominator record that is worse than two honest per-host ones.

Evidence from a visualizer that independently shipped two host integrations against the same two runtimes supports exactly this split. It introduced a four-method session-watcher interface *and* explicitly refused a shared tool summarizer in the same release, recording the reason in a header comment: the two runtimes' tool shapes don't overlap enough. Token counting followed the same rule in the other direction — Codex exposes authoritative token counts, so the estimator was deleted there; Claude Code exposes no equivalent field, so estimation stayed. Two runtimes, two strategies, no forced uniformity.

This is a real counterweight to the standing proposal for a declarative host-adapter schema — a host described as a YAML stanza with capability booleans. That proposal assumes hosts are uniform enough for one schema to describe them. The evidence from two hosts actually implemented is that the *lifecycle* generalizes cleanly and the *content* does not, which suggests the seam belongs at the watcher with per-host content code behind it, rather than at a schema that tries to describe the content. Weigh it when that design decision is actually made; it is not a refutation.

## Sequencing

Sequencing matters and should be stated in the issue rather than discovered during review: build the seam when the second implementation makes the duplication concrete, not in anticipation of it. Codex is that second implementation, so the seam is now earned. The reference implementation followed the same order — the first host was built with no abstraction at all, and the interface arrived only once the second host made the duplication real.

Keeping the Codex reader free of any UI-framework dependency is what lets one implementation serve `ll-logs`, `ll-ctx-stats`, and a future dashboard without modification.

### Live watch is deferred (review decision, 2026-09-08)

The original four-method interface (`detect_session`/`watch`/`stop`) was borrowed from a visualizer that has a live panel. Nothing in this issue's call path is live: `ll-logs sequences`/`extract`/`scan-failures`/`eval-export`, `ll-messages`, and `ll-ctx-stats` are all batch reads over finished files, and `ll-logs tail` tails loop event files, not host sessions. Option B's selection leaned on "the AC's live-watch requirement", which was the AC citing itself. v1 therefore ships the batch half only — `detect_sessions` (plural: `_collect_sequences` needs every session for a project, not "the active one") and `iter_events` — and leaves `watch`/`stop` for the first consumer that actually tails a host session (a dashboard). This removes the file-growth test harness the confidence check flagged as originated-from-nothing work. The interface must be shaped so `watch(handle)` can be added later without changing `detect_sessions`/`iter_events`.

## Testing

Test the Codex parser against a captured real-shape rollout fixture — actual JSONL from a real session, committed alongside the parser — not hand-minimized stubs. This is complementary to, not a substitute for, the scripted fake-host work: a fake host tests our handling of a sequence we chose, a captured fixture tests our parser against a record shape the vendor chose and can change under us without telling us.

Treat the fixture as perishable and re-capture it periodically. The concrete precedent: a vendor started inlining full base instructions into the first line of its rollout file, that line blew past a consumer's fixed 64KB read buffer, `cwd` extraction failed, and sessions were silently skipped — an empty panel with no error. Neither a scripted fake host nor the existing unit tests would have caught it; re-capturing the fixture would have.

### Fixture capture (added by review, 2026-09-08)

A fixture lifted from the local corpus covers only the `exec` one-shot vocabulary (`session_meta`, `turn_context`, `message`, `user_message`, `task_started`, `task_complete`). That is insufficient for AC #2 (per-host tool-call shapes and token accounting) and for `ll-logs`' tool-name/sequence paths. Required before the parser is considered tested:

1. Deliberately run one **interactive** Codex session in this repo (`codex`, not `codex exec`) that issues at least one shell tool call and one file read, then copy its rollout to `scripts/tests/fixtures/codex/rollout-interactive.jsonl`. Also commit one `exec` one-shot as `rollout-exec.jsonl` (both sanitized: strip `base_instructions.text` to a short placeholder, keep its key so the oversized-header code path is still exercised — record the original byte length in the fixture README).
2. While capturing, **confirm whether rollout files carry per-turn usage at all.** `docs/reference/HOST_COMPATIBILITY.md`'s `[^tok-codex]` footnote proves usage only on the `codex exec --json` stdout stream (`turn.completed`), not in the rollout file. If the rollout has no `token_count`-style event, `ll-ctx-stats` for Codex is scoped as "returns no cache rate" (see Implementation Steps) and the decision is recorded in the parser docstring, not left for the next reader to rediscover.
3. **Perishability marker = the learning test.** Register a new learning-test target `codex-rollout` (`.ll/learning-tests/codex-rollout.md`, via `/ll:explore-api` or `/ll:spike`) whose assertions are the layout and record-shape claims in § Codex On-Disk Layout, stamped with the `cli_version` read from the captured `session_meta`. The fixture README's re-capture rule is then mechanical: "re-run `ll-learning-tests prove codex-rollout` and re-capture both fixtures whenever `codex --version` differs from the `cli_version` recorded here." This replaces inventing a calendar-based convention, which has no precedent in the tree. The existing `codex` learning-test record covers MCP `config.toml` shape only and does not stand in for this.

## Relations

Relates to the session-id minting work, which fixes run↔transcript pairing precision above this layer, and to the declarative host-adapter schema proposal discussed above.

## Use Case

**Who**: A little-loops maintainer running `ll-logs` or `ll-ctx-stats` against a workspace.

**Context**: The active coding session in that workspace was started via `ll-adapt --host codex` (Codex CLI) rather than Claude Code, so its session data lives in a Codex rollout file, not `~/.claude/projects/`.

**Goal**: Run `ll-logs` (or `ll-ctx-stats`) unmodified and get session activity for the Codex session, the same way it already works for a Claude Code session.

**Outcome**: The command detects the Codex rollout file for the workspace, watches it through the session-watcher interface, and reports activity — no host-specific flag or separate tool required. Goal 6's dataset export and goal 7's quality rollups then cover both hosts instead of silently covering Claude Code only.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

Research surfaced a real fork this issue does not yet resolve. A per-host content-parsing seam already exists (`session_store/writers.py`'s `HostLayout.normalize`/`normalize_file`, covering `qwen`/`gemini`/`omp`), and it takes the opposite position from this issue's stated design: those three normalizers translate host-native records *into a shared Claude-shaped record* ("yields Claude-shaped `user`/`assistant` records" — `gemini.py`, `omp.py` docstrings), whereas this issue explicitly refuses a shared content abstraction. Codex has no entry in that seam today (falls through to `normalize=None`), so both routes below are live options, not merely hypothetical.

**Option A**: Extend the existing `HostLayout` seam with a Codex `normalize`/`normalize_file` entry that translates Codex rollout records into the existing Claude-shaped record schema, then let `extract_user_messages`/`_compute_cache_rate_from_jsonl` consume that already-normalized stream unchanged (no new `SessionEvent`/`detect_session`/`watch` types). Reuses `_iter_events`/`_backfill_raw_events`, already wired end-to-end for `ll-session backfill --host codex` at the CLI layer. Lowest new-surface-area option, but inherits the "unify to Claude shape" convention this issue's own "seam is refused on content" section argues against, and it does not by itself give `ll-logs`/`ll-ctx-stats` a live-watch capability — only backfill-shaped batch reads.

**Option B**: Build the session-watcher interface as specified in `## Program Design` (`detect_session`/`watch`/`stop`, `SessionEvent` carrying a host-native `payload` dict, `parse_codex_rollout` as the second implementation), independent of `HostLayout`. Keeps per-host content genuinely separate as the issue's design section argues for, and adds the live-watch capability (`watch(handle) -> Iterator[SessionEvent]`) that `HostLayout` was never built for — but leaves two parallel per-host dispatch mechanisms in the codebase (`HostLayout` for backfill, the new watcher for `ll-logs`/`ll-ctx-stats`) unless a follow-up unifies them, and duplicates the Codex path-detection `get_project_folder`/`get_sessions_folder` already provide.
> **Selected:** Option B — Option A's own agent-verified evidence shows `extract_user_messages`/`_compute_cache_rate_from_jsonl` never call `HostLayout.normalize` today (the `HostLayout` seam is batch/backfill-only, exercised only by `_iter_events`'s cursor-replay path), so Option A cannot satisfy the Acceptance Criteria's live-watch requirement without inventing the same lifecycle Option B proposes anyway; Option B is also the only option consistent with this issue's own "seam is refused on content" design section.

**Recommended**: Option B for v1, per the issue's own "seam is refused on content" rationale (§ above) and because it is the only option that gives `ll-logs`/`ll-ctx-stats` the live-watch behavior the Acceptance Criteria and Use Case describe — Option A only solves batch backfill. The `HostLayout`/new-watcher duplication this leaves behind is worth a follow-up issue, not a blocker for this one.

### Review corrections to the analysis above (2026-09-08)

Option B stands, but two of the facts both options were scored on were wrong and one justification was circular:

- **"`ll-session backfill --host codex` is already wired end-to-end"** — wired, but non-functional: `host_layout_for("codex").projects_root` points at `~/.codex/projects/`, which does not exist (§ Codex On-Disk Layout). Option A's "zero new CLI plumbing" advantage was therefore illusory; it would have needed the same discovery work.
- **"`get_project_folder` already has a working Codex path probe that `detect_session` would duplicate"** — the probe never resolves. There is nothing to duplicate; the Codex discovery path is net-new either way, and `get_project_folder`'s folder contract cannot express Codex's date-keyed layout at all.
- **"Option B is the only option that satisfies the AC's live-watch requirement"** — no consumer in the call path is live (see § Live watch is deferred). Option B is still correct on the content-refusal ground alone; the live-watch ground is withdrawn and `watch`/`stop` are dropped from v1.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-08.

**Selected**: Option B — standalone session-watcher interface (`detect_session`/`watch`/`stop`, `SessionEvent`, `parse_codex_rollout`)

**Reasoning**: Two parallel `ll:codebase-pattern-finder` agents independently verified that Option A's central premise does not hold — `extract_user_messages` and `_compute_cache_rate_from_jsonl` never call `host_layout_for(...).normalize` today, so the `HostLayout` seam is batch/backfill-only (only `_iter_events`'s cursor-replay path invokes `.normalize`) and gives no live-watch path for `ll-logs`/`ll-ctx-stats` — meaning Option A cannot meet the Acceptance Criteria's watch requirement without building the same lifecycle Option B already proposes. Option B also directly matches the issue's own "seam is refused on content" design section, whereas Option A repeats the qwen/gemini/omp convention of unifying content into a shared Claude-shaped schema, which that section explicitly argues against.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (extend HostLayout) | 1/3 | 2/3 | 2/3 | 1/3 | 6/12 |
| Option B (session-watcher interface) | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**: The rejected approach reuses a 3x-repeated `HostLayout.normalize`/`normalize_file` convention (qwen/gemini/omp) and needs zero new CLI plumbing for `ll-session backfill --host codex` (already wired end-to-end), but that convention unifies content into a shared schema — contradicting this issue's own design section — and is never consumed by `ll-logs`/`ll-ctx-stats` today, leaving the AC's live-watch requirement unmet. The selected approach has no `detect`/`watch`/`stop` lifecycle trio precedent anywhere in the tree (zero hits repo-wide), so it introduces genuinely new abstractions and duplicates `get_project_folder`/`get_sessions_folder`'s existing Codex path detection — but `SessionEvent` has a direct field-for-field precedent in `LLEvent`/`LLHookEvent`, its parser's generator shape matches the `gemini.py`/`omp.py` convention exactly, and it is the only approach that actually satisfies the Acceptance Criteria and matches the issue's stated per-host-content design.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

Concrete files, callers, and conventions this issue's implementer needs, grouped below.

### Files to Modify
- `scripts/little_loops/cli/messages.py` (`main_messages`, calls `get_project_folder(cwd)` at line 173 with **no `host=` kwarg**, then `extract_user_messages(project_folder, ...)` at line 192) — always resolves the Claude Code project folder regardless of the actual running host; rewired per Option B (Decision Rationale) to obtain sessions via `detect_sessions(cwd, host)` / `iter_events` (Program Design → Call Path) rather than a bare `get_project_folder` call
- `scripts/little_loops/user_messages.py` (`extract_user_messages`, line 638) — takes only `project_folder`/`limit`/`since`/`include_agent_sessions`/`include_response_context`, no `host` parameter; globs `*.jsonl` and parses every record against the Claude Code schema via `_parse_user_record` (line 858). This function and its sibling `extract_commands` (line 721) are the Option-B call-path consumers named in Program Design → Call Path and Implementation Step 4 — retained here as the functions to rewire onto `detect_sessions`/`iter_events`, not leftover Option-A text
- `scripts/little_loops/cli/ctx_stats.py` (`_compute_cache_rate_from_jsonl`, line 342; called from `main_ctx_stats` at line 753 with no `host=`) — calls `get_sessions_folder(cwd)` without `host=`, so it inherits whatever `LL_HOOK_HOST` resolves to; parses `record["message"]["usage"]` fields that are Claude Code-specific. Rewired per Option B to dispatch through `detect_sessions`/`iter_events`, with Codex usage read by a separate Codex-only reader (Implementation Step 5) rather than a shared normalizer

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` (module docstring, line 1, frames the whole file as reading only the Claude Code session-log root) — this IS `ll-logs`, the file AC #4 names, and it was absent from "Files to Modify" entirely. It has 11 direct, un-hosted `get_project_folder(...)` calls across 6 functions — `_collect_sequences` (lines 653, 658, 667), `_cmd_sequences` (693), `_cmd_extract` (774, 783), `_collect_failure_clusters` (1353, 1358, 1367), `_cmd_scan_failures` (1554), `_cmd_eval_export` (2032) — none pass `host=`, confirmed by grep (no `--host` CLI flag exists anywhere in this file's argparse). Beyond folder resolution, the Claude-schema-coupled content functions `_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error` all branch on `record["type"]`/`message.content[*].type` — these must either gain a per-host equivalent behind the new interface or be explicitly scoped out as Claude-Code-only for this issue's v1 (the issue does not currently state which).

### Dependent Files (Callers/Importers)
- `get_project_folder`/`get_sessions_folder` (`user_messages.py:373`, `:422`) are imported by: `session_log.py:15`, `fsm/continuity.py:22`, `cli/logs.py:35`, `cli/ctx_stats.py:34`, `cli/session.py:71`
- `extract_user_messages` (`user_messages.py:638`) has exactly one production caller: `cli/messages.py:192` (import at `:30`)
- `_compute_cache_rate_from_jsonl` (`cli/ctx_stats.py:342`) has exactly one production caller: `main_ctx_stats` at `cli/ctx_stats.py:753`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/session_start.py:162` — `_pf = get_project_folder(cwd)` with no `host=` kwarg, even though the enclosing block already has the correct value in scope: `event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` is computed two lines later (line 178) to stamp the separate backfill-worker subprocess. The same `event.host` fallback should resolve `_pf` too — today it silently depends on ambient `LL_HOOK_HOST` matching the event's actual host.
- `scripts/little_loops/cli/backfill_worker.py:57,59` — local `from little_loops.session_store import host_layout_for` + call site; a second, previously unlisted consumer of `host_layout_for` alongside `_backfill_raw_events`/`_iter_events`/`cli/session.py`.
- `.loops/ll-logs-telemetry-digest.yaml:66` — a built-in FSM loop's `scan_failures` state greps `ll-logs scan-failures`'s stderr for the literal string `"No session project folder found"` to distinguish "no session data" from a real failure (`FAILURES_NO_DATA` vs `FAILURES_ERROR`). If the session-watcher rewire changes this message's wording, this loop's branch stops matching and silently falls through to the JSON-count branch on empty/errored output — a gate consumer, confirmed as the only place in the tree (tests included) keyed on this exact string.
- `commands/loop-suggester.md` (lines 740-768) and `skills/ll-loop-suggester/SKILL.md` (lines 303-309, 408, 631, 650) — `/ll:loop-suggester --from-sequences` shells out to `ll-logs sequences --json` directly as a documented telemetry source; verify it picks up Codex-sourced n-grams once `_collect_sequences` is rewired, since today it silently covers Claude Code only.

_Second wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py:664,702,718` (`main_session()`'s `backfill` subcommand) — calls `get_project_folder(host=args.host)` twice and treats the return as a bare `Path`: `(project_folder / host_layout_for(...).sessions_subdir).glob("*.jsonl")` (671-675, 704-708), then passes it through as `sessions_root=project_folder` into `session_store.backfill()`. Locks in a constraint: `get_project_folder`'s Path-returning signature must not change for this consumer; test coverage at `scripts/tests/test_ll_session.py:704` patches it directly.
- `scripts/little_loops/user_messages.py:721` (`extract_commands`) — an undocumented sibling of `extract_user_messages` with the identical `project_folder.glob("*.jsonl")` pattern (line 748-749) and the same sole caller, `cli/messages.py` (called at line 201-207, right after `extract_user_messages` at 192-198). The issue's plan rewires `extract_user_messages` through `detect_session`/`watch` but never mentions `extract_commands` — left as-is, a Codex session would get its user messages extracted but not its commands.
- `scripts/little_loops/session_log.py:159-212` (`get_current_session_jsonl`/`get_current_session_id`, wrapping `get_sessions_folder` as a bare `Path`) and `scripts/little_loops/fsm/continuity.py:43` (`summarize_completed_state`, same pattern) are outside this issue's Call Path but depend on the same `get_sessions_folder` contract. Downstream of `session_log.py`: `fsm/executor.py` (prompt-mode payload's `session_jsonl` stamp), `parallel/orchestrator.py` (`session_id` stamp on `parallel_merge_fallback` events), `advisor.py::resolve_task_key()` (fallback `TaskKey`), `issue_lifecycle.py::_session_id_or_none()`. None of these need modification, but `get_project_folder`/`get_sessions_folder`'s Path-returning signature must stay stable for all of them — test coverage locking this in: `scripts/tests/test_session_log.py:26-95,384-458`, `scripts/tests/test_fsm_continuity.py:53,61,82`.
- Four uncoordinated raw-transcript readers exist outside `get_project_folder`/`detect_session`'s reach entirely, all keyed on a hook payload's `transcript_path` rather than host+cwd resolution: `scripts/little_loops/hooks/session_start.py:150-161` (primary branch when `transcript_path` is present, bypassing `get_project_folder` — only the fallback at line 162 goes through it, already flagged above), `scripts/little_loops/cli/backfill_worker.py:52-53` (single-file JSONL read for that same transcript_path case, no `HostLayout` involved), `scripts/little_loops/hooks/pre_compact.py:108,112-120` (reads the transcript tail directly for the rubric-gate compaction-timing decision), `hooks/scripts/context-monitor.sh:49,316-317,343-347` (bash hook, tails the transcript file for model detection and a token-count baseline). None of these route through the new session-watcher interface; needs an explicit scope call (see Wiring Phase below).

### Conventions in Force
- Per-host path/layout resolution in this codebase is a literal-string `if`/`elif` chain over a fixed host vocabulary, not a registered adapter table — evidence: `get_project_folder` (`user_messages.py:373-419`, dispatches to `_get_claude_project_folder`/`_get_codex_project_folder`/etc.), `host_layout_for` (`writers.py:2527-2604`)
- `get_project_folder`/`get_sessions_folder` are already host-parameterized, and `_get_codex_project_folder` (`user_messages.py:458`) probes `~/.codex/projects/<encoded>` using the same dash-encoding (`encode_project_path`, line 362) as Claude Code — **but that directory does not exist; Codex is date-keyed under `~/.codex/sessions/` (§ Codex On-Disk Layout), so the probe always returns `None`.** `host` defaults from `os.environ.get("LL_HOOK_HOST", "claude-code")` when not passed explicitly (line 395). Two gaps, then: discovery (no code in the tree can find a Codex session for a cwd) and content (`extract_user_messages` and `_compute_cache_rate_from_jsonl` never receive or forward a `host` value, so they always assume Claude Code's JSONL schema).
- The three existing per-host content parsers (`session_store/qwen.py:normalize_qwen_record`, `gemini.py:normalize_gemini_session`, `omp.py:normalize_omp_session`) all normalize *into a shared Claude-shaped record* rather than keeping a per-host content type — evidence: `gemini.py` and `omp.py` module docstrings both state the normalizer "yields Claude-shaped `user`/`assistant` records". This is the opposite of this issue's stated design ("refuse [a shared abstraction] on content"); see Proposed Solution → Codebase Research Findings for the resulting decision point.
- Uniform per-line JSONL resilience: `line.strip()` → skip empty → `json.loads` inside `try/except json.JSONDecodeError: continue`; whole-file `OSError` caught per-file and skipped, never raised — evidence: `user_messages.py:703-707`, `cli/ctx_stats.py:387-405`, `session_store/writers.py` `_iter_events`. No line-length guard exists anywhere in these paths (plain `open()` text iteration has no ceiling, unlike `asyncio.StreamReader`'s 64KB default) — directly relevant to this issue's cited oversized-first-line failure mode.
- Host discrimination is always a bare `str` field/attribute (`HostRunner.name`, `HostLayout.name`, `LLHookEvent.host`) — no `Host` enum or `Literal[...]` type exists anywhere in `scripts/little_loops/` to constrain these values.
- Two separate, unrelated host knobs already coexist: `LL_HOST_CLI`/`orchestration.host_cli` (which CLI *binary* `resolve_host()` invokes, `host_runner.py`) vs. `LL_HOOK_HOST` (which session-log *layout* `get_project_folder`/`get_sessions_folder` probe) — they are read independently and are not unified.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` already has a partial, narrower precedent for host-plumbing that the new seam should build on rather than duplicate: `_has_ll_activity` (line 97), `_extract_cwd_from_project` (134), and `_extract_ll_event_streams` (261, called from `_cmd_sequences` at 676) all take an optional `layout: HostLayout | None = None` and defer to `effective.normalize` when given one — but default to `host_layout_for("claude-code")` when `None`, the same un-hosted-default shape as the 9 bare `get_project_folder()` calls above. `_collect_failure_clusters` also has a second caller beyond `_cmd_scan_failures` — `_cmd_fleet_review` (line 2843) — that must be covered by the same rewire.

_Second wiring pass added by `/ll:wire-issue`:_
- Module registration precedent, if the new session-watcher module lands under `session_store/`: `session_store/__init__.py` eagerly imports each per-host sibling (`normalize_gemini_session`, `normalize_omp_session`, `normalize_qwen_record`/`qwen_skip_at_ingest`, lines 67/91/100) and re-exports them via its explicit `__all__` (176-283); `writers.py:2559,2572`'s `host_layout_for()` also lazily imports the same normalizers as a second, narrower registration point. Neither `scripts/little_loops/__init__.py` (imports only `SQLiteTransport`/`record_issue_snapshot`/`record_session_lifecycle_event` from `session_store`, no per-host parser by name) nor `.claude-plugin/plugin.json` (no Python-module registration section at all) needs a change for a new module — confirmed, not just assumed.

### Tests
- `scripts/tests/test_cli_ctx_stats.py` — `TestComputeCacheRateFromJsonl` class (lines 676-974) is the existing coverage for `_compute_cache_rate_from_jsonl`; includes `test_resolves_qwen_chats_transcript` (:937) and `test_resolves_gemini_chats_transcript` (:974), which set `LL_HOST_CLI`/`LL_HOOK_HOST` env vars and build the host's real directory layout under `tmp_path` — the closest existing template for a Codex-equivalent test
- `scripts/tests/test_user_messages.py` — `test_host_codex_probes_codex_projects` (:147) and a second `LL_HOOK_HOST=codex` test (:509) cover only the static `get_project_folder`/`get_sessions_folder` path probe for Codex; there is no existing test that parses Codex message *content*
- `scripts/tests/test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py` — existing per-host normalizer test pattern; `test_enh_3393_gemini_normalizer.py` reads a committed fixture from `scripts/tests/fixtures/gemini/session.jsonl`, but that fixture is explicitly documented as hand-synthesized ("Verified 2026-09-06 against gemini-cli 0.46.0", `gemini.py:29`), not a sanitized real capture — no fixture in this codebase today is a genuine vendor capture, and no "perishable"/re-capture marker convention exists anywhere in the tree
- No committed Codex rollout fixture exists under `scripts/tests/fixtures/` today (searched, zero matches)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` (6587 lines; confirmed sole test file for `cli/logs.py`) — `TestSequences`/`TestArgumentParsingSequences` (797-1339), `TestExtract` (1547-2127), `TestScanFailures` (2924-4155), `TestEvalExport`/`TestEvalExportMapping`/`TestEvalExportRoundTrip` (4437-4841) cover all 6 functions named above, but every fixture helper (`_make_project_dir`, one per class) hard-codes the Claude Code layout and patches only `pathlib.Path.home` — none sets `LL_HOOK_HOST` or passes `host=`. Closest host-aware template to follow: `test_cli_ctx_stats.py`'s `test_resolves_qwen_chats_transcript`/`test_resolves_gemini_chats_transcript` (909, 941), which drive the real resolution chain via `monkeypatch.setenv("LL_HOOK_HOST", ...)` rather than patching the resolver function directly.
- `scripts/tests/test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` has no Codex-equivalent of its qwen/gemini host-resolution tests (grep for `codex` in this file: zero hits) — a third pair (`test_resolves_codex_*_transcript`) is the template gap for `_compute_cache_rate_from_jsonl`.
- No test anywhere in the repo appends bytes to a real on-disk file and asserts a watcher/tailer observes the new content (`cli/logs.py`'s own `_cmd_tail` tests mock `readline()`/`open()` entirely — `TestTail`, lines 639-742). _Moot for v1 since `watch()` is deferred (§ Live watch is deferred); retained as the cost estimate for whichever follow-up adds it._
- The issue's "fixture marked as perishable, re-capture periodically" convention has no precedent anywhere in `scripts/tests/fixtures/` (confirmed by repo-wide search) — the closest existing convention is a real-vs-synthesized *docstring disclosure* (`test_enh_3166_qwen_normalizer.py:18-19` states its fixtures are sanitized real captures; `gemini.py:29-30` and `test_enh_omp_normalizer.py:26-29` state theirs are hand-synthesized, not captures). The perishability/re-capture-cadence marker itself must be originated by this issue's implementation, not copied from an existing file.

_Second wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py::TestLLHookEvent` (`hooks/types.py:21`) is a closer test template for `SessionEvent` than `test_events.py::TestLLEvent` (the issue's cited precedent for `SessionEvent`'s *shape*) — `LLHookEvent`, like `SessionEvent`, carries a `host` discriminator plus optional fields, and its test class adds `test_host_required`, `test_to_dict_skips_none`, and `test_from_dict_accepts_timestamp_alias`, none of which `TestLLEvent` needs.
- `scripts/tests/test_host_runner.py::TestResolveHost::test_detect_binary_probe_order`/`test_raises_when_no_host` (`host_runner.py`) — template for testing `detect_session`'s None-vs-handle branches by mocking the filesystem probe and asserting which result comes back, distinct from the already-cited qwen/gemini transcript-resolution tests (which resolve a path, not a handle-or-None).
- `scripts/tests/test_transport.py::TestUnixSocketTransport::test_close_unlinks_socket_file` (line 427) — template for testing `stop(handle) -> None` actually releases a resource (assert via `Path.exists()`), not just that the call doesn't raise; no existing watch/tail test does this.
- `scripts/tests/conftest.py` conventions to reuse rather than reinvent: the `no_parallel` marker (xdist-sensitive tests, relevant if `watch()` tests touch real filesystem events under worker contention), the `fixtures_dir`/`load_fixture` helpers (a Codex fixture would resolve via `fixtures_dir / "codex" / "rollout.jsonl"` through these), and the autouse `_isolate_session_log_dir` fixture (patches `Path.home` so `detect_session`/`watch` tests don't race a real `~/.claude` or `~/.codex` directory).
- Closest structural template for the required "perishable fixture" marker: `scripts/tests/fixtures/streaming_parity/rebuild.sh`'s `WHEN TO RE-RUN:` trigger-list block (plus `PRE-CONDITIONS:`/`USAGE:`) and its README's "Synthetic vs Real Recordings" section — closer in shape than any per-host normalizer fixture, though neither is a calendar/staleness-based precedent (both are triggered-by-upstream-change).

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — per-host capability matrix; does not yet document session-log/rollout-file reading, only CLI-invocation capabilities
- `docs/codex/usage.md` — documents `LL_HOST_CLI=codex`/`resolve_host()` detection and `ll-adapt --host codex`, but has no mention of the Codex rollout file format
- `docs/reference/API.md` — module reference for `user_messages.py` and `session_store`; would need a new entry for the session-watcher module

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`### ll-logs` section) — opens "Discover and extract ll-relevant JSONL entries from Claude Code session logs," the authoritative CLI doc's own Claude-Code-only framing.
- `docs/guides/HISTORY_SESSION_GUIDE.md` (§"Session Log Tooling (`ll-logs`)", ~line 503) — describes `ll-logs` purely in terms of the host's session JSONL with no host-branching language.
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` (lines 10, 81, 429-454) — "`ll-messages` extracts these from your Claude Code session logs," plus the `ll-logs sequences`-driven loop-suggestion section.
- `docs/guides/EXAMPLES_MINING_GUIDE.md` (lines 146, 421) — "session logs from Claude Code session logs" framing and a table row naming the Claude-Code-specific session path as `ll-messages`'s source.

_Second wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:3552` (`### ll-messages` section) — opens "Extract user messages from Claude Code session logs," Claude-Code-only phrasing in a section not previously flagged (the earlier pass only caught `### ll-logs`). `### ll-ctx-stats` and `### ll-session` are already host-agnostic in this file — no change needed there.

## Program Design

_Revised by review on 2026-09-08: `detect_session`/`watch`/`stop` replaced by the batch pair below (see § Live watch is deferred); Codex discovery specified (see § Codex On-Disk Layout)._

### Types

- `SessionEvent`: frozen dataclass carrying `type: str`, `timestamp: str`, `host: str`, and host-native `payload: dict[str, Any]` — no cross-host content normalization of `payload`
- `SessionHandle`: frozen dataclass carrying `host: str`, `session_id: str`, `path: Path`, `cwd: Path`, `updated_at: float`; one per session file (a Codex rollout, a Claude Code `<uuid>.jsonl`)

### Signatures

- `detect_sessions(cwd: Path, host: str, *, limit: int | None = None) -> list[SessionHandle]` — every session for a workspace under the given host, newest `updated_at` first; empty list when the host has none (never raises for a missing host home). Claude Code: wraps `get_sessions_folder` + `*.jsonl` glob (excluding `agent-*`). Codex: sqlite `threads` query with date-dir scan fallback, per § Codex On-Disk Layout
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — typed events for one finished-or-growing file, read once from offset 0; dispatches to the per-host parser by `handle.host`
- `parse_codex_rollout(path: Path) -> Iterator[SessionEvent]` — Codex-specific parser behind the interface; the second implementation alongside the existing Claude Code JSONL reader. Reads line 1 for `session_meta` (id, cwd, cli_version); bare `return` on a missing/unparseable header, matching the gemini/omp generator convention
- `parse_claude_transcript(path: Path) -> Iterator[SessionEvent]` — the existing Claude Code per-line read, lifted verbatim behind the same signature as the first implementation
- Deferred, not in v1: `watch(handle) -> Iterator[SessionEvent]` / `stop(handle)`. `SessionHandle` carries `path` so a later `watch` needs no signature change above it

### Call Path

`extract_user_messages` / `extract_commands` (`user_messages.py`), `_compute_cache_rate_from_jsonl` (`cli/ctx_stats.py`), and `cli/logs.py`'s six `get_project_folder()` callers -> `detect_sessions` / `iter_events` (new module `session_store/sessions.py`) -> per-host parser (`parse_codex_rollout` for Codex; `parse_claude_transcript` for Claude Code). `get_project_folder`/`get_sessions_folder` keep their Path contract for their other callers (`session_log.py`, `fsm/continuity.py`, `cli/session.py`); `_get_codex_project_folder` is changed to return `None` with a docstring pointing at `detect_sessions`, and its test is rewritten to assert that

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Existing precedent for `SessionEvent`: `little_loops.events.LLEvent` (`events.py:32`) is field-for-field the same shape already proposed — `type: str`, `timestamp: str`, `payload: dict[str, Any] = field(default_factory=dict)`, plus `to_dict()`/`from_dict()` — but it is a mutable `@dataclass`, not frozen, and serializes `timestamp` to a `"ts"` wire key while keeping the `timestamp` attribute name. `little_loops.hooks.types.LLHookEvent` is a documented sibling of `LLEvent` with the same field shape plus `host`/`intent`. Either is closer prior art than an ad hoc new dataclass; `history_reader/models.py`'s bare `ts`-named dataclasses are a *different* convention reserved for read-only DB-row types, not wire/event objects, and should not be the model for `SessionEvent`.
- No `detect`/`watch`/`stop` lifecycle trio exists anywhere in `scripts/little_loops/` today (searched repo-wide). The closest partial analogs: `HostRunner.detect() -> bool` (`host_runner.py`, nine implementations) answers a different question (is this host's CLI binary present) than the proposed `detect_session(cwd, host) -> SessionHandle | None` (is there an active session file for this workspace); `fsm/host_guard.py`'s `stop()` releases an unrelated lock, not a session-watch resource; a live-tail idiom exists (`cli/logs.py:896`, `_cmd_tail`: `f.seek(0, 2)` then `readline()`/`sleep(0.1)`/print loop) but is CLI-local (prints directly) and not a reusable `Iterator`-returning function — it is the shape a `watch()` implementation would need to generalize, not something it can call directly.
- `get_project_folder(cwd, *, host=None) -> Path | None` (`user_messages.py:373`) and `get_sessions_folder(cwd, *, host=None) -> Path | None` (`:422`) already implement the `detect`-half of this issue's lifecycle for eight hosts including Codex (`_get_codex_project_folder`, `:458`, resolves `~/.codex/projects/<encoded>`) — a new `detect_session` would either wrap these or duplicate them; the issue's premise that no host-aware detection exists is true only for `extract_user_messages`/`_compute_cache_rate_from_jsonl`, not for path resolution itself.
- The per-record vs. whole-file parsing fork that `session_store/writers.py`'s `HostLayout.normalize`/`normalize_file` resolves per-host (qwen: per-record; gemini/omp: whole-file, for hosts whose session id lives only in a header line) is analogous to a choice `parse_codex_rollout(path) -> Iterator[SessionEvent]` must independently make — the real Codex rollout shape must be inspected to know whether Codex events can be parsed per-line or need whole-file context. `parse_codex_rollout` makes this choice itself; it does not extend or call into `HostLayout` (Option B, selected above, is standalone — this is a design-precedent analogy, not a dependency).
- Generator/Iterator typing precedent for per-host parsers: `from collections.abc import Iterator` (not `typing.Iterator`), plain generator functions using `yield`/`yield from`, malformed input handled by an early bare `return` from the generator rather than a raised exception (`session_store/gemini.py:40-52`, `omp.py:54`) — this is the convention a new `parse_codex_rollout` should match for consistency with its two siblings.

## Implementation Steps

### Core (revised by review, 2026-09-08)

1. **Prove the layout first.** Register learning-test target `codex-rollout` asserting § Codex On-Disk Layout (sessions path pattern, `session_meta` header keys incl. `cwd`/`cli_version`, `threads` table columns `cwd`/`rollout_path`/`updated_at`, record envelope `{timestamp,type,payload}`). Capture both fixtures per Testing → Fixture capture and write `scripts/tests/fixtures/codex/README.md` with the `cli_version`-keyed re-capture rule. Record whether the interactive rollout carries per-turn usage.
2. **New module `session_store/sessions.py`**: `SessionHandle`, `SessionEvent`, `detect_sessions`, `iter_events`, `parse_claude_transcript`, `parse_codex_rollout`. Register exports in `session_store/__init__.py` following the gemini/omp precedent. Codex discovery = sqlite `threads` query (newest `state_*.sqlite` by name sort; `sqlite3` stdlib, read-only URI, every `rollout_path` existence-checked) with date-dir scan fallback reading line 1 only. The content-refusal rule goes in the module docstring: no shared tool-call or usage summarizer; per-host consumers read `payload` directly.
3. **Retire the dead Codex probe**: `_get_codex_project_folder` returns `None` with a docstring pointing at `detect_sessions`; `host_layout_for("codex").projects_root` becomes `None` (matching gemini/omp's strict-None convention); rewrite `test_host_codex_probes_codex_projects` to assert the `None` contract; `cli/session.py`'s `backfill --host codex` prints a clear "use detect_sessions-backed backfill (follow-up)" notice rather than silently finding nothing.
4. **Rewire consumers** through `detect_sessions`/`iter_events`: `extract_user_messages` **and** `extract_commands` (`user_messages.py`), `_compute_cache_rate_from_jsonl` (`cli/ctx_stats.py`), and `cli/logs.py`'s six functions (Wiring Phase below). Claude Code behaviour must be byte-identical: existing tests in `test_ll_logs.py`, `test_user_messages.py`, `test_cli_ctx_stats.py` pass unmodified except where they patch `get_project_folder` directly.
5. **`ll-ctx-stats` Codex scope (decided)**: per the content-refusal rule there is no shared usage extractor. If step 1 finds per-turn usage in the rollout, add a Codex-only reader beside `_compute_cache_rate_from_jsonl` keyed on the observed keys (expected `cached_input_tokens`/`cache_write_input_tokens`/`input_tokens` per HOST_COMPATIBILITY `[^tok-codex]`); if not, `_compute_cache_rate_from_jsonl` returns `None` for `host == "codex"` and `ll-ctx-stats` prints "cache rate: unavailable for codex sessions". Either way the outcome is stated in the parser docstring and in `docs/reference/HOST_COMPATIBILITY.md`.
6. **`ll-messages` Codex content**: `event_msg.payload.type == "user_message"` → user message text (`payload.message`); `response_item` `message` with `role == "user"` is the same text echoed into the model input and must be deduplicated against it, not double-counted.

**Split recommendation (not applied):** steps 1–3 are self-contained and independently testable; steps 4–6 plus the Wiring Phase are the rewire. If change surface stays a blocker at implementation time, split at that line into a FEAT (discovery + parser + fixture + learning test) and an ENH (seam adoption by the three CLIs).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/logs.py` — route its 6 un-hosted `get_project_folder()`-calling functions (`_collect_sequences`, `_cmd_sequences`, `_cmd_extract`, `_collect_failure_clusters`, `_cmd_scan_failures`, `_cmd_eval_export`) through `detect_sessions`/`iter_events` instead; this is the literal `ll-logs` AC #4 names and was missing from "Files to Modify" entirely
- **Decided**: `cli/logs.py`'s Claude-schema-coupled content functions (`_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error`) are scoped out as Claude-Code-only for v1 — they stay unmodified and are not given Codex equivalents. This follows directly from the issue's own "seam is refused on content" design (tool-call shapes are deliberately not unified across hosts) and matches the precedent already set for the `HostLayout`/watcher duplication (Proposed Solution → Recommended: "worth a follow-up issue, not a blocker for this one"). A follow-up issue should add Codex-native equivalents once real Codex session content justifies the per-host effort. Only the lifecycle (`detect_sessions`/`iter_events`) needs to serve both hosts for this issue's Acceptance Criteria; per-host content interpretation in `cli/logs.py` does not.
- Inject `host=event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` at `scripts/little_loops/hooks/session_start.py:162`'s `get_project_folder(cwd)` call — the same fallback expression already exists two lines below (line 178) for the backfill-worker's `--host` argument; the session-folder resolution should use it too instead of depending on ambient `LL_HOOK_HOST` matching the event's actual host
- Update `scripts/tests/test_ll_logs.py` — add `LL_HOOK_HOST=codex`-driven fixture coverage for `TestSequences`, `TestExtract`, `TestScanFailures`, `TestEvalExport` following the `test_resolves_qwen_chats_transcript` template (`test_cli_ctx_stats.py:909`), since every existing fixture helper in this file hard-codes the Claude Code layout
- Add `test_resolves_codex_*_transcript`-equivalent coverage to `test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` (no Codex pair exists alongside the qwen/gemini ones)
- ~~Write a new file-growth/tailing test harness for `watch()`~~ — dropped with `watch()` (§ Live watch is deferred); no tailing test is needed in v1
- Fixture "perishable" marker: implemented as the `codex-rollout` learning test + `cli_version`-keyed README rule (Testing → Fixture capture), not a new convention
- Update `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`, `docs/guides/EXAMPLES_MINING_GUIDE.md` — remove or qualify their Claude-Code-only framing of `ll-logs`/`ll-messages`
- Verify `/ll:loop-suggester --from-sequences` (`commands/loop-suggester.md`, `skills/ll-loop-suggester/SKILL.md`) surfaces Codex-sourced n-grams once `_collect_sequences` is rewired
- If the session-watcher rewire changes the wording of `"No session project folder found"`, update `.loops/ll-logs-telemetry-digest.yaml:66`'s `scan_failures` state, which greps stderr for that exact string to distinguish "no session data" from a real failure

_Second wiring pass added by `/ll:wire-issue`:_
- **Decided (review, 2026-09-08)**: `extract_commands` (`user_messages.py:721`) routes through `detect_sessions`/`iter_events` too — same glob pattern, same sole caller (`cli/messages.py`), trivial to include, and leaving it out would extract Codex user messages but not Codex commands
- Do not change `get_project_folder`/`get_sessions_folder`'s Path-returning signature — `cli/session.py`'s `backfill` subcommand, `session_log.py`'s `get_current_session_jsonl`/`get_current_session_id` (consumed by `fsm/executor.py`, `parallel/orchestrator.py`, `advisor.py`, `issue_lifecycle.py`), and `fsm/continuity.py::summarize_completed_state` all depend on the bare-`Path`-or-`None` contract and sit outside this issue's Call Path
- **Decided (verification pass, 2026-09-09)**: the transcript_path-driven raw readers outside `get_project_folder` (`hooks/session_start.py`'s primary branch, `cli/backfill_worker.py`'s single-file path, `hooks/pre_compact.py`'s rubric-gate read, `hooks/scripts/context-monitor.sh`'s tail-based read) stay separate and are out of scope for this issue's v1 — they key off a hook payload's `transcript_path` for hook-timing/backfill-triggering concerns, not host+cwd session discovery for activity reporting, so they have no Acceptance Criterion here. This follows the same "worth a follow-up issue, not a blocker for this one" pattern already applied to the `HostLayout`/watcher duplication and the `cli/logs.py` content-function scope-out above.
- Template `SessionEvent`'s tests on `test_hook_intents.py::TestLLHookEvent` (closer than `test_events.py::TestLLEvent` — it already covers a `host`-discriminated dataclass with optional fields) and `detect_sessions`' empty-vs-handles tests on `test_host_runner.py::TestResolveHost::test_detect_binary_probe_order`/`test_raises_when_no_host`. Add Codex discovery tests for both paths: a `tmp_path` fake `~/.codex/state_5.sqlite` with a `threads` table (sqlite path, including a row whose `rollout_path` no longer exists), and a fake `~/.codex/sessions/YYYY/MM/DD/` tree with no DB (scan fallback). `stop()`'s template is no longer needed
- Reuse `conftest.py`'s `fixtures_dir`/`load_fixture` helpers and the autouse `_isolate_session_log_dir` fixture when writing the new Codex fixture and `watch()` test harness, rather than inventing new path-isolation fixtures
- Update `docs/reference/CLI.md`'s `### ll-messages` section (line 3552) alongside the already-flagged `### ll-logs` section

## Acceptance Criteria

- A session-discovery interface exists covering the lifecycle only: enumerate the sessions for a workspace under a host (`detect_sessions`), iterate typed events for one (`iter_events`). Live `watch`/`stop` are explicitly deferred and the handle type does not need to change to add them.
- Per-host parsers live behind the interface and share no content-level code above it; tool-call shapes and token accounting stay per-host, with the refusal recorded in the module docstring.
- Codex rollout files are discovered from `~/.codex/sessions/` (sqlite `threads` index with date-dir scan fallback, cwd matched from `session_meta`) and parsed as the second implementation, exercising the seam. `_get_codex_project_folder` and `host_layout_for("codex").projects_root` no longer claim a `~/.codex/projects/` layout.
- `ll-logs`, `ll-messages` (user messages **and** commands), and `ll-ctx-stats` are served by the one implementation rather than reaching for `~/.claude/projects/` directly; Claude Code output for every existing test is unchanged.
- `ll-ctx-stats` under Codex either reports a cache rate from a Codex-only usage reader or states that the rate is unavailable — never silently computes zero from Claude-shaped keys.
- The Codex parser is tested against two captured real-shape fixtures committed alongside it (one interactive session with tool calls, one `exec` one-shot), a `codex-rollout` learning-test record proves the layout claims, and the fixture README states the `cli_version`-keyed re-capture rule.

## Impact

- **Priority**: P2 - unblocks goal 6's dataset export and goal 7's quality rollups, which currently cover Claude Code sessions only and silently miss Codex ones.
- **Effort**: Medium-High - one new interface, one new per-host parser (Codex), net-new Codex session discovery (sqlite + scan fallback; the tree's existing Codex probe is dead code), an interactive fixture capture and learning-test target, and rewiring three CLIs (`ll-logs`, `ll-messages`, `ll-ctx-stats`) to go through it. Revised up from Medium by the 2026-09-08 review; see the split recommendation under Implementation Steps.
- **Risk**: Medium - touches read paths other automation already depends on (`ll-messages`, `ll-ctx-stats` caching); existing Claude Code session behavior must not change. Codex discovery depends on a vendor-private sqlite schema, mitigated by the scan fallback and the learning test.
- **Breaking Change**: No - Claude Code session handling is preserved as the first per-host implementation; Codex support is additive.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 28/100 → VERY LOW

### Concerns
- Architecture Compliance (15/20): Option B deliberately leaves two parallel per-host dispatch mechanisms in the codebase — `HostLayout.normalize`/`normalize_file` (qwen/gemini/omp) stays as-is while a new, independent session-watcher interface is added for `ll-logs`/`ll-ctx-stats`. The issue's own Decision Rationale calls the unification "worth a follow-up issue, not a blocker for this one," but no follow-up issue is filed yet.
- No Duplicate Implementations (10/20): partial precedent exists (`get_project_folder`/`get_sessions_folder`'s working Codex path probe, `HostLayout`) but no `detect`/`watch`/`stop` lifecycle exists anywhere in the repo — "related code exists but doesn't solve the problem." Carries a `−5` learning-test modifier: the `codex` target is `proven` but has 1 failing claim (see risk factor below).
- `unapplied_decision` gap (caps Criterion C at 10/25): `format-check` still flags `extract_user_messages` and `_compute_cache_rate_from_jsonl` as present in both Program Design and Files to Modify after Option B was selected (down from 7 flagged identifiers to 4 since the last pass — `ll-session backfill --host codex`/`normalize`/`normalize_file` were cleared). These two remaining identifiers are also the legitimate Option-B Call Path consumers (`extract_user_messages`/`_compute_cache_rate_from_jsonl` → `detect_session`/`watch`), so this may be a benign false positive rather than genuine leftover rejected-option text — a quick `/ll:reconcile-issue` pass to explicitly frame them as retained call-path references (not Option-A residue) would clear the cap.

### Outcome Risk Factors
- Complexity (0/25): broad enumeration across 16+ sites (6 functions/9+ call sites in `cli/logs.py` alone, plus `user_messages.py`, `cli/ctx_stats.py`, `hooks/session_start.py`, 4+ docs files, 2-3 test files, an FSM loop YAML, and a downstream `/ll:loop-suggester` consumer) combined with deep per-site architectural work — a brand-new `detect`/`watch`/`stop` lifecycle with zero existing precedent in the repo.
- Change Surface (0/25): very wide blast radius — `get_project_folder`/`get_sessions_folder` alone have 5 non-test callers, `cli/logs.py` has 7 functions to rewire, and external consumers (`.loops/ll-logs-telemetry-digest.yaml`'s exact-string grep, `/ll:loop-suggester --from-sequences`) depend on current behavior/wording that this rewire can silently break.
- No existing pattern for the `watch()` live-tail test: every current tail-adjacent test (`_cmd_tail`'s `TestTail`) mocks `readline()` entirely — the file-growth harness itself must be originated, not adapted.
- No committed Codex rollout fixture exists yet, and the issue's "perishable, re-capture periodically" fixture-marker convention has no precedent anywhere in the tree to copy from.
- Learning-test target mismatch: `learning_tests_required: [codex]` resolves to a "proven" record, but its assertions are about Codex MCP server config (`~/.codex/config.toml` TOML shape) — a different subsystem than the Codex rollout/session-log JSONL format this issue's `parse_codex_rollout` actually depends on. The mechanically-proven status does not cover the real unproven mechanism here.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-08._

Spot-checked ~15 `file:line` citations against current HEAD (`cli/messages.py:173,192`;
`user_messages.py:373,422,458,638,721,858`; `cli/ctx_stats.py:342,753`; `cli/logs.py`'s
module docstring and `get_project_folder()` call sites; `session_store/writers.py:2527-2604`
`host_layout_for`; `hooks/session_start.py:162,178`; `.loops/ll-logs-telemetry-digest.yaml:66`;
`events.py:32` `LLEvent`; `gemini.py`/`omp.py` docstrings) — all match verbatim, including
the exact `host_layout_for("codex").projects_root` → `~/.codex/projects` dead-path claim.
Decisions log: no active required rules. `ll-verify-evidence`: clean (0 findings).

Two gaps found, both minor and fixable without re-research:

1. **Count error, not a citation error** (Integration Map → Wiring Phase, `cli/logs.py`
   bullet): states "9 direct, un-hosted `get_project_folder(...)` calls across 6
   functions," but the same sentence's own line list (653, 658, 667, 693, 774, 783,
   1353, 1358, 1367, 1554, 2032) totals **11**, and all 11 verified as real call sites
   (grep-confirmed, none passing `host=`). Fix: change "9" to "11".
2. **AC coverage gap** (check 2B.6): the second wiring pass's "four uncoordinated
   raw-transcript readers" point (`hooks/session_start.py`'s primary branch,
   `cli/backfill_worker.py`'s single-file path, `hooks/pre_compact.py`,
   `hooks/scripts/context-monitor.sh`) is left as an open "Decide whether... need
   routing... or stay separate" question with no corresponding Acceptance Criterion —
   unlike every other such fork in this issue (e.g. the `HostLayout`/watcher
   duplication, the `cli/logs.py` content-function scope-out), which was resolved via
   an explicit "**Decided**" annotation. This should be resolved the same way (either
   an AC/Implementation Step, or an explicit "out of scope, follow-up issue" call)
   before implementation.

Verdict: **NEEDS_UPDATE**. Everything else — Program Design signatures, Proposed
Solution decision rationale, Codex on-disk-layout claims (self-disclosed as
maintainer-verified and not independently reproducible from the repo), and the
remaining Integration Map / Acceptance Criteria — holds.

**Both gaps corrected 2026-09-09**: the `cli/logs.py` call-site count was fixed to
11, and the "four uncoordinated raw-transcript readers" question was resolved with
an explicit "Decided" annotation (out of scope for v1, same pattern as the other
scope-outs in this issue).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 85/100 → STOP — ADDRESS GAPS (Learning Test Hard Override)
**Outcome Confidence**: 28/100 → VERY LOW

### Concerns
- Architecture Compliance (15/20): Option B leaves two parallel per-host dispatch mechanisms (`HostLayout.normalize`/`normalize_file` for qwen/gemini/omp vs. the new session-watcher interface) with no follow-up issue filed yet.
- No Duplicate Implementations (10/20): partial precedent exists (`get_project_folder`/`get_sessions_folder`'s Codex path probe, `HostLayout`) but no `detect`/`iter_events` lifecycle exists anywhere in the repo.
- `unapplied_decision` gap (caps Criterion C at 10/25): `format-check` still flags `extract_user_messages` and `_compute_cache_rate_from_jsonl` as present in Program Design, Implementation Steps, and Files to Modify after Option B was selected — likely benign (they are the legitimate Option-B call-path consumers), but mechanically unresolved.

### Gaps to Address
- **Learning Test Hard Override**: `learning_tests_required` in frontmatter lists both `codex` and `codex-rollout`, but `ll-learning-tests check codex-rollout` returns "no record found" — the target does not exist at all (not merely unproven). Implementation Step 1 explicitly calls for registering and proving `codex-rollout` before implementation begins ("Prove the layout first"), and that step has not been done. The existing `codex` target (proven, 4/1/0) covers Codex MCP `config.toml` shape only, a different subsystem than the rollout/session-log JSONL format this issue's `parse_codex_rollout` depends on — it does not substitute. Remedy: run `/ll:explore-api` or `/ll:spike` to register `codex-rollout` per § Testing → Fixture capture (item 3), capture the two fixtures, and prove the target before implementation.

### Outcome Risk Factors
- Complexity (0/25): broad enumeration across 16+ sites (6 functions/11 call sites in `cli/logs.py` alone, plus `user_messages.py`, `cli/ctx_stats.py`, `hooks/session_start.py`, 4+ docs files, 2-3 test files, an FSM loop YAML, and a downstream `/ll:loop-suggester` consumer) combined with a brand-new `detect_sessions`/`iter_events` lifecycle with zero existing precedent in the repo.
- Change Surface (0/25): very wide blast radius — `get_project_folder`/`get_sessions_folder` alone have 5 non-test callers, `cli/logs.py` has 7 functions to rewire, and external consumers (`.loops/ll-logs-telemetry-digest.yaml`'s exact-string grep, `/ll:loop-suggester --from-sequences`) depend on current behavior/wording this rewire can silently break.
- No existing pattern for a `watch()` live-tail test if a future follow-up adds it — every current tail-adjacent test mocks `readline()` entirely.
- No committed Codex rollout fixture exists yet, and the "perishable, re-capture periodically" fixture-marker convention has no precedent in the tree to copy from.
- Learning-test target mismatch (escalated to a hard override this pass, see Gaps to Address): `codex-rollout` has no record at all, not just an unproven claim.

## Spike Results

_Added by `/ll:spike` on 2026-09-08_

Retires the "No Duplicate Implementations" / "Complexity" outcome-risk
factors (zero-precedent `detect`/`iter_events` lifecycle) — not the
"Learning Test Hard Override" (`codex-rollout`), which is an external
vendor-format claim and stays `/ll:explore-api` territory.

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| No precedent for a `detect`/`iter_events` lifecycle anywhere in the repo | `TestDetectSessionsCodexSqlitePath`, `TestIterEventsDispatch` | ✓ pass |
| Codex sqlite `threads`-query + newest-`state_*.sqlite`-selection ordering unverified | `test_detect_sessions_codex_uses_sqlite_when_present`, `test_detect_sessions_codex_picks_newest_state_db_by_name` | ✓ pass |
| Stale `rollout_path` rows (DB outlives deleted files) could leak into results | `test_detect_sessions_codex_filters_stale_rollout_paths` | ✓ pass |
| DB-absent / schema-mismatched fallback to date-dir scan untested, ordering could diverge from the DB path | `test_detect_sessions_codex_falls_back_to_date_scan_when_db_missing`, `test_detect_sessions_codex_falls_back_when_db_schema_mismatched`, `test_detect_sessions_codex_scan_orders_newest_date_dir_first` | ✓ pass |
| Per-host parser dispatch could leak Claude-shaped assumptions onto Codex handles or vice versa | `test_iter_events_dispatches_by_host_without_cross_contamination` | ✓ pass |
| Isolation guard (spike must not depend on production code to be a valid proof) | `test_lifecycle_module_has_no_production_imports` | ✓ pass |

**Spike location**: `scripts/tests/spike/session_discovery_lifecycle/`
**Verification**: 11 tests pass across 2 commands (spike AC suite +
`test_user_messages.py -k codex` regression, unaffected).
**Promotion**: move `SessionHandle`/`SessionEvent`/`detect_sessions`/
`iter_events`/`parse_codex_rollout`/`parse_claude_transcript` into
`scripts/little_loops/session_store/sessions.py` in a separate PR, per §
Program Design and the Wiring Phase.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 33/100 → VERY LOW

### Concerns
- Architecture Compliance (15/20): Option B still leaves two parallel per-host dispatch mechanisms (`HostLayout.normalize`/`normalize_file` for qwen/gemini/omp vs. the new session-watcher interface) with no follow-up issue filed yet.
- No Duplicate Implementations (10/20): partial precedent exists (`get_project_folder`/`get_sessions_folder`'s Codex path probe, `HostLayout`) but no `detect_sessions`/`iter_events` lifecycle exists in production code yet (only the spike, which lives outside the shipped module). Carries a −5 learning-test modifier: the `codex` target is proven but has 1 failing claim (an unrelated MCP `config.toml` assertion, not the rollout-parsing mechanism this issue depends on).
- `unapplied_decision` gap (caps Criterion C at 10/25): `format-check` still flags `extract_user_messages` and `_compute_cache_rate_from_jsonl` as present in Program Design, Implementation Steps, and Files to Modify after Option B was selected. Likely benign — these are the legitimate Option-B call-path consumers (`extract_user_messages`/`_compute_cache_rate_from_jsonl` → `detect_sessions`/`iter_events`), not rejected-option residue — but mechanically unresolved. A `/ll:reconcile-issue` pass to explicitly frame them as retained call-path references would clear the cap.

### Outcome Risk Factors
- Complexity (5/25): Breadth still 0/12 (16+ change sites: `cli/logs.py`'s 11 call sites, `user_messages.py`, `cli/ctx_stats.py`, `hooks/session_start.py`, 4+ docs files, 2-3 test files, an FSM loop YAML, and `/ll:loop-suggester`). Depth improved to 5/13 (Moderate, from Deep/0): the `/ll:spike` run (`scripts/tests/spike/session_discovery_lifecycle/`, 11 passing tests) proved the previously zero-precedent sqlite-query + date-dir-fallback + per-host-dispatch algorithm correct in isolation, retiring the "brand-new lifecycle, might not work" risk. Remaining depth is cross-module production wiring (multi-function, shared dispatch across `cli/logs.py`/`user_messages.py`/`cli/ctx_stats.py`), not architectural rewiring.
- Test Coverage (18/25): unchanged — the spike's 11 tests cover the algorithm in isolation only; the production module (`session_store/sessions.py`) and its wiring into the three CLIs have no tests yet since they aren't built.
- Change Surface (0/25, Pattern A): 11+ callers of `get_project_folder`/`get_sessions_folder` alone, plus external consumers keyed on exact current behavior/wording (`.loops/ll-logs-telemetry-digest.yaml`'s stderr string grep, `/ll:loop-suggester --from-sequences`). Not a uniform mechanical sweep — some sites need per-site judgment (`ctx_stats.py`'s Codex usage-reader decision, `messages.py`'s command/message dedup, `session_start.py`'s host-fallback injection) alongside the many simple call-site swaps.
- `unapplied_decision` gap also caps Ambiguity at 10/25 (see Concerns above).

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
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
