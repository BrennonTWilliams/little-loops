---
id: ENH-3433
type: ENH
title: Detect ll activity in Codex-shaped session records so ll-logs sees Codex sessions
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T05:10:54Z'
reconcile_attempted: true
verify_verdict: EVIDENCE_UNVERIFIED
labels:
- multi-host
- observability
blocked_by: []
blocks: []
relates_to:
- ENH-3422
- ENH-3429
confidence_score: 90
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3433: Detect ll activity in Codex-shaped session records so ll-logs sees Codex sessions

## Summary

Follow-up split out of ENH-3430's pre-implementation review (2026-09-10). ENH-3430 rewires `ll-logs` onto `detect_sessions`/`iter_events`, so Codex (and kimi-code) sessions are *enumerated* — but every ll-signal consumer in `cli/logs.py` keys on Claude record shape, so those sessions contribute zero events. This issue adds host-shape ll-signal detection so a Codex session's `ll-*` shell calls and `/ll:` prompts show up in `ll-logs sequences`/`extract`/`scan-failures`/`eval-export` and count toward the `--all` ll-activity filter.

## Current Behavior

The five ll-signal readers in `scripts/little_loops/cli/logs.py` — `_is_ll_relevant`, `_detect_ll_signal`, `_record_has_error`, `_extract_eval_invocation`, and the inline walk in `_collect_failure_clusters` (line numbers shift under the in-flight ENH-3430 rewrite; locate by name) — all check `record["type"] in {"user", "assistant", "queue-operation"}` and `message.content[].tool_use.name == "Bash"`. They also read `timestamp` and `sessionId` from the record itself, and `_collect_failure_clusters` pairs `tool_use.id` with `tool_result.tool_use_id` to attribute an error to the CLI that produced it.

`iter_events` on a Codex handle (`session_store/sessions.py::parse_codex_rollout`, 659) yields `SessionEvent(type=<envelope type>, payload=<inner payload>)` untouched: envelope types are `session_meta`, `turn_context`, `world_state`, `response_item`, `event_msg`; a shell call is `response_item` with `payload.type == "custom_tool_call"`, `payload.name == "exec"`, `payload.call_id`, and `payload.input` a model-authored JS snippet. The literal `input` string on `scripts/tests/fixtures/codex/rollout-interactive.jsonl` line 13 (ordinal 12) is:

```
const r = await tools.exec_command({\n  cmd: "rg --files scripts/little_loops; sed -n '1,240p' pyproject.toml",\n  workdir: "/workspace/project",\n  yield_time_ms: 10000,\n  max_output_tokens: 20000\n});\ntext(r.output);\n
```

The tool result arrives as `custom_tool_call_output` (line 15, ordinal 14) with the same `call_id` and `output: [{"type": "input_text", "text": ...}, ...]`, the first block being a `Script completed\nWall time N seconds\nOutput:\n` header. The inner payload carries neither the envelope `timestamp` nor any `sessionId`. No Codex→Claude-shape normalizer exists anywhere (unlike qwen/gemini/omp, whose parsers normalize before yielding). kimi-code (`parse_kimi_wire`, 749) is likewise raw passthrough.

**Between each `custom_tool_call` and its `custom_tool_call_output` sits an `event_msg`/`item_completed` record whose `item.type == "CommandExecution"`** (fixture lines 14, 22, 26; observed order is `custom_tool_call` → `item_completed` → `custom_tool_call_output`, 3/3). That item carries the already-parsed shell command as `command: ["/bin/zsh", "-lc", "<cmd>"]`, plus `cwd` (a `file://` URI), `status` (`"completed"` | `"failed"`), `exit_code`, `stdout`, `stderr`, `aggregated_output`, `duration`, `formatted_output`, and an `id` of the form `exec-<uuid>` — which is **not** the `call_id`, so there is no shared key between the item and the `custom_tool_call`/`_output` pair.

**Evidence base (surveyed 2026-09-10, re-run same day).** Across the 8,859 rollouts under `~/.codex/sessions` on the dev machine, the *only* `exec` tool calls that exist are the 3 `custom_tool_call`/`exec` records in the fixture's source session (codex-cli 0.152.1). The remaining 8,858 rollouts (0.98.0 and 0.130.0, all `codex exec` one-shots) contain no `custom_tool_call`, `function_call`, or `local_shell_call` records at all (`exec_command` matches in 2,163 of them are the tool description inside line 1's `base_instructions`, not calls). All 3 observed snippets use double-quoted `cmd:`. **One of the three execs failed**: fixture line 14's `CommandExecution` has `status: "failed"`, `exit_code: 1`, and an `aggregated_output` ending in `sed: pyproject.toml: No such file or directory\n`. Its `custom_tool_call_output` (line 15) is **indistinguishable from a successful one** — the same `Script completed\nWall time 0.1 seconds\nOutput:\n` header, followed by the body the model chose to `text()`. The header reports that the JS snippet completed, not the shell exit code, so **the output text carries no failure marker and never can**; the only failure signal is `CommandExecution.status`/`exit_code`.

Consequence: after ENH-3430, `ll-logs sequences` in a workspace with only Codex sessions prints "No sequences found."; `--all` drops Codex-only workspaces because `_is_ll_relevant` never fires; `eval-export` produces no fixtures from Codex runs.

## Expected Behavior

