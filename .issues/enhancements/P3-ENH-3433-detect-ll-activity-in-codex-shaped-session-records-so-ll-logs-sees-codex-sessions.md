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
blocked_by:
- ENH-3430
blocks: []
relates_to:
- ENH-3422
- ENH-3429
confidence_score: 80
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

`iter_events` on a Codex handle (`session_store/sessions.py::parse_codex_rollout`, 659) yields `SessionEvent(type=<envelope type>, payload=<inner payload>)` untouched: envelope types are `session_meta`, `turn_context`, `world_state`, `response_item`, `event_msg`; a shell call is `response_item` with `payload.type == "custom_tool_call"`, `payload.name == "exec"`, `payload.call_id`, and `payload.input` a JS snippet of the form `const r = await tools.exec_command({ cmd: "<shell command>", workdir: ... })` (see `scripts/tests/fixtures/codex/rollout-interactive.jsonl`, ordinals 12 and 20). The tool result arrives as `custom_tool_call_output` with the same `call_id` and `output: [{"type": "input_text", "text": ...}, ...]`, the first block being a `Script completed\nWall time N seconds\nOutput:\n` header. The inner payload carries neither the envelope `timestamp` nor any `sessionId`. No Codex→Claude-shape normalizer exists anywhere (unlike qwen/gemini/omp, whose parsers normalize before yielding). kimi-code (`parse_kimi_wire`, 749) is likewise raw passthrough.

**Evidence base is thin (surveyed 2026-09-10).** Across the 8,859 rollouts under `~/.codex/sessions` on the dev machine, the *only* `exec` tool calls that exist are the 3 `custom_tool_call`/`exec` records in the fixture's source session (codex-cli 0.152.1). The remaining 8,858 rollouts (0.98.0 and 0.130.0, all `codex exec` one-shots) contain no `custom_tool_call`, `function_call`, or `local_shell_call` records at all. All 3 observed snippets use double-quoted `cmd:` and all 3 outputs succeeded — **no failed-exec output has ever been observed**, so the error-marker shape is unknown, not merely undocumented.

Consequence: after ENH-3430, `ll-logs sequences` in a workspace with only Codex sessions prints "No sequences found."; `--all` drops Codex-only workspaces because `_is_ll_relevant` never fires; `eval-export` produces no fixtures from Codex runs.

## Expected Behavior

