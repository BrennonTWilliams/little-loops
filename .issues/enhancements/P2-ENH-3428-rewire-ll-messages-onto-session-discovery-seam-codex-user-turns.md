---
id: ENH-3428
type: ENH
title: Rewire ll-messages onto the session-discovery seam (Codex user-turn support)
priority: P2
status: done
discovered_by: issue-size-review
discovered_date: '2026-09-09'
captured_at: '2026-09-09T21:54:30Z'
completed_at: '2026-09-10T02:56:04Z'
labels:
- multi-host
- observability
parent: ENH-3419
blocked_by: []
blocks: []
relates_to:
- ENH-3420
- FEAT-3417
- ENH-3429
- ENH-3430
confidence_score: 100
outcome_confidence: 86
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
---

# ENH-3428: Rewire ll-messages onto the session-discovery seam (Codex user-turn support)

## Summary

Decomposed from ENH-3419 (score 8/11, Very Large). Rewires `user_messages.py`'s
`extract_user_messages`, `extract_commands`, and `extract_conversation_turns` off the
`project_folder: Path` glob and onto `session_store/sessions.py:detect_sessions`/`iter_events`
(added by ENH-3427), and adds the Codex user-turn extraction. Their sole caller is `main_messages`
in `cli/messages.py`. ENH-3427 (now complete) already added `_resolve_host` and the `--host` flag
registered on `ll-messages`.

## Expected Behavior

`main_messages` resolves sessions via `detect_sessions(cwd, host=_resolve_host(...))` and passes
the resulting `list[SessionHandle]` into `extract_user_messages`/`extract_commands`/
`extract_conversation_turns`, which iterate `iter_events(handle)` per handle instead of globbing
`project_folder`. Claude Code output is byte-identical to today (same `_parse_user_record` parse
of `event.payload`). For Codex handles, `extract_user_messages` yields one `UserMessage` per typed
user prompt (from `response_item` role-`user` messages, deduped against any paired 0.130.0
`event_msg` `user_message`), excluding `<environment_context>`, `developer`-role messages, and
`<turn_aborted>`; `extract_commands` yields no records for Codex handles (out of scope — see
Proposed Solution step 5). `--host codex`/`--host claude-code` narrows to one host; no flag unions
**every registered host** (`detect_sessions(host=None)` returns claude-code, codex, opencode, pi,
kimi-code, qwen, gemini, and omp — not just two), so the extractors dispatch per `handle.host`
(Proposed Solution step 0). A target with no sessions still exits 1, now via
`"No sessions found for: <cwd>"`.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Current Behavior

