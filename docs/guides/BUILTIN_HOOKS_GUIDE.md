# Built-in Hooks Guide

Everything little-loops does automatically in the background — and the exact config key that turns each behavior on or off.

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
| **UserPromptSubmit** | user-prompt-check | Optimizes vague prompts; records corrections & skill calls | — | on (opt-in for recording) |
| **PreToolUse** | check-duplicate-issue-id | Blocks creating an issue file whose ID collides cross-type | **yes** | on |
| **PreToolUse** | learning-tests gate | Warns (or blocks) on imports with no Learning Test record | warn/block | off |
| **PreToolUse** | scratch-pad-redirect | Redirects oversized Bash/Read output to a scratch file | **yes** | off |
| **PostToolUse** | post-tool-use | Records tool & file events to `history.db` | — | opt-in |
| **PostToolUse** | context-monitor | Estimates context usage; nudges a handoff near the limit | exit 2 | on |
| **PostToolUse** | issue-completion-log | Appends a session log entry to issues marked `done` | — | on |
| **PostToolUse** | check-duplicate-issue-id-post | Deletes a just-written duplicate issue file (TOCTOU guard) | exit 2 | on |
| **PostToolUse** | issue-auto-commit | Auto-commits issue-file edits | — | off |
| **Stop** | context-handoff-sentinel | Drops a sentinel if the session ended context-heavy | — | on |
| **Stop** | session-cleanup | Removes locks, state, scratch, orphaned worktrees | — | on |
| **Stop** | sweep-stale-refs | Finds/fixes prose calling a `done` issue still "open" | — | on (report) |
| **PreCompact** | precompact | Snapshots task state before compaction | exit 2 | on |

The rest of this guide walks each event in firing order.

---

## Safe by Default

The behaviors that **write data or change your repo** are **off until you opt in**:

- `analytics.enabled` (recording to `history.db`) — **off**
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

---

## UserPromptSubmit

**Hook:** `user-prompt-check.sh` → `little_loops.hooks.user_prompt_submit.handle`

Fires every time you submit a prompt. Two independent jobs:

### Prompt optimization

If your prompt looks like it could be sharpened, the hook renders `hooks/prompts/optimize-prompt-hook.md` and injects it as additional context so the model first clarifies intent. It **skips** prompts that are very short (<10 chars), start with `/`, `#`, or `?`, or begin with the bypass prefix.

- `prompt_optimization.enabled` (default **true**)
- `prompt_optimization.mode` — `quick` (default) or `thorough` (the latter can call the `prompt-optimizer` agent for codebase context)
- `prompt_optimization.confirm` (default **true**)
- `prompt_optimization.bypass_prefix` (default `*`) — prefix a prompt with `*` to send it through untouched
- `prompt_optimization.clarity_threshold` (default `6`, range 1–10)

Toggle interactively with `/ll:toggle-autoprompt`.

### Analytics recording

If analytics is enabled, it records user **corrections** (messages matching patterns like "no", "don't", "instead", "remember") and `/ll:*` skill invocations to `history.db`. Gated by `analytics.enabled` (default **false**) and `analytics.capture.corrections` (default **true**).

**Never blocks.** Exit 0 always.

---

## PreToolUse

Three hooks run before a tool executes. These are the only place little-loops can **deny** an action outright.

### Duplicate issue-ID guard (blocks)

**Hook:** `check-duplicate-issue-id.sh` (pure bash)

On `Write`/`Edit` of a **new** `.md` file under `issues.base_dir` (default `.issues`), it checks whether the bare issue integer is already allocated under a different type (e.g. creating `FEAT-007` when `BUG-007` exists). If so it **denies** the write with:

> `[little-loops] Duplicate ID detected: … conflicts with … Use the next available ID.`

It allows edits to existing files and anything outside `.issues/`. Always on; uses an advisory lock that fails open.

### Learning-tests discoverability gate (warn or block)

**Hook:** `pre-tool-use.sh` → `little_loops.hooks.learning_tests_gate.gate`

On `Write`/`Edit`, parses the file for `import`/`require` statements and checks each package against the [Learning Test Registry](LEARNING_TESTS_GUIDE.md). Behavior depends on mode:

- `learning_tests.enabled` (default **false** — the whole gate is off unless you turn it on)
- `learning_tests.discoverability.mode` — `off`, `warn` (default), or `block`
- `learning_tests.discoverability.skip_packages` (default `["std", "typing", "os", "sys"]`)

In `warn` mode it injects a hint and allows the write; in `block` mode it denies until a Learning Test exists.

### Scratch-pad redirection (blocks oversized reads)

**Hook:** `scratch-pad-redirect.sh` (pure bash)

Keeps large tool output out of the conversation. On `Bash`, it rewrites allowlisted commands to redirect output into `.loops/tmp/scratch/` and shows only the tail. On `Read`, if the file exceeds the line threshold it **denies** the read and tells you to save it to scratch instead.

- `scratch_pad.enabled` (default **false**)
- `scratch_pad.automation_contexts_only` (default **true**) — by default only fires inside automation sessions (`bypassPermissions`), so it never interrupts interactive work
- `scratch_pad.threshold_lines` (default `200`), `scratch_pad.tail_lines` (default `20`)
- `scratch_pad.command_allowlist` (default `["cat", "pytest", "mypy", "ruff", "ls", "grep", "find"]`)
- `scratch_pad.file_extension_filters` (default `[".log", ".txt", ".json", ".md", ".py", ".ts", ".tsx", ".js"]`)

