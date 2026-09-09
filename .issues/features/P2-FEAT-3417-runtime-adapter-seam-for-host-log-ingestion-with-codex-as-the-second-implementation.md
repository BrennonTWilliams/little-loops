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
learning_tests_required:
- codex
confidence_score: 85
outcome_confidence: 28
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 0
---

## Summary

`ll-logs`, `ll-messages`, and `ll-ctx-stats` all reach directly for `~/.claude/projects/<munged-cwd>/`, and nothing in the tree parses a Codex rollout file. That is the observability half of goal 2 going unbuilt while the generation half is already done: `ll-adapt --host codex` ships today, so little-loops writes artifacts for Codex and then cannot read a single Codex session back. Every log-derived capability downstream — goal 6's dataset export, goal 7's quality rollups — silently covers one host while claiming to generalize.

Introduce a session-watcher seam, not a Codex feature. The interface is small and covers the lifecycle only: detect a session for a workspace, watch it, emit typed events, stop. Per-host parsers live behind it and share nothing above it. One implementation then serves `ll-logs`, `ll-ctx-stats`, and any future dashboard, the same way one extension point can serve a CLI and a UI without either knowing about the other.

## Current Behavior

`ll-logs`, `ll-messages`, and `ll-ctx-stats` each reach directly for `~/.claude/projects/<munged-cwd>/` — Claude Code's own JSONL session layout — with no seam between the CLI and the on-disk format. Nothing in the tree parses a Codex rollout file. `ll-adapt --host codex` already generates Codex-targeted artifacts, but no code reads a Codex session back, so a workspace driven by Codex is invisible to every log-derived command.

## Expected Behavior

A session-watcher interface exists covering the lifecycle only — detect a session for a workspace, watch it, emit typed events, stop — with per-host parsers living behind it. `ll-logs` and `ll-ctx-stats` consume that interface instead of reaching for `~/.claude/projects/` directly, and a Codex rollout parser implements the same interface as the second host. A session started under Codex becomes observable through the same commands as one started under Claude Code, with no host-specific flag required.

## The seam is at the lifecycle, and is refused on content

Deliberately keep the seam at the lifecycle and refuse it on content. Tool-call shapes and token accounting do not overlap enough between hosts to justify a common abstraction, and forcing one produces a lowest-common-denominator record that is worse than two honest per-host ones.

Evidence from a visualizer that independently shipped two host integrations against the same two runtimes supports exactly this split. It introduced a four-method session-watcher interface *and* explicitly refused a shared tool summarizer in the same release, recording the reason in a header comment: the two runtimes' tool shapes don't overlap enough. Token counting followed the same rule in the other direction — Codex exposes authoritative token counts, so the estimator was deleted there; Claude Code exposes no equivalent field, so estimation stayed. Two runtimes, two strategies, no forced uniformity.

This is a real counterweight to the standing proposal for a declarative host-adapter schema — a host described as a YAML stanza with capability booleans. That proposal assumes hosts are uniform enough for one schema to describe them. The evidence from two hosts actually implemented is that the *lifecycle* generalizes cleanly and the *content* does not, which suggests the seam belongs at the watcher with per-host content code behind it, rather than at a schema that tries to describe the content. Weigh it when that design decision is actually made; it is not a refutation.

## Sequencing

Sequencing matters and should be stated in the issue rather than discovered during review: build the seam when the second implementation makes the duplication concrete, not in anticipation of it. Codex is that second implementation, so the seam is now earned. The reference implementation followed the same order — the first host was built with no abstraction at all, and the interface arrived only once the second host made the duplication real.

Keeping the Codex watcher free of any UI-framework dependency is what lets one implementation serve `ll-logs`, `ll-ctx-stats`, and a future dashboard without modification.

## Testing

Test the Codex parser against a captured real-shape rollout fixture — actual JSONL from a real session, committed alongside the parser — not hand-minimized stubs. This is complementary to, not a substitute for, the scripted fake-host work: a fake host tests our handling of a sequence we chose, a captured fixture tests our parser against a record shape the vendor chose and can change under us without telling us.

