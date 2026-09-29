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

## Live `codex exec --json` usage contract (BUG-3531 Decision 6)

Captured 2026-09-24 against `codex-cli 0.152.1`, model `gpt-5.6-sol` (pinned
with `-m`; the machine's configured default model is rejected by 0.152.1), in an
empty scratch directory with `--sandbox read-only --skip-git-repo-check` and
stdin closed:

1. `codex exec --json "Run the shell command 'echo hello', then reply with just the word ok."`
   → `exec-json-turn.jsonl` (stdout, verbatim)
2. `codex exec resume --last --json "Reply with just the word again."`
   → `exec-json-resume.jsonl` (stdout, verbatim)

`rollout-exec-resume.jsonl` is the matching rollout for that thread (both
invocations append to the same rollout file), **trimmed to the token-accounting
records**: `session_meta`, `turn_context`, the `custom_tool_call`/
`custom_tool_call_output` pair, and the `task_started`/`token_count`/
`task_complete`/`thread_settings_applied` `event_msg`s. The developer/user/
assistant `message` items, `world_state` and `item_completed` records were
dropped (they carry machine-local memories, skill listings and paths). The
scratch working directory was rewritten to `/workspace/project` and the home
directory to `/workspace/home`; `base_instructions.text` truncated (original
length 17,730 chars). `ll-verify-private-refs` → PASS.

### Findings

| | stdout `turn.completed.usage` | rollout `token_count` |
|---|---|---|
| Invocation 1 (2 model requests) | `input 38945, cached 26752, cache_write 0, output 117` | request 1 `last` = `19404/7552/0/112`; request 2 `last` = `19541/19200/0/5`; `total` after request 2 = `38945/26752/0/117` |
| Invocation 2 (`resume --last`, 1 request) | `input 19559, cached 19328, cache_write 0, output 5` | `last` = `total` = `19559/19328/0/5` |

- **Scope is per invocation.** The live value is the thread-usage `total`
  (`codex-rs/exec/src/event_processor_with_jsonl_output.rs::usage_from_last_total`,
  tag `rust-v0.152.1`), which sums every model request in the invocation. The
  total is **not** restored by `exec resume`: the resumed invocation's `total`
  restarts at its own first request. `codex exec` shuts down after one
  `turn.completed`, so no live-path differencing is needed; `scope_kind =
  "invocation"` is correct.
- **Input is inclusive.** `cached_input_tokens (+ cache_write_input_tokens) <=
  input_tokens` on every observation; uncached = `input - cached - cache_write`.
- **`cache_write_input_tokens` is always emitted by 0.152.1.**
  `exec_events.rs::Usage` has `#[serde(default)]` (deserialization only) and no
  `skip_serializing_if`; both captures carry an explicit `0`. An omitted field
  therefore indicates an older CLI that predates the field, and stays unknown.
- **All-zero usage is not a measurement.** When no `ThreadTokenUsageUpdated`
  notification arrived before the turn completed, the producer emits
  `Usage::default()` (all zeros). A `turn.completed` whose components are all
  `0` is indistinguishable from "no usage observed".
- **Not covered by this capture:** a mid-invocation auto-compaction. The
  older rollout observations suggested `total_token_usage` could reset across
  compaction. The paired 0.158.0 resume/fork fixtures below show different
  cumulative behavior, so current live scope remains unknown without a
  producer-backed per-version boundary.

# `models-catalog.json` (ENH-3641)

Shape of `codex debug models` (refreshed catalog) as of `codex-cli 0.152.1`,
captured 2026-09-28: `{"models": [...]}` where each entry carries `slug`,
`priority`, `visibility` (`list`/`hide`) and `upgrade` (`null`, or
`{model, migration_markdown, retirement_at}`). **Synthetic, not a verbatim
capture**: slugs are placeholders, `base_instructions`/`migration_markdown` are
elided (the live entries carry ~35 unrelated large fields), and the
retirement dates are pinned to 2999/2020 so tests are time-stable. It is the
contract for `little_loops.cli.doctor._parse_codex_catalog`, which reads only
`slug`, `visibility`, `upgrade.model` and `upgrade.retirement_at`. `codex debug`
has no stability promise: re-check the live shape when `codex --version`
differs from `0.152.1`.

## Paired live/rollout join spike (ENH-3655, Codex 0.158.0)

Captured 2026-09-29 using an isolated `@openai/codex@0.158.0` npm invocation
(`npm view @openai/codex version` reported `0.158.0`). The machine's installed
`codex` remained 0.152.1. All three calls used `--ignore-user-config`,
`--ignore-rules`, `-m gpt-5.6-sol`, `--skip-git-repo-check`, `--json`, and an
empty scratch directory. The prompts requested one harmless word each:

1. `codex exec ... 'Reply with exactly alpha.'` →
   `exec-json-v0.158.0.jsonl`; thread `01a0ebf9-897a-7710-8dd9-436ba7483c83`.
2. `codex exec resume ... <thread> 'Reply with exactly beta.'` →
   `exec-json-resume-v0.158.0.jsonl`; same thread and same rollout file.
3. `codex exec fork ... <thread> 'Reply with exactly gamma.'` →
   `exec-json-fork-v0.158.0.jsonl`; new thread
   `01a0ebfa-3c21-76d1-98d3-f9aa76a00929` and a second rollout file.

`rollout-exec-resume-v0.158.0.jsonl` and `rollout-fork-v0.158.0.jsonl` are
their paired, trimmed rollouts. Each live `thread.started.thread_id` was used
to locate the sole newly written rollout filename under the producer's
`sessions/2026/09/29/` directory and checked against
`session_meta.payload.id` and `token_usage_record.payload.thread_id`. The
resume call appended to the first file. The fork file's `forked_from_id` and
`history_base.thread_id` point to the parent. These checks establish fixture
pairing; they do not establish an invocation-to-turn join for arbitrary data.

The files preserve native timestamps, ordinals, `turn_id`, `response_id`,
per-request `usage`, `turn_token_usage`, `thread_token_usage`, and the
`token_count` last/total usage fields. Live files retain only
`thread.started`, `turn.started`, and `turn.completed`. Rollouts retain only
`session_meta`, `turn_context`, `task_started`, `task_complete`,
`token_usage_record`, and `token_count`. The scratch path became
`/workspace/project`; account/user IDs, base instructions, message content,
rate limits, credit balance, repo metadata, and byte offsets were removed.
`ll-verify-private-refs scripts/tests/fixtures/codex/` passed. The records
are authentic producer output with these fields removed, not synthetic
tokens or identifiers.

| Call | Live `turn.completed` input/cache-read/cache-write/output | New rollout request usage | Rollout `thread_token_usage` |
|---|---:|---:|---:|
| exec | 15849/11264/0/5 | 15849/11264/0/5 | 15849/11264/0/5 |
| resume | 34365/26880/0/10 | 18516/15616/0/5 | 34365/26880/0/10 |
| fork | 52897/38144/0/15 | 18532/11264/0/5 | 52897/38144/0/15 |

**Finding: the proposed raw positional sum join is REFUTED on 0.158.0.**
The resume live total equals the two parent requests combined; the fork live
total equals both parent requests plus the fork request. Neither equals the
new request in its closed rollout turn span. This differs from the 0.152.1
resume capture above, whose live total restarted. The 0.158.0 fork has its
own `session_meta.payload.id` **and** `payload.session_id`; the parent is
`forked_from_id`, not `payload.session_id`. Its native ordinals start after
the parent's final ordinal. `token_usage_record` has `turn_id` and
`response_id`, while live JSON events still have no `turn_id` or response ID.

No interactive turn, actual concurrent resume, compaction, or subagent was
generated by this controlled capture. The spike test constructs missing,
extra, mismatched, concurrent-ambiguity, and window-change cases from the
real fixture records; those counterexamples are synthetic and do not claim
the producer exercised those paths. See ENH-3655 for the safe fallback.

### ENH-3532 synthetic replay variants

These three files are **synthetic transformations of the sanitized 0.158.0
parent rollout**, not additional producer captures:

- `rollout-mixed-v0.158.0-synthetic.jsonl` removes the first
  `token_usage_record` but retains its `token_count`. The old-shape-only
  request must remain as an unknown observation while the second native
  request remains measured.
- `rollout-page-a-v0.158.0-synthetic.jsonl` keeps the first closed turn;
  `rollout-page-b-v0.158.0-synthetic.jsonl` keeps the second, repeats the
  thread ID, supplies a distinct page header timestamp, and restarts native
  ordinals at zero. This challenges `(thread_id, ordinal)` uniqueness. The
  page timestamp is retained only as a diagnostic stream label; no producer
  proof establishes it as a durable request-key namespace.

The replay tests also construct duplicate, non-advancing-total, conflict,
incomplete, and malformed variants in temporary files. A native
`response_id` is used to collapse exact replayed copies in a full rebuild;
conflicting reuse is retained with unknown provenance. Global uniqueness of
`response_id` and a safe key for old `token_count`-only requests remain
unproven, so v56 creates no request-uniqueness index. Captures do not prove a
live invocation-to-rollout span join.

### Stop-hook timing capture

`stop-hook-v0.152.1.json`, `stop-observation-v0.152.1.json`, and
`stop-rollout-v0.152.1.jsonl` come from a separate `codex exec --json` run on
Codex CLI 0.152.1 with a session-level `Stop` command hook. The hook received
the native rollout path in `transcript_path`; while the hook ran, that file
already held the completed turn's `event_msg.token_count.info.last_token_usage`
(output 5). The observation fixture records this at-hook fact, and the
rollout fixture projects the matching `session_meta` and `token_count` rows.
Local paths, prompt text, and unrelated event content are omitted; the path
in the payload fixture is `__TRANSCRIPT_PATH__` for test substitution. The
capture proves a post-turn trigger for this CLI version, not a live-to-rollout
request identity join.