- A Codex session containing an `exec_command` whose `cmd` matches `\bll-\w+` is ll-relevant; `_detect_ll_signal` returns `_InvocationSignal(tool_name=<ll-tool>, runner="bash", input_context=<cmd>)` for it, where `<cmd>` is the *unescaped* shell command (JS string escapes such as `\"` and `\n` resolved), not the raw regex capture.
- A Codex `custom_tool_call_output` whose output carries the failure marker **captured in the pre-implementation step below** satisfies `_record_has_error`, so `eval-export` can classify the session outcome. Until that sample exists the marker rule is unspecified; do not guess one from the success-only fixtures.
- The normalized `tool_use` block carries `id = payload.call_id` and the normalized `tool_result` block carries `tool_use_id = payload.call_id`, so `_collect_failure_clusters` can pair a Codex error with the `ll-*` CLI that produced it. Without this linkage Codex errors count toward `eval-export` outcomes but never form failure clusters.
- The normalized record carries `timestamp` (from the envelope) and `sessionId` + `cwd` (from line 1's `session_meta.payload.id` / `.cwd`, which `parse_codex_rollout` sees before any tool call). ENH-3430's `payload.get("sessionId") or handle.session_id` fallback stays as belt-and-braces for every reader, but Codex records are self-sufficient — `_cmd_extract`, which writes the record into the index and reads `timestamp` from it, works without the fallback.
- `_is_ll_relevant`'s `(a)` queue-operation and `(b)` `<command-name>/ll:` user-prompt signals have no Codex analogue today (Codex has no `/ll:` skill dispatch); document as not applicable rather than emulate. One check is owed before closing that door: Codex's `event_msg`/`user_message` records (present in every 0.98.0/0.130.0 rollout) are the user-prompt carrier — confirm that a Codex skill invocation (`$skill` / `/prompts:` syntax) does not surface there as an `ll-`-prefixed marker; if it does, that is a `(b)` analogue and gets a one-line mapping, otherwise record "checked, none" in the doc row.
- Every Codex record type other than `custom_tool_call` and `custom_tool_call_output` still passes through `parse_codex_rollout` untouched (`session_meta`, `turn_context`, `world_state`, `event_msg` incl. `token_count`, `reasoning`, `message`, `item_completed`, …).
- Claude-shaped behavior is byte-for-byte unchanged; kimi-code is either covered by the same mechanism or explicitly listed as a remaining gap.

## Proposed Solution

**Decision (2026-09-10 review): parser-level normalizer in a new `scripts/little_loops/session_store/codex.py`, following the qwen convention exactly.** A `cli/logs.py`-local adapter was rejected because ENH-3422 already specifies that `raw_events` rows are Claude-shaped for every normalizer host and lists Codex as "no normalizer"; a logs-local adapter would leave the backfill/ingest path with the same blindness and force a second Codex normalizer later. Parser-level gives `_backfill_raw_events` (ENH-3422) and `ll-messages` the mapping for free.

Shape: `normalize_codex_record(envelope: dict, *, session_id: str, cwd: str) -> dict | None` maps

- `response_item`/`custom_tool_call` with `name == "exec"` → a Claude `assistant` record: `{"type": "assistant", "timestamp": <envelope.timestamp>, "sessionId": <session_id>, "cwd": <cwd>, "message": {"role": "assistant", "content": [{"type": "tool_use", "id": <payload.call_id>, "name": "Bash", "input": {"command": <unescaped cmd>}}]}}`. If `cmd` cannot be extracted, return the raw envelope unchanged (never drop a record).
- `response_item`/`custom_tool_call_output` → a Claude `user` record with one `tool_result` block: `tool_use_id = payload.call_id`, `content = [{"type": "text", "text": ...}]` from the `output[].text` blocks (this is the shape `_extract_error_text` already reads), `is_error` per the marker rule derived from the captured failure sample.
- everything else → `None`, meaning **pass the raw envelope through untouched** (unlike qwen, where `None` means drop). This is the pass-through guarantee that keeps `cli/ctx_stats.py::_codex_cache_usage`'s `event_msg`/`token_count` reads and the `session_meta` header tests working unmodified.

`parse_codex_rollout` becomes stateful in the smallest way: it remembers `session_meta.payload.id` and `.cwd` from line 1 and passes them into the normalizer for every later line. `SessionEvent.type` is taken from the normalized record's `type` (so `assistant`/`user`), mirroring `parse_qwen_session`.

**Pre-implementation step (required, ~5 minutes): capture a failed-exec sample.** codex-cli 0.152.1 is installed on the dev machine. Run one `codex exec` (sandboxed, in a throwaway dir) whose prompt makes the model execute a command that exits non-zero, e.g. `false` or `python -c "import sys; sys.exit(3)"`, then locate the resulting rollout under `~/.codex/sessions/<today>/` and copy its `custom_tool_call`/`custom_tool_call_output` pair (sanitized per `scripts/tests/fixtures/codex/README.md`) into a new fixture. The `is_error` rule is whatever discriminates that output from the `Script completed` header — derive it from the sample, and record the observed header text in this issue and in the normalizer docstring. `_collect_failure_clusters` already clusters on a `Traceback (most recent call last)` in content regardless of `is_error`, so Python-traceback failures are covered even before this rule lands; only non-traceback non-zero exits depend on it.

**`cmd` extraction.** `_extract_exec_cmd(js_snippet: str) -> str | None` accepts double-quoted, single-quoted, and backtick-delimited `cmd:` values (`cmd:\s*(["'`])((?:(?!\1)[^\\]|\\.)*)\1`, `re.DOTALL`), since the snippet is model-authored and n=3 from a single session is not enough to assume double quotes forever. The captured group is a JS-escaped string: unescape it with `json.loads('"' + captured + '"')` for the double-quoted case (JS and JSON escapes coincide for everything the model emits in practice), falling back to the raw capture on `ValueError`; for single-quote/backtick captures, apply the same after swapping the delimiter escapes. `_is_ll_relevant`/`_detect_ll_signal` then see the true shell text. A snippet with several `ll-*` invocations (`ll-issues … && ll-loop …`) yields the first match, same as Claude's Bash branch.

## Scope Boundaries

- **In scope**: `session_store/codex.py::normalize_codex_record` + `_extract_exec_cmd`; wiring it into `parse_codex_rollout` with `session_meta`-derived `sessionId`/`cwd` and envelope `timestamp` stamping; capturing and committing a failed-exec sample; flipping the three pass-through contract statements (parser docstring, `test_parses_interactive_fixture_header_and_unknown_types_pass_through`, `docs/codex/usage.md`) to the new contract; the `(b)`-analogue check on `event_msg`/`user_message`; documenting the `/ll:` skill-dispatch and queue-operation signals as not applicable to Codex; updating the stale "kimi-code rows are host-native … like codex" sentence in ENH-3422.
- **Out of scope**: kimi-code normalization beyond "covered for free if the mechanism generalizes, else documented as a remaining gap" (Expected Behavior); rewriting `_codex_cache_usage`'s direct `event_msg`/`token_count` reads (must keep working unmodified per Proposed Solution); any change to Claude-shaped record handling, which must stay byte-for-byte unchanged; editing the committed real-capture fixtures `rollout-interactive.jsonl`/`rollout-exec.jsonl` (see Acceptance Criteria — ll-invoking rollouts are built inline or as a separately named synthetic fixture).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

**Files to Modify (decided 2026-09-10 — parser-level, see Proposed Solution)**
- `scripts/little_loops/session_store/codex.py` — **new**; `normalize_codex_record` + `_extract_exec_cmd`, module docstring modeled on `session_store/qwen.py`'s (documents the observed shapes, the n=3 evidence base, and the captured failure marker).
- `scripts/little_loops/session_store/sessions.py` — `parse_codex_rollout` (line 659) wraps the normalizer the way `parse_qwen_session` (779) wraps `normalize_qwen_record`, plus remembers `session_meta` id/cwd from line 1. **Its docstring (665-671) currently promises every subtype "is passed through untouched … never enumerates the subtype vocabulary"** — rewrite to: every type passes through except `custom_tool_call`/`custom_tool_call_output`, which are replaced by Claude `assistant`/`user` records. `parse_kimi_wire` (749) is untouched.
- `scripts/little_loops/session_store/__init__.py` — export `normalize_codex_record` alongside `normalize_qwen_record` (111, 251).
- `scripts/tests/test_session_discovery.py:486` — `test_parses_interactive_fixture_header_and_unknown_types_pass_through` asserts `custom_tool_call` and `custom_tool_call_output` appear in the yielded subtypes; flip those two assertions to the new contract (they are now absent; `assistant`/`user` events with the `call_id` linkage are present) while keeping the `reasoning`/`item_completed`/`token_count`/`world_state` pass-through assertions verbatim.
- `docs/codex/usage.md:101` — the sentence "yields every record's host-native `payload` untouched … the parser passes all of them through rather than enumerating a fixed vocabulary" is now false for the two exec subtypes; amend.
- `.issues/enhancements/P2-ENH-3422-*.md` — the Proposed Solution sentence "kimi-code rows are host-native `wire.jsonl` events (no normalizer), like codex" becomes stale; strike "like codex" and note Codex rows are pre-normalized for the exec subtypes.
- `scripts/little_loops/cli/logs.py` — **no changes**; the five readers (`_is_ll_relevant`, `_detect_ll_signal`, `_record_has_error`, `_extract_eval_invocation`, `_collect_failure_clusters`) consume the normalized records as-is.

**Conventions in Force**
- Per-host normalization lives in its own module exposing a `normalize_<host>_record`/`normalize_<host>_session` function, wrapped by a `parse_<host>_*` generator in `sessions.py` that stamps `host` and yields `SessionEvent` — evidence: `session_store/qwen.py:59` (`normalize_qwen_record(record: dict) -> dict | None`), `session_store/gemini.py:40` (`normalize_gemini_session(path: Path) -> Iterator[dict]`), `session_store/omp.py:54` (`normalize_omp_session(path: Path) -> Iterator[dict]`), wrapped at `sessions.py:779,814,827` respectively.
- Per-host normalizers get their own `test_enh_NNNN_<host>_normalizer.py` test file, plus a cross-check test in `test_session_discovery.py` asserting `iter_events` output matches the normalizer's direct output — evidence: `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_session_discovery.py:753` (`test_qwen_iter_events_matches_normalize_qwen_record`).

**Tests**
- `scripts/tests/test_session_discovery.py:486,517,548` — existing direct `parse_codex_rollout` tests (486 flips, see Files to Modify); `:1006,1012` — direct `parse_kimi_wire` tests. New coverage goes in `test_enh_3433_codex_normalizer.py` plus a `test_codex_iter_events_matches_normalize_codex_record` cross-check next to `:753`.
- `scripts/tests/fixtures/codex/rollout-interactive.jsonl` and `rollout-exec.jsonl` — existing real-capture fixtures, **not to be edited**: `scripts/tests/fixtures/codex/README.md:14` ties them to a `cli_version`-keyed re-capture rule, and a hand-inserted `ll-issues` exec would break that provenance. Build ll-invoking rollouts inline with `test_session_discovery.py:35::_write_rollout` (extend it to accept extra envelope lines) or add a clearly named synthetic fixture (`rollout-synthetic-ll-exec.jsonl`) with its own README paragraph. The captured failed-exec sample is a third, real-capture fixture (`rollout-exec-failure.jsonl`) under the same re-capture rule.
- `scripts/tests/test_ll_logs.py:113,118,144,150` — existing `--host codex` CLI-parsing coverage; no ll-signal-detection-on-Codex-shape assertions exist yet (the gap this issue's Acceptance Criteria requires).
- `scripts/tests/test_cli_ctx_stats.py:981,998,1008,1038` — Codex cache-rate regression tests reading `iter_events` output directly; must keep passing unmodified per Acceptance Criteria.

**Documentation**
- `docs/reference/HOST_COMPATIBILITY.md` — the `## Runner Capabilities` matrix (251) is *runner* capabilities (streaming, permission skip, token reporting…), not per-CLI observability, so an "`ll-logs` row" does not belong in it. Land the support statement as an extension of the existing `[^codexsessions]` footnote (556-566), which already describes `parse_codex_rollout`: one sentence on which record types are normalized for `ll-logs`, one on the `(a)`/`(b)` signals being N/A, one naming kimi-code as the remaining gap. No `ll-logs` row and no "enumerated, no events" phrase exists in the file today (its only two `ll-logs` mentions, 596 and 651, are unrelated prose).
- `docs/reference/API.md:9585` — `parse_codex_rollout` signature doc; add `normalize_codex_record` next to `normalize_qwen_record`'s entry.
- `docs/codex/usage.md:101` — pass-through prose to amend (see Files to Modify).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/session_store/__init__.py:138,140,280,283` — re-exports `parse_codex_rollout`/`parse_kimi_wire`
- `scripts/little_loops/cli/ctx_stats.py:20,351,419` — imports `_aggregate_skill_stats` from `cli/logs.py`; `_codex_cache_usage` (351) reads `event_msg`/`token_count` directly from `iter_events` output and is called at 419 — must keep working unmodified per Proposed Solution
- `scripts/little_loops/user_messages.py:35` — imports `session_store` symbols
- `scripts/tests/test_session_discovery.py:489,517,548,753,1006,1012` — direct parser tests and the qwen cross-check pattern (see Conventions in Force above)
- `scripts/tests/test_cli_ctx_stats.py:981,998,1008,1038` — Codex cache-rate regression tests
- `scripts/tests/test_ll_logs.py:113,118,144,150` — existing `--host codex` CLI-parsing coverage

## Program Design

### Types

- Reuses existing `SessionEvent` (`scripts/little_loops/session_store/sessions.py`); no new types.

### Signatures

- `normalize_codex_record(envelope: dict, *, session_id: str, cwd: str) -> dict | None` (`scripts/little_loops/session_store/codex.py`) — maps `response_item`/`custom_tool_call` (`name == "exec"`) to a Claude `assistant` record with `tool_use(id=call_id, name="Bash", input={"command": cmd})`, and `response_item`/`custom_tool_call_output` to a `user` record with `tool_result(tool_use_id=call_id, content=[text blocks], is_error=<marker rule>)`; stamps `timestamp` (envelope), `sessionId`, `cwd`. Returns `None` for every other record, which the caller treats as "pass raw envelope through" — not "drop".
- `_extract_exec_cmd(js_snippet: str) -> str | None` (same module) — quote-tolerant `cmd:` extraction from the model-authored `tools.exec_command({...})` snippet, with JS-escape unescaping and raw-capture fallback.
- `parse_codex_rollout(path: Path) -> Iterator[SessionEvent]` — signature unchanged; body remembers `session_meta` id/cwd from line 1 and applies `normalize_codex_record` per line.

### Call Path

`iter_events` -> `parse_codex_rollout` -> `normalize_codex_record` (-> `_extract_exec_cmd`) -> `SessionEvent(type="assistant"|"user", payload=<Claude-shaped>)` -> `_is_ll_relevant` / `_detect_ll_signal` / `_record_has_error` / `_extract_eval_invocation` / `_collect_failure_clusters` (`scripts/little_loops/cli/logs.py`, unchanged) and, under ENH-3422, `_backfill_raw_events`.

## Impact

- **Priority**: P3 - follow-up split from ENH-3430's pre-implementation review; ENH-3430 lands independently, but `ll-logs` stays blind to Codex-only workspaces until this closes.
- **Effort**: Medium - one normalizer plus a regex helper is the core work, plus a ~5-minute failed-exec capture; the five readers in `cli/logs.py` consume it unchanged once Claude-shaped records are produced, so this isn't five separate patches.
- **Risk**: Low-Medium - Claude-shaped paths are untouched and `test_ll_logs.py` / `test_cli_ctx_stats.py` act as regression guards; the residual risk is shape drift — the exec-call shape is verified on exactly one 0.152.1 session (n=3 calls), so the normalizer must degrade to raw pass-through (never drop, never raise) on anything it doesn't recognize.
- **Breaking Change**: No for `cli/logs.py` consumers. **Yes, narrowly, for direct `parse_codex_rollout`/`iter_events` consumers** that expected the two exec subtypes raw — the only such consumer in-tree is the test at `test_session_discovery.py:486`; `_codex_cache_usage` reads `event_msg` only and is unaffected.

## Dependencies

Blocked by ENH-3430 (the handles-based readers in `cli/logs.py`; the `sessionId`/`handle.session_id` fallback there becomes belt-and-braces for Codex once this issue stamps `sessionId` in the parser). Relates to ENH-3422 (its backfill consumes the parser-level normalizer for free; its "like codex" sentence must be updated here) and ENH-3429 (`_codex_cache_usage` pass-through constraint).

## Acceptance Criteria

- A real failed-exec `custom_tool_call`/`custom_tool_call_output` pair captured from codex-cli 0.152.1 is committed under `scripts/tests/fixtures/codex/` with a README entry, and the `is_error` rule in `normalize_codex_record` is derived from (and its docstring quotes) that sample's header text.
- `normalize_codex_record` on the interactive fixture's ordinal-12 `custom_tool_call` returns an `assistant` record whose `tool_use` block has `id == "call_IXnX78lRvoEbxkhwSt9fR6uq"`, `name == "Bash"`, and `input.command == "rg --files scripts/little_loops; sed -n '1,240p' pyproject.toml"` (unescaped); on ordinal 14 returns a `user` record whose `tool_result.tool_use_id` is the same `call_id`. Both carry `timestamp`, `sessionId == "01a086ea-c8bc-79f1-9faa-1ce2716aa80f"`, and `cwd == "/workspace/project"`.
- `_extract_exec_cmd` handles double-quoted, single-quoted, and backtick `cmd:` values and unescapes `\"`/`\n`; an unrecognizable snippet makes the normalizer return the raw envelope, not `None`/raise.
- `ll-logs sequences --host codex` against a fixture home whose rollout is built inline (via `_write_rollout`, or the synthetic `rollout-synthetic-ll-exec.jsonl`) containing an `exec_command` whose `cmd` starts with `ll-issues` lists the `ll-issues` invocation. The real-capture fixtures `rollout-interactive.jsonl`/`rollout-exec.jsonl` are byte-identical before and after this issue.
- `ll-logs discover` under the union default includes a Codex-only workspace whose only ll signal is such an `exec_command`, with **no** `state_*.sqlite` present in the fixture home (i.e. via the date-dir scan fallback, which is what a test-built home has).
- `ll-logs eval-export --host codex` emits a `cmd`-runner fixture for it, with `session_id` equal to the rollout's `session_meta.payload.id`; with the failed-exec fixture the same session's outcome is `failed`.
- `ll-logs scan-failures --host codex` on a rollout containing an `ll-issues` exec followed by its failing output forms a cluster keyed on `ll-issues` (proves the `call_id` linkage).
- `test_ll_logs.py` Claude-shaped tests pass unmodified; `test_cli_ctx_stats.py` Codex cache-rate tests (`:981,998,1008,1038`) pass unmodified; `test_session_discovery.py:486` is the only existing test that changes, and only its two exec-subtype assertions.
- `docs/reference/HOST_COMPATIBILITY.md` `[^codexsessions]` footnote states the added `ll-logs` support, the `(a)`/`(b)` N/A result (including the `user_message` check outcome), and names kimi-code as the remaining gap; `docs/codex/usage.md:101` and the `parse_codex_rollout` docstring no longer promise blanket pass-through; ENH-3422's "like codex" sentence is updated.

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
- Blocked by ENH-3430, which is still `status: open` (Dependencies Hard Override, BUG-3051). Criteria 1-4 all score 20/20 (no duplicate implementation, matches the qwen/gemini/omp normalizer convention, rationale and Program Design fully specified, format-check clean), but Criterion 5 scores 0 and forces STOP regardless of the 80/100 aggregate. Land or advance ENH-3430 first, or re-run this check once it reaches `done`.

