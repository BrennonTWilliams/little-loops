---
id: ENH-3433
type: ENH
title: Detect ll activity in Codex-shaped session records so ll-logs sees Codex sessions
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T05:10:54Z'
labels:
- multi-host
- observability
blocked_by:
- ENH-3430
blocks: []
relates_to:
- ENH-3422
- ENH-3429
---

# ENH-3433: Detect ll activity in Codex-shaped session records so ll-logs sees Codex sessions

## Summary

Follow-up split out of ENH-3430's pre-implementation review (2026-09-10). ENH-3430 rewires `ll-logs` onto `detect_sessions`/`iter_events`, so Codex (and kimi-code) sessions are *enumerated* — but every ll-signal consumer in `cli/logs.py` keys on Claude record shape, so those sessions contribute zero events. This issue adds host-shape ll-signal detection so a Codex session's `ll-*` shell calls and `/ll:` prompts show up in `ll-logs sequences`/`extract`/`scan-failures`/`eval-export` and count toward the `--all` ll-activity filter.

## Current Behavior

The five ll-signal readers in `scripts/little_loops/cli/logs.py` — `_is_ll_relevant` (52), `_detect_ll_signal` (358), `_record_has_error` (1920), `_extract_eval_invocation` (1900), and the inline walk in `_collect_failure_clusters` (1399-1415) — all check `record["type"] in {"user", "assistant", "queue-operation"}` and `message.content[].tool_use.name == "Bash"`.

`iter_events` on a Codex handle (`session_store/sessions.py::parse_codex_rollout`, 659) yields `SessionEvent(type=<envelope type>, payload=<inner payload>)` untouched: envelope types are `session_meta`, `turn_context`, `world_state`, `response_item`, `event_msg`; a shell call is `response_item` with `payload.type == "custom_tool_call"`, `payload.name == "exec"`, and `payload.input` a JS snippet of the form `const r = await tools.exec_command({ cmd: "<shell command>", workdir: ... })` (see `scripts/tests/fixtures/codex/rollout-interactive.jsonl`, ordinals 12 and 20). The tool result arrives as `custom_tool_call_output`. No Codex→Claude-shape normalizer exists anywhere (unlike qwen/gemini/omp, whose parsers normalize before yielding). kimi-code (`parse_kimi_wire`, 749) is likewise raw passthrough.

Consequence: after ENH-3430, `ll-logs sequences` in a workspace with only Codex sessions prints "No sequences found."; `--all` drops Codex-only workspaces because `_is_ll_relevant` never fires; `eval-export` produces no fixtures from Codex runs.

## Expected Behavior

- A Codex session containing an `exec_command` whose `cmd` matches `\bll-\w+` is ll-relevant; `_detect_ll_signal` returns `_InvocationSignal(tool_name=<ll-tool>, runner="bash", input_context=<cmd>)` for it.
- A Codex `custom_tool_call_output` (or `event_msg` equivalent) carrying a non-zero exit / error marker satisfies `_record_has_error`, so `eval-export` can classify the session outcome.
- Session id for Codex records comes from the handle (`SessionHandle.session_id`), never from the payload — ENH-3430 already threads `payload.get("sessionId") or handle.session_id` through every reader; this issue relies on that.
- `_is_ll_relevant`'s `(a)` queue-operation and `(b)` `<command-name>/ll:` user-prompt signals have no Codex analogue today (Codex has no `/ll:` skill dispatch); document as not applicable rather than emulate.
- Claude-shaped behavior is byte-for-byte unchanged; kimi-code is either covered by the same mechanism or explicitly listed as a remaining gap.

## Proposed Solution

Prefer a single seam over five per-reader patches: a `_codex_to_claude_shape(event: SessionEvent) -> dict | None` adapter (or a `normalize` step inside `parse_codex_rollout`, matching how `parse_qwen_session` normalizes via `normalize_qwen_record`) that maps `custom_tool_call`/`exec_command` to a Claude `assistant` record with a `tool_use` block named `Bash` and `input.command = cmd`, and `custom_tool_call_output` errors to a `user` record with a `tool_result` block flagged `is_error`. Then all five readers work unchanged. Decide, and record in the issue, whether the normalization belongs in `session_store` (benefits `_backfill_raw_events` under ENH-3422 too, and `ll-messages`) or stays `cli/logs.py`-local. `ll-ctx-stats` (`cli/ctx_stats.py::_codex_cache_usage`) reads `event_msg`/`token_count` directly and must keep working if normalization moves into the parser — so a parser-level normalizer must pass those through, not drop them.

Extracting `cmd` from the JS snippet needs a tolerant regex (`cmd:\s*"((?:[^"\\]|\\.)*)"`), since the snippet is model-authored, not a fixed template.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Dependencies

Blocked by ENH-3430 (the handles-based readers and the `sessionId` fallback this relies on). Relates to ENH-3422 (if the normalizer lands in `session_store`, its backfill consumes it for free) and ENH-3429 (`_codex_cache_usage` pass-through constraint).

## Acceptance Criteria

- `ll-logs sequences --host codex` against a fixture home built from `scripts/tests/fixtures/codex/rollout-interactive.jsonl` (augmented with an `exec_command` whose `cmd` starts with `ll-issues`) lists the `ll-issues` invocation.
- `ll-logs discover` under the union default includes a Codex-only workspace whose only ll signal is such an `exec_command`.
- `ll-logs eval-export --host codex` emits a `cmd`-runner fixture for it, with `session_id` equal to the rollout's `session_meta.payload.id`.
- `test_ll_logs.py` Claude-shaped tests pass unmodified; `test_ctx_stats*` Codex cache-rate tests pass unmodified.
- `docs/reference/HOST_COMPATIBILITY.md` `ll-logs` row for Codex flips from "enumerated, no events" to supported (or names the remaining kimi-code gap).

## Status

**Open** | Created: 2026-09-10 | Priority: P3