`cli/messages.py`'s `main_messages` calls `get_project_folder(cwd)` (line 173) then
`extract_user_messages(project_folder, ...)` (192) and `extract_commands(project_folder, ...)`
(201-207). `user_messages.py`'s `extract_user_messages` (639) and `extract_commands` (722) take a
bare `project_folder: Path`, glob `*.jsonl`, and parse via `_parse_user_record`.
`extract_user_messages` defaults to `include_agent_sessions=True`. A third globbing function,
`extract_conversation_turns` (1028, glob at 1096), is called from `main_messages` for
`--sft-format` (`cli/messages.py:250`) with the same `project_folder`; only its `--reader db` mode
bypasses the glob.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Confirmed current (2026-09-09) line numbers in `scripts/little_loops/user_messages.py` — this section's existing citations have drifted since the last refine pass: `extract_user_messages` now starts at line 684 (not 639), `extract_commands` at 767 (not 722), `_extract_messages_with_context` at 980, `_extract_turn_pairs` at 1021, `extract_conversation_turns` at 1073 (not 1028); its glob is at line 1140.
- Confirmed current call sites in `scripts/little_loops/cli/messages.py`: `get_project_folder(cwd)` at line 175 (not 173, and it passes no `host=` kwarg); the `None`-folder error/return-1 branch at lines 177-179; `extract_user_messages` call at lines 193-200 (not 192); `extract_commands` call at lines 202-209 (not 201-207); the `--sft-format` branch (import + `extract_conversation_turns` call) at lines 245-258 (not 250).
- New gap not previously captured: `--host` is registered on `ll-messages` (`add_host_arg(parser)` at `cli/messages.py:86`) and parsed into `args.host`, but a repo-wide grep for `args.host` inside `cli/messages.py` returns zero hits — the flag is never read anywhere in `main_messages()`. It is not passed to `get_project_folder()` (whose call at line 175 has no `host=` kwarg) nor could it be passed to any of the three `extract_*` functions today, since none of their current signatures accept a `host` parameter. `ll-messages --host codex` today silently behaves identically to no flag at all (always Claude-Code-only via `get_project_folder`'s default).
- Exact current no-results wording (the issue's Proposed Solution step 8 target text differs from what exists today): `logger.error(f"No session project folder found for: {cwd}")`, return 1 (`cli/messages.py:178-179`) — not "No sessions found for: <cwd>" as the issue paraphrases; that is the proposed replacement text, not the current one.

## Proposed Solution

0. **Per-host dispatch** (required because the no-flag default is an 8-host union, see Summary):
   each extractor branches on `handle.host`. `codex` → the new Codex branch (steps 2-4).
   `claude-code`, `opencode`, `pi`, `qwen`, `gemini`, `omp` → the existing Claude branch
   (`_parse_user_record(event.payload, …)`) — every one of those parsers yields Claude-shaped
   `type: "user"` records (`_parse_claude_shaped` passes the whole record; the qwen/gemini/omp
   normalizers emit `{"type": "user", "message": {"role": "user", "content": …}}`).
   `kimi-code` → skipped (raw `wire.jsonl` records, no normalizer yet — see `parse_kimi_wire`'s
   docstring). Because the normalized hosts do not reliably carry `sessionId`/`cwd`, the Claude
   branch gains handle fallbacks: `session_id = record.get("sessionId") or handle.session_id`,
   `cwd = record.get("cwd") or str(handle.cwd)`. For `claude-code` records both keys are always
   present, so Claude Code output is unchanged.
1. **Signature change**: `extract_user_messages`/`extract_commands`/`extract_conversation_turns`
   gain a `handles: list[SessionHandle]` entry point and iterate `iter_events(handle)`. The Claude
   branch keeps `_parse_user_record` byte-for-byte on `event.payload` (plus the step 0 fallbacks).
   `main_messages` passes `include_agents=not args.exclude_agents` to `detect_sessions` (the seam
   defaults to `False`; the extractors default to `True`). The extractors keep their
   `include_agent_sessions` kwarg and filter on `handle.is_agent` so the Python API stays
   meaningful for callers that build handles directly; on the CLI path this is a harmless
   double-filter.
2. **Codex user-turn mapping** (corrected against the 0.152.1 fixtures): neither committed fixture
   contains an `event_msg` of type `user_message`; the user's prompt lives in `response_item`
   events with `payload.type == "message"` and `payload.role == "user"`, text under
   `payload.content[].text` (`type: "input_text"`). Filter out two injected user-role messages:
   the host-injected `<environment_context>...</environment_context>` block and any
   `role == "developer"` message; also filter `<turn_aborted>` (match on the stripped text's
   opening tag, kept as a single named constant list).
3. **Paired `event_msg` dedup path** (the common path on the real corpus — surveyed 2026-09-09:
   8859 local rollouts, 6696 on 0.98.0, 2162 on 0.130.0, 1 on 0.152.1; **both** 0.98.0 and
   0.130.0 write the paired `event_msg`, only 0.152.1 omits it): both a `response_item`
   role-`user` message and an `event_msg` `user_message` carry the same text per turn; the
   `event_msg` payload's text is under **`message`** (not `text`). Observed order on every sampled
   file is `response_item` first, `event_msg` second, but the rule must be order-independent:
   track the last emitted user text per file and emit an `event_msg` `user_message` only when
   `payload.message` differs from it (likewise skip a `response_item` whose joined text equals
   the last emitted `event_msg` text). This also yields the turn from a file that carries only
   the `event_msg`. Unknown `event_msg` types pass through untouched.
4. **Codex → `UserMessage` field mapping**: `content` = joined `input_text` texts; `timestamp` =
   envelope `timestamp` (same ISO-Z parse as Claude, file mtime fallback); `session_id` =
   `handle.session_id`; `uuid` = `payload.id` (`msg_…`) **when present, else
   `f"{handle.session_id}:{line_no}"`** — 0.130.0 (and 0.98.0) `response_item` user messages
   carry no `payload.id`, so the fallback is the common case on the real corpus, and `uuid` has
   no consumer beyond `to_dict()` serialization; `cwd` = the `session_meta` payload's `cwd` if
   seen else `str(handle.cwd)`; `git_branch` = the `session_meta` payload's `git.branch` if seen
   (both committed fixtures carry `git: {commit_hash, branch, repository_url}` on line 1) else
   `None`; `is_sidechain = False`.
5. **`extract_commands` stays Claude-Code-only**: it parses Claude `tool_use` blocks for `Bash`
   (722-745); Codex handles yield no `CommandRecord`s. The Codex equivalent
   (`response_item.payload.type == "custom_tool_call"`, `name: "exec"`) is out of scope — a
   content-level mapping deferred to a follow-up.
6. **Two more Claude branches must move off the glob**: `extract_user_messages` with
   `include_response_context=True` (935) and `extract_conversation_turns`'s JSONL branch (976) —
   both take the file only for the mtime fallback; under handles,
   `all_records = [e.payload for e in iter_events(h)]`, pass `h.path`.
7. **`extract_conversation_turns`'s JSONL branch** takes `handles` and iterates `iter_events`, with
   the same `include_agent_sessions` → `include_agents` mapping and the mtime-based `since`
   pre-filter re-expressed on `handle.updated_at`; `_extract_turn_pairs` stays Claude-shaped
   (Codex handles yield no windows here). **The `--reader db` branch loses its input**: today it
   builds `resolve_history_db(project_folder / ".ll" / "history.db")`, and `project_folder` is
   gone from the signature. That path is default-shaped (`_is_default_shaped`: name `history.db`,
   parent `.ll`), so it already routes through the env → config → project-root chain and the
   folder prefix is ignored — replace it with `resolve_history_db(DEFAULT_DB_PATH)` (same
   resolution, no extra parameter). The DB query logic itself is untouched.
8. **No-sessions stderr**: change the wording to `"No sessions found for: <cwd>"` (no test asserts
   the old string); exit code stays 1. Drop the `logger.info(f"Project folder: …")` line
   (`cli/messages.py:181`) — replace with a session count per host under `--verbose`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Precedent for the Codex-returns-None-from-`get_project_folder` framing: `get_project_folder(host="codex")` already returns `None` unconditionally (landed under FEAT-3417 — Codex never writes `~/.codex/projects/`). `scripts/tests/test_user_messages.py:147-161` (`test_host_codex_returns_none`) documents this and its docstring already directs callers to `little_loops.session_store.sessions.detect_sessions` — i.e. this issue's `handles`-based rewrite is the change that docstring anticipates, not a new direction.
- Confirmed Codex `SessionEvent` shape from `parse_codex_rollout` (`session_store/sessions.py:631-672`): `event.type` is the raw top-level record `type` (`"response_item"`, `"event_msg"`, `"session_meta"`, ...); `event.payload` is the nested `payload` dict verbatim (`{}` if missing/non-dict), with no subtype filtering at the parser level — `payload.type`/`payload.role` access as described in Proposed Solution step 2 is the correct place to filter `<environment_context>`/`developer`/`<turn_aborted>`, since the parser passes every subtype through untouched by design (see its docstring).

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- No production caller of `detect_sessions`/`iter_events` exists yet anywhere in the codebase — every real call site of `ss.detect_sessions(...)`/`ss.iter_events(...)` is inside `scripts/tests/test_session_discovery.py` (the seam's own test suite). `cli/logs.py`, `cli/ctx_stats.py`, and `cli/session.py` all still use `get_project_folder`/`get_sessions_folder` + manual `project_folder.glob("*.jsonl")`; `cli/session.py:701` only mentions `detect_sessions()` inside a warning *string* ("Codex backfill via detect_sessions() is not wired up yet (ENH-3420)"), not a call. This issue is the first production consumer of the seam, not a repeat of an already-landed migration — there is no sibling call site to mirror.
- False friend: `session_store/writers.py:3250` defines its own private `_iter_events(source: list[Path] | sqlite3.Cursor) -> Generator[tuple[str, str], None, None]`, unrelated to `session_store/sessions.py`'s `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]`. It takes paths/a cursor and yields `(line, source_label)` string tuples for the backfill/rebuild raw-JSONL pipeline (6 call sites inside `writers.py`, plus one in `test_enh_3166_qwen_normalizer.py:525`). A grep for `iter_events(` alone surfaces these as false positives.
- 0.130.0 dedup shape (Proposed Solution step 3) has a confirmed synthetic fixture at `scripts/tests/test_session_discovery.py:430-435` — an `event_msg` record `{"type": "event_msg", "payload": {"type": "user_message", "message": "hi"}}`, keying the same-turn text under `payload.message` as this issue's step 3 already states. Neither committed real-capture fixture (`scripts/tests/fixtures/codex/rollout-interactive.jsonl`, `rollout-exec.jsonl`, both 0.152.1) contains an `event_msg` of type `user_message` at all — their README documents this as 0.152.1 drift from the 0.98.0/0.130.0 corpus, so the dedup path can be unit-tested against the synthetic fixture but has no real committed rollout to exercise it against.
- Real captured user-turn/injected-context shapes, confirmed against `scripts/tests/fixtures/codex/rollout-interactive.jsonl`: line 6 is the injected `<environment_context>` block (`{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"<environment_context>\n  <cwd>...</cwd>\n..."}]}}`), line 9 is a real user prompt of the same shape, and lines 3-5 are `role == "developer"` messages carrying skill instructions — confirming step 2's three-way exclusion rule against a real fixture, not just the issue's description.
- Payload-shape correction, scoped narrowly to Codex: `parse_codex_rollout` (`session_store/sessions.py:641-682`) does yield `event.payload` as the nested `payload` sub-dict verbatim, matching this section's step 2 framing — but that framing does not generalize to other hosts. For `claude-code`/`opencode`/`pi` (via the shared `_parse_claude_shaped` helper) and for `kimi-code` (`parse_kimi_wire`), `payload` is the *entire raw on-disk record* (`payload=record`), not a nested sub-key; for `qwen`/`gemini`/`omp`, `payload` is that host's own normalizer output. Relevant only if this issue's implementation generalizes payload-handling logic beyond the Codex branch — the Codex-specific claims in steps 2-4 are unaffected.
- No existing helper joins `response_item.payload.content[].text` blocks (step 4's "joined `input_text` texts" claim) — searched repo-wide for `input_text`; the only two hits are unrelated (`user_messages.py:1248`'s `ExampleRecord` joining, `sft_formatter.py:34`'s SFT turn joining). This is new code, not a call to a shared utility.
- No shared constant/helper list for filtering `<environment_context>`/`<turn_aborted>`/`developer`-role messages exists in any `.py` module (step 2's "kept as a single named constant list") — searched repo-wide for `environment_context` and `turn_aborted`; hits are confined to issue markdown and the two fixture JSONL files. The named constant list this step describes needs to be created fresh, not extracted from existing code.

## Program Design

### Types

- `SessionHandle` (existing, `session_store/sessions.py`): `host: str`, `session_id: str`,
  `path: Path`, `cwd: Path`, `updated_at: float`, `is_agent: bool`
- `UserMessage`, `CommandRecord` (existing, `user_messages.py`) — unchanged shape; only their
  source of construction changes

### Signatures

- `extract_user_messages(handles: list[SessionHandle], limit: int | None = None, since: datetime | None = None, include_agent_sessions: bool = True, include_response_context: bool = False) -> list[UserMessage]`
- `extract_commands(handles: list[SessionHandle], limit: int | None = None, since: datetime | None = None, include_agent_sessions: bool = True, tools: list[str] | None = None) -> list[CommandRecord]`
- `extract_conversation_turns(handles: list[SessionHandle], since: datetime | None = None, context_window: int = 3, include_agent_sessions: bool = True, reader: str = "auto") -> list[list[tuple[str, str]]]`

### Call Path

`main_messages` (`cli/messages.py:173`) -> `detect_sessions` (`session_store/sessions.py:291`) ->
`extract_user_messages`/`extract_commands`/`extract_conversation_turns` (`user_messages.py`) ->
`iter_events` (`session_store/sessions.py:824`) -> per-host parser (`_PARSERS[handle.host]`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Call Path line citations above have drifted since the last refine pass — current locations: `main_messages`'s `get_project_folder` call is at `cli/messages.py:175` (not 173); `detect_sessions` is defined at `session_store/sessions.py:297` (not 291); `iter_events` is defined at `session_store/sessions.py:834` (not 824). `SessionHandle` (lines 57-74 in that file) and `SessionEvent` (`type: str, timestamp: str, host: str, payload: dict`, lines 77-84) both confirm this section's existing Types claims exactly.
- `detect_sessions(cwd, host=None, *, include_agents=False, limit=None, home=None) -> list[SessionHandle]` dispatches per host at lines 297-335: `_detect_codex_sessions`, `_detect_claude_sessions`, or `_detect_layout_sessions` for `_LAYOUT_HOSTS = ("opencode", "pi", "kimi-code", "qwen", "gemini", "omp")`; `host=None` unions every registered host by recursing per host. Never raises for a missing host home — returns `[]`.

## Impact

- **Priority**: P2 - Enables Codex user-turn observability (parent ENH-3419's stated goal) but is
  one of four decomposed pieces, not standalone user-facing value until ENH-3429/ENH-3430 land too.
- **Effort**: Medium - three function signatures plus their sole caller change shape, but the
  change is scoped to two files (`user_messages.py`, `cli/messages.py`) plus docs; no new
  architecture (`detect_sessions`/`iter_events` already exist post-ENH-3427).
- **Risk**: Medium - `extract_user_messages`/`extract_commands`/`extract_conversation_turns` are
  the read path for every `ll-messages` consumer (including the `harvest` state in
  `docs/guides/EXAMPLES_MINING_GUIDE.md`'s loop); a regression in the Claude Code branch would be
  silent until a downstream loop's harvest yields zero records.
- **Breaking Change**: Yes, at the Python API layer - `extract_user_messages`/`extract_commands`/
  `extract_conversation_turns` change their first positional parameter from `project_folder: Path`
  to `handles: list[SessionHandle]`. The `ll-messages` CLI surface and its flags are unaffected.

## Scope Boundaries

- Codex `extract_commands` support (mapping `response_item.payload.type == "custom_tool_call"`,
  `name: "exec"` to `CommandRecord`) is explicitly out of scope — deferred to a follow-up (Proposed
  Solution step 5).
- `extract_conversation_turns`'s `--reader db` branch is untouched; only its JSONL (`--reader
  jsonl`/`auto` fallback) branch moves onto `iter_events`.
- ENH-3429 (`ll-ctx-stats`) and ENH-3430 (`ll-logs`) are separate issues — this issue touches only
  `user_messages.py` and `cli/messages.py`.
- `_resolve_host` and the `--host` flag are ENH-3427's scope, not this issue's — this issue only
  consumes them.
- `--skill` and `--examples-format` filter on the `<command-name>/ll:…</command-name>` marker
  (`cli/messages.py:215`), which only Claude-shaped transcripts carry. They keep working for the
  Claude-branch hosts and simply match nothing for Codex — no Codex equivalent is in scope.
- `kimi-code` handles are skipped by every extractor (no normalizer to Claude shape yet); adding
  one is a follow-up, not this issue.

## Files to Modify

- `scripts/little_loops/user_messages.py` (`extract_user_messages` 684, `extract_commands` 767,
  `_parse_user_record` 904, `_extract_messages_with_context` 980, `_extract_turn_pairs` 1021,
  `extract_conversation_turns` 1073, its glob 1140, its DB-path build 1106)
- `scripts/little_loops/cli/messages.py` (`main_messages`: `get_project_folder` call 175,
  no-folder branch 177-179, `Project folder:` log 181, `extract_user_messages` 194,
  `extract_commands` 203, `extract_conversation_turns` 252)
- `docs/reference/API.md:3424-3633,5466` — signature/docstring updates for
  `extract_user_messages`, `get_project_folder`, `get_sessions_folder`
- `docs/reference/CLI.md` — `### ll-messages` section (Claude-Code-only framing → host-generic +
  `--host` documented)
- `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`,
  `docs/guides/EXAMPLES_MINING_GUIDE.md` — remove/qualify Claude-Code-only framing for ll-messages
- `scripts/little_loops/cli/__init__.py` module docstring line 16 (`- ll-messages: Extract user
  messages from Claude Code logs`)
- `scripts/little_loops/loops/lib/cli.yaml:86-94` (`ll_messages` fragment description — stays
  unpinned per decision, description updated to "session logs of every registered host (narrow
  with `--host`)")

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `docs/guides/EXAMPLES_MINING_GUIDE.md` | Line 146: "The `harvest` state runs `ll-messages` ... to extract `(input, expected)` pairs from **Claude Code** session logs" | CHANGED | Reworded to host-generic language (e.g. "from session logs of any registered host") now that `--host codex` is supported; the `harvest` state's command line and output format are unchanged. |

### Tests

- `scripts/tests/test_user_messages.py` — Codex content tests: user-turn extraction from
  `response_item` role `user`; `<environment_context>`/`developer`/`<turn_aborted>` excluded;
  0.130.0 `user_message` dedup when present; `include_agent_sessions=True` regression through the
  new path; a `handles` builder helper.
- `scripts/tests/test_cli.py` — `TestMainMessagesIntegration` (~651) and
  `TestMainMessagesAdditionalCoverage` (~1815): re-patch `detect_sessions` (not
  `get_project_folder`) to return a fixed `[SessionHandle(...)]`. **Patch target**: `main_messages`
  imports lazily inside the function body (`cli/messages.py:26-33`), so
  `little_loops.cli.messages.detect_sessions` does not exist as a module attribute and `patch()`
  on it raises `AttributeError`. Patch `little_loops.session_store.sessions.detect_sessions`, or
  re-export `detect_sessions` from `little_loops.user_messages` and keep the existing
  `_PROJECT_FOLDER_PATH`-style constant pointing there.
- `scripts/tests/test_cli_messages.py` — same re-patch (currently patches `_PROJECT_FOLDER_PATH`,
  line 54).
- Codex handle tests: no `<turn_aborted>` appears anywhere in the 8859-file local corpus, so its
  exclusion test must use a synthetic record; likewise the missing-`payload.id` uuid fallback and
  the order-independent dedup (event_msg-first, and event_msg-only) are synthetic-fixture tests.
- Existing Claude Code tests in all files above pass unmodified except where they patch
  `get_project_folder` directly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed via grep: `extract_user_messages`/`extract_commands`/`extract_conversation_turns` have exactly one non-test, non-definition caller each — all three calls are in `scripts/little_loops/cli/messages.py` (lines 192, 201, 250). The "sole caller is `main_messages`" claim in the Summary holds.
- Test patch-site counts (for the Tests section's re-patch plan): `scripts/tests/test_cli.py` patches `little_loops.user_messages.get_project_folder` at 17 call sites (not just the ~651/~1815 areas named); `scripts/tests/test_cli_messages.py` patches `_PROJECT_FOLDER_PATH` (= `little_loops.user_messages.get_project_folder`) at 10 call sites. All 27 sites need the `detect_sessions` re-patch, not just the two named test classes.

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- `scripts/little_loops/cli/__init__.py` module docstring's ll-messages line is currently at line 16 (not line 18 as cited above), reading `- ll-messages: Extract user messages from Claude Code logs` — confirms the Claude-Code-only framing this issue's docs updates target, but the line number needs correcting when this file is touched.

## Acceptance Criteria

- `ll-messages` (user messages, commands, and `--sft-format --reader auto|jsonl` conversation
  turns) obtains sessions via `detect_sessions`/`iter_events` and never calls
  `get_project_folder`/`get_sessions_folder` for session enumeration.
- `ll-messages --host codex` yields the user's typed prompts from `response_item` role-`user`
  messages, excludes `<environment_context>`/`<turn_aborted>`/`developer`-role messages, and
  `extract_commands` yields no records for Codex handles.
- `ll-messages --host codex` on a 0.130.0/0.98.0-shaped session (both `response_item` and
  `event_msg` present for the same turn) yields each prompt once, regardless of which of the two
  records comes first; a session carrying only the `event_msg` still yields the prompt.
- `ll-messages --host codex` records carry `session_id == handle.session_id`,
  `uuid == payload.id` when the payload has an `id` else `"<session_id>:<line_no>"`, `cwd` and
  `git_branch` from `session_meta` (`git_branch is None` only when `session_meta` has no
  `git.branch`), `is_sidechain is False`.
- With no flag and no `LL_HOOK_HOST`, a workspace containing both a Claude Code and a Codex
  session shows both; `--host codex`/`--host claude-code` narrows to one. Handles for
  `opencode`/`pi`/`qwen`/`gemini`/`omp` go through the Claude branch with `session_id`/`cwd`
  falling back to the handle; `kimi-code` handles yield nothing and do not raise.
- `ll-messages` with no sessions for the target still exits 1, now with `"No sessions found for:
  <cwd>"` on stderr.
- Claude Code output for every existing test in `test_user_messages.py` is unchanged;
  `include_agent_sessions=True` still includes `agent-*` sessions, and `--exclude-agents` reaches
  `detect_sessions(include_agents=False)`.
- `ll-messages --sft-format --reader db` resolves the same `history.db` as before the change
  (`resolve_history_db(DEFAULT_DB_PATH)`), and `--reader auto` still falls back to JSONL.
- `docs/reference/CLI.md` and the three guides no longer frame `ll-messages` as Claude-Code-only.

## Dependencies

ENH-3427 (host-resolution seam) is complete (verified `ll-issues show ENH-3427` → done,
2026-09-09) — `blocked_by` cleared. Independent of ENH-3429/ENH-3430 (disjoint files — touches
`user_messages.py`/`cli/messages.py` only).

## Resolution

- **Action**: improve
- **Completed**: 2026-09-10
- **Status**: Completed

### Changes Made
- `scripts/little_loops/user_messages.py`: `extract_user_messages`/`extract_commands`/`extract_conversation_turns` take `handles: list[SessionHandle]` and read via `iter_events` instead of globbing `project_folder`; added Codex user-turn extraction (`_extract_codex_user_messages`, `_build_codex_user_message`) with `response_item`/`event_msg` order-independent dedup and `<environment_context>`/`developer`/`<turn_aborted>` exclusion; `_parse_user_record`/`_parse_command_record` gained handle-based `session_id`/`cwd` fallback; added shared `_parse_timestamp_or_fallback` helper; removed now-dead `_mtime`.
- `scripts/little_loops/cli/messages.py`: `main_messages` resolves sessions via `_resolve_host` + `detect_sessions(host=..., include_agents=...)` instead of `get_project_folder`; verbose mode logs a per-host session count instead of the removed "Project folder:" line; no-sessions error is now `"No sessions found for: <cwd>"`.
- `scripts/tests/test_user_messages.py`, `scripts/tests/test_cli.py`, `scripts/tests/test_cli_messages.py`: re-pointed to build `SessionHandle`s / patch `detect_sessions` instead of `get_project_folder`; added Codex extraction, per-host dispatch, and dedup test coverage.
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/EXAMPLES_MINING_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`, `scripts/little_loops/cli/__init__.py`, `scripts/little_loops/loops/lib/cli.yaml`: dropped Claude-Code-only framing; documented `--host` and the multi-host behavior.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 23025 passed, 12 skipped; 6 pre-existing failures unrelated to this issue, confirmed via `git stash` to fail identically without this change: `test_host_runner.py::TestAC8BaselineCoverage`, `test_issue_parser.py::TestPriorityRegexCompletenessAllowlist` (x2), `test_issue_parser.py::TestBug3295ContainmentCorpusDifferential`, `test_verify_evidence.py::TestRepoGate`, `test_prose_dep_sweep_gate.py`)
- Lint: PASS (`ruff check` on all changed files)
- Types: PASS (`mypy scripts/little_loops/user_messages.py scripts/little_loops/cli/messages.py`)
- Run: PASS (manually verified `ll-messages --stdout`, `--host claude-code --verbose`, and `--host codex --verbose` against real session data on this machine — 1790 real Codex rollouts correctly yielded typed user prompts with `<environment_context>`/developer/turn_aborted excluded)
- Integration: PASS (`ll-verify-docs` count check passes; no other production caller of the changed functions)

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-10T02:55:32 - `7404ab20-8130-4df4-a992-c730bf1293b4.jsonl`
- `/ll:confidence-check` - 2026-09-10T01:47:40 - `e5f879ce-163c-470b-875a-3db482daf36b.jsonl`
- `/ll:verify-issues` - 2026-09-10T01:43:25 - `500e387d-536a-4805-8735-c07c052de2f7.jsonl`
- manual review - 2026-09-09 - per-host dispatch (step 0), db-branch path, patch target, uuid/git_branch fallbacks, order-independent dedup, corpus survey, cite refresh
- `/ll:refine-issue` - 2026-09-10T01:26:15 - `af1b5be3-0894-42b0-b637-6b7a540d5db7.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:40:08 - `419c0f66-ac03-408b-af11-4cdc8ba58375.jsonl`
- `/ll:format-issue` - 2026-09-09T22:06:09 - `1744c85d-b425-4d1c-b20e-c1e871e66aec.jsonl`
- `/ll:issue-size-review` - 2026-09-09T21:57:08 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- No `SessionHandle` test-fixture builder/factory function exists anywhere in the repo (searched for `def _handle(`, `def _build_handle`, `def make_handle` in `test_user_messages.py` and repo-wide) — every existing test constructs `SessionHandle(...)` inline via the dataclass constructor (e.g. `test_session_discovery.py:446-455,471-477`). The "a `handles` builder helper" this section calls for would be new test infrastructure, not an extraction of an existing one.
- `test_user_messages.py`'s three relevant test classes each carry their own private, near-identical `temp_project_folder` fixture and `_write_jsonl` helper (`TestExtractUserMessages` ~733-742, `TestExtractUserMessagesWithResponseContext` ~1390-1399, `TestExtractCommands` ~1707-1716) rather than a shared one — precedent that per-class local fixtures are the norm here, relevant when deciding whether to introduce one shared `handles`-builder or keep per-class helpers.
- `test_session_discovery.py` fixtures always pass `home=tmp_path` to `detect_sessions(...)` (never real `Path.home()`), per that module's own isolation-rule docstring — the same pattern the new Codex-handle tests in `test_user_messages.py` should follow if they exercise `detect_sessions` rather than constructing `SessionHandle` directly.
