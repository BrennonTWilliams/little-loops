# Built-in Hooks Guide

## When to Use This Guide

Read this when you want to understand what little-loops is doing in the background, tune a specific automatic behavior, or disable something you don't need. If hooks are working fine and you just want to get things done, you don't need this guide.

## What Is a Hook?

A hook is a lifecycle callback — a script that fires automatically at a specific moment in your Claude Code session. Hooks can load config, inject context, record events, or block tool calls. They run silently: you usually only notice them when they inject a message or deny an action.

All **built-in** little-loops hooks are declared in `hooks/hooks.json`. They fire through a thin adapter layer and route to Python handlers under `scripts/little_loops/hooks/`. You never need to invoke them directly. (Developers may also register their own local-only hooks in `.claude/settings.local.json` — gitignored, fire only in their own checkout.)

---

When you install the little-loops plugin, it registers a set of Claude Code lifecycle hooks. These fire silently as you work: loading config when a session starts, recording what ran, watching context usage, guarding issue-file integrity, and preserving state before compaction. This guide documents every one of them so nothing about your session is a mystery — and so you can disable anything you don't want.

## Table of Contents

- [How Hooks Work](#how-hooks-work)
- [The Lifecycle at a Glance](#the-lifecycle-at-a-glance)
- [Safe by Default](#safe-by-default)
- [SessionStart](#sessionstart)
- [UserPromptSubmit](#userpromptsubmit)
- [PreToolUse](#pretooluse)
- [PostToolUse](#posttooluse)
- [Stop](#stop)
- [PreCompact](#precompact)
- [Turning Hooks Off](#turning-hooks-off)
- [Configuration Reference](#configuration-reference)
- [See Also](#see-also)

---

## How Hooks Work

All hooks are declared in `hooks/hooks.json` and dispatched through a thin translation layer. Each shell adapter under `hooks/adapters/claude-code/` reads the host's native hook payload from stdin, pipes the JSON through a Python dispatcher (`python -m little_loops.hooks <intent>`), which routes to a **host-agnostic** handler module under `scripts/little_loops/hooks/` (e.g. `session_start.handle`), then translates the result back into Claude Code's hook contract (exit code + stderr feedback). A few lightweight hooks are pure bash with no Python handler.

This adapter→handler split is why the same hook logic runs across Claude Code, Codex, and other hosts — only the thin adapter changes per host. See [Write a Hook](../claude-code/write-a-hook.md) for authoring details.

**Two outcomes a hook can produce:**

- **Passive** — records data, injects context, or writes a state file. You don't notice it.
- **Blocking / feedback** — denies a tool call, or returns *exit 2* to surface a message the model must act on (e.g. "context is full, run `/ll:handoff`"). Only a handful of hooks do this, and they're called out explicitly below.

---

## The Lifecycle at a Glance

| Event | Hook | What it does | Can block? | Default |
|-------|------|--------------|:---------:|:-------:|
| **SessionStart** | session-start | Loads config + local overrides, injects a 7-day project digest, starts history backfill | — | on |
| **SessionStart** | sweep-stale-refs | Finds/fixes prose calling a `done` issue still "open" | — | on (report) |
| **UserPromptSubmit** | user-prompt-check | Optimizes vague prompts; records corrections & skill calls | — | on (opt-in for recording) |
| **PreToolUse** | check-duplicate-issue-id | Blocks creating an issue file whose ID collides cross-type | **yes** | on |
| **PreToolUse** | check-decisions-yaml | Blocks writing a corrupt `.ll/decisions.yaml` or `.ll/decisions.d/*.json` fragment from Claude-side Write/Edit | **yes** | on |
| **PreToolUse** | learning-tests gate | Warns (or blocks) on imports with no Learning Test record | warn/block | off |
| **PostToolUse** | install-nudge gate | Nudges `/ll:explore-api` when a package-install Bash command is detected | — | off |
| **PreToolUse** | scratch-pad-redirect | Redirects oversized Bash output to a scratch file | **yes** | off |
| **PostToolUse** | post-tool-use | Records tool & file events to `history.db` | — | opt-in |
| **PostToolUse** | context-monitor | Estimates context usage; nudges a handoff near the limit | exit 2 | on |
| **PostToolUse** | issue-completion-log | Appends a session log entry to issues marked `done` | — | on |
| **PostToolUse** | check-duplicate-issue-id-post | Deletes a just-written duplicate issue file (TOCTOU guard) | exit 2 | on |
| **PostToolUse** | issue-auto-commit | Auto-commits issue-file edits | — | off |
| **PostToolUse** | edit-batch-nudge | Nudges batching once per session after a run of consecutive unbatched single edits | exit 2 | on |
| **PostToolUse** | session-capture | Appends structured event record (file/task/git/error) to `.ll/ll-session-events.jsonl` | — | off |
| **Stop** | context-handoff-sentinel | Drops a sentinel if the session ended context-heavy | — | on |
| **Stop** | session-cleanup | Removes locks, state, scratch, orphaned worktrees | — | on |
| **SessionEnd** | scratch-cleanup | Prunes dead-PID scratch files from `.loops/tmp/scratch` | — | on |
| **PreCompact** | precompact | Snapshots task state before compaction (rubric-gated when `hooks.pre_compact.rubric.enabled: true`) | exit 2 | on |
| **PreCompact** | precompact-handoff | Writes session continuation prompt before compaction (passive path for `/ll:resume`) | — | on |

The rest of this guide walks each event in firing order.

### A Session from Hook's Perspective

Here's what fires during a typical session:

```
You start a session
  → SessionStart: loads config + local overrides, injects project digest
  → SessionStart (stale refs): reports any open-issue references pointing at issues the previous session marked done

You submit a prompt
  → UserPromptSubmit: optimizes vague prompts; records skill calls and corrections

You use the Write or Edit tool
  → PreToolUse (duplicate-ID guard): blocks if the issue ID collides with an existing one
  → PreToolUse (learning-tests gate, if enabled): warns if import has no proven record

You run a Bash install command (pip install, npm install, etc.)
  → PostToolUse (install-nudge gate, if learning_tests.enabled): suggests /ll:explore-api for the new package

The tool finishes
  → PostToolUse (analytics, if enabled): records tool + file events to history.db
  → PostToolUse (context monitor): estimates context usage; nudges handoff near the limit
  → PostToolUse (issue completion log): if issue was just marked done, appends session log

Context window fills up (Claude Code fires PreCompact before compacting)
  → PreCompact (precompact.sh): snapshots task state to .ll/ll-precompact-state.json
  → PreCompact (precompact-handoff.sh): reads state snapshot for idempotency, writes .ll/ll-continue-prompt.md; use /ll:resume after compaction to pick up work

Session ends
  → Stop (cleanup): removes locks, temp files, orphaned worktrees
  → SessionEnd (scratch cleanup): prunes dead-PID scratch files
```

---

## Safe by Default

The behaviors that **write data or change your repo** are **off until you opt in**:

- `analytics.enabled` (recording to `history.db`) — **off** at runtime (the JSON schema lists `default: true` for documentation/UI purposes, but the hook code's `feature_enabled()` helper treats an *absent* key as `false`, so a project with no explicit `analytics.enabled` in `.ll/ll-config.json` gets no analytics recording)
- `scratch_pad.enabled` (output redirection) — **off**
- `learning_tests.enabled` (import gate) — **off**
- `issues.auto_commit` (auto-committing issue files) — **off**
- `hooks.stale_ref_fix` — defaults to `report` (never edits files unless set to `auto`)

The behaviors that are **on by default** are non-destructive: they load config, estimate context, inject advisory reminders, protect issue-ID uniqueness, and clean up *this session's* temp files on exit. None of them modify your source code.

> **Note on defaults vs. this repo.** Defaults below are the **fresh-install schema defaults**. A given project's `.ll/ll-config.json` may tune them — for example, the little-loops repo itself enables `analytics.enabled` and lowers `context_monitor.auto_handoff_threshold` to 50.

---

## SessionStart

**Hook:** `session-start.sh` → `little_loops.hooks.session_start.handle`

Fires once when a Claude Code session begins. It:

1. Loads `.ll/ll-config.json` (or built-in defaults if absent).
2. Applies `.ll/ll.local.md` frontmatter overrides — deep-merged (nested objects merge, arrays replace, explicit `null` removes a key).
3. Cleans up the previous session's `.ll/ll-context-state.json`.
4. Injects the resolved config into the session as context.
5. **Optionally** injects a 7-day project digest from `history.db` (recently touched files, completed issues, recurring corrections) — this is the `## Recently touched` block you see at session start.
6. Spawns a one-shot background worker that backfills `history.db` from session JSONL logs.

**Gated by:** always loads config; the digest is gated by `history.session_digest.enabled` (default **true**), tunable via `history.session_digest.days` and `history.session_digest.char_cap`.

**You see:** the injected config/digest context, plus a `[little-loops] Config loaded: <path>` line on stderr. Never blocks.

### Sweep stale cross-issue references

**Hook:** `session-end.sh` → `little_loops.hooks.sweep_stale_refs.handle`

Collects every `status: done` issue, then scans open issues for prose that still calls those IDs "open", "in_progress", "active", or "blocked by". Behavior is controlled by `hooks.stale_ref_fix`:

- `report` (default) — lists findings on stderr, edits nothing
- `auto` — rewrites the stale phrasing in place (e.g. "is open" → "is done")

Runs once, at the start of each session — catching drift left over from the *previous* session's edits. Originally bound to `SessionEnd`, but Claude Code enforces a hard ~1.5s ceiling on `SessionEnd` hooks before killing them on any exit path (Ctrl+C, Ctrl+D, `/exit`), regardless of the configured `timeout` — an unfixed upstream bug (anthropics/claude-code#32712, #41577). The sweep's full-tree issue scan exceeds that ceiling on repos with a few thousand issue files, so it was being silently killed (printing `Hook cancelled`) on nearly every exit. Re-homed to `SessionStart`, where there's no forced-kill deadline, with the same detection value.

The dispatch intent stays `session_end` (host-agnostic) and the adapter file is still named `session-end.sh` — only the Claude Code `hooks.json` event binding changed. On Codex, which has no separate `SessionEnd` event, `session_end` is mapped onto its `Stop` event instead (ENH-2105).

---

## UserPromptSubmit

**Hook:** `user-prompt-check.sh` → `little_loops.hooks.user_prompt_submit.handle`

Fires every time you submit a prompt. Two independent jobs:

### Prompt optimization

If your prompt looks like it could be sharpened, the hook renders `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md` (in-package since FEAT-2274) and injects it as additional context so the model first clarifies intent. It **skips** prompts that are very short (<10 chars), start with `/`, `#`, or `?`, or begin with the bypass prefix.

To **customize the template**, place your own `optimize-prompt-hook.md` at `${CLAUDE_PLUGIN_ROOT}/hooks/prompts/optimize-prompt-hook.md`. When `CLAUDE_PLUGIN_ROOT` is set and that file exists, it takes precedence over the in-package version — allowing per-installation overrides without modifying the package.

- `prompt_optimization.enabled` (default **true**)
- `prompt_optimization.mode` — `quick` (default) or `thorough` (the latter can call the `prompt-optimizer` agent for codebase context)
- `prompt_optimization.confirm` (default **true**)
- `prompt_optimization.bypass_prefix` (default `*`) — prefix a prompt with `*` to send it through untouched
- `prompt_optimization.clarity_threshold` (default `6`, range 1–10)

Toggle interactively with `/ll:toggle-autoprompt`.

### Analytics recording

If analytics is enabled, it records user **corrections** (messages matching patterns like "no", "don't", "instead", "remember") and `/ll:*` skill invocations to `history.db`. Gated by `analytics.enabled` (schema default `true`, but effectively **off** at runtime unless set explicitly — see [Safe by Default](#safe-by-default)) and `analytics.capture.corrections` (default **true**).

**Never blocks.** Exit 0 always.

---

## PreToolUse

Four hooks run before a tool executes. These are the only place little-loops can **deny** an action outright.

### Duplicate issue-ID guard (blocks)

**Hook:** `check-duplicate-issue-id.sh` (pure bash)

On `Write`/`Edit` of a **new** `.md` file under `issues.base_dir` (default `.issues`), it checks whether the bare issue integer is already allocated under a different type (e.g. creating `FEAT-007` when `BUG-007` exists). If so it **denies** the write with:

> `[little-loops] Duplicate issue ID detected: ${ISSUE_ID} conflicts with ${EXISTING_BASENAME} — integer ${ISSUE_NUM} must be unique across all types (BUG/FEAT/ENH/EPIC). Use the next available ID.`

It allows edits to existing files and anything outside `.issues/`. Always on; uses an advisory lock that fails open.

### Decisions YAML guard (blocks)

**Hook:** `check-decisions-yaml.sh` (bash + Python)

On `Write`/`Edit` of either `.ll/decisions.yaml` or a `.ll/decisions.d/*.json` fragment (decisions storage is hybrid — a legacy flat file plus append-only per-entry fragments), stages the candidate content in a temporary config root and runs `ll-verify-decisions` (ENH-2589) against it. For `Write`, the candidate is `tool_input.content`; for `Edit`, it is the post-edit result reconstructed from `old_string` → `new_string` (with optional `replace_all`). Validating the **candidate** — not the current on-disk file — is what makes this belt effective: a `Write` that's about to corrupt the file passes against the still-valid existing file and slips past the validator otherwise.

Corruption (any `yaml.YAMLError`/`KeyError`/`ValueError` caught by `ll-verify-decisions`) emits the validator's single-line `ERROR:` on stderr and exits 2 (host-level block). Clean candidates exit 0 and let the host write through. Non-target paths and non-`Write`/`Edit` tools early-exit 0.

It complements the pre-commit hook (ENH-2590) and pytest CI gate (ENH-2591); only this host-layer belt fires for Claude-driven writes inside the session. Skips gracefully when `python3` or `ll-verify-decisions` is missing.

### Learning-tests discoverability gate (warn or block)

**Hook:** `pre-tool-use.sh` → `little_loops.hooks.learning_tests_gate.gate`

On `Write`/`Edit`, parses the file for `import`/`require` statements and checks each package against the [Learning Test Registry](LEARNING_TESTS_GUIDE.md). Behavior depends on mode:

- `learning_tests.enabled` (default **false** — the whole gate is off unless you turn it on)
- `learning_tests.discoverability.mode` — `off`, `warn` (default), or `block`
- `learning_tests.discoverability.skip_packages` (default `["std", "typing", "os", "sys"]`)

In `warn` mode it injects a hint and allows the write; in `block` mode it denies until a Learning Test exists.

### Scratch-pad redirection (redirects oversized Bash output)

**Hook:** `scratch-pad-redirect.sh` (pure bash)

Keeps large **Bash** output out of the conversation: it rewrites allowlisted commands to redirect output into `.loops/tmp/scratch/` and shows only the tail. Bash output is uncapped, so this is where context bloat actually comes from. The wrapped command's **exit status is preserved** (BUG-2491) — a failing `pytest`/`mypy` still surfaces as a non-zero exit, with the inline `tail` summary shown only. The rewrite re-raises `$?` in an outer subshell at `hooks/scripts/scratch-pad-redirect.sh:119` so the failure signal survives the redirection.

`Read` is **not** intercepted. Denying a `Read` would leave the `Edit`/`Write` "file has been read" precondition unsatisfied, edit-locking the file for the rest of the session (BUG-2357); and `Read` is already self-capping via `offset`/`limit` pagination, so there was nothing to gain. Use `Read` with `offset`/`limit` to page through large files.

- `scratch_pad.enabled` (default **false**)
- `scratch_pad.automation_contexts_only` (default **true**) — by default only fires inside automation sessions (`bypassPermissions`), so it never interrupts interactive work
- `scratch_pad.tail_lines` (default `20`)
- `scratch_pad.command_allowlist` (default `["cat", "pytest", "mypy", "ruff", "ls", "grep", "find"]`)

> `scratch_pad.threshold_lines` and `scratch_pad.file_extension_filters` are retained for config compatibility but no longer affect behavior (they only gated the removed `Read` interception).

### Install-nudge gate (warn, PostToolUse)

**Hook:** `post-tool-use.sh` → `little_loops.hooks.post_tool_use.handle` → `little_loops.hooks.install_learning_gate.gate`

After a `Bash` tool call that just installed a package (`pip install`, `pip3 install`, `uv pip install`, `npm install`, `pnpm add`, `yarn add`), this hook emits a one-line nudge suggesting you run `/ll:explore-api` to prove the newly-installed package's API assumptions before writing integration code:

> `[ll: new dependency] No learning test for "stripe". Consider: /ll:explore-api "stripe"`

Never blocks (always advisory, exit 0). Gated by `learning_tests.enabled` (default **false**) — the nudge is silent unless learning tests are enabled. No additional configuration keys beyond the parent `learning_tests` block.

> **Note on lifecycle**: although this hook reads from the Bash tool result, it is wired as PostToolUse (not PreToolUse) because the package manager must already have produced a side-effect before a meaningful "you just installed X" nudge can fire.

---

## PostToolUse

Seven hooks run after each tool call.

### Tool & file analytics

**Hook:** `post-tool-use.sh` → `little_loops.hooks.post_tool_use.handle`

Records a `tool_events` row (tool name, bytes in/out, cache-hit, args hash) for every call, and a `file_events` row when a tool touches a file. Gated by `analytics.enabled` (default **false**); file capture is further gated by `analytics.capture.file_events` (default **true**). Writes to `.ll/history.db`. Never blocks. See the [History & Session Guide](HISTORY_SESSION_GUIDE.md).

### Context monitor (exit 2 near the limit)

**Hook:** `context-monitor.sh` (pure bash + jq)

The hook most users notice. After each tool call it estimates how much context you've consumed — heuristically per tool, refined against authoritative token counts from the transcript when available — and tracks it in `.ll/ll-context-state.json`. When usage crosses the threshold it emits a rate-limited (once/60s) reminder via **exit 2**:

> `[ll] Context ~N% used (tokens/limit estimated). Run /ll:handoff to preserve your work…`

It also resets its estimate after a compaction event.

- `context_monitor.enabled` (default **true**)
- `context_monitor.auto_handoff_threshold` (default `80`, range 50–95)
- `context_monitor.context_limit_estimate` (default `0` = auto-detect model limit; `[1m]`-suffixed model ids resolve to 1M by identifier, or the transcript baseline exceeding the resolved limit auto-upgrades to 1000000 as a fallback)
- `context_monitor.estimate_weights.*` and `context_monitor.post_compaction_percent` (default `30`) for fine-tuning

This pairs with [Session Handoff](SESSION_HANDOFF.md).

### Issue completion log

**Hook:** `issue-completion-log.sh`

On `Write` of an issue `.md` whose frontmatter is `status: done`, appends a session-log entry to the issue file for historical traceability, then fires `ll-issues decisions extract-from-completed --issue <ID> --min-confidence 0.8` in a background subshell to mine the closed issue for generalizable rules and append them to the decisions log as `.ll/decisions.d/*.json` fragments (append-only; folded into `.ll/decisions.yaml` on compaction). The extraction runs asynchronously (fire-and-forget), so the hook exits immediately regardless of LLM latency. Always on; silent. Never blocks.

### Duplicate issue-ID cleanup (TOCTOU race guard, exit 2)

TOCTOU — "time-of-check to time-of-use" — is the race window between checking a condition and acting on it.

**Hook:** `check-duplicate-issue-id-post.sh` (pure bash)

The belt-and-suspenders partner to the PreToolUse guard: after a `Write` lands, it re-checks for an ID collision and, if the just-written file is the duplicate, **deletes it** and returns exit 2:

> `[little-loops] Duplicate ID: ${FILENAME} conflicts with ${DUPLICATE_BASENAME} (integer ${ISSUE_NUM} already allocated). File removed — call ll-issues next-id again for a unique ID.`

Always on. Closes the race window where two writes pick the same ID concurrently.

### Issue auto-commit

**Hook:** `issue-auto-commit.sh` (pure bash)

If enabled, stages and commits issue-file changes (matching `P[0-5]-(BUG|FEAT|ENH|EPIC)-NNN-*.md`) with a conventional message. It **skips** the commit if you have other staged/unstaged changes, so it never sweeps unrelated work into a commit.

- `issues.auto_commit` (default **false**)
- `issues.auto_commit_prefix` (default `chore(issues)`)

Never blocks.

### Edit-batch nudge

**Hook:** `edit-batch-nudge.sh` → `little_loops.hooks.edit_batch_nudge.handle`

After an `Edit`, `Write`, or `MultiEdit` call, injects a short reminder to batch
independent edits into a single turn (parallel `Edit`/`Write` calls, or
`MultiEdit` for one file) rather than one edit per turn — fewer round-trips means
less avoidable token cost re-reading the conversation prefix. Returns exit 2 so
the reminder reaches the model's context (a Tier 0 token-cost quick-win from
EPIC-2456).

The nudge is **stateful** and **once-per-session**. Within a session, it fires
only once a run of consecutive *unbatched* single edits reaches the threshold
(default 3); after firing, a sticky `nudged: true` latch suppresses every
subsequent nudge for the lifetime of `session_id` — so it stays silent even if
the user reverts to unbatched edits later in the same session. A new session
re-arms the latch. Because `PostToolUse` carries no turn id, "unbatched" is
inferred from the wall-clock gap between hook fires: edits closer than
`_BATCH_WINDOW_SECONDS` (default 3s) are treated as one batched turn and reset
the run counter, while `MultiEdit` always resets it. The state file at
`.ll/ll-edit-batch-state.json` carries `{session_id, run, last_ts, nudged}`;
`nudged` is `false` pre-fire and flips to `true` on first fire. All state I/O is
best-effort and degrades to a silent pass-through on failure. Fires for the
three edit tools only; all other tools pass through. On by default; the matcher
is host-agnostic and mirrored to Codex. (ENH-2503)

---

## Stop

Two hooks run after each assistant turn (Claude Code's `Stop` event). Both are advisory and must never fail.

### Context handoff sentinel

**Hook:** `context-handoff-sentinel.sh` (pure bash)

If the session ended context-heavy (≥ ~50% estimated) and no handoff was completed, it writes a `.ll/ll-context-handoff-needed` sentinel so an automation worker (or your next session) knows to prompt for an explicit handoff. Gated by `context_monitor.enabled`. Silent.

### Session cleanup

**Hook:** `session-cleanup.sh` (pure bash)

Removes this session's lock and context-state files, and prunes orphaned git worktrees under `parallel.worktree_base` (default `.worktrees`) — while skipping any worktree owned by a **live** parallel worker. This is what keeps interrupted `ll-parallel` runs from leaving debris. Note there is a separate `automation.worktree_base` key (also default `.worktrees`) used by `ll-auto` and FSM sub-loop worktrees (`Config.get_worktree_base()`); this Stop-hook cleanup reads `parallel.worktree_base` specifically, not `automation.worktree_base`. (Scratch cleanup now lives in `scratch-cleanup.sh` on SessionEnd — see BUG-2420.) Always on.

---

## SessionEnd

Runs **once, when the session terminates** (Claude Code's `SessionEnd` event) — not per turn. Advisory; must never fail.

### Scratch-pad cleanup

**Hook:** `scratch-cleanup.sh` (pure bash)

Prunes stale files from `.loops/tmp/scratch` whose owning PID is no longer alive, leaving untouched any file a still-running concurrent session/`ll-loop`/`ll-auto` process owns. **Only files matching the `${SAFE_NAME}-<pid>.txt` shape produced by `scratch-pad-redirect.sh` are eligible for removal** — user-typed scratch files (no `-<pid>` suffix) are preserved unconditionally (BUG-2525). Always on.

> Keep `SessionEnd` handlers fast — Claude Code enforces a hard ~1.5s ceiling on this event before killing the hook on any exit path (Ctrl+C, Ctrl+D, `/exit`), regardless of the configured `timeout` (unfixed upstream: anthropics/claude-code#32712, #41577). This is why the stale-ref sweep lives under [SessionStart](#sessionstart) instead.

---

## PreCompact

**Hook:** `precompact.sh` → `little_loops.hooks.pre_compact.handle`

Fires just before Claude Code compacts the conversation. It snapshots task state to `.ll/ll-precompact-state.json` — timestamp, transcript path, a context-state snapshot, and up to 5 recently-touched plan files — then signals via **exit 2**:

> `[ll] Task state preserved before context compaction. Check .ll/ll-precompact-state.json if resuming work.`

This is what lets a post-compaction context pick up mid-task. Always on; writes are atomic with a fail-open advisory lock. See [Session Handoff](SESSION_HANDOFF.md).

**Rubric-gated timing (opt-in):** When `hooks.pre_compact.rubric.enabled: true`, the hook first evaluates four structural conditions over the recent transcript before writing state. If any condition fails, the hook returns exit 0 without writing state — the compaction still happens but without a continuation snapshot. Enable with:

```json
{ "hooks": { "pre_compact": { "rubric": { "enabled": true } } } }
```

The four conditions (each requires evidence in the transcript; absence → defer):
1. **closed_unit** — reasoning unit has a definite resolution (default signals: `done`, `completed`, `fixed`, `resolved`)
2. **reducible** — content can be summarised to a few facts (default signals: `in summary`, `to summarize`, `overall`)
3. **progress** — something changed since the last compact (default signals: `changed`, `updated`, `modified`, `implemented`)
4. **not_stuck** — no stuck-loop signals detected (default signals: `same error`, `still failing`, `repeat`)

Signal lists are configurable via `hooks.pre_compact.rubric.signals.*`. Disabled by default; when disabled (or on any transcript-read error), falls back to the original threshold-only behaviour.

**Hook:** `precompact-handoff.sh` → `little_loops.hooks.pre_compact_handoff.handle`

Fires as a second PreCompact handler, after `precompact.sh`. Reads `.ll/ll-precompact-state.json` as an idempotency guard (skips if no state snapshot was written by `precompact.sh`), then writes `.ll/ll-continue-prompt.md` atomically with a 3s advisory lock, returning **exit 2**:

> `[ll] Session continuation prompt written to .ll/ll-continue-prompt.md`

**Two content paths**: when `.ll/ll-session-events.jsonl` is present (written by the `session-capture.sh` PostToolUse hook when `session_capture.enabled: true`), the handler builds the continuation prompt from structured event data — deduplicating file edits by subject and surfacing only unresolved errors. When the event log is absent, it falls back to a git-diff/loop-state snapshot. Enable `session_capture.enabled` to get richer, event-structured continuation prompts; the fallback still produces a usable prompt without it.

Use `/ll:resume` after compaction to re-inject the continuation prompt. Always on; passive counterpart to the active `/ll:handoff` command. See [Session Handoff](SESSION_HANDOFF.md).

---

## Turning Hooks Off

Most behavior is controlled by config keys in `.ll/ll-config.json` (or your gitignored `.ll/ll.local.md` for local-only overrides). Set the gate to `false`:

```json
{
  "prompt_optimization": { "enabled": false },
  "context_monitor": { "enabled": false },
  "history": { "session_digest": { "enabled": false } }
}
```

To **fully unregister** a hook (including the always-on issue-ID guards and session cleanup), edit `hooks/hooks.json` and remove its entry — but note the issue-ID guards and cleanup exist to prevent real corruption, so prefer leaving them on.

A few quick controls:

- `/ll:toggle-autoprompt` — flip prompt optimization without editing config
- `/ll:configure` — interactive config editor
- Prefix any prompt with `*` — bypass prompt optimization for that message only

---

## Configuration Reference

| Config key | Hook | Default | Effect |
|------------|------|:-------:|--------|
| `history.session_digest.enabled` | SessionStart | `true` | Inject 7-day project digest |
| `prompt_optimization.enabled` | UserPromptSubmit | `true` | Optimize vague prompts |
| `prompt_optimization.mode` | UserPromptSubmit | `quick` | `quick` or `thorough` |
| `prompt_optimization.bypass_prefix` | UserPromptSubmit | `*` | Per-prompt bypass char |
| `analytics.enabled` | UserPromptSubmit, PostToolUse | `false` | Record events to `history.db` |
| `analytics.capture.corrections` | UserPromptSubmit | `true` | Record user corrections (needs `analytics.enabled`) |
| `analytics.capture.file_events` | PostToolUse | `true` | Record file events (needs `analytics.enabled`) |
| `learning_tests.enabled` | PreToolUse | `false` | Enable the import gate |
| `learning_tests.discoverability.mode` | PreToolUse | `warn` | `off` / `warn` / `block` |
| `hooks.pre_compact.rubric.enabled` | PreCompact | `false` | Enable rubric-gated compaction timing |
| `hooks.pre_compact.rubric.hard_ceiling_pct` | PreCompact | `0.95` | Reserved: hard ceiling fraction (not yet enforced) |
| `scratch_pad.enabled` | PreToolUse | `false` | Redirect oversized Bash output |
| `scratch_pad.automation_contexts_only` | PreToolUse | `true` | Only fire in automation |
| `context_monitor.enabled` | PostToolUse, Stop | `true` | Track context usage |
| `context_monitor.auto_handoff_threshold` | PostToolUse | `80` | % at which to nudge handoff |
| `issues.auto_commit` | PostToolUse | `false` | Auto-commit issue files |
| `session_capture.enabled` | PostToolUse | `false` | Append per-tool structured event records to `.ll/ll-session-events.jsonl` |
| `issues.base_dir` | (all issue hooks) | `.issues` | Issue directory |
| `hooks.stale_ref_fix` | SessionStart | `report` | `report` or `auto` |
| `parallel.worktree_base` | Stop | `.worktrees` | Worktree cleanup scope (distinct from `automation.worktree_base`, which `ll-auto`/FSM sub-loops use and this hook does not read) |

Full schema and substitution rules: [Configuration Reference](../reference/CONFIGURATION.md).

### Common Combinations

| Combination | Interaction |
|-------------|------------|
| `analytics.enabled` + `history.session_digest.enabled` | Complementary — analytics writes the data; digest reads it back at session start. Enable both for the full historical context experience. |
| `scratch_pad.enabled` + `learning_tests.enabled` | Compatible — scratch pad affects output size; learning tests affect import gates. No interaction. |
| `scratch_pad.enabled` + `scratch_pad.automation_contexts_only: true` | Safe default — scratch pad only fires inside automation sessions (`bypassPermissions`), never during interactive work. |
| `issues.auto_commit` + manual `/ll:commit` | Redundant — `auto_commit` will commit issue files automatically after each change; `/ll:commit` is for source code. Keep `auto_commit: false` if you want to review all changes in one commit. |

---

## See Also

- [Configuration Reference](../reference/CONFIGURATION.md) — every config key and its schema
- [Session Handoff](SESSION_HANDOFF.md) — the context-monitor / precompact / sentinel story end to end
- [History & Session Guide](HISTORY_SESSION_GUIDE.md) — what the analytics hooks record and how to query it
- [Learning Tests Guide](LEARNING_TESTS_GUIDE.md) — the registry behind the PreToolUse import gate
- [Write a Hook](../claude-code/write-a-hook.md) — author your own `LLHookIntentExtension`
- [Event Schema Reference](../reference/EVENT-SCHEMA.md) — `LLHookEvent` / `LLHookResult` wire format
