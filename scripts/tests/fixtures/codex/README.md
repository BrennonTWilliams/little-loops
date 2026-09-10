# Codex rollout fixtures

Captured 2026-09-09 against `codex-cli 0.152.1`, in this repo's own working
tree on the maintainer's machine (absolute path sanitized — see Sanitization
applied below).

- `rollout-interactive.jsonl` — an interactive `codex` (TUI) session that issued
  three shell tool calls (`custom_tool_call`, `name: "exec"`) reading repo files
  (`rg --files`, `find`, `sed -n`) and one `reasoning` item.
- `rollout-exec.jsonl` — a `codex exec "echo hello"` one-shot.

Also used as the AC fixtures for ENH-3422 D4: `test_backfill_ingests_codex_fixtures_via_handles`
(`scripts/tests/test_session_store_lifecycle.py`) places both files under a
`tmp_home/.codex/sessions/2026/09/08/` layout and drives them through
`detect_sessions()` → `backfill(handles=...)` end to end.

## cli_version

`0.152.1` (both fixtures). **Re-capture rule**: re-run `ll-learning-tests prove
codex-rollout` and re-capture both fixtures whenever `codex --version` differs
from `0.152.1`.

## Sanitization applied

- `session_meta.payload.base_instructions.text` truncated to a short
  placeholder on both fixtures. **Original length: 17,730 chars** (identical on
  both — same system prompt). `base_instructions.provenance` (`{"type": "model",
  "model": "gpt-5.6-sol"}`) left intact — not machine-specific.
- Original line-1 (`session_meta`) byte length before truncation: **18,672
  bytes** (interactive), **18,674 bytes** (exec).
- Every occurrence of the repo's absolute working-directory path rewritten to
  `/workspace/project`, consistently across `session_meta.payload.cwd`,
  `turn_context.payload.cwd`, and tool-call arguments/outputs.
- All other occurrences of the maintainer's home directory (e.g. inside
  `base_instructions`' skill-root listing before truncation) rewritten to
  `/workspace/home`.
- `git.repository_url` (`https://github.com/BrennonTWilliams/little-loops.git`)
  and `git.commit_hash` left as-is — public repo metadata, per Testing →
  Fixture capture.
- Verified clean: `ll-verify-private-refs scripts/tests/fixtures/codex/` → PASS.

## Per-turn-usage finding (Testing → Fixture capture item 2 — now answered)

**Yes, per-turn usage is present directly in the rollout file.** Both fixtures
contain `event_msg.payload.type == "token_count"` records with
`total_token_usage`/`last_token_usage`/`model_context_window`. This is a new
finding: the local pre-capture corpus (0.98.0/0.130.0, all `exec` one-shots) had
zero `token_count` events, and the issue's own Testing section treated the
question as open. `docs/reference/HOST_COMPATIBILITY.md`'s `[^tok-codex]`
footnote documents a different, complementary source (`codex exec --json`
stdout's `turn.completed` event) and is not contradicted by this — but the
rollout-file question it left open is now closed.

## Agent-thread finding

Neither fixture session has `threads.agent_role`/`agent_nickname` set, and
neither appears in `thread_spawn_edges` (checked directly against
`state_5.sqlite`). Both are ordinary top-level `thread_source = "user"`
sessions — expected, since neither was a spawned subagent. This confirms (does
not contradict) Decided #2's Codex agent rule; it does not exercise the
`is_agent = True` path. A future capture from an actual subagent invocation
would be needed to prove that branch directly.

## Archive-behavior finding (§ Codex On-Disk Layout → Archived threads)

Archived the exec-fixture session (`codex archive <session-id>`, the
`rollout-exec.jsonl` source session) after copying its rollout out for this
fixture. Result, confirmed against the live `~/.codex`:

- Rollout moved to `~/.codex/archived_sessions/rollout-<timestamp>-<id>.jsonl`
  — **directly under `archived_sessions/`, with no `YYYY/MM/DD/`
  subdirectory.** This corrects the issue's prior source-read-based prediction
  (a date-tree mirror of `sessions/`); the openai/codex `main` source that
  predicted the date tree did not match this installed CLI's actual behavior.
- `threads.rollout_path` rewritten to the new path; `threads.archived = 1`;
  `threads.archived_at` set to the archive timestamp.

The committed `rollout-exec.jsonl` fixture reflects the file's content from
*before* archiving (copied first) — archiving only changes the file's location
in a live `~/.codex`, not its content.

## 0.152.1 layout drift vs. the 0.98.0/0.130.0 corpus

See the issue's § Codex On-Disk Layout → Record shape (0.152.1 additions) for
the full list; summary:

- New top-level `type: "world_state"` (payload `{full, state}`).
- New `response_item.payload.type` values: `custom_tool_call`,
  `custom_tool_call_output`, `reasoning`.
- New `event_msg.payload.type` value: `item_completed`.
- New `session_meta.payload` fields: `context_window`, `git`, `history_mode`,
  `session_id`, `thread_source`.

The parser must treat all of these as opaque pass-through content — no new
schema/enum for the discovery seam — **except** `custom_tool_call`/
`custom_tool_call_output` (ENH-3433), which `CodexNormalizer` replaces with
Claude-shaped `assistant`/`user` records.

## `item_completed`/`CommandExecution` (ENH-3433)

Sits between a `custom_tool_call` and its `custom_tool_call_output` (observed
order on all 3 fixture execs: `custom_tool_call` → `item_completed` →
`custom_tool_call_output`). `item.type == "CommandExecution"` carries the
already-parsed shell invocation — fields: `id` (`exec-<uuid>`, shares no key
with the `custom_tool_call`'s `call_id`), `command` (`["/bin/zsh", "-lc",
"<cmd>"]`), `cwd` (a `file://` URI), `status` (`"completed"`/`"failed"`),
`exit_code`, `stdout`, `stderr`, `aggregated_output`, `duration`,
`formatted_output`. `CodexNormalizer` reads this item to flag the paired
`custom_tool_call_output`'s `is_error`, then lets it pass through untouched
as its own `event_msg` event. **Line 14 of `rollout-interactive.jsonl` is
the committed real-capture failed-exec sample**: `status: "failed"`,
`exit_code: 1`, `aggregated_output` ending in `sed: pyproject.toml: No such
file or directory\n` — its paired output at line 15 has the exact same
`"Script completed\nWall time 0.1 seconds\nOutput:\n"` header as every
successful call's, which is why the failure signal must come from this item,
never from the output text.