- A Codex session containing an `exec_command` whose `cmd` matches `\bll-\w+` is ll-relevant; `_detect_ll_signal` returns `_InvocationSignal(tool_name=<ll-tool>, runner="bash", input_context=<cmd>)` for it, where `<cmd>` is the *unescaped* shell command (JS string escapes such as `\"` and `\n` resolved), not the raw regex capture.
- A Codex `custom_tool_call_output` whose exec **failed per the preceding `item_completed`/`CommandExecution` item** (`status == "failed"` or `exit_code not in (0, None)`) satisfies `_record_has_error`, so `eval-export` can classify the session outcome. `is_error` is emitted as a literal `True` (never a truthy string/int): `_collect_failure_clusters` tests `block.get("is_error") is True`. The output text itself is never consulted for failure — see Current Behavior: the `Script completed` header is identical on success and failure.
- The normalized `tool_use` block carries `id = payload.call_id` and the normalized `tool_result` block carries `tool_use_id = payload.call_id`, so `_collect_failure_clusters` can pair a Codex error with the `ll-*` CLI that produced it. Without this linkage Codex errors count toward `eval-export` outcomes but never form failure clusters.
- The normalized record carries `timestamp` (from the envelope) and `sessionId` + `cwd` (from line 1's `session_meta.payload.id` / `.cwd`, which `parse_codex_rollout` sees before any tool call). ENH-3430's `payload.get("sessionId") or handle.session_id` fallback stays as belt-and-braces for every reader, but Codex records are self-sufficient — `_cmd_extract`, which writes the record into the index and reads `timestamp` from it, works without the fallback.
- `_is_ll_relevant`'s `(a)` queue-operation and `(b)` `<command-name>/ll:` user-prompt signals have no Codex analogue today (Codex has no `/ll:` skill dispatch); document as not applicable rather than emulate. One check is owed before closing that door: the user-prompt carriers are `event_msg`/`user_message` (present in every 0.98.0/0.130.0 rollout; absent on 0.152.1), `response_item`/`message` with `role == "user"`, and `event_msg`/`item_completed` with `item.type == "UserMessage"` (fixture line 10) — confirm that a Codex skill invocation (`$skill` / `/prompts:` syntax) does not surface in any of the three as an `ll-`-prefixed marker; if it does, that is a `(b)` analogue and gets a one-line mapping, otherwise record "checked, none" in the doc row.
- Every Codex record type other than `custom_tool_call` and `custom_tool_call_output` still passes through `parse_codex_rollout` untouched (`session_meta`, `turn_context`, `world_state`, `event_msg` incl. `token_count`, `reasoning`, `message`, `item_completed`, …). `item_completed`/`CommandExecution` is *read* by the parser for `status`/`exit_code`/`command` but still yielded untouched as its own `event_msg` event — the 1:1 line→event mapping is load-bearing for ENH-3422's `(source_path, line_no)` dedup index and `user_messages.py::_extract_codex_user_messages`'s per-event counter.
- Claude-shaped behavior is byte-for-byte unchanged; kimi-code is either covered by the same mechanism or explicitly listed as a remaining gap.

## Proposed Solution

**Decision (2026-09-10 review): parser-level normalizer in a new `scripts/little_loops/session_store/codex.py`, following the qwen convention exactly.** A `cli/logs.py`-local adapter was rejected because ENH-3422 already specifies that `raw_events` rows are Claude-shaped for every normalizer host and lists Codex as "no normalizer"; a logs-local adapter would leave the backfill/ingest path with the same blindness and force a second Codex normalizer later. Parser-level gives `_backfill_raw_events` (ENH-3422) and `ll-messages` the mapping for free.

Shape: `CodexNormalizer(session_id=..., cwd=...)`, called once per envelope (`__call__(envelope: dict) -> dict | None`), maps

- `response_item`/`custom_tool_call` with `name == "exec"` → a Claude `assistant` record: `{"type": "assistant", "timestamp": <envelope.timestamp>, "sessionId": <session_id>, "cwd": <cwd>, "message": {"role": "assistant", "content": [{"type": "tool_use", "id": <payload.call_id>, "name": "Bash", "input": {"command": <unescaped cmd>}}]}}`. If `cmd` cannot be extracted, return the raw envelope unchanged (never drop a record).
- `response_item`/`custom_tool_call_output` → a Claude `user` record with one `tool_result` block: `tool_use_id = payload.call_id`, `content = [{"type": "text", "text": ...}]` from the `output[].text` blocks (this is the shape `_extract_error_text` already reads), with the leading `Script completed\nWall time N seconds\nOutput:\n` header block dropped when it matches `^Script completed\nWall time [\d.]+ seconds\nOutput:\n$` — `_extract_error_text` joins every block, so a constant header would otherwise land in every `sample_error` and pollute `_normalize_error_sig` cluster keys. `is_error = True` iff the paired `CommandExecution` (below) reports `status == "failed"` or `exit_code not in (0, None)`; absent a paired item, `is_error` is omitted (never guessed from text).
- `event_msg`/`item_completed` with `item.type == "CommandExecution"` → `None` (**passed through untouched**), but the normalizer *records* `(command[-1], status, exit_code)` in its state so the next `custom_tool_call_output` can be flagged. `command` is `["/bin/zsh", "-lc", "<cmd>"]` on 0.152.1; take `command[-1]` when `len(command) == 3 and command[1] == "-lc"`, else `shlex.join(command)`.
- everything else → `None`, meaning **pass the raw envelope through untouched** (unlike qwen, where `None` means drop). This is the pass-through guarantee that keeps `cli/ctx_stats.py::_codex_cache_usage`'s `event_msg`/`token_count` reads and the `session_meta` header tests working unmodified.

**Pairing `is_error` to the right output (decided 2026-09-10 review).** `CommandExecution.id` (`exec-<uuid>`) shares no key with `call_id`, so the link is positional-with-cross-check: the normalizer keeps a `pending: dict[str, str]` of `call_id → unescaped cmd` from each `custom_tool_call`; on `CommandExecution` it matches `command[-1]` against a pending cmd (exact string equality — this is also the correctness oracle for `_extract_exec_cmd`) and stores the status under that `call_id`, falling back to the most recently pending `call_id` when no cmd matches; on `custom_tool_call_output` it pops the status for `payload.call_id`. Observed order is `custom_tool_call` → `item_completed` → `custom_tool_call_output` on all 3 fixture execs; an output arriving with no recorded status simply carries no `is_error`.

`parse_codex_rollout` therefore becomes stateful: it remembers `session_meta.payload.id` and `.cwd` from line 1 and holds the exec-pairing state above across lines. Concretely, `codex.py` exposes a small `CodexNormalizer` class (`__init__(self, *, session_id: str, cwd: str)`, `__call__(self, envelope: dict) -> dict | None`) rather than a pure function — the qwen per-record signature cannot carry the pairing state, and gemini/omp's whole-file generator shape would force the file I/O out of `sessions.py`. `SessionEvent.type` is taken from the normalized record's `type` (so `assistant`/`user`), mirroring `parse_qwen_session`.

**No failed-exec capture is needed.** The committed `rollout-interactive.jsonl` already holds one failed exec (line 14, `exit_code: 1`, `status: "failed"`) and two successful ones (lines 22, 26; `exit_code: 0`) — see Current Behavior. The normalizer docstring quotes line 14's `status`/`exit_code` and line 15's unchanged `Script completed` header as the evidence that output text cannot carry the rule. `_collect_failure_clusters` additionally clusters on a `Traceback (most recent call last)` in content regardless of `is_error`, so Python-traceback failures are covered by either path. Whether `codex exec` one-shots emit `CommandExecution` items at all is unverified (`rollout-exec.jsonl` ran no command); the design degrades to "no `is_error`" if they don't.

**`cmd` extraction.** `_extract_exec_cmd(js_snippet: str) -> str | None` accepts double-quoted, single-quoted, and backtick-delimited `cmd:` values (`cmd:\s*(["'`])((?:(?!\1)[^\\]|\\.)*)\1`, `re.DOTALL`), since the snippet is model-authored and n=3 from a single session is not enough to assume double quotes forever. The captured group is a JS-escaped string: unescape it with `json.loads('"' + captured + '"')` for the double-quoted case (JS and JSON escapes coincide for everything the model emits in practice), falling back to the raw capture on `ValueError`; for single-quote/backtick captures, apply the same after swapping the delimiter escapes. `_is_ll_relevant`/`_detect_ll_signal` then see the true shell text. A snippet with several `ll-*` invocations (`ll-issues … && ll-loop …`) yields the first match, same as Claude's Bash branch. The regex is still needed because the `assistant` record is built from the `custom_tool_call`, which arrives *before* the `CommandExecution` that carries the parsed command — but `CommandExecution.command[-1]` is the ground truth, and the test suite asserts `_extract_exec_cmd(input) == command[-1]` for all three fixture execs.

**ENH-3422 interaction (decided 2026-09-10 review): Codex stops being ingest-only, no replay shim.** ENH-3422's `rebuild()` derivers are host-agnostic (`writers.py::_iter_events` has only the shape-keyed qwen legacy shim), so once Codex exec rows are Claude-shaped with `sessionId`, `rebuild()` derives `sessions`/`tool_events` rows from Codex, and `raw_events.event_type` for those two lines becomes `assistant`/`user` instead of `response_item`. That is the intended payoff, and it makes ENH-3422's "Codex is ingest-only — `rebuild()` derives no rows from codex payloads" statements (its D4 and its planned `docs/reference/CLI.md` ingest-only note) stale the moment this lands; amend them. Codex rows ingested *before* this issue stay raw under the `(source_path, line_no)` dedup index — a replay shim like qwen's `is_raw_qwen_record` is **not** added, because a raw Codex `raw_events` row stores only the inner payload (no envelope `timestamp`, no `session_meta` context, no cross-row pairing state) and because ENH-3422 is itself uncommitted, so no released DB holds such rows. Document the limitation in the `parse_codex_rollout` docstring: pre-ENH-3433 Codex rows are inert on rebuild.

## Scope Boundaries

- **In scope**: `session_store/codex.py::CodexNormalizer` + `_extract_exec_cmd`; wiring it into `parse_codex_rollout` with `session_meta`-derived `sessionId`/`cwd`, envelope `timestamp` stamping, and `CommandExecution`-derived `is_error`; flipping the three pass-through contract statements (parser docstring, `test_parses_interactive_fixture_header_and_unknown_types_pass_through`, `docs/codex/usage.md`) to the new contract; the `(b)`-analogue check on the three user-prompt carriers; documenting the `/ll:` skill-dispatch and queue-operation signals as not applicable to Codex; a `rebuild()` test proving Codex-derived `tool_events` rows now appear, plus amending ENH-3422's "ingest-only" statements and its planned `docs/reference/CLI.md` note; documenting `CommandExecution`'s fields in `docs/codex/usage.md` and the fixture README.
- **Out of scope**: kimi-code normalization beyond "covered for free if the mechanism generalizes, else documented as a remaining gap" (Expected Behavior); rewriting `_codex_cache_usage`'s direct `event_msg`/`token_count` reads (must keep working unmodified per Proposed Solution); any change to Claude-shaped record handling, which must stay byte-for-byte unchanged; editing the committed real-capture fixtures `rollout-interactive.jsonl`/`rollout-exec.jsonl` (see Acceptance Criteria — ll-invoking rollouts are built inline or as a separately named synthetic fixture); a `rebuild()` replay shim for pre-ENH-3433 raw Codex rows (Proposed Solution, ENH-3422 interaction); capturing any new Codex fixture (the committed one already has a failed exec).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

**Files to Modify (decided 2026-09-10 — parser-level, see Proposed Solution)**
- `scripts/little_loops/session_store/codex.py` — **new**; `CodexNormalizer` + `_extract_exec_cmd`, module docstring modeled on `session_store/qwen.py`'s (documents the observed shapes, the n=3 evidence base, the `CommandExecution` pairing rule, and quotes fixture line 14/15 as the failed-exec evidence).
- `scripts/little_loops/session_store/sessions.py` — `parse_codex_rollout` (locate by name) instantiates `CodexNormalizer` after reading `session_meta` id/cwd from line 1 and applies it per line, the way `parse_qwen_session` wraps `normalize_qwen_record`. **Its docstring currently promises every subtype "is passed through untouched … never enumerates the subtype vocabulary"** — rewrite to: every type passes through except `custom_tool_call`/`custom_tool_call_output`, which are replaced by Claude `assistant`/`user` records; `item_completed`/`CommandExecution` is read for status but yielded untouched; pre-ENH-3433 `raw_events` rows are inert on rebuild. `parse_kimi_wire` is untouched.
- `scripts/little_loops/session_store/__init__.py` — export `CodexNormalizer` alongside `normalize_qwen_record` (111, 251).
- `scripts/tests/test_session_discovery.py:486` — `test_parses_interactive_fixture_header_and_unknown_types_pass_through` asserts `custom_tool_call` and `custom_tool_call_output` appear in the yielded subtypes; flip those two assertions to the new contract (they are now absent; `assistant`/`user` events with the `call_id` linkage are present) while keeping the `reasoning`/`item_completed`/`token_count`/`world_state` pass-through assertions verbatim.
- `docs/codex/usage.md:101` — the sentence "yields every record's host-native `payload` untouched … the parser passes all of them through rather than enumerating a fixed vocabulary" is now false for the two exec subtypes; amend, and document the `CommandExecution` item fields (`command`, `cwd`, `status`, `exit_code`, `stdout`, `stderr`, `aggregated_output`) the normalizer depends on.
- `scripts/tests/fixtures/codex/README.md:85` — the `item_completed` bullet gains the `CommandExecution` field list and a note that line 14 is the committed failed-exec sample (`exit_code: 1`).
- `.issues/enhancements/P3-ENH-3422-*.md` + its planned `docs/reference/CLI.md` `ll-session backfill --host codex` note — "Codex is ingest-only … `rebuild()` derives no rows from codex payloads" becomes false for the exec subtypes; amend to "Codex exec calls are normalized at the parser; `rebuild()` derives `tool_events`/`sessions` rows from them; rows ingested before ENH-3433 stay inert".
- `scripts/little_loops/cli/logs.py` — **no changes**; the five readers (`_is_ll_relevant`, `_detect_ll_signal`, `_record_has_error`, `_extract_eval_invocation`, `_collect_failure_clusters`) consume the normalized records as-is.

**Conventions in Force**
- Per-host normalization lives in its own module exposing a `normalize_<host>_record`/`normalize_<host>_session` function, wrapped by a `parse_<host>_*` generator in `sessions.py` that stamps `host` and yields `SessionEvent` — evidence: `session_store/qwen.py:59` (`normalize_qwen_record(record: dict) -> dict | None`), `session_store/gemini.py:40` (`normalize_gemini_session(path: Path) -> Iterator[dict]`), `session_store/omp.py:54` (`normalize_omp_session(path: Path) -> Iterator[dict]`), wrapped at `sessions.py:779,814,827` respectively.
- Per-host normalizers get their own `test_enh_NNNN_<host>_normalizer.py` test file, plus a cross-check test in `test_session_discovery.py` asserting `iter_events` output matches the normalizer's direct output — evidence: `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_session_discovery.py:753` (`test_qwen_iter_events_matches_normalize_qwen_record`).

**Tests**
- `scripts/tests/test_session_discovery.py:486,517,548` — existing direct `parse_codex_rollout` tests (486 flips, see Files to Modify); `:1006,1012` — direct `parse_kimi_wire` tests. New coverage goes in `test_enh_3433_codex_normalizer.py` plus a `test_codex_iter_events_matches_codex_normalizer` cross-check next to `:753` (build `expected` by running a fresh `CodexNormalizer` over the fixture lines and substituting the raw payload wherever it returns `None`).
- `scripts/tests/fixtures/codex/rollout-interactive.jsonl` and `rollout-exec.jsonl` — existing real-capture fixtures, **not to be edited**: `scripts/tests/fixtures/codex/README.md:14` ties them to a `cli_version`-keyed re-capture rule, and a hand-inserted `ll-issues` exec would break that provenance. Build ll-invoking rollouts inline with `test_session_discovery.py:35::_write_rollout` (extend it to accept extra envelope lines) or add a clearly named synthetic fixture (`rollout-synthetic-ll-exec.jsonl`) with its own README paragraph. A synthetic ll-invoking rollout must include the `custom_tool_call` → `item_completed`/`CommandExecution` → `custom_tool_call_output` triple (copy lines 13-15 of the interactive fixture and rewrite `cmd`/`command[-1]`), since the failure signal lives on the middle record. The interactive fixture's own line 14/15 pair is the real-capture failed-exec sample; no new fixture is captured.
- `scripts/tests/test_session_store_lifecycle.py` (model on the ENH-3422 D2 rebuild test) — new: ingest the interactive fixture via a Codex handle, run `rebuild()`, assert `tool_events` holds three `Bash` rows for the session and one is flagged failed; run `rebuild()` again and assert identical counts.
- `scripts/tests/test_ll_logs.py:113,118,144,150` — existing `--host codex` CLI-parsing coverage; no ll-signal-detection-on-Codex-shape assertions exist yet (the gap this issue's Acceptance Criteria requires).
- `scripts/tests/test_cli_ctx_stats.py:981,998,1008,1038` — Codex cache-rate regression tests reading `iter_events` output directly; must keep passing unmodified per Acceptance Criteria.

**Documentation**
- `docs/reference/HOST_COMPATIBILITY.md` — the `## Runner Capabilities` matrix (251) is *runner* capabilities (streaming, permission skip, token reporting…), not per-CLI observability, so an "`ll-logs` row" does not belong in it. Land the support statement as an extension of the existing `[^codexsessions]` footnote (556-566), which already describes `parse_codex_rollout`: one sentence on which record types are normalized for `ll-logs`, one on the `(a)`/`(b)` signals being N/A, one naming kimi-code as the remaining gap. No `ll-logs` row and no "enumerated, no events" phrase exists in the file today (its only two `ll-logs` mentions, 596 and 651, are unrelated prose).
- `docs/reference/API.md:9581` — `parse_codex_rollout` signature doc; add `CodexNormalizer` next to `normalize_qwen_record`'s entry.
- `docs/codex/usage.md:101` — pass-through prose to amend (see Files to Modify).

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