---

## PostToolUse

Five hooks run after each tool call.

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
- `context_monitor.context_limit_estimate` (default `0` = auto-detect model limit; upgrades to 1M when the transcript baseline indicates it)
- `context_monitor.estimate_weights.*` and `context_monitor.post_compaction_percent` (default `30`) for fine-tuning

This pairs with [Session Handoff](SESSION_HANDOFF.md).

### Issue completion log

**Hook:** `issue-completion-log.sh`

On `Write` of an issue `.md` whose frontmatter is `status: done`, appends a session-log entry to the issue file for historical traceability. Always on; silent. Never blocks.

### Duplicate issue-ID cleanup (TOCTOU guard, exit 2)

**Hook:** `check-duplicate-issue-id-post.sh` (pure bash)

The belt-and-suspenders partner to the PreToolUse guard: after a `Write` lands, it re-checks for an ID collision and, if the just-written file is the duplicate, **deletes it** and returns exit 2:

> `[little-loops] Duplicate ID: … File removed — call ll-issues next-id again for a unique ID.`

Always on. Closes the race window where two writes pick the same ID concurrently.

### Issue auto-commit

**Hook:** `issue-auto-commit.sh` (pure bash)

If enabled, stages and commits issue-file changes (matching `P[0-5]-(BUG|FEAT|ENH|EPIC)-NNN-*.md`) with a conventional message. It **skips** the commit if you have other staged/unstaged changes, so it never sweeps unrelated work into a commit.

- `issues.auto_commit` (default **false**)
- `issues.auto_commit_prefix` (default `chore(issues)`)

Never blocks.

---

## Stop

Three hooks run when the session ends. All are advisory and must never fail.

### Context handoff sentinel

**Hook:** `context-handoff-sentinel.sh` (pure bash)

If the session ended context-heavy (≥ ~50% estimated) and no handoff was completed, it writes a `.ll/ll-context-handoff-needed` sentinel so an automation worker (or your next session) knows to prompt for an explicit handoff. Gated by `context_monitor.enabled`. Silent.

### Session cleanup

**Hook:** `session-cleanup.sh` (pure bash)

Removes this session's lock and context-state files, clears `.loops/tmp/scratch`, and prunes orphaned git worktrees under `parallel.worktree_base` (default `.worktrees`) — while skipping any worktree owned by a **live** parallel worker. This is what keeps interrupted `ll-parallel` runs from leaving debris. Always on.

### Sweep stale cross-issue references

**Hook:** `session-end.sh` → `little_loops.hooks.sweep_stale_refs.handle`

Collects every `status: done` issue, then scans open issues for prose that still calls those IDs "open", "in_progress", "active", or "blocked by". Behavior is controlled by `hooks.stale_ref_fix`:

- `report` (default) — lists findings on stderr, edits nothing
- `auto` — rewrites the stale phrasing in place (e.g. "is open" → "is done")

Always runs; defaults to the non-destructive `report` mode.

---

## PreCompact

**Hook:** `precompact.sh` → `little_loops.hooks.pre_compact.handle`

Fires just before Claude Code compacts the conversation. It snapshots task state to `.ll/ll-precompact-state.json` — timestamp, transcript path, a context-state snapshot, and up to 5 recently-touched plan files — then signals via **exit 2**:

> `[ll] Task state preserved before context compaction. Check .ll/ll-precompact-state.json if resuming work.`

This is what lets a post-compaction context pick up mid-task. Always on; writes are atomic with a fail-open advisory lock. See [Session Handoff](SESSION_HANDOFF.md).

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
| `scratch_pad.enabled` | PreToolUse | `false` | Redirect oversized output |
| `scratch_pad.automation_contexts_only` | PreToolUse | `true` | Only fire in automation |
| `scratch_pad.threshold_lines` | PreToolUse | `200` | Read-size limit |
| `context_monitor.enabled` | PostToolUse, Stop | `true` | Track context usage |
| `context_monitor.auto_handoff_threshold` | PostToolUse | `80` | % at which to nudge handoff |
| `issues.auto_commit` | PostToolUse | `false` | Auto-commit issue files |
| `issues.base_dir` | (all issue hooks) | `.issues` | Issue directory |
| `hooks.stale_ref_fix` | Stop | `report` | `report` or `auto` |
| `parallel.worktree_base` | Stop | `.worktrees` | Worktree cleanup scope |

Full schema and substitution rules: [Configuration Reference](../reference/CONFIGURATION.md).

---

## See Also

- [Configuration Reference](../reference/CONFIGURATION.md) — every config key and its schema
- [Session Handoff](SESSION_HANDOFF.md) — the context-monitor / precompact / sentinel story end to end
- [History & Session Guide](HISTORY_SESSION_GUIDE.md) — what the analytics hooks record and how to query it
- [Learning Tests Guide](LEARNING_TESTS_GUIDE.md) — the registry behind the PreToolUse import gate
- [Write a Hook](../claude-code/write-a-hook.md) — author your own `LLHookIntentExtension`
- [Event Schema Reference](../reference/EVENT-SCHEMA.md) — `LLHookEvent` / `LLHookResult` wire format