Treat the fixture as perishable and re-capture it periodically. The concrete precedent: a vendor started inlining full base instructions into the first line of its rollout file, that line blew past a consumer's fixed 64KB read buffer, `cwd` extraction failed, and sessions were silently skipped — an empty panel with no error. Neither a scripted fake host nor the existing unit tests would have caught it; re-capturing the fixture would have.

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
- `scripts/little_loops/cli/messages.py` (`main_messages`, calls `get_project_folder(cwd)` at line 173 with **no `host=` kwarg**, then `extract_user_messages(project_folder, ...)` at line 192) — always resolves the Claude Code project folder regardless of the actual running host
- `scripts/little_loops/user_messages.py` (`extract_user_messages`, line 638) — takes only `project_folder`/`limit`/`since`/`include_agent_sessions`/`include_response_context`, no `host` parameter; globs `*.jsonl` and parses every record against the Claude Code schema via `_parse_user_record` (line 858)
- `scripts/little_loops/cli/ctx_stats.py` (`_compute_cache_rate_from_jsonl`, line 342; called from `main_ctx_stats` at line 753 with no `host=`) — calls `get_sessions_folder(cwd)` without `host=`, so it inherits whatever `LL_HOOK_HOST` resolves to; parses `record["message"]["usage"]` fields that are Claude Code-specific
- `scripts/little_loops/session_store/writers.py` (`HostLayout` dataclass at line 2455, `host_layout_for` at line 2527) — the codebase's pre-existing per-host content-parsing seam (`normalize`/`normalize_file` callables), already implemented for `qwen`/`gemini`/`omp`; `"codex"` currently falls through to the generic branch (line 2591) with `normalize=None`, `normalize_file=None`, so a Codex rollout file fed through `ll-session backfill --host codex` today passes through completely untranslated

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` (module docstring, line 1, frames the whole file as reading only the Claude Code session-log root) — this IS `ll-logs`, the file AC #4 names, and it was absent from "Files to Modify" entirely. It has 9 direct, un-hosted `get_project_folder(...)` calls across 6 functions — `_collect_sequences` (lines 653, 658, 667), `_cmd_sequences` (693), `_cmd_extract` (774, 783), `_collect_failure_clusters` (1353, 1358, 1367), `_cmd_scan_failures` (1554), `_cmd_eval_export` (2032) — none pass `host=`, confirmed by grep (no `--host` CLI flag exists anywhere in this file's argparse). Beyond folder resolution, the Claude-schema-coupled content functions `_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error` all branch on `record["type"]`/`message.content[*].type` — these must either gain a per-host equivalent behind the new interface or be explicitly scoped out as Claude-Code-only for this issue's v1 (the issue does not currently state which).

### Dependent Files (Callers/Importers)
- `get_project_folder`/`get_sessions_folder` (`user_messages.py:373`, `:422`) are imported by: `session_log.py:15`, `fsm/continuity.py:22`, `cli/logs.py:35`, `cli/ctx_stats.py:34`, `cli/session.py:71`
- `extract_user_messages` (`user_messages.py:638`) has exactly one production caller: `cli/messages.py:192` (import at `:30`)
- `_compute_cache_rate_from_jsonl` (`cli/ctx_stats.py:342`) has exactly one production caller: `main_ctx_stats` at `cli/ctx_stats.py:753`
- `host_layout_for` (`session_store/writers.py:2527`) is consumed by `_backfill_raw_events`/`_iter_events` (`session_store/lifecycle.py:747`, `writers.py:3247`) and by `cli/session.py`'s `ll-session backfill --host codex` path (lines 664-708), which is already wired end-to-end at the CLI-argument layer

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/session_start.py:162` — `_pf = get_project_folder(cwd)` with no `host=` kwarg, even though the enclosing block already has the correct value in scope: `event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` is computed two lines later (line 178) to stamp the separate backfill-worker subprocess. The same `event.host` fallback should resolve `_pf` too — today it silently depends on ambient `LL_HOOK_HOST` matching the event's actual host.
- `scripts/little_loops/cli/backfill_worker.py:57,59` — local `from little_loops.session_store import host_layout_for` + call site; a second, previously unlisted consumer of `host_layout_for` alongside `_backfill_raw_events`/`_iter_events`/`cli/session.py`.
- `.loops/ll-logs-telemetry-digest.yaml:66` — a built-in FSM loop's `scan_failures` state greps `ll-logs scan-failures`'s stderr for the literal string `"No session project folder found"` to distinguish "no session data" from a real failure (`FAILURES_NO_DATA` vs `FAILURES_ERROR`). If the session-watcher rewire changes this message's wording, this loop's branch stops matching and silently falls through to the JSON-count branch on empty/errored output — a gate consumer, confirmed as the only place in the tree (tests included) keyed on this exact string.
- `commands/loop-suggester.md` (lines 740-768) and `skills/ll-loop-suggester/SKILL.md` (lines 303-309, 408, 631, 650) — `/ll:loop-suggester --from-sequences` shells out to `ll-logs sequences --json` directly as a documented telemetry source; verify it picks up Codex-sourced n-grams once `_collect_sequences` is rewired, since today it silently covers Claude Code only.