**Re-refine findings (2026-09-10, post ENH-3430 merge + ENH-3422 in-flight)**

- `session_store/sessions.py`, `qwen.py`, `writers.py`, `lifecycle.py`, `__init__.py` carry active, uncommitted, in-working-tree changes as of this pass — ENH-3422's implementation (frontmatter still `status: open`) landing live in this shared local-editable checkout. `sessions.py` line numbers for `parse_codex_rollout`/`parse_kimi_wire`/`parse_qwen_session` have already shifted twice this session (post-ENH-3430 commit: 670/762/793; mid-ENH-3422-landing: 733/825/856) and are not stable citation points — locate these functions by name, the way this issue's own Current Behavior section already does for the `cli/logs.py` readers.
- ENH-3422's in-flight work adds `session_id_for(host, path)` and `_codex_header_session_id(path)` to `sessions.py`; the latter already derives a Codex session's id from line 1's `payload.id` — the same source `normalize_codex_record`'s proposed `session_id` parameter needs. Whether `parse_codex_rollout` should source `session_id` via this helper once ENH-3422 lands, rather than re-deriving it from its own line-1 memory, was an open question — **decided 2026-09-10 review #2: re-derive from line 1 in the parser.** The parser already parses line 1 in its own loop and also needs `cwd` from the same payload; calling `_codex_header_session_id` would re-open the file for a second read of an ~18KB line for no gain. `cwd` derivation is untouched by ENH-3422 — no equivalent `_codex_header_cwd` helper exists — so that part still has no existing helper to reuse.
- `SessionEvent` has gained a `line_no: int | None = None` field (ENH-3422, in-flight) not present when this issue's Program Design was last written. This is orthogonal to `normalize_codex_record`'s `assistant`/`user` payload remapping and needs no handling here; the existing "### Types" note ("Reuses existing `SessionEvent`; no new types") stays accurate.
- `parse_codex_rollout` is reached at runtime through a dict-literal host registry (`_PARSERS = {"codex": parse_codex_rollout, ...}` in `sessions.py`, consumed by `iter_events()`), never a direct parenthesized call in production code — this is why a call-graph query for callers of `parse_codex_rollout` returns no hits. The only literal `parse_codex_rollout(...)` call sites anywhere in the tree are the three direct tests in `test_session_discovery.py` (lines 489, 517, 548).
- Citation drift in this section's existing entries: `docs/reference/API.md`'s `parse_codex_rollout` signature-doc line is currently 9581, not 9585 (9585 is `parse_qwen_session`'s line in the same listing); `docs/reference/HOST_COMPATIBILITY.md`'s second unrelated `ll-logs` mention is at line 652, not 651 — both off by a few lines from unrelated edits elsewhere, not substantive.
- The ENH-3422 file this issue cites as `.issues/enhancements/P2-ENH-3422-*.md` is now filed under priority P3: `.issues/enhancements/P3-ENH-3422-make-_backfill_raw_events-consume-iter_events-and-shrink-hostlayout-to-path-metadata.md` — the P2 glob no longer matches. The specific sentence this issue's Files to Modify section says to strike ("kimi-code rows are host-native `wire.jsonl` events (no normalizer), like codex.") no longer exists in that file in any form — its current Scope Boundaries already states "a codex or kimi normalizer to Claude shape (codex/kimi stay ingest-only)" is out of scope for it, so the strike action is moot rather than pending.
- Three different per-host normalizer signatures already coexist with no single uniform contract: `normalize_qwen_record(record: dict) -> dict | None` (per-record; `qwen.py:59`; `None` means the record is genuinely dropped — no pass-through branch exists in its body) vs. `normalize_gemini_session(path: Path) -> Iterator[dict]` / `normalize_omp_session(path: Path) -> Iterator[dict]` (whole-file generators that open the file themselves; `gemini.py:40`, `omp.py:54`). The stateless-per-record-function-called-by-a-stateful-wrapper shape this issue proposes for Codex combines qwen's per-record signature with gemini/omp's file-level statefulness — no existing normalizer combines the two; each keeps state and reshaping in the same function.
- No existing normalizer stamps a `cwd` field onto its output records (checked `qwen.py`, `gemini.py`, `omp.py` — zero `"cwd"` assignments in any of the three); `sessions.py` itself only ever reads `cwd` off raw records for unrelated project-discovery logic. This issue's plan to stamp `cwd` onto the normalized Codex record has no existing precedent to follow or diverge from.
- No existing codebase pattern unescapes a regex-captured string the way this issue's `_extract_exec_cmd` proposes (`json.loads('"' + captured + '"')`). The two existing multi-branch quoted-string regexes in the tree (`fsm/validation/meta_rules.py:447`'s `_STRING_LITERAL_RE`, `issue_parser.py:956`'s status-value pattern) both exclude backslashes from the captured group entirely rather than unescaping them, and neither has a backtick-delimited branch. This helper is genuinely novel for this codebase, not an extension of an existing one.
- The existing per-host cross-check tests (this issue cites only `test_session_discovery.py:753`) all live together in one class, `TestDetectSessionsLayoutNormalizedHosts` (`test_session_discovery.py:749`): `test_qwen_iter_events_matches_normalize_qwen_record` (:753), `test_gemini_iter_events_matches_normalizer_and_session_id_from_header` (:784), `test_omp_iter_events_matches_normalizer_and_session_id_from_header` (:811) — each builds an `expected` list by calling the normalizer directly against the same fixture and asserts `[e.payload for e in events] == expected`. A `test_codex_iter_events_matches_normalize_codex_record` following this shape belongs in this same class, not a standalone function.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/session_store/__init__.py:138,140,280,283` — re-exports `parse_codex_rollout`/`parse_kimi_wire`
- `scripts/little_loops/cli/ctx_stats.py:20,351,419` — imports `_aggregate_skill_stats` from `cli/logs.py`; `_codex_cache_usage` (351) reads `event_msg`/`token_count` directly from `iter_events` output and is called at 419 — must keep working unmodified per Proposed Solution
- `scripts/little_loops/user_messages.py:35` — imports `session_store` symbols
- `scripts/tests/test_session_discovery.py:489,517,548,753,1006,1012` — direct parser tests and the qwen cross-check pattern (see Conventions in Force above)
- `scripts/tests/test_cli_ctx_stats.py:981,998,1008,1038` — Codex cache-rate regression tests
- `scripts/tests/test_ll_logs.py:113,118,144,150` — existing `--host codex` CLI-parsing coverage
- `scripts/little_loops/session_store/sessions.py::_PARSERS` — dict-literal host→parser registry consumed by `iter_events()`; dispatches `handle.host == "codex"` to `parse_codex_rollout` via a dict lookup, never a direct parenthesized call in production code — this is why a call-graph query for callers of `parse_codex_rollout` finds none; the negative result is expected, not evidence the function is unreached.

## Program Design

### Types

- Reuses existing `SessionEvent` (`scripts/little_loops/session_store/sessions.py`); no new types.

### Signatures

- `class CodexNormalizer` (`scripts/little_loops/session_store/codex.py`) — `__init__(self, *, session_id: str, cwd: str)`; `__call__(self, envelope: dict) -> dict | None` maps `response_item`/`custom_tool_call` (`name == "exec"`) to a Claude `assistant` record with `tool_use(id=call_id, name="Bash", input={"command": cmd})`, and `response_item`/`custom_tool_call_output` to a `user` record with `tool_result(tool_use_id=call_id, content=[text blocks minus the `Script completed` header], is_error=True)` when the paired `CommandExecution` failed; stamps `timestamp` (envelope), `sessionId`, `cwd`. Internal state: `_pending: dict[str, str]` (`call_id → cmd`) and `_status: dict[str, bool]` (`call_id → failed`), fed by `event_msg`/`item_completed`/`CommandExecution`. Returns `None` for every other record (including `CommandExecution` itself), which the caller treats as "pass raw envelope through" — not "drop".
- `_extract_exec_cmd(js_snippet: str) -> str | None` (same module) — quote-tolerant `cmd:` extraction from the model-authored `tools.exec_command({...})` snippet, with JS-escape unescaping and raw-capture fallback; tested against `CommandExecution.command[-1]` as ground truth.
- `_command_text(command: list[str]) -> str` (same module) — `command[-1]` for the `[shell, "-lc", cmd]` shape, else `shlex.join(command)`.
- `parse_codex_rollout(path: Path) -> Iterator[SessionEvent]` — signature unchanged; body reads `session_meta` id/cwd from line 1, builds one `CodexNormalizer`, and applies it per line.

### Call Path

`iter_events` -> `parse_codex_rollout` -> `CodexNormalizer.__call__` (-> `_extract_exec_cmd`, `_command_text`) -> `SessionEvent(type="assistant"|"user", payload=<Claude-shaped>)` -> `_is_ll_relevant` / `_detect_ll_signal` / `_record_has_error` / `_extract_eval_invocation` / `_collect_failure_clusters` (`scripts/little_loops/cli/logs.py`, unchanged) and, under ENH-3422, `_backfill_raw_events`.

## Impact

- **Priority**: P3 - follow-up split from ENH-3430's pre-implementation review; ENH-3430 lands independently, but `ll-logs` stays blind to Codex-only workspaces until this closes.
- **Effort**: Medium - one stateful normalizer class plus a regex helper is the core work; no fixture capture is needed (the committed fixture already holds a failed exec); the five readers in `cli/logs.py` consume it unchanged once Claude-shaped records are produced, so this isn't five separate patches.
- **Risk**: Low-Medium - Claude-shaped paths are untouched and `test_ll_logs.py` / `test_cli_ctx_stats.py` act as regression guards; the residual risk is shape drift — the exec-call shape and the `custom_tool_call` → `CommandExecution` → `custom_tool_call_output` ordering are verified on exactly one 0.152.1 session (n=3 calls), so the normalizer must degrade to raw pass-through (never drop, never raise) on anything it doesn't recognize, and an unpaired output simply carries no `is_error`.
- **Breaking Change**: No for `cli/logs.py` consumers. **Yes, narrowly, for direct `parse_codex_rollout`/`iter_events` consumers** that expected the two exec subtypes raw — the only such consumer in-tree is the test at `test_session_discovery.py:486`; `_codex_cache_usage` reads `event_msg` only and is unaffected.

## Dependencies

ENH-3430 (the handles-based readers in `cli/logs.py`; the `sessionId`/`handle.session_id` fallback there becomes belt-and-braces for Codex once this issue stamps `sessionId` in the parser) has landed (`status: done`, commit `415d6b1cb`) — no longer a blocker, and `blocked_by` in frontmatter is now historical. Relates to ENH-3422 (its backfill consumes the parser-level normalizer for free; in-flight in this working tree as of this pass — see Integration Map re-refine findings) and ENH-3429 (`_codex_cache_usage` pass-through constraint).

## Acceptance Criteria

- `is_error` comes from `item_completed`/`CommandExecution` (`status == "failed"` or non-zero `exit_code`), never from output text; the `CodexNormalizer` docstring quotes fixture line 14's `status: "failed"`/`exit_code: 1` and line 15's unchanged `Script completed` header as the evidence. No new fixture is captured.
- `CodexNormalizer` run over the interactive fixture: line 13 (ordinal 12, `custom_tool_call`) yields an `assistant` record whose `tool_use` block has `id == "call_IXnX78lRvoEbxkhwSt9fR6uq"`, `name == "Bash"`, and `input.command == "rg --files scripts/little_loops; sed -n '1,240p' pyproject.toml"` (unescaped); line 14 (`CommandExecution`) yields `None`; line 15 (ordinal 14) yields a `user` record whose `tool_result.tool_use_id` is the same `call_id`, whose `is_error is True`, and whose `content` omits the `Script completed` header block. Lines 21-23 and 25-27 yield the same shapes with no `is_error` key. All normalized records carry `timestamp`, `sessionId == "01a086ea-c8bc-79f1-9faa-1ce2716aa80f"`, and `cwd == "/workspace/project"`.
- `_extract_exec_cmd(input) == item.command[-1]` for all three fixture execs (lines 13/14, 21/22, 25/26); it handles double-quoted, single-quoted, and backtick `cmd:` values and unescapes `\"`/`\n`; an unrecognizable snippet makes the normalizer return the raw envelope, not `None`/raise.
- A `custom_tool_call_output` with no preceding `CommandExecution` (synthetic rollout) yields a `user` record with no `is_error` key; a `CommandExecution` whose `command[-1]` matches no pending cmd falls back to the most recent pending `call_id`.
- `ll-logs sequences --host codex` against a fixture home whose rollout is built inline (via `_write_rollout`, or the synthetic `rollout-synthetic-ll-exec.jsonl`) containing an `exec_command` whose `cmd` starts with `ll-issues` lists the `ll-issues` invocation. The real-capture fixtures `rollout-interactive.jsonl`/`rollout-exec.jsonl` are byte-identical before and after this issue.
- `ll-logs discover` under the union default includes a Codex-only workspace whose only ll signal is such an `exec_command`, with **no** `state_*.sqlite` present in the fixture home (i.e. via the date-dir scan fallback, which is what a test-built home has).
- `ll-logs eval-export --host codex` emits a `cmd`-runner fixture for it, with `session_id` equal to the rollout's `session_meta.payload.id`; on a synthetic rollout whose `ll-issues` exec's `CommandExecution` has `status: "failed"`, the same session's outcome is `failed`.
- `ll-logs scan-failures --host codex` on a rollout containing an `ll-issues` exec, a failed `CommandExecution`, and its output forms a cluster keyed on `ll-issues` (proves the `call_id` linkage and the `is_error is True` flag).
- `rebuild()` over a `raw_events` table ingested from the interactive fixture via a Codex handle derives three `Bash` `tool_events` rows (one failed) and a `sessions` row for `01a086ea-c8bc-79f1-9faa-1ce2716aa80f`; a second `rebuild()` yields identical counts.
- `test_ll_logs.py` Claude-shaped tests pass unmodified; `test_cli_ctx_stats.py` Codex cache-rate tests (`:981,998,1008,1038`) pass unmodified; `test_session_discovery.py:486` is the only existing test that changes, and only its two exec-subtype assertions.
- `docs/reference/HOST_COMPATIBILITY.md` `[^codexsessions]` footnote states the added `ll-logs` support, the `(a)`/`(b)` N/A result (including the outcome of the three-carrier user-prompt check), and names kimi-code as the remaining gap; `docs/codex/usage.md:101`, the fixture README, and the `parse_codex_rollout` docstring no longer promise blanket pass-through and document the `CommandExecution` fields; ENH-3422's "ingest-only / rebuild derives no rows from codex" statements are amended.

## Verification Notes

_Added by `/ll:verify-issues --auto` — 2026-09-10._

**Verdict: EVIDENCE_UNVERIFIED** (`ll-verify-evidence --json`, check B7, BUG-3282).

- The "Current Behavior" quote `const r = await tools.exec_command({ cmd: "<shell command>", workdir: ... })`, attributed to `scripts/tests/fixtures/codex/rollout-interactive.jsonl`, does not appear verbatim in that fixture at HEAD or in the working tree. The fixture's actual ordinal-12 `input` string is `const r = await tools.exec_command({\n  cmd: "rg --files scripts/little_loops; sed -n '1,240p' pyproject.toml",\n  workdir: "/workspace/project",\n  yield_time_ms: 10000,\n  max_output_tokens: 20000\n});\ntext(r.output);\n` — the issue's quote is a paraphrase (placeholders `<shell command>` / `workdir: ...` substituted for the literal values), not a fabricated claim about the shape. Per the current advisory policy (F3, decided 2026-08-21) this is the known low-precision *paraphrase* class and is **not** routed to `reconcile_issue`; flagging here only so the persisted `verify_verdict` reflects the deterministic check result. Recommended fix if this issue is reconciled: replace the placeholder quote with a literal fixture excerpt or mark it as illustrative prose rather than a quote.
- Everything else checked is accurate and current, including several assumptions that depend on ENH-3430 already being live in the working tree (uncommitted, matches this session's git status):
  - `codex.py` does not yet exist under `scripts/little_loops/session_store/` — consistent with this issue being unimplemented.
  - `parse_codex_rollout` (line 659), `parse_kimi_wire` (749), `parse_qwen_session` (779) in `sessions.py` match cited line numbers exactly; the current docstring still promises blanket pass-through as quoted.
  - `_is_ll_relevant`, `_detect_ll_signal`, `_record_has_error`, `_extract_eval_invocation`, `_collect_failure_clusters` in `cli/logs.py` (ENH-3430 already rewired onto `iter_events`/handles in the working tree) still key on Claude record shape (`user`/`assistant`/`queue-operation`, `Bash` tool_use) exactly as described; the `record.get("sessionId") or handle.session_id` fallback and the `tool_use.id` / `tool_result.tool_use_id` pairing in `_collect_failure_clusters` are present verbatim as claimed.
  - `_codex_cache_usage` (`cli/ctx_stats.py:351`) filters on `event.type == "event_msg"` / `payload.get("type") == "token_count"` only, confirming it is unaffected by the proposed `custom_tool_call`/`custom_tool_call_output` remapping.
  - The ENH-3422 sentence `"kimi-code rows are host-native \`wire.jsonl\` events (no normalizer), like codex."` exists verbatim as quoted.
  - `docs/reference/HOST_COMPATIBILITY.md`'s only two `ll-logs` mentions are at lines 596 and 651 (unrelated prose) as claimed; the `[^codexsessions]` footnote exists and does not yet state `ll-logs` support.
  - `docs/reference/API.md:9585` and `docs/codex/usage.md:101` match exactly.
  - Test citations `test_session_discovery.py:486` (exact), `:517`/`:548` (off by a few lines — actual bodies at ~514/~546, same test class, not a material discrepancy), `:753`, `:1006-1012` all correspond to the described tests.
  - No active required decision rules exist in `.ll/decisions.yaml`/`.ll/decisions.d/` to check for `DECISIONS_VIOLATION`.
  - Proposal-vs-code consequence check (B6): no `except`-clause or test-fixture incompatibility found; `test_parses_interactive_fixture_header_and_unknown_types_pass_through`'s two exec-subtype assertions are correctly identified as the only test needing to flip.
- Not independently reverified: the corpus-survey claim ("8,859 rollouts … only 3 exec calls, zero failures") is a point-in-time empirical scan of `~/.codex/sessions` on the dev machine and was not re-run by this pass.

**Graph**: provider=`codegraph` freshness=`stale` (not used to originate a verdict; all checks above were confirmed by direct grep/read).

## Status

**Open** | Created: 2026-09-10 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-10_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 67/100 → MODERATE

### Gaps to Address
- **Resolved as of this pass**: the Dependencies Hard Override (BUG-3051) that forced STOP here was keyed on ENH-3430's `status: open`. ENH-3430 is now `status: done` (commit `415d6b1cb`), so Criterion 5 no longer forces STOP. Criteria 1-4 all scored 20/20 (no duplicate implementation, matches the qwen/gemini/omp normalizer convention, rationale and Program Design fully specified, format-check clean). Re-run `/ll:confidence-check` to get a current aggregate verdict — this refine pass does not recompute the score itself.

### Outcome Risk Factors
- Change-surface / fanout: `parse_codex_rollout`/`iter_events` output is read directly by 6 dependent files (`session_store/__init__.py`, `cli/ctx_stats.py`, `user_messages.py`, and three test files) — broad enough that a subtle shape regression could surface away from this issue's own tests, even though the issue's Acceptance Criteria pin `test_cli_ctx_stats.py`/`test_ll_logs.py` as must-pass-unmodified regression guards.
- Ambiguity (**resolved 2026-09-10 review #2**): the `is_error` rule was unresolved pending a failed-exec capture; the committed interactive fixture already holds one (line 14, `exit_code: 1`), and the rule now reads `item_completed`/`CommandExecution` rather than output text. Residual ambiguity is the n=3 ordering assumption behind the `call_id` ↔ `CommandExecution` pairing, mitigated by the cmd-equality cross-check and the "unpaired output carries no `is_error`" fallback.

## Session Log
- `review (manual: pre-implementation review #2 — failed-exec sample already in committed fixture (line 14, exit_code 1); output-text is_error rule shown unworkable (identical header on failure); is_error sourced from item_completed/CommandExecution with cmd-keyed pairing; normalizer becomes stateful CodexNormalizer class; ENH-3422 rebuild() consequence decided (Codex no longer ingest-only, no replay shim); capture step, rollout-exec-failure fixture, and stale "like codex" strike removed; (b) check widened to three carriers; blocked_by cleared)` - 2026-09-10
- `/ll:confidence-check` - 2026-09-10T15:23:39 - `3d67c671-8653-4204-85ba-84a503b35f40.jsonl`
- `/ll:refine-issue` - 2026-09-10T15:16:33 - `60603960-f7ef-45f5-89b9-8c484017089f.jsonl`
- `/ll:confidence-check` - 2026-09-10T05:48:53 - `77ab7fdc-7869-4b18-b7da-f619a8919cd3.jsonl`
- `/ll:verify-issues` - 2026-09-10T05:39:27 - `6d2a11b3-eb6b-4880-aa61-0eef42449941.jsonl`
- `review (manual: pre-implementation review — normalizer landing spot decided (session_store/codex.py, parser-level); pass-through contract flips enumerated; failed-exec capture required (corpus survey: 3 exec calls total, zero failures); call_id linkage + timestamp/sessionId/cwd stamping specified; quote-tolerant cmd regex + unescape; real-capture fixtures frozen; HOST_COMPATIBILITY row → footnote)` - 2026-09-10
- `/ll:reconcile-issue` - 2026-09-10T05:24:39 - `7c0566e8-82de-4bff-a1c2-39aedcf32886.jsonl`
- `/ll:refine-issue` - 2026-09-10T05:22:49 - `b0553632-9109-487b-a1e0-f4e935a2ac32.jsonl`
- `/ll:format-issue` - 2026-09-10T05:15:13 - `583c50e2-277e-42f5-a42d-ed4c75663779.jsonl`