### Outcome Risk Factors
- Change-surface / fanout: `parse_codex_rollout`/`iter_events` output is read directly by 6 dependent files (`session_store/__init__.py`, `cli/ctx_stats.py`, `user_messages.py`, and three test files) — broad enough that a subtle shape regression could surface away from this issue's own tests, even though the issue's Acceptance Criteria pin `test_cli_ctx_stats.py`/`test_ll_logs.py` as must-pass-unmodified regression guards.
- Ambiguity: the `is_error` marker rule for `custom_tool_call_output` is explicitly unresolved pending the required pre-implementation capture (a failed `codex exec` sample) — implementation cannot finish the error-detection path until that ~5-minute capture step is done first.

## Session Log
- `/ll:confidence-check` - 2026-09-10T05:48:53 - `77ab7fdc-7869-4b18-b7da-f619a8919cd3.jsonl`
- `/ll:verify-issues` - 2026-09-10T05:39:27 - `6d2a11b3-eb6b-4880-aa61-0eef42449941.jsonl`
- `review (manual: pre-implementation review — normalizer landing spot decided (session_store/codex.py, parser-level); pass-through contract flips enumerated; failed-exec capture required (corpus survey: 3 exec calls total, zero failures); call_id linkage + timestamp/sessionId/cwd stamping specified; quote-tolerant cmd regex + unescape; real-capture fixtures frozen; HOST_COMPATIBILITY row → footnote)` - 2026-09-10
- `/ll:reconcile-issue` - 2026-09-10T05:24:39 - `7c0566e8-82de-4bff-a1c2-39aedcf32886.jsonl`
- `/ll:refine-issue` - 2026-09-10T05:22:49 - `b0553632-9109-487b-a1e0-f4e935a2ac32.jsonl`
- `/ll:format-issue` - 2026-09-10T05:15:13 - `583c50e2-277e-42f5-a42d-ed4c75663779.jsonl`