### Conventions in Force
- Per-host path/layout resolution in this codebase is a literal-string `if`/`elif` chain over a fixed host vocabulary, not a registered adapter table — evidence: `get_project_folder` (`user_messages.py:373-419`, dispatches to `_get_claude_project_folder`/`_get_codex_project_folder`/etc.), `host_layout_for` (`writers.py:2527-2604`)
- `get_project_folder`/`get_sessions_folder` are already host-parameterized, including a working Codex path probe — `_get_codex_project_folder` (`user_messages.py:458`) resolves `~/.codex/projects/<encoded>` using the same dash-encoding (`encode_project_path`, line 362) as Claude Code. `host` defaults from `os.environ.get("LL_HOOK_HOST", "claude-code")` when not passed explicitly (line 395). The gap is downstream: `extract_user_messages` and `_compute_cache_rate_from_jsonl` never receive or forward a `host` value, so they always assume Claude Code's JSONL schema regardless of which host's folder was actually resolved.
- The three existing per-host content parsers (`session_store/qwen.py:normalize_qwen_record`, `gemini.py:normalize_gemini_session`, `omp.py:normalize_omp_session`) all normalize *into a shared Claude-shaped record* rather than keeping a per-host content type — evidence: `gemini.py` and `omp.py` module docstrings both state the normalizer "yields Claude-shaped `user`/`assistant` records". This is the opposite of this issue's stated design ("refuse [a shared abstraction] on content"); see Proposed Solution → Codebase Research Findings for the resulting decision point.
- Uniform per-line JSONL resilience: `line.strip()` → skip empty → `json.loads` inside `try/except json.JSONDecodeError: continue`; whole-file `OSError` caught per-file and skipped, never raised — evidence: `user_messages.py:703-707`, `cli/ctx_stats.py:387-405`, `session_store/writers.py` `_iter_events`. No line-length guard exists anywhere in these paths (plain `open()` text iteration has no ceiling, unlike `asyncio.StreamReader`'s 64KB default) — directly relevant to this issue's cited oversized-first-line failure mode.
- Host discrimination is always a bare `str` field/attribute (`HostRunner.name`, `HostLayout.name`, `LLHookEvent.host`) — no `Host` enum or `Literal[...]` type exists anywhere in `scripts/little_loops/` to constrain these values.
- Two separate, unrelated host knobs already coexist: `LL_HOST_CLI`/`orchestration.host_cli` (which CLI *binary* `resolve_host()` invokes, `host_runner.py`) vs. `LL_HOOK_HOST` (which session-log *layout* `get_project_folder`/`get_sessions_folder` probe) — they are read independently and are not unified.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` already has a partial, narrower precedent for host-plumbing that the new seam should build on rather than duplicate: `_has_ll_activity` (line 97), `_extract_cwd_from_project` (134), and `_extract_ll_event_streams` (261, called from `_cmd_sequences` at 676) all take an optional `layout: HostLayout | None = None` and defer to `effective.normalize` when given one — but default to `host_layout_for("claude-code")` when `None`, the same un-hosted-default shape as the 9 bare `get_project_folder()` calls above. `_collect_failure_clusters` also has a second caller beyond `_cmd_scan_failures` — `_cmd_fleet_review` (line 2843) — that must be covered by the same rewire.

### Tests
- `scripts/tests/test_cli_ctx_stats.py` — `TestComputeCacheRateFromJsonl` class (lines 676-974) is the existing coverage for `_compute_cache_rate_from_jsonl`; includes `test_resolves_qwen_chats_transcript` (:937) and `test_resolves_gemini_chats_transcript` (:974), which set `LL_HOST_CLI`/`LL_HOOK_HOST` env vars and build the host's real directory layout under `tmp_path` — the closest existing template for a Codex-equivalent test
- `scripts/tests/test_user_messages.py` — `test_host_codex_probes_codex_projects` (:147) and a second `LL_HOOK_HOST=codex` test (:509) cover only the static `get_project_folder`/`get_sessions_folder` path probe for Codex; there is no existing test that parses Codex message *content*
- `scripts/tests/test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py` — existing per-host normalizer test pattern; `test_enh_3393_gemini_normalizer.py` reads a committed fixture from `scripts/tests/fixtures/gemini/session.jsonl`, but that fixture is explicitly documented as hand-synthesized ("Verified 2026-09-06 against gemini-cli 0.46.0", `gemini.py:29`), not a sanitized real capture — no fixture in this codebase today is a genuine vendor capture, and no "perishable"/re-capture marker convention exists anywhere in the tree
- No committed Codex rollout fixture exists under `scripts/tests/fixtures/` today (searched, zero matches)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` (6587 lines; confirmed sole test file for `cli/logs.py`) — `TestSequences`/`TestArgumentParsingSequences` (797-1339), `TestExtract` (1547-2127), `TestScanFailures` (2924-4155), `TestEvalExport`/`TestEvalExportMapping`/`TestEvalExportRoundTrip` (4437-4841) cover all 6 functions named above, but every fixture helper (`_make_project_dir`, one per class) hard-codes the Claude Code layout and patches only `pathlib.Path.home` — none sets `LL_HOOK_HOST` or passes `host=`. Closest host-aware template to follow: `test_cli_ctx_stats.py`'s `test_resolves_qwen_chats_transcript`/`test_resolves_gemini_chats_transcript` (909, 941), which drive the real resolution chain via `monkeypatch.setenv("LL_HOOK_HOST", ...)` rather than patching the resolver function directly.
- `scripts/tests/test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` has no Codex-equivalent of its qwen/gemini host-resolution tests (grep for `codex` in this file: zero hits) — a third pair (`test_resolves_codex_*_transcript`) is the template gap for `_compute_cache_rate_from_jsonl`.
- No test anywhere in the repo appends bytes to a real on-disk file and asserts a watcher/tailer observes the new content (`cli/logs.py`'s own `_cmd_tail` tests mock `readline()`/`open()` entirely — `TestTail`, lines 639-742). A test for the new `watch(handle) -> Iterator[SessionEvent]` would be the first of its kind, not an adaptation of an existing pattern — budget for writing the file-growth harness itself, not just the assertions.
- The issue's "fixture marked as perishable, re-capture periodically" convention has no precedent anywhere in `scripts/tests/fixtures/` (confirmed by repo-wide search) — the closest existing convention is a real-vs-synthesized *docstring disclosure* (`test_enh_3166_qwen_normalizer.py:18-19` states its fixtures are sanitized real captures; `gemini.py:29-30` and `test_enh_omp_normalizer.py:26-29` state theirs are hand-synthesized, not captures). The perishability/re-capture-cadence marker itself must be originated by this issue's implementation, not copied from an existing file.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — per-host capability matrix; does not yet document session-log/rollout-file reading, only CLI-invocation capabilities
- `docs/codex/usage.md` — documents `LL_HOST_CLI=codex`/`resolve_host()` detection and `ll-adapt --host codex`, but has no mention of the Codex rollout file format
- `docs/reference/API.md` — module reference for `user_messages.py` and `session_store`; would need a new entry for the session-watcher module

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`### ll-logs` section) — opens "Discover and extract ll-relevant JSONL entries from Claude Code session logs," the authoritative CLI doc's own Claude-Code-only framing.
- `docs/guides/HISTORY_SESSION_GUIDE.md` (§"Session Log Tooling (`ll-logs`)", ~line 503) — describes `ll-logs` purely in terms of the host's session JSONL with no host-branching language.
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` (lines 10, 81, 429-454) — "`ll-messages` extracts these from your Claude Code session logs," plus the `ll-logs sequences`-driven loop-suggestion section.
- `docs/guides/EXAMPLES_MINING_GUIDE.md` (lines 146, 421) — "session logs from Claude Code session logs" framing and a table row naming the Claude-Code-specific session path as `ll-messages`'s source.

## Program Design

### Types

- `SessionEvent`: dataclass carrying the event's `type`, `timestamp`, and host-specific `payload`

### Signatures

- `detect_session(cwd: Path, host: str) -> SessionHandle | None` — locate the active session file/dir for a workspace under the given host
- `watch(handle: SessionHandle) -> Iterator[SessionEvent]` — stream typed events as the underlying session file grows
- `stop(handle: SessionHandle) -> None` — release any resources the watch opened
- `parse_codex_rollout(path: Path) -> Iterator[SessionEvent]` — Codex-specific parser behind the interface; the second implementation alongside the existing Claude Code JSONL reader

### Call Path

`extract_user_messages` (`user_messages.py`) and `_compute_cache_rate_from_jsonl` (`cli/ctx_stats.py`) -> `detect_session` / `watch` (new session-watcher module) -> per-host parser (`parse_codex_rollout` for Codex; the existing Claude Code JSONL parsing becomes the first per-host implementation behind the same interface)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Existing precedent for `SessionEvent`: `little_loops.events.LLEvent` (`events.py:32`) is field-for-field the same shape already proposed — `type: str`, `timestamp: str`, `payload: dict[str, Any] = field(default_factory=dict)`, plus `to_dict()`/`from_dict()` — but it is a mutable `@dataclass`, not frozen, and serializes `timestamp` to a `"ts"` wire key while keeping the `timestamp` attribute name. `little_loops.hooks.types.LLHookEvent` is a documented sibling of `LLEvent` with the same field shape plus `host`/`intent`. Either is closer prior art than an ad hoc new dataclass; `history_reader/models.py`'s bare `ts`-named dataclasses are a *different* convention reserved for read-only DB-row types, not wire/event objects, and should not be the model for `SessionEvent`.
- No `detect`/`watch`/`stop` lifecycle trio exists anywhere in `scripts/little_loops/` today (searched repo-wide). The closest partial analogs: `HostRunner.detect() -> bool` (`host_runner.py`, nine implementations) answers a different question (is this host's CLI binary present) than the proposed `detect_session(cwd, host) -> SessionHandle | None` (is there an active session file for this workspace); `fsm/host_guard.py`'s `stop()` releases an unrelated lock, not a session-watch resource; a live-tail idiom exists (`cli/logs.py:896`, `_cmd_tail`: `f.seek(0, 2)` then `readline()`/`sleep(0.1)`/print loop) but is CLI-local (prints directly) and not a reusable `Iterator`-returning function — it is the shape a `watch()` implementation would need to generalize, not something it can call directly.
- `get_project_folder(cwd, *, host=None) -> Path | None` (`user_messages.py:373`) and `get_sessions_folder(cwd, *, host=None) -> Path | None` (`:422`) already implement the `detect`-half of this issue's lifecycle for eight hosts including Codex (`_get_codex_project_folder`, `:458`, resolves `~/.codex/projects/<encoded>`) — a new `detect_session` would either wrap these or duplicate them; the issue's premise that no host-aware detection exists is true only for `extract_user_messages`/`_compute_cache_rate_from_jsonl`, not for path resolution itself.
- `session_store/writers.py`'s existing `HostLayout.normalize: Callable[[dict], dict | None] | None` (per-record) vs. `HostLayout.normalize_file: Callable[[Path], Iterator[dict]] | None` (whole-file, for hosts whose session id lives only in a header line) is the exact fork `parse_codex_rollout(path) -> Iterator[SessionEvent]` needs to resolve — the real Codex rollout shape must be inspected to know whether a per-record or per-file normalizer is correct, the same choice already made per-host for qwen (per-record) vs. gemini/omp (per-file).
- Generator/Iterator typing precedent for per-host parsers: `from collections.abc import Iterator` (not `typing.Iterator`), plain generator functions using `yield`/`yield from`, malformed input handled by an early bare `return` from the generator rather than a raised exception (`session_store/gemini.py:40-52`, `omp.py:54`) — this is the convention a new `parse_codex_rollout` should match for consistency with its two siblings.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/logs.py` — route its 6 un-hosted `get_project_folder()`-calling functions (`_collect_sequences`, `_cmd_sequences`, `_cmd_extract`, `_collect_failure_clusters`, `_cmd_scan_failures`, `_cmd_eval_export`) through `detect_session`/`watch` instead; this is the literal `ll-logs` AC #4 names and was missing from "Files to Modify" entirely
- Decide and state explicitly whether `cli/logs.py`'s Claude-schema-coupled content functions (`_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error`) get a per-host equivalent in v1 or are scoped out as Claude-Code-only pending a follow-up
- Inject `host=event.host or os.environ.get("LL_HOOK_HOST", "claude-code")` at `scripts/little_loops/hooks/session_start.py:162`'s `get_project_folder(cwd)` call — the same fallback expression already exists two lines below (line 178) for the backfill-worker's `--host` argument; the session-folder resolution should use it too instead of depending on ambient `LL_HOOK_HOST` matching the event's actual host
- Update `scripts/tests/test_ll_logs.py` — add `LL_HOOK_HOST=codex`-driven fixture coverage for `TestSequences`, `TestExtract`, `TestScanFailures`, `TestEvalExport` following the `test_resolves_qwen_chats_transcript` template (`test_cli_ctx_stats.py:909`), since every existing fixture helper in this file hard-codes the Claude Code layout
- Add `test_resolves_codex_*_transcript`-equivalent coverage to `test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` (no Codex pair exists alongside the qwen/gemini ones)
- Write a new file-growth/tailing test harness for `watch()` — no existing test in the repo appends to a real on-disk file and asserts a watcher observes it; `_cmd_tail`'s tests mock `readline()` entirely and are not adaptable
- Originate the fixture "perishable, re-capture periodically" marker convention this issue's Testing section requires — no existing fixture anywhere in the tree carries one to copy
- Update `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`, `docs/guides/EXAMPLES_MINING_GUIDE.md` — remove or qualify their Claude-Code-only framing of `ll-logs`/`ll-messages`
- Verify `/ll:loop-suggester --from-sequences` (`commands/loop-suggester.md`, `skills/ll-loop-suggester/SKILL.md`) surfaces Codex-sourced n-grams once `_collect_sequences` is rewired
- If the session-watcher rewire changes the wording of `"No session project folder found"`, update `.loops/ll-logs-telemetry-digest.yaml:66`'s `scan_failures` state, which greps stderr for that exact string to distinguish "no session data" from a real failure

## Acceptance Criteria

- A session-watcher interface exists covering the lifecycle only: detect a session for a workspace, watch it, emit typed events, stop.
- Per-host parsers live behind the interface and share no content-level code above it; tool-call shapes and token accounting stay per-host, with the refusal recorded in the code.
- Codex rollout files are parsed as the second implementation, exercising the seam.
- `ll-logs` and `ll-ctx-stats` are served by the one implementation rather than reaching for `~/.claude/projects/` directly.
- The Codex parser is tested against a captured real-shape rollout fixture committed alongside it, with the fixture marked as perishable and a re-capture expectation stated.

## Impact

- **Priority**: P2 - unblocks goal 6's dataset export and goal 7's quality rollups, which currently cover Claude Code sessions only and silently miss Codex ones.
- **Effort**: Medium - one new interface plus one new per-host parser (Codex), rewiring three existing call sites (`ll-logs`, `user_messages.py`, `ctx_stats.py`) to go through it.
- **Risk**: Medium - touches read paths other automation already depends on (`ll-messages`, `ll-ctx-stats` caching); existing Claude Code session behavior must not change.
- **Breaking Change**: No - Claude Code session handling is preserved as the first per-host implementation; Codex support is additive.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 28/100 → VERY LOW

### Concerns
- Architecture Compliance (15/20): Option B deliberately leaves two parallel per-host dispatch mechanisms in the codebase — `HostLayout.normalize`/`normalize_file` (qwen/gemini/omp) stays as-is while a new, independent session-watcher interface is added for `ll-logs`/`ll-ctx-stats`. The issue's own Decision Rationale calls the unification "worth a follow-up issue, not a blocker for this one," but no follow-up issue is filed yet.
- Issue Well-Specified (15/20): the Wiring Phase explicitly states an open scope question the issue itself does not resolve — whether `cli/logs.py`'s Claude-schema-coupled content functions (`_is_ll_relevant`, `_detect_ll_signal`, `_extract_tool_name`, `_extract_eval_invocation`, `_cmd_matches`, `_record_has_error`) get a per-host equivalent in v1 or are scoped out as Claude-Code-only. An implementer will have to make this call mid-implementation.
- `unapplied_decision` gap (caps Criterion C at 10/25): `format-check` flags 7 identifiers from the rejected Option A (`extract_user_messages`, `_compute_cache_rate_from_jsonl`, `ll-session backfill --host codex`, `normalize`, `normalize_file`) still present, unmarked, in Program Design and Files to Modify after Option B was selected. Recommend `/ll:reconcile-issue` to either mark these as rejected-option context or remove them from directive sections.
- Learning-test target mismatch: `learning_tests_required: [codex]` resolves to a "proven" record, but its assertions are about Codex MCP server config (`~/.codex/config.toml` TOML shape) — a different subsystem than the Codex rollout/session-log JSONL format this issue's `parse_codex_rollout` actually depends on. The mechanically-proven status does not cover the real unproven mechanism here; also carries a `−5` Criterion 1 modifier for 1 failing claim.

### Outcome Risk Factors
- Complexity (0/25): broad enumeration across 16+ sites (6 functions/9+ call sites in `cli/logs.py` alone, plus `user_messages.py`, `cli/ctx_stats.py`, `hooks/session_start.py`, 4+ docs files, 2-3 test files, an FSM loop YAML, and a downstream `/ll:loop-suggester` consumer) combined with deep per-site architectural work — a brand-new `detect`/`watch`/`stop` lifecycle with zero existing precedent in the repo.
- Change Surface (0/25): very wide blast radius — `get_project_folder`/`get_sessions_folder` alone have 5 non-test callers, `cli/logs.py` has 7 functions to rewire, and external consumers (`.loops/ll-logs-telemetry-digest.yaml`'s exact-string grep, `/ll:loop-suggester --from-sequences`) depend on current behavior/wording that this rewire can silently break.
- No existing pattern for the `watch()` live-tail test: every current tail-adjacent test (`_cmd_tail`'s `TestTail`) mocks `readline()` entirely — the file-growth harness itself must be originated, not adapted.
- No committed Codex rollout fixture exists yet, and the issue's "perishable, re-capture periodically" fixture-marker convention has no precedent anywhere in the tree to copy from.

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-09T03:42:59 - `96a64da7-7e7c-4bdc-9e11-d16d6c8ed5d2.jsonl`
- `/ll:wire-issue` - 2026-09-09T03:26:48 - `0961ed9a-8a16-4f5b-b6df-7c9ad07e35e7.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:13:40 - `1bbd8d24-c939-4e16-a513-a2fcf919d545.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:03:58 - `184f5f10-ed2d-4c54-a9b0-aeaf09c80493.jsonl`
- `/ll:format-issue` - 2026-09-09T02:31:56 - `41091f97-0a07-455f-8f9a-e78193f9f4b8.jsonl`
